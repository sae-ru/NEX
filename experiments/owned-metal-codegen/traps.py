"""Compare original CPU/GPU fatal diagnostics and physical cleanup on Metal."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

SCALAR = '''
fn transform(kind:i64,value:i64)->i64{
 if kind==1{return value+1;}
 if kind==2{return 42/value;}
 if kind==3{assert(value>0);return value;}
 var i:i64=0;while i<value{i=i+1;}return i;
}
'''
CASES = [
    ("overflow", 1, 9223372036854775807, 4096, "E_OVERFLOW", 0, 30000),
    ("division", 2, 0, 4096, "E_DIV_ZERO", 0, 30000),
    ("assertion", 3, 0, 4096, "E_ASSERT", 0, 30000),
    ("device_steps", 4, 1000, 32, "E_GPU_STEP_LIMIT", 0, 30000),
    ("cancellation_overflow", 1, 9223372036854775807, 4096, "E_CANCELLED", 1500, 5000),
    ("deadline_overflow", 1, 9223372036854775807, 4096, "E_TIMEOUT", 3000, 2000),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["sdk", "cxx", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    sdk, cxx = args.sdk.resolve(strict=True), args.cxx.absolute()
    # Preserve the selected C++ driver's name when it is a symlink.
    if not cxx.is_file():
        parser.error("select an actual C++20 compiler")
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent
    spec = importlib.util.spec_from_file_location("owned_generated_trace", source / "verify.py")
    trace = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(trace)
    compiler = sdk / "bin/nex"
    env = {**os.environ, "NEX_RESOURCE_DIR": str(sdk / "share/nex"), "PYTHONDONTWRITEBYTECODE": "1", "NEX_OWNED_METAL_MAP_TEST_NOISE": "1"}
    for name in ["NEX_OWNED_METAL_MAP_TEST_BAD_REPLY", "NEX_OWNED_METAL_MAP_TEST_GATE_MS"]:
        env.pop(name, None)
    started = time.monotonic()
    report = {"schema": "nex.owned-generated-Metal-fatal-traps/1", "ok": False, "compiler_sha256": sha(compiler),
              "commands": [], "cases": [], "CPU_diagnostics": [], "installed_SDK_accepted": False, "whole_original_goal_complete": False}

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, argv, cwd, expected=0, extra=None):
        row = {"label": label, "argv": list(map(str, argv)), "cwd": str(cwd)}
        report["commands"].append(row)
        save()
        p = subprocess.run(row["argv"], cwd=cwd, env={**env, **(extra or {})}, capture_output=True, text=True, timeout=600)
        (out / (label + ".stdout")).write_text(p.stdout)
        (out / (label + ".stderr")).write_text(p.stderr)
        row["exit_code"] = p.returncode
        save()
        assert p.returncode == expected, (label, p.returncode, p.stdout[-2000:], p.stderr[-2000:])
        return p

    def project(directory, text, stdlib=None):
        directory.mkdir()
        configuration = {"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"}
        if stdlib:
            configuration["libraries"] = {"std": str(stdlib)}
        (directory / "nex.json").write_text(json.dumps(configuration) + "\n")
        (directory / "main.nex").write_text(text)

    try:
        cpu = out / "source"
        project(cpu, "module scalar_traps;\n" + SCALAR + "\nfn main()->unit{}\n")
        provider = out / "provider"
        run("prepare", [sys.executable, "-B", source / "prepare.py", "--sdk", sdk, "--source-project", cpu, "--symbol", "transform", "--output", provider, "--cxx", cxx], out)
        prepared = json.loads((provider / "preparation/report.json").read_bytes())
        assert prepared["ok"] and prepared["direct_fatal_trap_forwarding_integrated"] and not prepared["hardware_executed"]
        report["provider"] = {"manifest_sha256": sha(provider / "bundle/manifest.json"), "worker_sha256": sha(provider / "bundle/worker"),
                              "module_sha256": sha(provider / "bundle/module.so"), "kernel_sha256": prepared["kernel_sha256"], "source_revision": prepared["source_revision"]}
        prefix = (provider / "main.nex").read_text().split("server fn main()->unit")[0]
        foreign = provider / "foreign.json"
        for name, kind, value, steps, code, gate, timeout in CASES:
            directory = out / name
            call = "let result:bytes=apply(session,[encode_i64s([" + str(kind) + "]),encode_i64s([" + str(value) + "])],1," + str(steps) + ");"
            if code == "E_CANCELLED":
                call = "with_tasks(1,server fn(scope:task_scope)->unit !{task,ffi,throw}{let child:task<unit>=task_spawn(scope,server fn()->unit !{task,ffi}{" + call + "});while busy_raw(session)==0{task_yield();}assert(task_cancel(child));task_wait(child);});"
            body = 'let session:d::Session=unwrap(make_context());try{' + call + 'print("after");}catch(c,m){print("caught");}finally{print("finalized");}'
            project(directory, prefix + "\nserver fn main()->unit !{task,ffi,io,throw}{" + body + "}\n", provider / "stdlib")
            extra = {"NEX_OWNED_METAL_MAP_TEST_GATE_MS": str(gate)} if gate else {}
            reference_trace, native_trace = directory / "reference.jsonl", directory / "native.jsonl"
            controls = ["--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout)]
            reference = json.loads(run(name + "-reference", [compiler, "eval", "--foreign", foreign, *controls, "--json"], directory, 1,
                                       {**extra, "NEX_OWNED_METAL_MAP_TRACE": str(reference_trace)}).stdout)
            assert reference["code"] == code and reference["stdout"] == "", reference
            built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", *controls, "--json"], directory).stdout)
            native = run(name + "-native", [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1", "--nex-task-timeout-ms", str(timeout)], directory, 70,
                         {**extra, "NEX_OWNED_METAL_MAP_TRACE": str(native_trace)})
            assert native.stdout == "" and code in native.stderr, native.stderr
            ref = trace.inspect_trace(reference_trace, 1, 1, bool(gate), code == "E_CANCELLED")
            nat = trace.inspect_trace(native_trace, 1, 1, bool(gate), code == "E_CANCELLED")
            assert ref["devices"] == nat["devices"]
            report["cases"].append({"name": name, "code": code, "native_reference": True, "reference": ref, "native": nat})
            if name in ["overflow", "division", "assertion"]:
                cpu_case = out / (name + "-CPU")
                project(cpu_case, "module cpu_trap;\n" + SCALAR + '\nfn main()->unit !{io,throw}{try{print(transform(' + str(kind) + ',' + str(value) + '));}catch(c,m){print("caught");}finally{print("finalized");}}\n')
                failed = json.loads(run(name + "-CPU-reference", [compiler, "eval", "--json"], cpu_case, 1).stdout)
                assert failed["code"] == code and failed["stdout"] == ""
                for profile in ["debug", "release"]:
                    built = json.loads(run(name + "-CPU-build-" + profile, [compiler, "build", "--profile", profile, "--build-directory", out / "cpu-native", "--json"], cpu_case).stdout)
                    failed = run(name + "-CPU-" + profile, [built["executable"]], cpu_case, 70)
                    assert code in failed.stderr and failed.stdout == ""
                report["CPU_diagnostics"].append({"case": name, "code": code, "reference_debug_release_agree": True})
            save()
        assert sha(compiler) == report["compiler_sha256"]
        report.update(ok=True, state="passed", native_reference_pairs=len(report["cases"]), direct_fatal_trap_forwarding_integrated=True,
                      physical_GPU_kernel_events=sum(len(case[mode]["physical_GPU_events"]) for case in report["cases"] for mode in ["reference", "native"]))
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "native_reference_pairs", "physical_GPU_kernel_events"]}))


if __name__ == "__main__":
    main()
