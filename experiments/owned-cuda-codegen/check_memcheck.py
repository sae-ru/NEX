"""Local source/reader/process controls only; never execute a CUDA sanitizer."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "project", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    compiler, resources, project = [p.resolve(strict=True) for p in [args.compiler, args.resources, args.project]]
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("generated_CUDA_memcheck_control", source / "memcheck.py")
    memcheck = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(memcheck)
    report = {"schema": "nex.experimental-generated-CUDA-memcheck-source-controls/1", "ok": False,
        "commands": [], "synthetic_log_contracts": [], "synthetic_argument_contracts": [],
        "actual_GPU_execution": False, "actual_Compute_Sanitizer_execution": False,
        "source_sha256": {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in ["verify.py", "memcheck.py", "check_memcheck.py"]}}
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEX_", "PYTHON"))}
    env.update(NEX_RESOURCE_DIR=str(resources), PYTHONDONTWRITEBYTECODE="1")

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def run(label, argv, expected=0):
        assert all(hashlib.sha256((source / n).read_bytes()).hexdigest() == h for n, h in report["source_sha256"].items())
        row = {"label": label, "argv": list(map(str, argv))}
        report["commands"].append(row)
        value = subprocess.run(row["argv"], cwd=out, env=env, capture_output=True, timeout=600)
        (out / (label + ".stdout")).write_bytes(value.stdout)
        (out / (label + ".stderr")).write_bytes(value.stderr)
        row["exit_code"] = value.returncode
        save()
        assert value.returncode == expected, (label, value.stderr[-2000:])
        return value

    def accepts(function, *values):
        try:
            function(*values)
            return True
        except RuntimeError:
            return False

    try:
        run("actual-NEX-corpus", [sys.executable, "-B", source / "verify.py", "--compiler", compiler, "--resources", resources,
            "--project", project, "--check-only", "--output", out / "corpus"])
        base = json.loads((out / "corpus/report.json").read_bytes())
        assert base["schema"] == "nex.experimental-owned-CUDA-scalar-parent-verification/2" and base["ok"] and base["source_cases_checked"] == 15
        assert not base["actual_GPU_execution"] and base["retained_input_sha256"] == {}
        missing_tool = out / "tool-must-not-be-resolved"
        invalid_output = out / "must-not-start-sanitizer"
        rejected = run("actual-source-receipt-rejected", [sys.executable, "-B", source / "memcheck.py", "--hardware-report", out / "corpus/report.json",
            "--sanitizer", missing_tool, "--output", invalid_output], 1)
        assert b"complete physical generated-CUDA v2 hardware report is required" in rejected.stderr
        assert not invalid_output.exists() and not missing_tool.exists()
        report["actual_source_only_receipt_rejected_before_tool_resolution"] = True
        header = "========= COMPUTE-SANITIZER\n"
        zero = "========= LEAK SUMMARY: 0 bytes leaked in 0 allocations\n========= ERROR SUMMARY: 0 errors\n"
        contracts = [("zero", header + zero, True), ("zero-ignored", header + zero.replace("0 errors", "0 errors (0 ignored)"), True),
            ("zero-suppressed", header + zero.replace("0 errors", "0 errors (0 suppressed)"), True),
            ("Windows-CRLF", (header + zero).replace("\n", "\r\n"), True),
            ("two-zero-summaries", header + zero + zero, True), ("empty", "", False), ("no-header", zero, False),
            ("memory-errors", header + zero.replace("0 errors", "1 errors"), False),
            ("device-leak", header + zero.replace("0 bytes leaked in 0", "128 bytes leaked in 1"), False),
            ("missing-leak-summary", header + "========= ERROR SUMMARY: 0 errors\n", False),
            ("zero-before-later-error", header + zero + zero.replace("0 errors", "2 errors"), False),
            ("zero-before-later-leak", header + zero + zero.replace("0 bytes leaked in 0", "8 bytes leaked in 1"), False),
            ("ignored-errors", header + zero.replace("0 errors", "0 errors (1 ignored)"), False),
            ("thousands-ignored", header + zero.replace("0 errors", "0 errors (1,024 ignored)"), False),
            ("malformed-ignored", header + zero.replace("0 errors", "0 errors (unknown ignored)"), False),
            ("extra-malformed-summary", header + zero + "========= LEAK SUMMARY: unknown\n", False),
            ("unparsed-thousands-leak", header + zero.replace("0 bytes leaked in 0", "1,024 bytes leaked in 1"), False)]
        for name, text, expected in contracts:
            path = out / (name + ".synthetic-memcheck.log")
            path.write_text(text, encoding="utf-8")
            actual = accepts(memcheck.parse_summary, text)
            assert actual == expected, name
            report["synthetic_log_contracts"].append({"name": name, "synthetic_only": True, "accepted": actual})
        executable, foreign = out / "contract-app", out / "contract-authority.json"
        argv = [str(executable), "--nex-foreign", str(foreign), "--nex-task-workers", "1", "--nex-task-timeout-ms", "2000"]
        argument_cases = [("unchanged-deadline", argv, 2000, True), ("changed-deadline", argv[:-1] + ["30000"], 2000, False),
            ("changed-cancel-budget", argv, 5000, False), ("extra-option", argv + ["--nex-task-steps", "999999"], 2000, False),
            ("different-workers", argv[:4] + ["2"] + argv[5:], 2000, False),
            ("different-executable", [str(out / "other-app"), *argv[1:]], 2000, False),
            ("different-authority", argv[:2] + [str(out / "other-authority.json"), *argv[3:]], 2000, False)]
        for name, values, timeout, expected in argument_cases:
            actual = accepts(memcheck.check_native_command, values, executable, foreign, timeout)
            assert actual == expected, name
            report["synthetic_argument_contracts"].append({"name": name, "synthetic_only": True, "accepted": actual})
        artifact = out / "retained-input-control"
        artifact.write_bytes(b"original local input\n")
        pins = {str(artifact): hashlib.sha256(artifact.read_bytes()).hexdigest()}
        memcheck.check_pins(pins)
        artifact.write_bytes(b"changed local input\n")
        assert not accepts(memcheck.check_pins, pins)
        report["actual_changed_input_rejected"] = True
        # This is a real process-group timeout control, not a simulated CUDA run.
        if os.name != "nt":
            child_pid = out / "timeout-child.pid"
            program = 'import pathlib,subprocess,sys,time\np=subprocess.Popen([sys.executable,"-I","-B","-c","import time;time.sleep(60)"])\npathlib.Path(sys.argv[1]).write_text(str(p.pid))\nprint("started",flush=True)\ntime.sleep(60)\n'
            code, stdout, stderr, timed_out = memcheck.run_bounded([sys.executable, "-I", "-B", "-c", program, child_pid], out, env, 1)
            assert timed_out and code != 0 and stdout == b"started\n" and not stderr
            pid = int(child_pid.read_text())
            retired = False
            for _ in range(100):
                status = subprocess.run(["/bin/ps", "-p", str(pid), "-o", "stat="], capture_output=True, text=True, timeout=10)
                if status.returncode == 1 or "Z" in status.stdout:
                    retired = True
                    break
                time.sleep(0.02)
            assert retired
            report["actual_POSIX_timeout_parent_and_child_retired"] = True
        assert all(hashlib.sha256((source / n).read_bytes()).hexdigest() == h for n, h in report["source_sha256"].items())
        report.update(ok=True, actual_NEX_cases_checked=15, synthetic_log_contracts_checked=len(contracts),
            false_log_contracts_rejected=sum(not expected for _, _, expected in contracts), synthetic_argument_contracts_checked=len(argument_cases),
            false_argument_contracts_rejected=sum(not expected for _, _, _, expected in argument_cases),
            compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest())
    except BaseException as error:
        report["error"] = repr(error)
        raise
    finally:
        save()
    print(json.dumps({k: report[k] for k in ["ok", "actual_NEX_cases_checked", "false_log_contracts_rejected", "false_argument_contracts_rejected", "actual_GPU_execution"]}))


if __name__ == "__main__":
    main()
