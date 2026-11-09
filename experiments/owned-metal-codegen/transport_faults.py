"""Exercise generated Metal framing, pending progress and UTF-8 error packets."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

HERE = Path(__file__).parent
spec = importlib.util.spec_from_file_location("generated_payload_faults", HERE / "faults.py")
payloads = importlib.util.module_from_spec(spec)
spec.loader.exec_module(payloads)
spec = importlib.util.spec_from_file_location("generated_transport_trace", HERE / "verify.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

FRAMES = ["frame_magic", "frame_version", "frame_sequence", "frame_operation", "frame_status", "frame_oversize", "frame_header_truncated", "frame_payload_truncated"]
PROGRESS = ["progress_truncated", "progress_trailing", "progress_tag", "progress_state_low", "progress_state_high", "progress_gate", "progress_duplicate", "progress_sequence", "progress_operation"]
FAILURES = ["failure_truncated", "failure_trailing", "failure_empty_code", "failure_long_code", "failure_code_prefix", "failure_code_lowercase", "failure_code_utf8", "failure_message_long", "failure_message_overlong_utf8", "failure_message_surrogate", "failure_message_beyond_scalar", "failure_message_truncated_utf8", "failure_message_NUL"]
BAD_FAILURE = payloads.MAP.replace("encode_i64s([6])", "encode_i64s([9223372036854775807])").replace("encode_i64s([2])", "encode_i64s([0])")
HEALTHY = '''let s:d::Session=unwrap(make_context());let bad:result<bytes>=try_apply(s,[encode_i64s([9223372036854775807]),encode_i64s([0])],1,512);assert(error_code(bad)=="E_OVERFLOW");@MESSAGE_ASSERT@let good:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);assert(decode_i64s(good)==[22]);resource_close(s);'''
CASES = {}
for name in FRAMES + PROGRESS + FAILURES:
    CASES[name] = {"body": BAD_FAILURE if name in FAILURES else payloads.MAP, "fault": name, "gate": 1500 if name in PROGRESS else 0,
                   "errors": int(name in FAILURES), "drained": 2 if name in FAILURES else 3,
                   "queued": int(name not in PROGRESS or name == "progress_duplicate"), "fatal": None, "timeout": 30000, "healthy": False}
CASES["failure_valid_utf8"] = {"body": HEALTHY.replace("@MESSAGE_ASSERT@", 'assert(error_message(bad)=="ошибка 🧠");'), "fault": "failure_valid_utf8", "healthy": True}
CASES["failure_valid_utf8_limit"] = {"body": HEALTHY.replace("@MESSAGE_ASSERT@", 'var expected:str="";var i:i64=0;while i<1024{expected=expected+"é";i=i+1;}assert(error_message(bad)==expected);'), "fault": "failure_valid_utf8_limit", "healthy": True}
for name, original in [("cancel_during_bad_progress", "cancel_enqueued_generated_GPU"), ("deadline_during_bad_progress", "deadline_enqueued_generated_GPU")]:
    body, fatal, gate, timeout, errors = verify.ERROR_CASES[original]
    CASES[name] = {"body": body, "fault": "progress_duplicate", "gate": gate, "errors": errors, "drained": 3, "queued": 1, "fatal": fatal, "timeout": timeout, "healthy": False}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_trace(path, case):
    if case["healthy"]:
        physical = verify.inspect_trace(path, 2, 1)
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert not any(row["event"] == "unsettled" for row in rows)
    sessions = [row for row in rows if row["event"] == "session_created"]
    ends = [row for row in rows if row["event"] == "session_destroyed"]
    assert len(sessions) == len(ends) == 1 and sessions[0]["backend"] == "Metal" and sessions[0]["registryID"] > 0 and not sessions[0]["cpu_fallback"]
    assert ends[0]["physical_completion_verified"]
    created = [(row["session"], row["buffer"]) for row in rows if row["event"] == "buffer_created"]
    released = [(row["session"], row["buffer"]) for row in rows if row["event"] == "buffer_released"]
    assert len(created) == len(set(created)) == (5 if case["healthy"] else 2)
    assert len(released) == len(set(released)) == len(created) and set(created) == set(released)
    assert all(row["physical_completion_verified"] and row["steady_ns"] < ends[0]["steady_ns"] for row in rows if row["event"] == "buffer_released")
    cursors = [(row["session"], row["cursor"]) for row in rows if row["event"] == "read_cursor_created"]
    closed = [(row["session"], row["cursor"]) for row in rows if row["event"] == "read_cursor_destroyed"]
    assert len(cursors) == len(set(cursors)) == len(closed) == len(set(closed)) and set(cursors) == set(closed)
    diagnostics = [row for row in rows if row["event"] == "worker_diagnostics"]
    assert len(diagnostics) == 1 and diagnostics[0]["bounded_capture"] and diagnostics[0]["bytes"] <= 65536
    raw = bytes.fromhex(diagnostics[0]["hex"]).decode("utf-8", errors="strict")
    assert "controlled worker stdout diagnostic" in raw
    opened = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_OPEN ")]
    kernels = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_MAP ")]
    admitted = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_ADMITTED ")]
    drainage = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_DRAIN ")]
    count = 2 if case["healthy"] else 1
    assert len(opened) == 1 and opened[0][1] == sessions[0]["registryID"] and len(kernels) == len(admitted) == count
    assert all(len(k) == 7 and k[0:2] == (1, 512) and k[2] > 0 and k[5:] == (4, 1) for k in kernels)
    assert sum(k[3] != 0 for k in kernels) == (1 if case["healthy"] else case["errors"])
    assert all(k[3] in (0, 1) and k[4] == 0 for k in kernels)
    assert drainage == [(0 if case["healthy"] else case["drained"], 1)]
    assert len([line for line in raw.splitlines() if line.startswith("NEXGPU_FAULT " + case["fault"] + " ")]) == 1
    exited = [row for row in rows if row["event"] == "worker_exited"]
    # 20 is the pinned worker's error/EOF cleanup path, emitted only after
    # closeNoThrow + settled. Signals and unknown vendor settlement still fail.
    assert len(exited) == 1 and exited[0]["signal"] == 0 and exited[0]["exit_code"] in (0, 20)
    if case["healthy"]:
        assert exited[0]["exit_code"] == 0
        return {"physical_GPU_events": kernels, "physical": physical, "valid_UTF8_preserved": True, "session_recovered": True}
    failures = [row for row in rows if row["event"] == "failed_session_drained"]
    assert len(failures) == 1 and failures[0]["physical_completion_verified"]
    assert all(row["steady_ns"] >= failures[0]["steady_ns"] for row in rows if row["event"] == "buffer_released")
    queued = [row for row in rows if row["event"] == "kernel_queued"]
    assert len(queued) == case["queued"] and all(row["physical_enqueue_verified"] for row in queued)
    assert not any(row["event"] in ["kernel_completed", "kernel_failure_settled"] for row in rows)
    pending = None
    if case["gate"]:
        assert admitted[0][0] in (2, 3) and admitted[0][1] == 1
        pending = (failures[0]["steady_ns"] - admitted[0][2]) / 1e9
        assert pending >= 0.5 and all(row["controlled_shared_event"] and row["completion_pending"] for row in queued)
        if case["fatal"] == "E_CANCELLED":
            busy = [row for row in rows if row["event"] == "kernel_busy_observed"]
            assert busy and admitted[0][2] <= busy[0]["steady_ns"] < failures[0]["steady_ns"]
    return {"physical_GPU_events": kernels, "Metal_registryID": opened[0][1], "worker_exit_code": exited[0]["exit_code"],
            "physical_drained_buffers": case["drained"], "published_buffers": len(created), "released_buffers": len(released),
            "closed_cursors": len(closed), "physical_settlement_before_release": True, "pending_seconds": pending}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["sdk", "project", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--only", choices=CASES, action="append")
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    sdk, project, out = args.sdk.resolve(strict=True), args.project.resolve(strict=True), args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    compiler = sdk / "bin/nex"
    template = (project / "main.nex").read_text()
    prefix = template[:template.index("server fn main()->unit")]
    language = json.loads((project / "nex.json").read_bytes())["language"]
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEX_OWNED_METAL_MAP_TEST_")}
    env.update(NEX_RESOURCE_DIR=str(sdk / "share/nex"), PYTHONDONTWRITEBYTECODE="1", NEX_OWNED_METAL_MAP_TEST_NOISE="1")
    report = {"schema": "nex.owned-generated-Metal-transport-faults/1", "ok": False, "state": "running", "cases": [], "commands": [],
              "compiler_sha256": sha(compiler), "module_sha256": sha(project / "bundle/module.so"), "worker_sha256": sha(project / "bundle/worker"),
              "manifest_sha256": sha(project / "bundle/manifest.json"), "harness_sha256": sha(Path(__file__)), "source_only": args.source_only,
              "installed_SDK_accepted": False, "whole_original_goal_complete": False}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        p = out / "report.tmp"
        p.write_text(json.dumps(report, indent=2) + "\n")
        p.replace(out / "report.json")

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

    try:
        for name, case in CASES.items():
            if args.only and name not in args.only:
                continue
            directory = out / name
            directory.mkdir()
            (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": language, "entry": "main.nex", "libraries": {"std": str(project / "stdlib")}}) + "\n")
            (directory / "main.nex").write_text(prefix + "server fn main()->unit !{task,ffi,io,throw}{" + case["body"] + ("" if case.get("fatal") else "print(42);") + "}\n")
            catalogue = json.loads((project / "foreign.json").read_bytes())
            catalogue["libraries"]["gpu"]["directory"] = str(project / "bundle")
            catalogue["resource_limit"] = 4
            foreign = directory / "foreign.json"
            foreign.write_text(json.dumps(catalogue, indent=2) + "\n")
            run(name + "-check", [compiler, "check", "--json"], directory)
            if args.source_only:
                report["cases"].append({"name": name, "checked_source": True})
                save()
                continue
            timeout = case.get("timeout", 30000)
            control = {"NEX_OWNED_METAL_MAP_TEST_BAD_REPLY": case["fault"]}
            if case.get("gate"):
                control["NEX_OWNED_METAL_MAP_TEST_GATE_MS"] = str(case["gate"])
            observed = {}
            for mode in ["reference", "native"]:
                trace = directory / (mode + ".trace.jsonl")
                fatal = case.get("fatal")
                if mode == "reference":
                    argv = [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout), "--json"]
                else:
                    built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout), "--build-directory", out / "native", "--json"], directory).stdout)
                    argv = [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1", "--nex-task-timeout-ms", str(timeout)]
                p = run(name + "-" + mode, argv, directory, (1 if mode == "reference" else 70) if fatal else 0,
                        {**control, "NEX_OWNED_METAL_MAP_TRACE": str(trace)})
                if mode == "reference":
                    value = json.loads(p.stdout)
                    if fatal:
                        assert value["code"] == fatal and value["stdout"] == ""
                    else:
                        assert value["stdout"] == "42\n" and value["foreign_resource_bytes_after_scope"] == 0
                elif fatal:
                    assert fatal in p.stderr and p.stdout == ""
                else:
                    assert p.stdout == "42\n" and p.stderr == ""
                observed[mode] = inspect_trace(trace, case)
            report["cases"].append({"name": name, "expected_fatal": case.get("fatal"), "native_reference": True, "physical": observed})
            save()
        assert sha(compiler) == report["compiler_sha256"] and sha(project / "bundle/module.so") == report["module_sha256"] and sha(project / "bundle/worker") == report["worker_sha256"]
        report.update(ok=True, state="passed", full_suite=not args.only, native_reference_pairs=0 if args.source_only else len(report["cases"]),
                      actual_GPU_execution=not args.source_only, physical_GPU_kernel_events=0 if args.source_only else sum(len(c["physical"][m]["physical_GPU_events"]) for c in report["cases"] for m in ["reference", "native"]))
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "source_only", "native_reference_pairs", "physical_GPU_kernel_events"]}))


if __name__ == "__main__":
    main()
