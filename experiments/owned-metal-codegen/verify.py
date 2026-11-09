"""Require owned NEX reference/native execution of the generated two-argument fixture."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

HELPERS = '''
fn repeat_word(value:i64,count:i64)->bytes{var result:bytes=unwrap(bytes([]));var block:bytes=encode_i64s([value]);var n:i64=count;while n>0{if n%2==1{result=result+block;}n=n/2;if n>0{block=block+block;}}return result;}
server fn owned_output(session:d::Session,a:bytes,b:bytes,count:i64)->d::Buffer !{task,ffi}{let x:d::Buffer=unwrap(upload_raw(session,1,a));let y:d::Buffer=unwrap(upload_raw(session,1,b));let output:d::Buffer=unwrap(map_raw(session,[x,y],count,512));resource_close(x);resource_close(y);return output;}
'''
CASES = {
    "small_and_i64_codec": ('''let values:list<i64>=[-9223372036854775808,-9223372036854775807,-257,-256,-255,-1,0,1,255,256,257,9223372036854775807];assert(decode_i64s(encode_i64s(values))==values);let s:d::Session=unwrap(make_context());let actual:bytes=apply(s,[encode_i64s([6,6,0]),encode_i64s([2,-2,0])],3,512);assert(decode_i64s(actual)==[22,22,2]);resource_close(s);''', 1, 0, None),
    "overflow_Result_and_recovery": ('''let s:d::Session=unwrap(make_context());let bad:result<bytes>=try_apply(s,[encode_i64s([9223372036854775807]),encode_i64s([0])],1,512);assert(error_code(bad)=="E_OVERFLOW");let good:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);assert(decode_i64s(good)==[22]);resource_close(s);''', 2, 1, None),
    "maximum_lanes_and_input_columns": ('''let s:d::Session=unwrap(make_context());let actual:bytes=apply(s,[repeat_word(6,32768),repeat_word(2,32768)],32768,512);assert(len(actual)==262144);assert(actual==repeat_word(22,32768));resource_close(s);''', 1, 0, None),
    "returned_Buffer_retains_closed_Session": ('''let value:d::Buffer=with_tasks(1,server fn(scope:task_scope)->d::Buffer !{task,ffi,throw}{let s:d::Session=unwrap(make_context());let output:d::Buffer=owned_output(s,encode_i64s([6]),encode_i64s([2]),1);assert(resource_close(s));return output;});assert(decode_i64s(unwrap(read_buffer(value)))==[22]);assert(resource_close(value));''', 1, 0, None),
    "sibling_channel_hidden_parent": ('''let value:d::Buffer=with_tasks(1,server fn(scope:task_scope)->d::Buffer !{task,ffi,throw}{let channel:channel<d::Buffer>=channel_new<d::Buffer>(scope,0);let producer:task<bool>=task_spawn(scope,server fn()->bool !{task,ffi}{let s:d::Session=unwrap(make_context());let output:d::Buffer=owned_output(s,encode_i64s([6]),encode_i64s([2]),1);resource_close(s);return task_send(channel,output);});let consumer:task<d::Buffer>=task_spawn(scope,server fn()->d::Buffer !{task,ffi}{return unwrap(task_recv(channel));});let output:d::Buffer=task_wait(consumer);assert(task_wait(producer));return output;});assert(decode_i64s(unwrap(read_buffer(value)))==[22]);resource_close(value);''', 1, 0, None),
    "admitted_cursor_retains_closed_parents": ('''let s:d::Session=unwrap(make_context());let value:d::Buffer=owned_output(s,repeat_word(6,32768),repeat_word(2,32768),32768);let cursor:ReadCursor=unwrap(download_raw(value));assert(resource_close(value));assert(resource_close(s));let first:bytes=unwrap(read_next_raw(cursor));assert(first==repeat_word(22,32768));assert(unwrap(read_next_raw(cursor))==unwrap(bytes([])));assert(resource_close(cursor));assert(error_code(read_buffer(value))=="E_DEVICE_CLOSED");''', 1, 0, None),
    "cross_session_columns_rejected": ('''let first:d::Session=unwrap(make_context());let second:d::Session=unwrap(make_context());let a:d::Buffer=unwrap(upload_raw(first,1,encode_i64s([6])));let b:d::Buffer=unwrap(upload_raw(second,1,encode_i64s([2])));assert(error_code(map_raw(first,[a,b],1,512))=="E_GPU_INPUT");resource_close(a);resource_close(b);resource_close(first);resource_close(second);''', 0, 0, None),
    "malformed_shape_never_uploads": ('''let s:d::Session=unwrap(make_context());assert(error_code(try_apply(s,[encode_i64s([6]),encode_i64s([2])],0,512))=="E_GPU_INPUT");assert(error_code(try_apply(s,[encode_i64s([6])],1,512))=="E_GPU_INPUT");assert(error_code(try_apply(s,[encode_i64s([6]),encode_i64s([2])],2,512))=="E_GPU_INPUT");assert(resource_close(s));assert(error_code(try_apply(s,[encode_i64s([6]),encode_i64s([2])],1,512))=="E_DEVICE_CLOSED");''', 0, 0, None),
    "raw_geometry_rejected": ('''let s:d::Session=unwrap(make_context());let a:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([6])));let b:d::Buffer=unwrap(upload_raw(s,1,encode_i64s([2])));assert(error_code(map_raw(s,[a,b],0,1))=="E_GPU_INPUT");assert(error_code(map_raw(s,[a,b],32769,1))=="E_GPU_INPUT");assert(error_code(map_raw(s,[a,b],1,65537))=="E_GPU_INPUT");assert(error_code(map_raw(s,[a,b],32768,65536))=="E_GPU_INPUT");assert(error_code(map_raw(s,[a],1,512))=="E_GPU_INPUT");assert(error_code(map_raw(s,[a,b],2,512))=="E_GPU_INPUT");resource_close(a);resource_close(b);resource_close(s);''', 0, 0, None),
    "declared_capacity_prevents_dispatch": ('''let s:d::Session=unwrap(make_context());assert(error_code(try_apply(s,[encode_i64s([6]),encode_i64s([2])],1,512))=="E_COMPUTE_LIMIT");resource_close(s);''', 0, 0, 3),
    "typed_source_error_after_GPU": ('''let s:d::Session=unwrap(make_context());try{let answer:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);assert(decode_i64s(answer)==[22]);throw(7);}catch(value:i64){assert(value==7);}resource_close(s);''', 1, 0, None),
}
ERROR_CASES = {
    "cancel_enqueued_generated_GPU": ('''let s:d::Session=unwrap(make_context());with_tasks(1,server fn(scope:task_scope)->unit !{task,ffi,throw}{let child:task<unit>=task_spawn(scope,server fn()->unit !{task,ffi}{let answer:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);});while busy_raw(s)==0{task_yield();}assert(task_cancel(child));task_wait(child);});''', "E_CANCELLED", 1500, 5000, 0),
    "deadline_enqueued_generated_GPU": ('''let s:d::Session=unwrap(make_context());let answer:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);''', "E_TIMEOUT", 3000, 2000, 0),
    "explicit_unwrap_E_RESULT_skips_finally": ('''let s:d::Session=unwrap(make_context());try{let answer:bytes=unwrap(try_apply(s,[encode_i64s([9223372036854775807]),encode_i64s([0])],1,512));}finally{print(99);}''', "E_RESULT", 0, 30000, 1),
    "direct_overflow_skips_catch_and_finally": ('''let s:d::Session=unwrap(make_context());try{let answer:bytes=apply(s,[encode_i64s([9223372036854775807]),encode_i64s([0])],1,512);}catch(code,message){print(98);}finally{print(99);}''', "E_OVERFLOW", 0, 30000, 1),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_trace(path, kernels, errors, pending=False, cancelled=False):
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    sessions = [x for x in rows if x["event"] == "session_created"]
    assert sessions and all(x["backend"] == "Metal" and x["registryID"] > 0 and x["persistent"] and not x["cpu_fallback"] for x in sessions)
    assert len(sessions) == len([x for x in rows if x["event"] == "session_destroyed"])
    assert not any(x["event"] in ["unsettled", "failed_session_drained"] for x in rows)
    created = {(x["session"], x["buffer"]) for x in rows if x["event"] == "buffer_created"}
    released = {(x["session"], x["buffer"]) for x in rows if x["event"] == "buffer_released"}
    assert created == released
    cursors = {(x["session"], x["cursor"]) for x in rows if x["event"] == "read_cursor_created"}
    assert cursors == {(x["session"], x["cursor"]) for x in rows if x["event"] == "read_cursor_destroyed"}
    physical, noise = [], False
    for x in rows:
        if x["event"] == "worker_diagnostics":
            raw = bytes.fromhex(x["hex"]).decode("utf-8", errors="replace")
            noise |= "controlled worker stdout diagnostic" in raw
            for line in raw.splitlines():
                if line.startswith("NEXGPU_MAP "):
                    values = tuple(map(int, line.split()[1:]))
                    assert len(values) == 7 and values[2] > 0 and values[5:] == (4, 1)
                    physical.append(values)
        if x["event"] in ["kernel_completed", "kernel_failure_settled", "buffer_released", "session_destroyed"]:
            assert x["physical_completion_verified"]
        if x["event"] == "kernel_completed":
            assert x["operation"] == "generated_map" and x["Metal_command_buffer_status"] == 4 and x["completion_handlers"] == 1
    assert noise and len(physical) == kernels and sum(x[3] != 0 for x in physical) == errors, (path, physical, kernels, errors)
    queued = [x for x in rows if x["event"] == "kernel_queued"]
    assert len(queued) == kernels and all(x["physical_enqueue_verified"] for x in queued)
    failed = [x for x in rows if x["event"] == "kernel_failure_settled"]
    completed = [x for x in rows if x["event"] in ["kernel_completed", "kernel_failure_settled"]]
    assert len(completed) == kernels and len(failed) == errors
    codes = {1: "E_OVERFLOW", 2: "E_DIV_ZERO", 3: "E_ASSERT", 4: "E_GPU_STEP_LIMIT", 5: "E_GPU_INTERNAL", 6: "E_GPU_INPUT"}
    assert sorted(x["code"] for x in failed) == sorted(codes[x[3]] for x in physical if x[3])
    for session in sessions:
        end = next(i for i, x in enumerate(rows) if x["event"] == "session_destroyed" and x["session"] == session["session"])
        assert all(i < end for i, x in enumerate(rows) if x["event"] == "buffer_released" and x["session"] == session["session"])
    delay = None
    if pending:
        # A failed generated function publishes no output Buffer. Both paths
        # still need an actual post-drain acknowledgement and driver status4/1.
        assert kernels == 1 and len(created) == 3 - errors and queued[0]["controlled_shared_event"] and queued[0]["completion_pending"] and queued[0]["execution_status"] in (2, 3)
        assert len(completed) == 1
        delay = (completed[0]["steady_ns"] - queued[0]["steady_ns"]) / 1e9
        assert delay >= 0.5
        assert all(x["steady_ns"] >= completed[0]["steady_ns"] for x in rows if x["event"] in ["buffer_released", "session_destroyed"])
        if cancelled:
            busy = [x for x in rows if x["event"] == "kernel_busy_observed"]
            assert busy and queued[0]["steady_ns"] <= busy[0]["steady_ns"] < completed[0]["steady_ns"]
    return {"devices": sorted({x["device"] for x in sessions}), "sessions": len(sessions), "buffers": len(created), "closed_cursors": len(cursors),
            "physical_GPU_events": physical, "GPU_error_codes": [x["code"] for x in failed],
            "all_buffers_released": True, "physical_settlement_before_parent_release": True, "pending_seconds": delay}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["sdk", "project", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--only", action="append", choices=[*CASES, *ERROR_CASES])
    args = parser.parse_args()
    sdk, project = args.sdk.resolve(strict=True), args.project.resolve(strict=True)
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    compiler = sdk / "bin/nex"
    prefix = (project / "main.nex").read_text().split("server fn main()->unit")[0] + HELPERS
    env = {**os.environ, "NEX_RESOURCE_DIR": str(sdk / "share/nex"), "PYTHONDONTWRITEBYTECODE": "1", "NEX_OWNED_METAL_MAP_TEST_NOISE": "1"}
    for name in ["NEX_OWNED_METAL_MAP_TEST_BAD_REPLY", "NEX_OWNED_METAL_MAP_TEST_GATE_MS"]:
        env.pop(name, None)
    report = {"schema": "nex.owned-generated-Metal-lifetimes/1", "ok": False, "commands": [], "cases": [], "compiler_sha256": sha(compiler),
              "worker_sha256": sha(project / "bundle/worker"), "module_sha256": sha(project / "bundle/module.so"), "manifest_sha256": sha(project / "bundle/manifest.json"),
              "direct_fatal_trap_forwarding_integrated": True, "installed_SDK_accepted": False, "whole_original_goal_complete": False}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, argv, cwd, expected=0, extra=None):
        p = subprocess.run(list(map(str, argv)), cwd=cwd, env={**env, **(extra or {})}, capture_output=True, text=True, timeout=300)
        (out / (label + ".stdout")).write_text(p.stdout)
        (out / (label + ".stderr")).write_text(p.stderr)
        report["commands"].append({"label": label, "argv": list(map(str, argv)), "exit_code": p.returncode})
        save()
        assert p.returncode == expected, (label, p.returncode, p.stdout[-2500:], p.stderr[-2000:])
        return p

    def check_case(name, body, kernels, errors, quota=None, code=None, gate=0, timeout=30000):
        directory = out / name
        directory.mkdir()
        (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex", "libraries": {"std": str(project / "stdlib")}}) + "\n")
        (directory / "main.nex").write_text(prefix + "\nserver fn main()->unit !{task,ffi,io,throw}{" + body + "print(42);}\n")
        catalogue = json.loads((project / "foreign.json").read_bytes())
        catalogue["libraries"]["gpu"]["directory"] = str(project / "bundle")
        if quota is not None:
            catalogue["resource_limit"] = quota
        foreign = directory / "foreign.json"
        foreign.write_text(json.dumps(catalogue, indent=2) + "\n")
        extra = {"NEX_OWNED_METAL_MAP_TEST_GATE_MS": str(gate)} if gate else {}
        reference_trace = directory / "reference.trace.jsonl"
        reference = json.loads(run(name + "-reference", [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout), "--json"], directory, 1 if code else 0,
                                   {**extra, "NEX_OWNED_METAL_MAP_TRACE": str(reference_trace)}).stdout)
        if code:
            assert reference["code"] == code and reference["stdout"] == ""
            if code == "E_RESULT":
                assert "E_OVERFLOW" in reference["message"]
        else:
            assert reference["stdout"] == "42\n" and reference["foreign_resource_bytes_after_scope"] == 0
        built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout), "--json"], directory).stdout)
        native_trace = directory / "native.trace.jsonl"
        native = run(name + "-native", [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1", "--nex-task-timeout-ms", str(timeout)], directory, 70 if code else 0,
                     {**extra, "NEX_OWNED_METAL_MAP_TRACE": str(native_trace)})
        if code:
            assert code in native.stderr and native.stdout == ""
            if code == "E_RESULT":
                assert "E_OVERFLOW" in native.stderr
        else:
            assert native.stdout == "42\n" and native.stderr == ""
        ref = inspect_trace(reference_trace, kernels, errors, bool(gate), code == "E_CANCELLED")
        nat = inspect_trace(native_trace, kernels, errors, bool(gate), code == "E_CANCELLED")
        assert ref["devices"] == nat["devices"] and ref["sessions"] == nat["sessions"] and ref["buffers"] == nat["buffers"]
        report["cases"].append({"name": name, "native_reference": True, "expected_error": code, "reference": ref, "native": nat})
        save()

    try:
        for name, (body, kernels, errors, quota) in CASES.items():
            if not args.only or name in args.only:
                check_case(name, body, kernels, errors, quota)
        for name, (body, code, gate, timeout, errors) in ERROR_CASES.items():
            if not args.only or name in args.only:
                check_case(name, body, 1, errors, code=code, gate=gate, timeout=timeout)
        assert sha(compiler) == report["compiler_sha256"]
        report.update(ok=True, state="passed", native_reference_pairs=len(report["cases"]), full_suite=not args.only,
                      physical_GPU_kernel_events=sum(len(case[mode]["physical_GPU_events"]) for case in report["cases"] for mode in ["reference", "native"]))
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "native_reference_pairs", "physical_GPU_kernel_events", "full_suite"]}))


if __name__ == "__main__":
    main()
