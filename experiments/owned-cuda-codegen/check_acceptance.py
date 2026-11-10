"""Check the future CUDA corpus and its receipt reader without a CUDA device."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
import platform
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "emitter", "frontend-archive", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--host-gate-config-controls", action="store_true")
    parser.add_argument("--cxx", type=Path)
    args = parser.parse_args()
    if args.host_gate_config_controls and (platform.system() != "Darwin" or not args.cxx):
        parser.error("host gate configuration controls currently require macOS and explicit --cxx")
    compiler, resources, emitter, frontend = [p.resolve(strict=True) for p in
        [args.compiler, args.resources, args.emitter, args.frontend_archive]]
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("generated_CUDA_verifier", source / "verify.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    env = {k: v for k, v in os.environ.items() if not k.startswith("NEX_")}
    env.update(NEX_RESOURCE_DIR=str(resources), PYTHONDONTWRITEBYTECODE="1")
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    report = {"schema": "nex.experimental-owned-CUDA-acceptance-source-controls/1", "ok": False,
              "compiler_sha256": sha(compiler), "commands": [], "receipt_contracts": [], "actual_GPU_execution": False}

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def run(label, argv, expected=0, extra=None):
        row = {"label": label, "argv": list(map(str, argv))}
        report["commands"].append(row)
        save()
        value = subprocess.run(row["argv"], cwd=out, env={**env, **(extra or {})}, capture_output=True, timeout=600)
        (out / (label + ".stdout")).write_bytes(value.stdout)
        (out / (label + ".stderr")).write_bytes(value.stderr)
        row["exit_code"] = value.returncode
        assert value.returncode == expected, (label, value.stderr[-2000:])
        return value

    try:
        fixture = out / "fixture"
        fixture.mkdir()
        assert sha(source / "fixture.nex") == verifier.FIXTURE_SHA256
        (fixture / "main.nex").write_bytes((source / "fixture.nex").read_bytes())
        (fixture / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"}) + "\n")
        project = out / "prepared"
        run("prepare", [sys.executable, "-B", source / "prepare.py", "--compiler", compiler, "--resources", resources,
            "--emitter", emitter, "--frontend-archive", frontend, "--source-project", fixture, "--symbol", "transform", "--source-only", "--acceptance-gate", "--output", project])
        prep = json.loads((project / "preparation/report.json").read_bytes())
        assert prep["root_hash"] == verifier.ROOT_HASH and not prep["native_provider_built"] and not prep["driver_initialized"]
        run("check-corpus", [sys.executable, "-B", source / "verify.py", "--compiler", compiler, "--resources", resources,
            "--project", project, "--check-only", "--output", out / "corpus"])
        corpus = json.loads((out / "corpus/report.json").read_bytes())
        assert corpus["ok"] and corpus["check_only"] and corpus["source_cases_checked"] == 15
        assert not corpus["actual_GPU_execution"] and corpus["physical_GPU_kernel_events"] == 0 and not corpus["complete_owned_CUDA_acceptance"]
        report["checked_NEX_cases"] = 15
        if args.host_gate_config_controls:
            inputs = project / "preparation/inputs"
            apple_sdk = run("gate-host-sdk", ["/usr/bin/xcrun", "--sdk", "macosx", "--show-sdk-path"]).stdout.decode().strip()
            probe = out / "gate-config-probe"
            run("gate-config-probe-build", [args.cxx, "-isysroot", apple_sdk, "-std=c++20", "-O1", "-pthread", "-Wall", "-Wextra", "-Werror",
                "-I" + str(resources / "runtime"), "-I" + str(inputs), inputs / "context_probe.cpp", "-o", probe])
            configurations = [("off", None, None, 0), ("minimum", "1", "1", 0), ("maximum", "200000000", "32", 0),
                ("missing-repeats", "1", None, 1), ("missing-cycles", None, "1", 1), ("cycles-over-limit", "200000001", "32", 1),
                ("repeats-over-limit", "1", "33", 1), ("negative", "-1", "1", 1), ("leading-space", " 1", "1", 1),
                ("trailing-data", "1x", "1", 1), ("uint64-overflow", "18446744073709551616", "1", 1)]
            for name, cycles, repeats, expected in configurations:
                settings = {}
                if cycles is not None:
                    settings["NEX_OWNED_CUDA_MAP_GATE_CYCLES"] = cycles
                if repeats is not None:
                    settings["NEX_OWNED_CUDA_MAP_GATE_REPEATS"] = repeats
                value = run("gate-config-" + name, [probe, "--check-gate-config"], expected, settings)
                if expected:
                    assert b"E_DEVICE_CONFIG" in value.stderr and value.stdout == b""
                else:
                    control = json.loads(value.stdout)
                    assert control["scope"] == "gate-config-host-control" and control["compiled"] and control["actual_CUDA_contexts"] == 0
                    assert control["cycles"] == int(cycles or 0) and control["repeats"] == int(repeats or 0)
            report["actual_CPP_gate_configuration_controls"] = len(configurations)
        # Synthetic records test the receipt reader's rejection behavior only.
        # They are never written as a hardware receipt or passed to NEX execution.
        ledger = {"allocations": 4, "frees": 4, "events": 2, "event_frees": 2, "contexts": 1, "context_frees": 1,
                  "modules": 1, "module_frees": 1, "streams": 1, "stream_frees": 1, "live_bytes": 0, "cleanup_errors": 0, "kernel_launches": 1, "acceptance_gate_launches": 0}
        shader, ptx, gate = "a" * 64, "b" * 64, "e" * 64
        valid = [
            {"event": "session_created", "session": 1, "name": "NVIDIA synthetic contract record", "uuid": "c" * 32,
             "pci_bus_id": "00000000:01:00.0", "driver_version": 12010, "ordinal": 0, "cpu_fallback": False},
            {"event": "status_storage_allocated", "session": 1, "bytes": 131072},
            {"event": "generated_session_ready", "session": 1, "kernel_sha256": shader, "PTX_sha256": ptx, "gate_source_sha256": gate, "acceptance_gate_compiled": True, "arguments": 2, "cpu_fallback": False},
            *[{"event": "buffer_allocated", "session": 1, "buffer": identity, "bytes": 8} for identity in [10, 11, 12]],
            {"event": "kernel_queued", "session": 1, "dispatch": 1, "input_buffers": [10, 11], "output_buffer": 12, "columns": 2, "physical_enqueue_verified": True, "gate_launches": 0, "gate_cycles": 0},
            {"event": "kernel_completed", "session": 1, "dispatch": 1, "output_buffer": 12, "kernel_sha256": shader, "physical_completion_verified": True, "cpu_fallback": False, "lane_status": 0},
            *[{"event": "buffer_released", "session": 1, "buffer": identity, "bytes": 8, "physical_completion_verified": True} for identity in [10, 11, 12]],
            {"event": "status_storage_released", "session": 1, "bytes": 131072, "physical_completion_verified": True},
            {"event": "session_destroyed", "session": 1, "physical_completion_verified": True},
            {"event": "module_unloaded", "physical_completion_verified": True, "ledger": ledger},
        ]
        def find(rows, event, buffer=None):
            return next(i for i, row in enumerate(rows) if row["event"] == event and (buffer is None or row.get("buffer") == buffer))

        contracts = [("synthetic-contract-consistency", valid, True)]
        rows = copy.deepcopy(valid)
        rows[-1]["ledger"].update(live_bytes=8, frees=3)
        contracts.append(("clean-exit-with-device-buffer-leak", rows, False))
        rows = copy.deepcopy(valid)
        rows.pop(find(rows, "kernel_completed"))
        contracts.append(("successful-process-without-kernel-completion", rows, False))
        rows = copy.deepcopy(valid)
        rows[-1]["ledger"]["context_frees"] = 0
        contracts.append(("balanced-buffers-but-leaked-context", rows, False))
        rows = copy.deepcopy(valid)
        rows[-1]["ledger"].update(event_frees=1, stream_frees=0)
        contracts.append(("pending-events-and-stream-at-unload", rows, False))
        rows = copy.deepcopy(valid)
        rows.insert(-1, {"event": "unsettled"})
        contracts.append(("unsettled-state-followed-by-success-claim", rows, False))
        rows = copy.deepcopy(valid)
        rows.insert(find(rows, "buffer_released", 12), {"event": "read_cursor_created", "session": 1, "buffer": 12, "cursor": 7})
        contracts.append(("unreleased-cursor-with-balanced-GPU-counters", rows, False))
        rows = copy.deepcopy(valid)
        rows[find(rows, "kernel_completed")]["cpu_fallback"] = True
        contracts.append(("CUDA-identity-with-CPU-fallback", rows, False))
        rows = copy.deepcopy(valid)
        rows[find(rows, "generated_session_ready")]["PTX_sha256"] = "d" * 64
        contracts.append(("different-compiled-PTX", rows, False))
        for buffer, name in [(10, "input-freed-before-dispatch-settlement"), (12, "unpublished-output-freed-before-settlement")]:
            rows = copy.deepcopy(valid)
            release = rows.pop(find(rows, "buffer_released", buffer))
            rows.insert(find(rows, "kernel_completed"), release)
            contracts.append((name, rows, False))
        rows = copy.deepcopy(valid)
        close = rows.pop(find(rows, "session_destroyed"))
        rows.insert(find(rows, "buffer_released", 12), close)
        contracts.append(("parent-session-destroyed-before-last-buffer", rows, False))
        rows = copy.deepcopy(valid)
        rows.insert(find(rows, "buffer_released", 12), {"event": "read_cursor_created", "session": 1, "buffer": 12, "cursor": 7})
        rows.insert(find(rows, "status_storage_released"), {"event": "read_cursor_released", "session": 1, "buffer": 12, "cursor": 7})
        contracts.append(("buffer-freed-while-retained-cursor-exists", rows, False))
        pending = copy.deepcopy(valid)
        pending[find(pending, "kernel_queued")].update(gate_launches=32, gate_cycles=200000000, completion_pending=True, event_status=600)
        pending[find(pending, "kernel_completed")] = {"event": "physical_drain", "session": 1, "dispatch": 1, "output_buffer": 12,
            "kernel_sha256": shader, "cpu_fallback": False, "physical_completion_verified": True, "event_status": 0, "unwind": True, "gate_launches": 32}
        pending[-1]["ledger"]["acceptance_gate_launches"] = 32
        pending.insert(find(pending, "physical_drain"), {"event": "kernel_busy_observed", "session": 1})
        pending.insert(find(pending, "buffer_released"), {"event": "host_trap", "session": 1, "status": 10})
        contracts.append(("pending-valid-drain-contract", pending, True))
        rows = copy.deepcopy(pending)
        rows[find(rows, "kernel_queued")]["gate_launches"] = rows[-1]["ledger"]["acceptance_gate_launches"] = 0
        contracts.append(("pending-CPU-delay-with-no-GPU-gates", rows, False))
        rows = copy.deepcopy(pending)
        rows[find(rows, "physical_drain")].update(event="kernel_completed", lane_status=0)
        contracts.append(("pending-no-unwind-drain", rows, False))
        rows = copy.deepcopy(pending)
        release = rows.pop(find(rows, "buffer_released", 12))
        rows.insert(find(rows, "physical_drain"), release)
        contracts.append(("pending-output-freed-before-drain", rows, False))
        rows = copy.deepcopy(pending)
        rows.pop(find(rows, "kernel_busy_observed"))
        contracts.append(("pending-no-post-enqueue-busy-observation", rows, False))
        rows = copy.deepcopy(pending)
        rows.pop(find(rows, "host_trap"))
        contracts.append(("pending-no-host-interruption", rows, False))
        rows = copy.deepcopy(pending)
        rows[find(rows, "physical_drain")]["dispatch"] = 2
        contracts.append(("pending-acknowledgement-for-different-dispatch", rows, False))
        contracts.append(("pending-insufficient-physical-interval", copy.deepcopy(pending), False))
        for name, rows, accepted in contracts:
            trace = out / (name + ".synthetic.jsonl")
            for index, row in enumerate(rows):
                row.update(schema="nex.experimental-owned-CUDA-trace/2", steady_ns=index * 1000000000)
            if name == "pending-insufficient-physical-interval":
                rows[find(rows, "physical_drain")]["steady_ns"] = rows[find(rows, "kernel_queued")]["steady_ns"] + 1
            trace.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            try:
                verifier.inspect_trace(trace, 1, 0, shader, ptx, gate, name.startswith("pending-"), name.startswith("pending-"))
                actual = True
            except AssertionError:
                actual = False
            assert actual == accepted, name
            report["receipt_contracts"].append({"name": name, "synthetic_only": True, "accepted": actual})
        report.update(ok=True, synthetic_contracts=len(contracts), rejected_false_receipts=sum(not accepted for _, _, accepted in contracts),
                      preparation_report_sha256=sha(project / "preparation/report.json"), corpus_report_sha256=sha(out / "corpus/report.json"))
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "checked_NEX_cases", "synthetic_contracts", "rejected_false_receipts", "actual_GPU_execution"]}))


if __name__ == "__main__":
    main()
