# Explicit experimental Linux ARM64 compute providers

These opt-in trusted native FFI providers use pinned module/child-worker bundles.
They do not add source syntax, a general kernel/model compiler, task/FFI bridge,
owned device buffers, persistent worker pool or automatic platform support.

The OpenCL provider executes exact U8 `scale*a+b` with scale0..255 on an actual
GPU. `Add` uses scale1. Inputs cover all0..255 octets; at most262144 elements
cross the immutable bulk byte transport. A separate GPU overflow flag is written
for every element. Any result above255 returns `E_COMPUTE_OVERFLOW`; wrapped or
partially computed output is never published. Context reports CPU fallback only
when the caller explicitly permits it for unavailable/unsupported devices.
An overflow remains an error even when fallback is allowed.

The RKNN provider performs exact row-major signed I8 matmul with I32 little-endian
output. Bounds are M1..32 and K,N multiples of32 in32..128. SDK headers/runtime
remain private operator dependencies, outside the NEX repository; preparation
records their hashes and license. CPU initialization of the cached output DMA
mapping produced stale values on the tested board; output C is left untouched
before the vendor run, matching the verified upstream allocation discipline.

Only bounded binary frames cross the pinned child boundary. Vendor stdout/stderr
is isolated inside the child and retained separately; parent machine JSON is
unchanged. Host polling covers both the serialized device lease and child wait.
Cancellation while queued starts no worker; failure/cancellation after spawn
reaps the child and removes private files. Device call deadline is60 seconds.
Process reap is not a claim that all vendor/device settlement or future owned
buffer lifetimes have been implemented.

## Prepare and run

From this source tree on Linux ARM64, using a complete target C++20 compiler:

```sh
python3 experiments/rk3588/prepare.py --sdk /path/to/sdk --backend gpu \
  --output /new/gpu-project --cxx /usr/bin/g++
python3 experiments/rk3588/verify.py --sdk /path/to/sdk --backend gpu \
  --project /new/gpu-project --output /new/gpu-receipts
```

For the ordinary-source common compute API, prepare the GPU project directly:

```sh
python3 experiments/rk3588/prepare.py --sdk /path/to/sdk --backend gpu \
  --api compute --opencl-library /absolute/path/to/libOpenCL.so.1 \
  --output /new/common-gpu
python3 experiments/rk3588/verify_compute.py --sdk /path/to/sdk \
  --project /new/common-gpu --output /new/common-gpu-receipts
```

`--api raw` remains the default. Common GPU preparation vendors this tree's
`lib/compute.nex` under an explicit project library mapping, creates the typed
Context/CPU oracle/fallback example and generates the pinned foreign catalogue.
It works with a compatible language0.20 SDK and does not install or modify it.
The source alias `gpu_raw` and module export `gpu_compute` share the exact typed
signature; the compiler validates the catalogue before device execution.

`--opencl-library` is an operator-selected existing Linux ARM64 loader, resolved
to an absolute file and embedded in the pinned worker at compile time. There is
no environment variable for selecting the top-level loader and no CPU OpenCL fallback. Preparation
records the installed runtime SHA256 as provenance, without claiming that the
runtime stays immutable or that all its dependencies are pinned. On CIX the
installed loader is under `/opt/cixgpu-pro/lib/aarch64-linux-gnu/`; on RK3588 the
default is `/usr/lib/aarch64-linux-gnu/libOpenCL.so.1`. This selects a runtime,
not a physical GPU UUID: the worker still selects the first actual GPU device
and records its real name/type. Automatic multi-device discovery remains open.

Use `--opencl-include DIRECTORY` for an explicit OpenCL-Headers directory with
`CL/` and `OPENCL-LICENSE`. Otherwise the checked source headers under
`experiments/cix-p1/include` are used. This provider currently opens
`/usr/lib/aarch64-linux-gnu/libOpenCL.so.1` and uses the first actual GPU. Its
implementation/version metadata and operator ID are not a hardware attestation;
the numerical/device receipts record the actual selected device separately.

Preparation creates a new directory and validates signature/grants without
executing hardware. Verification runs reference, native Debug/Release, tests,
profile, archived source-deleted replay and standalone from `/` with SDK
resources unavailable. The exact reference budget is16M steps; actual usage is
reported. Normal FFI quotas are not raised: even maximum inputs/output need
786432 copied payload bytes, below the default1MiB quota.

