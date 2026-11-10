"""Check the generated CUDA scalar/parent corpus; physical mode requires CUDA."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import runpy
import subprocess
import time

ROOT_HASH = "b5c98cd904bba48ddcc03131b93e311e62c75553d084a130aa37d8c903c9bdc7"
FIXTURE_SHA256 = "f65ab8e26679ccae5dfa9619aed08351468f9e6e1e3d0e7cd1b9250dd08d3eec"
PAIRS = [("allocations", "frees"), ("events", "event_frees"),
         ("contexts", "context_frees"), ("modules", "module_frees"), ("streams", "stream_frees")]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inspect_trace(path, kernels, errors, shader_hash, ptx_hash, gate_hash="", pending=False, cancelled=False):
    assert path.stat().st_size <= 16 * 1024 * 1024
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert all(row["schema"] == "nex.experimental-owned-CUDA-trace/2" and type(row["steady_ns"]) is int and row["steady_ns"] >= 0 for row in rows)
    assert rows and rows[-1]["event"] == "module_unloaded" and rows[-1]["physical_completion_verified"]
    assert not any(row["event"] == "unsettled" for row in rows)
    ledger = rows[-1]["ledger"]
    assert ledger["live_bytes"] == 0 and ledger["cleanup_errors"] == 0
    for allocated, freed in PAIRS:
        assert type(ledger[allocated]) is int and ledger[allocated] >= 0 and ledger[allocated] == ledger[freed]
    sessions = [row for row in rows if row["event"] == "session_created"]
    destroyed = [row for row in rows if row["event"] == "session_destroyed"]
    assert sessions and len({row["session"] for row in sessions}) == len(sessions)
    assert len(destroyed) == len(sessions) and {row["session"] for row in sessions} == {row["session"] for row in destroyed}
    for row in sessions:
        assert row["session"] > 0 and row["cpu_fallback"] is False and "NVIDIA" in row["name"]
        assert len(row["uuid"]) == 32 and all(c in "0123456789abcdef" for c in row["uuid"])
        assert row["pci_bus_id"] and row["driver_version"] > 0 and 0 <= row["ordinal"] < 64
    ready = [row for row in rows if row["event"] == "generated_session_ready"]
    assert {row["session"] for row in ready} == {row["session"] for row in sessions}
    assert len(ready) == len(sessions) and all(row["kernel_sha256"] == shader_hash and row["PTX_sha256"] == ptx_hash and row["arguments"] == 2 and row["cpu_fallback"] is False for row in ready)
    assert all(row["gate_source_sha256"] == gate_hash and row["acceptance_gate_compiled"] == bool(gate_hash) for row in ready)
    queued = [row for row in rows if row["event"] == "kernel_queued"]
    complete = [row for row in rows if row["event"] in ["kernel_completed", "kernel_failure_settled", "physical_drain"]]
    failed = [row for row in complete if row["event"] == "kernel_failure_settled"]
    assert len(queued) == len(complete) == ledger["kernel_launches"] == kernels and len(failed) == errors
    assert all(row["physical_enqueue_verified"] and row["columns"] == 2 for row in queued)
    assert all(row["kernel_sha256"] == shader_hash and row["physical_completion_verified"] and row["cpu_fallback"] is False for row in complete)
    assert all(1 <= row["lane_status"] <= 6 for row in failed)
    assert all(row["lane_status"] == 0 for row in complete if row["event"] == "kernel_completed")
    drains = [row for row in complete if row["event"] == "physical_drain"]
    if pending:
        assert kernels == 1 and errors == 0 and len(drains) == 1 and len(queued) == 1
        assert queued[0]["completion_pending"] and queued[0]["event_status"] == 600
        assert queued[0]["gate_launches"] == drains[0]["gate_launches"] == ledger["acceptance_gate_launches"] == 32
        assert queued[0]["gate_cycles"] == 200000000 and drains[0]["event_status"] == 0 and drains[0]["unwind"]
        assert drains[0]["steady_ns"] - queued[0]["steady_ns"] >= 500000000
        assert any(row["event"] == "host_trap" and row["status"] == 10 for row in rows)
        if cancelled:
            assert any(row["event"] == "kernel_busy_observed" and row["session"] == queued[0]["session"] and queued[0]["steady_ns"] <= row["steady_ns"] <= drains[0]["steady_ns"] for row in rows)
    else:
        assert not drains and ledger["acceptance_gate_launches"] == 0 and all(row["gate_launches"] == 0 for row in queued)
    for row in rows:
        if row["event"] in ["buffer_released", "session_destroyed", "physical_drain"]:
            assert row["physical_completion_verified"]
    created = [row["cursor"] for row in rows if row["event"] == "read_cursor_created"]
    closed = [row["cursor"] for row in rows if row["event"] == "read_cursor_released"]
    assert len(created) == len(set(created)) and sorted(created) == sorted(closed)

    def indexed(event, key):
        selected = [row for row in rows if row["event"] == event]
        keys = [key(row) for row in selected]
        assert len(keys) == len(set(keys)), event
        return dict(zip(keys, selected))

    session_created = {row["session"]: row for row in sessions}
    session_closed = {row["session"]: row for row in destroyed}
    allocated = indexed("buffer_allocated", lambda row: row["buffer"])
    released = indexed("buffer_released", lambda row: row["buffer"])
    scratch = indexed("status_storage_allocated", lambda row: row["session"])
    scratch_closed = indexed("status_storage_released", lambda row: row["session"])
    assert set(allocated) == set(released) and set(scratch) == set(scratch_closed) == set(session_created)
    assert ledger["allocations"] == len(allocated) + len(scratch)
    for identity, row in allocated.items():
        end = released[identity]
        assert type(identity) is int and identity > 0 and row["bytes"] > 0
        assert row["session"] == end["session"] and row["bytes"] == end["bytes"]
        assert session_created[row["session"]]["steady_ns"] <= row["steady_ns"] <= end["steady_ns"] <= session_closed[row["session"]]["steady_ns"]
    for identity, row in scratch.items():
        end = scratch_closed[identity]
        assert row["bytes"] == end["bytes"] == 32768 * 4 and end["physical_completion_verified"]
        assert session_created[identity]["steady_ns"] <= row["steady_ns"] <= end["steady_ns"] <= session_closed[identity]["steady_ns"]
    launches = indexed("kernel_queued", lambda row: (row["session"], row["dispatch"]))
    settlements = {(row["session"], row["dispatch"]): row for row in complete}
    assert len(settlements) == len(complete) and set(launches) == set(settlements)
    for identity, row in launches.items():
        end = settlements[identity]
        assert type(row["dispatch"]) is int and row["dispatch"] > 0
        assert row["output_buffer"] == end["output_buffer"] and len(row["input_buffers"]) == 2
        assert row["output_buffer"] not in row["input_buffers"] and row["steady_ns"] <= end["steady_ns"]
        assert scratch[row["session"]]["steady_ns"] <= row["steady_ns"] <= end["steady_ns"] <= scratch_closed[row["session"]]["steady_ns"]
        for buffer in [*row["input_buffers"], row["output_buffer"]]:
            assert allocated[buffer]["session"] == row["session"]
            assert allocated[buffer]["steady_ns"] <= row["steady_ns"] <= end["steady_ns"] <= released[buffer]["steady_ns"]
    cursor_created = indexed("read_cursor_created", lambda row: row["cursor"])
    cursor_closed = indexed("read_cursor_released", lambda row: row["cursor"])
    for identity, row in cursor_created.items():
        end = cursor_closed[identity]
        assert row["session"] == end["session"] == allocated[row["buffer"]]["session"]
        assert row["buffer"] == end["buffer"]
        assert allocated[row["buffer"]]["steady_ns"] <= row["steady_ns"] <= end["steady_ns"] <= released[row["buffer"]]["steady_ns"]
    return {"trace_sha256": sha(path), "sessions": [{key: row[key] for key in ["name", "uuid", "pci_bus_id", "ordinal", "driver_version"]} for row in sessions],
            "ledger": ledger, "physical_kernel_completions": len(complete), "failed_kernel_completions": len(failed), "closed_cursors": len(closed),
            "acceptance_gate_GPU_launches": ledger["acceptance_gate_launches"], "post_enqueue_interruption_checked": pending,
            "all_resource_counter_pairs_balanced": True, "per_buffer_dispatch_and_cursor_lifetimes_checked": True, "context_probe_qualified_by_this_reader": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "project", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--check-only", action="store_true", help="Check every NEX case without loading any provider or executing CUDA")
    args = parser.parse_args()
    if not args.check_only and platform.system() not in {"Windows", "Linux"}:
        parser.error("physical CUDA verification requires Windows/Linux; use --check-only for source validation")
    compiler, resources, project = [p.resolve(strict=True) for p in [args.compiler, args.resources, args.project]]
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent
    assert sha(source / "fixture.nex") == FIXTURE_SHA256
    corpus_path = source.parent / "owned-metal-codegen/verify.py"
    shared = runpy.run_path(str(corpus_path))
    cases = {name: (body, kernels, errors, quota, None, 30000, False) for name, (body, kernels, errors, quota) in shared["CASES"].items()}
    for name in ["explicit_unwrap_E_RESULT_skips_finally", "direct_overflow_skips_catch_and_finally"]:
        body, code, gate, timeout, errors = shared["ERROR_CASES"][name]
        assert gate == 0 and timeout == 30000
        cases[name] = body, 1, errors, None, code, timeout, False
    for name in ["cancel_enqueued_generated_GPU", "deadline_enqueued_generated_GPU"]:
        body, code, _, timeout, errors = shared["ERROR_CASES"][name]
        assert errors == 0 and timeout == (5000 if code == "E_CANCELLED" else 2000)
        cases[name] = body, 1, 0, None, code, timeout, True
    assert len(cases) == 15
    prep_path = project / "preparation/report.json"
    preparation = json.loads(prep_path.read_bytes())
    assert preparation["ok"] and preparation["compiler_sha256"] == sha(compiler)
    assert preparation["root"] == "baseline::transform" and preparation["root_hash"] == ROOT_HASH
    assert preparation["parameter_types"] == ["i64", "i64"] and preparation["result_type"] == "i64"
    assert preparation["emission_sha256"] == sha(project / "generation/report.json")
    assert preparation["kernel_sha256"] == sha(project / "generation/kernel.cu")
    if not args.check_only:
        assert preparation["native_provider_built"] and preparation["NVRTC"]["version"][0] >= 12
        assert preparation["NVRTC"]["PTX_sha256"] == sha(project / "generation/kernel.ptx")
    assert preparation["acceptance_gate"]["compiled"], "prepare the fixture with --acceptance-gate for this corpus"
    prefix = (project / "main.nex").read_text(encoding="utf-8").split("server fn main()->unit", 1)[0] + shared["HELPERS"]
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEX_")}
    env.update(NEX_RESOURCE_DIR=str(resources), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    report = {"schema": "nex.experimental-owned-CUDA-scalar-parent-verification/1", "ok": False, "commands": [], "cases": [],
              "compiler_sha256": sha(compiler), "preparation_sha256": sha(prep_path), "shared_corpus_sha256": sha(corpus_path),
              "check_only": args.check_only, "actual_GPU_execution": False, "complete_owned_CUDA_acceptance": False,
              "required_additional_gates": ["actual post-enqueue cancellation/deadline", "physical context restoration/rollback probe required by hardware mode",
                                            "source-deleted replay/standalone", "Compute Sanitizer", "remaining generated scalar roots and public SDK delivery"]}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def guard():
        assert sha(compiler) == report["compiler_sha256"] and sha(prep_path) == report["preparation_sha256"] and sha(corpus_path) == report["shared_corpus_sha256"]
        assert preparation["emission_sha256"] == sha(project / "generation/report.json") and preparation["kernel_sha256"] == sha(project / "generation/kernel.cu")
        assert preparation["acceptance_gate"]["source_sha256"] == sha(project / "preparation/inputs/gate.cu")
        assert preparation["acceptance_gate"]["compilation_source_sha256"] == sha(project / "generation/compilation.cu")
        if not args.check_only:
            assert preparation["manifest_sha256"] == sha(project / "bundle/manifest.json")
            manifest = json.loads((project / "bundle/manifest.json").read_bytes())
            assert all(sha(project / "bundle" / row["path"]) == row["sha256"] for row in manifest["files"])

    def run(label, argv, directory, expected=0, trace=None, pending=False):
        guard()
        row = {"label": label, "argv": list(map(str, argv)), "cwd": str(directory)}
        report["commands"].append(row)
        save()
        extra = {"NEX_OWNED_CUDA_MAP_TRACE": str(trace)} if trace else {}
        if pending:
            extra.update(NEX_OWNED_CUDA_MAP_GATE_CYCLES="200000000", NEX_OWNED_CUDA_MAP_GATE_REPEATS="32")
        value = subprocess.run(row["argv"], cwd=directory, env={**env, **extra}, capture_output=True, timeout=300)
        (out / (label + ".stdout")).write_bytes(value.stdout)
        (out / (label + ".stderr")).write_bytes(value.stderr)
        row["exit_code"] = value.returncode
        save()
        assert value.returncode == expected, (label, value.returncode, value.stderr[-2000:])
        guard()
        return value

    try:
        if not args.check_only:
            probe = project / "preparation" / ("context-probe.exe" if os.name == "nt" else "context-probe")
            assert sha(probe) == preparation["context_probe_sha256"]
            control = json.loads(run("physical-context-probe", [probe], out, trace=out / "context-probe.trace.jsonl").stdout)
            assert control["ok"] and control["scope"] == "physical-CUDA-context-probe" and control["actual_CUDA_contexts"] == 3
            assert control["actual_device_allocations"] == 1 and all(control[key] for key in ["caller_context_preserved", "source_reentry_rejected_before_poll", "nested_cleanup_restores_context", "constructor_trap_rolls_back", "physical_cleanup_verified"])
            report["physical_context_probe"] = control
            report["required_additional_gates"].remove("physical context restoration/rollback probe required by hardware mode")
        for name, (body, kernels, errors, quota, code, timeout, pending) in cases.items():
            directory = out / name
            directory.mkdir()
            (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex", "libraries": {"std": str(project / "stdlib")}}) + "\n", encoding="utf-8")
            (directory / "main.nex").write_text(prefix + "\nserver fn main()->unit !{task,ffi,io,throw}{" + body + "print(42);}\n", encoding="utf-8")
            checked = json.loads(run(name + "-check", [compiler, "check", "--json"], directory).stdout)
            row = {"name": name, "checked_revision": checked["revision"], "expected_kernels_per_backend": kernels, "expected_failed_kernels_per_backend": errors}
            report["cases"].append(row)
            if args.check_only:
                save()
                continue
            catalogue = json.loads((project / "foreign.json").read_bytes())
            catalogue["libraries"]["gpu"]["directory"] = str(project / "bundle")
            if quota is not None:
                catalogue["resource_limit"] = quota
            foreign = directory / "foreign.json"
            foreign.write_text(json.dumps(catalogue, indent=2) + "\n", encoding="utf-8")
            reference_trace = directory / "reference.trace.jsonl"
            reference = json.loads(run(name + "-reference", [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout), "--json"], directory, 1 if code else 0, reference_trace, pending).stdout)
            if code:
                assert reference["code"] == code and reference["stdout"] == ""
                if code == "E_RESULT":
                    assert "E_OVERFLOW" in reference["message"]
            else:
                assert reference["stdout"] == "42\n" and reference["foreign_resource_bytes_after_scope"] == 0
            built = json.loads(run(name + "-build", [compiler, "build", "--profile", "release", "--task-workers", "1", "--task-steps", "16000000", "--task-timeout-ms", str(timeout), "--build-directory", out / "native", "--json"], directory).stdout)
            native_trace = directory / "native.trace.jsonl"
            native = run(name + "-native", [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1", "--nex-task-timeout-ms", str(timeout)], directory, 70 if code else 0, native_trace, pending)
            assert native.stdout == (b"" if code else b"42\n")
            if code:
                assert code.encode() in native.stderr
                if code == "E_RESULT":
                    assert b"E_OVERFLOW" in native.stderr
            else:
                assert native.stderr == b""
            row["reference"] = inspect_trace(reference_trace, kernels, errors, preparation["kernel_sha256"], preparation["NVRTC"]["PTX_sha256"], preparation["acceptance_gate"]["source_sha256"], pending, code == "E_CANCELLED")
            row["native"] = inspect_trace(native_trace, kernels, errors, preparation["kernel_sha256"], preparation["NVRTC"]["PTX_sha256"], preparation["acceptance_gate"]["source_sha256"], pending, code == "E_CANCELLED")
            assert row["reference"]["sessions"] == row["native"]["sessions"]
            save()
        guard()
        report.update(ok=True, state="passed", source_cases_checked=len(cases),
                      actual_GPU_execution=not args.check_only,
                      physical_GPU_kernel_events=0 if args.check_only else sum(row[mode]["physical_kernel_completions"] for row in report["cases"] for mode in ["reference", "native"]))
        if not args.check_only:
            report["required_additional_gates"].remove("actual post-enqueue cancellation/deadline")
            report["acceptance_gate_GPU_launches"] = sum(row[mode]["acceptance_gate_GPU_launches"] for row in report["cases"] for mode in ["reference", "native"])
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "source_cases_checked", "actual_GPU_execution", "physical_GPU_kernel_events", "complete_owned_CUDA_acceptance"]}))


if __name__ == "__main__":
    main()
