"""Compare generated scalar Metal kernels with actual NEX reference/native execution."""
import argparse
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import time

MIN, MAX = -(1 << 63), (1 << 63) - 1
CODES = {0: None, 1: "E_OVERFLOW", 2: "E_DIV_ZERO", 3: "E_ASSERT", 4: "E_GPU_STEP_LIMIT", 5: "E_GPU_INTERNAL", 6: "E_GPU_INPUT"}


def checked(value):
    return value if MIN <= value <= MAX else "E_OVERFLOW"


def quotient(x, y):
    if not y:
        return "E_DIV_ZERO"
    value = abs(x) // abs(y)
    return checked(-value if (x < 0) != (y < 0) else value)


def remainder(x, y):
    if not y:
        return "E_DIV_ZERO"
    value = abs(x) % abs(y)
    return -value if x < 0 else value


def fixtures():
    rng = random.Random(0x4e4558)
    edges = [MIN, MIN + 1, -3037000500, -3037000499, -(1 << 32), -3, -1, 0, 1, 3, 1 << 32, 3037000499, 3037000500, MAX - 1, MAX]
    rows = list(itertools.product(edges, repeat=2)) + [(rng.randrange(MIN, MAX + 1), rng.randrange(MIN, MAX + 1)) for _ in range(64)]
    cases = []
    for name, operator, oracle in [
        ("add", "+", lambda x, y: checked(x + y)),
        ("subtract", "-", lambda x, y: checked(x - y)),
        ("multiply", "*", lambda x, y: checked(x * y)),
        ("divide", "/", quotient), ("remainder", "%", remainder)]:
        cases.append({"name": name, "source": "fn transform(x:i64,y:i64)->i64{return x" + operator + "y;}", "rows": rows,
                      "gold": [oracle(x, y) for x, y in rows], "types": ["i64", "i64"], "result": "i64"})
    extra = [
        ("negate", "fn transform(x:i64)->i64{return -x;}", [(x,) for x in edges], [checked(-x) for x in edges], ["i64"], "i64"),
        ("comparisons", "fn transform(x:i64,y:i64)->i64{if x<y{return -1;}if x==y{return 0;}assert(x>y);return 1;}", rows, [(x > y) - (x < y) for x, y in rows], ["i64", "i64"], "i64"),
        ("loop_helpers", "fn helper(x:i64)->i64{return x*3;}fn transform(x:i64,y:i64)->i64{var out:i64=helper(x);var i:i64=0;while i<y{out=out+1;i=i+1;}return out;}",
         [(x, y) for x in [-9, 0, 17] for y in [-1, 0, 4, 20]], [x * 3 + max(0, y) for x in [-9, 0, 17] for y in [-1, 0, 4, 20]], ["i64", "i64"], "i64"),
        ("lazy_boolean", "fn boom()->bool{return (1/0)==0;}fn transform(x:bool,y:bool)->bool{return x&&(y||boom());}",
         [(False, False), (False, True), (True, False), (True, True)], [False, False, "E_DIV_ZERO", True], ["bool", "bool"], "bool"),
        ("lazy_or", "fn boom()->bool{return (1/0)==0;}fn transform(x:bool,y:bool)->bool{return x||(!y&&boom());}",
         [(False, False), (False, True), (True, False), (True, True)], ["E_DIV_ZERO", False, True, True], ["bool", "bool"], "bool"),
        ("left_to_right_operands", "fn transform(x:i64,y:i64)->i64{return x/0+(9223372036854775807+y);}", [(1, 1)], ["E_DIV_ZERO"], ["i64", "i64"], "i64"),
        ("left_to_right_arguments", "fn use(x:i64,y:i64)->i64{return 0;}fn transform(x:i64,y:i64)->i64{return use(9223372036854775807+x,y/0);}",
         [(1, 1)], ["E_OVERFLOW"], ["i64", "i64"], "i64"),
        ("source_contracts", "fn transform(x:i64,y:i64)->i64 requires(x>=0) ensures(r=>r>=x){return x+y;}",
         [(1, 2), (-1, 2), (3, -2), (MAX, 1)], [3, "E_ASSERT", "E_ASSERT", "E_OVERFLOW"], ["i64", "i64"], "i64"),
        ("loop_contracts", "fn transform(x:i64,y:i64)->i64{var i:i64=x;while i<y invariant(i>=0) decreases(y-i){i=i+1;}return i;}",
         [(0, 5), (2, 9), (-1, 4)], [5, 9, "E_ASSERT"], ["i64", "i64"], "i64"),
        ("lexical_scopes", "fn transform(x:i64,y:i64)->i64{var answer:i64=x;if y>0{let answer:i64=y;assert(answer==y);}return answer;}",
         [(3, 8), (-4, 9), (7, -1)], [3, -4, 7], ["i64", "i64"], "i64"),
        ("generic_helpers", "fn identity<T>(x:T)->T{return x;}fn transform(x:i64,y:i64)->i64{return identity<i64>(x)+identity<i64>(y);}",
         [(3, 8), (MAX, 0), (MIN, 1)], [11, MAX, MIN + 1], ["i64", "i64"], "i64"),
        ("unit_helper", "fn require_positive(x:i64)->unit{assert(x>0);}fn transform(x:i64)->i64{require_positive(x);return x;}",
         [(3,), (0,), (-1,)], [3, "E_ASSERT", "E_ASSERT"], ["i64"], "i64"),
        ("unit_root", "fn transform(x:i64,y:i64)->unit{assert(x<y);}", [(1, 2), (3, 2)], [0, "E_ASSERT"], ["i64", "i64"], "unit"),
        ("constant", "fn transform()->i64{return 42;}", [()] * 8, [42] * 8, [], "i64"),
        ("reachable_only", 'fn unused()->str{return "NEX_unreachable_device_secret";}fn also_unused(x:f64)->f64{return x;}fn transform(x:i64)->i64{return x+1;}',
         [(0,), (5,)], [1, 6], ["i64"], "i64"),
    ]
    for name, source, values, gold, types, result in extra:
        cases.append(dict(name=name, source=source, rows=values, gold=gold, types=types, result=result))
    return cases


