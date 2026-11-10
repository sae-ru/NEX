"""Check generated-provider preparation without CUDA or remote machines."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "emitter", "frontend-archive", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--host-unavailable-controls", action="store_true")
    parser.add_argument("--cxx", type=Path)
    args = parser.parse_args()
    if args.host_unavailable_controls and (platform.system() != "Darwin" or not args.cxx):
        parser.error("the explicit no-CUDA host controls currently require macOS and --cxx")
    compiler, resources, emitter, frontend = [p.resolve(strict=True) for p in
        [args.compiler, args.resources, args.emitter, args.frontend_archive]]
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    write = lambda p, v: p.write_text(json.dumps(v, indent=2) + "\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEX_")}
    env.update(NEX_RESOURCE_DIR=str(resources), PYTHONDONTWRITEBYTECODE="1")
    source, rows = Path(__file__).resolve().parent, []
    report = {"schema": "nex.experimental-owned-CUDA-source-controls/1", "ok": False,
              "compiler_sha256": sha(compiler), "emitter_sha256": sha(emitter),
              "preparation_cases": rows, "commands": [], "actual_GPU_execution": False,
              "public_CUDA_CLI_or_SDK_accepted": False}

    def run(label, argv, cwd=out, expected=0, extra=None):
        command = {"label": label, "argv": list(map(str, argv)), "cwd": str(cwd)}
        report["commands"].append(command)
        write(out / "report.json", report)
        result = subprocess.run(command["argv"], cwd=cwd, env={**env, **(extra or {})}, capture_output=True, timeout=600)
        (out / (label + ".stdout")).write_bytes(result.stdout)
        (out / (label + ".stderr")).write_bytes(result.stderr)
        command["exit_code"] = result.returncode
        assert (result.returncode != 0 if expected == "failure" else result.returncode == expected), (label, result.stderr[-2000:])
        return result

    def prepare(name, project, selected_frontend=frontend, expected=0):
        return run(name + "-prepare", [sys.executable, "-B", source / "prepare.py", "--compiler", compiler,
            "--resources", resources, "--emitter", emitter, "--frontend-archive", selected_frontend,
            "--source-project", project, "--symbol", "transform", "--source-only", "--output", out / (name + "-prepared")], expected=expected)

    fixtures = [
        ("zero", "pub fn transform()->unit{assert(true);}", 0, "unit"),
        ("eight", "pub fn transform(" + ",".join("a" + str(i) + ":i64" for i in range(8)) + ")->i64{return a0+a7;}", 8, "i64"),
        ("match", "pub fn transform(x:bool,y:i64)->i64{return match x{true=>match y{0=>7,n=>n},false=>-1};}", 2, "i64"),
        ("generic", "fn choose<T:integer>(x:T)->T{return match x{0=>1,n=>n};}pub fn transform(x:i64)->i64{return choose<i64>(x);}", 1, "i64"),
        ("float", "pub fn transform(x:f64,y:f64)->f64{return x/y;}", 2, "f64"),
    ]
    try:
        for name, body, arity, result in fixtures:
            project = out / (name + "-source")
            project.mkdir()
            write(project / "nex.json", {"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"})
            (project / "main.nex").write_text("module scalar_source;\n" + body + "\n", encoding="utf-8")
            prepare(name, project)
            prepared = out / (name + "-prepared")
            proof = json.loads((prepared / "preparation/report.json").read_bytes())
            assert proof["ok"] and proof["source_checked"] and not proof["driver_initialized"] and not proof["native_provider_built"]
            assert len(proof["signature_sha256"]) == 11 and len(proof["parameter_types"]) == arity and proof["result_type"] == result
            assert proof["root_hash"] in {f["hash"] for f in proof["functions"]}
            rows.append({"name": name, "arity": arity, "result": result, "checked_signatures": 11,
                         "preparation_report_sha256": sha(prepared / "preparation/report.json")})
        wrong = out / "wrong-frontend.a"
        wrong.write_bytes(b"not the checked frontend archive\n")
        prepare("wrong-frontend", out / "match-source", wrong, "failure")
        rejected = out / "unsupported-source"
        rejected.mkdir()
        write(rejected / "nex.json", {"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"})
        (rejected / "main.nex").write_text("module unsupported;pub fn transform(x:str)->str{return x;}\n")
        prepare("unsupported", rejected, expected="failure")
        for name in ["wrong-frontend", "unsupported"]:
            prepared = out / (name + "-prepared")
            assert (prepared / "preparation/failure.json").is_file() and not (prepared / "bundle").exists()
        assert "identities differ" in json.loads((out / "wrong-frontend-prepared/preparation/failure.json").read_bytes())["error"]
        assert json.loads((out / "unsupported-prepared/preparation/generate.stdout").read_bytes())["code"] == "E_GPU_TYPE"
        report["rejected_preparations"] = 2
        if args.host_unavailable_controls:
            prepared = out / "match-prepared"
            inputs, bundle = prepared / "preparation/inputs", prepared / "bundle"
            bundle.mkdir()
            apple_sdk = run("host-sdk", ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"]).stdout.decode("utf-8").strip()
            run("host-module-build", [args.cxx, "-isysroot", apple_sdk, "-std=c++20", "-O1", "-g", "-shared", "-fPIC", "-fvisibility=hidden", "-pthread",
                "-Wall", "-Wextra", "-Werror", "-I" + str(resources / "runtime"), "-I" + str(inputs), inputs / "module.cpp", "-o", bundle / "module.so"])
            probe = out / "context-probe"
            run("host-probe-build", [args.cxx, "-isysroot", apple_sdk, "-std=c++20", "-O1", "-g", "-pthread",
                "-Wall", "-Wextra", "-Werror", "-I" + str(resources / "runtime"), "-I" + str(inputs), inputs / "context_probe.cpp", "-o", probe])
            probe_result = json.loads(run("host-probe-unavailable", [probe, "--expect-unavailable"]).stdout)
            assert probe_result["scope"] == "unavailable-driver-host-control" and probe_result["ok"]
            assert probe_result["actual_CUDA_contexts"] == 0 and probe_result["actual_device_allocations"] == 0 and not probe_result["physical_CUDA_context_probe_passed"]
            lane = json.loads(run("host-probe-lane-status", [probe, "--check-lane-status"]).stdout)
            assert lane["ok"] and not lane["floating_point"] and lane["actual_CUDA_contexts"] == 0 and not lane["actual_kernel_status_observed"]
            blocked = run("host-probe-gate-disabled", [probe, "--check-gate-config"], expected=1,
                extra={"NEX_OWNED_CUDA_MAP_GATE_CYCLES": "1", "NEX_OWNED_CUDA_MAP_GATE_REPEATS": "1"})
            assert b"E_DEVICE_CONFIG" in blocked.stderr and blocked.stdout == b""
            (bundle / "NOTICE").write_bytes((resources / "LICENSE").read_bytes() + b"\n" + (resources / "runtime/third_party/JSON-LICENSE.MIT").read_bytes())
            proof = json.loads((prepared / "preparation/report.json").read_bytes())
            write(bundle / "manifest.json", {"schema": "nex.foreign-bundle/1", "platform": "macos-" + ("arm64" if platform.machine().lower() in {"arm64", "aarch64"} else "x86_64"), "entry": "module.so",
                "files": [{"path": n, "sha256": sha(bundle / n)} for n in ["module.so", "NOTICE"]], "exports": proof["signature_sha256"], "notices": ["NOTICE"]})
            pin = sha(bundle / "manifest.json")
            text = (prepared / "main.nex").read_text().replace("0" * 64, pin)
            text = text[:text.index("server fn main()")]+'''server fn main()->unit !{task,ffi,io}{
 var i:i64=0;while i<32{
  let result:result<d::Session>=make_context();assert(!is_ok(result));
  assert(error_code(result)=="E_COMPUTE_UNAVAILABLE");i=i+1;
 }print(42);
}
'''
            (prepared / "main.nex").write_text(text, encoding="utf-8")
            foreign = prepared / "foreign.json"
            # One session fits; two unreleased reservations do not. Repeated
            # constructor failure must restore capacity on every backend.
            write(foreign, {"schema": "nex.foreign-host/1", "module_limit": 1, "resource_limit": 64, "resource_bytes": 262144,
                "libraries": {"gpu": {"directory": "./bundle", "manifest_sha256": pin, "exports": list(proof["signature_sha256"])}}})
            trace = out / "reference-trace.jsonl"
            value = json.loads(run("host-reference", [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--task-timeout-ms", "30000", "--json"], prepared,
                extra={"NEX_OWNED_CUDA_MAP_TRACE": str(trace)}).stdout)
            assert value["stdout"] == "42\n" and value["foreign_resource_bytes_after_scope"] == 0
            for mode in ["debug", "release"]:
                built = json.loads(run("host-build-" + mode, [compiler, "build", "--profile", mode, "--task-timeout-ms", "30000", "--build-directory", out / ("native-" + mode), "--json"], prepared).stdout)
                native_trace = out / ("native-" + mode + "-trace.jsonl")
                value = run("host-native-" + mode, [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1"], prepared,
                    extra={"NEX_OWNED_CUDA_MAP_TRACE": str(native_trace)})
                assert value.stdout == b"42\n" and value.stderr == b""
            for path in [trace, *[out / ("native-" + mode + "-trace.jsonl") for mode in ["debug", "release"]]]:
                events = [json.loads(line) for line in path.read_text().splitlines()]
                final = events[-1]
                assert final["event"] == "module_unloaded" and final["physical_completion_verified"]
                assert final["ledger"]["contexts"] == 0 and final["ledger"]["allocations"] == 0 and final["ledger"]["cleanup_errors"] == 0 and final["ledger"]["kernel_launches"] == 0
            report["host_unavailable_controls"] = {"actual_CXX_module_built": True, "backends": ["reference", "native-debug", "native-release"],
                "typed_unavailable_results": 96, "zero_created_CUDA_contexts_allocations_or_launches": True,
                "declared_resource_byte_capacity": 262144, "constructor_reservation_capacity_recovered_each_call": True,
                "context_probe_compiled_and_unavailable_control_passed": True, "physical_context_probe_passed": False,
                "reference_resource_capacity_after_scope": 0, "CPU_fallback": False, "GPU_execution_accepted": False}
        report["ok"] = True
    finally:
        write(out / "report.json", report)
    print(json.dumps({"ok": True, "source_preparations": len(rows), "checked_signatures": len(rows) * 11, "rejected_preparations": 2, "actual_GPU_execution": False}))


if __name__ == "__main__":
    main()
