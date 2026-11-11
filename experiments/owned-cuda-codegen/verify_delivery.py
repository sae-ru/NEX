"""Verify captured replay and relocated packaging of the generated CUDA provider."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import runpy
import shutil
import subprocess
import sys
import tempfile
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def inventory(root):
    result = {}
    for path in root.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("delivery inputs must contain regular files, not symlinks")
        if path.is_file():
            result[path.relative_to(root).as_posix()] = sha(path)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["compiler", "resources", "project", "notices", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--host-unavailable-control", action="store_true", help="macOS only: actual FFI delivery with a typed unavailable CUDA result; never GPU acceptance")
    parser.add_argument("--toolchain", type=Path, help="Explicit native toolchain for task builds")
    args = parser.parse_args()
    if args.host_unavailable_control:
        if platform.system() != "Darwin":
            parser.error("the explicit unavailable-driver delivery control requires macOS")
    elif platform.system() not in {"Windows", "Linux"}:
        parser.error("physical delivery verification requires Windows/Linux NVIDIA hardware")
    compiler, resources, project, notices = [p.resolve(strict=True) for p in [args.compiler, args.resources, args.project, args.notices]]
    out = args.output.resolve()
    if any((parent / "nex.json").exists() for parent in [out, *out.parents]):
        parser.error("use a fresh output outside every NEX project, so temporary inputs cannot enter a parent graph")
    out.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).resolve().parent
    spec = importlib.util.spec_from_file_location("generated_CUDA_delivery_trace", source / "verify.py")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    prep = json.loads((project / "preparation/report.json").read_bytes())
    assert prep["ok"] and prep["compiler_sha256"] == sha(compiler) and prep["source_language"] == "0.28"
    assert prep["kernel_sha256"] == sha(project / "generation/kernel.cu")
    assert prep["emission_sha256"] == sha(project / "generation/report.json")
    if not args.host_unavailable_control:
        assert prep["native_provider_built"] and prep["root_hash"] == verifier.ROOT_HASH
        assert prep["NVRTC"]["version"][0] >= 12 and prep["NVRTC"]["PTX_sha256"] == sha(project / "generation/kernel.ptx")
    original_paths = [project / name for name in ["main.nex", "nex.json", "foreign.json", "preparation/report.json", "generation/kernel.cu", "generation/report.json"]]
    original_pins = {str(p): sha(p) for p in original_paths}
    bundle_pins = inventory(project / "bundle")
    pins = {str(p): sha(p) for p in [compiler, notices, source / "verify.py", Path(__file__).resolve()]}
    report = {"schema": "nex.experimental-owned-CUDA-delivery/1", "ok": False, "commands": [],
              "compiler_sha256": sha(compiler), "preparation_sha256": sha(project / "preparation/report.json"),
              "host_unavailable_control": args.host_unavailable_control, "actual_GPU_execution": False,
              "complete_owned_CUDA_or_public_SDK_accepted": False, "original_prepared_inputs_preserved": False}
    started = time.monotonic()
    scratch = Path(tempfile.mkdtemp(prefix="nex-CUDA-delivery-scratch-")).resolve()
    assert not any((p / "nex.json").exists() for p in [scratch, *scratch.parents])
    report["external_TMP"] = str(scratch)
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEX_", "PYTHON", "LD_", "DYLD_"))}
    env.update(NEX_RESOURCE_DIR=str(resources), PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    env.update({name: str(scratch) for name in ["TMPDIR", "TMP", "TEMP", "TEMPDIR"]})

    def save():
        report["seconds"] = time.monotonic() - started
        write(out / "report.json", report)

    def guard():
        assert all(sha(p) == h for p, h in {**pins, **original_pins}.items())
        assert inventory(project / "bundle") == bundle_pins

    def run(label, argv, cwd=out, expected=0, trace=None, deployed=False):
        guard()
        row = {"label": label, "argv": list(map(str, argv)), "cwd": str(cwd), "expected_exit_code": expected}
        report["commands"].append(row)
        save()
        environment = dict(env)
        if deployed:
            environment = {k: v for k, v in os.environ.items() if k in {"SystemRoot", "WINDIR", "SystemDrive", "TEMP", "TMP", "USERPROFILE", "LOCALAPPDATA"}}
            environment.update(PATH=os.path.join(os.environ.get("SystemRoot", "C:/Windows"), "System32") if os.name == "nt" else "/usr/bin:/bin", NEX_RESOURCE_DIR="/absent")
        if trace:
            assert not trace.exists()
            environment["NEX_OWNED_CUDA_MAP_TRACE"] = str(trace)
        value = subprocess.run(row["argv"], cwd=cwd, env=environment, capture_output=True, timeout=900)
        (out / (label + ".stdout")).write_bytes(value.stdout)
        (out / (label + ".stderr")).write_bytes(value.stderr)
        row["exit_code"] = value.returncode
        save()
        assert value.returncode == expected, (label, value.returncode, value.stderr[-3000:])
        guard()
        return value

    def inspect(path, processes):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        groups, current = [], []
        for row in rows:
            current.append(row)
            if row["event"] == "module_unloaded":
                groups.append(current)
                current = []
        assert len(groups) == processes and not current
        result = []
        for index, group in enumerate(groups):
            assert all(row["schema"] == "nex.experimental-owned-CUDA-trace/2" for row in group)
            part = path.with_name(path.stem + "-process-" + str(index) + ".jsonl")
            part.write_text("".join(json.dumps(row) + "\n" for row in group), encoding="utf-8")
            if args.host_unavailable_control:
                last = group[-1]
                assert last["physical_completion_verified"] and not any(row["event"] in {"session_created", "kernel_queued", "unsettled"} for row in group)
                assert all(value == 0 for value in last["ledger"].values())
                result.append({"typed_unavailable_calls": 32, "CUDA_contexts_allocations_launches": 0, "trace_sha256": sha(part)})
            else:
                result.append(verifier.inspect_trace(part, 1, 0, prep["kernel_sha256"], prep["NVRTC"]["PTX_sha256"], prep["acceptance_gate"]["source_sha256"]))
        return result

    try:
        work, authority = out / "working-project", out / "operator-authority"
        work.mkdir()
        authority.mkdir()
        for name in ["stdlib", "bundle"]:
            shutil.copytree(project / name, work / name)
        for name in ["nex.json", "main.nex", "foreign.json"]:
            shutil.copyfile(project / name, work / name)
        catalogue = json.loads((work / "foreign.json").read_bytes())
        assert set(catalogue["libraries"]) == {"gpu"}
        catalogue["libraries"]["gpu"]["directory"] = "./bundle"
        assert catalogue["libraries"]["gpu"]["manifest_sha256"] == sha(work / "bundle/manifest.json")
        write(work / "foreign.json", catalogue)
        shutil.copytree(work / "bundle", authority / "bundle")
        write(authority / "foreign.json", catalogue)
        prefix = (work / "main.nex").read_text(encoding="utf-8").split("server fn main()->unit", 1)[0]
        if args.host_unavailable_control:
            body = 'var i:i64=0;while i<32{let result:result<d::Session>=make_context();assert(!is_ok(result));assert(error_code(result)=="E_COMPUTE_UNAVAILABLE");i=i+1;}'
        else:
            shared = runpy.run_path(str(source.parent / "owned-metal-codegen/verify.py"))
            body, kernels, errors, quota = shared["CASES"]["small_and_i64_codec"]
            assert kernels == 1 and errors == 0 and quota is None
        (work / "main.nex").write_text(prefix + "\nserver fn main()->unit !{task,ffi,io}{" + body + "print(42);}\n", encoding="utf-8")
        checked = json.loads(run("check", [compiler, "check", "--json"], work).stdout)
        foreign = json.loads(run("foreign", [compiler, "foreign", work / "foreign.json", "--json"], work).stdout)
        task = json.loads(run("task-init", [compiler, "task", "main.nex", "--kind", "init", "--json"], work).stdout)
        assert len(task["programs"]) == 1 and task["programs"][0]["id"] == "app"
        assert len(task["checks"]) == 1 and task["checks"][0]["kind"] == "build"
        build = task["checks"][0]
        build.update(timeout_seconds=300, task_limits={"steps": 16000000, "timeout_ms": 30000, "workers": 1})
        toolchain_catalog = None
        if args.toolchain:
            toolchain_report = json.loads(run("toolchain", [compiler, "toolchain", args.toolchain.resolve(strict=True), "--json"], work).stdout)
            build["toolchain"] = "delivery"
            build["toolchain_hash"] = toolchain_report["hash"]
            toolchain_catalog = out / "toolchains.json"
            write(toolchain_catalog, {"delivery": str(args.toolchain.resolve(strict=True))})
        task.update(title="Generated CUDA provider delivery", goal="Capture and replay the exact checked provider, then run an independently relocated package")
        observe = {"id": "observe", "kind": "run", "target": "native", "program": "app", "entry": build["entry"],
            "foreign_hash": foreign["hash"], "timeout_seconds": 180, "task_limits": {"steps": 16000000, "timeout_ms": 30000, "workers": 1},
            "expect": {"stdout": "42\n", "exit_code": 0}}
        if args.toolchain:
            observe["toolchain"] = "delivery"
            observe["toolchain_hash"] = toolchain_report["hash"]
        task["checks"].append(observe)
        task["requirements"].append({"id": "delivery", "text": "Exact values and resource cleanup from the selected generated provider", "targets": ["native"],
            "checks": ["observe"], "bindings": [{"program": "app", "kind": "function", "symbol": build["entry"]}]})
        write(work / "task.json", task)
        toolchain_args = ["--toolchains", str(toolchain_catalog)] if toolchain_catalog else []
        task_checked = json.loads(run("task-check", [compiler, "task", "task.json", "--kind", "check", "--foreign", work / "foreign.json", *toolchain_args, "--json"], work).stdout)
        capture_trace = out / "capture.trace.jsonl"
        captured = json.loads(run("task-capture", [compiler, "task", "task.json", "--kind", "run", "--foreign", work / "foreign.json", "--task-hash", task_checked["task_hash"], *toolchain_args, "--directory", out / "capture", "--json"], work, trace=capture_trace).stdout)
        assert captured["ok"] and all(c["status"] == "passed" for c in captured["checks"])
        report["capture"] = inspect(capture_trace, 2)
        notice_data = json.loads(notices.read_bytes())
        assert notice_data["schema"] == "nex.sdk-notices/1"
        for component in notice_data["components"]:
            for key in ["roots", "license_files"]:
                component[key] = [str((notices.parent / p).resolve(strict=True)) for p in component[key]]
        notice_data["components"].append({"name": "NEX-generated-CUDA-provider", "version": "experimental", "url": "https://github.com/sae-ru/NEX",
            "roots": [str(work / "bundle")], "license_files": [str(work / "bundle/NOTICE")]})
        write(out / "package-notices.json", notice_data)
        package = out / "application"
        package_command = [compiler, "package", "--foreign", work / "foreign.json", "--notices", out / "package-notices.json", "--directory", package, "--json"]
        if args.toolchain:
            package_command += ["--toolchain", str(args.toolchain.resolve(strict=True))]
        packaged = json.loads(run("package", package_command, work).stdout)
        application = json.loads((package / "application.json").read_bytes())
        assert application["schema"] == "nex.application-package/1" and not application["execution_verified"]
        assert {p.relative_to(package).as_posix() for p in package.rglob("*") if p.is_file() or p.is_symlink()} == set(application["files"]) | {"application.json"}
        for name, item in application["files"].items():
            path = package / name
            if path.is_symlink():
                assert str(path.readlink()) == item["symlink"] and path.resolve().is_relative_to(package)
            else:
                assert sha(path) == item["sha256"] and path.stat().st_size == item["bytes"]
        report.update(checked_revision=checked["revision"], task_hash=task_checked["task_hash"], captured_receipt_sha256=sha(captured["output"]),
                      original_bundle_manifest_sha256=sha(work / "bundle/manifest.json"), application_manifest_sha256=sha(package / "application.json"),
                      deleted_working_inventory=inventory(work))
        shutil.rmtree(work)
        assert not work.exists()
        moved = out / "Relocated CUDA application % 🧠"
        package.rename(moved)
        receipt = Path(captured["output"])
        denied_trace = out / "unauthorized-replay.trace.jsonl"
        denied = json.loads(run("replay-without-authority", [compiler, "task", receipt, "--kind", "replay", *toolchain_args, "--directory", out / "denied-replay", "--json"], expected=1, trace=denied_trace).stdout)
        assert denied["code"] == "E_TASK_FOREIGN" and not denied_trace.exists()
        replay_trace = out / "replay.trace.jsonl"
        replay = json.loads(run("source-deleted-replay", [compiler, "task", receipt, "--kind", "replay", "--foreign", authority / "foreign.json", *toolchain_args, "--directory", out / "replay", "--json"], trace=replay_trace).stdout)
        assert replay["ok"] and replay["task_hash"] == captured["task_hash"] and replay["foreign_catalogue"] == captured["foreign_catalogue"]
        report["replay"] = inspect(replay_trace, 2)
        executable = moved / ("bin/app.exe" if os.name == "nt" else "bin/app")
        command = [executable]
        if platform.system() == "Darwin":
            forbidden = [project, resources, authority]
            policy = '(version 1)(allow default)' + ''.join('(deny file-read* (subpath ' + json.dumps(str(p)) + '))' for p in forbidden) + '(deny file-read* (literal ' + json.dumps(str(compiler)) + '))'
            (out / "standalone.sb").write_text(policy, encoding="utf-8")
            canaries = [project / "main.nex", resources / "LICENSE", authority / "foreign.json", compiler]
            probe = 'import sys\nfor p in sys.argv[1:]:\n try:\n  open(p,"rb").close()\n except PermissionError:\n  continue\n raise RuntimeError("input was readable: "+p)\nprint(len(sys.argv)-1)\n'
            denied = run("standalone-input-read-denials", ["/usr/bin/sandbox-exec", "-f", out / "standalone.sb", sys.executable, "-I", "-B", "-c", probe, *canaries], deployed=True)
            assert denied.stdout == b"4\n" and denied.stderr == b""
            report["standalone_actual_input_read_denials"] = len(canaries)
            command = ["/usr/bin/sandbox-exec", "-f", out / "standalone.sb", executable]
        standalone_trace = out / "standalone.trace.jsonl"
        value = run("relocated-standalone", command, cwd=out, trace=standalone_trace, deployed=True)
        assert value.stdout == b"42\n" and value.stderr == b""
        report["standalone"] = inspect(standalone_trace, 1)
        assert not work.exists()
        guard()
        report.update(ok=True, state="passed", working_project_sources_bundle_and_graph_deleted=True,
            replay_explicit_current_authority_required=True, original_prepared_inputs_preserved=True,
            standalone_original_project_resources_and_authority_OS_read_denied=platform.system() == "Darwin",
            actual_GPU_execution=not args.host_unavailable_control,
            actual_GPU_kernel_completions=0 if args.host_unavailable_control else 5,
            typed_unavailable_calls=160 if args.host_unavailable_control else 0,
            remaining_gates=["Native NVIDIA execution of delivery controls" if args.host_unavailable_control else "Remaining physical provider corpora", "Compute Sanitizer", "Other generated roots", "Coherent public compiler and immutable SDK"])
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({k: report[k] for k in ["ok", "working_project_sources_bundle_and_graph_deleted", "actual_GPU_execution", "typed_unavailable_calls"]}))


if __name__ == "__main__":
    main()
