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
