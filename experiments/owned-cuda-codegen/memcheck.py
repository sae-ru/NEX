"""Memcheck the exact complete generated-CUDA hardware cohort; never build/eval."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import re
import signal
import subprocess
import time


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_pins(pins):
    require(bool(pins), "missing retained input pins")
    for name, digest in pins.items():
        require(Path(name).is_absolute() and re.fullmatch(r"[0-9a-f]{64}", digest), "malformed retained input pin")
        require(sha(name) == digest, "retained input changed: " + name)


def parse_summary(text):
    text = text.replace("\r\n", "\n")
    require("COMPUTE-SANITIZER" in text, "missing Compute Sanitizer log header")
    errors = re.findall(r"^=+\s+ERROR SUMMARY:\s*(\d+) errors[^\r\n]*$", text, re.M)
    leaks = re.findall(r"^=+\s+LEAK SUMMARY:\s*(\d+) bytes leaked in (\d+) allocations[^\r\n]*$", text, re.M)
    ignored = re.findall(r"\(([^()\r\n]+) (?:ignored|suppressed)\)", text)
    require(errors and leaks and len(errors) == len(leaks)
        and len(errors) == len(re.findall(r"^=+\s+ERROR SUMMARY:", text, re.M))
        and len(leaks) == len(re.findall(r"^=+\s+LEAK SUMMARY:", text, re.M)), "missing, malformed or incomplete error/leak summaries")
    require(all(int(n) == 0 for n in errors) and all(int(n) == 0 for pair in leaks for n in pair) and all(n == "0" for n in ignored),
            "Compute Sanitizer reported errors, leaks or suppressed results")
    return {"error_summaries": len(errors), "leak_summaries": len(leaks), "errors": 0, "leaked_bytes": 0, "leaked_allocations": 0}


def check_native_command(argv, executable, foreign, timeout):
    require(len(argv) == 7 and Path(argv[0]).resolve() == Path(executable).resolve() and argv[1] == "--nex-foreign"
        and Path(argv[2]).resolve() == Path(foreign).resolve() and argv[3:] == ["--nex-task-workers", "1", "--nex-task-timeout-ms", str(timeout)],
            "native command differs from its exact retained executable, authority, workers or original task timeout")


def inspect_context(path):
    require(path.stat().st_size <= 16 * 1024 * 1024, "context trace exceeds its bound")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    require(rows and all(r["schema"] == "nex.experimental-owned-CUDA-trace/2" for r in rows), "context trace schema differs")
    require(rows[-1]["event"] == "module_unloaded" and rows[-1]["physical_completion_verified"] and not any(r["event"] == "unsettled" for r in rows), "context resources did not settle")
    ledger = rows[-1]["ledger"]
    require(ledger["contexts"] == ledger["context_frees"] == 3 and ledger["allocations"] == ledger["frees"] == 1 and ledger["peak_bytes"] == 4, "context probe did not execute its three contexts and allocation")
    require(all(ledger[k] == 0 for k in ["live_bytes", "cleanup_errors", "events", "event_frees", "modules", "module_frees", "streams", "stream_frees", "kernel_launches", "acceptance_gate_launches"]), "unexpected context resources")
    sessions = [r for r in rows if r["event"] == "session_created"]
    require(len(sessions) == 3 and len({r["session"] for r in sessions}) == 3 and all(r["cpu_fallback"] is False and "NVIDIA" in r["name"] for r in sessions), "missing physical context identity")
    require({r["session"] for r in rows if r["event"] == "session_destroyed"} == {r["session"] for r in sessions}, "context destruction differs")
    return {"ledger": ledger, "devices": [dict(zip(["uuid", "pci_bus_id", "driver_version", "ordinal"], identity))
        for identity in sorted({tuple(r[k] for k in ["uuid", "pci_bus_id", "driver_version", "ordinal"]) for r in sessions})]}


def run_bounded(argv, cwd, env, timeout):
    process = subprocess.Popen(list(map(str, argv)), cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name != "nt", creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0)
    timed_out = False
    try:
        out, err = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        if os.name == "nt":
            subprocess.run([str(Path(os.environ["SystemRoot"]) / "System32/taskkill.exe"), "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        out, err = process.communicate(timeout=15)
    return process.returncode, out, err, timed_out


def load_plan(source, verifier):
    base = json.loads(source.read_bytes())
    require(base.get("schema") == "nex.experimental-owned-CUDA-scalar-parent-verification/2" and base.get("ok") is True
        and base.get("check_only") is False and base.get("actual_GPU_execution") is True and not base.get("synthetic_only"),
        "a complete physical generated-CUDA v2 hardware report is required; source-only and synthetic controls are not accepted")
    require(base["verifier_sha256"] == sha(Path(__file__).with_name("verify.py")), "hardware verifier changed")
    require(base["shared_corpus_sha256"] == sha(Path(__file__).parent.parent / "owned-metal-codegen/verify.py"), "shared corpus changed")
    _, specs = verifier.case_specs()
    cases = {row["name"]: row for row in base["cases"]}
    require(len(cases) == len(base["cases"]) == 15 and set(cases) == set(specs), "expected the complete canonical 15-case corpus")
    pins = dict(base["retained_input_sha256"])
    check_pins(pins)
    project = Path(base["project"]).resolve(strict=True)
    prep_path = project / "preparation/report.json"
    prep = json.loads(prep_path.read_bytes())
    require(sha(prep_path) == base["preparation_sha256"] and prep["ok"] and prep["native_provider_built"] and prep["compiler_sha256"] == base["compiler_sha256"], "native preparation changed")
    require(prep["root_hash"] == verifier.ROOT_HASH and prep["NVRTC"]["version"][0] >= 12 and prep["acceptance_gate"]["compiled"], "wrong root, NVRTC or acceptance gate")
    require(sha(project / "generation/kernel.cu") == prep["kernel_sha256"] == base["kernel_sha256"] and sha(project / "generation/kernel.ptx") == prep["NVRTC"]["PTX_sha256"] == base["PTX_sha256"], "generated source/PTX changed")
    manifest_path = project / "bundle/manifest.json"
    require(sha(manifest_path) == prep["manifest_sha256"] == base["manifest_sha256"], "provider manifest changed")
    required_pins = {prep_path: base["preparation_sha256"], project / "generation/report.json": prep["emission_sha256"],
        project / "generation/kernel.cu": base["kernel_sha256"], project / "generation/kernel.ptx": base["PTX_sha256"],
        project / "generation/compilation.cu": prep["acceptance_gate"]["compilation_source_sha256"],
        project / "preparation/inputs/gate.cu": prep["acceptance_gate"]["source_sha256"], manifest_path: base["manifest_sha256"]}
    require(all(pins.get(str(path)) == digest and sha(path) == digest for path, digest in required_pins.items()), "required preparation/source/gate/PTX pin missing or changed")
    manifest = json.loads(manifest_path.read_bytes())
    for row in manifest["files"]:
        path = (manifest_path.parent / row["path"]).resolve(strict=True)
        require(path.is_relative_to(manifest_path.parent) and sha(path) == row["sha256"] == pins[str(path)], "provider file changed")
    require(sha(manifest_path.parent / manifest["entry"]) == prep["module_sha256"] == base["module_sha256"], "provider image changed")
    commands = {row["label"]: row for row in base["commands"]}
    require(len(commands) == len(base["commands"]), "duplicate baseline commands")
    probe = Path(base["physical_context_probe_executable"]).resolve(strict=True)
    require(sha(probe) == base["physical_context_probe_executable_sha256"] == prep["context_probe_sha256"] == pins[str(probe)], "context probe changed")
    require(commands["physical-context-probe"]["argv"] == [str(probe)] and commands["physical-context-probe"]["exit_code"] == 0, "physical context probe was not run")
    control = base["physical_context_probe"]
    require(control["ok"] and control["scope"] == "physical-CUDA-context-probe" and control["actual_CUDA_contexts"] == 3 and control["actual_device_allocations"] == 1
        and all(control[key] for key in ["caller_context_preserved", "source_reentry_rejected_before_poll", "nested_cleanup_restores_context", "constructor_trap_rolls_back", "physical_cleanup_verified"]), "context probe did not qualify physical ownership")
    probe_trace = source.parent / "context-probe.trace.jsonl"
    require(sha(probe_trace) == base["physical_context_probe_trace_sha256"], "baseline context trace changed")
    context_baseline = inspect_context(probe_trace)
    pins[str(probe_trace)] = sha(probe_trace)
    plan = [{"name": "physical-context-probe", "argv": [str(probe)], "cwd": commands["physical-context-probe"]["cwd"], "expected_exit_code": 0, "context": True, "baseline": context_baseline}]
    for name, spec in specs.items():
        _, kernels, errors, _, code, timeout, pending = spec
        case = cases[name]
        require((case["expected_kernels_per_backend"], case["expected_failed_kernels_per_backend"], case["expected_error"], case["task_timeout_ms"], case["pending"]) == (kernels, errors, code, timeout, pending), "baseline case contract changed: " + name)
        directory = source.parent / name
        executable, foreign = Path(case["executable"]).resolve(strict=True), directory / "foreign.json"
        require(sha(executable) == case["executable_sha256"] == pins[str(executable)] and sha(foreign) == case["foreign_sha256"] == pins[str(foreign)], "native executable or authority changed: " + name)
        build_path = source.parent / (name + "-build.stdout")
        require(sha(build_path) == case["build_receipt_sha256"] == pins[str(build_path)], "build receipt changed: " + name)
        built = json.loads(build_path.read_bytes())
        require(Path(built["executable"]).resolve(strict=True) == executable, "build receipt selects another executable")
        old = commands[name + "-native"]
        check_native_command(old["argv"], executable, foreign, timeout)
        require(Path(old["cwd"]).resolve(strict=True) == directory.resolve(strict=True) and old["exit_code"] == old["expected_exit_code"] == (70 if code else 0), "native baseline failed or moved")
        catalogue = json.loads(foreign.read_bytes())
        require(set(catalogue["libraries"]) == {"gpu"} and (foreign.parent / catalogue["libraries"]["gpu"]["directory"]).resolve(strict=True) == project / "bundle"
            and catalogue["libraries"]["gpu"]["manifest_sha256"] == base["manifest_sha256"], "foreign authority differs")
        trace = directory / "native.trace.jsonl"
        measured = verifier.inspect_trace(trace, kernels, errors, base["kernel_sha256"], base["PTX_sha256"], prep["acceptance_gate"]["source_sha256"], pending, code == "E_CANCELLED")
        require(measured == case["native"], "baseline native trace differs")
        pins[str(trace)] = sha(trace)
        plan.append({"name": name, "argv": old["argv"], "cwd": old["cwd"], "expected_exit_code": old["exit_code"], "context": False,
            "kernels": kernels, "errors": errors, "code": code, "task_timeout_ms": timeout, "pending": pending, "baseline": measured})
    pins[str(source)] = sha(source)
    return base, prep, pins, plan


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["hardware-report", "sanitizer", "output"]:
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    source = args.hardware_report.resolve(strict=True)
    spec = importlib.util.spec_from_file_location("generated_CUDA_memcheck_verifier", Path(__file__).with_name("verify.py"))
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    # Validate physical evidence before resolving or executing the supplied tool.
    base, prep, pins, plan = load_plan(source, verifier)
    if platform.system() not in {"Windows", "Linux"}:
        parser.error("native NVIDIA Compute Sanitizer execution requires Windows/Linux")
    tool = args.sanitizer.resolve(strict=True)
    pins.update({str(tool): sha(tool), str(Path(__file__).resolve()): sha(__file__), str(Path(__file__).with_name("verify.py").resolve()): sha(Path(__file__).with_name("verify.py"))})
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEX_", "NV_COMPUTE_SANITIZER_", "PYTHON", "LD_", "DYLD_"))}
    env.update(PYTHONUTF8="1", NV_COMPUTE_SANITIZER_LOCAL_CONNECTION_OVERRIDE="named-pipes" if os.name == "nt" else "uds")
    report = {"schema": "nex.experimental-generated-CUDA-memcheck/1", "ok": False, "cases": [], "hardware_report_sha256": sha(source),
        "compiler_sha256": base["compiler_sha256"], "module_sha256": base["module_sha256"], "manifest_sha256": base["manifest_sha256"],
        "kernel_sha256": base["kernel_sha256"], "PTX_sha256": base["PTX_sha256"], "retained_input_sha256": pins,
        "task_budgets_changed": False, "actual_GPU_execution": False, "complete_provider_or_public_SDK_accepted": False}

    def save():
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    try:
        check_pins(pins)
        code, stdout, stderr, timed_out = run_bounded([tool, "--version"], out, env, 30)
        (out / "sanitizer-version.stdout").write_bytes(stdout)
        (out / "sanitizer-version.stderr").write_bytes(stderr)
        require(code == 0 and not timed_out and "compute" in (stdout + stderr).decode("utf-8", "replace").lower(), "Compute Sanitizer version probe failed")
        report["sanitizer_version"] = (stdout + stderr).decode("utf-8", "replace")
        for item in plan:
            check_pins(pins)
            name = item["name"]
            log, trace = out / (name + ".memcheck.log"), out / (name + ".trace.jsonl")
            environment = {**env, "NEX_OWNED_CUDA_MAP_TRACE": str(trace)}
            if item.get("pending"):
                environment.update(NEX_OWNED_CUDA_MAP_GATE_CYCLES="200000000", NEX_OWNED_CUDA_MAP_GATE_REPEATS="32")
            argv = [tool, "--tool", "memcheck", "--leak-check", "full", "--error-exitcode", "86", "--log-file", log, *item["argv"]]
            row = {"name": name, "argv": list(map(str, argv)), "expected_exit_code": item["expected_exit_code"], "ok": False}
            report["cases"].append(row)
            save()
            began = time.monotonic()
            code, stdout, stderr, timed_out = run_bounded(argv, item["cwd"], environment, 300)
            (out / (name + ".stdout")).write_bytes(stdout)
            (out / (name + ".stderr")).write_bytes(stderr)
            row.update(exit_code=code, timed_out=timed_out, seconds=time.monotonic() - began)
            require(not timed_out and code == item["expected_exit_code"], name + ": unexpected exit code or process-tree timeout")
            require(log.stat().st_size <= 16 * 1024 * 1024, "memcheck log exceeds its bound")
            row["summary"] = parse_summary(log.read_text(encoding="utf-8", errors="strict"))
            if item["context"]:
                require(json.loads(stdout) == base["physical_context_probe"] and not stderr, "physical context probe result changed")
                context = inspect_context(trace)
                require(context == item["baseline"], "physical context work or device changed")
                row["context"] = context
            else:
                require(stdout == (b"" if item["code"] else b"42\n"), "native source output changed")
                if item["code"]:
                    require(item["code"].encode() in stderr and (item["code"] != "E_RESULT" or b"E_OVERFLOW" in stderr), "native source error changed")
                else:
                    require(not stderr, "unexpected native stderr")
                measured = verifier.inspect_trace(trace, item["kernels"], item["errors"], base["kernel_sha256"], base["PTX_sha256"], prep["acceptance_gate"]["source_sha256"], item["pending"], item["code"] == "E_CANCELLED")
                require(measured["ledger"] == item["baseline"]["ledger"] and measured["sessions"] == item["baseline"]["sessions"], "instrumented physical work/device differs from baseline")
                row["physical"] = measured
            row.update(ok=True, trace_sha256=sha(trace), memcheck_log_sha256=sha(log))
            check_pins(pins)
            save()
        report.update(ok=True, actual_GPU_execution=True, native_cases=15, physical_context_probe=True,
            remaining_gates=["Other generated roots", "Source-deleted NVIDIA delivery", "Coherent public compiler and immutable SDK"])
    except BaseException as error:
        report["error"] = repr(error)
        raise
    finally:
        save()
    print(json.dumps({k: report[k] for k in ["ok", "native_cases", "physical_context_probe", "task_budgets_changed", "actual_GPU_execution"]}))


if __name__ == "__main__":
    main()
