"""Compare actual NEX CPU functions and their owned generated GPU calls."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["sdk", "cxx", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    sdk, cxx = args.sdk.resolve(strict=True), args.cxx.resolve(strict=True)
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent
    fixtures = load_module("generated_numerical_fixtures", source.parent / "metal-codegen/verify.py")
    lifetime = load_module("owned_generated_lifetime_inspection", source / "verify.py")
    compiler = sdk / "bin/nex"
    env = {**os.environ, "NEX_RESOURCE_DIR": str(sdk / "share/nex"), "PYTHONDONTWRITEBYTECODE": "1", "NEX_OWNED_METAL_MAP_TEST_NOISE": "1"}
    for name in ["NEX_OWNED_METAL_MAP_TEST_BAD_REPLY", "NEX_OWNED_METAL_MAP_TEST_GATE_MS"]:
        env.pop(name, None)
    report = {"schema": "nex.owned-generated-Metal-numerics/1", "ok": False, "cases": [], "commands": [], "compiler_sha256": sha(compiler),
              "direct_fatal_trap_forwarding_integrated": True, "installed_SDK_accepted": False, "whole_original_goal_complete": False}
    start = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - start
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, argv, cwd, extra=None):
        p = subprocess.run(list(map(str, argv)), cwd=cwd, env={**env, **(extra or {})}, capture_output=True, text=True, timeout=600)
        (out / (label + ".stdout")).write_text(p.stdout)
        (out / (label + ".stderr")).write_text(p.stderr)
        report["commands"].append({"label": label, "argv": list(map(str, argv)), "exit_code": p.returncode})
        save()
        assert p.returncode == 0, (label, p.returncode, p.stdout[-2200:], p.stderr[-2200:])
        return p

    def columns(rows, types):
        return "[" + ",".join("encode_i64s([" + ",".join(str(int(row[i])) for row in rows) + "])" for i in range(len(types))) + "]"

    def prepare(name, text):
        directory = out / name
        directory.mkdir()
        cpu = directory / "source"
        cpu.mkdir()
        (cpu / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"}) + "\n")
        (cpu / "main.nex").write_text("module generated_gpu;\n" + text + "\nfn main()->unit{}\n")
        project = directory / "provider"
        run(name + "-prepare", [sys.executable, "-B", source / "prepare.py", "--sdk", sdk, "--source-project", cpu, "--symbol", "transform", "--output", project, "--cxx", cxx], directory)
        metadata = json.loads((project / "preparation/report.json").read_bytes())
        assert metadata["ok"] and metadata["native_provider_built"] and metadata["input_layout"] == "columns" and not metadata["hardware_executed"]
        return directory, project, metadata

    def compare(name, directory, project, metadata, text, body, kernels, errors):
        caller = directory / "caller"
        caller.mkdir()
        (caller / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex", "libraries": {"std": str(project / "stdlib")}}) + "\n")
        prefix = (project / "main.nex").read_text().split("server fn main()->unit")[0]
        (caller / "main.nex").write_text(prefix + "\n" + lifetime.HELPERS.split("server fn owned_output")[0] + "\n" + text + "\nserver fn main()->unit !{task,ffi,io,throw}{" + body + "print(42);}\n")
        foreign = project / "foreign.json"
        reference_trace = directory / "reference.trace.jsonl"
        reference = json.loads(run(name + "-reference", [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", "30000", "--json"], caller,
                                   {"NEX_OWNED_METAL_MAP_TRACE": str(reference_trace)}).stdout)
        assert reference["stdout"] == "42\n" and reference["foreign_resource_bytes_after_scope"] == 0
        built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", "30000", "--json"], caller).stdout)
        native_trace = directory / "native.trace.jsonl"
        native = run(name + "-native", [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1"], caller, {"NEX_OWNED_METAL_MAP_TRACE": str(native_trace)})
        assert native.stdout == "42\n" and native.stderr == ""
        ref = lifetime.inspect_trace(reference_trace, kernels, errors)
        nat = lifetime.inspect_trace(native_trace, kernels, errors)
        assert ref["devices"] == nat["devices"] and ref["buffers"] == nat["buffers"]
        report["cases"].append({"name": name, "native_reference": True, "source_revision": metadata["source_revision"],
                                "kernel_sha256": metadata["kernel_sha256"], "manifest_sha256": metadata["manifest_sha256"], "worker_sha256": metadata["worker_sha256"],
                                "module_sha256": metadata["module_sha256"], "parameter_types": metadata["parameter_types"], "reference": ref, "native": nat})
        save()

    try:
        for case in fixtures.fixtures():
            name = case["name"]
            directory, project, metadata = prepare(name, case["source"])
            valid = [(row, gold) for row, gold in zip(case["rows"], case["gold"]) if type(gold) is not str]
            body = "let s:d::Session=unwrap(make_context());"
            kernels = errors = 0
            if valid:
                calls = [fixtures.invocation(row) for row, gold in valid]
                if case["result"] == "bool":
                    calls = ["match " + call + "{true=>1,false=>0}" for call in calls]
                elif case["result"] == "unit":
                    body += "".join(call + ";" for call in calls)
                    calls = ["0"] * len(calls)
                body += "let expected:list<i64>=[" + ",".join(calls) + "];assert(expected==[" + ",".join(str(int(gold)) for row, gold in valid) + "]);"
                body += "assert(decode_i64s(apply(s," + columns([row for row, gold in valid], case["types"]) + "," + str(len(valid)) + ",4096))==expected);"
                kernels += 1
            error_codes = sorted({gold for gold in case["gold"] if type(gold) is str})
            for code in error_codes:
                row = next(row for row, gold in zip(case["rows"], case["gold"]) if gold == code)
                body += 'assert(error_code(try_apply(s,' + columns([row], case["types"]) + ',1,4096))=="' + code + '");'
                kernels += 1
                errors += 1
            if valid and error_codes:
                row, gold = valid[0]
                body += "assert(decode_i64s(apply(s," + columns([row], case["types"]) + ",1,4096))==[" + str(int(gold)) + "]);"
                kernels += 1
            if name == "lazy_boolean":
                body += 'assert(error_code(try_apply(s,[encode_i64s([2]),encode_i64s([1])],1,4096))=="E_GPU_INPUT");'
                kernels += 1
                errors += 1
            body += "resource_close(s);"
            compare(name, directory, project, metadata, case["source"], body, kernels, errors)
        text = "fn transform(a:i64,b:i64,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64)->i64{return a+b+c+d+e+f+g+h;}"
        directory, project, metadata = prepare("eight_argument_maximum", text)
        body = "let s:d::Session=unwrap(make_context());let expected:i64=transform(1,2,3,4,5,6,7,8);assert(expected==36);let actual:bytes=apply(s,[" + ",".join("repeat_word(" + str(i) + ",32768)" for i in range(1, 9)) + "],32768,512);assert(actual==repeat_word(expected,32768));resource_close(s);"
        compare("eight_argument_maximum", directory, project, metadata, text, body, 1, 0)
        text = "fn transform(x:i64)->i64{var i:i64=0;while i<x{i=i+1;}return i;}"
        directory, project, metadata = prepare("step_bound", text)
        body = 'let s:d::Session=unwrap(make_context());assert(error_code(try_apply(s,[encode_i64s([1000])],1,32))=="E_GPU_STEP_LIMIT");assert(decode_i64s(apply(s,[encode_i64s([1000])],1,16384))==[transform(1000)]);resource_close(s);'
        compare("step_bound", directory, project, metadata, text, body, 2, 1)
        assert sha(compiler) == report["compiler_sha256"]
        report.update(ok=True, state="passed", native_reference_pairs=len(report["cases"]), physical_GPU_kernel_events=sum(len(case[mode]["physical_GPU_events"]) for case in report["cases"] for mode in ["reference", "native"]))
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "native_reference_pairs", "physical_GPU_kernel_events"]}))


if __name__ == "__main__":
    main()
