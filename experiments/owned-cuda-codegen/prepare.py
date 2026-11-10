"""Prepare an experimental owned provider for a checked-AST CUDA scalar root."""
import argparse
import ctypes as C
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def compile_ptx(library, shader, output, compute):
    """NVRTC needs no initialized CUDA driver; PTX remains an explicit build input."""
    library_pin = sha(library)
    if os.name == "nt":
        directory = os.add_dll_directory(str(library.parent))
        rtc = C.CDLL(str(library), winmode=0x1100)
    else:
        directory = None
        rtc = C.CDLL(str(library))

    def bind(name, types):
        function = getattr(rtc, name)
        function.argtypes, function.restype = types, C.c_int
        return function

    def checked(function, *values):
        code = function(*values)
        if code:
            raise RuntimeError(function.__name__ + " returned " + str(code))

    version = bind("nvrtcVersion", [C.POINTER(C.c_int), C.POINTER(C.c_int)])
    create = bind("nvrtcCreateProgram", [C.POINTER(C.c_void_p), C.c_char_p, C.c_char_p, C.c_int, C.c_void_p, C.c_void_p])
    compile_program = bind("nvrtcCompileProgram", [C.c_void_p, C.c_int, C.POINTER(C.c_char_p)])
    log_size = bind("nvrtcGetProgramLogSize", [C.c_void_p, C.POINTER(C.c_size_t)])
    get_log = bind("nvrtcGetProgramLog", [C.c_void_p, C.c_void_p])
    ptx_size = bind("nvrtcGetPTXSize", [C.c_void_p, C.POINTER(C.c_size_t)])
    get_ptx = bind("nvrtcGetPTX", [C.c_void_p, C.c_void_p])
    destroy = bind("nvrtcDestroyProgram", [C.POINTER(C.c_void_p)])
    major, minor, program = C.c_int(), C.c_int(), C.c_void_p()
    try:
        checked(version, C.byref(major), C.byref(minor))
        if major.value < 12:
            raise RuntimeError("NVRTC 12+ is required for generated CUDA C++20")
        checked(create, C.byref(program), shader.read_bytes(), b"kernel.cu", 0, None, None)
        options = [b"--std=c++20", ("--gpu-architecture=compute_" + str(compute)).encode(), b"--generate-line-info"]
        result = compile_program(program, len(options), (C.c_char_p * len(options))(*options))
        size = C.c_size_t()
        checked(log_size, program, C.byref(size))
        if not 1 <= size.value <= 1024 * 1024:
            raise RuntimeError("NVRTC log exceeds its bounded capture")
        log = C.create_string_buffer(size.value)
        checked(get_log, program, log)
        (output / "nvrtc.log").write_bytes(log.raw)
        if result:
            raise RuntimeError("NVRTC rejected generated code; inspect nvrtc.log, status " + str(result))
        checked(ptx_size, program, C.byref(size))
        if not 1 <= size.value <= 32 * 1024 * 1024:
            raise RuntimeError("NVRTC PTX exceeds its bound")
        ptx = C.create_string_buffer(size.value)
        checked(get_ptx, program, ptx)
        if ptx.raw[-1:] != b"\0" or b"\0" in ptx.raw[:-1]:
            raise RuntimeError("NVRTC returned malformed PTX")
        (output / "kernel.ptx").write_bytes(ptx.raw)
        if sha(library) != library_pin:
            raise RuntimeError("NVRTC library changed during compilation")
        return {"NVRTC_sha256": library_pin, "version": [major.value, minor.value],
                "options": [value.decode() for value in options], "PTX_sha256": sha(output / "kernel.ptx")}
    finally:
        if program:
            checked(destroy, C.byref(program))
        if directory:
            directory.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "source-project", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    for name in ["emitter", "frontend-archive"]:
        parser.add_argument("--" + name, type=Path, help="Optional standalone developer harness; both options must be supplied together")
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--source-only", action="store_true")
    parser.add_argument("--acceptance-gate", action="store_true", help="Compile a bounded GPU delay kernel for explicit cancellation/deadline tests")
    parser.add_argument("--cxx", type=Path)
    parser.add_argument("--nvrtc", type=Path)
    parser.add_argument("--compute", type=int, default=52)
    parser.add_argument("--index", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.index < 64 or not 52 <= args.compute <= 999:
        parser.error("select GPU ordinal 0..63 and a supported compute target >=52")
    if not args.source_only and (platform.system() not in {"Windows", "Linux"} or not args.nvrtc):
        parser.error("native preparation requires Windows/Linux and explicit NVRTC; use --source-only on other hosts")
    if bool(args.emitter) != bool(args.frontend_archive):
        parser.error("--emitter and --frontend-archive must be supplied together")
    compiler, resources, project = [p.resolve(strict=True) for p in [args.compiler, args.resources, args.source_project]]
    emitter = args.emitter.resolve(strict=True) if args.emitter else None
    frontend = args.frontend_archive.resolve(strict=True) if args.frontend_archive else None
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    evidence, generation, inputs = out / "preparation", out / "generation", out / "preparation/inputs"
    for path in [evidence, generation, inputs]:
        path.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEX_")}
    env.update(NEX_RESOURCE_DIR=str(resources), PYTHONDONTWRITEBYTECODE="1")
    commands = []
    pin_files = {"compiler": compiler}
    if emitter:
        pin_files.update(emitter=emitter, frontend=frontend)
    pins = {name: sha(path) for name, path in pin_files.items()}

    def guard():
        assert pins == {name: sha(path) for name, path in pin_files.items()}

    def run(label, argv, cwd=out):
        guard()
        row = {"label": label, "argv": list(map(str, argv)), "cwd": str(cwd)}
        commands.append(row)
        write(evidence / "commands.json", commands)
        result = subprocess.run(row["argv"], cwd=cwd, env=env, capture_output=True, timeout=600)
        for name, data in [("stdout", result.stdout), ("stderr", result.stderr)]:
            (evidence / (label + "." + name)).write_bytes(data)
        row["exit_code"] = result.returncode
        write(evidence / "commands.json", commands)
        if result.returncode:
            raise RuntimeError(label + " failed; inspect retained stdout/stderr")
        guard()
        return result.stdout

    try:
        index = json.loads(run("index", [compiler, "describe", "--kind", "index", "--json"]))
        descriptor = json.loads(run("descriptor", [compiler, "describe", "--json"]))
        doctor = json.loads(run("doctor", [compiler, "doctor", "--json"]))
        assert index["language"] == "0.28" and doctor["language"] == "0.28"
        assert descriptor["source_resources"]["source_task_bridge"]
        assert descriptor["resource_regions"]["dependency_graph"]["C_table_parent_creation"]
        assert descriptor["foreign_trap_reporting"]["C_table_prefix"] == "NEX_FFI_V1_TRAP_SIZE"
        if emitter:
            generated = json.loads(run("generate", [emitter, project, args.symbol, "columns", generation / "kernel.cu"], project))
            assert generated["schema"] == "nex.experimental-cuda-emission/1" and not generated["integrated_compiler_CLI"]
            if generated["frontend_archive_sha256"] != pins["frontend"]:
                raise RuntimeError("emitter and selected frontend archive identities differ")
            functions = generated["functions"]
        else:
            capability = descriptor["gpu_codegen"]["cuda"]
            assert capability["source_support"] and capability["schema"] == "nex.cuda-emission/1"
            generated = json.loads(run("generate", [compiler, "emit", "--kind", "cuda", "--entry", args.symbol,
                "--input-layout", "columns", "-o", generation / "kernel.cu", "--json"], project))
            assert generated["schema"] in capability.get("schemas", [capability["schema"]]) and generated["kind"] == "cuda"
            assert all(generated[name] == index[name] for name in ["compiler_build", "descriptor_hash", "toolchain", "language"])
            functions = generated["function_map"]
            assert generated["functions"] == {row["name"]: row["hash"] for row in functions}
        write(generation / "report.json", generated)
        assert generated["ok"] and generated["language"] == "0.28" and generated["input_layout"] == "columns"
        assert generated["kernel"] == "nex_generated_cuda_map"
        assert not generated["driver_initialized"] and not generated["device_executed"]
        assert generated["shader_sha256"] == sha(generation / "kernel.cu")
        assert generated["source_bytes"] == (generation / "kernel.cu").stat().st_size
        checked = json.loads(run("check-root", [compiler, "check", "--json"], project))
        graph = json.loads(run("checked-graph", [compiler, "graph", "--json"], project))
        nodes = {node["name"]: node for node in graph["nodes"]}
        if checked["revision"] != generated["revision"]:
            raise RuntimeError("selected compiler and CUDA emission checked different program revisions")
        for function in functions:
            if nodes.get(function["name"], {}).get("hash") != function["hash"]:
                raise RuntimeError("selected compiler and CUDA emission differ for " + function["name"])
        root_hash = next(f["hash"] for f in functions if f["name"] == generated["entry"])
        (out / "stdlib").mkdir()
        for name in ["compute.nex", "device.nex"]:
            shutil.copyfile(resources / "lib" / name, out / "stdlib" / name)
        write(out / "nex.json", {"schema": "nex.project/1", "language": "0.28", "entry": "main.nex", "libraries": {"std": "./stdlib"}})
        value_abi = generated.get("value_abi")
        argument_words = value_abi["parameter_words"] if value_abi else [1] * len(generated["parameter_types"])
        output_words = value_abi["result_words"] if value_abi else 1
        if len(argument_words) != len(generated["parameter_types"]) or any(type(n) is not int or not 1 <= n <= 64 for n in [*argument_words, output_words]):
            raise RuntimeError("invalid fixed device value widths")
        batch_lanes = min(32768 // n for n in [*argument_words, output_words])
        text_pool = value_abi["text_pool"] if value_abi else []
        if len(text_pool) > 1024 or any(not isinstance(s, str) or "\0" in s or len(s.encode("utf-8")) > 1023 for s in text_pool):
            raise RuntimeError("invalid bounded device text pool")
        source = Path(__file__).resolve().parent
        all_f64 = generated["result_type"] == "f64" and all(t == "f64" for t in generated["parameter_types"])
        template = (source / "main.nex.in").read_text().replace("@INDEX@", str(args.index)).replace("@ARGUMENTS@", str(len(generated["parameter_types"]))).replace("@ROOT_HASH@", root_hash).replace("@F64_INTERFACE@", "true" if all_f64 else "false")
        width_function = "".join("if index==" + str(i) + "{return " + str(n) + ";}" for i, n in enumerate(argument_words)) + "return 0;"
        template = template.replace("@ARGUMENT_WORDS@", width_function).replace("@OUTPUT_WORDS@", str(output_words)).replace("@BATCH_LANES@", str(batch_lanes))
        (out / "main.nex").write_text(template.replace("@PIN@", "0" * 64), encoding="utf-8")
        run("check-template", [compiler, "check", "--json"])
        signatures = {}
        for name in ["open", "upload", "map", "download", "read_next", "name", "kernel_ns", "busy", "fatal", "encode_f64", "decode_f64"]:
            signature = json.loads(run("signature-" + name, [compiler, "ffi", "--symbol", name + "_raw", "--json"]))
            signatures[name] = hashlib.sha256(json.dumps(signature, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        for name in ["module.cpp", "cuda_driver.h", "main.nex.in", "context_probe.cpp", "gate.cu"]:
            shutil.copyfile(source / name, inputs / name)
        (inputs / "signatures.h").write_text("\n".join('#define PIN_' + n.upper() + ' "' + h + '"' for n, h in signatures.items()) + "\n")
        ptx, nvrtc = b"", None
        compilation_source = generation / "kernel.cu"
        gate_hash = sha(source / "gate.cu") if args.acceptance_gate else ""
        if args.acceptance_gate:
            compilation_source = generation / "compilation.cu"
            compilation_source.write_bytes((generation / "kernel.cu").read_bytes() + b"\n" + (inputs / "gate.cu").read_bytes())
        if not args.source_only:
            nvrtc = compile_ptx(args.nvrtc.resolve(strict=True), compilation_source, generation, args.compute)
            ptx = (generation / "kernel.ptx").read_bytes()
            if args.acceptance_gate and (b"nex_acceptance_gate" not in ptx or b"%clock64" not in ptx):
                raise RuntimeError("NVRTC PTX omitted the explicit acceptance gate or its device clock")
        (inputs / "generated_kernel.h").write_text("#pragma once\n#define GENERATED_ARGUMENTS " + str(len(generated["parameter_types"])) +
            "\n#define GENERATED_VALUE_ABI " + ("1" if value_abi else "0") +
            "\n#define GENERATED_ARGUMENT_WORDS {" + ",".join(map(str, argument_words or [0])) + "}" +
            "\n#define GENERATED_OUTPUT_WORDS " + str(output_words) +
            "\n#define GENERATED_TEXT_POOL_JSON " + json.dumps(json.dumps(text_pool, ensure_ascii=True, separators=(",", ":"))) +
            "\n#define GENERATED_FLOATING_POINT " + ("1" if generated.get("floating_point") else "0") +
            "\n#define GENERATED_SHADER_SHA256 " + json.dumps(generated["shader_sha256"]) +
            "\n#define GENERATED_PTX_SHA256 " + json.dumps(hashlib.sha256(ptx).hexdigest()) +
            "\n#define GENERATED_ACCEPTANCE_GATE " + ("1" if args.acceptance_gate else "0") +
            "\n#define GENERATED_GATE_SOURCE_SHA256 " + json.dumps(gate_hash) +
            "\n#define GENERATED_PTX " + json.dumps(ptx.rstrip(b"\0").decode("utf-8")) + "\n", encoding="utf-8")
        input_pins = {p.name: sha(p) for p in inputs.iterdir()}
        report = {"schema": "nex.experimental-owned-CUDA-codegen-preparation/1", "ok": True,
            "experimental": True, "compiler_sha256": pins["compiler"], "emitter_sha256": pins.get("emitter", pins["compiler"]),
            "frontend_archive_sha256": pins.get("frontend"), "emitter": "standalone" if emitter else "public_checked_AST",
            "emission_schema": generated["schema"], "compiler_build": index["compiler_build"], "descriptor_hash": index["descriptor_hash"], "compiler_index": index, "source_language": "0.28",
            "source_revision": generated["revision"], "emission_sha256": sha(generation / "report.json"),
            "kernel_sha256": generated["shader_sha256"], "root": generated["entry"], "root_hash": root_hash,
            "functions": generated["functions"], "parameter_types": generated["parameter_types"], "result_type": generated["result_type"],
            "signature_sha256": signatures, "source_input_pins": input_pins, "source_checked": True,
            "native_provider_built": False, "driver_initialized": False, "hardware_executed": False,
            "public_CUDA_CLI_or_SDK_accepted": False, "NVRTC": nvrtc,
            "value_abi": value_abi, "maximum_batch_lanes": batch_lanes,
            "floating_point": generated.get("floating_point"), "all_f64_interface": all_f64,
            "f64_transport": {"implemented": True, "byte_order": "little", "chunk_values": 1024, "maximum_values": 32768,
                "finite_only": True, "positive_zero_normalized": True, "GPU_acceptance": False},
            "acceptance_gate": {"compiled": args.acceptance_gate, "source_sha256": gate_hash,
                "compilation_source_sha256": sha(compilation_source), "default_active": False,
                "maximum_cycles_per_kernel": 200000000, "maximum_repeats": 32}, "commands": commands}
        if not args.source_only:
            cxx = (args.cxx or Path(doctor["native_compiler"])).resolve(strict=True)
            flags = ["-std=c++20", "-O2", "-pthread", "-Wall", "-Wextra", "-I" + str(resources / "runtime"), "-I" + str(inputs)]
            if os.name == "nt":
                if not doctor["host"].startswith("x86_64"):
                    raise RuntimeError("native Windows provider currently selects x86_64")
                flags += ["--target=" + doctor["host"], "--sysroot=" + doctor["native_sysroot"], "-static"]
                image, target = "module.dll", "windows-x86_64"
            else:
                flags += ["-fPIC", "-fvisibility=hidden"]
                image, target = "module.so", "linux-" + ("arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64")
            bundle = out / "bundle"
            bundle.mkdir()
            run("compile-module", [cxx, *flags, "-shared", inputs / "module.cpp", *([] if os.name == "nt" else ["-ldl"]), "-o", bundle / image])
            probe = evidence / ("context-probe.exe" if os.name == "nt" else "context-probe")
            run("compile-context-probe", [cxx, *flags, "-DNEX_CUDA_PROBE_INDEX=" + str(args.index), inputs / "context_probe.cpp",
                *([] if os.name == "nt" else ["-ldl"]), "-o", probe])
            notice = "NEX experimental generated CUDA provider\n\n" + (resources / "LICENSE").read_text() + "\n\nnlohmann/json\n" + (resources / "runtime/third_party/JSON-LICENSE.MIT").read_text()
            if os.name == "nt":
                notice += "\n\nNative compiler runtime notices\n" + Path(doctor["native_windows_notices"]).read_text(encoding="utf-8")
            (bundle / "NOTICE").write_text(notice, encoding="utf-8")
            write(bundle / "manifest.json", {"schema": "nex.foreign-bundle/1", "platform": target, "entry": image,
                "files": [{"path": n, "sha256": sha(bundle / n)} for n in [image, "NOTICE"]], "exports": signatures, "notices": ["NOTICE"]})
            pin = sha(bundle / "manifest.json")
            (out / "main.nex").write_text(template.replace("@PIN@", pin), encoding="utf-8")
            write(out / "foreign.json", {"schema": "nex.foreign-host/1", "module_limit": 1, "resource_limit": 64, "resource_bytes": 16777216,
                "libraries": {"gpu": {"directory": "./bundle", "manifest_sha256": pin, "exports": list(signatures)}}})
            run("check-pinned", [compiler, "check", "--json"])
            run("catalogue", [compiler, "foreign", out / "foreign.json", "--json"])
            report.update(native_provider_built=True, manifest_sha256=pin, module_sha256=sha(bundle / image), cxx_sha256=sha(cxx),
                          context_probe=str(probe), context_probe_sha256=sha(probe), context_probe_executed=False)
        assert all(sha(inputs / n) == h for n, h in input_pins.items())
        guard()
        write(evidence / "report.json", report)
        print(json.dumps({"ok": True, "output": str(out), "source_checked": True, "native_provider_built": report["native_provider_built"], "hardware_executed": False}))
    except BaseException as error:
        write(evidence / "failure.json", {"ok": False, "error": repr(error), "commands": commands})
        raise


if __name__ == "__main__":
    main()
