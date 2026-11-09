"""Check malformed replies in the generated-map protocol on physical Metal."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


UPLOAD = '''let s:d::Session=unwrap(make_context());let bad:result<d::Buffer>=upload_raw(s,1,encode_i64s([6]));assert(error_code(bad)=="E_DEVICE_PROTOCOL");assert(error_code(upload_raw(s,1,encode_i64s([7])))=="E_DEVICE_LOST");resource_close(s);'''
MAP = '''let s:d::Session=unwrap(make_context());let a:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([6])));let b:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([2])));let bad:result<d::Buffer>=map_raw(s,[a,b],1,512);assert(error_code(bad)=="E_DEVICE_PROTOCOL");assert(error_code(upload_raw(s,1,encode_i64s([7])))=="E_DEVICE_LOST");resource_close(a);resource_close(b);resource_close(s);'''
DOWNLOAD = '''let s:d::Session=unwrap(make_context());let a:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([6])));assert(error_code(read_buffer(a))=="E_DEVICE_PROTOCOL");assert(error_code(read_buffer(a))=="E_DEVICE_LOST");resource_close(a);resource_close(s);'''
# body, real kernels, worker buffers at final drainage, published buffers,
# exact resource quota, controlled reply name, expected fatal code
CASES = {
    "upload_truncated": (UPLOAD, 0, 1, 0, 2, "upload_truncated", None),
    "upload_wrong_size": (UPLOAD, 0, 1, 0, 2, "upload_wrong_size", None),
    "upload_reused_id": ('''let s:d::Session=unwrap(make_context());let held:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([6])));assert(error_code(upload_raw(s,1,encode_i64s([2])))=="E_DEVICE_PROTOCOL");assert(error_code(read_buffer(held))=="E_DEVICE_LOST");resource_close(held);resource_close(s);''', 0, 2, 1, 3, "upload_reused_id", None),
    **{name: (MAP, 1, 3, 2, 4, name, None) for name in [
        "map_truncated", "map_trailing", "map_reused_id", "map_wrong_size", "map_bad_status", "map_bad_handlers"]},
    "download_truncated": (DOWNLOAD, 0, 1, 1, 3, "download_truncated", None),
    "download_wrong_size": (DOWNLOAD, 0, 1, 1, 3, "download_wrong_size", None),
    "free_trailing": ('''let s:d::Session=unwrap(make_context());let held:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([6])));with_tasks(1,server fn(scope:task_scope)->unit !{task,ffi}{let child:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([2])));resource_close(child);});assert(error_code(read_buffer(held))=="E_DEVICE_LOST");resource_close(held);resource_close(s);''', 0, 1, 2, 3, "free_trailing", None),
    "close_truncated": ('''with_tasks(1,server fn(scope:task_scope)->unit !{task,ffi}{let s:d::Session=unwrap(make_context());let a:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([6])));resource_close(a);resource_close(s);});''', 0, 0, 1, 2, "close_truncated", None),
    "open_trailing": ('''let bad:result<d::Session>=make_context();assert(error_code(bad)=="E_DEVICE_PROTOCOL");''', 0, 0, 0, 1, "open_trailing", None),
    "try_apply_keeps_protocol_failure": ('''let s:d::Session=unwrap(make_context());assert(error_code(try_apply(s,[encode_i64s([6]),encode_i64s([2])],1,512))=="E_DEVICE_PROTOCOL");assert(error_code(try_apply(s,[encode_i64s([6]),encode_i64s([2])],1,512))=="E_DEVICE_LOST");resource_close(s);''', 1, 3, 2, 4, "map_bad_status", None),
    "apply_protocol_trap_skips_handlers": ('''let s:d::Session=unwrap(make_context());try{let output:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);}catch(code,message){print(98);}finally{print(99);}''', 1, 3, 2, 4, "map_trailing", "E_DEVICE_PROTOCOL"),
}


def inspect_trace(path, fault, kernels, drained, published):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert not any(row["event"] == "unsettled" for row in rows)
    ends = [row for row in rows if row["event"] == "session_destroyed"]
    failures = [row for row in rows if row["event"] == "failed_session_drained"]
    assert len(ends) == len(failures) == 1
    assert ends[0]["physical_completion_verified"] and failures[0]["physical_completion_verified"]
    sessions = [row for row in rows if row["event"] == "session_created"]
    assert len(sessions) == (0 if fault == "open_trailing" else 1)
    assert all(row["backend"] == "Metal" and row["registryID"] > 0 and not row["cpu_fallback"] for row in sessions)
    created = [(row["session"], row["buffer"]) for row in rows if row["event"] == "buffer_created"]
    released = [(row["session"], row["buffer"]) for row in rows if row["event"] == "buffer_released"]
    assert len(created) == len(set(created)) == published and len(released) == len(set(released)) == published and set(created) == set(released)
    cursors = [(row["session"], row["cursor"]) for row in rows if row["event"] == "read_cursor_created"]
    closed = [(row["session"], row["cursor"]) for row in rows if row["event"] == "read_cursor_destroyed"]
    assert len(cursors) == len(set(cursors)) == len(closed) == len(set(closed)) and set(cursors) == set(closed)
    assert all(row["physical_completion_verified"] for row in rows if row["event"] == "buffer_released")
    assert all(row["steady_ns"] < ends[0]["steady_ns"] for row in rows if row["event"] == "buffer_released")
    if fault != "close_truncated":
        assert all(row["steady_ns"] >= failures[0]["steady_ns"] for row in rows if row["event"] == "buffer_released")
    diagnostics = [row for row in rows if row["event"] == "worker_diagnostics"]
    assert len(diagnostics) == 1 and diagnostics[0]["bounded_capture"] and diagnostics[0]["bytes"] <= 65536
    raw = bytes.fromhex(diagnostics[0]["hex"]).decode("utf-8", errors="strict")
    assert "controlled worker stdout diagnostic" in raw
    opened = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_OPEN ")]
    physical = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_MAP ")]
    drainage = [tuple(map(int, line.split()[1:])) for line in raw.splitlines() if line.startswith("NEXGPU_DRAIN ")]
    assert len(opened) == 1 and opened[0][1] > 0 and drainage == [(drained, 1)]
    assert all(row["registryID"] == opened[0][1] for row in sessions)
    assert len(physical) == kernels and all(len(p) == 7 and p[0:2] == (1, 512) and p[2] > 0 and p[3:5] == (0, 0) and p[5:] == (4, 1) for p in physical)
    assert len([line for line in raw.splitlines() if line.startswith("NEXGPU_FAULT " + fault + " ")]) == 1
    queued = [row for row in rows if row["event"] == "kernel_queued"]
    assert len(queued) == kernels and all(row["physical_enqueue_verified"] for row in queued)
    # Corrupt success cannot publish a completed kernel or its output Buffer.
    assert not any(row["event"] in ["kernel_completed", "kernel_failure_settled"] for row in rows)
    exited = [row for row in rows if row["event"] == "worker_exited"]
    assert len(exited) == 1 and exited[0]["exit_code"] == exited[0]["signal"] == 0
    return {"Metal_registryID": opened[0][1], "physical_GPU_events": physical, "worker_drained_buffers": drained,
            "published_buffers": published, "released_buffers": len(released), "closed_cursors": len(closed),
            "physical_session_retired": True, "unpublished_capacity_returned_after_drain": True}


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
    language = json.loads((project / "nex.json").read_text())["language"]
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEX_OWNED_METAL_MAP_TEST_")}
    env.update(NEX_RESOURCE_DIR=str(sdk / "share/nex"), PYTHONDONTWRITEBYTECODE="1", NEX_OWNED_METAL_MAP_TEST_NOISE="1")
    report = {"schema": "nex.owned-generated-Metal-reply-faults/1", "ok": False, "state": "running", "commands": [], "cases": [],
              "compiler_sha256": sha(compiler), "worker_sha256": sha(project / "bundle/worker"), "module_sha256": sha(project / "bundle/module.so"),
              "manifest_sha256": sha(project / "bundle/manifest.json"), "harness_sha256": sha(Path(__file__)),
              "source_only": args.source_only, "installed_SDK_accepted": False, "whole_original_goal_complete": False}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, argv, cwd, expected=0, extra=None):
        row = {"label": label, "argv": list(map(str, argv)), "cwd": str(cwd)}
        report["commands"].append(row)
        save()
        result = subprocess.run(row["argv"], cwd=cwd, env={**env, **(extra or {})}, capture_output=True, text=True, timeout=300)
        (out / (label + ".stdout")).write_text(result.stdout)
        (out / (label + ".stderr")).write_text(result.stderr)
        row["exit_code"] = result.returncode
        save()
        assert result.returncode == expected, (label, result.returncode, result.stdout[-2000:], result.stderr[-2000:])
        return result

    try:
        for name, case in CASES.items():
            if args.only and name not in args.only:
                continue
            body, kernels, drained, published, quota, fault, fatal = case
            directory = out / name
            directory.mkdir()
            (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": language, "entry": "main.nex", "libraries": {"std": str(project / "stdlib")}}) + "\n")
            (directory / "main.nex").write_text(prefix + "server fn main()->unit !{task,ffi,io,throw}{" + body + ("" if fatal else "print(42);") + "}\n")
            catalogue = json.loads((project / "foreign.json").read_bytes())
            catalogue["libraries"]["gpu"]["directory"] = str(project / "bundle")
            catalogue["resource_limit"] = quota
            foreign = directory / "foreign.json"
            foreign.write_text(json.dumps(catalogue, indent=2) + "\n")
            run(name + "-check", [compiler, "check", "--json"], directory)
            if args.source_only:
                report["cases"].append({"name": name, "checked_source": True})
                save()
                continue
            observed = {}
            for mode in ["reference", "native"]:
                trace = directory / (mode + ".trace.jsonl")
                if mode == "reference":
                    argv = [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--json"]
                else:
                    built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--json"], directory).stdout)
                    argv = [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1"]
                result = run(name + "-" + mode, argv, directory, (1 if mode == "reference" else 70) if fatal else 0,
                             {"NEX_OWNED_METAL_MAP_TEST_BAD_REPLY": fault, "NEX_OWNED_METAL_MAP_TRACE": str(trace)})
                if mode == "reference":
                    value = json.loads(result.stdout)
                    if fatal:
                        assert value["code"] == fatal and value["stdout"] == ""
                    else:
                        assert value["stdout"] == "42\n" and value["foreign_resource_bytes_after_scope"] == 0
                elif fatal:
                    assert fatal in result.stderr and result.stdout == ""
                else:
                    assert result.stdout == "42\n" and result.stderr == ""
                observed[mode] = inspect_trace(trace, fault, kernels, drained, published)
            assert observed["reference"]["Metal_registryID"] == observed["native"]["Metal_registryID"]
            report["cases"].append({"name": name, "native_reference": True, "expected_fatal": fatal, "physical": observed})
            save()
        assert sha(compiler) == report["compiler_sha256"] and sha(project / "bundle/worker") == report["worker_sha256"] and sha(project / "bundle/module.so") == report["module_sha256"]
        report.update(ok=True, state="passed", full_suite=not args.only, native_reference_pairs=0 if args.source_only else len(report["cases"]),
                      actual_GPU_execution=not args.source_only, physical_GPU_kernel_events=sum(len(case["physical"][mode]["physical_GPU_events"]) for case in report["cases"] for mode in ["reference", "native"]) if not args.source_only else 0)
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "source_only", "native_reference_pairs", "physical_GPU_kernel_events"]}))


if __name__ == "__main__":
    main()
