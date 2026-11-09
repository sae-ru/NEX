"""Check generated Metal protocol isolation from bounded vendor diagnostics."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["sdk", "project", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    sdk, project, out = args.sdk.resolve(strict=True), args.project.resolve(strict=True), args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    compiler = sdk / "bin/nex"
    template = (project / "main.nex").read_text()
    prefix = template[:template.index("server fn main()->unit")]
    language = json.loads((project / "nex.json").read_bytes())["language"]
    spec = importlib.util.spec_from_file_location("generated_log_trace", Path(__file__).with_name("verify.py"))
    verify = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verify)
    directory = out / "application"
    directory.mkdir()
    (directory / "nex.json").write_text(json.dumps({"schema": "nex.project/1", "language": language, "entry": "main.nex", "libraries": {"std": str(project / "stdlib")}}) + "\n")
    body = '''let s:d::Session=unwrap(make_context());let answer:bytes=apply(s,[encode_i64s([6]),encode_i64s([2])],1,512);assert(decode_i64s(answer)==[22]);resource_close(s);print(42);'''
    (directory / "main.nex").write_text(prefix + "server fn main()->unit !{task,ffi,io}{" + body + "}\n")
    catalogue = json.loads((project / "foreign.json").read_bytes())
    catalogue["libraries"]["gpu"]["directory"] = str(project / "bundle")
    foreign = directory / "foreign.json"
    foreign.write_text(json.dumps(catalogue, indent=2) + "\n")
    env = {key: value for key, value in os.environ.items() if not key.startswith("NEX_OWNED_METAL_MAP_TEST_")}
    env.update(NEX_RESOURCE_DIR=str(sdk / "share/nex"), PYTHONDONTWRITEBYTECODE="1", NEX_OWNED_METAL_MAP_TEST_NOISE="1")
    report = {"schema": "nex.owned-generated-Metal-log-isolation/1", "ok": False, "state": "running", "commands": [], "cases": [],
              "compiler_sha256": sha(compiler), "worker_sha256": sha(project / "bundle/worker"), "module_sha256": sha(project / "bundle/module.so"),
              "manifest_sha256": sha(project / "bundle/manifest.json"), "harness_sha256": sha(Path(__file__)),
              "trace_verifier_sha256": sha(Path(__file__).with_name("verify.py")), "vendor_file_limit_imposed": False,
              "installed_SDK_accepted": False, "whole_original_goal_complete": False}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(label, argv, extra=None):
        row = {"label": label, "argv": list(map(str, argv))}
        report["commands"].append(row)
        save()
        result = subprocess.run(row["argv"], cwd=directory, env={**env, **(extra or {})}, capture_output=True, text=True, timeout=300)
        (out / (label + ".stdout")).write_text(result.stdout)
        (out / (label + ".stderr")).write_text(result.stderr)
        row["exit_code"] = result.returncode
        save()
        assert result.returncode == 0, (label, result.returncode, result.stdout[-2000:], result.stderr[-2000:])
        return result

    try:
        run("check", [compiler, "check", "--json"])
        built = json.loads(run("build", [compiler, "build", "--profile", "release", "--build-directory", out / "native", "--json"]).stdout)
        for name, cache_enabled, noise in [("cache9MiB", True, 0), ("stdout9MiB", False, 9437184), ("cache_and_stdout9MiB", True, 9437184)]:
            modes = {}
            for mode in ["reference", "native"]:
                trace, cache = out / (name + "-" + mode + ".trace.jsonl"), out / (name + "-" + mode + "-cache.bin")
                extra = {"NEX_OWNED_METAL_MAP_TRACE": str(trace)}
                if cache_enabled:
                    extra["NEX_OWNED_METAL_MAP_TEST_CACHE_FILE"] = str(cache)
                if noise:
                    extra["NEX_OWNED_METAL_MAP_TEST_NOISE_BYTES"] = str(noise)
                argv = [compiler, "eval", "--foreign", foreign, "--task-workers", "1", "--json"] if mode == "reference" else [built["executable"], "--nex-foreign", foreign, "--nex-task-workers", "1"]
                result = run(name + "-" + mode, argv, extra)
                if mode == "reference":
                    value = json.loads(result.stdout)
                    assert value["stdout"] == "42\n" and value["foreign_resource_bytes_after_scope"] == 0
                else:
                    assert result.stdout == "42\n" and result.stderr == ""
                physical = verify.inspect_trace(trace, 1, 0)
                rows = [json.loads(line) for line in trace.read_text().splitlines()]
                diagnostics = [row for row in rows if row["event"] == "worker_diagnostics"]
                assert len(diagnostics) == 1
                diagnostic = diagnostics[0]
                assert diagnostic["bounded_capture"] and diagnostic["bytes"] <= 65536
                raw = bytes.fromhex(diagnostic["hex"]).decode("utf-8", errors="strict")
                assert "NEXGPU_OPEN " in raw and "NEXGPU_MAP " in raw and "NEXGPU_DRAIN " in raw
                if noise:
                    assert diagnostic["received_bytes"] > noise and "NEXGPU_LOG_DROPPED " in raw and "NEXGPU_TEST_NOISE_END 9437184" in raw
                if cache_enabled:
                    assert cache.stat().st_size == 9437184 and "NEXGPU_TEST_CACHE_END 9437184" in raw
                exited = [row for row in rows if row["event"] == "worker_exited"]
                assert len(exited) == 1 and exited[0]["exit_code"] == exited[0]["signal"] == 0
                modes[mode] = {"physical": physical, "received_log_bytes": diagnostic["received_bytes"], "saved_log_bytes": diagnostic["bytes"],
                               "cache_bytes": cache.stat().st_size if cache_enabled else 0, "physical_GPU_events": 1}
            assert modes["reference"]["physical"]["devices"] == modes["native"]["physical"]["devices"]
            report["cases"].append({"name": name, "native_reference": True, "observed": modes})
            save()
        assert sha(compiler) == report["compiler_sha256"] and sha(project / "bundle/worker") == report["worker_sha256"] and sha(project / "bundle/module.so") == report["module_sha256"]
        report.update(ok=True, state="passed", native_reference_pairs=3, actual_GPU_execution=True, physical_GPU_kernel_events=6)
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "native_reference_pairs", "physical_GPU_kernel_events"]}))


if __name__ == "__main__":
    main()
