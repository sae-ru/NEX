# Development0.120 acceptance and physical stands

NEX is Neural Execution Language. This source carries toolchain0.120.0,
language0.20. The primary checkout0.81/language0.16, all47 original graph
revisions/all16 tables/schema/IDs and normal Git HEAD/index remain preserved.
This development checkpoint does not complete PLAN.md or promote the primary.

The exact frozen browser-task implementation passed Mac full152 CTest groups,
installed SDK31 phases/575 commands and18 actual Chromium/Firefox/WebKit cases.
Five later Markdown clarifications preserved its compiler/runtime/build inputs.
This source additionally reconciles current README/STATUS/PLAN and adds opt-in
RK3588 experiments; those additions are not retrospectively labelled a fresh
full152/compiler acceptance. Core compiler/runtime/TypeScript, grammar,
capability descriptor, manifests and npm lock are unchanged from the accepted
implementation. [Machine-readable scopes](evidence/toolchain-0.120.0-acceptance.json).

| Host | Verified scope |
|---|---|
| Astra1.7 x86-64 VM | Native compiler built from1041 verified source files; CPU reference/Debug/Release,16 events with overlapping threads, balanced managed memory, source-deleted replay, standalone. Composite13 scoped CLI groups:10 pristine groups,4 exact packaging cases in3 groups completed with explicit existing conda notices, one harness-only old Python retry retained. Actual LLDB/NEX-DAP, offline production web/replay. No full152 on Astra. |
| Debian12 ARM64/CIX P1 | Private SDK, native target SQLite/OpenSSL/FFI/apps.12 pristine scoped CLI groups; CPU/profile/replay/standalone and offline production web/replay. Fixed fixture30 actual Mali-G720-Immortalis GPU calls/30720 checked bytes and20 exclusive ZhouyiExecutionProvider NPU calls/120 values, with CPU EP fallback disabled and20 original provider profiles independently checked. A retained harness directory-glob error has a two-execution continuation. No actual browser engines/LLDB/full152 on CIX. |
| Ubuntu22.04 ARM64/Orange Pi5 Pro RK3588S | CPU/profile/replay/standalone and offline production web/replay. Composite12 CLI groups:10 pristine and2 exact static/shared packaging retests after adding private patchelf. Private SDK selects the installed complete GCC11; the incomplete system GCC12 is unchanged. Fixed OpenCL30 actual Mali-G610 calls/30720 exact bytes via pinned child worker, preserving parent JSON. RKNN NPU has a separate exact numerical acceptance and retained initial failures described below. |

Canonical CPU and web example revisions agree on all three hosts. Returned
archives have independent local name/type/size/mode/SHA verification:
Astra46 files, CIX117 files, initial RK3588 receipt200 files. The original
1041-source names/modes/hashes, previous SDKs/graphs and system settings remain.
These counts describe bounded receipts, not full platform certification.

RK3588 GPU vendor startup writes to stdout. An in-process adapter computed
correct values but broke machine JSON; a separate pinned worker now captures
vendor stdout/stderr privately and sends bounded binary result frames. Do not
strip arbitrary prefixes from host JSON or redirect the whole application's
stdout. The original failure is retained.

Initial RKNN tests returned stale zeros/sentinels despite successful APIs.
The unmodified official example at upstream commit
`2c723177a94fac65cbc036d722907ddbc91980cf` passed all3 shapes on installed2.3.0
and private2.5.0. Avoiding CPU initialization of the cached output DMA mapping
fixed the original exact3-matrix oracle/640 values. No driver, SSH or installed
runtime change was required. NEX reference/nativeDebugRelease/tests/profile,
source-deleted replay and standalone then passed30 RKNN calls/6400 values;
separate tracing recorded3 successful submit ioctls on actual RKNPU device FDs
from an actual NEX run. This is direct RKNN int8 matmul, without CPU fallback.

The first per-scalar-list FFI adapter exceeded the normal4096-reference quota at
maximum shape. Its boundary failure is retained. The current adapter transports
immutable bytes in bulk, with a NEX list convenience wrapper; it does not raise
FFI host limits. The extra NEX pack/unpack loops exceeded the default1M
interpreter budget; the explicit reference test uses bounded16M steps and records
actual consumption. Original limit failures are retained. The current optimized
wrapper passes the full fixture:30 actual calls/6400 checked values,993161
reference steps, normal Debug/Release tests, profile/replay/standalone. The same
bytes ABI/worker with its earlier equivalent wrapper passed min/max shapes and
full int8 extrema:6 NEX calls/16448 exact values in reference/nativeRelease.
The current packing function independently passes all256 int8 values, bounds
and immutable-input checks on native/TypeScript/reference. The supplemental138
receipt files are independently name/type/size/mode/SHA verified locally.
This fixture is not a stable generic compute API, zero-copy device tensor type,
source-task dispatch, persistent worker pool or arbitrary model/kernel compiler.

A CPU-only regression of the production NPU broker passes10 controlled-child
cases: exact/structured replies, malformed/truncated/oversized/status/length
frames, abnormal exit/signal and host limit cancellation. Each verifies physical
child reap and private-file cleanup. It does not establish all vendor timeout,
source-task or device resource lifetime behavior.

Activate the isolated SDK in one shell on the relevant host:

```sh
. /tmp/nex-120-stand-astra-v1/activate.sh
# or /tmp/nex-120-stand-cix-v1/activate.sh
# or /tmp/nex-120-stand-rk3588-v1/activate.sh
nex doctor --json
nex describe --json
```

These are temporary validation installations; deleting `/tmp` requires restoring
archives. On Astra, application packaging requires explicit existing conda
notices through `--notices /opt/nex/packaging-notices.json`. Node/npm/cache and
additional native test tools are installed only in private test prefixes.

See the [RK3588 fixture instructions](../experiments/rk3588/README.md) for
explicit grants, dependency provenance and opt-in execution. RKNN SDK headers
and proprietary runtime remain optional operator inputs, outside NEX source.
General compute/resource/task APIs, graphics/mobile/Windows target execution,
broader debugging/profiling, project conversion and multi-model/token quality
work remain open in PLAN.md. Hardware presence or cross-building alone is not
execution support for every device/OS.
