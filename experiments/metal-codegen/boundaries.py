"""Check explicit scalar-backend rejections, canonical inputs and GPU step bounds."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ["sdk", "runner", "output"]:
        parser.add_argument("--" + key, required=True, type=Path)
    args = parser.parse_args()
    sdk, runner = args.sdk.resolve(strict=True), args.runner.resolve(strict=True)
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    compiler = sdk / "bin/nex"
    env = {**os.environ, "NEX_RESOURCE_DIR": str(sdk / "share/nex"), "PYTHONDONTWRITEBYTECODE": "1"}
    report = {"schema": "nex.generated-Metal-boundaries/1", "ok": False, "commands": [], "source_rejections": [], "physical": [], "runner_rejections": [],
              "compiler_sha256": sha(compiler), "runner_sha256": sha(runner), "installed_SDK_accepted": False, "source_task_provider_integrated": False}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, argv, cwd, expected=0):
        p = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
        (out / (label + ".stdout")).write_text(p.stdout)
        (out / (label + ".stderr")).write_text(p.stderr)
        report["commands"].append({"label": label, "argv": list(map(str, argv)), "exit_code": p.returncode})
        save()
        assert p.returncode == expected, (label, p.returncode, p.stdout[-2000:], p.stderr[-2000:])
        return p

    def project(name, source, main=""):
        directory = out / name
        directory.mkdir()
        (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"}) + "\n")
        (directory / "main.nex").write_text("module generated_gpu;\n" + source + "\nfn main()->unit !{io}{" + main + "}\n")
        return directory

    def generate(name, directory, expected=0):
        output = directory / "emitted"
        run(name + "-generate", [sys.executable, "-B", Path(__file__).with_name("codegen.py"), "--sdk", sdk, "--project", directory, "--symbol", "transform", "--output", output], directory, expected)
        result = json.loads((output / "report.json").read_bytes())
        assert result["ok"] == (expected == 0)
        return output, result

    def gpu(name, emitted, count, parameters, steps, data, expected_output, expected_errors):
        directory = out / name
        directory.mkdir()
        input_file = directory / "input.bin"
        input_file.write_bytes(data)
        actual = json.loads(run(name, [runner, emitted / "kernel.metal", input_file, directory / "output.bin", directory / "errors.bin", str(count), str(parameters), str(steps), "0"], directory).stdout)
        assert actual["ok"] and actual["Metal_command_buffer_status"] == 4 and actual["completion_handlers"] == 1
        assert actual["physical_completion_before_readback"] and actual["all_three_buffers_released_after_completion"] and not actual["CPU_substitute"]
        assert struct.unpack("<" + "q" * count, (directory / "output.bin").read_bytes()) == tuple(expected_output)
        assert struct.unpack("<" + "I" * count, (directory / "errors.bin").read_bytes()) == tuple(expected_errors)
        report["physical"].append({"name": name, "actual": actual})
        save()
        return directory

    rejected = [
        ("float_parameter", "fn transform(x:f64)->i64{return 0;}", "type f64"),
        ("float_result", "fn transform(x:i64)->f64{return 1.0;}", "type f64"),
        ("heap_result", 'fn transform(x:i64)->str{return "hello";}', "type str"),
        ("heap_parameter", "fn transform(x:list<i64>)->i64{return x[0];}", "type list<i64>"),
        ("effect", "fn transform(x:i64)->i64 !{io}{print(x);return x;}", "shared and pure"),
        ("server_realm", "server fn transform(x:i64)->i64{return x;}", "shared and pure"),
        ("recursion", "fn transform(x:i64)->i64{if x==0{return 0;}return transform(x-1);}", "recursive GPU call graph"),
        ("match", "fn transform(x:i64)->i64{return match x{0=>1,_=>x};}", "expression kind 10"),
        ("finally", "fn transform(x:i64)->i64{try{return x;}finally{assert(true);}}", "statement kind 10"),
        ("callable", "fn id(x:i64)->i64{return x;}fn transform(x:i64)->i64{let f:fn(i64)->i64=id;return f(x);}", "GPU scalar backend does not support type"),
        ("generic_root", "fn transform<T>(x:T)->T{return x;}", "must be concrete"),
        ("nine_arguments", "fn transform(a:i64,b:i64,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64,i:i64)->i64{return a;}", "more than8"),
    ]
    chain = "".join("fn chain_" + str(i) + "(x:i64)->i64{return " + ("x" if i == 129 else "chain_" + str(i + 1) + "(x)") + ";}" for i in range(130))
    rejected.append(("call_depth", chain + "fn transform(x:i64)->i64{return chain_0(x);}", "call depth exceeds128"))
    wide = "".join("fn leaf_" + str(i) + "()->i64{return 0;}" for i in range(130))
    rejected.append(("function_count", wide + "fn transform()->i64{return " + "+".join("leaf_" + str(i) + "()" for i in range(130)) + ";}", "call graph exceeds128"))
    try:
        for name, source, diagnostic in rejected:
            directory = project(name, source)
            run(name + "-actual-source-check", [compiler, "check", "--json"], directory)
            emitted, result = generate(name, directory, 1)
            assert result["state"] == "rejected" and diagnostic in result["error"] and not (emitted / "kernel.metal").exists(), (name, result)
            report["source_rejections"].append({"name": name, "actual_NEX_source_accepted": True, "backend_rejected_before_driver": True, "diagnostic": result["error"]})
            save()
        finite = project("finite_loop", "fn transform(x:i64)->i64{var i:i64=0;while i<x{i=i+1;}return i;}", "print(encode_json([transform(1000),transform(1)]));")
        emitted, metadata = generate("finite_loop", finite)
        reference = json.loads(run("finite-loop-reference", [compiler, "eval", "--json"], finite).stdout)
        assert json.loads(reference["stdout"]) == ["1000", "1"]
        built = json.loads(run("finite-loop-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--json"], finite).stdout)
        assert json.loads(run("finite-loop-native", [built["executable"]], finite).stdout) == ["1000", "1"]
        data = struct.pack("<qq", 1000, 1)
        gpu("low_step_bound", emitted, 2, 1, 32, data, [0, 1], [4, 0])
        gpu("adequate_step_bound", emitted, 2, 1, 16384, data, [1000, 1], [0, 0])
        boolean = project("canonical_bool", "fn transform(x:bool)->bool{return !x;}")
        bool_kernel, metadata = generate("canonical_bool", boolean)
        gpu("noncanonical_bool_rejected", bool_kernel, 3, 1, 32, struct.pack("<qqq", 2, 0, 1), [0, 1, 0], [6, 0, 0])
        arguments = project("eight_arguments", "fn transform(a:i64,b:i64,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64)->i64{return a+b+c+d+e+f+g+h;}")
        argument_kernel, metadata = generate("eight_arguments", arguments)
        gpu("maximum_arguments", argument_kernel, 1, 8, 128, struct.pack("<8q", *range(1, 9)), [36], [0])
        constant = project("constant", "fn transform()->i64{return 42;}")
        constant_kernel, metadata = generate("constant", constant)
        maximum = gpu("maximum_lanes", constant_kernel, 32768, 0, 32, b"", [42] * 32768, [0] * 32768)
        for name, count, parameters, steps, data, diagnostic in [
            ("zero_count", 0, 0, 32, b"", "invalid bounded argument"),
            ("too_many_lanes", 32769, 0, 32, b"", "invalid bounded argument"),
            ("too_many_arguments", 1, 9, 32, b"", "invalid bounded argument"),
            ("zero_steps", 1, 0, 0, b"", "invalid bounded argument"),
            ("too_many_steps", 1, 0, 65537, b"", "invalid bounded argument"),
            ("work_product", 32768, 0, 65536, b"", "count times per-lane step bound"),
            ("truncated_input", 2, 1, 32, b"\0" * 8, "input does not match scalar row shape"),
            ("trailing_input", 1, 0, 32, b"\0" * 8, "input does not match scalar row shape")]:
            directory = out / name
            directory.mkdir()
            (directory / "input.bin").write_bytes(data)
            result = json.loads(run(name, [runner, constant_kernel / "kernel.metal", directory / "input.bin", directory / "output.bin", directory / "errors.bin", str(count), str(parameters), str(steps), "0"], directory, 1).stdout)
            assert not result["ok"] and diagnostic in result["error"] and "physical_GPU_kernel_events" not in result
            assert not (directory / "output.bin").exists() and not (directory / "errors.bin").exists()
            report["runner_rejections"].append({"name": name, "before_GPU_submission": True, "error": result["error"]})
            save()
        assert sha(compiler) == report["compiler_sha256"] and sha(runner) == report["runner_sha256"]
        report.update(ok=True, state="passed", actual_checked_source_rejections=14, physical_GPU_kernel_events=5, runtime_shape_or_bound_rejections=8,
                      finite_loop_reference_native_GPU_agreement=True, maximum_lanes=32768)
        assert len(report["source_rejections"]) == 14 and len(report["physical"]) == 5 and len(report["runner_rejections"]) == 8
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "actual_checked_source_rejections", "physical_GPU_kernel_events", "runtime_shape_or_bound_rejections"]}))


if __name__ == "__main__":
    main()
