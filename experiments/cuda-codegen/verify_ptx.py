"""Compile pinned emitted CUDA through LLVM22.1 IR verification and NVPTX."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def kernel_abi(text, name):
    match = re.search(r"\.visible\s+\.entry\s+" + re.escape(name) + r"\s*\((.*?)\)", text, re.S)
    if not match:
        raise RuntimeError("missing PTX kernel entry " + name)
    return [int(bits) for bits in re.findall(r"\.param\s+\.[ub](\d+)\s", match[1])]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ["matrix", "clang", "opt", "llc", "gate", "combined", "output"]:
        parser.add_argument("--" + name, required=True, type=Path)
    args = parser.parse_args()
    matrix, clang, opt, llc, gate, combined = [p.resolve(strict=True) for p in
        [args.matrix, args.clang, args.opt, args.llc, args.gate, args.combined]]
    out = args.output.absolute()
    out.mkdir(parents=True, exist_ok=False)
    header = Path(__file__).with_name("clang_device.h").resolve(strict=True)
    pins = {str(p): sha(p) for p in [matrix, clang, opt, llc, gate, combined, header, Path(__file__).resolve()]}
    env = {k: v for k, v in os.environ.items() if not k.startswith(("NEX_", "CUDA_", "CLANG_", "PYTHON", "LD_", "DYLD_")) and k not in
        {"CPATH", "CPLUS_INCLUDE_PATH", "C_INCLUDE_PATH", "OBJC_INCLUDE_PATH", "LIBRARY_PATH", "SDKROOT"}}
    report = {"schema": "nex.experimental-CUDA-offline-NVPTX-control/1", "ok": False, "commands": [], "cases": [],
              "input_pins": pins, "actual_GPU_execution": False, "NVRTC_or_CUBIN_assembly_accepted": False,
              "public_CUDA_CLI_or_provider_or_SDK_accepted": False}
    started = time.monotonic()

    def save():
        report["seconds"] = time.monotonic() - started
        (out / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def run(label, argv):
        row = {"label": label, "argv": list(map(str, argv))}
        report["commands"].append(row)
        save()
        value = subprocess.run(row["argv"], cwd=out, env=env, capture_output=True, timeout=60)
        (out / (label + ".stdout")).write_bytes(value.stdout)
        (out / (label + ".stderr")).write_bytes(value.stderr)
        row["exit_code"] = value.returncode
        save()
        if value.returncode:
            raise RuntimeError(label + " failed; preserve LLVM IR and diagnostics")
        return value.stdout

    try:
        versions = {}
        for name, tool in [("clang", clang), ("opt", opt), ("llc", llc)]:
            text = run(name + "-version", [tool, "--version"]).decode("utf-8")
            if not re.search(r"version\s+22\.1\.\d+", text):
                raise RuntimeError(name + " must be LLVM22.1")
            versions[name] = text
        assert clang.parent == opt.parent == llc.parent
        report["tool_versions"] = versions
        resource = Path(run("clang-resource-dir", [clang, "--no-default-config", "-print-resource-dir"]).decode().strip()).resolve(strict=True)
        builtin = resource / "include/__clang_cuda_builtin_vars.h"
        pins[str(builtin)] = sha(builtin)
        report["Clang_builtin_header_sha256"] = pins[str(builtin)]
        data = json.loads(matrix.read_bytes())
        assert data["ok"] and not data["GPU_execution_claimed"] and len(data["cases"]) == 56
        assert data["source_fixtures"] == 28 and data["lane_results_checked"] == 256
        inputs = []
        for case in data["cases"]:
            shader = (matrix.parent / case["shader"]).resolve(strict=True)
            assert shader.is_relative_to(matrix.parent) and sha(shader) == case["shader_sha256"]
            pins[str(shader)] = case["shader_sha256"]
            pointers = 3 if case["layout"] == "rows" else len(case["metadata"]["parameter_types"]) + 2
            inputs.append((case["name"] + "-" + case["layout"], shader, {"nex_generated_cuda_map": [64] * pointers + [32, 32]}, False))
        inputs += [("acceptance-gate", gate, {"nex_acceptance_gate": [64]}, True),
                   ("prepared-combined", combined, {"nex_generated_cuda_map": [64, 64, 64, 64, 32, 32], "nex_acceptance_gate": [64]}, True)]
        for name, shader, entries, needs_clock in inputs:
            for arch, ptx_feature, ptx_version in [("sm_52", "ptx42", "4.2"), ("sm_86", "ptx71", "7.1")]:
                for optimization in [0, 2]:
                    label = name + "-" + arch + "-O" + str(optimization)
                    ir, ptx = out / (label + ".ll"), out / (label + ".ptx")
                    run(label + "-frontend", [clang, "--no-default-config", "--target=x86_64-unknown-linux-gnu", "-x", "cuda",
                        "--cuda-device-only", "--cuda-gpu-arch=" + arch, "--cuda-feature=+" + ptx_feature,
                        "-resource-dir", resource, "-nocudainc", "-nocudalib", "-nostdinc", "-nostdinc++", "-isystem", resource / "include",
                        "-std=c++20", "-O" + str(optimization), "-S", "-emit-llvm", "-include", header, shader, "-o", ir])
                    ir_text = ir.read_text()
                    assert 'target triple = "nvptx64-nvidia-cuda"' in ir_text
                    assert all("ptx_kernel void @" + entry + "(" in ir_text for entry in entries)
                    run(label + "-IR-verify", [opt, "-passes=verify", "-disable-output", ir])
                    run(label + "-NVPTX", [llc, "-march=nvptx64", "-mcpu=" + arch, "-mattr=+" + ptx_feature,
                        "-O=" + str(optimization), "-verify-machineinstrs", ir, "-o", ptx])
                    text = ptx.read_text()
                    assert ".address_size 64" in text and re.search(r"\.target\s+" + arch + r"\b", text)
                    assert re.search(r"\.version\s+" + re.escape(ptx_version) + r"\b", text)
                    assert not re.search(r"\.extern\s+\.func", text), "unexpected unresolved device runtime dependency"
                    actual = {entry: kernel_abi(text, entry) for entry in entries}
                    assert actual == entries, (label, actual, entries)
                    if needs_clock:
                        assert "%clock64" in text
                    report["cases"].append({"name": name, "target": arch, "PTX_version": ptx_version, "optimization": optimization,
                        "source_sha256": sha(shader), "LLVM_IR_sha256": sha(ir), "PTX_sha256": sha(ptx), "kernel_parameter_bits": actual,
                        "LLVM_IR_and_machine_instructions_verified": True, "unresolved_device_functions": 0, "clock64_required_and_present": needs_clock})
                    save()
        assert all(sha(Path(path)) == value for path, value in pins.items())
        assert len(report["cases"]) == 232
        report.update(ok=True, state="passed", emitted_source_layouts=56, scalar_programs=28,
                      verified_IR_and_PTX_variants=len(report["cases"]), target_architectures=["sm_52", "sm_86"], optimization_levels=[0, 2],
                      gate_and_actual_combined_preparation_included=True, NVIDIA_headers_or_libdevice_used=False)
    except BaseException as error:
        report.update(state="failed", error=repr(error))
        raise
    finally:
        save()
    print(json.dumps({key: report[key] for key in ["ok", "scalar_programs", "emitted_source_layouts", "verified_IR_and_PTX_variants", "actual_GPU_execution"]}))


if __name__ == "__main__":
    main()
