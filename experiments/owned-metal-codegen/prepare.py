"""Prepare an owned persistent Metal provider for a selected checked NEX scalar function."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["sdk", "source-project", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--cxx", default=shutil.which("clang++"))
    parser.add_argument("--index", type=int, default=0)
    parser.add_argument("--check-sdk", action="store_true")
    args = parser.parse_args()
    sdk, source_project = args.sdk.resolve(strict=True), args.source_project.resolve(strict=True)
    out = args.output.absolute()
    if platform.system() != "Darwin" and not args.check_sdk:
        parser.error("native Metal preparation requires macOS; use --check-sdk for source-only validation")
    if not 0 <= args.index < 64:
        parser.error("GPU index must be0..63")
    if not args.check_sdk and (not args.cxx or not Path(args.cxx).is_file()):
        parser.error("select an actual C++20 compiler")
    out.mkdir(parents=True, exist_ok=False)
    evidence = out / "preparation"
    evidence.mkdir()
    compiler = sdk / "bin" / ("nex.exe" if os.name == "nt" else "nex")
    resources = sdk / "share/nex"
    source = Path(__file__).parent
    env = {**os.environ, "NEX_RESOURCE_DIR": str(resources), "PYTHONDONTWRITEBYTECODE": "1"}
    commands = []

    def run(label, argv, cwd=out):
        row = {"label": label, "argv": list(map(str, argv)), "cwd": str(cwd)}
        commands.append(row)
        write(evidence / "commands.json", commands)
        result = subprocess.run(row["argv"], cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
        (evidence / (label + ".stdout")).write_text(result.stdout)
        (evidence / (label + ".stderr")).write_text(result.stderr)
        row["exit_code"] = result.returncode
        write(evidence / "commands.json", commands)
        if result.returncode:
            raise RuntimeError(label + " failed; inspect retained diagnostics: " + result.stdout[-1000:] + result.stderr[-1500:])
        return result.stdout

    run("generate", [sys.executable, "-B", ROOT / "experiments/metal-codegen/codegen.py", "--sdk", sdk, "--project", source_project, "--symbol", args.symbol, "--input-layout", "columns", "--output", out / "generation"])
    generated = json.loads((out / "generation/report.json").read_bytes())
    assert generated["ok"] and generated["input_layout"] == "columns" and generated["compiler_sha256"] == sha(compiler)
    descriptor = json.loads(run("describe", [compiler, "describe", "--json"]))
    if not descriptor.get("resource_regions", {}).get("dependency_graph", {}).get("C_table_parent_creation") or not descriptor.get("source_resources", {}).get("source_task_bridge"):
        raise RuntimeError("selected compiler lacks source-task FFI and dependent resources")
    stdlib = out / "stdlib"
    stdlib.mkdir()
    for name in ["compute.nex", "device.nex"]:
        shutil.copyfile(resources / "lib" / name, stdlib / name)
    write(out / "nex.json", {"schema": "nex.project/1", "language": "0.28", "entry": "main.nex", "libraries": {"std": "./stdlib"}})
    template = (source / "main.nex.in").read_text().replace("@INDEX@", str(args.index)).replace("@ARGUMENTS@", str(len(generated["parameter_types"]))).replace("@ROOT_HASH@", generated["functions"][generated["root"]])
    (out / "main.nex").write_text(template.replace("@PIN@", "0" * 64))
    run("check-template", [compiler, "check", "--json"])
    signatures = {}
    for name, local in [("open", "open_raw"), ("upload", "upload_raw"), ("map", "map_raw"), ("download", "download_raw"), ("read_next", "read_next_raw"), ("name", "name_raw"), ("kernel_ns", "kernel_ns_raw"), ("busy", "busy_raw")]:
        value = json.loads(run("signature-" + name, [compiler, "ffi", "--symbol", local, "--json"]))
        signatures[name] = hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    inputs = evidence / "inputs"
    inputs.mkdir()
    for name in ["module.cpp", "worker.mm", "protocol.h", "main.nex.in"]:
        shutil.copyfile(source / name, inputs / name)
    (inputs / "signatures.h").write_text("\n".join('#define PIN_' + name.upper() + ' "' + digest + '"' for name, digest in signatures.items()) + "\n")
    (inputs / "generated_kernel.h").write_text("#pragma once\n#define GENERATED_ARGUMENTS " + str(len(generated["parameter_types"])) + "\n#define GENERATED_SHADER_SHA256 " + json.dumps(generated["kernel_sha256"]) + "\n#define GENERATED_MSL " + json.dumps((out / "generation/kernel.metal").read_text()) + "\n")
    input_pins = {p.name: sha(p) for p in inputs.iterdir() if p.is_file()}
    report = {"schema": "nex.owned-Metal-codegen-preparation/1", "ok": True, "compiler_sha256": sha(compiler), "source_language": "0.28", "toolchain": generated["toolchain"],
              "source_revision": generated["revision"], "root": generated["root"], "root_hash": generated["functions"][generated["root"]], "kernel_sha256": generated["kernel_sha256"],
              "input_layout": "columns", "parameter_types": generated["parameter_types"], "result_type": generated["result_type"], "source_input_pins": input_pins,
              "signature_sha256": signatures, "source_checked": True, "native_provider_built": False, "driver_initialized": False, "hardware_executed": False,
              "direct_fatal_trap_forwarding_integrated": False, "installed_SDK_accepted": False, "commands": commands}
    if args.check_sdk:
        write(evidence / "report.json", report)
        print(json.dumps({"ok": True, "source_checked": True, "hardware_executed": False}))
        return
    sysroot = subprocess.check_output(["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"], text=True, timeout=10).strip()
    bundle = out / "bundle"
    bundle.mkdir()
    flags = ["-std=c++20", "-O2", "-pthread", "-isysroot", sysroot, "-I" + str(resources / "runtime"), "-I" + str(inputs)]
    run("compile-worker", [args.cxx, *flags, "-fobjc-arc", "-fobjc-arc-exceptions", "-fblocks", inputs / "worker.mm", "-framework", "Foundation", "-framework", "Metal", "-o", bundle / "worker"])
    run("compile-module", [args.cxx, *flags, "-shared", "-fPIC", "-fvisibility=hidden", inputs / "module.cpp", "-o", bundle / "module.so"])
    (bundle / "NOTICE").write_text("NEX generated owned Metal provider\n\n" + (ROOT / "LICENSE").read_text() + "\nnlohmann/json\n" + (resources / "runtime/third_party/JSON-LICENSE.MIT").read_text())
    manifest = {"schema": "nex.foreign-bundle/1", "platform": "macos-" + ("arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"), "entry": "module.so", "executables": ["worker"],
                "files": [{"path": name, "sha256": sha(bundle / name)} for name in ["module.so", "worker", "NOTICE"]], "exports": signatures, "notices": ["NOTICE"]}
    write(bundle / "manifest.json", manifest)
    pin = sha(bundle / "manifest.json")
    (out / "main.nex").write_text(template.replace("@PIN@", pin))
    write(out / "foreign.json", {"schema": "nex.foreign-host/1", "module_limit": 1, "resource_limit": 64, "resource_bytes": 16777216,
                                  "libraries": {"gpu": {"directory": "./bundle", "manifest_sha256": pin, "exports": list(signatures)}}})
    run("check-pinned", [compiler, "check", "--json"])
    run("catalogue", [compiler, "foreign", out / "foreign.json", "--json"])
    assert all(sha(inputs / name) == digest for name, digest in input_pins.items())
    assert sha(compiler) == report["compiler_sha256"]
    report.update(native_provider_built=True, manifest_sha256=pin, worker_sha256=sha(bundle / "worker"), module_sha256=sha(bundle / "module.so"), selected_Apple_SDK=sysroot)
    write(evidence / "report.json", report)
    print(json.dumps({"ok": True, "output": str(out), "manifest_sha256": pin, "hardware_executed": False}))


if __name__ == "__main__":
    main()
