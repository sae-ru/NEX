# Owned device resources

Development toolchain0.132 adds `import "std/device.nex" as device;` as an
ordinary library, introduced with language0.23. Query `nex describe --field device --json`.
No syntax, canonical identity, retained-history or migration rule changes.
Matching regression, installed SDK and actual platform acceptance have separate
receipts. The OpenCL adapter is experimental and selected explicitly.

Toolchain0.163 installs the experimental Metal preparer and verification tools
at `tools/owned-metal` below the SDK resources. Query
`nex describe --field device.metal_provider --json`. Native execution requires
macOS. It uses these same public resource types with native Metal registry
IDs, command-buffer completion and shared-event cancellation tests. Its
[physical hardware evidence](evidence/macos-owned-metal-0.162.2-2026-11-09.json)
has a separate scope from installed SDK acceptance. Current kernels remain
exact U8 Add/Affine; general Metal code generation and Apple NPU are pending.
Provider instructions are installed at `tools/owned-metal/README.md`;
checkout instructions are in `experiments/owned-metal/README.md`.
Source-only preparation and all27 scenario checks require no Apple SDK or GPU.

A separate checkout prototype at `experiments/owned-metal-matmul` adds exact
I8×I8→I32 Matmul and a private parent-retaining read cursor. Its
[hardware evidence](evidence/macos-owned-metal-matmul-0.163.0-2026-11-09.json)
covers 57 native/reference pairs, including both I32 endpoints, overflow,
maximum matrices and cross-provider opaque-resource rejection. It is outside
the frozen 0.163 SDK and has distinct eight-function signatures and protocol3.
The installed provider descriptor above continues to cover U8 Add/Affine.

The separate `experiments/metal-codegen` backend generates scalar Metal kernels
from ordinary checked NEX graph functions; its
[three-way numerical record](evidence/macos-scalar-Metal-codegen-0.163.0-2026-11-09.json)
covers i64/bool/unit, control flow, helper calls and source contracts. This code
path is not yet connected to the owned resource/provider API below. Its physical
native harness is a distinct precursor; task cancellation, generated-kernel
resource ownership and installed delivery still need matching integration.

## Source contract

`Session` and `Buffer` are opaque server resources. A trusted pinned C provider
constructs sessions and creates dependent buffers with
`resource_create_with_parents`. Source metadata cannot create native authority.
`Context` contains a Session, checked `compute::Device`, and exact server
upload/dispatch/download callables declaring `!{task,ffi}`. Direct external
leaves keep `!{ffi}`; ordinary task-callable wrappers declare both effects.

`upload(ctx,compute::Tensor)` returns a device Tensor with immutable dtype,
shape, logical device ID, Buffer and download callback. `dispatch(ctx,op,inputs)`
returns another Tensor; `download(tensor)` returns checked row-major host bytes
as `compute::Tensor`. Metadata validates rank1..4, positive dimensions, at most
262144 elements and1MiB. The adapter additionally validates physical session,
dtype and byte count; a matching textual device ID is insufficient.

`close_context` denies new context operations immediately. Existing buffers
retain their genuine physical session and download callback: returning only
a Tensor from a scope or through a channel does not destroy its hidden parent.
`close_tensor` revokes that buffer. Physical storage, capacity and destructor
code remain retained until the last admitted use and device completion settle.
Sibling/foreign authority and ended logical owners cannot be revived.
Resources/callbacks cannot cross wire/JSON/browser boundaries.

`execute(ctx,compute::Request)` preserves the checked compute1 request/response
contract. Explicit CPU requests use the source CPU backend. An explicitly
allowed CPU fallback applies only to unavailable/unsupported placement or
capability, and reports the actual CPU device and reason. Invalid data,
overflow, protocol failure, cancellation and deadlines never become fallback.
Successful dispatch input/output cleanup also runs on error/trap scope exits.

## Prepare an experimental persistent OpenCL provider

From an installed SDK:

```sh
python3 /chosen/sdk/share/nex/tools/owned-opencl/prepare.py \
  --sdk /chosen/sdk --output /new/gpu-project
cd /new/gpu-project
/chosen/sdk/bin/nex eval --foreign foreign.json --json
/chosen/sdk/bin/nex build --profile release --json
# Run the reported executable with --nex-foreign /new/gpu-project/foreign.json.
```

