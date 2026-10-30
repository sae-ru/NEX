# Experimental CIX P1 accelerator fixture

This optional example calls the actual Mali GPU and Zhouyi NPU from NEX
language0.16 through the existing trusted C value FFI. It does not change the
language/compiler, implement a general GPU kernel compiler or accept arbitrary
NPU models. It is outside the installed SDK and default regression suite.

The physical CIX P1 CD8160 board passed the interpreter, native debug/release,
both native test profiles and a standalone executable with its SDK/source paths
temporarily unavailable. Across these runs, NEX checked24 GPU calls/24,576 bytes
and16 NPU calls/96 values. All16 NPU profiles identify only
`ZhouyiExecutionProvider`; CPU EP fallback was explicitly disabled. See
[the evidence](../../docs/evidence/cix-p1-ffi-0.70.0.json).

## Current preparer

The current preparer selects the actual SDK's advertised source dialect
(language0.20+, including0.27); its original language0.16 native branch is
retained. `--check-sdk` validates the real template and both FFI signatures on
the selected SDK without compiling native code or initializing either device:

```sh
python3 experiments/cix-p1/prepare.py --sdk /path/to/nex-sdk --check-sdk
```

Current-language source preparation is checked separately from the historical
hardware receipts below. The0.151.0/language0.27 CIX/RK device checks are recorded
in [the scoped receipt](../../docs/evidence/accelerators-0.151.0.json); they do not
certify a later compiler or a portable SDK. For0.151.0 the CIX preparation used
an external helper selecting027; the integrated preparer update is in0.151.1.

## Prepare and execute

The existing0.70 fixture has also been retested on the same physical board with
a private0.92/language0.18 SDK and explicit migration of a copied genuine0.16
graph. Reference/native Debug/Release tests and runs, native profile,
source-deleted archived replay and standalone execution pass. Native tests run
both reference and native paths: ten fixture executions produce30 GPU calls
and20 exclusively Zhouyi NPU calls, with CPU fallback disabled. Original graph
rows/schema and the original fixture remain preserved. This does not expand
the fixed adapter API or establish generic accelerator support.
See [the0.92 receipt](../../docs/evidence/cix-p1-ffi-0.92.0.json).

Use an installed, matching Linux ARM64 NEX SDK, system GCC with C++20, and the
configured CIX driver environment. Preparation creates a new project, derives
signatures with the actual compiler, builds a module, pins its manifest and
checks the separate operator catalogue. It does not initialize either device.

```sh
python3 experiments/cix-p1/prepare.py --sdk /path/to/nex-sdk --output /tmp/my-new-cix-project
cd /tmp/my-new-cix-project
export PATH=/path/to/nex-sdk/bin:$PATH
export OPERATOR_PATH=/usr/share/cix/lib/onnxruntime/operator/
export NEX_CIX_ORT_LIBRARY=/opt/afar-npu/lib/python3.11/site-packages/onnxruntime/capi/libonnxruntime.so.1.20.0
export NEX_CIX_TRACE_FILE=/tmp/my-new-cix-project/trace.jsonl
nex eval --foreign host.json --json
nex run --profile debug --foreign host.json --json
nex run --profile release --foreign host.json --json
nex test --profile debug --foreign host.json --json
nex test --profile release --foreign host.json --json
```

The tested NPU runtime SHA-256 is
`79474a8eb6288ca73dae8d7b9fac746f62e6fd9c60737612d1baa16715b2b715`.
Runtime/driver files outside the bundle are external platform dependencies;
the module manifest does not authenticate them. Configure and verify their
actual versions separately. `NEX_CIX_ORT_LIBRARY` is a required absolute path,
not a CPU fallback choice. The GPU library path is specific to this board.

`nex build --profile release --json` reports a standalone executable. Execute it
with `--nex-foreign /absolute/path/to/host.json` and the configured driver
environment. It requires the adapter bundle, platform C++/Crypto libraries and
GPU/NPU libraries. The historical private-SDK test verified actual execution
with SDK/source paths unavailable; the commands above do not hide your SDK.

## Boundaries and lifetime

`gpu_affine(a:bytes,b:bytes)` computes a fixed OpenCL `3*a+b` kernel on a GPU-only
device. Inputs have equal nonzero lengths up to65,536, `a<=60`, `b<=30`.
`npu_mul(list<f64>)` accepts exactly six finite, exactly float32-representable
values and runs one embedded3x2 ONNX Mul fixture. NEX checks outputs against
its own arithmetic. Size, range and precision errors are tested. Calls are
synchronous and serialized; source concurrency and hard cancellation during a
driver call remain pending. These small checks establish correctness and
placement, not representative speed or memory performance.

The vendor NPU compiler contains LLVM symbols. On the tested glibc target,
`RTLD_DEEPBIND` prevents collision with LLVM22 in the development compiler.
Ordinary unload/reload passed one NPU call but failed the second; retaining
vendor code/static state with `RTLD_NODELETE` passed three successive control
runs and the complete NEX acceptance. Sessions, tensors and OpenCL resources
are released on each call. The vendor library intentionally remains loaded
until process exit. This is a platform-specific adapter policy.

Check/build/signature export do not grant native execution. Source pins plus
the explicit `--foreign`/`--nex-foreign` catalogue grant are mandatory. Native
extensions are trusted code; this is not memory isolation. Generic tensors,
arbitrary models/kernels, device-loss recovery, async scheduling, runtime
caching, application packaging of drivers and other hardware remain pending.

Header provenance: Microsoft ONNX Runtime v1.20.0 C API (MIT), Khronos
OpenCL-Headers v2024.10.24 (Apache-2.0), and Arm China Compass ONNX Runtime
rel-1.22.0 Zhouyi factory declaration (Apache-2.0). The installed runtime exports
the tested factory signature. Full licenses accompany the headers; the generated
module NOTICE includes nlohmann/json's MIT notice from its matching NEX SDK.
