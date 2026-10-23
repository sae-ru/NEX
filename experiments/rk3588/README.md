# RK3588: explicit experimental accelerator fixtures

These Linux ARM64 **trusted native FFI** fixtures are opt-in, with pinned
module/worker bundles. They do not add language syntax, a stable compute API,
source task dispatch, asynchronous device resources or CPU fallback. Large
applications must not treat these fixed tests as a complete accelerator stack.

The GPU fixture executes byte affine `3*a+b` on an actual OpenCL GPU, with
explicit bounds and exact NEX result checks. The NPU fixture performs row-major
signed int8 matmul with int32 output through RKNN. Its checked bounds are
`1 <= M <= 32`, `K,N` multiples of32 within32..128; source values must be in
-128..127. Products and exact accumulations fit int32. NEX receives immutable
`list<i64>` values with exact sign extension. A convenience NEX wrapper packs
inputs as signed int8 bytes and decodes int32 little-endian output; the C FFI
transports immutable bytes in bulk. It does not create one handle per scalar or
raise the standard4096-reference/65536-operation limits. The retained initial
list-per-scalar prototype failed at maximum shape with `NEX_FFI_LIMIT`; its
original matrices and extrema oracles are preserved in the bytes adapter. Unsupported shapes/ranges fail;
there is no implicit quantization or CPU substitution.

Each callback spawns a pinned child worker from its verified bundle. Only
bounded binary frames cross this boundary. Vendor stdout/stderr is captured in
the private child; parent machine stdout remains strict JSON. The broker polls
the host, drains/reaps the child on failure/cancellation and removes private
files. Current calls are synchronous and serialized; this is not the structured
task/foreign bridge. A 60-second process deadline bounds a stuck vendor call.
Diagnostic data is not a device kernel profiler or total RAM measurement.

## Prepare and explicitly execute

Use the actual0.120 SDK on the target, a complete target C++20 compiler, and
read `nex describe --json` before use. From this source tree:

```sh
python3 experiments/rk3588/prepare.py --sdk /path/to/sdk --backend gpu \
  --output /new/gpu-project --cxx /usr/bin/g++
python3 experiments/rk3588/verify.py --sdk /path/to/sdk --backend gpu \
  --project /new/gpu-project --output /new/gpu-receipts
```

The NPU fixture additionally requires operator-provided official RKNN SDK
headers and their SDK license. These files and the proprietary runtime are
**not included or relicensed in this repository**. Use an SDK grant appropriate
for the compatible Rockchip device. Preparation records dependency hashes;
the child opens the installed `/usr/lib/librknnrt.so`.

```sh
python3 experiments/rk3588/prepare.py --sdk /path/to/sdk --backend npu \
  --vendor-include /private/rknn/include --vendor-license /private/RKNN-SDK-LICENSE \
  --output /new/npu-project --cxx /usr/bin/g++
python3 experiments/rk3588/verify.py --sdk /path/to/sdk --backend npu \
  --project /new/npu-project --output /new/npu-receipts
```

Preparation creates a new project/bundle and checks signatures/grants without
executing the accelerator. Verification explicitly runs reference, native
Debug/Release, tests, profile, source-deleted revision replay and standalone
execution from `/` with SDK resources unavailable. It restores the test source
and retains the raw reports; it does not modify an operator's original project.
The reference check uses an explicit bounded16,000,000-step budget for NEX
pack/unpack and full CPU-oracle loops, recording actual steps used. The default
1,000,000-step failures are retained; native and ordinary FFI limits are unchanged.

On Orange Pi5 Pro/RK3588S, Ubuntu22.04, RKNPU0.9.6 and installed RKNN2.3.0,
CPU-initializing the cached output DMA buffer caused unchanged zeros/sentinel
values despite a successful run. The unmodified pinned upstream example passed.
Leaving the output buffer untouched before the run fixed the original exact
three-matrix oracle without a driver/runtime/configuration change. Preserve
this allocation discipline; never weaken the numerical checks to accept stale
buffers. This observation is specific to the tested device/runtime path.

Pure signed-byte packing, including all256 int8 values and rejected ranges,
is checked with native/TypeScript/reference agreement:

```sh
python3 experiments/rk3588/test_pack.py --sdk /path/to/sdk \
  --output /new/pack-receipts
```

CPU-only transport regressions use controlled children, not fake accelerators:

```sh
python3 experiments/rk3588/test_process.py --sdk /path/to/sdk \
  --output /new/transport-receipts
```

They check exact/structured replies, malformed/truncated/oversized/invalid status
frames, payload length, abnormal exit/signal and host limit cancellation, with
physical child reap and private-file cleanup. They do not establish generic
worker-pool lifetime, source-task cancellation or all vendor timeout paths.

The current standalone worker/broker is Linux ARM64 specific. Actual device
support must be separately tested; the presence of an OpenCL/RKNN library is
not a numerical hardware result. See [current acceptance](../../docs/stand-acceptance-0.120.md).