macOS selects the system OpenCL framework. Linux requires an explicit
`--opencl-library /absolute/path/to/libOpenCL.so.1`; `--index 0..63` selects a
GPU ordinal. Preparation compiles the real source template/signatures, module
and worker without initializing the driver. `--check-sdk` checks the actual
source/signatures without compiling native provider images or using hardware.
Output must be a new directory. Preserve its pinned bundle, catalogue and notice.
The SDK preparation tool also works from `experiments/owned-opencl` in a checkout.

Only an actual GPU is accepted; a CPU OpenCL device cannot substitute for it.
One persistent child owns the OpenCL context, queue and immutable buffers for
each Session. The private framed socket carries bounded bytes/IDs, never NEX
values, C call tokens or borrowed source frames. Worker stdout/stderr use a
separate bounded log. The host verifies completed NDRange events before exposing
output. A bundle's optional hashed `executables` members become0500 in its
private snapshot; other files remain0400 and directories0500.

Current kernels are exact U8 Add/Affine(scale0..255), at most262144 elements;
per-element overflow is rejected. I8/I32 upload/readback storage is supported,
but this adapter does not execute Matmul. Upload is also bounded to1044480 bytes
to leave transport envelope headroom. The generic byte-count ceiling remains1MiB.
Session accounting declares the fixed262144-byte device scratch plus host owner;
buffers declare data bytes plus their owner. This is not total driver/process/VM
memory accounting or a claim of GPU speedup.

## Successful replies and session failure

Toolchain0.132.2 validates every successful reply while holding the Session
command lock. Buffer IDs must be the next unique allocation in the pinned
worker protocol. Size, trailing/truncated data, kernel event and profiling
checks complete before buffer metadata is committed or a later command enters.
A malformed reply drains the worker and its actual buffers before a failed
factory returns physical capacity. Later operations report E_DEVICE_LOST;
existing source aliases retain their owners until ordinary cleanup. Known
recoverable compute overflow preserves its existing checked semantics.

`tools/owned-opencl/faults.py` exercises actual GPU upload/dispatch/download and
cleanup with controlled malformed replies, repeated IDs and strict object quotas.
The test-only fault environment variable is not an application/provider API.
Unknown vendor completion still retains resources as described below.

## Cancellation, failure and limits

Before admission, host cancellation can reject a call. After admission, the
host continues consuming the exact physical acknowledgement and retains any
new buffer ID for unpublished cleanup. A cancelled task does not kill a worker
and does not return capacity before the physical operation finishes. Session
destruction follows all child buffer releases and acknowledged queue drainage.

Known failures drain the pinned worker. Its confirmed orderly cleanup can
settle resources; arbitrary process death cannot prove GPU/DMA completion.
Unproven device completion deliberately retains resources and blocks instead
of publishing a false completion fence. Recovery/reset and reliable fault
handling remain open; this experimental adapter is not a fault-tolerant device
service. NPU/model ownership, other operations/dtypes, arbitrary kernels,
concurrent queues and explicit source fence values remain pending.

Generated scope/join fixtures declare their source-error effects for language0.25+;
pre025 fixtures retain their original effects. The device-contract regression
checks every generated normal/error/fault source with the selected compiler
before device execution. Such source checks do not initialize an OpenCL driver
or establish physical GPU acceptance.

`verify.py` requires real GPU execution and native/independent AST agreement.
Its controlled cancellation/deadline cases enqueue a kernel behind a genuine
OpenCL user event before cancelling or timing out, then verify physical
completion and child-before-parent cleanup. Test gate/noise/trace environment
variables are harness instrumentation, not the production device API.

## Bounded driver diagnostics

Toolchain0.132.3 drains child stdout/stderr through a private pipe. A Session
retains bounded first/last diagnostic bytes and an omitted-byte count; the saved
file is at most64KiB. The reader starts before spawn, joins before the owner
is destroyed, and never receives NEX values, call tokens or source authority.
Exit status/signal is recorded without turning arbitrary death into completion.

No process-wide file-size limit is imposed for logging: such a limit also
applies to vendor shader caches and can kill a worker with SIGXFSZ. Existing
operator/OS limits still apply. The native provider remains trusted code; this
is not total driver/process/disk accounting. `logs.py` checks9MiB cache writes
and9MiB stdout independently and together on actual GPU native/reference runs.
Its old-limit mode reproduces the former8MiB restriction in a separate test
process and preserves the unproven-completion state before operator termination.