def literal(value):
    return ("true" if value else "false") if type(value) is bool else str(value)


def invocation(values):
    return "transform(" + ",".join(literal(x) for x in values) + ")"


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
    report = {"schema": "nex.generated-Metal-agreement/1", "ok": False, "commands": [], "cases": [],
              "compiler_sha256": sha(compiler), "runner_sha256": sha(runner), "installed_SDK_accepted": False,
              "source_task_provider_integrated": False, "general_GPU_backend_complete": False}
    start = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - start
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(name, argv, cwd, expected=0):
        p = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, capture_output=True, text=True, timeout=900)
        (out / (name + ".stdout")).write_text(p.stdout)
        (out / (name + ".stderr")).write_text(p.stderr)
        report["commands"].append({"label": name, "argv": list(map(str, argv)), "exit_code": p.returncode})
        save()
        if p.returncode != expected:
            raise AssertionError((name, p.returncode, p.stdout[-3000:], p.stderr[-3000:]))
        return p

    def project(path, case, body):
        path.mkdir()
        (path / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"}) + "\n")
        (path / "main.nex").write_text("module generated_gpu;\n" + case["source"] + "\nfn main()->unit !{io}{" + body + "}\n")

    try:
        for case in fixtures():
            name = case["name"]
            directory = out / name
            directory.mkdir()
            valid = [(row, gold) for row, gold in zip(case["rows"], case["gold"]) if type(gold) is not str]
            values = [invocation(row) for row, gold in valid]
            if case["result"] == "unit":
                body = "".join(x + ";" for x in values) + "print(42);"
            else:
                body = "print(encode_json([" + ",".join(values) + "]));" if values else "print(42);"
            source = directory / "CPU-project"
            project(source, case, body)
            emission = directory / "emitted"
            run(name + "-codegen", [sys.executable, "-B", Path(__file__).with_name("codegen.py"), "--sdk", sdk, "--project", source, "--symbol", "transform", "--output", emission], source)
            metadata = json.loads((emission / "report.json").read_bytes())
            assert metadata["ok"] and metadata["parameter_types"] == case["types"] and metadata["result_type"] == case["result"]
            # NEX wire JSON represents i64 as exact decimal strings, including
            # small values. Bool remains a JSON boolean.
            wire_values = [str(gold) if case["result"] == "i64" else gold for row, gold in valid]
            expected_stdout = "42\n" if case["result"] == "unit" or not values else json.dumps(wire_values, separators=(",", ":")) + "\n"
            reference = json.loads(run(name + "-reference", [compiler, "eval", "--json"], source).stdout)
            # JSON permits insignificant spaces; compare its actual value.
            expected_value = json.loads(expected_stdout)
            assert json.loads(reference["stdout"]) == expected_value
            built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--json"], source).stdout)
            native = run(name + "-native", [built["executable"]], source)
            assert json.loads(native.stdout) == expected_value
            input_file = directory / "input.bin"
            input_file.write_bytes(b"".join(struct.pack("<q", int(value)) for row in case["rows"] for value in row))
            physical = json.loads(run(name + "-GPU", [runner, emission / "kernel.metal", input_file, directory / "output.bin", directory / "errors.bin", str(len(case["rows"])), str(len(case["types"])), "4096", "0"], directory).stdout)
            assert physical["ok"] and physical["Metal_command_buffer_status"] == 4 and physical["completion_handlers"] == 1
            assert physical["physical_completion_before_readback"] and physical["all_three_buffers_released_after_completion"] and not physical["CPU_substitute"]
            output = struct.unpack("<" + "q" * len(case["rows"]), (directory / "output.bin").read_bytes())
            errors = struct.unpack("<" + "I" * len(case["rows"]), (directory / "errors.bin").read_bytes())
            for actual, code, expected in zip(output, errors, case["gold"]):
                if type(expected) is str:
                    assert CODES[code] == expected and actual == 0, (name, actual, code, expected)
                else:
                    assert code == 0 and actual == int(expected), (name, actual, code, expected)
            cpu_errors = []
            for code in sorted({gold for gold in case["gold"] if type(gold) is str}):
                index = next(i for i, gold in enumerate(case["gold"]) if gold == code)
                trap = directory / code
                project(trap, case, invocation(case["rows"][index]) + ";")
                result = json.loads(run(name + "-" + code + "-reference", [compiler, "eval", "--json"], trap, 1).stdout)
                assert result["code"] == code
                built = json.loads(run(name + "-" + code + "-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--json"], trap).stdout)
                result = run(name + "-" + code + "-native", [built["executable"]], trap, 70)
                assert code in result.stderr and result.stdout == ""
                cpu_errors.append(code)
            if name == "reachable_only":
                assert "NEX_unreachable_device_secret" not in (emission / "kernel.metal").read_text() and len(metadata["functions"]) == 1
            report["cases"].append({"name": name, "NEX_reference_native_and_Metal": True, "lanes": len(case["rows"]), "analytical_integer_oracle": True,
                                    "CPU_error_codes_checked_in_both_modes": cpu_errors, "physical": physical, "kernel_sha256": sha(emission / "kernel.metal")})
            save()
        assert sha(compiler) == report["compiler_sha256"] and sha(runner) == report["runner_sha256"]
        report.update(ok=True, state="passed", three_way_cases=len(report["cases"]), physical_GPU_kernel_events=len(report["cases"]),
                      checked_lanes=sum(x["lanes"] for x in report["cases"]))
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "three_way_cases", "physical_GPU_kernel_events", "checked_lanes"]}))


if __name__ == "__main__":
    main()
