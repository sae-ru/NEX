# Physical CIX P1 verification

The physical test board reports CIX P1 CD8160 / CIX Phecda,12 ARM cores
(Cortex-A720/A520), Debian12 ARM64, kernel6.6.89-cix, glibc2.36 and GCC12.2.
Its Mali-G720-Immortalis GPU is exposed through the proprietary ARM OpenCL3.0
and Vulkan driver. The NPU driver exposes `/dev/aipu`; the installed CIX
ONNX Runtime1.20.0 registers `ZhouyiExecutionProvider`.

## NEX compiler and native applications

The toolchain0.70/language0.16 Linux SDK was deployed to a private test directory
on this board. The development compiler and LLVM22.1.8 use a private ELF loader
and dependency closure compatible with that compiler's build. Generated programs
use the board's own Debian12/GCC12/glibc2.36 environment. A private SQLite3.54.1
archive is compiled against the board; OpenSSL headers/libraries come from its
installed development environment. No system packages, loader settings or global
installation are changed. This is a verified private test setup, not a portable
installer or a generic Linux distribution certification.

On the actual CPU, ten installed examples pass check/eval/test and debug/release
build/run: arithmetic, immutable data, modules, generics, traits, function values,
finite numbers, bytes, matching and results/typed JSON. All20 application runs
agree with the reference interpreter. Copied executables also run from `/` with
only the ordinary system PATH and no NEX environment. Their actual `ldd` output
contains no NEX SDK, LLVM, MLIR or Z3 dependency. Checked overflow returns
`E_OVERFLOW`/exit70 in both profiles. This evidence applies to the patched private
toolchain0.70 SDK; the0.71 project-build candidate has separate acceptance gates.

## Accelerator probes

```sh
python3 tools/accelerators/cix_opencl_probe.py
python3 tools/accelerators/cix_onnx_probe.py
```

Run these explicitly on a configured CIX board. The OpenCL probe expects the
installed CIX GPU library path and selects only `CL_DEVICE_TYPE_GPU`; it never
substitutes a CPU device. It compiles one bounded integer kernel, checks all
65,536 outputs against a host oracle for each of three inputs and records actual
event profiling timestamps. All196,608 results matched on this board. These are
capability/correctness checks, not representative application performance data.

The ONNX probe requires a Python environment with the installed CIX runtime and
NumPy. It uses that runtime's existing fixed-shape3x2 `mul_1.onnx` fixture,
sets `session.disable_cpu_ep_fallback=1`, disables Python fallback and compares
three inputs against an explicit CPU reference session. It requires all executed
profile events to identify Zhouyi EP. The observed process opened `/dev/aipu`,
all three profiled executions used Zhouyi and maximum absolute error was zero.
Its temporary directory retains the profile and receipt. Provider registration
alone is not sufficient evidence of actual placement.

The platform-specific probes above do not execute NEX source. A separate
[experimental trusted adapter](../experiments/cix-p1/README.md) now executes a
fixed OpenCL affine kernel and one embedded3x2 ONNX model from actual NEX source.
The interpreter, native debug/release, both native test profiles and a standalone
application passed on the board:24 GPU calls/24,576 checked output bytes and16
NPU calls/96 checked values. All16 NPU profiles identify Zhouyi EP only; CPU
fallback remains disabled. Size/range/float32-precision rejection and standalone
execution with SDK/source paths unavailable also passed. Exact hashes and scope
are recorded in [the accelerator evidence](evidence/cix-p1-ffi-0.70.0.json).

The adapter isolates vendor LLVM symbol lookup with `RTLD_DEEPBIND` and retains
vendor library/static state with `RTLD_NODELETE` until process exit. Without the
latter, a three-run control passed the first call and failed the second; with it,
all three passed. Per-call sessions, tensors and OpenCL resources are released.
This policy is specific to the tested runtime; the compiler/core language did
not change. The optional fixture is outside the installed SDK/default tests.

Additional models/operators, a general kernel/model API, automatic precision
policies, device-loss handling, scheduling and integration with NEX profiling/
debugging remain pending. Physical testing on one ARM64 board proves neither
every target nor every driver/OS/processor combination. Application deployment
still requires matching target ABI, platform libraries and accelerator drivers.

Primary runtime references: [Arm China Compass ONNX Runtime](https://github.com/Arm-China/Compass_Onnxruntime)
and [ONNX Runtime CPU fallback setting](https://github.com/microsoft/onnxruntime/blob/v1.20.0/include/onnxruntime/core/session/onnxruntime_session_options_config_keys.h).
