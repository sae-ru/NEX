"""Check the future CUDA corpus and its receipt reader without a CUDA device."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "emitter", "frontend-archive", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
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

    def run(label, argv):
        row = {"label": label, "argv": list(map(str, argv))}
        report["commands"].append(row)
        save()
        value = subprocess.run(row["argv"], cwd=out, env=env, capture_output=True, timeout=600)
        (out / (label + ".stdout")).write_bytes(value.stdout)
        (out / (label + ".stderr")).write_bytes(value.stderr)
        row["exit_code"] = value.returncode
        assert value.returncode == 0, (label, value.stderr[-2000:])

    try:
        fixture = out / "fixture"
        fixture.mkdir()
        assert sha(source / "fixture.nex") == verifier.FIXTURE_SHA256
        (fixture / "main.nex").write_bytes((source / "fixture.nex").read_bytes())
        (fixture / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": "0.28", "entry": "main.nex"}) + "\n")
        project = out / "prepared"
        run("prepare", [sys.executable, "-B", source / "prepare.py", "--compiler", compiler, "--resources", resources,
            "--emitter", emitter, "--frontend-archive", frontend, "--source-project", fixture, "--symbol", "transform", "--source-only", "--output", project])
        prep = json.loads((project / "preparation/report.json").read_bytes())
        assert prep["root_hash"] == verifier.ROOT_HASH and not prep["native_provider_built"] and not prep["driver_initialized"]
        run("check-corpus", [sys.executable, "-B", source / "verify.py", "--compiler", compiler, "--resources", resources,
            "--project", project, "--check-only", "--output", out / "corpus"])
        corpus = json.loads((out / "corpus/report.json").read_bytes())
        assert corpus["ok"] and corpus["check_only"] and corpus["source_cases_checked"] == 13
        assert not corpus["actual_GPU_execution"] and corpus["physical_GPU_kernel_events"] == 0 and not corpus["complete_owned_CUDA_acceptance"]
        report["checked_NEX_cases"] = 13
        # Synthetic records test the receipt reader's rejection behavior only.
        # They are never written as a hardware receipt or passed to NEX execution.
        ledger = {"allocations": 4, "frees": 4, "events": 2, "event_frees": 2, "contexts": 1, "context_frees": 1,
                  "modules": 1, "module_frees": 1, "streams": 1, "stream_frees": 1, "live_bytes": 0, "cleanup_errors": 0, "kernel_launches": 1}
        shader, ptx = "a" * 64, "b" * 64
        valid = [
            {"event": "session_created", "session": 1, "name": "NVIDIA synthetic contract record", "uuid": "c" * 32,
             "pci_bus_id": "00000000:01:00.0", "driver_version": 12010, "ordinal": 0, "cpu_fallback": False},
            {"event": "generated_session_ready", "session": 1, "kernel_sha256": shader, "PTX_sha256": ptx, "arguments": 2, "cpu_fallback": False},
            {"event": "kernel_queued", "columns": 2, "physical_enqueue_verified": True},
            {"event": "kernel_completed", "kernel_sha256": shader, "physical_completion_verified": True, "cpu_fallback": False, "lane_status": 0},
            {"event": "buffer_released", "physical_completion_verified": True},
            {"event": "session_destroyed", "session": 1, "physical_completion_verified": True},
            {"event": "module_unloaded", "physical_completion_verified": True, "ledger": ledger},
        ]
        contracts = [("synthetic-contract-consistency", valid, True)]
        rows = copy.deepcopy(valid)
        rows[-1]["ledger"].update(live_bytes=8, frees=3)
        contracts.append(("clean-exit-with-device-buffer-leak", rows, False))
        rows = copy.deepcopy(valid)
        rows.pop(3)
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
        rows.insert(2, {"event": "read_cursor_created", "cursor": 7})
        contracts.append(("unreleased-cursor-with-balanced-GPU-counters", rows, False))
        rows = copy.deepcopy(valid)
        rows[3]["cpu_fallback"] = True
        contracts.append(("CUDA-identity-with-CPU-fallback", rows, False))
        rows = copy.deepcopy(valid)
        rows[1]["PTX_sha256"] = "d" * 64
        contracts.append(("different-compiled-PTX", rows, False))
        for name, rows, accepted in contracts:
            trace = out / (name + ".synthetic.jsonl")
            trace.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
            try:
                verifier.inspect_trace(trace, 1, 0, shader, ptx)
                actual = True
            except AssertionError:
                actual = False
            assert actual == accepted, name
            report["receipt_contracts"].append({"name": name, "synthetic_only": True, "accepted": actual})
        report.update(ok=True, synthetic_contracts=len(contracts), rejected_false_receipts=8,
                      preparation_report_sha256=sha(project / "preparation/report.json"), corpus_report_sha256=sha(out / "corpus/report.json"))
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "checked_NEX_cases", "synthetic_contracts", "rejected_false_receipts", "actual_GPU_execution"]}))


if __name__ == "__main__":
    main()