NPU preparation additionally requires explicitly supplied private SDK files:

```sh
python3 experiments/rk3588/prepare.py --sdk /path/to/sdk --backend npu \
  --vendor-include /private/rknn/include --vendor-license /private/RKNN-SDK-LICENSE \
  --output /new/npu-project --cxx /usr/bin/g++
```

`compute-main.nex.in` adapts these raw byte bindings to `std/compute.nex`:
checked Tensor/Request/Response/Device, server Context, actual-device reporting,
strict response validation and explicit CPU fallback. Materialize reviewed real
bundle pins and device descriptors before checking/executing it. Logical device
IDs describe this configured provider, not general multi-GPU discovery. The
source Context is an ordinary opaque callable value, not a new owned resource.

## Numerical and process checks

```sh
python3 experiments/rk3588/test_pack.py --sdk /path/to/sdk --output /new/pack
python3 experiments/rk3588/test_gpu_process.py --sdk /path/to/sdk \
  --opencl-include /path/to/OpenCL-Headers --output /new/process
python3 experiments/rk3588/test_gpu_worker.py --bundle /new/gpu-project/bundle \
  --output /new/worker
```

Packing checks fixed signed encodings, all256 I8 values, bounds and immutable
inputs on native/TypeScript/reference. Eleven controlled-child process tests
check framing, malformed/truncated/oversized/status/length results, exit/signal,
cancellation/reap and queued cancellation without spawning. These are transport
regressions, not simulated hardware acceptance. The worker test explicitly
executes the real pinned OpenCL worker at representative scale0..255 boundaries,
maximum arrays and overflow only in the last element; invalid frames are rejected
before GPU creation.

RK3588S/Mali-G610 receipts retain90 raw GPU calls,30780 exact successful values
and10 overflow rejections through reference/Debug/Release/test/profile/replay/
standalone. The worker boundary suite checks524321 successful bytes. The common
Context receipt adds49 GPU calls (7 intentional overflow errors),21 RKNN calls,
maximum512x512 tensors, exact CPU oracle, denied/allowed fallback and retained
cleanup/profile/replay. These source/library tests use the existing0.120/language
0.20 compiler on the board; they are not a full0.121 compiler/platform gate.

See [the common contract](../../docs/compute.md) for typed semantics and
[historical0.120 acceptance](../../docs/stand-acceptance-0.120.md) for the earlier
fixed fixtures. Float tensors, generalized OpenCL matmul/models, other providers,
proper runtime discovery, owned buffers and async/persistent execution remain
planned work.

## Versioning a generated project

Keep the NEX source, `nex.json`, vendored `stdlib/compute.nex`, provider source,
preparation recipe and reviewed dependency/license metadata in Git. The generated
`host.json` and bundle manifest bind exact platform artifacts; retain those
artifacts in your release storage when retaining their pins. Rebuilding on a new
machine may produce a different bundle pin: regenerate and validate the source
binding/catalogue together, then record that change as a new revision. Do not
edit an old pin to pretend a different binary is the original artifact.

The source graph/replay retains imported NEX source. It does not make a vendor
SDK, installed driver or external native module part of the language. The tested
standalone executable runs without SDK resource files but still requires its
explicit pinned foreign catalogue/bundle, installed vendor runtime and GPU.
Private RKNN headers/runtime are operator dependencies and are not copied into
this repository by preparation.

## Portable common-GPU acceptance

The same generator passed on CIX Mali-G720-Immortalis and RK3588 Mali-G610.
Each common project completed49 actualGPU calls/1835078 exact valid outputs and
7 intentional overflow errors, including maximum262144 elements, reference and
Release execution/tests, native profile, source-deleted replay and standalone.
Each current pinned worker passed20 cases/14actualGPU calls/524321 valid outputs.
CIX also passed11 CPU broker transport/cancellation cases. Returned203 files
were independently verified against current source and exact binary outputs;
see [the bounded proof](../../docs/evidence/portable-opencl-0.121-development.json).
These receipts use compatible compiler0.120/language0.20 and do not substitute
for pending full0.121 compiler/SDK/platform acceptance. Initial preparation's
source/export alias mistake was fixed before hardware execution; its rejection
logs are retained separately.
