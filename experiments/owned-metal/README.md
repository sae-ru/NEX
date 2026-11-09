# Owned Metal development provider

This macOS experiment connects real Metal compute to NEX language0.28 through
the existing `std/device` API. It provides persistent GPU sessions, immutable
typed buffers, exact U8 Add/Affine kernels, checked overflow and physical GPU
timing. It introduces no source syntax, compiler ABI or graph migration.

Toolchain0.163 installs its preparation and verification tools under
`share/nex/tools/owned-metal`; `nex describe --field device.metal_provider --json`
describes their actual scope. Preparation builds a separate pinned provider
bundle. Matching installed SDK hardware acceptance remains pending. General GPU
code generation, Matmul, Apple NPU and complete Metal SDK acceptance remain
pending. The native API prerequisite is in [../metal](../metal/README.md).

## Prepare and run

Use an actual current macOS SDK installation and Apple's Objective-C++ compiler.
Select new output directories; preparation checks the selected NEX compiler's
resource-parent, task/FFI and executable-member capabilities, checks the source,
and obtains all seven actual FFI signatures before compiling the provider.

```sh
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
NEX_SDK=/absolute/path/to/current/nex-sdk
python3 -B experiments/owned-metal/prepare.py --sdk "$NEX_SDK" \
  --output /absolute/new/metal-project --cxx "$(xcrun --find clang++)"
python3 -B experiments/owned-metal/verify.py --sdk "$NEX_SDK" \
  --project /absolute/new/metal-project --output /absolute/new/metal-hardware
python3 -B experiments/owned-metal/faults.py --sdk "$NEX_SDK" \
  --project /absolute/new/metal-project --output /absolute/new/metal-replies
python3 -B experiments/owned-metal/logs.py --sdk "$NEX_SDK" \
  --project /absolute/new/metal-project --output /absolute/new/metal-logs
```

From an installed SDK, replace `experiments/owned-metal` in the commands with
`$NEX_SDK/share/nex/tools/owned-metal`.

`prepare.py --check-sdk` performs source/signature discovery without building a
provider, selecting an Apple SDK or initializing a GPU, including on non-macOS
64-bit hosts. Run `check_sources.py --sdk ... --project ... --output ...` after
that preparation to check all27 scenario sources and the missing-effect
rejection with the selected compiler. The default ordinal is0; `--index 0..63` selects
an available Metal device. Unavailable devices return an error. The bundle pins
the module, worker, exported signatures and notices. Metal and the selected
Apple SDK remain external system dependencies.

## Ownership and observable behavior

Genuine `Buffer` resources retain their `Session` as a physical parent. Closing
a context prevents new dispatches while existing tensors can still be read.
Each session has one worker and serialized command admission. A bounded private
socket on descriptor3 carries versioned frames; worker stdout/stderr are drained
separately and cannot become an application result. Logs retain bounded first
and last segments while allowing the driver to produce more diagnostics.

Metal commands retain their inputs until physical completion. Once admitted,
task cancellation becomes sticky in the host call: the provider still waits for
the GPU and receives the exact output identity needed for unpublished cleanup.
A controlled shared-event wait exercises cancellation and deadlines while a
real command is pending. Unproven completion retains resource capacity; it is
never reported as a completed fence. Completed command status4 and exactly one
finished completion handler are required before publishing a tensor. Registry
IDs and native Metal statuses are carried as Metal values, with a distinct
protocol identity from the OpenCL provider.

Overflow is checked on the GPU and rejected before the output becomes a NEX
buffer. A CPU oracle verifies test results; it does not supply GPU output.
CPU execution happens only when explicitly selected or when the request permits
fallback for unavailable/unsupported placement. Overflow and protocol errors
are preserved even when CPU fallback was allowed. The module is trusted native
code selected by the operator through an explicit foreign-host configuration.

The hardware suite preserves fifteen native/reference scenario pairs, including
all octets, scale boundaries,262144 elements, last-element overflow, session
recovery, parent lifetime, cross-session rejection, fallback, cancellation and
deadline settlement. Twelve malformed-reply cases check worker drainage and
lost-session errors. Three log cases check9MiB cache/stdout output without
imposing a process file-size limit. Their JSON reports record actual results;
source generation alone establishes no execution or SDK acceptance.
