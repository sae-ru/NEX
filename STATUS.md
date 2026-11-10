# Bounded CUDA lists — development0.165.0

Public CUDA emission now lowers existing immutable list literals, indexing,
`len`, `push`, `set`, concatenation, equality and nested exact list patterns.
`--list-capacity` selects1..1024 slots (default32). Emission `/3` and value ABI2
record length, capacity and element layout. Active elements are checked and
inactive words must be zero. Invalid indices trap with E_BOUNDS; operations
exceeding the declared device capacity trap with E_LIMIT. CPU semantics,
language0.28, task ABI7, C ABI1 and prior emission versions are retained.

The complete block builds. Three affected groups passed in40.72seconds: the new
list cases execute22 CPU kernel layouts/76 lane outcomes under UBSan and11 NEX
oracles per reference/native Release/TypeScript backend; fixed-value and scalar
checks also passed. The actual generated adapter status parser and source-only
preparation passed. One list example passed actual LLVM22.1 IR and machine
verification to sm_86/PTX7.1, with33-word input/output and no unresolved device
functions. [Development record](docs/evidence/cuda-bounded-lists-0.165.0-2026-11-10.json).
Full regression, physical NVIDIA/Compute Sanitizer and matching immutable SDK
qualification remain deferred to the final milestone under the implementation-first
workflow. General GPU/NPU compilation and the remaining PLAN scope are pending.

# CUDA fixed values — development0.165.0

Public CUDA emission now supports fixed records/concrete generics, enums,
Results, nested constructor matches, bounded device text and checked `as_i64`.
The new `nex.cuda-emission/2` record describes canonical layouts in
`nex.cuda-values/1`; legacy scalar `/1` and source language0.28 are retained.
`?` propagates ordinary errors; `unwrap(err)` retains fatal E_RESULT and its
bounded original diagnostic. Wide columns are batched before FFI without
raising existing call limits. [Implementation/check record](docs/evidence/cuda-fixed-values-0.165.0-2026-11-10.json).

All targets build. Short checks covered16 emitted CPU layouts/74 lane outcomes
under UBSan and eight NEX tests in reference/native Release/TypeScript, plus
provider source preparation and the actual C++ status parser. One Record/Result
example also passed Clang/LLVM IR and machine verification to sm_86/PTX7.1 with
no unresolved device functions. The original LLVM22.1.8 by-value parameter
verifier failure is retained; immutable const-reference helper arguments avoid
it while returned values remain independent copies. Verification stays enabled.
Full regression, NVIDIA/memcheck and immutable SDK qualification remain deferred
under the implementation-first workflow. Dynamic GPU allocation, NPU general
compilation and the remaining original PLAN scope are still pending.

# Public CUDA source backend — development0.165.0

`nex emit --kind cuda` now lowers the checked language0.28 AST directly through
the same implementation as the standalone CUDA developer harness. The public
record `nex.cuda-emission/1` binds exact shader bytes, reachable function hashes,
function maps, compiler/descriptor identities and saved revision. Shared pure
scalar i64/f64/bool/unit, concrete generics, guarded scalar matches, branches,
loops and contracts are supported. Unsupported reachable code is rejected before
overwriting output. Syntax, graph identities, task ABI7 and C ABI1 are unchanged.

Owned CUDA preparation now defaults to this selected compiler, with no separate
emitter or frontend archive. It checks11 FFI exports and exact source/revision
identity. CMake installs its provider tools; the descriptor, language pack,
model-independent prompt, schemas, example and English/Russian entry documents
are updated. The compiler build identity now includes private source headers.
All native targets build; only the two affected CUDA/Metal source-command groups
(13 methods) were checked. [Current integration record](docs/evidence/public-CUDA-source-0.165.0-2026-11-10.json). Complete regression, current NVIDIA owned-provider
acceptance and a newly qualified immutable SDK remain deferred gates. Earlier
standalone f64/IR/PTX and32-kernel hardware records retain their original scope.

# CUDA typed transport and returned-stand results — 2026-11-10

The experimental generated CUDA provider now transports finite f64 through11
checked exports, bounded1024-value calls and32768-value columns. Actual reference,
native Debug and native Release controls passed nine codec/fatal processes,
including exact bits, zero normalization, malformed input rejection and original
E_FLOAT bypass of source catch/finally. Standard C-call limits are unchanged.
Five roots/55 signatures,96 unavailable-driver calls and15 parent source cases
passed. [Host evidence](docs/evidence/owned-cuda-f64-host-0.165.0-2026-11-10.json).
The new11-export provider has no NVIDIA hardware qualification yet.

An earlier pinned checked-AST CUDA corpus passed actual NVRTC12.1 and RTX3090:
32 generated kernels,186 checked lane outcomes,107 allocations/frees, physical
completion, unchanged inputs and untouched excess lanes. Its separate Python
Compute Sanitizer failed to attach before any CUDA allocation/launch and was
retired at its original1800s observer limit. Both outcomes are retained in the
[hardware record](docs/evidence/windows-checked-AST-CUDA-physical-0.165.0-2026-11-10.json).
This qualifies the named integer/bool/unit corpus, not f64, owned integration,
memcheck, a complete SDK or release.

Development now batches features into functional milestones. Incremental work
uses builds and short affected-behavior checks; broad regression/platform/device
suites run at milestone and release gates. The newly started101-group Windows
continuation was stopped at the user's request; prior reports remain intact.

# RK3588 current0.165 and checked-AST CUDA experiment — 2026-11-10

[Current RK3588 evidence](docs/evidence/rk3588-current-GPU-NPU-0.165.0-2026-11-10.json)
now covers source2172b35, all targets, eight original selected groups plus two
unchanged ELF groups after private producer/probe dependency packaging correction,
and ordinary installed source preparation. Its common OpenCL fixture passed49
GPU calls/1,835,078 valid values and7 expected overflow rejections; the worker
suite added14 GPU calls/524,321 values on Mali-G610. RKNN passed30 physical NPU
calls/6400 values with actual RKNPU descriptors and CPU fallback disabled.
Replay, standalone with SDK resources unavailable and managed cleanup passed.
The original failed ELF invocation and first incomplete private packaging attempt
remain retained. Full304 and portable SDK qualification remain separate.

The [independent CUDA AST emitter](experiments/cuda-codegen/README.md) compiles
against the existing frontend without changing the public compiler or grammar.
Its source controls passed16 fixtures,32 layouts and186 lane results under host
UBSan plus reference/native/TypeScript agreement and7 rejected programs. The
initial metadata check caught a BLAKE3/SHA256 field error; SHA256 was corrected
and the original failed control retained. GPU/NVRTC and Compute Sanitizer checks
are separately queued on Windows after existing jobs retire. No physical CUDA
or generated owned-provider/SDK acceptance is claimed by those CPU controls.
All original language/platform/mobile/UI/Studio/conversion/LLM requirements remain.

# Public checked scalar Metal emission — development0.165.0

The [installed-tool source and current SDK candidate record](docs/evidence/macos-installed-Metal-full302-SDK-candidate-0.165.0-2026-11-10.json)
adds all302 unfiltered Mac groups for `0abc5d7`, with no failures or skips.
Current `53634a5` has identical production C++/CMake/pack/grammar and separately
passed nine packaging/discovery/HTTP delta groups plus six public debug-builder
controls. Its official single-install SDK candidate passed move/restore, doctor
and both inventories; all13 owned Metal tools and11 current entry documents
match the source. New immutable SDK workflows and physical Metal acceptance
remain pending. This does not claim an unfiltered `53634a5` invocation.

The earlier [`61fbd21` immutable macOS SDK baseline](docs/evidence/macos-baseline-SDK-82-184-0.165.0-2026-11-10.json)
passed 82 maintained phases, 184 additional cases and 4000 C++ host calls with
4000 cleanup checks. Python 3.10/3.14 installations were moved/restored, read-only,
and subject to actual source/dependency/opposite-SDK read denials. Its exact
archive is pinned independently; six post stages and the later public-owned
Metal tools' matching immutable SDK acceptance remain separate.

The C++ compiler now implements `nex emit --kind metal`, using its checked AST
and only reachable shared pure scalar functions. It preserves checked integer
operations, source evaluation order and lowered contracts, supplies function
line mappings and a versioned JSON record, and initializes no device driver.
`nex describe --field gpu_codegen --json` and `nex guide --kind gpu --json`
describe the exact subset and rejected programs. Language0.28, graph identities,
task ABI7 and C ABI major1 remain unchanged; no migration is needed.

The [scoped acceptance](docs/evidence/macos-public-Metal-emission-0.165.0-2026-11-10.json)
passed all native targets, six CLI tests,86 schema documents/eight actual
artifacts/37 rejected mutations and20 reference/native Debug/Release/TypeScript/
Metal cases. Both input layouts execute on Apple M5 Max:48 physical dispatches,
including eight boundary dispatches, plus nine rejected host inputs. The exact
61fbd21/2136-file snapshot has since passed
[all302 macOS groups](docs/evidence/macos-public-Metal-full302-0.165.0-2026-11-10.json)
and [all304 Fedora groups plus ordinary installed smoke](docs/evidence/fedora-public-Metal-full304-0.165.0-2026-11-10.json)
in unfiltered invocations, without failures or skips. These results retain that
snapshot's identity; they do not qualify later fixture/provider changes.
Complete matching portable SDK delivery remains pending. Earlier experimental
Python/typed-graph and0.164 SDK results retain their original pins. Installed owned
dispatch, broader types/backends, GPU debugging/profiling and the remaining
original roadmap are still required.

The checkout [public-emission owned provider](docs/evidence/macos-public-owned-Metal-0.165.0-2026-11-10.json)
now prepares its shader through the actual `nex emit --kind metal` CLI, retaining
compiler/descriptor identity, canonical hashes, source maps and shader SHA256.
Nine source checks passed on Mac and Windows;96 reference/native pairs passed
on Apple M5 Max with230 physical GPU kernels over24 prepared providers.
Numerics, hidden parents, cancellation/deadlines, original fatal codes, malformed
replies/progress and bounded diagnostic capture retain their existing checks.
The numerical/fatal runners also preserve the name of a symlinked C++ driver.
Compiler/runtime C++, language0.28, ABI and graph history are unchanged.
The SDK installation now includes this provider's preparation/verification tools
and adjacent native sources; `gpu_codegen.owned_provider` advertises their paths,
source-only check and required explicit foreign catalogue. Matching complete
immutable SDK qualification, GPU operation debugging/profiling and broader
GPU/NPU support remain pending.

The [installed-tool follow-up](docs/evidence/macos-installed-public-Metal-tools-0.165.0-2026-11-10.json)
passed all targets and six relevant groups. All13 tool files were installed
unchanged; source-only and native provider preparation passed with checkout
reads denied. The installed verifier then passed15 reference/native pairs and
24 physical Metal kernels on Apple M5 Max, retaining resource settlement and
cleanup checks and the exact ordinary SDK inventory. Full regression of this
follow-up and complete matching immutable SDK qualification remain pending.

The same0.165 source passed [all-target Windows compilation, seven selected
CTest groups,35 physical CUDA cases and36 Compute Sanitizer cases](docs/evidence/windows-current-source-CUDA-0.165.0-2026-11-10.json)
through its ordinary development installation on RTX3090. The source/compiler
and raw records are pinned independently; full current Windows regression and
portable SDK qualification remain pending.

The later [2172b35 Windows follow-up](docs/evidence/windows-latest-build-CUDA-0.165.0-2026-11-10.json)
includes the installed public Metal tools and corrected HTTP fixtures. It passed
all targets, eleven selected groups, 35 physical CUDA cases and 36 Compute
Sanitizer cases on RTX 3090 with the original 2000 ms runtime deadline. Its
ordinary installation includes all 13 owned Metal tool files and passed source-only
preparation without executing a GPU. Full Windows regression, positive IPv6 and
complete portable SDK qualification remain pending; earlier snapshots retain
their original evidence.

The frozen4490655/0.164 source now passed [all303 Fedora groups and ordinary installed smoke](docs/evidence/fedora-package-notices-full303-0.164.0-2026-11-10.json),
with no failures or skips. The separate frozen1681802 Windows snapshot passed
[39 of40 debug/profile groups](docs/evidence/windows-combined-debugger-39plus1-0.164.0-2026-11-10.json)
with the combined pipe/stdio LLDB. The historical modular HTTP fixture still
times out during its first pure-static O0 recover session. Original results
and individual budgets are preserved; complete Windows acceptance is pending.

A [current0.165 phase trace and same-PE regression](docs/evidence/windows-HTTP-debug-startup-0.165.0-2026-11-10.json)
identified a fixture startup race: the client exhausted its30-second readiness
budget before a cold LLDB launch reached the server listener. The fixture now
stops at `main` after loader startup, starts clients and resumes through the
existing primary-listener helper. The exact failing current PE passed all
original session assertions after a deliberate31-second hold before clients.
The original failures and unchanged deadlines are retained. The complete fixed
Windows HTTP group remains pending; compiler/runtime,
language, ABI and debugger-helper code are unchanged.
The corrected fixture separately passed
[all38 macOS HTTP sessions and38 offline captures](docs/evidence/macos-HTTP-debug38-0.165.0-2026-11-10.json)
with the same frozen0.165 compiler. Each session retained absent source files,
logical stacks/watches/steps, request identity and terminal cleanup checks.

That full current Windows replay subsequently passed
[37 original HTTP debugging sessions](docs/evidence/windows-HTTP37-Defender-0.165.0-2026-11-10.json).
The final mixed/O2/TLS case still exhausted its client clock during native module
initialization after `main`. A separate listener-gated diagnostic reached HTTPS
health200 and an inferior stop, then image validation failed with WinError225:
Defender quarantined the test server under `Behavior:Win32/DefenseEvasion.A!ml`.
The original timeout and Defender events are retained. The listener-gate change
is still external/unaccepted; complete Windows HTTP and SDK gates remain open.

The subsequent [callback/census fixture correction](docs/evidence/HTTP-debug-callback-census-0.165.0-2026-11-10.json)
passed all38 original HTTP debug sessions and38 offline captures on both Windows
and macOS. Clients start after the listener is ready; task-memory inspection
waits for actual marker-callback selection or error, avoiding transient
auto-continuing stops. Cleanup uses the same baseline/final observations for
its verdict and telemetry, with exact Windows handle-set equality. The tested
driver and C++ host body are now in their source files. All original numeric
budgets and source/stack/watch/step/request/cleanup assertions remain.
No production runtime, debugger helper or security setting changed. Complete
Windows source regression and portable SDK qualification remain pending.

The [exact979ef54 CIX ARM64 cohort](docs/evidence/cix-current-source-GPU-NPU-0.165.0-2026-11-10.json)
passed all targets, six relevant groups and36 physical GPU/26 NPU calls through
an ordinary development installation. Reference, Debug/Release, test/profile/
replay and source-deleted standalone paths retain their checks. Typed device
payloads survive suspended guards/catch/finally. Every NPU placement profile
uses ZhouyiExecutionProvider with CPU fallback disabled; managed cleanup passed.
Full304 source regression is running separately. Portable delivery, later
Metal-tool/HTTP-fixture changes and other devices retain separate qualification.

# Native Windows fixture paths — development0.164.0

The current Windows restricted source run completed292 of296 groups; its four
failed groups and all original diagnostics remain retained. Two native failures
stopped while constructing an AF_UNIX test fixture under a long temporary path,
before their nonregular-file rejection checks ran. The test helper now creates
a real endpoint in a new private short directory on the same volume, closes it
and moves its reparse point to the requested path. It changes no process cwd,
existing ACL, network setting, product runtime or source-language semantics.

The [independent correction record](docs/evidence/windows-native-file-fixture-0.164.0-2026-11-09.json)
pins an isolated2108-file Windows derived source, the unchanged NEX compiler,
all four affected native groups and four actual Python fixture cases, including
the native resource suite under a long Unicode temporary parent. All five CTest
groups passed without skips. Mac all-target compilation and the same four native
groups also passed. The original cache-relocation setup failure is retained.
The other two original failures involve debugging; their40-group replay uses
the combined LLDB cohort in bounded batches. Full current regression, positive
Windows IPv6 and complete installed SDK qualification remain separate gates.

# Explicit fatal C API — development0.164.0

The new append-only `raise_trap` slot copies bounded diagnostic packets from
trusted C providers. Original host control remains sticky; source catches and
user finalizers cannot consume a runtime trap. Partial-factory/owned cleanup,
all previous table prefixes, language0.28, taskABI7 and graph histories retain
their contracts. See [the API contract](docs/ffi-design.md#explicit-fatal-diagnostics-0164).
The generated Metal `apply` path now uses it after `try_apply` settles physical
work and closes temporary resources. The [scoped record](docs/evidence/macos-explicit-FFI-traps-0.164.0-2026-11-09.json)
passed all targets, nine core groups and21 native/reference Metal pairs with36
physical GPU events. Three original CPU trap codes agree in reference/Debug/Release;
GPU step limits and cancellation/deadline precedence over overflow retain their
separate expectations. Both valid and failed queued commands settle before
parent release; failed outputs are not published. The original failed trace
expectation is retained. The exact 0.164 runtime source subsequently passed
[all 301 macOS groups](docs/evidence/macos-current-source-full301-0.164.0-2026-11-09.json)
in one unfiltered invocation, with unchanged deadlines and preserved primary
source/graph. Matching SDK and remaining platform qualification remain pending;
later Windows builder and experimental provider changes have separate records.

The subsequent [source package/SDK checker correction](docs/evidence/source-package-notices-parent-prefix-0.164.0-2026-11-09.json)
forwards explicit private-runtime notices through eight additional package
fixtures. Nine groups passed across the retained initial run and targeted
recovery; pure web package tasks retain their original no-native-notice path.
The same correction updates the SDK checker from37 to43 dependent-resource
checks for0.164, requiring six distinct C11/C++20 executions against the frozen
304-byte parent-table prefix. The actual43-case installed report passed; its
old aggregate checker rejected it. That failed immutable archive remains
unaccepted. The corrected validator passed108 unit tests. Its exact4490655
source subsequently passed [all301 macOS groups](docs/evidence/macos-package-notices-source-full301-0.164.0-2026-11-09.json)
in one unfiltered invocation, with no failures or skips and the original deadlines.
An independent archive retains its all-target build and registry/JUnit evidence.
Matching complete immutable SDK qualification remains required; this source
result does not accept an installed SDK or the other platforms.

The latest4490655 source also passed a [native RK3588 CPU and TypeScript smoke check](docs/evidence/rk-current-CPU-TypeScript-0.164.0-2026-11-09.json).
Reference, native Debug and Release agree on the constraints example; its generic
Unicode test passes natively and under Node22.22.3/TypeScript7.0.2. This is an
actual Jammy ARM64 build with LLVM22.1.8 and explicit GCC11 headers. The full
all-target/303-group run, GPU/NPU and portable SDK remain separate. A private
Z3 5.3.1 cohort passed its own C++20 probe after retaining two preparation
failures; NEX still uses its original4.8.12 cohort in this smoke record.

The separate [generated-protocol corpus](docs/evidence/macos-generated-Metal-protocol-0.164.0-2026-11-09.json)
now passed16 native/reference pairs over14 corrupt reply payloads, failed-session
reuse refusal and direct protocol-trap forwarding. Three log/cache pairs kept
9MiB worker files and diagnostic stdout separate from the framed protocol,
with capture bounded to64KiB. These19 pairs executed22 physical GPU kernels.
The ordinary0.164 SDK and pinned prepared provider remained unchanged during
that earlier corpus. The [subsequent transport/error correction](docs/evidence/macos-generated-Metal-transport-0.164.0-2026-11-09.json)
rejects malformed frame/progress/error packets before the host API. It reproduced
the original malformed-UTF-8 `E_FFI` outcome, then passed34 new pairs including
valid Unicode at2048 bytes and cancellation/deadline over corrupt pending-GPU
progress. Repeating all preceding corpora on the corrected provider passed74
pairs and130 physical GPU kernels. The SDK inventory stayed unchanged; the new
provider was built separately with Apple Clang. Unknown-completion recovery,
general GPU integration and complete installed SDK delivery remain required.

The earlier frozen0.163 Metal-tool source now passed
[all301 groups in one unfiltered invocation](docs/evidence/macos-Metal-tools-full301-0.163.0-2026-11-09.json).
Its independent receipt rehashes the exact2070 sources and compiler and retains
raw JUnit/build evidence. That result excludes the new0.164 trap suffix; its
corresponding SDK stages remain separate.

# Earlier owned generated Metal task path — 2026-11-09

The [persistent generated provider](experiments/owned-metal-codegen/README.md)
executes ordinary generated scalar functions through actual NEX task/FFI
Session/Buffer resources. Its [38 native/reference pairs](docs/evidence/macos-owned-scalar-Metal-0.163.0-2026-11-09.json)
passed 122 physical GPU events: 14 lifetime/control cases, 22 numerical/limit
scenarios and 2 cross-provider rejection cases. Hidden Session/Buffer parents
survive task returns/channels/logical close, admitted reads retain parents,
and cancellation/deadline drain a genuinely queued gated command. Eight maximum
columns total 2 MiB without increasing the per-call FFI copy budget. All 22 scalar
MSL function prefixes match their prior physical-stage bytes.

This is outside the frozen0.163 SDK. `try_apply` retains numeric errors inside
an explicit Result; that recorded `apply` had the ordinary E_RESULT unwrap contract.
The later0.164 bridge and generated-protocol/log corpus are described above.
Public CLI, source diagnostics/debug/profile and coherent installed delivery
remain pending.
The independent raw archive retains the original native-limit mismatch and
corrects an overbroad reporting label without changing executed checks.

# Earlier scalar Metal code generation precursor — 2026-11-09

The separate [scalar backend](experiments/metal-codegen/README.md) emits MSL from
the selected compiler's actual checked language0.28 graph. It preserves checked
i64 arithmetic, operand/argument order, short-circuiting, branches, loops,
helper/concrete generic calls and lowered source contracts. No second parser or
handwritten per-function shader is used. [20 three-way cases](docs/evidence/macos-scalar-Metal-codegen-0.163.0-2026-11-09.json)
passed against actual NEX reference/native execution, with1799 GPU lanes checked
against exact integer/known-result oracles. Fourteen compiler-accepted programs
are explicitly rejected by the narrower GPU backend. Five more physical GPU
dispatches check limits/canonical inputs, including32768 lanes. All25 current
kernel events verify status4, one completion handler and drained buffers.

This direct native-harness record remains outside the frozen0.163 SDK and
separate from the new owned task path above. Public CLI/discovery, debug/profile,
installed delivery and broader GPU/NPU code generation remain pending.

# Development0.163.0 — installed Metal tools

Language0.28/taskABI7 and graph identities are unchanged. This candidate installs
the fixed-kernel Metal provider and native prerequisite tools, advertises the
experimental provider through `nex describe`, and checks its seven FFI signatures
and27 scenario sources plus the missing-effect rejection without a driver.
Source checking is available on the supported64-bit hosts; compiling and running
the native worker requires macOS. The earlier separate0.162.2 experiment passed
[30 native/reference pairs on Apple M5 Max](docs/evidence/macos-owned-metal-0.162.2-2026-11-09.json).
The matching frozen source passed all301 groups as recorded above. Moved/restored
SDK, Metal hardware and complete platform acceptance remain pending. Earlier
accepted archives retain their exact scope.
The [private float-header correction](docs/macos-float-header-compatibility.md)
addresses the actual packaged-Clang22 Metal compilation failure without changing
source LLVM installations or redefining numeric constants.
The [scoped development receipt](docs/evidence/macos-Metal-SDK-tools-0.163.0-2026-11-09.json)
records the actual all-target build, changed groups, installed source checks and
six physical GPU events through the corrected-header prerequisite.

# Separate exact Metal Matmul prototype — 2026-11-09

The checkout [Matmul provider](experiments/owned-metal-matmul/README.md) executes
row-major I8×I8→I32 with exact final overflow checking. A private parent-retaining
read cursor delivers the full 1 MiB result through 262144-byte chunks within the
original FFI budget. [57 native/reference pairs](docs/evidence/macos-owned-metal-matmul-0.163.0-2026-11-09.json)
passed on Apple M5 Max with 88 physical GPU kernel events, 52 accepted sources
and one missing-effect rejection. Both actual providers rejected foreign opaque
buffers before pointer use. The independent archive rechecks 50 cursor lifetimes
and preserves the earlier full-result FFI-budget failure. This is outside the
frozen 0.163 SDK candidate; installation and general GPU/NPU remain pending.

The earlier [function-definition source snapshot passed all 301 macOS groups](docs/evidence/macos-function-def-full301-0.162.2-2026-11-09.json)
in one complete run after the retained power interruption. The exact fixed 0.163
source full run and corresponding SDK pipeline are still running.

# Earlier0.162.2 qualification — 2026-11-09

Language0.28/taskABI7 are unchanged. The current strict-LLDB-command-capture
[e63 source snapshot passed all301 macOS groups](docs/evidence/macos-e63-source-full301-0.162.2-2026-11-09.json).
Its [immutable archive passed moved/restored and all subsequent SDK gates](docs/evidence/macos-e63-sdk-complete-0.162.2-2026-11-09.json).
Fedora12281 passed full303 and ordinary installed smoke
with its separately pinned source/compiler.

The [native Bookworm solver cohort](docs/evidence/cix-native-Z3-5.3.1-2026-11-09.json)
built all892 Z3 steps and the matching NEX passed all11 original bounded-proof
methods with unchanged limits. Full303 and the portable Linux SDK remain pending.
The earlier4.8.12 proof failure and dual-SONAME linker warning are retained.
Windows current SDK/regression and matching physical-device qualification remain
separate gates. General devices, Metal/Apple NPU, mobile/UI, Studio, conversion,
real multi-model costs and every unfinished original PLAN requirement remain open.

Earlier entries below retain their own source/archive identities and do not
accept later source or SDKs.

# Development0.162.2 — preserve GCC floating environment

On physical CIX ARM64 with optimized GCC12, float-to-integer conversion was
executed after the saved caller environment had been restored. FCVTZS then
leaked FE_INEXACT into that caller. Materializing the converted integer inside
the guard fixes both the inline helper and the public owned-value wrapper.
The [runtime record](docs/evidence/floating-environment-gcc12-0.162.2-2026-11-08.json)
includes the original failure and the separately rebuilt passing probe with
four rounding modes and three worker threads. Source language0.28, task ABI7
and graph identities are unchanged; native artifacts need rebuilding.

Windows SDK assembly also requires the selected OpenSSL cohort's openssl.cnf.
The private build recipe installs it through upstream install_ssldirs. The
source checks passed on Python3.10/3.14; a separate Windows CLI copy reproduced
the missing-config failure and created/verified certificates after relocation
with the upstream configuration. Combined full regression and matching SDK
delivery are pending. Earlier receipts below retain their original versions.

# Development0.162.1 — selected ELF runtime search

The current working source adds one SONAME-aware directory planner for both
native link paths, with explicit missing-alias/conflict diagnostics and no
language0.28/ABI7 or graph-format change. The [development record](docs/evidence/native-runtime-search-0.162.1-2026-11-08.json)
records Mac full301 and Linux native/package execution plus exact union303.
The failed Linux299/4 invocation remains failed; all5 groups affected by the
notice-argument correction passed on unchanged source/compiler/dependencies.
Windows all-target build, ordinary installation and12 moved/restored C11/CXX20
history pairs passed. Complete matching SDK delivery and current physical
platform acceptance remain pending. Historical0.162.0 receipts keep their scope.

# Qualified macOS SDK0.162 / source language0.28

The [current delivery record](docs/releases/0.162.0.json) accepts the immutable
Mac ARM64 archive with300 matching source groups,82 installed phases,180 extra
cases,4000 C++ host calls/cleanup checks,150 browsers,18 CLI scenarios,21 OpenCL
native/reference cases and47 physical kernels. Q1–Q5 passed with actual9900/0/1
LLVM calls, preserved10000 IDs and source-deleted replay. All85 schema documents,
12 actual artifacts and36 rejected mutations passed. Packaged-Clang controls
detected intentional leak, overflow and race faults; generated provider IR is not
instrumented. The non-isolated numerical comparison retains its single-workload scope.

The qualified SDK source is0.162.0/lang0.28. Archive resources remain4fb860e; subsequent Windows
fixtures, source-only SDK tests and documentation keep their own source identities.
This source publication does not upload a binary release; published0.159 remains
historical. Fresh Windows source built/installed and passed local smoke; complete
current Windows/Linux SDK and positive Windows IPv6 remain separate. Fedora45's
full289/300 attempt remains failed. Mobile/UI/Studio/conversion/generalGPU/NPU,
real multi-LLM costs and the remaining original PLAN are still open.

Earlier entries below are historical and do not override this record.

# Workload fixture ownership — source development 0.162 / language 0.28

Windows test cleanup now authenticates the held process handle against the
test's exact unnamed Job and its recorded creation FILETIME. PID-only records
cannot authorize termination. The Job has no kill-on-close policy, so production
supervision remains independently observable. The [scoped record](docs/evidence/windows-workload-ownership-2026-11-06.json)
includes all nine server-workload cases, all four task-workload cases, actual
outside-Job/stale-birth controls and both corresponding Fedora POSIX cases.
Original timeouts are unchanged. Failed setup/combined invocations are retained;
the cause of the initial server fixture startup delay is still unresolved.
Current full regression and installed SDK qualification remain open. These
checks do not complete the original PLAN or update the published 0.159 archive.

# Integrated source development0.160

Native entry ABI discovery, the independently pinned Linux debugger and current
quality runners are combined here. The parent source289b078 passed Linux298;
its Mac297/298 result retains the diagnosed DAP output-category fixture failure.
The fixed fixture passed an exact original-binary replay and focused groups.
The finite Q1–Q5 chain passed with current0.28 and actual9900/0/1 native calls.
These parent/source receipts do not accept this combined tree or updated SDK.
Fresh complete regression and installed delivery are required. Public SDK159
and every remaining original PLAN requirement remain unchanged.

# Quality-runner source follow-up for language0.28

The opt-in checked-core helper accepts explicit0.28 while preserving its old
algorithms and0.18 default. Short actual Mac/Linux runs passed backend agreement
and resource-accounting checks; these are operational checks, not throughput
results. Q1–Q5 source runners select a bounded0.21/0.28 compiler response and
create fresh projects. Current task scope/wait callers explicitly declare throw.
The full finite Q1–Q5 chain passed against the immutable0.160 SDK:100 modules,
10000 declarations, actual native cold/warm/edit calls9900/0/1, preserved IDs and
source-deleted replay. Three physical fence modes passed; packaged LeakSanitizer
and ThreadSanitizer detected their intentional control faults. Generated provider
LLVM IR is not instrumented. The [source receipt](docs/evidence/quality-language-0.28-source.json)
keeps failed attempts and limits. Updated helpers' installed delivery and matching
regression remain separate gates. Published archives remain unchanged;
no original pending project requirement is removed.

# Linux debugger and UTF-8 follow-up — source development 0.160

The Linux recipe independently pins LLDB23.1.5 while compilation remains on
LLVM/MLIR22.1.8. Four preserved Linux binaries passed their original debugger
scenarios with the new debugger. The reader explicitly decodes UTF-8 manifests
and relocation receipts. Actual Mac tests cover Unicode paths, invalid UTF-8
and Unicode watch contents with a C locale. Linux retained-compiler checks
passed three debugger groups and a separate complete watch group; an earlier
`lost connection` failure is retained with its cause unresolved. See the
[scoped record](docs/evidence/linux-debugger-0.160.0.json).

The preceding Mac full298 run completed with296 passes and two timeouts during
host sleep. Both groups passed a separate unchanged repeat; this does not accept
the full run. Fresh full regression, current Linux/Windows delivery and portable
SDK0.160 qualification remain open. The public0.159 archive remains unchanged.

# Native entry ABI — source development 0.160

Native library builds expose bounded `native_entry_abi` JSON from verified LLVM,
including hidden source-error outputs, physical types/attributes, target/layout,
runtime cohort and executor-only task boundaries. Four focused cases passed:
Debug/Release each executed 1000 matching-runtime host calls and cleanup checks;
cache/metadata repair, archived source and a real static task project were checked.
Full regression and installed acceptance for this source development remain open;
the accepted public 0.159 SDK archive remains unchanged. Language stays 0.28.

The exact 0.159 SDK also has a scoped native iOS Simulator receipt: 1400 calls and
cleanup checks across two target processes. This is standalone runtime execution;
UIKit, physical devices and complete mobile delivery remain pending.

# Platform cohort preparation after SDK 0.159

Windows/CUDA platform preparation now discovers supported027/028 from consistent
compiler identities; Linux smoke includes028. Resume refuses different source
versions without rewriting existing stores. Four targeted cases passed on actual
Python3.10/3.14, including CUDA source-only FFI signatures and mixed-identity
refusal. Full regression, installed helper and actual current Windows/Linux/device
qualification remain separate gates. The accepted159 SDK archive is unchanged.

# macOS development SDK 0.159 / ordinary language 0.28

The [delivery receipt](docs/releases/0.159.0.json) accepts exact source
3165aaf56866b0c3f341b63571e808cfb061aa3a in its Mac development scope:
296 CTest groups, moved/restored SDK41 with 57 additional cases each,
150 production-browser checks, 18 installed CLI scenarios and physical Apple
M5 Max OpenCL (21 native/reference cases plus six profiles, 47 kernel events).
The immutable archive was created before both installed workflows. Source
contracts are enabled in the ordinary 0.28 CLI; 0.27 history migrates explicitly.
The root-example version and retained-vs-current test failures were corrected
with diagnostics preserved; compiler/runtime implementation bytes stayed fixed.

Current Windows/Linux regression and SDK delivery, CUDA/NPU/device expansion,
general GPU code generation, Metal compute, mobile/native UI, Studio, converter,
cross-model accepted-task token measurement and every other unfinished original
requirement below remain open. The [Windows prompt](docs/WINDOWS-CODEX-PROMPT.md)
continues platform work. This SDK checkpoint does not complete the whole project.
Earlier entries below retain their historical source and acceptance scopes.

# Language0.28 ordinary CLI integration — development0.159

The working CLI selects028 and advertises source_contracts. Named/generic
requires/ensures and annotated while checks now compose with typed ABI7 delivery,
original-declaration and source-backed operation edits. Seven actual ordinary-CLI
scenarios passed: native Debug/Release, reference/TypeScript/scalar Wasm, guarded
edits, genuine027 migration and source-absent mixed-history recovery/export.
The [CLI receipt](docs/evidence/source-contract-CLI-0.159.0.json) records the
initial stale-example failure and compiler-refreshed028 bindings with unchanged
source/function hashes and clause intents. Seventeen initial focused groups and
all seven refreshed example/contract/task groups passed. The new required SDK
contract phase ran from source; installed acceptance of all41 phases and final
full296 remain pending.
PublishedSDK156 and its acceptance remain unchanged. Current Windows/Linux/device,
mobile/UI/Studio/converter and every remaining original PLAN requirement remain.

# Public028 integration in progress — toolchain0.159 / ordinary language0.27

The next working source composes explicit028 clauses with detached runtime
contracts. It preserves the selected source version, discovers original loops
through checked wrapper/body relationships and retains source checks once.
The physical clause interval is derived source metadata, outside canonical IDs.
All-target build,9 composed native/reference/TaskIR/Node/TypeScript/proof/refusal
cases and7 retained contract/verification/migration groups passed. The
[scoped receipt](docs/evidence/source-contract-composition-0.159.0.json) records
these inputs. Full integrated acceptance remains open; ordinary028 CLI/default,
history/project/example and installed SDK delivery remain in progress. Every
original PLAN item remains.
The preceding158 delivery is frozen at6fb91f4 for full294;157 passed full290 at59bdf23.

# Source-contract project delivery candidate0.158 / ordinary language0.27

Version-selected028 source/static/shared/mixed components retain exact source
language through provider records, native cohorts, debug unions and capture.
ABI7 and retained027 formats remain separate from the028 cohort identity.
TypeScript task-test execution selects the typed scheduler for028. Scoped checks
passed:28 component/capture/profile/package cases,8 debugger cases,136 provider
record checks and75 production-browser cases across Chromium/Firefox/WebKit.
The [delivery receipt](docs/evidence/source-contract-delivery-0.158.0.json) pins
this explicit C++ candidate. Matching full294 and installed SDK acceptance remain
pending; public028 CLI and every original PLAN requirement remain. The preceding
157 source/full290 stays frozen separately at59bdf23.

# Source-contract028 development - toolchain0.157 / ordinary language0.27

Explicit version-selected028 syntax adds requires/ensures to ordinary named
functions and invariant/decreases to while loops. Static helpers retain generic
bounds, original return/finally boundaries and ordinary checked exits. Loop
observations check purely outside body-local shadows; retained027 parser/identities
and guarded history migration stay separate. Public CLI/default remain027.
Focused29 native/reference/TaskIR/Node programs and16 rejected programs passed,
including exact clause locations. The genuine027 fixture retains two revisions
and all16 tables. Matching full290, installed SDK, public028 project/provider/browser/debug/profile
integration and all remaining original PLAN requirements are still pending.
The accepted immutable0.156 SDK/main publication remains a separate milestone.

# macOS development SDK delivery - 0.156.0 / language 0.27

Source 3a220f3 passed 288 CTest groups. Both moved/restored SDKs passed 40 phases
plus 57 extra contract/debugger cases on actual Python 3.10.22 and 3.14.9.
The published archive is the exact immutable archive used by both workflows:
docs/releases/0.156.0.json. Concrete/generic runtime contracts retain exact types,
effects, bounds and owned cleanup; scalar/loop/value/generic families1/2/3/4 coexist.
Physical Apple M5 Max OpenCL and native source-profile scopes are recorded
separately. This accepts the recorded Mac development scope; current Windows/Linux,
mobile, general GPU/NPU, UI/Studio/converter, source contract syntax and every
other unfinished original requirement below remain open. Earlier entries preserve
their historical development states and do not override this receipt.

# Scoped Mac GPU and generic profiling qualification - 0.156.0

Compiler source 3a220f3 passed 21 actual OpenCL native/reference scenarios and six
native source profiles on Apple M5 Max (47 physical kernel events). Generic
Tagged<T> roots retain str/list<str>, pure T-annotated predicates, physical fence
cleanup, cancellation/deadline and exact source-call counts. Visible managed
shallow pools balanced on success, pre/post traps, body overflow and control exits.
The receipt is docs/evidence/macos-opencl-0.156.0.json; compiler/runtime code is
unchanged by this evidence publication. Full regression of 288 groups and installed SDK acceptance are separate gates. Integrated GPU timeline, general kernels, Metal compute, Apple
NPU, current Windows/Linux delivery and every unfinished original item remain.

# Generic runtime contract development - 0.156.0 / language 0.27

The next source candidate projects ordinary generic templates without a language
or ABI change. Predicates must type-check under the template bounds even when
unused; type parameters and constructor kinds are carried to the private body.
New candidate/session4 records exact original parameter metadata. Existing scalar,
loop and value receipt families stay compatible. All-target build and targeted
scalar15, loop15, value14 and final generic9 cases passed. The generic example
passed reference, native Debug/Release and TypeScript tests. The initial invalid
str/ordered fixture remains retained; string addition and numeric ordering are
checked under their actual bounds. Full288 regression, installed SDK and platform
acceptance remain pending.
Frozen0.155 full287 and relocated/restored SDK gates continue independently.

# SDL Metal/Retina example qualification — 0.155.0 compiler

The SDL example now maps its logical board to the actual physical presentation
rectangle, retains surfaces through RAII and exposes a bounded smoke-only size
control. Native/reference/Node rules, eight physical Metal scenes, ten invalid
size refusals and relocated read-only/source-denied package execution passed.
The [scoped receipt](docs/evidence/sdl-metal-retina-0.155.0.json) pins the exact
source overlay and unchanged compiler. The parent ce72e9f core/SDK gates run in
their separate frozen worktree; this example result does not accept the full
language, SDK, current Windows patch, Linux graphics or remaining PLAN work.

# Runtime value contract development — 0.155.0 / language 0.27

The next source candidate extends executable contracts to concrete value/effectful
roots and checked pure expressions. Original lexical signatures, aliases, realms
and effects are retained; generated body calls preserve source-error and finally
return boundaries. Candidate/session3 identifies this extended scope; scalar1 and
loop2 remain separate. All-target builds passed. The existing scalar/loop groups
passed; a 13-case value run and a separate real FFI case passed after test-fixture
repairs. Original failed logs/fixtures remain retained locally. These are scoped
development checks: full287 regression, matching SDK and platform acceptance
remain pending. The shipped effectful example is explicitly unsupported by the
separate scalar proof engine; runtime generation is not a proof.
The frozen0.154 integration is undergoing independent full and SDK validation.

# Windows/runtime integration — 0.154.0 / language 0.27

Development combines Mac runtime loop contracts (7272ebc) and the five native
Windows acceptance commits ending bfe4486. Language0.27 and task ABI7 are
unchanged. The integration has not inherited either parent's acceptance:
matching build, targeted/full regression and installed SDK checks are required.
The Windows 274-group/CUDA35 receipts below remain pinned to toolchain0.152.1;
Mac0.153 passed286 groups and40 phases in each moved/restored SDK before merge.
Those parent results are retained evidence, not validation of this source.
Full Windows SDK qualification and all remaining PLAN work stay open.

# Runtime loop contract development — 0.153.0 / language 0.27

Selected while rules now project invariant entry/back-edge checks, nonnegative
iteration rankings and strict descent into ordinary checked source. Early
returns, source errors, finally and lexical bindings retain their boundaries;
no closure or language/ABI change is introduced. Pre/post-only receipts retain1;
loop coverage uses2. Build and nine targeted groups have passed (separate retained attempts).
Full regression, matching SDK and platform acceptance remain pending.
Effectful/aggregate roots, source syntax and all other original PLAN work remain.

# Native Windows acceptance — 2026-11-01

Toolchain **0.152.1**, language **0.27**, task ABI **7**. The native Windows x64
compiler and applications run without WSL. All **274 CTest groups passed**, with
zero failed/skipped outer groups, on unchanged pinned compiler/resources/harness.
The same run passed all **35 CUDA hardware cases** on RTX 3090. All-target build
also passed. Inner Python reporting contains 1018 cases and 48 explicit skips;
platform-only and non-live methods are itemized in the [final evidence](docs/evidence/windows-native-2026-11-01.json).

The [relocated Windows SDK](docs/evidence/windows-sdk-2026-11-01.json) passed native
EXE/static/Wasm/package checks and installed CUDA helper discovery, all 35 hardware
cases and 35 native cases plus a context probe under NVIDIA memcheck. The latter
uses local Named Pipes, zero memory errors/leaks and the original 2000 ms deadline.
This is scoped SDK verification; the maintained complete 40-phase distribution
qualification remains pending on Windows.

The [portable Tic-Tac-Toe example](examples/tic-tac-toe/README.md) includes NEX rules,
SDL3 GUI/GPU, `.bat`/`.sh` build/test/run/package scripts and license notices.
All four Windows batch launchers, native/reference/TypeScript, real GPU readback,
a five-move game and a relocated source-absent standalone package passed from the
installed SDK. macOS/Linux execution of these shared sources remains unverified.

Continue from [the current Windows handoff](docs/windows-handoff-current.md).
It records exact pins, local SDK paths, reproduction commands and remaining scopes.
This delivery uses branch `codex/windows-native-acceptance`; Git history identifies
the publication commit. The historical Mac and earlier failed Windows receipts
below remain separate evidence.

# Logical debugger resume delivery — 0.152.1 / language 0.27

The [matching Mac SDK receipt](docs/releases/0.152.1.json) records 285/285 groups
in the first full run, 40 maintained phases plus 15 runtime and four resume-protocol
cases in each moved/restored SDK. The [debugger evidence](docs/evidence/lldb-resume-0.152.1.json)
keeps the original timeout, prototype replays and actual implementation scopes.
An additional [126 browser tests](docs/evidence/sdk-browsers-0.152.1.json) passed
for both SDKs, using isolated compiler/driver/preview processes and a separate
same-machine browser runtime. The browser test fixture is included in installation.
Broader platform, UI/accessibility, device, language and other PLAN work remains
pending. The sections below preserve their historical versions and failed runs.

# Runtime contract development — 0.152.0 / language 0.27

The [0.152 Mac SDK receipt](docs/releases/0.152.0.json) records 284 first-run core passes
and one unchanged isolated debugger recheck, 40 maintained phases and 15 runtime
scenarios in each moved/restored SDK.
The explicit [scalar runtime pre/post projection](docs/runtime-contracts.md)
preserves original source/history and generates a distinct ordinary source
revision through private static bodies. Broader platform delivery remains pending.
The initial modular HTTP LLDB timeout remains under investigation; its successful
isolated recheck does not establish the cause or remove the original failure.
The original PLAN includes additional unfinished capabilities.

# Public025 integration candidate — not accepted for delivery

This working tree advances the ordinary language default to0.25 and retains
explicit024 parsing/canonical identities for history-preserving migration.
Mac development checks now pass retained-origin migration, nine cases across
native debug/release and TypeScript, and24 live HTTP POSTs across four normal
sync/task server images. Public task emission uses ABI6; retained ABIs stay distinct.
ABI6 providers now have versioned static/shared/mixed project records, File
cleanup, profiling and captured replay. Pure-helper logical frames were exercised
in actual LLDB sessions. Full regression, complete debug/profile, Linux/provider
and installed SDK acceptance remain pending before replacing source233 or SDK209.
Primary081/016 and all original graph/Git history stay unchanged.

# HTTP storage transaction start233

Toolchain0.135.30 starts an HTTP SQL transaction at the first storage operation.
Handlers without DB access hold no writer lease. Actual storage keeps its
method-based read/write policy,1000ms busy timeout, atomic commit/rollback and
principal isolation. The old C++ constructor remains eager. Source syntax,
public language0.24, graph history and task/provider ABIs are unchanged.
Public025 integration, complete SDK/platform acceptance and PLAN work stay open.
Sanitizers are authorized; security audit/fuzz campaigns remain deferred.

# Private modular HTTP debugging232 experiment

Toolchain0.135.29 adds matching HTTP debug hosting, actual request-ID watches
and a terminal-step marker outside scheduler/debug locks. Public language stays
0.24; the private ABI2502/catalogABI2 keep their sizes and meanings. Static,
shared and mixed HTTP programs use the same source/consumer/image context/2.
Read [the module debug guide](docs/source-exception-module-debug.md).
Public025 migration, full SDK/platform delivery and remaining PLAN work stay open.
Sanitizers are authorized; audit/fuzz campaigns remain deferred.

# Private module debugging231 experiment

Toolchain0.135.28 adds architecture/6 debug instrumentation, records/6 and an
explicit unarchived source/consumer/image context. Static/shared/mixed application
frames use the common catalog ABI2, LLDB/DAP and checked watch/capture. Public
language stays0.24. Read [the module debug guide](docs/source-exception-module-debug.md).
HTTP debug hosting/request selection, public build/debug CLI/SDK, broader delivery
and explicit025 migration remain pending. Sanitizers are user-authorized;
audit/fuzz campaigns remain deferred. The full goal stays open.

# Private module profiling230 experiment

Toolchain0.135.27 adds architecture/5 profile instrumentation and per-component
registries. Static/shared/mixed applications and HTTP hosts use one collector;
the catalog retains actual source/template, machine component and image owners.
Public language stays0.24. Read [the module profile guide](docs/source-exception-module-profile.md).
Request-ID attribution, module logical debug, public build/profile CLI/SDK,
broader delivery and explicit025 migration remain pending. Sanitizers are
user-reauthorized; audit/fuzz campaigns remain deferred. The full goal stays open.

# Private modular HTTP229 experiment

Toolchain0.135.26 adds explicit architecture/4 host selection and module/4 HTTP
root descriptors. Source errors and owned cleanup cross static/shared/mixed
code images, including consumer-owned trait instances, under one ABI2502 runtime.
Public language stays0.24. Read [the modular HTTP guide](docs/source-exception-module-http.md).
Public build/SDK, module profile/logical debug, broader platform delivery and
explicit history-preserving025 migration remain pending. Security checks are
user-deferred; the original full goal remains open.

# Private checked watch/capture223 experiment

Toolchain0.135.20 adds explicit inspect-private-task and shared checked expression
inspection over unarchived source contexts, including snapshot-only module imports.
Private LLDB/DAP watches use actual retained values, type/effect checking, bounded
lazy reads and out-of-process evaluation. Captured frames can be inspected after
execution without source files or a graph revision. Public language stays0.24;
ordinary025 publication, IDE/crash-capsule/replay, full SDK/platform acceptance and
history-preserving migration remain pending. Read source-exception-task-watch.md
and the actual descriptor. Security-specific campaigns remain user-deferred.

# Private source LLDB/DAP222 experiment

Toolchain0.135.19 emits an explicitly unarchived private task debug context.
An opt-in nex-load-private-task-debug loader connects private ABI2501 frames to
actual all-stop LLDB and the existing logical DAP stack/locals/step bridge. Catch
shadowing, caller values, rethrow, cleanup and deadlines while stopped have
separate functional conformance. Public language stays0.24. Read
source-exception-task-lldb.md and the actual descriptor. Checked expressions,
private IDE/capture/replay integration, full SDK/platform acceptance and explicit
history-preserving025 migration remain pending. Security checks stay deferred.

# Private source task debug221 experiment

Toolchain0.135.18 adds emitSourceExceptionTasksPrototypeNativeDebug with actual
native checkpoints and lexical catch/caller visibility. A separate controller
pauses the owning continuation, reads stable live frame values and resumes it;
source/control exits retire the non-owning catalog. Public language stays0.24.
Read source-exception-task-debug.md and the actual descriptor. Public025,
process all-stop/LLDB/DAP/IDE, debug/capture/replay CLI and complete SDK/platform
acceptance plus history-preserving migration remain pending.

# Private task control/profile220 experiment

Toolchain0.135.17 fixes canonical child resource-fatal delivery to blocked owners
and implicit owned-scope source cleanup. Native source-failed tasks now profile
as Aborted. A dedicated emitSourceExceptionTasksPrototypeNativeProfile produces
registered native task instrumentation and real raw schema2 reports. Public
language stays0.24; private ABI2501 is unchanged. Read
source-exception-task-control-profile.md and the actual descriptor. Public025,
profile CLI/replay, debug, host-resource integration and full SDK/platform
acceptance/history-preserving migration remain pending.

# Private native task exception219 experiment

Toolchain0.135.16 adds emitSourceExceptionTasksPrototypeNative: explicit exception
TaskIR becomes verified MLIR/LLVM and executes on physical TaskGroup workers.
Owned handlers and source failures survive calls/yield/wait; future/drain delivery
preserves original payload/site and runtime/control priority. The descriptor uses
private ABI0x4e45585400002501; published ABI3/4/5 remain distinct. Public language
stays0.24. See docs/source-exception-native-tasks.md and actual capabilities.
This is a compiler-private experiment; resource/FFI/binary/debug/profile and full
compiler/SDK/platform acceptance plus history-preserving025 migration are pending.

# Private exception TaskIR218 experiment

Toolchain0.135.15 adds explicit handler/unwind instructions and an independent
TaskIR machine selected through evaluateSourceExceptionTaskIRPrototype. It shares
the existing serial coordinator; ordinary AST reference execution stays AST-only.
This stage does not execute compiled native task code or physical CPU workers.
Public language remains0.24. See docs/source-exception-task-ir.md and actual
source_exception_prototype capabilities. Native frames/scheduler, full platform/
SDK acceptance and explicit history-preserving025 migration remain pending.

# Exception lifetime flow217 / toolchain0.135.14, public language0.24

Extends the shared task authority model with binding identities, projected
exceptional states, normal/throw outcomes and handler-aware joins. The private
Task025 experiment now has bounded lifetime analysis; unknown/widened paths keep
mandatory runtime checks. Native task exception lowering and public025/SDK
migration remain pending. Read [the lifetime guide](docs/source-exception-lifetimes.md).
The full original goal remains active and security campaigns remain deferred.

# Private TypeScript task exceptions216 / toolchain0.135.13, public language0.24

Adds a dedicated checked TypeScript generator emitter and a per-driver source
error channel, with future observation/repeated waits and joined group close.
The independent AST/reference and generated TypeScript share the same source
semantics; runtime/control failures stay distinct. Public projects, native task
exceptions, static lifetime integration, UI/worker/SDK and025 migration remain
pending. Read [the private task guide](docs/source-exception-tasks-prototype.md).
The full original goal remains active. User-deferred security campaigns stay off.

# Private reference task exceptions215 / toolchain0.135.12, public language0.24

Adds a separate private task/exception parser and checked-AST handlers, future
source-error delivery and joined group close in the independent reference
scheduler. Wait/close use explicit throw effects; cancellation, budgets and
runtime traps remain distinct. Native/TypeScript task continuations and lifetime
integration remain pending and rejected. Read
[the task exception experiment](docs/source-exception-tasks-prototype.md).
This does not publish025 or finish the full language/toolchain goal. The user's
security campaigns remain deferred; only ordinary functional work proceeds.

# Private TypeScript exception214 experiment / toolchain0.135.11, public language0.24

Adds a dedicated C++ TypeScript emitter, branded immutable user-error helper and
private operation/source mapping. Generated handlers rethrow runtime traps,
host errors and Result propagation; lexical rethrow preserves the original site.
Public source/build/archival, browser UI, Wasm, tasks and explicit025 migration
remain gated. Ordinary strict TypeScript/reference/native fixture comparisons
and compiler/platform acceptance are separate gates. Read
[the private guide](docs/source-exceptions-prototype.md). Security campaigns
remain deferred by the user's request; the full original objective remains open.

# Private native exception213 experiment / toolchain0.135.10, public language0.24

Adds a dedicated C++ native emitter with explicit error output slots, lexical
try/handler ownership frames and transfers for outer-variable assignments.
Public builds/archival and TypeScript/Wasm/tasks remain gated. Ordinary native/
reference comparisons exercise actual generated code at O0/O2; compiler, SDK,
platform and migration acceptance are separate gates. Read
[the private guide](docs/source-exceptions-prototype.md). User-deferred security
checks remain off. This does not complete the original language/toolchain goal.

# Private exception212 prototype / toolchain0.135.9, public language0.24

Adds an opt-in C++ frontend and sequential reference experiment with a distinct
0.25-prototype identity: try/catch, explicit throw effect and lexical rethrow.
Normal source/project commands remain024; native/TypeScript/Wasm, tasks and
public migration are unfinished and private emission is rejected explicitly.
Read docs/source-exceptions-prototype.md. Matching prototype/retained024 tests
and compiler/SDK/platform acceptance remain separate gates. This does not
complete the original full objective. User-deferred security checks stay off.

# HTTP211 stream prototype — intended toolchain0.135.8 / language0.24

Adds ordinary std/http_stream.nex with an opaque Body, incremental Chunk reads,
explicit close and chunked download to a regular file. It uses existing source
resources and task/ffi/fs operations; there is no language syntax or ABI change.
The provider retains one curl transfer across calls, pauses delivery when its
single16KiB staging slot is occupied, and releases the connection at EOF/close.

Combined source preflight on SDK0.135.7 passes36 ordinary cases per platform
on macOS ARM64 and Linux ARM64: HTTP1, HTTPS/HTTP1 and HTTPS/HTTP2, each with
AST/debug/release large-body reads, EOF/close, downloads and child-task handoff.
The2MiB+17byte downloaded files match the peer bytes. A separate C++ engine
probe verifies all bytes and redirect continuation; it is not NEX source
execution. HTTPS peer receipts independently record the negotiated protocol.

The continuation preflight on SDK0.135.8 adds9 actual simultaneous-reader
cases per platform across all three transports and AST/debug/release. An owned
peer releases its body only after two physical provider calls are observed;
the returned chunks retain one cursor order. A moved HTTPS2 download application
passes after its original test project and public CA file are removed, with
all2MiB+17bytes and complete static dependency licenses checked.

Source registration adds http_response_streams, the http-stream guide and
indexed examples/helpers. Ordinary CTest groups include portable values,
all three transports with simultaneous readers and a positive relocated
application download. Matching current compiler/SDK acceptance and broader
platforms have separate pending gates. Primary081/016 and its graph/Git remain
preserved. User-deferred checks are not run.

# HTTP210 source-provider candidate — intended toolchain0.135.7 / language0.24

Adds the ordinary checked std/http_client.nex library and an explicit pinned
HTTP/1.1+HTTPS/HTTP2 task/FFI provider using curl8.23.0, nghttp2 1.70.0,
c-ares1.34.9 and selected OpenSSL. Syntax, source ABI, frontend/interpreter/
backend semantics and the source language version remain unchanged.
See [the HTTP client guide](docs/http-client.md). Preparation uses explicit
operator domain/port/method/resolver/CA policies; it grants no ambient proxy,
netrc, system-DNS fallback or TLS keylog file authority.

Source preflight on the verified0.135.6 SDK passes90 actual AST/debug/release
cases per Mac/Linux ARM64 host, plus client pruning and relocated HTTP/HTTPS
packages after deleting original source/CA. The typed host/runtime/module and
static curl/nghttp2/c-ares pass126 normal/ASAN-UBSAN/TSAN case executions per
host; OpenSSL, compiler/generated IR and macOS leak detection are excluded.
Current operator/dependency validation passes57 rejection cases per host.

This is an experimental source candidate. Matching0.135.7 compiler build, full regression and current installed SDK
acceptance remain pending. Capability/guide/resource/CMake registration is
implemented and awaits actual new-compiler validation. Fuzzing, OpenSSL/generated-IR instrumentation,
process isolation, public-URL address-range restrictions, persistent streams,
network debug/profile and broader original platform/language/Studio work stay
open. Primary081/016, the original graph and Git are preserved. All work remains
local; no new GitHub/stand export or primary SDK promotion occurs.

Older entries below retain their original checkpoint and validation scopes.

# Source209 — packaging helper and macOS c-ares alignment

Toolchain0.135.6/language0.24 C++, runtime ABI, CMake, frontend, interpreter,
MLIR/TypeScript and grammar remain identical208. Linux's shared test packaging
helper now composes across independent test classes; all5 affected Linux groups
passed on the same208 compiler. The original208 full-run failures stay recorded.

Fully instrumented c-ares exposed a packed-pointer alignment UB on macOS. The
explicit dependency builder now applies an exact hash-checked byte-addressing
patch, preserves original/effective source manifests and ships patch identity.
macOS preparation rejects older unpatched prefixes; Linux source stays upstream.
The maintained typed DNS sanitizer harness checks real C-API/runtime/module and
separately instrumented c-ares. Exact208 Linux passed120 cases; the macOS
alignment diagnostic passed80 ASAN/UBSAN/TSAN cases. See docs/dns-provider.md.
Final209 builder, normal source/package, installed SDK and platform acceptance
remain separate pending gates. This is a local candidate; primary081, graph,
Git and all original broader requirements remain preserved/open.

# DNS208 development candidate — toolchain0.135.6 / language0.24

Adds an ordinary checked `std/dns.nex` library and an operator-prepared pinned
c-ares1.34.9 task/FFI provider for64-bit macOS/Linux. Explicit numeric resolvers,
domain authority, answer/time/call bounds and physical retirement are required.
DNS results contain addresses and create no connection authority. See
[DNS guide](docs/dns-provider.md), `nex describe --field dns_provider --json`
and `nex guide --kind dns --json`. The separate static PIC dependency is built
only on explicit request and its full license/source identity travels with the
module. Base SDK compilation does not link c-ares or download it.

The earlier45-case macOS/Linux ARM64 preflight used SDK0.135.4 and an earlier
provider revision. Final208 compiler, repeated conformance, sanitizer, installed
SDK and moved-package acceptance remain pending. Syntax, language version,
checker/interpreter/backend semantics and runtime ABI are unchanged. The
primary0.81 installation, graph and Git history remain unchanged. TLS/HTTP,
DNS-to-TCP integration and all broader planned work remain open.

SQLite fixtures207 / toolchain0.135.5 / language0.24 prepares the complete
actual ELF dependency closure when a test copies the selected SQLite library.
The original Astra193 fixture copies SQLite away from ICU; clean root RUNPATH
cannot find those children. Independent fixture preparation now captures all
resolved non-platform inputs, bounded to128 images/256MiB, preserves SONAME
aliases, gives each copy an origin-relative path, rejects unresolved inputs
and verifies original library bytes remain unchanged. Notice discovery uses a
clean loader environment. No production resolver or provenance rule is relaxed.
The same real NEX storage scenario on one206 compiler fails with the206 fixture
and passes with207 against an actual doctor-selected private SDK containing
system SQLite plus two owned DSOs. Complete installed SQLite/GCC notices and
owned MIT are retained. A separate source/SDK-free container verifies15 package
files,5 absent-input controls, actual packaged loader paths, Unicode output and
a real SQLite database. The normal Linux packaging suite passes7 tests.
Compiler C++, CMake, runtime, frontend, interpreter, MLIR, TypeScript, language
specification, grammar and language pack remain byte-identical to206. This is
conformance-only source work; matching206 full/SDK acceptance and207 Mac tests
remain separate gates. Actual current-source Astra execution, general explicit
runtime search policies and all original future requirements remain open.
Primary081/016, graph and Git are preserved. Current work is saved locally only.

ELF loader context206 / toolchain0.135.5 / language0.24 retains each root
image's actual loader resolution while collecting its transitive dependencies.
A real executable with inherited DT_RPATH runs, but the old collector failed
when standalone inspection of its child lost that path. The same new regression
fails on the unchanged205 helper and passes on206: three nested owned DSOs,
source-deleted moved execution, actual packaged loader paths, non-inherited
RUNPATH rejection and conflicting deep-provider rejection across cached roots.
Notice catalogues add no search authority. Inputs unresolved in their real root
context still fail; general explicit search policies and the remaining Astra
SQLite/ICU fixture causes are not declared resolved. Frontend, native backends,
interpreter, TypeScript, runtime, language specification, grammar and language
pack remain unchanged. Full203/SDK38 Mac/Linux have completed; current205 and
matching206 build, full regression, installed SDK and platform gates remain
separate. Primary081/016 and the full original objective remain unchanged.

Shared owned pthread205 / toolchain0.135.4 / language0.24 gives the separately
built shared runtime the owned executor's pthread dependency even when source
tasks, parallel calls, profiling and FFI are absent. The exact approved193
two-DSO/file test on Astra fails with real pthread_create/pthread_join link
errors and passes unchanged with an explicit operator -pthread driver,
including execution after original sources/images are removed. The ordinary
application backend fix199 did not cover this independent runtime builder.
Runtime compilation and shared linking now select pthread from the actual
executor component; the runtime cache seed records that selection. The real
two-DSO moved-execution case covers debug and release. No source task workers
or language/ABI changes are enabled by this link dependency. Current build,
focused/full/SDK/platform verification remains required. Local204 private
runtime packaging has independent4250-pin proof; full203 and SDK204 still
retain their own pending scopes. Primary081/016 and the full objective remain.

Nested notices204 / toolchain0.135.3 / language0.24 forwards the explicitly
selected SDK notice catalogue into public file-write delivery and all three
static/shared/mixed project packages. The real Astra193 SDK run passed22 phases
then failed because that subprocess omitted the catalogue; the same retained
static project packages successfully with the authentic existing notices.
The helper pins its catalogue path/hash, and the parent verifies that selection.
No provenance checks are relaxed. Compiler/runtime/CMake/language/ABI remain
byte-identical to203; all original failures, current full203 tests and the broad
objective stay preserved. Matching private-runtime and installed SDK proof is
still required. This local source204 snapshot has not been exported to stands
or backed up to GitHub; the pending GitHub question concerns exact source203.

ELF identity203 / toolchain0.135.3 / language0.24 explicitly requests a
SHA-1 GNU build ID for every final Linux native application link. Source193
on Astra produced a real profile application without any build ID under its
existing Clang; the same approved example with an operator flag has an ID.
The task-debug-only request did not cover ordinary captured/profile images.
The static-provider profile regression now suppresses the driver's implicit
build ID while preserving a later explicit compiler selection; actual source
counts, completed task lifetimes and physical image validation must still pass.
Source language/ABI, runtime, other backends and shared-image link policy stay
unchanged. Current build/focused/full/SDK/platform proof remains required.
Earlier199 Mac/Linux full214 and Linux live22 have independent proof; SDK202
and Astra193 retain their exact scopes and original failures. Primary081/016
and the full original objective stay preserved.

SDK bootstrap202 / toolchain0.135.2 / language0.24 validates its fixed38
registered workflow actions before discovery without reading an uninitialized
doctor response. The source199 full214 Mac run passed; its SDK run retained a
real KeyError before any phase. This is an acceptance-driver correction only:
compiler/frontend/backends/runtime/root CMake/spec/grammar are unchanged. Full
matching SDK38 retry remains required. The original broad objective, all older
failures and primary081/016 history stay preserved.

TCP sanitizer multiarch201 / toolchain0.135.2 / language0.24 selects exact
OpenSSL include/crypto/SSL paths from the actual doctor response for the optional
sanitizer host. Explicit root=/usr did not find libcrypto in Linux multiarch;
the source200 maintained-runner failure is preserved. The original six-variant
C++ matrix remains valid under its original build settings. Compiler, runtime,
root CMake, language/ABI and C++ case sources are unchanged. Matching maintained
wrapper checks on Mac/Linux and installed delivery remain pending; main199
full/SDK38 and the original broad objective stay open. Primary081 is preserved.

TCP sanitizer200 / toolchain0.135.2 / language0.24 adds an optional installed
typed-host sanitizer driver. Compiler/frontend/backends/runtime and source ABI
are byte-identical to199. The actual C++ typed C API, copied task/FFI bridge,
loaded pinned TCP provider and IO pool pass Mac/Linux normal/ASAN-UBSAN/TSAN,
192 case executions/216 real sockets. Flags and symbols are independently
verified573 evidence pins. No compiler/generated LLVM IR instrumentation is
claimed; Mac LSan is disabled and Linux LSan enabled. Two initial test-harness
failures are retained: explicit two-context module quota and concurrent logical/
physical revocation error precedence. The maintained wrapper's scoped discovery
and OpenSSL selection are checked separately. Main199 full214/SDK38/Linux and
Astra193 continue under their original source scopes. The original full objective
and all broader unfinished integrations remain open; primary081/016 is preserved.

Owned pthread199 / toolchain0.135.2 / language0.24 makes POSIX native
owned-cleanup runtime linkage explicit even for fs/resource-only applications.
Astra193's actual unchanged file diagnostic test failed before execution:
ld.lld could not resolve pthread_create/pthread_join from nex_resource_executor.o.
Newer glibc merges pthread into libc and had hidden this dependency locally.
The owned executor compilation and final non-archive link now select -pthread;
its runtime-object cache identity records the changed compilation setting.
Source semantics, source version and task ABI stay unchanged. Actual current
build/focused/full/SDK/platform verification remains pending; source198's full
run and separate source193 stand receipt retain their original scopes.
Primary081/016, original graph/Git state and the full objective stay preserved.

TCP198 / toolchain0.135.1 / language0.24 adds a checked std/tcp library and
operator-prepared pinned native module using the existing copied task/FFI bridge.
Actual NEX AST/debug/release calls pass36 loopback cases on the previous197
compiler: binary IPv4/IPv6, limits/reset, own timeout/reuse, single-CPU progress,
parent cancellation/deadline and ResourceDomain-backed provider call capacity.
This adds no source syntax, effect, ABI or implicit migration. Exact targets are
compiled into the pinned module; the explicit foreign catalogue still grants
execution. Delivery negatives, matching full/SAN/Linux and installed SDK proof
remain pending. A cleanup-only DAP BrokenPipeError fix preserves other errors;
15 DAP tests pass. Primary081/016 and the original full objective stay preserved.
Source197 exact Mac full212 and source196 Linux full211/live22/source-free SDK37
have now passed independently checked logs, commands, resources and binaries.
The old Mac196 full DAP failure remains recorded; it is not a pass.

Network197 / toolchain0.135.0 / language0.24 adds a private trusted-host TCP
kernel on the existing external IO pool: exact operator-granted IPv4/IPv6
endpoints, copied binary inputs, nonblocking connect/send/read, queue-inclusive
deadlines, cancellation/revocation checks, bounded replies and socket settlement
before completion.87 actual loopback checks pass on macOS normal/ASAN-UBSAN/TSAN
and Linux normal/ASAN-UBSAN/TSAN. Each variant runs87 checks on actual sockets.
The separate Linux image retains pinned compiler-rt22.1.8 and original image layers.
CMake registers the same kernel as a separate conformance target. Discovery,
language pack, host guide and LLM prompt explicitly keep source_support false.
No source syntax, language migration, task ABI or existing source semantics change.
Source/native/reference network bridges, DNS/TLS/HTTP/streaming, async DB and
matching compiler/SDK/platform delivery remain open alongside the entire original
objective. Primary081/016, previous SDKs and graph/Git history stay preserved.

Capsule196 / toolchain0.134.5 / language0.24 creates core-capsule staging
beside the destination using a literal POSIX path. The general LLVM temporary
helper redirected percent-bearing parents to /tmp, breaking exclusive publication
across filesystems in the actual Linux installed-live DSO test. The original193
failure and direct filesystem controls are retained. Existing destinations remain
protected by exclusive rename; OS publication errors now retain their reason.
Language, runtime, grammar, graph identities and frontend semantics are unchanged.
Matching build/full/live/SDK/platform acceptance is pending. Primary081/016 and
the complete original objective remain preserved and open.

Quality195 / toolchain0.134.4 / language0.24 adds explicit024 checked-core
comparison and fixes inherited Python-driver RSS on Linux with a tiny C launcher.
Both actual100M-step/five-repeat observations pass, independently verified271 pins.
Mac NEX/checked-C++ medians0.316214/0.314782s; Linux ARM64 VM0.361694/0.308447s.
Linux misses the initial90-percent throughput target in this observation; general
parity, large-application quality and model/token savings remain open. Legacy018
remains the helper default, with discovery/doctor agreement required.
Mac193 moved/restored SDKs each passed37 phases/740 commands/302 indexed resources;
11614 evidence pins and2996 normalized archive members are independently verified.
Exact191 full211 passes;193's only raw core change is a direct optional include,
with eight equal Darwin preprocessing pairs and current focused3/46guards/live
Unicode DAP. Linux193 full211 passed; its stale023 smoke helper is corrected to
actual checked023/024 discovery and passes on installed024. Linux live/source-free
SDK recovery remains pending. Compiler/runtime/spec/grammar/pack/CMake match193.
Primary081/016 and the complete original objective remain preserved and open.

SDK Unicode193 / toolchain0.134.4 / language0.24 encodes producer marker
paths as UTF-8 bytes in C/C++ string literals. JSON surrogate pairs are not valid
C universal characters; the exact readonly moved191 failure is retained. The
source-resource and actual debugger producer paths share the corrected encoder.
A real C11/C++20 compile/run regression covers emoji, quotes, backslashes,
controls and adjacent digits. Linux192's direct <optional> fix is retained.
No language/ABI changes. Matching moved/archive/platform acceptance is pending;
primary081/016 and the original full objective remain preserved and open.

Linux portability192 / toolchain0.134.4 / language0.24 adds the direct
<optional> include required by the POSIX file runtime. The exact frozen191
Linux ARM64 build failure is retained; macOS had supplied this standard header
transitively. No language, runtime semantics, ABI or dependencies change.
Fresh matching Linux build/full/installed SDK acceptance is pending. MacOS191
full and readonly moved/archive SDK checks remain separate live scopes.
Primary081/016 and the original full objective remain preserved and open.

Readonly SDK191 / toolchain0.134.4 / language0.24 corrects the model replay
acceptance to use a private explicitly selected resource projection. Its model
and compute sources are absent, fresh imports must fail, and the archived
revision is rebuilt after deleting native caches. Installed SDK sources remain
unchanged. Frozen190's timeout/actual phase-count fixes are retained. The original
190 kernel-isolated failure is retained. Actual readonly relocated/archive SDK
acceptance is pending; primary081/016 and the full remaining objective remain.

Distribution190 / toolchain0.134.4 / language0.24 corrects the maintained
macOS moved/restored SDK workflow budget and its actual phase count. All
compiler/runtime/core source and installed SDK189 input resources are unchanged.
Actual kernel-isolated relocation/archive acceptance remains pending. Primary081
and the entire original goal are preserved. Older entries retain their scopes.

Delivery189 / toolchain0.134.4 / language0.24 adds mandatory37-phase installed
SDK acceptance for public task HTTP/verified HTTPS. The indexed helper retains
148 checks,50 request outcomes,14 clean server exits and exact cancellation
codes;45 archive/receipt guard tests pass. Compiler/runtime source and version
are byte-identical to188. Installed source-absent37-phase, full188211 and matching
platform delivery remain pending. Primary081/016 is preserved; the complete
original objective remains open. Older entries retain their historical scopes.

Development188 / toolchain0.134.4 / language0.24: public native task HTTP
handlers now use a dedicated descriptor bridge in debug/release, inheriting
request control and operator file grants. Actual HTTP preflight passed132
checks across two profiles, including source-absent execution and disconnect
cleanup. Full build and11 focused CTest groups passed. Async network/DB, HTTP task providers/profile/debug, matching full/
SAN/SDK/platform acceptance and the complete original objective remain open.
The approved primary081/016 is not replaced. Older entries below retain their
historical scopes. See docs/server.md and structured_tasks_runtime.http_server.

# Development0.134.2: current source task discovery and example project

Current type-patch, scalar verification and acceptance-task examples have024
snapshot/content/intent pins issued by the actual compiler. Replacement bodies,
pre/postconditions, loop annotations, task requirements and budgets are preserved.
Historical SDK fixtures are unchanged; metadata refresh is verified in isolated copies.

Current task profile/debug discovery advertises execution ABI5, matching emitted
TaskStreams024 code. The checkout example project declares024; original historical
fixtures and the primary081 project remain unchanged. Runtime ABI, source semantics,
grammar and stored identities are unchanged. Matching full/SAN/SDK/platform delivery
and all original broader requirements remain pending.

# Development0.134.1: public024 provider profile capture

Acceptance-task profiling includes the checked ABI5 component source union
(linkage9), alongside strict retained linkage3/6. Private startup-linked lifetime
drivers now require the current ABI5 descriptors; physical completion, cancellation,
profile/debug catalog ownership and single-runtime checks remain unchanged.
No source semantics, grammar, provider ABI, grants or historical records change.
Matching regression, sanitizers, installed SDK and platform delivery remain pending;
all original language/server/accelerator/UI/mobile/Studio/converter goals remain open.

# Development0.134.0: public source language0.24 candidate

Ordinary source/project commands select TaskStreams024. Checked server task/fs
functions support opened File IO and genuine File owner captures/results across
structured tasks. Static/fixed-shared source providers use ABI5 records8/9/10;
read/write/stream requirements never grant OS authority. The same source semantics
are executed by native continuations and the independent AST interpreter.

Explicit migration verifies retained018..023 origin identity before checking024
and before opening a writable Store. Original rows/schema/IDs and physical files
remain; export creates a separate current-language project. Merely editing a
manifest does not migrate a graph. Retained023 parsing and ABI3/4 stay intact.
See [source file streams](docs/task-file-streams.md). Current compiler, full/SAN,
installed SDK and platform acceptance remain independent pending gates. The
accepted SDK0.133.5 and primary081 have not been replaced. All original broader
language/server/accelerator/UI/mobile/Studio/converter requirements remain open.

# Development0.133.12: source alias-close and genuine mixed histories

The private024 physical IO suite covers source alias-close during read, write,
append, flush, seek and size, in addition to existing host/source controls:
62 native/independent-AST pairs on12 compiled NEX images. A closed alias loses
logical access while physical leases and quotas remain until IO retirement.
Visible completed writes are retained; cancellation/close promises no rollback.

Four real installed SDK1335 histories add12 original023 revisions combining
File/whole-file IO with C11/C++20 opaque resources and task captures. Explicit
migration retains all16 tables and original identities, rechecks external
signatures and ownership, and records any new-platform binary-pin projection
only in the new024 candidate. Original pinned runtime execution is reported
only when actually available. See docs/task-stream-ffi-histories.md.

This adds conformance and test-host integration, with no compiler/runtime source
semantics, syntax, canonical identities, public023 or historical rule changes.
Matching full/SAN/SDK/platform acceptance and public024 delivery remain open,
as do all original language/server/accelerator/UI/mobile/Studio requirements.

# Development0.133.11: private physical IO and marker conformance

Private024 actual syscall gates exercise held leases/quota, host cancellation,
deadline, domain revocation, trusted host failure and source task_cancel across
native continuations and independent AST execution. Exceptional completion keeps
strict one-shot admission and preserves E_RESOURCE_SCOPE/E_TASK_HOST diagnostics.
An exact publisher-local fallback addresses instrumented marker prologues without
inferior execution, disabled sanitizers or relaxed formatter/image/publication
checks. Normal and sanitized delivery must be verified for this exact source.
Public023/default and the complete original project scope remain unchanged.

# Development0.133.10: private024 pure-helper requirements fix

The native file requirement classifier lifts reachable pure helpers before
inspection, consistently with actual continuation emission. Pure generic
callables and File identity helpers remain valid checked source; no new effect,
grant, syntax, public024 switch or historical revision reinterpretation is added.
Five real SDK1335 histories/15 revisions extend migration conformance. Current
full/SAN/SDK/platform acceptance is separate and is not inferred from focused
tests; all original project requirements remain open.

# Development0.133.9: explicit private024 project delivery

Compiler-owned source selection now rechecks024 physical projects and their
matching locks without deriving the parser from untrusted metadata or opening
a graph Store. Ordinary CLI/default projects retain023. ABI5 project linkage
records distinguish read/write/stream requirements, task-code/5 imports and
strict retained ABI3/4. Captures recheck the selected language, source ownership
and exact plan before replay; native packages record the checked program language.
Native profile readers and source-backed LLDB/DAP accept ABI5. Private024 File
bindings expose only diagnostic identities in pure watches; filesystem/effectful
operations remain rejected. No File IO authority is reconstructed by a watch.
Read docs/task-stream-project.md. Public024 publication, explicit migration,
remaining in-flight source IO/history cases and matching full/SAN/SDK/platform
acceptance remain pending. The entire original project scope remains open.

# Development0.133.8: private024 mixed file/resource conformance

Actual NEX programs retain a genuine File and a genuine C11/C++20 opaque
resource in the same immutable graph. Twenty-four native/independent-AST pairs
exercise captures, futures, sibling channels, returned closures, nested aliases,
scoped cleanup/quota reuse, function-local errors, readonly grants, checked
abort and source task_cancel. Nine invalid FFI/wire entry checks retain the
existing rejection; public023 and client-only pruning stay unchanged. This adds
conformance, not C FFI File transport, arbitrary in-flight syscall cancellation,
public024 publication or platform acceptance. Read docs/task-stream-mixed.md.
Compiler/runtime/spec/grammar/language-pack semantics match175; the toolchain
identity and test registry change. Matching full/SAN/SDK acceptance keeps its
separate evidence and all original project requirements remain open.

# Development0.133.7: private024 native source file providers

Private024 source providers have explicit ABI5 records8/9/10 and root stage3.
Checked File parameters/results, including immutable aggregates, cross static
and fixed shared source boundaries under the same application runtime and
resource-region guards. File-bearing retained task values request the stream
image flag independently of read/write operations. Image/component/root flags
never grant OS authority. ABI3/4, public023 and provider masks31/799 stay strict;
ABI5 provider mask3871 excludes standalone source FFI bits. Profile/debug source
metadata accepts explicit024; full CLI project-plan/capture/replay/package/
debug/profile and public024 delivery remain separate pending work. Compiler,
source/provider conformance, full/SAN/SDK/platform acceptance must be verified.
All original language/server/accelerator/UI/mobile/Studio/converter/measurement
requirements remain in scope. There is no grammar or public language change.

# Development0.133.6: private024 source control conformance

Twelve actual compiled-NEX/independent-AST pairs pass across six native images:
real TaskGroup/stop-token cancellation at file boundaries, real request timeout,
coordinator grant revocation, multi-module calls, checked overflow/assertion,
source task_cancel with an opened file and function-local ? errors with70 scopes.
The trusted native host requires zero IO credits and cleanup reservations and
restored managed-value counts; reference caller-region settlement must be ready
before return. Detached native runs preserve the exact written prefix. This
checks source boundaries, not cancellation during an arbitrarily blocked syscall.
Compiler/runtime/spec/grammar/pack source bytes match173; this adds conformance
and staging/observation helpers, with a toolchain identity update. Public023 and
retained ABI3/4/history are unchanged. Public024, additional in-flight/mixed
cases, ABI5 provider/capture/package/debug/profile, current SDK/platform and all
original language/server/accelerator/UI/Studio/converter/measurement work remain.

# Development0.133.5: owning cleanup for private024 source files

Every private024 source open reserves an owning executor cleanup slot before
physical file construction. Native host contexts and the independent AST
scheduler provide this executor explicitly. Logical close revokes all aliases
immediately; the last physical lease queues the complete payload/destructor,
file quota and settlement fence on that executor. No cleanup admission or
allocation is needed at final release, including after the executor closes.
Cancellation, discarded opens, factory failure and resource-region retirement
retain physical settlement. A missing source cleanup executor is rejected;
legacy host opens without an executor preserve their existing inline contract.
This does not promise bounded OS close latency, rollback or directory durability.
Public023/default, retained ABI3/4 and syntax/history remain unchanged. Controlled
source cancellation, ABI5 provider/capture/package/debug/profile, public024 and
matching full/SAN/SDK/platform acceptance remain pending. All original language,
server, GPU/NPU, UI/mobile, Studio, converter and measurement work remains open.

# Development0.133.4: precise private024 task file requirements

ABI5 image read/write flags and standalone build metadata now classify checked
reachable task instructions consistently. Read/open-read and write/open-write/
append/flush have separate flags; seek/size/close/is_open retain the existing
opened owner without requesting another root read/write grant. All stream
operations set the stream image flag and enable the owning task IO machinery.
Unreachable helpers cannot add grants. Declared effects and image metadata do
not grant OS authority or upgrade a read-only file. Public023/default, retained
ABI3/4 descriptors and their build metadata, grammar and history stay unchanged.
Public024, physical-close offload, provider/capture/package/debug/profile and
matching full/SAN/SDK/platform acceptance remain pending. All original language,
server, accelerator, UI/mobile, Studio and converter requirements remain open.

# Development0.133.3: SDK migration acceptance correction

The SDK019-history gate now keeps current language separate from each migrated
revision hash. Language/revision/namespace/16-table assertions remain strict.
This is a Python acceptance correction; compiler/runtime/TypeScript/grammar and
language-pack bytes match frozen169. Public023 and private024 scopes are unchanged.
Actual CLI gate and complete installed SDK acceptance are separate requirements.

# Private024 source stream integration (development0.133.3)

Explicit C++ source APIs may select TaskStreams024. Ordinary CLI/default projects
remain language023; changing nex.json does not enable024. The existing stream
syntax suspends inside server task/fs functions. Files created by such opens
have real logical owners, physical request/root grants and retirement fences.
Native ABI5 appends stream requests and requires explicit stream bits. Retained
ABI3/4 masks and public023 stream rejection are unchanged. File-bearing source
captures/results/futures/channels/closures use atomic mixed external/file owner
transfer; no file authority crosses browser/wire/FFI/unstructured parallel paths.
Source/physical conformance, explicit transactional migration, public publication,
provider/capture/package/debug/profile contracts and current SDK/platform delivery
remain pending. This is implemented private code, not a completed language release.

# Development0.133.2: private asynchronous file-stream foundation

Trusted hosts can prepare bounded open/read/write/seek/size/flush operations
under captured original grants. Genuine opened owners use a one-shot typed
channel; IO workers carry no source Values or raw file IDs. Immutable write
snapshots, shared cursors, partial counts, physical quotas and cancellation/
deadline settlement have actual host conformance. Query task_file_streams_host
and read docs/task-file-stream-host.md. Public language023 still rejects
reachable file-bearing task execution; source ownership/lowering/migration and
all remaining original requirements are pending. This changes no grammar or
semantic identity. Complete regression/SAN/SDK/platform acceptance is separate.
The compact prompt again includes snapshot/recovery commands; its current byte
count is 9538. Prior candidate statistics below keep their original scope.
Primary081 and its history remain separate and preserved.

# Development0.133.1 candidate: current example contracts

Current023 example revisions and proof intent hashes are regenerated by the
compiler. Intent includes the source language; the old hash is checked with
SDK1326 before rebinding. Mathematical clauses, loop strategies, type-patch
replacements, task requirements, tests and budgets remain exact. The native
read suite checks real023 writes with denied/allowed grants; retained022 write
rejection remains in the explicit retained-language suites. Compiler/runtime/
adapter bytes match the preceding166 candidate. Full188/SAN/installedSDK35
acceptance remains required; the approved primary081 and history are separate.

# Development0.133.1: compact current language contract

The model-independent coding prompt now describes current0.23 rules without
accumulated milestone instructions; detailed indexed guides remain on demand.
Six genuine SDK1326/022 histories (18 revisions) are maintained conformance
fixtures. Source tests exercise actual write DAP resumes and complete profiles;
the installed SDK gate additionally requires the18 archived migrations. The
9,215-byte prompt replaces87,830 bytes; this measures document bytes, not total
LLM token cost or coding quality.
Whole-file write discovery agrees across task/runtime sections and the language
pack. Standalone Python/Node editor acceptance discovers the actual compiler
language instead of creating hardcoded022 projects. Source language, grammar,
canonical identities and explicit migration rules are unchanged. Matching full
regression, installed SDK and platform acceptance remain required. Primary081
and its history remain separate. All original runtime/NPU/UI/mobile/Studio/
converter/quality requirements remain open.

# Development0.133.0 / language0.23

Ordinary CLI projects now support checked whole-file writes inside server task/fs
functions, including separately compiled static/shared providers. ABI4 uses
explicit record/plan/root write requirements; retained022 parsing and ABI3
records remain strict. Use explicit `nex migrate` for old graph HEADs; changing
nex.json alone is never a migration. Captured old-language tasks require their
matching retained SDK or a newly reviewed capture after source migration.

This is a development candidate. Matching complete regression, fresh relevant
sanitizers, installed SDK035 and current platform/stand acceptance remain open.
The approved primary081 checkout and its history are separate and preserved.
Read docs/task-file-writes-prototype.md and docs/task-write-providers.md.
Earlier notes below retain their historical scopes and do not override023.

# Development0.132.7: explicit private023 write-provider contracts

Separate static/shared task images use ABI4 provider records5/6/7, precise
write-image requirements and one root grant/runtime. Legacy ABI3/mask31 and
public022 remain unchanged. Private native/reference static/shared debug,
release/profile and logical-debug metadata paths are checked independently;
public023 migration, capture/replay/package, matching full/SAN/SDK/platform
acceptance and the entire original project scope remain open.
Read docs/task-write-providers.md.

# Development0.132.6: shared explicit migration and HEAD-language integrity

Genuine022 histories are rechecked through the same read-only origin/target
preflight as the CLI before private023 Store transactions. Automatic live sync
cannot switch HEAD language, including a race with an explicit migration;
readonly preflight prevents old-schema initialization on this refusal. Public022
stays unchanged. Private023 publication, write-provider contracts, matching full
regression/SAN/SDK/platform delivery and all original requirements remain open.
Read docs/task-write-migration.md.

# Development0.132.5: explicit private023 source writes

TaskIR/native continuations and the independent AST scheduler suspend checked
whole-file writes with genuine root write grants and exact owned snapshots.
Execution ABI4 appends write requests without widening retained ABI3/mask31.
Public language022/default/history are unchanged; explicit023 publication,
genuine022 migration, new provider contracts and matching SDK/platform delivery
remain pending. Read docs/task-file-writes-prototype.md. The complete original
runtime/compute/NPU/UI/mobile/Studio/converter/quality scope remains open.

# Development0.132.4: private asynchronous whole-file write foundation

Trusted hosts capture an explicit revocable write grant and snapshot bounded
input bytes before submitting IO. The worker reuses checked temporary+fsync+
rename replacement; physical retirement precedes completion/credit return.
Late cancellation can suppress admission after commit without claiming rollback.
Source language0.22 still rejects task writes; source/reference/native/provider
integration and an explicit compatible migration remain pending. Normal host,
sanitizer, full regression and SDK/platform receipts have separate scopes.
All existing NPU/runtime/UI/platform/Studio requirements remain open.

# Development0.132.3: bound diagnostic capture without limiting driver caches

A private drained pipe captures at most64KiB of first/last worker diagnostics.
The worker no longer sets a process-wide8MiB file-size limit that also restricted
vendor shader caches. Controlled old-limit SIGXFSZ and real9MiB cache/stdout GPU
probes verify the boundary. Matching frozen/SAN/SDK acceptance is separate.
All remaining language/runtime/platform/NPU/UI/Studio requirements stay open.

# Development0.132.2: validate complete device acknowledgements

Successful worker replies are checked under the Session command lock before
committing unique buffer IDs. Malformed replies drain actual storage before
failed construction returns capacity; later operations report E_DEVICE_LOST.
The original source/runtime/platform/NPU/Studio scope remains open. Matching
frozen regression, sanitizers and SDK delivery have separate gates.

# Development0.132.1: reference fence publication race

A sanitizer run of frozen132 found a false E_TASK_DEADLOCK after valid source
output while finalization raced the independent AST idle checks. A controlled
physical handoff reproduces the old failure; the fix keeps an unconsumed ready
fence as possible progress until task/scope publication. Four controlled cases,
384 async stress iterations and genuine channel-deadlock rejection pass in
preflight. Matching frozen full regression, sanitizers, GPU and SDK are required.

# Development0.132 device candidate

The ordinary owned-device library and experimental persistent OpenCL worker
are implemented. Physical GPU tests, full regression, sanitizers and installed
SDK delivery have separate receipts; no general accelerator/platform completion
is implied. Cancellation waits physical completion rather than killing a worker.
Recovery/reset, owned NPU and additional operations remain open. Read docs/device.md.

# Development0.130 / language022: publication candidate

Ordinary parse/load/CLI now selects TaskForeign022. Retained018/019/020/021
origins keep their parsers and identities; explicit migration preflights source
and origin before writes. Native provider/debug readers accept022 alongside
retained formats without widening ABI3 mask31. Capability metadata, grammar,
language pack and model-independent instructions describe the source-only
task/FFI owned-resource bridge. Full current delivery is pending; no primary,
installed SDK or hardware acceptance is implied. Earlier receipts retain scope.

# Development0.126: private native logical resource regions

The trusted native TaskGroup adapter can enable explicit logical resource regions.
It preserves256 scope depth with bounded physical joins, checked ancestry and
explicit ancestor promotion. Scope exit parks until its complete physical cleanup
fence; destructors run outside scheduler locks and on a supplied executor when
required. Root group retirement owns the remaining promoted resources.
Query `resource_regions`; read [the exact host scope](docs/resource-regions.md).
Source task/FFI/value transport, independent reference scheduling, request-parent
transfer and actual devices remain pending. Language0.21 and primary081 stay intact.

# Development0.125: executor-owned external cleanup

The private trusted host executor constructs and destroys selected external
resources on one owning thread. Cleanup slots are reserved before factories;
logical close/cancel retains physical leases and object/byte quota until the
actual destructor and code-pin release finish. Operation completion follows
physical settlement and destruction of its retained host operation.
Query `resource_executor`; read [its precise scope](docs/resource-executor.md).
Source-task ownership, C executor binding and actual GPU/NPU objects are still
pending. Language0.21, public guards and historical canonical identities are
unchanged. This separate development tree does not promote primary0.81.

# Development0.124: resource debugger arguments and current example pins

DAP launch uses its args array exactly once; raw LLDB CLI receives one run-args
command. Both ordinary and project debug commands follow the same rule. A real
resource debugger gate checks quoted operator paths, archived source, alias IDs,
pure watch refusal, stale references and graceful cleanup. Source language stays
021, with no canonical or graph migration change from0.123. Current proof/task
and type-patch snapshots are regenerated while retaining reviewed clauses,
checks, outputs and budgets. Full matching delivery acceptance remains required.

# Development0.123 / language0.21: opaque source resources

The current candidate enables server resource declarations, genuine typed extern
owners, server/ffi alias close/status and explicit history-preserving migration.
Graph type identities remain stable; editor/LSP projections distinguish resource
declarations and exact name tokens. See [source resources](docs/source-resources.md).
Matching full compiler/SDK/platform acceptance is still in progress. Source task
completion, owned GPU/NPU resources and actual resource debugging remain pending.
The approved primary0.81 checkout is separate and is not promoted by this work.

# Historical private137 source integration

Explicit internal0.21 source staging adds server resource declarations, generic
resource identities, typed extern owners and server/ffi close/status operations.
The reference and MLIR backends execute these through actual pinned C11/C++20
modules. Constructors, wire/browser/task/channel/parallel authority transport
are rejected. Public CLI/default language remains0.20; migration, public
resource publication and actual device/task integration remain pending.
Read [the private boundary](docs/external-resources-design.md).

The first scoped probe passed28 source cases/51 commands, two real native
applications and C++ factory throw cleanup. All12 genuine020 revisions recheck
to their original hashes. The maintained gate additionally checks native
throw/checked-trap exits with live owners. Matching current regression, installed
SDK, actual resource debugging and migration gates remain separate required work.

# Private136: typed external-resource C and loader integration

This cohort adds an append-only C resource suffix, result-reachable constructors,
actual pinned module callback/borrow ownership, physical capacity retention and
lexical/request revocation. Its normal seven-group private host/compatibility gate
passed, including21 new C boundary cases and the preceding21 owned-value cases.
Sanitizer, compiler/runtime integration and platform gates for this exact cohort
remain pending. Source resource declarations, task/FFI tickets and actual owned
GPU/NPU resources are still unavailable. Read
[the exact contract](docs/external-resources-design.md).

The preserved134/0.122 compiler separately passed fresh full154, installedSDK33
(595 commands/280 resources), and18 actual Chromium/Firefox/WebKit task cases.
That accepted local SDK has its own exact compiler SHA and does not validate new
private136 code. Primary0.81 and original graph history remain unchanged.

# Private135: owned external value foundation

A separate host prototype now adds typed external resource owners, physical byte
budgets, managed values and C opaque forwarding. Public source resource types,
typed construction, device executors and task/ffi integration remain pending.
Read [the implementation contract and required integration](docs/external-resources-design.md).
This changes no source language or migration and does not enable owned handles
in std/model. The frozen134 candidate and its historical full154/SDK33 gates remain
separate and unchanged. The private host foundation passed21 cases, existing
file/C compatibility and3 suites each under ASAN/UBSAN and TSAN. Normal evidence
is composite3 after correcting a missing request scope in the new task test;
the original failure remains retained. See [scope](docs/evidence/owned-external-host-foundation.json).
The reference guard has syntax validation; public source behavior and matching
compiler/platform delivery still require their own implementation and gates.

# Development0.122: installed named model contract

This candidate integrates `std/model.nex`, exact discovery/guide/prompt metadata,
installed ONNX provider preparation and matching library/SDK checks. Language0.20
and primary0.81 are unchanged. Build, four focused groups (including9 model
cases/29 compiler commands) and the exact installed model phase passed. That
phase used12 commands with the original compiler source path hidden, standard
model/compute files absent for replay, and standalone resources unavailable.
See [the scope](docs/evidence/model-sdk-0.122-development.json). Full matching154
regression, installedSDK33 and platform delivery remain pending. The verified0.121 core and compatible0.120
experimental provider receipts below retain their original scope.

# Verified local0.121 and experimental models

The unchanged0.121 compiler passed an audited153-group composite (148 original
plus4 TypeScript repeats and the complete8-case Wasm group), installedSDK32/584
commands with its original source path absent, and a separate18-case run in
Chromium/Firefox/WebKit. See [the exact local scope](docs/evidence/compute-0.121-local.json).
Primary0.81 and graph history are preserved. Full current Linux121/portable
bundle and remaining PLAN work are separate.

The experimental [named model API](experiments/models/README.md) passed its
source contract tests and compatible0.120 CIX provider acceptance. Current
MatchCPU receipts contain14 actual NPU calls,28 selected CPU calls,14 separately
attributed CPU references,14588 checked selected output values and126 bit-exact
reference values. Mul and Add/Sub models ran on NPU; two-input MatMul was refused
with CPU EP fallback disabled, followed only by explicitly requested CPU fallback.
Vendor precision separately passed3 CPU/3 NPU calls without a CPU oracle.
All three application source files were absent for MatchCPU replay/standalone;
native managed memory balanced and17 controlled production-broker cases passed.
Returned791 files and118 raw ORT profiles (including retained v2) were verified.
See [the exact evidence](docs/evidence/named-models-0.121-development.json).
This remains outside installed0.121; arbitrary graphs, other runtimes/platforms,
owned model/device resources and source task integration remain pending.

# Current portable common OpenCL development

One preparation workflow generates ordinary-source common compute projects for
CIX and RK3588 using each installed OpenCL loader. Both passed49GPU calls,
1835078 exact valid outputs,7 explicit overflow errors, nativeRelease tests,
profile, source-deleted replay and standalone with pinned external bundles.
Each pinned worker passed20 boundary cases/14actualGPU calls/524321 validvalues;
the same broker additionally passed11 CPU transport/cancellation cases on CIX.
Returned203 files were independently verified. See [scope and hashes](docs/evidence/portable-opencl-0.121-development.json).
This is compatible0.120/language0.20 source/provider execution. The0.121 core
passed the composite153 and matching SDK32 described above; original failures
and their successful targeted repeats are retained. Primary0.81 stays preserved.
The stdlibrary delta from130 is one comment, with unchanged function text.
Owned resources/task bridge, generic kernels/models, discovery and PLAN remain open.

# Current compute/OpenCL development

The0.121 ordinary-source compute contract has checked CPU operations and a real
experimental full-U8 OpenCL provider on RK3588. Independent returned evidence:
90 rawGPU calls/30780 valid output values/10 overflow errors; common Context
49GPU calls/1835078 valid values/7 overflow errors and21NPU calls/4480 values;
20 direct-worker cases plus11 process-boundary cases. All device results use
the compatible0.120 compiler. See [scope and counts](docs/evidence/compute-opencl-0.121-development.json).
The unchanged0.121 compiler core passed the composite153 and installed SDK32
described above; the four failed TypeScript groups passed with the pinned path.
Primary0.81/lang0.16 is preserved. General ownership/resources, task dispatch,
float/model support, provider discovery and the remaining PLAN are open.

# Working130: common compute contract

Development0.121/language0.20 adds ordinary-source tensors and CPU operations,
checked provider selection, response validation and explicit fallback. Focused six-case CPU/native/TypeScript/reference, overflow/limits, negative
provider/context/realm cases and owned profile pass; matching compute/discovery/
SDK archive workflow groups pass3/3. Compiler build passes;
complete regression/SDK and actual common GPU/NPU adapters remain pending.
Primary081 and accepted129 recovery are preserved.

# Working128: browser structured task hosting

Toolchain0.120/language0.20 connects task-only worker_compute to its own
cooperative TypeScript scheduler inside a dedicated module Worker. This is an
adapter change: no syntax, canonical identity, execution ABI or migration change.
UI entries remain pure; only wire values cross messages. The matching
frozen implementation acceptance passed full152, installed SDK31/575 and18
cases in Chromium/Firefox/WebKit. Astra/CIX/RK3588 physical results have separate
scopes; see [current acceptance](docs/stand-acceptance-0.120.md).
Original primary081 and accepted119 source/compiler/SDKs remain preserved.

# Working126: checked provider logical task debugging

Toolchain0.119.0/language0.20 enables development source-backed static and fixed
startup-linked shared provider debugging. Seven actual LLDB/NEX-DAP scenarios
and separate normal/ASAN/UBSAN/LSAN/TSAN physical-drain preflights pass on macOS
ARM64. Relocation derives new image/symbol references from immutable raw pins;
Darwin completion7 retains the root dSYM and packages it beside the executable.
Source-deleted capture/package/replay and substituted-path/symbol rejection are
exercised. Full matching152-group regression, installedSDK31 and platform gates
require separate final receipts; preflights do not certify that delivery.
Provider4/catalog1/source-union1 and catalogABI2 are separate tooling formats;
executionABI3/88, old source-only debug2 and profile3 retain their contracts.
See docs/task-provider-debugging.md. No language migration or primary081
promotion is introduced.

# Preserved125: checked native task-provider profiling development slice

Toolchain0.118/language0.20 enables one collector and checked registry batch
across static and fixed startup-linked task providers. Provider3/catalog1,
completion6/linkage3/retained3/request3 and raw/saved/session3 are separate tooling
formats; source syntax/canonical/migration and execution ABI3 remain unchanged.
The matching ten-case source/report suite, including canonical cache-parent alias
and internal-input symlink boundaries, passed. A separate private physical-drain
fence/sanitizers and the exact scoped SDK30 phase body passed. Preserved125b has
Mac composite148 (147 original groups plus corrected boundary55/39) and scoped
Linux composite11 (10 original groups plus corrected boundary). Matching installed
SDK30 passed30 phases/557 commands/269 resources with original compiled source
path absent and restored unchanged. Original failures remain retained; no pristine
full148/fullLinux/kernel-isolation claim. Exact identities and sanitizer scope:
[the125b summary](docs/evidence/toolchain-0.118.0-task-provider-profiling.json).
This accepted baseline does not validate126.
Profile-configuration test/build-test paths have an additional checked matrix;
measured profile sessions for tests remain unsupported. Provider3 itself does not
enable the distinct126 debugger. Runtime load/unload, combined
debug/profile, Tracy tasks, HTTP/foreign, authority/callable transport and
non-native profilers remain unsupported. See docs/task-provider-profiling.md.
Primary081 and prior checkpoints remain unchanged.

# Preserved124d: fixed shared task providers

Toolchain0.117.2/language0.20 passed a pristine full144 regression and matching
installedSDK29/542 commands, with its original compiled source path absent and
restored unchanged. Seven scoped LinuxARM64 groups and the separate actual
startup-linked private image fence/sanitizers passed. This fixes atomic cached
image publication while preserving loaded mappings and treats literal percent,
Unicode and quote characters in parent paths as data. Original124b/c failures
remain retained; they are not relabelled as passes. Exact identities and limits:
[the124d summary](docs/evidence/toolchain-0.117.2-task-shared-providers.json).
These are development-checkpoint results, without full Linux/installed Linux SDK,
kernel source-isolation, root promotion or whole-objective completion claims.
Provider profiling belongs to the separate125 slice above.

# Preserved123/123b: concrete static task providers

Toolchain0.116/language0.20 integrates source-checked concrete static task
archives, descriptor accessors and one root executor/grant/limits. Its17-case
source suite, strict boundary checks and reviewed capture/replay/package passed.
Preserved regression is explicit composite141:140 passed original groups plus
the repaired21-case integration group on the same frozen compiler. The original
stale capability assertion failure remains retained; no pristine full141 rerun
is claimed. InstalledSDK28/523 commands/262 indexed resources and four scoped
Linux groups/17 actual cases passed. Exact hashes and limits are in
[the123b summary](docs/evidence/toolchain-0.116.0-task-providers.json).
This does not validate124 shared integration or complete the objective.

# Preserved122: logical native task debugger integration

Toolchain0.115/language0.20 integrates separately versioned debug catalog ABI1,
compiled safe points and logical LLDB/nex-dap inspection/stepping. Its immutable
acceptance is [recorded separately](docs/evidence/toolchain-0.115.0-task-debug.json):
composite139 means138 retained passes plus one corrected9-case server workload
group using the same implementation/compiler. The original full139 failure is
retained; no pristine complete rerun is claimed. InstalledSDK27/504 commands,
three scoped Linux groups with10 actual LLDB/DAP cases and bounded runtime
sanitizer checks passed. Execution ABI3/source/canonical/history are unchanged.
Those receipts cover122/122b only. Primary081 is preserved; no full objective
completion or123 provider acceptance follows from them.

# Working121: native source task-profile integration in progress

Toolchain0.114/language0.20 is integrating the private120 collector with native
jobs, retained source frames, emitted site metadata and checked CLI/project/task
reports. Complete candidate acceptance remains pending.
Source language/canonical history/migration remain020; a separate
private compiled-task ABI3 transition is implemented consistently.
Initial actual source/profile CLI, five project/capture/replay workflows,
the60-case report validator and a separately executed installed SDK profile
phase pass. These mutable scoped results do not replace the complete frozen
134-group regression, SDK26, sanitizer and platform gates. The final source suite
passed31 commands, including six successful scenarios, checked failure cleanup
and strict raw Tracy rejection before source output/report creation.
Frozen120 independently passed cleanallbuild, focused12, strict42-case macOS
ASAN/UBSAN/LSAN+TSAN and scoped Linux Clang22 release/GCC13 sanitizer probes;
its full129 gate passed in1071.867s and its matching installed SDK25/486 commands
passed in663.640s. Its969 source files and primary081 remain unchanged.
Frozen119b full128 and its matching installedSDK25/486 commands passed.
Exact receipts retain all scopes and failed attempts.
Primary081/source/graph/Git remain preserved. No full-objective completion.

# Working120: private logical task-profile collector foundation

Toolchain0.113/language0.20 is developing a bounded private collector module and
independent native probe for logical invocation/TLS/clock ownership. No scheduler,
frame-driver, compiler emission or public task-profile integration is enabled.
Existing debug/profile rejections, task execution ABI2, semantics, grammar and
history migration remain unchanged. Its clean allbuild,12 focused groups,
129 full regression groups and scoped sanitizer/module probes passed.
Matching installed SDK25/486 commands passed. Primary081 remains preserved.
Current editor fixtures and verified119b type/proof/intent pin repairs are included.
A CLI regression checks bundled proof snapshots/task intent, preserving criteria.
The complete public task profiler requires a later integrated acceptance stage.

# Working118: consistent pending-capability discovery

Toolchain0.111/language0.20 retains117 public file-read implementation and fixes
one metadata mismatch: browser_workers.pending had different unfinished-task
wording in describe and language-pack. Frozen117 passed cleanallbuild,25/26
focused groups and five strict sanitizer probes per sanitizer, but discovery
failed on this exact comparison. Its failure receipt is retained; no full117
or117 SDK acceptance is claimed. Current118 complete acceptance is pending.
Runtime/compiler semantic source, language020, grammar and history migration
are unchanged. Primary081 remains preserved. The full objective is active.

# Working117: public task file reads with explicit020 migration

Toolchain0.110/language0.20 connects file_read_text/bytes to actual server task/fs
suspension. Explicit root FileReadGrant, raw bounded host transport and checked
scheduler admission preserve cancellation/drain, UTF-8 and result boundaries.
The independent AST reference and native continuations have separate execution.
Migration verifies genuine018/019 origins and preserves history/IDs/schema;
current physical projects and output schemas use020. Implementation and complete
current acceptance are in progress; no accepted release is claimed.

Frozen115 passed full122 and matching SDK24/438, strict sanitizers, three scoped
production browser engines and21 Linux ARM64 groups. Frozen116 passed common build, focused20, strict sanitizers, full122 and
matching installedSDK24/438.
Older records below describe their own immutable snapshots. Primary081 remains
preserved; public bridge117 does not inherit acceptance from older kernels.
Broader IO/debug/profile/providers/UI/accelerators/delivery/quality remain open.

# Working116: private explicit root file-read grant

Toolchain0.109 / language0.19 retains the verified115 transport and adds a
host-only FileReadGrant captured once from the root coordinator. Per-path
preparation survives temporary task-resume scopes, honors lexical/root request
revocation and never discovers worker permissions. Missing authority reports
CAPABILITY only at check/lease, not at entry; a future source driver must turn
ordinary preparation errors into typed results before ticket admission. A retained
4096-byte path now uses exactly4096 owned payload bytes; measured std::string
storage at that boundary required4103 bytes on the checked platform.

Standalone45 scheduler and42 non-task compatibility cases pass; independent
review found no further actionable issue. Current common build/full regression,
sanitizers, installed SDK and platform acceptance are pending. Public source
async IO and task/fs callback widening remain unsupported in019. Their future
integration requires explicit020 identity and019 history-preserving migration.
No source keyword/type/canonical shape is changed by this private foundation.
Writes, streaming/db/ffi/tasks-in-HTTP/providers/browser filesystem remain pending.

Frozen115 separately passed 122 groups, strict sanitizers, three production
browser engines (87 private host cases each), and21 Linux ARM64 groups. Its
matching installed SDK is being checked. Primary081 and history are unchanged.
Historical entries below apply to their own source snapshots.

# Working115: external-completion ownership correction

Toolchain0.108 / language0.19 corrects independently reproduced private114
failures: normal parent scope drain consumed a live child's external ticket;
post-operation cancellation masked a returned fatal error; a late physical
failure replaced an already-selected fatal error at native join. Coordinator
admission allocation failures also require preserved fatal priority. Frozen114 and
its reproducing probes are retained. It is not an accepted release.

Current115 shared build, focused/full regression, sanitizers, installed SDK and
platform checks are pending. Public source async IO remains disabled. The exact
previous113 passed118 regression groups and installedSDK24/438 commands.
Primary081 and its complete history remain preserved; the full objective is
still active. The records below refer to their own historical source stages.

# Working114: private external completion transport

Toolchain0.107 / language0.19 adds experimental native, independent reference
and TypeScript host-completion kernels. Tickets bind a scheduler, logical owner,
slot generation and single acceptance. Physical operation retirement, rather
than a cancellation request, releases transport reservations and permits owner
completion. Separate native/reference host pools have at most two workers.
The private file-read adapter captures a revocable physical lease explicitly;
workers do not discover permissions from ambient TLS or create source Values.
See [the exact contract](docs/task-external.md). No source asynchronous IO,
source fs/db/ffi task lowering or stable host ABI is enabled.

Individual kernel checks and an initial shared build have passed; the final
frozen114 build, combined focused/full regression, sanitizers, installed SDK
and platform acceptance are pending. Current source is not an accepted release.
Frozen113 separately passed all118 regression groups in1034.269s; its matching
installed SDK passed24 phases/438 commands. That evidence does not validate114.
Primary081 and its history remain unchanged. Task debug/profile, provider/UI
integration, general GPU/NPU, remaining platform delivery and cross-model
quality/cost evidence remain required by the active objective.

Previous entries below retain their original stage-specific status.

# Public019 integration corrections (working110)

This snapshot keeps toolchain0.105/language019. The previous integration's full
regression exposed reference diagnostic guards inherited from private018 mode:
ordinary019 errors lost their operation sites/IDs. The site map now determines
attribution, while raw private atoms retain their bounded no-map path.
An additional boundary audit found pure nested task authority signatures could
cross a native library ABI without a task effect. Provider lifetime support
remains pending; those exports and task-effect callable signatures are rejected
explicitly. Current shared build and18 focused CTest groups pass, including corrected
operation sites, native/TypeScript agreement, migration and32 standalone native
executions. Ten nested ABI signatures and an additional library export are
rejected; internal task helpers and source-only projects still pass. The LSP
acceptance fixtures and example patch pin now explicitly match019. Profile
options/native-host checks retain their earlier diagnostic precedence. Full114
and installed-SDK/platform acceptance are pending. Source109 and its
raw failed regression (101/114 pass) and backup remain preserved. Primary081 and
the full objective are unchanged.

# Working109: public language0.19 integration

Toolchain0.105.0 connects task types/effect and conservative lifetime checking to
native compiled continuations, reference evaluation, TypeScript generators and
real018 history migration. The shared CMake build passes. Focused checks pass: native15xdebug/release,
TypeScript11 source scenarios, migration66 requests, lifetime91 fixtures and
ordinary graph/version/history/integration groups. Full114 acceptance is pending;
this source is not an accepted release.
Native task applications and source-only projects are supported by the new path;
binary task providers, asynchronous IO, task debugger/profile, NEX UI integration,
complete static region inference and current full SDK/platform delivery remain
pending. Primary081 is preserved. This does not complete the full objective.

Frozen108 passed full110, strict ASan/UBSan/LSan and TSan gates, and eight scoped
Linux ARM64 groups. Those receipts apply to its exact private-task source,
not current109 or a full Linux/installed SDK claim. Previous entries below record
historical implementation stages and their original pending work.

# Working108 private authority-flow diagnostics

Toolchain0.104.0/language0.18 adds early source diagnostics for known task
capability escapes. Ancestor borrowing, helpers, callable factories and precise
aggregate projections retain useful values. Unknown calls, channel payloads,
recursion, joins and loop widening retain mandatory runtime obligations. This
is not complete static region typing or public source integration. See
[the lifetime contract](docs/task-lifetimes.md). Early analysis91source scenarios and33additional independent AST runs pass.
These include borrowed/owned helpers, closures, empty capability containers,
phantom types and conditionally selected channels. The first29new lifetime
fixtures also agree on native O0/O2 and strict generated TypeScript7.0.2.
Current native91/TS100/full110, sanitizers, installed SDK and platform acceptance
remain pending; whole CMake build passes.

Frozen107 completed full109 in1014.958s, strict ASan/UBSan/LSan and TSan gates
with AST/IR/reference and native58xO0/O2, plus seven scoped LinuxARM64 groups.
Linux container gates took136.38s; these are not a full Linux suite or installed
SDK proof. Primary081 remains preserved.019 migration, complete lifetime/effect
integration, asyncIO/debug/profile/provider lifetime and delivery remain required.

# Working107 private generated TypeScript task execution

This separate toolchain0.103.0/language0.18 source emits checked client/shared
functions as generators with an independent event-loop scope/future/channel
scheduler. Node67 source scenarios agree with independent AST, including58
native-suite fixture inputs; strict TypeScript7.0.2 checking and16 trusted-host
protocol/lifetime/cleanup guards pass. Host timers cancel a checked pure helper
through compiler checkpoints. Standalone production Chromium/Firefox/WebKit
responsiveness has separate one-program evidence and does not enable the NEX UI
task adapter. Current full109/sanitizer/platform/installed-SDK acceptance remains
pending. Public source tasks stay disabled pending complete lifetime/effect
contracts,019 migration, async IO/debug/profile/provider lifetime and delivery.

A boundary discrepancy was reproduced: earlier AST and initial TS counted the
root at depth0 and allowed257 total task levels. Native counts root at1.
Working107 aligns both; checked255-descendant success and256-descendant rejection
pass native O0/O2. Data's immutable owner-family tag now occupies header alignment
space: measured macOS ARM64 sizeof(Data) returns from106's112 to104 bytes, matching
105. This is a layout measurement, not broad performance evidence. Frozen106
passed full108, strict AST/reference/IR sanitizers and six Linux groups; its exact
receipts remain scoped to its old source and tests. Primary081 is preserved.

Toolchain0.98 development source adds an internal C++20 coroutine task/channel
scheduler, enabled only in a private runtime probe. NEX source async/tasks/channels
and their MLIR/reference/TypeScript integrations remain pending; ordinary
applications do not enable this prototype. Final13focusedgroups pass; the
38-case coroutine probe passes strictASan/UBSan/TSan on macOS and normal
Clang/GCC plus GCCASan/UBSan on LinuxARM64. A real initial TSan race was
fixed; raw failure is retained. Full102/SDK/platform gates remain pending. See [the design](docs/tasks-runtime-design.md).

Toolchain0.97 development source adds typed dedicated browser worker jobs.
Six focused groups and15 actual production worker cases in Chromium/Firefox/
WebKit pass on the exact current compiler; full101/SDK/platform acceptance
remains pending. No release/platform acceptance is implied. See [browser workers](docs/browser-workers.md).

# Development0.96 / language0.18 — raw buffered compiler inputs

The actual095native100module/10000function gate passes: cold9900/warm0/edit1,
standalone original/edited outputs and both archived revisions after source
paths move outside the project. Warm observation69.021s versus the earlier
09481.494s is recorded with concurrent-host scope. A live sample of that actual
095warm process identifies per-character readFile work inside cache validation.

Compiler inputs now use64KiB fread blocks, explicit ferror/feof and C++ RAII
FILE cleanup. No size/seek assumption, text normalization, source/runtime/ABI
layout change or weaker cache check is introduced. The first std::ifstream::read
variant treated a macOS directory as empty EOF; the new directory assertion
exposed this and the raw failed receipt remains. Explicit stream-error checking
fixes it without weakening that test.

All17 focused groups pass. The new five-case IO group covers every octet,
empty/exact/partial/multiple blocks, fragmented FIFO, failed reads, /dev/null and
a real UTF8 scalar split at byte65534 across the64KiB boundary. Native/reference/
TypeScript tests agree; invalidUTF8 remains E_UTF8. Its Linux procfs case is
pending actual Linux execution. The same private probe compiled against real
095/096frontend libraries compares every output byte from MachO/MLIR/JSON
artifacts across18observations and retains their unchanged hashes. Median
read/output/comparison wall for146.6MBMLIR is4.747s versus0.145s, for14.7MBMachO
0.504s versus0.042s and for24.1MBJSON0.805s versus0.048s on the concurrent Mac.
This is not a complete-build or isolated throughput measurement. Current096
native10000/full100/SDK/platform/editor/history gates remain pending.

Frozen094Mac/Linuxfull98, installedSDK24, Linuxlive22/source-free acceptance,
five installed editor profiles, CPUworkerDAP and complete016->018migration now
pass. Frozen095Macfull99passed; its SDK/Linux acceptance continues. Primary081
is unchanged. Generalasync/tasks/channels/browserworkers, accelerators, platform
delivery, model-cost quality and reviewed primary integration remain open.

# Development0.95 / language0.18 — readonly native planning index

The actual0.94 full10,000-function native gate passes: cold9,900 compiled,
warm0compiled/9,900reused, one changed leaf1compiled/9,899reused and original/
edited standalone outputs. Both archived revisions execute after their physical
sources move outside the project. Cold/warm/edit observations are577.309s,
81.494s and116.048s on a concurrently used Mac; no isolated throughput claim.
The original093E2BIG and090timeout remain retained. See the exact scale receipt.

An81.356s cached diagnostic confirms no LLVM compilation. Its live sample
locates repeated linear function searches inside native planning. Candidate095
uses an index scoped to that readonly operation; no mutable Program keeps
pointers or cached indices. First-match local/exact precedence and generic local
names containing qualified arguments are preserved. A shared private receipt
probe linked against actual094/095 libraries produces byte-exact plans for
seven programs in normal/all-callable modes, including9,900units. The large
checked-load/plan/serialization observation changes17.225s to3.945s (normal)
and19.550s to4.177s (all-callable). This is not a full095warm-build measurement.

The final15 focused groups pass. The first new plan fixture omitted
required local type annotations and failed parsing; its raw failure is retained.
The corrected four cases pass, covering module/generic names, layouts, callable
bridges, dependency edges and missing-name diagnostics. Final full99/SDK/platform/
editor/migration and native scale gates remain pending. Language018/runtime/canonical formats/ABI contracts are unchanged.

The opt-in checked-core experiment now has a reusable runner. Initial operational
smoke1/2 exposed a CLI variable shadowed by subprocess argv; a distinct settings
object fixes it. The final operational smoke passes with the exact final095
compiler; short smoke timings are not throughput evidence. Its recorded094
single positive integer kernel takes median0.307272s NEX,0.292982s checked C++
and9.922024s CPython for100million steps over five repetitions, with other
verification running. All five additional input observations agree. It does
not establish general parity or model-cost savings. Current094full98/SDK/Linux
and installed acceptance continue;093Macfull97/SDK24 and complete migration/
five installed IDE profiles pass after preserving four successful observations
and resuming the fifth with a shorter private macOS socket path.

# Development0.94 / language0.18 — bounded native tool arguments

Actual0.93 native scale compiled9,900 functions, then failed at posix_spawn:
its2.17MB link command exceeded the host argv limit. Native build tools now use
GNU UTF-8 response files for large commands. Native image linking shares the
helper; applications retain literal argv. Owned0700 directories/0600 files are
removed on success; failures preserve exact inputs and a useful path.

The first new test exposed default temporary-directory mode0750; explicit
private modes fix it. Fourteen focused groups then pass, including real Clang
and LLVM ar requests beyond host argv limits with spaces/quotes/backslashes/
percent/Unicode paths. The helper also linked all9,900 retained actual093 objects,
verified their unchanged bytes and DWARF, and executed49,460,406 correctly.
The original093 scale failure remains retained; this recovery does not turn it
into acceptance. Full09498-group/SDK/platform/editor/migration and independent
cold/warm/edit/standalone scale gates remain pending. Language0.18 and its
canonical identity/runtime/source semantics are unchanged.

Frozen092 passes Mac/Linux full97, installedSDK24, Linux live22 and source-free
acceptance, five actual installed IDE profiles, installed CPU-worker debugging
and complete primary016->018 migration. On the actual CIX
board, its private SDK passes CPU Debug/Release/reference/profile checks with
four overlapping workers, balanced managed pools, source-deleted replay and a
standalone AArch64 application without SDK dependencies. OldSDK070 and the
system installation are unchanged. Its existing fixed accelerator fixture also
passes with the private092 SDK:30 GPU calls and20 exclusively Zhouyi NPU calls,
both profiles/reference/tests, balanced managed profile, archived source-deleted
replay and standalone execution. Genuine016 history is preserved through
explicit migration in a copy. Both harness failures are retained in the exact
092 receipt. General GPU/NPU source APIs remain unfinished.
Approved primary081 remains unchanged and the full objective is not complete.

# Development 0.93 / language 0.18 — native emission analysis

A sample of the actual0.90 10,000-function build found repeated whole-closure
callable analysis in every function emitter; linear name resolution made this
work cubic. Native builds now share their already checked callable/CPU analysis
across aggregate and per-function IR emission, with readonly selected sets.
Standalone emit/Wasm paths retain their local analysis. No language, canonical
format, runtime, ownership or explicit migration change is introduced.

Twelve focused groups pass. A same-source20-module/2,000-function comparison
compiled1,980 functions under each0.92/0.93 compiler:299.583s versus113.567s.
All1,980 MLIR and LLVM units match after normalizing only the exact compiler
build identity (including its encoded form) and DWARF compiler version. Source,
semantic and operation identities remain exact. Warm reuse is0/1,980; editing
one leaf compiles1/reuses1,979. Original/edited standalone outputs and archived
source-deleted replay pass. Other verification ran concurrently; this single
host observation does not prove isolated throughput, runtime parity or model
cost. An initial comparison omitted the required compiler_build difference;
its failed receipt is retained, and the corrected check verified those exact
identities before reusing the completed cold artifacts and continuing checks.

Complete10,000-function native scale and matching full97/SDK/platform/editor
acceptance remain pending. Frozen0.92 has separate full gates in progress;
frozen0.91 has passed Mac/Linux full96, SDK24, live Linux, five installed editor
profiles and complete primary0.16 migration. Approved primary0.81 is unchanged.
The broad language/development-chain objective remains incomplete.

# Development 0.92 / language 0.18 — source CPU mapping candidate

Source parallel_map has checker/reference/native/TypeScript implementations.
Actual native profile events show overlapping callbacks on distinct CPU threads;
reference/TypeScript execute serially. Ten focused CTest groups pass, including
source semantics, genuine0.17 migration, static/dynamic providers and runtime
ownership. The mixed ordinary-error/recursion-limit regression passes after
fixing global resource-error priority. Private actual-NEX7 and runtime26 suites
pass ASan/UBSan with strict leak/error settings and ThreadSanitizer.
A source-deleted live worker breakpoint/watch/resume passes. A stale first LLDB
thread-list response is refreshed once only when it omits the actual stopped
thread; transport checks retain stop identity and checked normal shutdown.
A production TypeScript/Vite CPU-map application passes actual capture/update
interaction in Chromium, Firefox and WebKit. This is serial browser execution,
not browser worker support. Current SDK/editor fixtures use language0.18.
Full matching regression, installed SDK24, Linux, editor and complete historical
migration gates remain pending. The approved primary remains0.81/language0.16.
Historical receipts below keep their original scopes; this candidate is not an
accepted release or completion of the full objective.

# Development 0.91 / language 0.17 — compiled worker boundary

The compiler-private CPU bridge creates job-local handles, passes scalar bits,
checks result ABI kinds, retains heap/callable outputs and unwinds owned frames
on all exits. It is enabled only by NEX_STRUCTURED_WORKERS. Ordinary emitted
runtimes and the frontend/reference/TypeScript source capabilities are unchanged;
source concurrency is pending. Actual NEX closure bodies are built into a
code-only archive for the new native integration test. Full final acceptance of
this source remains pending. Previous 0.90 platform gates retain their own scope.

# Isolated candidate 0.90 / language 0.17 — validation pending

The 0.89 full95 regression failed the same four groups on macOS and Linux:
exponential duplicate statement-match traversal; two fresh-fixture copies of an
already-used example graph; and an example patch pinned to language 0.16.
Version 0.90 fixes those causes without relaxing their assertions or timeouts.
Five focused groups pass, including the 30-deep match/native/TypeScript case.
Two unchanged test methods also pass with the actual used 0.89 example as input.
Full95/SDK24, Linux live/source-free, installed editor and migration validation
for this exact frozen source remain pending. Earlier receipts below keep their
original source scopes. Primary 0.81 is preserved separately and retains the
known DAP shutdown defect. This candidate is not an accepted release.

Development toolchain0.89/language0.17 fixes a confirmed Python3.9 DAP adapter
shutdown abort: wake and join both input readers before destroying stdio; SDK
acceptance rejects abnormal adapter exits. Nine transport tests pass on the same
Python3.9 interpreter. New full/installed/platform validation remains pending.
The approved primary remains0.81/language0.16; earlier notes below are historical
cohorts. Source result propagation is carried forward from the saved0.88 draft.

Development toolchain0.88/language0.17 adds a **candidate** postfix result
propagation operator `?`. Parsing, checking and all three execution backends are
implemented in this isolated source; complete migration/platform/SDK/editor gates
remain pending. See [the contract](docs/error-propagation.md). Earlier cohort
notes below refer to their original versions. General source try/catch/throw,
source concurrency and CPU/GPU/NPU adapters remain pending. No production parity
or complete LLM-token saving is claimed.

# Mutable0.88 error-propagation draft (not integrated)

Compiler-private function ownership boundaries are being implemented so a future
propagation operation can release unnamed argument/constructor temporaries and
preserve its returned value. Scope/request/application/worker cleanup is coordinated.
Source `?` is not implemented; language remains0.16 until a coherent0.17 checker,
all backends, specification and migration exist. See the pending
[design journal](docs/error-propagation-design.md). The first19-case runtime
prototype passes, including complete files/quotas, source diagnostics, allocation
faults, stale/cross-thread/context tokens, worker reuse and failure cleanup. Six
focused CTest groups pass1.21seconds. The same19 cases pass ASan/UBSan and TSan;
source operator integration and broad/SDK/platform validation remain pending.
Frozen085/086/087 and approved primary081 remain unchanged.

# Development cohort0.87 (not integrated)

Readonly capability index and dotted-field projections bind exact descriptor
values to language/toolchain/compiler-build/hash identity. Default full describe
remains available. A short bootstrap routes models to relevant guides/context;
all source syntax and language0.16 identities remain unchanged. The
[quality contract](docs/quality.md) defines large-system, correctness,
performance and full-task LLM-cost targets; those targets are not achieved claims.
Focused and broad0.87 verification are pending.

The frozen0.85 Mac full91 and installed SDK24 pass. Four final installed editor
profiles pass; its independently generated source-server fixture incorrectly
asserted project owned-image metadata and failed. Its original failure remains;
the corrected owned fixture checks the actual inlined source-provider contract.
Linux full91/all21 live suites pass, but source-free SDK foreign project task
packaging correctly rejects missing Crypto provenance. This cohort captures the
installed Debian provider's complete reviewed license inputs before the task;
it does not relax provenance or silently grant --dpkg-notices during replay.

# Development cohort0.86 (not integrated)

Internal native structured-worker groundwork shares the parent request budget,
cancellation and absolute deadline while keeping per-job handle/resource cleanup.
Ordered immutable results, joined failures and bounded nested scheduling are
implemented behind NEX_STRUCTURED_WORKERS. Ordinary emitted runtimes do not
enable this prototype. Source concurrency and all new syntax remain pending;
language0.16 is unchanged. See [the contract](docs/concurrency-design.md).
The0.85 LSP fixture's stale extension0.6 literal is explicitly corrected to0.7
in this cohort; frozen0.85 remains unchanged. Full0.86 validation is pending.

# Development cohort0.85 (not integrated)

Native server debug preparation now retains actual source/archive/shared
providers, checked HTTP application kind, host ABI and explicit runtime args.
Extension0.7 supports source/project server launches, reviewed foreign fields
and bounded individual arguments. Plans/source aliases/dirty buffers/trust
remain checked. Native budgets, ownership and request deadlines are unchanged.

Prototype Mac descriptor/source/real HTTP worker/provider stops, source-deleted
watch and request completion, graceful shutdown, stopped-deadline timeout and
SQLite rollback pass4 cases in76.447seconds. Actual project/source editor source
breakpoints and Unicode watch pass2 cases in28.836seconds. Node25 contract cases
pass. Initial retained fixtures appended --json to runtime args and replaced
editor source-map commands; corrected fixtures preserve the actual launch.
Updated7-case bounded-argument/live worker/editor suite passes93.580seconds;
current Node39 cases pass. The original FFI project regression with a valid
catalogue granting only an unrelated export passes99.049seconds; it still
rejects the selected test before initialization. An earlier new negative
fixture used an invalid empty grant and expected the wrong diagnostic; retained
evidence shows E_FFI_GRANT, and the corrected valid denied grant exercises
E_TASK_FOREIGN_BINDING. Actual installed VSIX0.7 project/server commands, runtime
input UI, original provider breakpoint, Unicode watch, response and graceful
exit pass in two fresh private profiles in31.098seconds. These are prototype
checks; frozen full91/SDK/Linux and matching final installed extension gates
remain mandatory. Language0.16 syntax/canonical identities/history stay unchanged.

Frozen0.84 6f19a671 passes89/90 groups on Mac and Linux ARM64. Both complete
reports stop at source_ffi's existing project test: a new packaging catalogue
annotation entered its private test-plan hash but not its build plan. SDK gates
were not reached. This source excludes deployment-only annotations from private
test-entry plans while retaining parent exact reachable-grant validation; the
existing regression and denied-grant test must pass. Frozen816-file source,
GitHub2fe5a4c6 and original failure evidence remain unchanged.

# Development cohort0.84 (not integrated)

Project foreign packaging prepares selected app exports once, projects exact
literal pins across physical shared/source/archive components, reloads/rechecks
binary contracts and consumes the actual native images. Each deployed app gets
only its reachable grants; foreign-free HTTP entries skip common-runtime foreign
configuration. Original source/lock/Store stay untouched. Input aliases, metadata,
catalogue, helper and toolchain identities are checked around native tools.
Package tasks pin current operator trust and retain captured inventories; exact
member provenance mappings preserve reviewed notice roots and license bytes.
Language0.16 is unchanged. Prototype focused5 checks pass200.940seconds, including direct deployment,
per-app grants, profile ownership, module integrity, same-byte alias rejection
and source-deleted task package replay. Earlier prototype foreign/task/project
package regression4 groups pass699.07seconds; full final-source90/installed SDK/
Linux validation is still required before considering promotion. Earlier focused failures retain
test fixture glob/lock/static-index/API-path mistakes and a genuine captured
module provenance refusal; the new mapping does not grant directory-wide trust.

Frozen portable0.82 2953e041 passes Mac/Linux full88, installed SDK24/379 commands/
230 resources, plus Linux20 live suites. Initial0.82 C11/core-reader failures
remain separate. Frozen0.83 cd3c89d8 passes Mac/Linux full89; Linux20 live and
source-free/network-disabled SDK24/384 commands/232 resources pass. Its matching
Mac installed SDK24/384 commands/232 resources also passes. Both completed
cohorts are recorded in build/server-workload-082-083-complete-evidence-v1.json
of the primary workspace. Approved primary0.81 remains unchanged.

# Development cohort0.83 (not integrated)

Project server profile checks pin SHA-256 workload bytes, preserve actual binary
providers and supervise the trusted runner/native descendants directly. Each
check creates a fresh synthetic user/credential/database, excluded from receipt
inputs and cleaned after execution. Readonly check needs no credentials. Captured
workloads and current trusted runner replay after source deletion with readonly
receipts and an isolated output graph. Existing operator FFI/toolchain grants
remain explicit. Request p95/p99/rate budgets require reviewed hardware; exact
integer rate comparisons avoid overflow. Doctor now exposes readonly CPU identity.

Focused preflight passes7.244seconds; actual two-check fresh-state measurement
and readonly source-deleted replay passes102.031seconds; impossible p95/uint64
rate and unsupported-hardware checks pass43.562seconds. An initial replay attempt
retains task timeout diagnostics and a test cleanup-order mistake; new command
receipts add chosen timeout and elapsed time for inspection. The full task timeout/SIGINT/explicit-FFI/fork cleanup case passes151.734seconds.
The expanded hardware/budget/bad-response/captured-input-tamper case passes
56.215seconds, including unchanged graph rows after rejected replay. The earlier
4second cancellation fixture expired during preparation; its corrected30second
case measures a long sequence of bounded250ms requests and reaches native code
before the timeout, then interrupts an uncooperative callback separately.
Matching full89 and installed SDK/platform gates remain pending.
Language0.16 syntax/canonical/effect/realm/ownership semantics are unchanged.

Initial frozen0.82 Linux passes87/88 groups: only its strict-C11 usleep fixture
fails. The portable fixture passes Mac/Linux. Initial0.82 Macfull88 passes, but
SDK24 fails a bounded core reader during capsule export; the same compiler and
inputs independently export/read successfully in19.275seconds. Original failure
is retained; portable full Mac/Linux/SDK acceptance remains mandatory. Primary
verified0.81 source/compiler/Git and all47 revisions/all16tables/schema/IDs remain.
Server debugging, dedicated task/editor commands, source concurrency, general
accelerators, source-foreign packages and broader platform delivery remain open.

# Portable0.82 fixture revision (not integrated)

Frozen0.82 sourcebbd93663 passes the Mac server workload group; its Linux group
passes7/8 cases but strict C11 correctly rejects undeclared usleep in the new
forked-heartbeat C fixture. This revision selects POSIX200809L and nanosleep
with time.h. Compiler/runtime/source grammar are unchanged. The portable
fixture now passes on Linux ARM64 in82.464seconds and macOS in80.672seconds,
including project timeout/SIGINT, source profile cancellation, descendant and
sealed-module cleanup. Compiler/runtime source bytes match the first revision
exactly; its complete frozen Mac/Linux/SDK verification remains pending. Original
failed evidence and the verified primary0.81 remain preserved.

# Development cohort0.82 (not integrated)

Bounded server workload metadata drives project native profiles under the real
source/static/dynamic architecture. The readonly plan validates data before
sources/tools and pins definition/helper hashes. The runner owns a fresh
loopback HTTP listener; credentials stay runtime environment values. Profiles
include expected/completed requests, warmup, concurrent phase latency/rates and
actual provider call/memory attribution. Language0.16 is unchanged.

Two public command/preflight cases pass32.613seconds. Native timeout/SIGINT
supervision with an uncooperative FFI callback and forked heartbeat descendant
passes39.094seconds: the group stops, sealed module snapshots are cleaned and
all pre-existing graph rows/schema/IDs remain. Earlier retained failures found
test argument/source-fixture mistakes, insufficient startup time and real
read-only snapshot cleanup; corrected observations preserve the checks.
The matching profiler/workload CTest pair passes125.25seconds, including ordinary
source-profile descendant cleanup. Operator replacement of the workload after
the actual listener starts is rejected in24.152seconds without accepting a
profile or leaving temporary files. The earlier attempt to mutate through a
request correctly failed its missing file capability; that boundary is unchanged.
The full regression, installed SDK24 and Linux validation remain pending.
Public workload task capture/replay, server debugging, source concurrency,
general accelerators and broader platform delivery remain pending.

# Verified primary0.81

The explicitly approved0.77→0.81 transition is complete. Primary full87 passes
1192.790seconds; installed SDK24/375commands/225resources passes815.194seconds.
Actual installed VSIX0.6 works in three fresh private editor hosts; strict
analysis1/2/3 and complete store/schema/local-ID comparisons with0.77 pass.
The frozen source also passes macOS/Linux ARM64 full87, installed SDK24 and
Linux20 live suites. [Evidence](docs/evidence/toolchain-0.81.0.json) records
implementation/source backup identities and preserved graph/Git state.

Language0.16 is unchanged. All47 revisions/all16tables/schema/IDs remain, and
old0.77 source/compiler are retained separately. This documentation update
changes prose/evidence only; compiler implementation and executable are unchanged.
Public server workload profiling is being developed in an isolated0.82 copy.
Concurrency, general accelerators, source-foreign project packaging and broader
platform/development delivery remain pending. Full objective is not complete.

The development sections below retain their original historical observations;
their former pending0.81 gates are resolved by the evidence above.

# Development cohort0.81 (not integrated)

Extension0.6 adds explicit project launches and NEX: Debug Project Component.
Metadata/configuration choices delegate to fresh plan/debug/plan compiler calls.
The final executable/build identity and captured sources must agree; source
entry aliases are pinned, project file mappings preserve workspace spelling and
dirty compiled buffers prevent launch registration. Runtime npm dependencies
remain empty. Node launch/command contracts pass22 cases.

Real0.80-backed preparation passes, with actual DSO source breakpoint/watch and
clean continuation in11.772seconds after correcting /var provider source maps.
The earlier two cases retain mismatched manifest-path spelling assertions, and
a later case retains the expected second stop on a closure defined on the same
source line. The corrected observation removes the breakpoint before continuing.
Matching0.81 editor/project-action CTest groups pass126.81seconds and all five
live editor cases pass27.106seconds. An installed prototype VSIX0.6 executes
NEX: Debug Project Component and the configuration picker in an isolated real
VS Code profile: an original provider breakpoint, typed watch42, DSO execution,
exact Unicode output and exit0 pass12.255seconds. Its SDK/compiler bytes match
the prototype. Linux ARM64 builds this compiler and passes the exact owned
assertion diagnostic regression in54.007seconds. Complete frozen macOS/Linux
regressions, installed SDK and final frozen VSIX validation remain pending.

Frozen0.80 Macfull87 passes1282.18seconds. Linuxfull87 passes86/87: a deferred
reference_error.message borrowed exception.what() after exception destruction.
This source stores an owned string and checks the exact assertion message.
MacSDK24 reaches the last phase but fails on an unused notice-fixture root
inside the deleted source project. The fixture now names the current compiler
file, which remains available during replay; provenance rules are unchanged.
These are retained failures, not accepted0.80 platform/SDK results.

Primary0.77 source/compiler/Git and original47 revisions/all16tables/schema/IDs
remain preserved. All new work is isolated. Primary promotion requires explicit
approval after automatic approval review rejected that separate action. No
source concurrency, general accelerator API, broader platform delivery or full
objective completion is claimed.

# Development cohort0.80 (not integrated)

Replay no longer searches ancestor project manifests. Frozen-input preflight
uses an owned temporary graph; an exact SQLite snapshot preserves its local
IDs under NEW_RUN/state/.nex before execution. New task history/build caches
belong to that state. Explicit output permits readonly receipt inputs. SDK
acceptance also creates its own project boundary. Language0.16 is unchanged.

The first narrower receipt-directory fix passes2 source/project isolation cases
(2.079/12.505seconds); old0.79 fails the same source regression as intended.
The stronger output-owned state implementation passes two source/readonly/ID
cases in4.377seconds, a source-deleted project case in12.418seconds and exact8192
files/replay in67.365seconds. Full87/SDK/Linux validation remains pending. The corrected exact8192-file test passes78.855seconds;
the limit itself is unchanged and includes both package helper resources.

Frozen0.79 source9f09c4b17530f0656a7bbb67ee3b56b305dd02b5 passes86/87 groups
on both macOS and Linux ARM64. Only the fixture resource count fails; native
project cancellation now runs successfully on both systems. No0.79 SDK/platform
acceptance or root integration is claimed.

Frozen0.78 passes Macfull86 and SDK24, but its post-SDK guard detects one added
test-program revision in the primary graph: replay selected an enclosing root.
All original rows remained; the complete48-revision graph is retained separately.
The original47 revisions/all16tables/schema/IDs are restored from the validated
snapshot, and primary source/compiler/Git are unchanged. Earlier failures and
receipts remain separate. This source does not complete the full objective.

# Development cohort0.79 (not integrated)

Project-backed tasks can request package checks under declared configurations.
The task parent captures deployable native/server/web output without executing
the application. Package helpers are current trusted resources; Python bytecode
caches cannot mutate saved inputs. Relative file aliases are accepted only
inside the saved package; ordinary task inputs still reject symlinks. Existing
8192-file/256MiB artifact limits remain. Reviewed custom notice catalogues and project-confined license text can be
captured and pinned through a readonly inspector. Source-foreign package
projection and broader delivery remain pending.

The first3 focused cases pass64.042seconds. A server case retains a
missing-external-notices failure; the new pinned-notice implementation addresses
that integration and passes the server/source-deleted-replay plus readonly,
changed-license and escaping-path cases (2tests,53.095seconds). Frozen0.78 source
ab95fbeed959a87f3688aa225554dd65c614c5ad (785files) is backed up and running
macOS full86 in1296.35seconds; installed SDK checks are running and it is not
integrated. Its first Linux run
passes85/86groups; the new cancellation fixture fails to compile dprintf under
strict Linux C headers. This source uses snprintf/write for that fixture; renewed
Linux cancellation and full87/SDK checks remain pending. Actual0.77 remains
verified separately. No full-objective completion is claimed.

# Development cohort0.78 (not integrated)

Optional project-backed nex.task/1 programs pin architecture and configuration,
retain physical source/package/component aliases, and replay captured namespaces.
Native compilation and execution are separated so the task parent supervises
run/test/profile processes directly. Current toolchain/FFI catalogues remain
required; captures grant no authority. Language0.16 and graph history are unchanged.

The first5project-task cases pass270.882seconds, including real archives/DSOs,
profiles, web output, readonly trust checks, archived graph code and moved replay
after original sources/packages were deleted. A later six-case direct-supervision
cohort passes461.544seconds. Initial cancellation cases retained a physical
/var versus /private/var manifest comparison failure before native execution.
The canonical-parent fix reaches native code: run/profile timeouts and all three
SIGINT cases pass. The test-mode timeout expired before native execution, so its
native-descendant assertion failed; the renewed test allows60seconds for
compilation and execution and still requires a marker from the actual forked
native process. Its result is pending.
Full86/SDK/Linux and final schema/descriptor/example validation remain pending.

Frozen0.77 passes full85 and installed SDK24/369/215 on macOS/Linux ARM64,
19Linux live suites, actual installed VSIX, strict compatibility,6cross
configurations/15artifacts/3iOS links/x64Wine and12real browser/API/restart cases.
Actual root0.77 also passes full85/SDK24/369/215, its own installed VSIX,
compatibility, cross-build/Wine and12browser cases, plus a live SDK debugger/web
preview case in27.322seconds. These are separate post-integration observations.
Root0.76 SDK/source recovery, all47revisions/all16tables and normal
Git HEAD/index remain preserved.

Project package task checks, server workloads, task/editor debugging, source
concurrency, general CPU/GPU/NPU APIs and broader platform delivery remain open.
This source does not complete the full objective.

Historical cohorts below retain their original scope.

# Development cohort0.77 (not integrated)

Project run/test/debug/profile consume the declared binary architecture and
configuration. Pure tests compare the interpreter with their selected backend; pure shared tests compare native, TypeScript and interpreter;
effectful tests execute once with explicit runtime grants. Captured project
traps/profiles carry checked content identities and null persistent graph IDs.
Native debug sessions reuse the final image and its captured provider manifests.
Initial six regression groups pass in141.90seconds. The first live action
cohort passes9cases; a later10-case cohort has one retained DAP test failure
because an unloaded DSO breakpoint was required to be pre-resolved. Its corrected
case requires the actual stop and a resolved breakpoint after loading. Corrected DAP and bounded-output cases pass2tests in32.423seconds. The quoted/backslash/percent/Unicode LLDB/DAP/HTTP case also passes in27.840seconds.
Final frozen full85/SDK/Linux gates remain pending. Explicit FFI actions, one-time effectful execution, relative profile cwd
and source changes between preflighted tests have passed addressed checks.
No completion of the full objective is claimed.

Frozen0.76 source f52e7e69a081c58e2d450095363fb3f55aa0f718 (770files)
passes full84 and installed SDK24 on macOS/Linux ARM64, including18Linux live
suites. Actual0.75 root source8b5f35b9e91544b93c3ff66f760538d5e12c431a
passes83groups, SDK24/361/213, installed VSIX, strict072/075 compatibility,
6cross configurations/15artifacts/3iOS links/x64Wine and12real browser/API/restart
cases. Candidate0.76 source is now promoted to the primary checkout with preserved0.75 recovery; actual root full84/SDK24 are running as a separate scope.

Project task/replay/editor workflows, server workload debug/profile, packaged
image provenance, Windows packages, source concurrency, general accelerators
and broader platform delivery remain open.

The following cohorts retain their original scope and validation history.

# Development cohort0.76 (not integrated)

`project --kind package` consumes the declared configuration and actual built
artifacts, capturing native applications/shared images/runtime/dependencies and
browser dist/notices in one exclusively published package. Exact compiler-owned
image provenance leaves external native licensing requirements intact. A sibling
mkdtemp stage handles literal percent paths without crossing filesystems.

The initial prototype passes five focused groups in184.62seconds, including four
new package cases: moved/source-build-deleted native+browser output, shared
profile identity/cleanup, preflight output/selection rejection and private SQLite
provenance/relocation. Legacy ordinary/foreign packaging and project/shared-image
groups also pass. Final descriptor/schema/SDK additions require fresh validation.
Full84, installed SDK and Linux validation of0.76 remain pending.

Candidate0.75 passed83 groups and SDK24/361/213 on macOS/Linux ARM64,18Linux live
suites, actual installed VSIX, strict072/075 analysis/store compatibility,
6cross configurations/15artifacts/3iOS links/x64Wine, and12real browser/API/restart
cases with a dynamic model in Chromium/Firefox/WebKit. Root0.75 integration has
started with old0.72 source/SDK recovery and a complete graph snapshot; actual
root checks remain separate. Goal completion is not claimed.

Project foreign-pin projection, packaged-image debug provenance, combined
project execution/DAP/editor/task flows, Windows packages, source concurrency,
general accelerators and broader delivery remain pending.

# Verified root development checkpoint0.72 / language0.16

Implementation source `1f24a09cd71ee7cf203359b7a70d03e243505669` (756 files) builds and passes
all80 CTest groups in747.94 seconds. Its installed SDK passes24 phases,
348 commands and213 indexed resources; compiler SHA-256 is
`ae7db3947b533f0b84d90fbf1bb1904b1210214a87e15174def414674ff7e83d`.
[Machine-readable evidence](docs/evidence/toolchain-0.72.0.json) separates actual
root, source candidates, Linux, SSH compatibility and research scopes. Final
overview/quickstart/research evidence changes no compiler, runtime, grammar or
indexed resource. Exact test sources and original failures remain retained.

Project `static` edges consume real code-only archives under checked private
compiler/toolchain/runtime contracts, with concrete exports, consumer generic
instantiations and one runtime in the final application. Retained completion
records bind ABI data and captured archives. Module-based frozen source origins
cover provider entry/import aliases; live source-deleted library watches and
moved core capsules pass. Historical capsule basenames remain readable.

The current source passes Linux ARM64 full80,17 live groups and source-free,
network-disabled SDK24/348. Mac candidate full80 initially had one old temporary
filename assertion; the stronger manifest-origin test passes all13 module cases
with unchanged production code. Actual root then passes a fresh complete80 run.
The Mac candidate SDK's omitted optional Wasm-linker selection is retained as a
configuration failure; explicit LLVM22.1.8 selection and actual root defaults pass.

Actual root-SDK checks produce15 cross artifacts in6 configurations and3 final
iOS links; an archive-dependent x64 application runs under Wine. A static-model
HTTP server and source-model browser client pass12 cases across3 browser engines.
Installed VSIX0.5 passes fresh-profile language/debug checks. Genuine0.71/0.72
checks preserve strict analysis1/2/3 responses apart from compiler identity and
all isolated store rows/schema/IDs. All47 primary revisions/all16 tables/schema,
local identities and normal Git HEAD/index remain unchanged.

Separate Astra Linux1.7.4/old-glibc development checks include a complete SDK24
and targeted native toolchain groups. Their hashes are distinct from this root.
Manual Mac/Linux two-DSO probes establish one runtime, managed callbacks/values,
file aliases, checked failure cleanup and relative relocation. General compiler
DLL mode, dynamic debug/core/profile/package integration, source concurrency,
accelerators and the remaining development chain are still pending.

The following historical statements retain their original source/compiler scope.

# Verified root development checkpoint0.71 / language0.16

Implementation source `1a3da612e0f3c10e1f737802ef4c580723e27311` (750 files) builds and passes
all79 CTest groups in 747.49 seconds. Its installed SDK passes24 phases,
344 commands and209 indexed resources; compiler SHA-256 is
`df5a138402e91abd21e3ec83d4d3550f96f50cec591a61377e1958aecadbb843`.
[Machine-readable evidence](docs/evidence/toolchain-0.71.0.json) separates original
candidate735, actual root750, installed IDE, cross-target, real-browser and
historical CIX scopes. The final overview/quickstart/notice delta changes no
compiler, grammar, manifest, test, example or indexed resource; full-suite
receipts retain their exact source cohort.

The optional nex.project-build/1 manifest describes source/executable/archive/
server/web components, disjoint physical roots, direct architecture edges and
profile/CPU/ABI/toolchain configurations. Readonly planning checks captured
sources, locks, entry contracts and toolchain fingerprints without graph writes
or tool execution. Build consumes those Programs and rechecks native tooling.
Thirteen focused cases include the reproduced package-alias boundary bypass,
rejection paths, actual archive host linkage and browser server-code exclusion.
Only source dependency linkage is implemented; emitting a static archive is
separate from consuming it as a dependency. DLLs, full-static policy, resolved
binary dependency reports and source concurrency remain pending.

The exact original735 compiler cohort passes full79 and SDK24 on macOS and
Linux ARM64. Linux completes16 live suites and a source-free/network-disabled
SDK run. Linux build/install ELF files differ in one trailing DT_RUNPATH byte;
all other bytes are verified equal after normalizing that declared padding.
The root750 fixture/documentation follow-up changes two indexed guides, without
changing compiler/runtime/indexed code from735; its actual SDK verifies all209
resources. The final unindexed overview delta retains these scopes.

Six checked project configurations produce9 Intel/Windows/iOS artifacts and3
final iOS linked images. A project PE returns42 under isolated x64 Wine.
An actual-root project builds one shared model, HTTP server and production
client, then passes12 cases across Chromium/Firefox/WebKit, including restart
persistence, clean shutdown and no forbidden redirect. Missing dependency and
mismatched server ABI requests reject. These are build/runtime observations,
not universal device or performance guarantees.

Installed VSIX0.5 passes actual private-profile LSP/native debugger checks.
Nine fresh root SDK PE cases and17 Wine scenarios retain their original fixture
graph snapshots. Genuine0.70/0.71 comparisons preserve analysis1/2/3 payloads
apart from compiler identity, revisions, interpreter results and every isolated
store row/schema/ID through complete normalized API snapshots. Initial direct
Python-readonly WAL inspection failures and a fixture-path driver correction
are retained; they are not accepted product failures or migration evidence.
The primary47-revision graph, all16 tables/schema, IDs and normal Git HEAD/index
remain unchanged. CIX GPU/NPU evidence remains explicitly toolchain0.70 and
fixed-fixture FFI, separate from general acceleration support.

The following historical statements retain their original source/compiler scope.

# Verified root development checkpoint0.70 / language0.16

Core source 74a013fc876cfcb725608c9ce490e71720aeb76b (719 files) builds and passes all78 CTest groups
in 752.95 seconds. Its installed SDK passes23 phases/332 commands/198
indexed resources; compiler SHA-256 is 88273ccf08e1f73b8ecd08130514c6d00cb487eeaad5a49960cbf36148506701.
[Machine-readable evidence](docs/evidence/toolchain-0.70.0.json) separates the
candidate macOS/Linux/installed-IDE and actual root execution scopes. The final
README/STATUS/PLAN/evidence-only delta changes no compiler, grammar, manifest,
example or indexed resource and does not relabel earlier executions.

Explicit analysis/3 uses exact lexer-word ranges and actual bound source
signatures, generic arities/bounds, lexical values, aliases and trait members.
Builtin types/constraints have null physical targets; syntax words have null
descriptions and targets. This fixes the genuine0.69 `id<i64>(42)` false-definition
counterexample. Generic functions show source templates; concrete field reads
can show their checked instantiated type. The model-independent prompt, schema,
manifest and guides describe these distinctions and explicit limits.
33 compiler/stdio cases and two actual Node-client/contract wrappers cover source
and graph isolation, UTF-16/CRLF, conflicts, cancellation and16KiB/8MiB limits.
Five genuine old/new compiler cases preserve canonical revisions and both strict
legacy analysis/1 and analysis/2 payloads apart from compiler identity. Source
language0.16 and canonical formats require no migration.

The original implementation candidate passes full78 and installed SDK on macOS and Linux
ARM64. Linux completes16 live suites and source-free/network-disabled SDK
acceptance. Installed Python LSP sends29 messages and the Node client17 requests;
both verify exact aliases, generics, members, signatures and builtin no-definition.
Only tests/editor_lsp_host.js changes from the original66280d5d candidate to
the corrected74a013fc source: the first actual-IDE test compared raw plaintext
to VS Code codeblock markup. The corrected driver verifies rendered expected
text. All compiler/client runtime files, CTest suites and198 indexed resources
are unchanged; original full-suite receipts keep their66280d5d scope. The initial
IDE failure and dependent exits before root mutation are retained.
The Linux installed ELF delta is checked separately from byte-identical compiler
claims. Actual installed VSIX0.5 in VS Code1.142.0 uses
private macOS ARM64 profiles and verifies the same descriptions, unsaved imports,
explicit CRLF/Unicode repair, lifecycle, native watches and indexed value pages.
All npm dependency records remain unchanged; only extension own version fields
change. Fresh root-SDK checks retain9 Windows PE build graphs and17 x64 Wine
successes. Wine is distinct from actual Windows OS/ARM64 execution. All47 root
graph revisions, all16 tables/schema, local IDs and normal Git HEAD/index remain
preserved. Process-scoped test sleep assertions change no global power settings.

Completion/rename, parser recovery/incremental indexing, closed-file/cross-workspace
coverage, Studio, cross-provider coding/token measurements and broader platform/
application acceptance remain pending. Earlier mobile/browser/distribution
results retain their original cohorts. The full objective remains open.
The following historical0.69 statements retain their original source/compiler scope.

# Verified root development checkpoint0.69 / language0.16

Core source 787525a23c5fb313df2298d1532463d7e47b5728 (717 files) builds and passes all78 CTest groups
in 743.77 seconds. Its installed SDK passes23 phases/332 commands/197
indexed resources; compiler SHA-256 is ba4878efe8cafaae451e9eb62139d0f0adceb258884eefe9adeff6bb55e30f96.
[The machine-readable evidence](docs/evidence/toolchain-0.69.0.json) retains
separate corrected candidate/macOS/Linux/installed/root scopes. The final
README/STATUS/PLAN/evidence-only delta changes no compiler, grammar, manifest,
example or indexed resource and does not relabel earlier executions.

Readonly analysis/2 now projects actual parser/module-binder type, generic,
trait/member, implementation, import-alias and enum-variant identities. Strict
analysis/1 and analysis/2 wire shapes, source language0.16 and canonical formats
are unchanged. Five genuine0.68/new-compiler comparisons retain equal canonical
revisions and legacy payloads apart from compiler identity.25 compiler/stdio
cases,25 Node contracts and two actual-client/contract cases exercise scope,
UTF-16, conflicts, cancellation, result limits and no source/Store writes.
Installed SDK LSP acceptance sends23 messages and the Node client11 requests.
Reference offsets are grouped once per file; synthetic complete-result equality
and timings are separate from compiler/application performance claims.

The same corrected source's first Mac full run (v2) overlapped observed clamshell,
maintenance sleep and a later full wake. It retained75 passed groups and failures
in Windows targets/tasks/toolchains with timeouts; its CTest elapsed time was
23597.55 seconds. After wake, the same compiler/source passed all26 cases in
those three groups, without source changes. Accepted Mac full validation uses v3; the same binary then passes8
fully enabled Wasm cases and installed SDK v4 with the supported explicit
NEX_WASM_LD selection. The earlier v3 SDK stopped at command220 with
E_WASM_TOOLCHAIN because its default linker was not configured. This configuration
error and all before-mutation prerequisite failures are retained.
Tests use temporary process-scoped idle/system-sleep assertions; global power
settings were unchanged. Original power timestamps, failed receipts and initial
root prerequisite/startup failures are retained. These are separate execution
scopes and are not relabeled as successful first runs.

Corrected candidate0.69 also passes full78/SDK on macOS and Linux ARM64. Linux
finishes16 live suites and source-free/network-disabled SDK acceptance. The
first candidate fd1262fe remains explicitly unaccepted: a broad extension-version
replacement inadvertently changed three dependency requirements in npm lock.
Its in-progress Mac/Linux tests were intentionally stopped and the waiting IDE
job ended before packaging. Only this task's identified CTest process and exact-
mount Docker container were stopped. The corrected candidate787525a2 changes
only npm lock; all dependency records match the previous verified lock and only
the extension's own version fields change. Full corrected checks use new v2
controllers; original interrupted logs and failures remain retained.

Actual root SDK VSIX0.4 runs in VS Code1.142.0 using
private macOS ARM64 profiles. Typed parameter/alias references, exact trait
method contract definitions, imported unsaved-buffer invalidation, explicit
CRLF/Unicode repair, lifecycle and native debugger/page checks pass. Fresh root
SDK Windows checks retain9 original graph snapshots and17 x64 Wine successes;
Wine remains distinct from actual Windows OS/ARM64 execution. All47 root graph
revisions, all16 tables/schema, local IDs and normal Git HEAD/index are preserved.

Dedicated generic/member/alias hover, closed-file/cross-workspace indexing,
completion/rename, recovery/incremental parsing, Studio and broader platform/
application acceptance remain pending. Earlier mobile/browser/distribution
results retain their old compiler/source cohorts. The full objective is open.

# Verified root development checkpoint0.68 / language0.16

Actual root source 13a9d72d1bd9aa017deb010e84932dd1f6b29817 (716 files) builds and passes all78
CTest groups in 758.09 seconds. Its installed SDK passes23 phases,
332 commands and197 indexed resources. Root compiler SHA-256 is
76eacede4038dd3f7362bd47a103d270c612b795900561a3786ef5204f5fd572.
[Machine-readable evidence](docs/evidence/toolchain-0.68.0.json) separates
candidate, installed, resumed Linux and actual root execution scopes. The final
README/STATUS/PLAN/evidence-only delta changes no compiler/runtime/grammar/
manifest/example or indexed resource; it does not relabel earlier executions.

The source13a9d72d candidate has its own macOS full78/SDK23/332/197 and Linux
full78 receipts. Linux completed14 live suites before its Docker container ended
with137 during live-string-debug. Docker Desktop was later observed stopped.
The exact source/compiler/SDK bytes were retained; two remaining live suites
passed in a fresh identical-image container after Desktop startup, followed by
source-free/network-disabled SDK23/332/197. Original failed controllers/report
and the interrupted zero-byte live log remain retained. The combined16live
coverage is not a claim of one uninterrupted run. Dependent first root jobs
stopped before mutation; successful root verification uses separate v2 jobs.

Opt-in analysis/2 adds exact declaration/read/write/call/pattern intervals with
checker-resolved targets. Default analysis/1 and its strict schema are retained.
Functions/values, lexical scopes, nominal constructors/patterns and structure
fields have checked reference lookup; result limits, declaration inclusion,
deterministic deduplication, cancellation and captured-context conflicts are
explicit. Type/trait/import-alias reference syntax and broader workspace
coverage remain pending. Source language0.16 and graph formats are unchanged.

An actual old/new compiler counterexample proves the editor wildcard correction:
`match ... {_=>_}` does not declare a new `_` that shadows an outer ordinary
value. The corrected location points at the outer declaration; both compiler
versions evaluate42 and produce the same canonical revision. Field/pattern/
wildcard fixtures additionally agree in native/reference/TypeScript execution.
Nineteen compiler/stdio cases,25 Node contracts and two actual-client/contract
cases cover scope, Unicode, result limits, contexts and source/history isolation.
Installed SDK checks send16 Python/server messages and8 Node/client requests.

Actual root SDK VSIX0.3 runs in VS Code1.142.0 on macOS
ARM64 using two private profiles. It verifies references, unchanged-entry queries
immediately after imported-buffer edits, repaired imports, explicit CRLF and
Unicode, diagnostics/navigation/outline, restart/disable/enable and close.
Physical source bytes remain unchanged and source analysis creates no graph.
Native debugging verifies source breakpoints, stack/scopes, scalar/trait pure
watches, unchanged stop identity,32768-item list/4MiB byte roots with bounded
1000-child pages, continuation and exit0. The user's profile is not modified.

Fresh root SDK Windows checks retain9 PE outputs, each original build context's
graph snapshot and source where present, and17 x64 Wine cases. Actual Windows
OS/ARM64 execution and the failed filesystem prototype remain separate/pending.
All47 root revisions, all16 tables/schema, local identities and normal Git HEAD/
index are preserved. Earlier SDKs and source/recovery cohorts remain available.

Completion/rename, parser recovery/incremental indexing, remaining reference
syntax/workspace coverage, Windows/physical-platform adapters, signing and the
rest of PLAN.md remain open. This is verified development progress, not a
release or completion of the full language/development-chain objective.

Earlier milestones retain their original identities and scopes below.

# Verified root development checkpoint 0.67 / language 0.16

Actual root source 4fbd3c6775702a76c16a8d93611ef65a2df0506c (714 files) builds and passes all 78
CTest groups in 741.94 seconds. Its installed SDK passes 23 phases,
332 commands and 196 indexed resources. Root compiler SHA-256 is
aa76f1768eae9b9f136c156079a70f045cedfad4375f731e9744db39355ff628.
[Machine-readable evidence](docs/evidence/toolchain-0.67.0.json) records exact
source/compiler/report scopes. The final README/STATUS/PLAN/evidence-only delta
preserves all compiler/runtime/grammar/manifest/example bytes and all 196 indexed
resources; those overview edits do not imply another full-suite execution.

The separate 9cb7e996 implementation candidate passes all 78 groups on macOS
and Linux ARM64. Each installed SDK passes 23 phases/332 commands/196 resources;
Linux also passes 16 live suites and runs acceptance with no source checkout
or network. Root source differs from that candidate only in the unindexed
actual-IDE host test, which explicitly sets/asserts CRLF and restores original
EOL before saving. Its own full78/SDK and actual-IDE results are recorded here.

Readonly compiler analysis and stdio LSP provide unsaved diagnostics, checked
types, declaration outlines and cross-file function/value definitions. Fourteen
compiler/stdio cases cover Unicode, cancellation, lifecycle, rejected input and
source/history isolation. The Node client has 22 contracts and two actual-client/
contract cases; installed SDK checks exercise both Python/server and Node/client.
Language 0.16, canonical graph formats and language semantics are unchanged.

The actual root SDK packages and installs VSIX 0.2 into a private extension
directory. Real VS Code 1.142.0 on macOS ARM64 passes
unsaved Unicode/explicit-CRLF error/repair, hover, cross-module definitions,
outline, restart, disable/enable and close. Physical sources remain unchanged
and language analysis creates no graph. A second private profile verifies native
breakpoints, stack/scopes, pure scalar/trait watches, unchanged stopped identity,
32768-item list and 4 MiB byte roots with bounded 1000-child pages, continuation
and exit 0. The user's editor profile is not modified.

Fresh root SDK Windows checks retain nine x86-64/ARM64 PE outputs with each
original build context's graph snapshot and source where present. Seventeen
x86-64 Wine cases pass. This does not verify actual Windows OS/ARM64 execution;
the failed filesystem prototype remains unavailable and is retained separately.

All 47 root revisions, all 16 graph tables/schema, local identities and normal
Git HEAD/index are preserved. Earlier SDK/source cohorts and failed attempts
remain retained: the 0.66 lifecycle/protocol failures were fixed and checked;
its first SDK runs failed from a missing Python import after full77 passed.
The initial 0.67 IDE collector omitted its native-pages flag, and one owned
waiting collector was terminated before IDE execution to correct that flag.
Successful corrected runs do not relabel those original failures.

Completion/references/rename, parser recovery/incremental indexing, broader
IDE/Windows development, physical-device validation, signing and the remaining
PLAN.md language/runtime integrations stay open. This is verified development
progress; no release or full-objective completion is claimed.

# Completed predecessor 0.66: language server and lifecycle repair

Source 126b0d59 adds the SDK import fix to the lifecycle-corrected 158fb058
source. Fourteen focused cases and both corrected installed SDKs pass
23 phases/330 commands/185 resources. Their compiler/runtime bytes remain
those of the original e8f4bbef implementation, whose macOS/Linux full77 and
Linux 16 live suites passed before the first SDK failure. These are distinct
cohorts; exact proof is retained in build/lsp-066-scoped-verification.json.

Earlier milestones retain their original source/compiler scopes below.

# Language contract documentation: toolchain 0.65 / language 0.16

Source 35c1a438 corrects five language-pack documents: four indexed guides and
the delivered llm/README.md. The specification/protocol now match actual source
type/trait/implementation patches, snapshot-scoped identity aliases, stopped
pure expressions, owned streaming files, concrete source FFI and target scopes.
Historical introduction versions remain distinguished from current capabilities.

The matching macOS and source-free/network-disabled Linux ARM64 SDKs each pass
23 phases, 329 commands and 180 indexed resources. A separate 41-command
workflow verifies valid and rejected graph transactions, native/interpreter/
TypeScript agreement, alias preservation, exact UTF-8/NUL streaming bytes and
explicit migration of a genuine 0.15 snapshot with old revisions/IDs retained.
See docs/evidence/language-contract-0.65.0.json for exact source/report digests.

Compiler/runtime/grammar/manifest/examples remain byte-identical to the prior
0.65 implementation. The full76 and Windows17 execution receipts below retain
their original implementation scopes. The final README/STATUS/PLAN/evidence
delta changes no indexed resource. All47 root graph revisions/all16 tables,
schema and Git HEAD/index remain preserved. Earlier root SDKs remain retained.
Cross-provider evaluation and the unfinished integrations in PLAN.md remain
pending; this documentation milestone does not complete the broad objective.

# Toolchain0.65 root verification

Current root toolchain0.65.0/language0.16 uses source618efe51 (698 files before
the final overview/evidence-only delta). Actual root build/full76 and its
installed SDK23/329/180 pass. Candidate macOS full76/SDK23/329/180 and native
Linux ARM64 full76/16live/source-free SDK23/329/180 pass independently. Exact
compiler/source/report identities are in docs/evidence/toolchain-0.65.0.json.

Windows environment and explicit target SQLite pass x86-64/ARM64 debug/release
cross-builds, static host/archive linkage, caches and source replay. Fresh
installed-root SDK output retains9 PE files;17 x86-64 Wine executions verify
Unicode environment/database paths, separate-process persistence, three binary
principal partitions and capability failures. ARM64 and actual Windows OS
execution remain unverified. Standalone owner defaults to local; an explicitly
empty owner is invalid, and no default database path is granted.

Windows filesystem/resource operations remain unavailable. The direct prototype
cross-compiles but its Wine run passes16 ordinary/system groups and fails5
required filesystem checks; fixture removal also fails. These are retained
failures, not a passing platform adapter. Native Windows/NTFS validation,
HTTP/foreign/plugin adapters, Windows development tools/packages/distribution,
physical-device execution and signing remain pending.

All47 root graph revisions, all16 graph tables/schema and local identities are
preserved. Original Git HEAD/index remain unchanged. The final overview-only
delta preserves compiler/runtime/grammar/manifest/examples and all180 indexed
resources. This is verified development progress, not full objective completion.

Earlier milestones retain their distinct source/compiler scopes below.

# Toolchain0.64 root verification

The earlier0.64 root cohort is toolchain0.64.0/language0.16. Its implementation source is
d39fd643 (691 files); actual root build/full75 and its SDK23/329/178 pass.
The corrected four-document language pack ec5f050b preserves all compiler/runtime
bytes and passes separate Mac/Linux SDK23/329/178 checks.
The native Linux ARM64 implementation passes75 groups,16 live suites and a
network-disabled, source-free SDK23/329/178 workflow. Source/compiler identities
and the final overview-only delta are tracked in docs/evidence/toolchain-0.64.0.json.

Windows GNU/UCRT core cross-builds produce debug/release PE/COFF and GNU archives
for x86-64 and ARM64. Fresh installed root SDK builds pass8 PE checks in literal
Unicode/percent paths and6 x86-64 Wine compatibility executions. Overflow logs
map to exact NEX source operations; wrong-build logs stay unmapped. Wine under
Linux emulation is separate from Windows OS and ARM64 execution. The initial
ARM64 Wine attempt timed out during initialization and remains unverified.

All47 root graph revisions and every graph table are preserved. Original Git
HEAD/index are unchanged. Windows-hosted development, platform I/O/plugin/package
adapters, actual Windows/physical-device execution and release signing remain
pending. This is verified development progress, not a completed full objective.

Earlier detailed milestones and their distinct evidence cohorts follow.

# Verified root development checkpoint0.63 / language0.16

The actual root compiler is rebuilt and passes all74 CTest groups. Its installed
SDK passes23 phases/329 commands/176 indexed resources with compiler SHA256
2d84c38b202cdd617efa4603a8a51e23352e7b928728656ab82a620eadadcae1.
Root full74 uses tree9d346edf; the one-file corrected LLM prompt is verified in
SDK source treeb6324fa8. Compiler/runtime source is unchanged by that prose delta.
This final status update changes only unindexed overview/evidence documents.
[Exact evidence](docs/evidence/toolchain-0.63.0.json) separates these cohorts.

The matching Linux ARM64 implementation4c1edca2 passes74 groups,16 live suites
and23 source-free/network-disabled SDK phases/329 commands/176 resources.
The installed root SDK freshly generates both native mobile projects offline;
all five non-index assets are byte-identical to the actually tested iOS/Android
API applications, while the operator's HTTPS index configuration has its own
recorded derivation. Generation and actual native execution remain separate.
All47 root graph revisions and every table remain unchanged through integration,
SDK acceptance and the fresh mobile generation. Earlier SDKs/frames are retained.

Actual Simulator/emulator/API/browser validation is recorded below. Windows
NEX target/host support, physical-device/Intel validation, native mobile bindings,
release signing and broader distribution gates remain pending. The separate
manual Windows PE prototype does not make Windows a supported NEX CLI target.
This is a development checkpoint, not a release or full objective completion.
Historical records below keep their original time and validation scope.

# Development integration0.63 / language0.16

The source includes explicit iOS archives, generated native WebView projects and
explicit HTTPS API hosting. The tested implementation is Git tree4c1edca2,
commit ee207153aaa64aa8ad37fc2970b4e25632854eb9. This documentation records its
scoped results; root integration has its own pending build/full74/SDK23 checks.
[Machine-readable evidence](docs/evidence/toolchain-0.63.0.json) preserves exact
source/compiler identities and remaining gates.

The implementation passes all74 macOS/Linux ARM64 CTest groups. Its installed
macOS SDK passes23 phases/329 commands/176 indexed resources. The same-source
HTTPS client passes three browsers with native API restart. Actual iOS27.1
Simulator XCTest passes1 case without failures/skips; actual Android16/API36
ARM64 WebView passes7 API/UI checks. iOS long credentials use runtime native
keyboard paste; failed earlier input automation attempts remain retained. Final
Linux live/source-free SDK acceptance and the root's own gates remain pending.

The UI is TypeScript/React inside a native WebView. Native MLIR iOS archive
embedding, physical devices/Intel, Windows, native plugin bindings, production
PKI and release signing remain separate work. Language0.16, graph canonical
formats and stored history do not change. Historical records below retain their
original time/scope; an old pending statement does not override this record.

# Isolated development0.62: mobile projects and local iOS URL policy

A first prototype builds an actual Simulator .app and Android debug APK from
NEX-generated React assets using Capacitor8.5.3. Native dependency hashes, exact
original web assets and build logs are recorded separately. The first iOS run
survives and paints its document, but shows E_UI on capacitor://localhost
relative links. Its default screenshot also selected a secondary inactive screen;
the primary display establishes the actual adapter error. These failures are
retained rather than reported as successful mobile UI acceptance.

The candidate adds a pinned mobile project generator, local checksum-checked
iOS frameworks, no inherited Android local.properties, offline generation and
bounded provenance/logs. It adds a scoped relative-route/asset policy for the exact
capacitor://localhost origin and rejects opaque-origin network requests. Four
focused artifact/input/policy cases pass; the full current build, installed SDK,
actual corrected mobile UI and browser regressions remain required. Language0.16
and canonical forms are unchanged. See docs/mobile.md.

# Isolated development 0.61: explicit iOS archives

The candidate adds macOS cross-compilation of debug/release static libraries for
ARM64 iOS devices and ARM64/x86-64 iOS Simulator. Explicit versioned targets and
matching Xcode SDK settings are required; platform, architecture and deployment
range are checked, followed by a real compiler ABI probe. An ARM64 target on an
ARM64 Mac is still foreign. It cannot use local run/test/debug/profile/package,
host dependencies, Tracy profile builds or source foreign-library loading.

The first focused run builds and links all six target/profile combinations,
checks every object's platform/minimum OS/architecture, verifies cache/revision
reuse and rejects wrong SDK/target/deployment inputs. One package refusal fixture
failed earlier with E_NAME because it omitted its nonstandard entry; the corrected
fixture explicitly selects answer and expects the backend E_TARGET refusal for
unsupported application output. Local execution commands retain E_TARGET_RUN.
Matching final focused and full regressions
are required before promotion. No simulator/device application or execution is
claimed. Language0.16 and canonical formats are unchanged. See docs/ios.md.

The verified root remains0.60.2. Its evidence below belongs to the exact source
identity recorded there and does not automatically validate this candidate.

# Verified development checkpoint 0.60.2 / language 0.16

Updated 20 October 2026. The compiled and tested source is the exact 666-file
Git tree `1f7c88310352fcd563cb153f418f12d27f776945`, backed up as commit
`983051eeed369b0a49e158208bd0ba651e10f01d`. The following documentation update
records those completed checks; it does not change their source identity.
The machine-readable record is [toolchain-0.60.2.json](docs/evidence/toolchain-0.60.2.json).

- The actual root compiler was rebuilt with `cmake --build build -j 4 --clean-first`.
  All 72 CTest groups pass: 593 Python cases and 9 explicit skips, 1385.71 seconds.
- Its installed macOS ARM64 SDK passes 23 phases / 329 commands / 161 indexed
  resources, including build/run/test, task repair, profiling, real LLDB/DAP,
  source-deleted replay, API/storage/HTTP, contracts and browser builds.
- A matching installed VSIX passes in actual VS Code 1.142.0 with this SDK:
  breakpoints, scopes, watches, large list/byte tail pages, continuation and exit.
- Fresh generated React production applications pass 18 browser cases and three
  development renderer-rejection cases across Chromium, Firefox and WebKit.
  Three production skips are explicitly development-only cases. The scalar Wasm
  example also passes all three engines.
- Matching macOS and Linux ARM64 SDK distributions each pass all 23 phases after
  relocation and archive restoration. Linux runs in a source-free runtime image.
  An independent Linux core capsule reader restores exact `Я🧠2` with neither
  original source nor original build mounted, without running the inferior.
- The Linux compiler/runtime/test baseline is tree `b603e2392ab8f473209944a188bbd0c4a92ba145`:
  full 72 groups, 593 Python cases, 16 live suites and SDK23/329 pass. The final
  tree changes only two Python packaging files. Their actual ELF alias/collision
  probe and fresh installed/relocated/restored SDKs pass separately. The actual
  macOS root independently reruns all 72 groups from the final tree.
- Same-graph JS/Wasm measurements record load and first-call costs separately
  from nine alternating warm samples for each of two scenarios. They establish
  measurements for the recorded machine and inputs, with no general superiority
  or token-savings claim.
- All root graph tables are unchanged across this promotion and its acceptance;
  all 47 revisions remain present. The earlier 0.58.2 graph-probe incident and
  its history-preserving repair remain recorded below and in recovery evidence.

The 0.60.1–0.60.2 corrections cover Docker CSV bind paths, literal-percent Wasm
link output paths and separate relocation of ELF multicall aliases. Original
failed attempts remain retained alongside the corresponding passing controls.
Language 0.16 and graph canonical forms are unchanged.

Native iOS/device and simulator targets still return `E_TARGET`, including with
explicit installed Xcode SDKs. The host query finds no installed simulator
runtimes. Android NDK/runtime integration and Windows support remain unfinished.
Cross-built Intel artifacts and emulated historical tests do not establish
current physical Intel execution. General Wasm applications/WASI/heap values/f64,
GPU integration and other unfinished PLAN items retain their stated limits.
This checkpoint is not an all-platform release or completion of the whole goal.

## Historical captures

The entries below describe the state when captured. A pending check in an older
entry may have a later result in the current checkpoint; its original scope and
failed attempts are preserved.

# Development0.60: bounded scalar WebAssembly draft

The isolated implementation adds a real wasm32 MLIR/LLVM backend, pinned
compiler-rt multiplication support, a no-import module and a checked BigInt
wrapper. Seven draft backend tests pass, including boundary/seeded arithmetic
agreement, exact failure sites, evaluation order, short-circuiting, bounded
loops/recursion, 100 repeated trap recoveries, strict inputs, cache repair and
source-deleted export. The installed workflow has a23rd Wasm phase; thirteen
archive/workflow contract tests pass. Actual SDK23 acceptance remains pending.

The committed browser example passes real Chromium, Firefox and WebKit checks
for exact integers, overflow, invalid input, recovery, keyboard control and a
narrow viewport. These are mutable-draft checks, not frozen-source/full-platform
acceptance. The full72 regression, matching installed/portable SDKs and JS/Wasm
measurements remain required. The language stays0.16; no migration is introduced.
General Wasm applications, WASI, heap values, f64 and GPU remain unsupported by
this adapter. The existing TypeScript/React application path remains available.

Root0.58.2 passes full70 (577 Python cases) and SDK22/317. Its graph audit
retains the original strict failure from three owned probes that discovered the
parent project. A guarded CLI restore returns HEAD to its original revision and
preserves every original and probe history row. Subsequent probes use explicit
project manifests; the root graph is not described as unchanged across that
incident. Separate frozen0.59 focused and actual macOS moved-core checks pass;
its full71 and platform/SDK gates remain pending at this capture.

# Development0.59: native core capsule draft

The isolated implementation adds explicit export/read directories, bounded
file inventories, original/physical image identities and trusted SDK readers.
An earlier Python copying/projection prototype passes against a retained0.58.2
build. The later historical-alias binding is not part of that prototype proof;
matching0.59 compiler/live acceptance remains pending. Twelve SDK archive/workflow contract checks
pass. Matching C++ build, actual moved-core/source-deleted tests and complete
platform/SDK gates remain pending. No language or graph migration is introduced.

The preceding0.58.2 frozen638 files pass Linux full70 (577 Python cases),
all15 live suites and source-free SDK22/317; macOS focused/live/SDK22 and both
moved/restored portable workflows pass. Linux portable moved/restored22/310 also passes. The exact638 source is
promoted to the root, whose clean build passes and full70/SDK22/graph-preservation
gates are running separately. These scopes do not validate the new capsule code.

# Development0.58.2: bounded kernel ELF mapping

A real Linux kernel SIGABRT ELF core was correctly refused by0.58.1 because
LLDB exposes no filename through its memory-region API. The isolated correction
reads the core's own bounded NT_FILE metadata and binds its PC mapping to the
retained content-addressed build directory, while keeping loaded-module checks.
A pure Python reader prototype restores exact caller watch Я🧠2 from the
source-deleted core and rejects a different executable. It uses the original
unchanged manifest and an older compiler for the stable watch protocol; this
is not a matching0.58.2 installed-SDK result. Eleven metadata/string provider
cases pass, including malformed/ambiguous/nonregular inputs and both byte orders.
Current C++ directory binding, matching compiler/live/full/SDK checks are pending.

Frozen0.58 macOS full70 passes571 Python cases with six explicit skips in
1433.61s. Frozen0.58.1 macOS SDK22/317 passes in367.378s. Its five matching
installed core/image controls pass on each macOS/Linux host, and Linux full70
is running. These separate scopes are retained; no root promotion or release
is claimed. Portable core capsules and unique optimized-PC attribution remain
pending with the wider language/platform/development-chain objective.

# Development0.58.1: Linux core image correction

The frozen0.57.1 Linux ARM64 full69 regression passes, but its additional
live-debug_image negative control fails: LLDB minidump resolves a PC through
another supplied executable and SBModule equality alone accepts wrong-source
attribution. Frozen0.58 is not promoted. Its macOS SDK22/317 commands pass;
its macOS full70 remains a separate running gate.

The isolated correction checks the core-recorded mapping and rejects ambiguous
same-path images. The original failing Linux test and an additional executable
replacement at the same path pass against a formatter overlay. This is a
prototype, not a matching installed-SDK result. Linux LLDB saves an MDMP
minidump here; the earlier ELF-only input check is extended with bounded
minidump header/directory/64-bit system-information validation. Matching build,
full regression, installed SDK22 and platform gates are pending.

An actual controlled macOS SIGABRT core restores caller-frame Unicode/list
values after source deletion with unchanged graph/core bytes. Its raw Mach-O
stop metadata does not retain a signal cause; none is inferred. Portable core
capsules and unique optimized-PC attribution remain pending. No release or
full language/development-chain completion is claimed.

# Development0.58: retained-build read-only native core reports

An isolated source extension adds `nex core`, matching compiler/build/source/image
checks, bounded LLDB stacks and pure exact watches, and a22-phase installed SDK
workflow. Three normal tests pass. The initial direct SBCommandReturnObject
status bug was retained and corrected; a live source-deleted Unicode/list watch
and wrong-image negative control then pass. Subsequent header/image-report
changes need their current focused/live/full/SDK checks. No release is claimed.

The preceding615-file0.57 baseline now also passes the optimized macOS compiler
full68 and installedSDK21. That baseline does not include0.57.1's frame-image
guard. Its CTest wall time includes host sleep and is not a performance result.
Current622-source0.57.1 initial macOS full/SDK attempts retain original-deadline
task failures alongside host sleep observations; their rechecks remain pending.
Full language/platform/development-chain acceptance is still open.

# NEX implementation status

## Toolchain 0.57.1: loaded-frame image binding under development

A negative core control exposed incorrect attribution when LLDB loads the
core's executable beside another selected NEX image with identical function
names. The candidate checks actual loaded SBModule identity and physical path
before frame values, operation candidates or exact watches receive the selected
manifest's revision. Source language0.16, runtime ABI and canonical forms remain
unchanged. Current focused/live, full69, SDK21 and platform validation are
separate required gates; no accepted release is claimed.

The preceding frozen615-file 0.57.0 passes all68 macOS ARM64 groups (566 Python
cases, four explicit skips;1658.87s) and all68 Linux ARM64 groups (1335.62s).
Its installed macOS SDK21/312 commands and actual installed VSIX page checks
pass. Both moved/restored macOS SDK21 workflows pass312 commands each with
source/dependency reads and SDK writes denied by the kernel (915.134s total).
Linux live13, source-free SDK21, portable SDK and optimized host checks are
recorded separately. Emulated Linux x86-64 currently retains three task-FFI
timeout failures; no passing current x86-64 matrix is claimed.

Core feasibility probes on macOS/Linux ARM64 read small modified-memory dumps,
including native frames and watches. macOS source-deleted replay retains exact
Unicode/list values. These probes do not implement a core archive format or
complete optimized-PC attribution. A full macOS core also replays but grows to
7.115GB; its size and the failed image-control result remain recorded.

## Toolchain 0.57: native indexed pages under development

An isolated build adds lazy native list/byte children beyond the 32-element
text preview. The matching NEX bridge bounds every native variables request to
1000 children, validates signed32 page arguments, preserves source offsets,
handles named-only indexed-root requests and rejects handles after execution.
Page metadata has a separate schema; native previews are not exact wire values.

The initial resource prototype passed five transport cases and a real macOS
ARM64 list32768/bytes4MiB scenario. The unchanged previous adapter failed the
late-index check. A subsequent filter check caught LLDB returning indexed
children to a named-only request; the bridge correction passes that check.
The actual 0.57 compiler is built. Current full68, installed SDK21, Linux and
actual editor page checks remain pending. The preceding root604 full67 and
both root604/root606 SDK20 results retain their separate source/compiler scope.
The current root606 full67 run is still in progress. Source stays language0.16;
historical stopped values require their matching saved SDKs.

## Toolchain0.56.1: scoped distribution checks passed; root validation pending

The [aggregate evidence](docs/evidence/sdk-distribution-0.56.1.json) links exact
source/compiler identities and complete terminal reports. Frozen597 passes all67
Linux ARM64 groups, twelve live debugger suites and source-free SDK20. Its
portable Linux SDK passes twenty phases after relocation and archive recovery
in a separate network-free container without source, LLVM, MLIR or Z3.

macOS base594 passes all67 groups. The subsequent selected-Crypto search-path
repair passes all29 cases in source FFI/SDK groups and an actual @rpath library
regression: the unchanged scenario fails on the preceding compiler, then prints42
in debug/release and after source deletion. Both relocated/restored macOS SDK20
workflows pass310 commands each, live LLDB/DAP and real browser builds with five
negative read controls and a read-only SDK. npm is offline; the kernel profile
does not claim complete network isolation. Root build/full67/SDK20 remain pending.

Retained attempts include a frozen588 task timeout followed by an unchanged
offline-cache rerun, Node/TypeScript path failures, percent-TMPDIR staging,
Darwin LLDB backslash image paths and missing Crypto runtime search paths in
the independent C++ acceptance hosts and source extern executables. Corrections
retain assertions and timeouts. Current native builds select configured library
directories explicitly; language0.16/runtime ABI/canonical forms are unchanged.
The current generated web example separately passes18 production UI tests and3
development renderer rejection tests across Chromium, Firefox and WebKit. The
initial browser harness selected the wrong directory; its logs are retained,
and the corrected invocation uses the exact build.directory response without
changing application code, assertions or timeouts. The full PLAN is still open.

## Isolated0.56 editor installation integration: scoped acceptance passed

Toolchain0.56 keeps source0.16 and its canonical forms unchanged. CMake installs
editor sources and their separate pinned development lock; the descriptor and
language pack expose an editor guide. The compiler regression adds an editor
suite, giving67 groups. The installed SDK workflow adds an editor-tools phase,
giving20. The Node contract cases run from installed SDK resources; live mode
also prepares a native session and checks its original-file mapping. Actual IDE
execution is explicitly a separate check.

The current compiler passes the editor suite (two Python cases and ten Node
contract cases). Its installed SDK VSIX also passes an actual separate-profile
VS Code 1.142.0/macOS ARM64 run: original-file breakpoint, stack/scopes, scalar
and trait watches at the same native stop, exact output42 and exit0. The first
focused run exposed a /var physical-alias mismatch; the corrected implementation
preserves the selected path and rejects a symlink retarget during preparation.
The initial failure is retained in [current evidence](docs/evidence/editor-integration-0.56.0.json).
The frozen576-file editor integration passes all67 macOS/Linux ARM64 groups,
both complete SDK20 workflows/310 commands, twelve Linux live debugger suites
and the separate actual installed IDE check. The Linux SDK runs without source
or network. See the exact [macOS full](docs/evidence/editor-integration-0.56.0-macos-full.json),
[Linux](docs/evidence/editor-integration-0.56.0-linux.json) and
[macOS SDK](docs/evidence/editor-integration-0.56.0-sdk.json) evidence. Subsequent
0.56.1 portable workflow corrections remain separately pending.

The preceding 0.55 trait/library API source separately passes Linux66, twelve
live suites and all19 source-free SDK phases/307 commands. Its host controller
was interrupted; the already running source container completed successfully,
then the unchanged source-free helper completed. The
[Linux evidence](docs/evidence/trait-library-api-0.55.0-linux.json) records compiler
hashes, platform skips and resource equality. macOS full66 also passes (1621.33s).

## Editor extension prototype: actual installed VSIX check passed

The extension registers NEX debugging in VS Code and uses a fresh compiler
descriptor for the matching frozen executable, formatter, source map and stdio
adapter. Original-file mappings require equality with frozen bytes; changed
library files keep their frozen fallback, while a changed entry requires a
fresh launch. Compiler-provided foreign execution arguments remain intact.

All9 focused Node cases pass. The official VSIX packager creates an archive with
the exact five extension sources and no runtime npm dependencies. A separate
VS Code1.142.0/macOS ARM64 profile installs that archive, activates it, stops at
the physical source breakpoint, reads stack/scopes, evaluates scalar and generic
trait NEX watches to42, resumes and observes clean native output/termination.
The initial missing source mapping and its failed real IDE run are retained.

This prototype uses the independently checked0.55/source0.16 compiler. SDK/source
installation integration, current full regression and wider IDE/platform checks
remain pending. No NEX Studio/LSP/Marketplace or stable release is claimed.
See [editor evidence](docs/evidence/editor-extension-prototype.json).

## Isolated trait/library API projection: scoped regression passed

The new source tree retains real client/shared trait contracts, method targets
and private dependencies for application models and captured libraries. Server
members/bindings/functions, tests, endpoints and unused private code are omitted.
The full input is checked; a binding-only source view preserves imports and
witness references erased by concrete normalization. It is never lowered or
executed. The final server/client projects are checked before output creation.

The current compiler passes20 trait cases,14 API cases and21 frontend
diagnostic cases (one macOS filename skip), plus two C++ probes,102.09s.
The independent-bound/same-name generic method case passes without a language
version change. The installed SDK's exact traits/API phase passes24 commands
in22.057s, including a generated client invoking the real method, native and
TypeScript agreement, exclusion of server bodies and a native server build.
Live generic constructor/trait watches retain their stop and handle identities;
the source-deleted replay and genuine0.15 migration also pass.

The initial specialized-method-name failure and the standalone phase adapter's
missing shutil import remain recorded. The installed acceptance script already
imports shutil; the corrected adapter requires no product change. See
[current scoped evidence](docs/evidence/trait-library-api-0.55.0.json).

The preceding553-file source016 baseline separately passes all66 macOS groups
(551 Python cases, two platform skips,13 C++ probes;1333.30s) and the same
baseline compiler's19-phase SDK (302 commands;331.279s). Its final documentation
postdates the frozen validation input. [Baseline evidence](docs/evidence/source-traits-0.55.0-macos-baseline.json)
does not substitute for current-source acceptance. Full current66, SDK19/Linux,
Release/sanitizers and the full language/development-chain PLAN remain open.

## Verified internal 0.55 core: language 0.15

The frozen constructor-kind/application/substitution/coherence core passes all65
macOS ARM64 groups:534 Python cases and13 C++ probes,1347.82s. Twenty native
invariant groups include symmetry and exact reconstruction. A genuine SDK0.54
fixture remains readable without source, with its exact old revision/SQL rows.
This core adds no source trait syntax and proves no language0.16 feature.
Linux/core SDK acceptance is not claimed. See
[the scoped evidence](docs/evidence/constructor-core-0.55.0.json).

## Verified root0.54: full64 and installed SDK18

The exact verified isolated0.54 implementation is now in the root checkout.
The root clean build passes, followed by all64 macOS ARM64 groups (534 Python
cases and12 C++ probes,1318.30s) and its actual installed SDK18 (322.356s).
All127 indexed resources match the root; live debugger/browser and native string
capture/source-deleted replay pass. Exact compiler/source scopes remain in
the string-range evidence. Isolated Linux/macOS results below remain separate.

The preceding root0.53 frontend diagnostic failure was a stale-build error:
copying sources with their older timestamps left a pre052 modules.cpp object.
Its dependency file lacked the new directly included diagnostics header.
A clean rebuild of unchanged source passes the same21 diagnostic cases (4.85s,
one macOS filename skip). The failed full62 and focused correction remain in
the graph-query evidence; no replacement full053 pass is claimed.

## Verified isolated0.54: stopped-string Unicode scalar windows

The frozen534-file source passes all64 groups on macOS ARM64 (1496.29s) and
Linux ARM64 (780.41s), with534 Python cases and12 C++ probes. Installed SDK18
passes on macOS (405.32s) and Linux (248.03s); all127 indexed resources match
frozen source. Twelve Linux live debugger suites pass. Its SDK runs without
source checkout or network. [Evidence](docs/evidence/string-ranges-0.54.0.json)
keeps exact compiler/source hashes and platform skips.

String shapes expose scalar length; bounded text_range captures support
length/index/slice and retained/overlapping replay with alias consistency.
The read-only LLDB provider streams strict UTF-8 under separate physical-read,
output and deadline limits with per-expression/stop checkpoints. Actual LLDB/DAP
and installed SDK checks capture a4MiB string at an unchanged stop and replay
the retained window after source deletion. Complete strings, language0.15,
native ABI, canonical forms and graph format remain unchanged.

The frozen source is backed up separately. The new root has independent gates
as stated above; the prior failed full053 run is retained alongside its
clean-rebuild diagnosis. Direct large-root DAP paging, editor/core/PC
mapping, traits/associated/higher-kinded types/async and the remaining full
platform/release/ABI/LLM plan remain open.

## Isolated 0.53 graph search and dependency-radius queries

The prototype adds literal name/source discovery over module/type/function/
endpoint declarations, bounded declaration previews and minimum-hop dependency/
dependent/bidirectional subgraphs. Nodes/edges page independently with explicit
byte and depth boundaries. Responses preserve revision, exact archived source,
namespace and selection identity. Queries select archived source, preserve HEAD
and its journal, and do not execute program/native-extension code. Existing
identity/edge metadata is checked against source; old stores may lazily backfill
indexes. Language0.15, canonical forms and graph schema 4 remain unchanged.
Current implementation/focused/schema/SDK/platform validation remains pending.
The full0.52 checks below are separate, on a frozen earlier source tree.

## Isolated 0.52 captured-source frontend context

The prototype adds source-buffer hashes, phase/scope, bounded UTF-8 or lossless
base64 previews and content-derived diagnostic identity for parser/binder/checker
errors. Rejected assembled candidates remain distinct from physical source and
committed graph identities. Static watch context is bound to supplied frame/stop
hashes; runtime operation metadata remains separate. Language0.15 and graph
schema 4 are unchanged. The 21 Python diagnostic cases (one macOS filesystem
skip), 15 native API cases and seven related regression groups pass. Offline
validation accepts 23 actual error forms and rejects 13 malformed variants. The
exact installed SDK diagnostic phase passes 12 commands including rejected and
repaired candidates, lossless malformed bytes and supplied-frame watch context.
The actual macOS installed SDK16 passed all phases in434.171s with live
LLDB/DAP/browser builds and all122 indexed resources matching frozen source.
Full current regression/Linux live/source-free SDK workflows remain pending.

## Verified 0.49 / language 0.15: atomic change history and restore

The preceding corrected 0.49 compiler passes all 57 regression groups on macOS ARM64
(447 Python cases + 11 C++ probes, 1375.92 s) and Linux ARM64 (1166.28 s). Both
thirteen-phase installed SDK workflows pass: macOS 412.565 s and Linux 263.748 s
in a network-disabled container without the source checkout. Linux additionally
passes eleven live debugger suites. Exact hashes, source scope, platform skips
and retained failed/cancelled baseline attempts are in
[the evidence](docs/evidence/change-history-0.49.0.json). The optional old 0.43
SDK now proves original schema 3 readability and schema 4 refusal. A legacy
migration fixture no longer fabricates unjournaled HEAD writes; an independent
case verifies tampering is rejected without candidate rows.

The journal records actual atomic HEAD transitions and declared labels, with
bounded page/link checks. Guarded restore retains sources/IDs/history and does
not materialize physical files. Schema 4 starts an explicit old HEAD base rather
than inventing prior transitions. This is scoped development evidence, not
proof of every platform, full-system safety or stable cross-SDK ABI.

The intermediate 0.50 passed its focused checks, macOS SDK14 and Linux58/live11/SDK14
matrix; no full macOS regression was run for that intermediate compiler. The
preceding isolated 0.51 source passes all59 groups on macOS/Linux ARM64, both
SDK15 workflows and eleven Linux live suites. Its exact implementation is now
promoted to the root, where the root build/SDK15 pass and full root regression
remains running. [Evidence](docs/evidence/project-versions-0.51.0.json) preserves
the pre-promotion scope. Current0.52 adds diagnostics above that implementation;
its pending checks are not implied by earlier successful versions.

The full requested objective remains open: build the NEX language and complete development chain, including web applications and model-independent authoring. The working core below is a milestone, not completion of that objective. Application products will be built later in NEX; the current deliverable is the language and complete development toolchain.

## In progress: change provenance and archived restore

Toolchain **0.49.0 / language 0.15** adds an atomic local HEAD-transition
journal, bounded paging and optimistic restoration of retained checked sources.
Graph schema 4 preserves existing revision/source/identity/task rows and begins
an empty journal at the prior HEAD. Notes/actors are bounded declared labels;
record hashes and selected adjacent links are checked without authenticating
identity or fabricating historical events. Restore retains all revisions and
IDs, accepts an expected-HEAD guard and does not materialize or execute source.

The initial thirteen history cases pass with five compatibility groups, totaling
six groups and 90 Python cases in 90.41 s. The initial installed SDK passes all
thirteen phases in 293.641 s, including four source-deleted HEAD transitions and
native/reference/TypeScript restoration. Offline JSON Schema 4.25.1 validation
accepts five actual CLI response forms and rejects ten malformed variants; a
foreign graph's claimed journal is not imported as local history.

A final implementation adjustment avoids decoding/hashing an archived bundle
when HEAD is unchanged. All thirteen targeted history cases pass again in 11.11 s.
Earlier compatibility/SDK evidence retains its pre-adjustment compiler scope.
Full current root/platform/installed-SDK validation and the complete requested
NEX language/development chain remain pending.

## Verified development milestone: exact source-operation replacements

Toolchain **0.48.0 / language 0.15** adds complete nonsemantic syntax ranges,
bounded UTF-8 context previews and revision/source-checked patches by local
operation ID. Single expression/statement/pattern fragments preserve precedence
and line-comment boundaries. Non-overlapping edits can span modules and existing
declarations; the whole candidate is checked before a final expected-HEAD
transaction. Derived owners and synthetic intervals remain explicit noneditable
targets. Canonical definitions, database schema 3, operation identity policy 1 and
the runtime tree are retained.

All **56 regression groups** pass on macOS ARM64 in **1334.39 s** and Linux
ARM64 in **1152.04 s**, including **433 Python cases and eleven C++ probes**;
Linux reports its platform-specific skips separately. Eighteen operation-patch
cases cover exact source guards, precedence/comments, nested and complete enum
patterns, generic/closure restrictions, cross-module type edits, effect/realm
rejections, limits and unchanged rejected-candidate rows. Genuine 0.47 archives
retain original revisions, IDs, sites, hashes and diagnostic locations.

Both installed SDKs pass thirteen phases, including source-deleted operation
edits, stable local IDs with changed sites and native/reference/TypeScript
agreement. macOS takes **314.901 s** and source-free Linux **278.590 s** with
networking disabled and all eleven live debugger suites passing. Resource hashes
match the frozen 498-file source. Offline schema validation accepts four actual
current/historical reports and three patch forms and rejects eleven malformed
variants. The [evidence](docs/evidence/operation-patches-0.48.0.json) records exact
scope and the initial composed-expression crash corrected by a resulting-tree
bound. Broader current Release, sanitizer, x86-64, distribution and remaining
language/development-chain work stay pending; this milestone is not project
completion.

## Verified development milestone: checked native integer fast paths

Toolchain **0.47.0 / language 0.15** keeps signed overflow checks and guarded
division/remainder in SSA, with integer runtime calls on failure branches.
Assertions branch on their evaluated boolean; failure retains checked operation
metadata. `MIN % -1` is defined without LLVM undefined behavior. Arguments still
evaluate once, left to right. Error codes/sites, floating rules, canonical
definitions and C value ABI 1 are retained.

All **55 regression groups** pass on macOS ARM64 in **1303.39 s** and Linux
ARM64 in **1098.76 s**, including **415 Python cases and eleven C++ probes**.
Both installed SDK workflows pass thirteen phases: macOS **320.447 s** and
source-free Linux **226.347 s**, with all eleven Linux live debugger suites.
Integer acceptance checks boundaries and loops across reference/native Debug
and Release/TypeScript, then deletes source and replays archived execution.
Native trap mapping and retained historical fixtures also pass. All SDK resource
hashes match the frozen 491-file source snapshot. The
[evidence](docs/evidence/native-arithmetic-0.47.0.json) records exact compiler,
source and report hashes.

Initial shared-host observations measured 71.9 ms vs 105.9 ms for a 20-million
iteration loop and 259,040 vs 391,168 bytes for a constant-expression workload
against 0.46. That initial compiler preceded final descriptor/assertion changes;
these measurements are limited observations, not a general speed guarantee.
Current full Release, sanitizer, x86-64 and SDK distribution checks remain
pending, as does the rest of the requested language and development chain.

## Verified development milestone: native runtime trap attribution

Toolchain **0.46.0 / language 0.15** adds compact constant operation descriptors,
per-link application identity, bounded `NEX_NATIVE_TRAP` records and checked local
graph resolution. `nex run --json` returns native diagnostics; `nex diagnose`
maps retained standalone/HTTP operator logs against current or archived checked
sources. Error propagation preserves the innermost located trap. Original helper
signatures, `Trap` definition, C value ABI 1 and language semantics remain intact.
The [guide](docs/native-diagnostics.md) defines data trust and attribution limits.

The corrected implementation passes all **54 regression groups** on macOS ARM64
in **1258.90 s** and Linux ARM64 in **1078.17 s**, including **412 Python cases**
and **eleven C++ probes**. Both installed SDKs pass thirteen workflow phases;
macOS takes **310.851 s**, source-free Linux takes **306.114 s** with networking
disabled. Linux also passes eleven live debugger suites. Native diagnostics agree
with interpreter operation IDs in debug/release, remain available after source
deletion, and resolve to distinct local IDs after graph import into a new store.
HTTP operator reports retain request IDs while public responses keep their generic
messages. Offline JSON Schema validation accepts actual mapped/unmapped records
and the sanitized C++ producer; six malformed variants are rejected. All 37
historical fixture hashes, six C/value headers and the original `Trap` definition
match 0.45. The [evidence](docs/evidence/native-diagnostics-0.46.0.json) binds exact
compiler/source/report hashes and preserves the initial Linux build failure.

The Linux build initially selected `std::quoted` through ADL; explicit
`nexrt::quoted` fixes that portability defect. Compact typed descriptors reduce
a synthetic many-site executable from 687,584 to 391,168 bytes compared with the
initial JSON-per-site prototype. Arithmetic-call overhead remains visible in a
limited local experiment; isolated 0.47 moves checked integer success paths into
SSA. These measurements are observations, not general performance guarantees.
Broader current Release, sanitizer, x86-64 and SDK distribution checks remain
pending. Parser/checker identities, signal/core recovery, remaining platform and
language/toolchain features are open. This milestone does not complete NEX.

## Verified development milestone: atomic source-type replacements

Toolchain **0.45.0 / language 0.15** adds replacement of existing source
structs/enums with their constructors, signatures, matches and handlers in one
optimistic patch. Optional replacement `kind` must match its declaration;
unknown fields and malformed expected digests are rejected. Source type nodes
are editable, generic instances remain derived, and retained revisions keep
their original layouts. Module/import/new-top-level-declaration edits still use
export/edit/check. Runtime semantics and graph identity policy remain unchanged.

All **52 regression groups** pass on macOS ARM64 in **1196.45 s** and Linux
ARM64 in **1007.88 s**, including 400 Python cases and ten C++ probes.
Both installed SDKs pass thirteen phases, including a partial-type-edit rejection,
a complete type/factory/caller patch, preserved type IDs and source-deleted
native/reference/TypeScript execution. The macOS workflow takes **301.940 s**;
source-free Linux takes **210.147 s**, with networking disabled and all eleven
live debugger suites passing. The final SDK resource hashes match the frozen
source snapshot. Offline schema validation accepts current and five actual 0.44
artifacts plus a legacy function patch, and rejects six malformed variants.
The [evidence](docs/evidence/type-patches-0.45.0.json) binds exact source, compiler
and report hashes. Broader current Release, sanitizer, x86-64 and SDK distribution
checks remain pending. This milestone does not complete the requested language
and development chain.

## Verified development milestone: declaration graph and cross-store references

Toolchain **0.44.0 / language 0.15** adds persistent module/type nodes,
dependency-context fingerprints, bounded declaration queries and explicit
snapshot-scoped identity reconciliation. Local function/operation IDs, database
schema 3, language hashing and runtime semantics remain unchanged. Reconciliation
checks an expected HEAD and commits a complete page atomically without changing
source or HEAD. A genuine 0.43 database fixture covers additive backfill.
The [graph guide](docs/graph.md) defines limits, provenance and mapping scope.

The initial implementation passes all 51 macOS/Linux ARM64 groups (387 Python
cases and ten C++ probes), both thirteen-phase SDK workflows and Linux live
debugger checks. Additional coverage exposed duplicate visits of nested
statement-match bodies in dependency collection: depth 25 took 0.067 s on 0.43
but exceeded a 3-s timeout in the new implementation. Each arm is now visited
once. The same corrected case passes in 0.0423 s; all 17 focused identity cases,
including depth-30 native/TypeScript execution and arm-local type dependencies,
pass in the isolated corrected build. The corrected root passes all 17 focused
cases in 11.198 s. Its full macOS ARM64 regression passes all 51 groups (389
Python cases and ten C++ probes) in 1165.35 s with two parallel workers. Linux
ARM64 passes the same full 51 groups in 999.31 s, then all eleven live debugger
suites and a source-free installed SDK. Both SDKs pass thirteen workflow phases,
including 166 reconciled graph records with destination IDs preserved; macOS
takes 289.973 s and source-free Linux takes 207.806 s with networking disabled.
The five real current graph response artifacts validate offline against JSON
Schema 4.25.1; seven malformed variants are rejected. A 56-record comparison
confirms that the traversal fix preserves identity output.

The [evidence](docs/evidence/graph-identities-0.44.0.json) separates baseline and
corrected results and preserves exact compiler/source/report hashes. Broader
current Release, sanitizer, x86-64 and SDK distribution checks remain pending.
Source type replacement is added in the current 0.45 development; it was not
advertised by the verified 0.44 compiler. Remaining platform adapters, callbacks, async
and the rest of the language/toolchain plan remain open. This milestone does
not complete NEX.

## Verified development milestone: native foreign application packaging

Toolchain **0.43.0 / language 0.15** connects explicit `nex package --foreign`
to recursive Mach-O/ELF dependency collection and complete notices. Only
reachable logical libraries/exports enter the deployed catalogue. Relocated
module bytes get new manifest hashes; the compiler changes only the exact
reachable source pin tokens, rechecks the derived bundle and retains both graph
revisions without changing HEAD or materialized sources. The binary resolves its
packaged catalogue relative to its actual executable location. Captured bytes
are rehashed before publication. C ABI 1 remains unchanged.

The initial integrated snapshot passes all **50 groups** (368 Python cases and
ten C++ probes) on macOS ARM64 in **1107.74 s** and Linux ARM64 in **940.65 s**.
Both installed SDKs pass all thirteen workflow phases, including a moved,
source-deleted nominal C-module application package. The macOS workflow takes
285.702 s; the Linux workflow takes 201.888 s in a source-free container with
networking disabled. The Linux live debugger matrix also passes. These results
describe the initial snapshot before the corrections below.

Additional checks found three defects. Python initially followed a host symlink
and omitted the native regular-file/1-MiB limit; the two new root checks pass in
0.839 s. Relative schema references were unresolved; canonical URIs now resolve
through an offline registry. JSON Schema 4.25.1 accepts three real SDK metadata
artifacts and rejects five malformed variants. Finally, component notice paths
split one shared native image: an observable counter changed from `1,2` to
`1,1` after packaging. Distribution notices are now captured at catalogue scope,
and an inventoried source-identity member preserves distinct original pins.
Both shared-state and independent-state native/reference/package cases pass in
66.212 s, including deleted original inputs and complete file/notice inventories.

The corrected implementation passes all **50 groups** (372 Python cases and ten
C++ probes) on macOS ARM64 in **1170.30 s** and Linux ARM64 in **993.26 s**.
All twelve packaging cases pass on both hosts. The corrected macOS installed SDK
passes thirteen phases in **286.713 s**; Linux passes the live debugger matrix
and thirteen-phase SDK workflow in **205.069 s**, without a source mount or
external networking. Its moved nominal C-module package runs after input/source
deletion. The current schemas validate all three real SDK metadata artifacts
offline and reject seven malformed variants. All 37 historical fixture/header
hashes remain unchanged.

The [evidence](docs/evidence/foreign-packages-0.43.0.json) keeps baseline and
corrected scope separate. Broader compiler Release, x86-64, sanitizer and SDK
distribution checks remain pending; this is not a stable release or completion
of NEX. Cross-target native modules, arbitrary dynamic native loads,
Windows/mobile installers, callbacks and the remaining language/toolchain work
stay open.

## Earlier milestone: reviewed foreign inputs for tasks

Toolchain **0.42.0 / language 0.15** adds read-only `nex foreign HOST.json`
discovery, location-independent operator fingerprints and per-check
`foreign_hash` in native task tests/runs/profiles. Task execution captures all
inventoried binary/notice/manifest bytes and passes the normalized catalogue
only to selected execution commands. Replay requires current operator trust;
rehashed captured receipts cannot grant authority. Checks validate current grants
and source binding/signature pins before native module initialization. Input
integrity is checked around each command. The exact 8192-input boundary now
counts the integrity index separately, and oversized indexes fail before running.

Before the forced-exit correction, 0.42 passed all 49 groups on macOS ARM64
(358 Python cases and ten C++ probes) in 1019.58 s and all 49 groups on Linux
ARM64 in 845.31 s. Both installed SDK workflows passed all thirteen phases,
including the reviewed nominal C-module task and source-deleted trusted replay.
The macOS SDK workflow took 247.092 s. Those results describe the initial
0.42 snapshot, not the correction below.

A real uncooperative C callback exposed a cleanup defect: the supervisor reaped
the timed-out process, but one private module snapshot remained. The task parent
now owns a fresh mode-0700 system temporary directory for each selected foreign
command, removes it after group reaping, and verifies directory identity before
cleanup. Interrupt state is retained before cleanup so cancellation still skips
remaining checks. The isolated nine-case system-temp run passes in 261.686 s;
the final timeout/interruption pair passes in 4.381 s. Existing grant, integrity,
8192-input-boundary and replay cases are included. The corrected ten-case task-FFI group and fourteen-case source-FFI group pass in
249.03 s and 312.53 s. The corrected macOS ARM64 full regression passes all
49 groups in 1058.18 s; the installed SDK passes all thirteen phases in
260.600 s. The corrected Linux ARM64 full regression passes all 49 groups, its
live debugger matrix passes, and its thirteen-phase SDK workflow passes in a
source-free container in 187.131 s with networking disabled. Broader platform,
sanitizer and distribution validation remains pending.

The [task-FFI evidence](docs/evidence/ffi-tasks-0.42.0.json) records the baseline,
correction and pending checks. This is an experimental integration, not completion
of NEX. Dependency-closure packaging, callbacks into NEX, general resources,
async and remaining platform adapters are still open.

## Verified development milestone: source foreign declarations

Toolchain **0.41.0 / language 0.15** connects experimental server-only `extern`
declarations and `ffi` to the checker, interpreter/native backend, explicit CLI
execution, profiling/debugging and browser exclusion. Source bindings identify
a manifest; a separate operator catalogue grants authority.

The final macOS ARM64 Debug regression passes all **48 groups** (350 Python cases
and ten C++ probes) in **889.25 s**. The corrected installed macOS SDK passes all
thirteen phases in **250.044 s**, including independent C module calls from NEX,
native Debug/Release, source-deleted replay, standalone output, real LLDB/DAP
and browser builds. Linux ARM64 passes all **48 groups**, the live debugger
matrix including an external-wrapper watch, and the thirteen-phase SDK workflow
in a separate source-free container with external networking disabled. That SDK
workflow takes **193.294 s**. Seven Linux cases explicitly skip unavailable
macOS cross-SDK/Mach-O checks. Supplemental current imported-callable and stronger
HTTP/static-root scenarios pass on Linux in **50.728 s**.

All 37 historical fixture/header hashes remain unchanged. Reviewed task/proof
metadata was regenerated under 0.15 without changing requirements, postconditions,
loop invariants or test bodies. The [source integration evidence](docs/evidence/source-ffi-0.41.0.json)
binds inputs, artifacts, initial failures/corrections and the executed scope.
Broader Release/Linux x86-64, sanitizer and distribution checks for 0.41 remain
pending. Its task-catalogue and package closures were explicitly unavailable;
the task integration is added in 0.42 above. The earlier 0.40 evidence below
applies to that preceding snapshot.

## Earlier milestone: scoped foreign invocation adapter

Toolchain **0.40.0 / language 0.14** adds explicit `nex.foreign-host/1` operator
catalogues, `nex.foreign-binding/1` metadata, thread-local lexical contexts and a
common invocation path with a native managed-handle bridge. Metadata caches
rebind every call to current request authority; there is no environment grant.
Native cancellation preserves the original diagnostic code/line and standalone
terminal cleanup revokes module owners. The 24 new C/C++ cases pass on macOS
ARM64, including all value kinds, real requests, callback destruction, shared
images across eight independent thread contexts and actual fatal-exit cleanup.
Full macOS ARM64 Debug regression passes all 47 suites (336 Python cases and ten
C++ probes) in 790.04 s with two parallel groups. The installed macOS SDK passes
all thirteen phases in 215.308 s, including the actual scoped native bridge with
deleted C++ sources, real LLDB/DAP and browser builds. All 125 transport, loader,
resource and context cases pass ASan/UBSan/LSan on macOS ARM64 and Linux
ARM64/emulated x86-64; macOS also passes ThreadSanitizer. Independent source-free
Linux hosts execute the scoped bridge against the same NEX value contract.
Private snapshot cleanup leaves no temporary files. Broader current Release/
Linux compiler, isolated Linux SDK and distribution checks remain pending.
[Evidence](docs/evidence/ffi-contexts-0.40.0.json) binds the checked inputs and
scope. Source
declarations, interpreter/MLIR calls, migration, browser exclusion, general
resources, callbacks and async remain pending. The descriptor keeps
`foreign_boundary.source_support:false`.

## Verified development milestone: authorized native module loading

Toolchain **0.39.0 / language 0.14** adds a separate C module descriptor and a
trusted host loader. Explicit library/export grants, manifest/signature pins,
pre-initialization file hashing, private snapshots, resource-bound authorization,
physical call leases and a weak content-addressed image cache are implemented.
The 22 loader cases, 48 legacy/typed transport cases and 31 resource cases pass
ASan/UBSan/LSan on macOS ARM64 and Linux ARM64/emulated x86-64; macOS also passes
ThreadSanitizer. The installed macOS SDK passes all thirteen phases in 223.865 s,
including a real C shared module with nominal values, deleted C/C++ sources,
real LLDB/DAP and browser builds. Separate source-free Linux ARM64/emulated
x86-64 containers execute the loaded nominal module and match the NEX model.
Private snapshot cleanup leaves no temporary files. The initial Linux run's
Docker `noexec` denial and successful corrected run are retained separately.
Full macOS ARM64 Debug regression passes all 46 suites (336 Python cases and
nine C++ probes) in 1596.33 s. Broader current Release/Linux compiler,
isolated Linux SDK and distribution validation remain pending.
[Evidence](docs/evidence/ffi-modules-0.39.0.json) binds the source, binaries and
executed checks. Source foreign
declarations/invocation, general dependency-closure packaging, callbacks and
async remain pending; `foreign_boundary.source_support` stays false.

## Verified development milestone: checked C value signatures

Toolchain **0.38.0 / language 0.14** adds compiler-derived
`nex.foreign-signature/1` metadata, exported with `nex ffi --symbol NAME`, and a
typed host invocation path. Inputs and results are checked through aggregates,
nominal/phantom identities, enum variants, callable authority and file owners.
Appended ABI-1 table slots construct checked records/enums and expose scoped type
tokens. The original C table prefix is preserved and an unchanged installed-0.37
header compiles the legacy producer. Language syntax/canonical formats remain
unchanged. Source declarations, loading/authorization, source backend invocation,
general resources and async remain pending. The descriptor continues to report
`source_support:false`.

The 25 legacy-prefix and 23 typed C/C++ cases pass ASan/UBSan/LSan on macOS ARM64
and Linux ARM64/emulated x86-64; macOS also passes ThreadSanitizer. Full macOS
Debug regression passes all 45 suites (336 Python cases and eight C++ probes) in
715.24 s. Eight new source/schema/history cases include C/native/reference/
TypeScript agreement on the same nested result, enum, generic record, binary and
NUL-string scenario. The installed macOS SDK passes all thirteen workflow phases
in 177.178 s with real LLDB/DAP and browser builds; its typed C host works after
source deletion, using only the retained contract metadata. Compiler, runtime
inputs and workflow match the checked sources. Broader current compiler and
isolated SDK/distribution validation remain pending.
[Evidence](docs/evidence/ffi-types-0.38.0.json) binds the inputs and scope.

A genuine language-0.14 source/SQL fixture was captured using the accepted
installed SDK 0.37 before future declarations. It keeps ordinary `ffi`, `extern`
and `foreign` names, actual server file signatures, callbacks and original IDs.
Its native Debug/Release, interpreter and TypeScript checks pass without retagging
history. [The C transport guide](docs/ffi-design.md) describes the new host scope.

## Verified development milestone: versioned C value transport

Toolchain **0.37.0 / language 0.14** adds an experimental C11 value table and a
trusted C++ invocation wrapper. Call-local, non-reused tokens retain immutable
values without exposing C++ layouts, pointers into NEX storage or raw file
descriptors. The boundary copies UTF-8/binary payloads, checks thread/reference
ownership and quotas, and preserves sticky host traps across cooperative polls.
The independently compiled C producer and 25 lifecycle/value cases pass on
macOS ARM64 and Linux ARM64/emulated x86-64 with ASan/UBSan/LSan; macOS also passes
ThreadSanitizer. Full macOS Debug regression passes all 43 suites (328 Python
cases and seven C++ probes) in 753.03 s. The installed macOS SDK passes thirteen
phases in 148.878 s, including an independently compiled C11 producer/C++20 host,
deleted-source execution without NEX resources, real LLDB/DAP and three browser
builds. Its compiler, runtime inputs and maintained workflow match these sources.
Current Release/Linux compiler and isolated SDK/distribution checks remain
pending. [Evidence](docs/evidence/ffi-transport-0.37.0.json) binds the checked inputs.
Language/canonical formats are unchanged. Source extern declarations, checked
signatures, library loading/authorization, packaging, general resource kinds,
callbacks into NEX and async remain pending. The descriptor keeps
`foreign_boundary.source_support:false`; [the design](docs/ffi-design.md)
defines the integration gates. This is not a stable published FFI.

## Verified development milestone: source file resources

Toolchain **0.36.0 / language 0.14** adds the `file` source type, ten server/`fs`
operations, immutable aggregate/capture owners and identity equality. The
interpreter and native debug/release paths agree on streaming, alias close,
limits and automatic cleanup. The checker excludes resource-bearing types from
client/shared functions, JSON/API and scalar proof models, including phantom
arguments. TypeScript emits no unreachable server resource code.

Source migration uses new function/11 and program/12 formats. Genuine 0.13
snapshots migrate with preserved history; conflicting old user names require
reviewed source repair and failed migrations leave HEAD unchanged. Pure watches
use opaque IDs with no IO authority. Fourteen source tests, five synthetic watch
tests and eleven live/synthetic macOS LLDB/DAP cases pass. The corrected compiler
passes all 42 suites on macOS ARM64 Debug and Release (328 Python cases and six
C++ probes), and Linux ARM64. Linux also passes ten live-debugger suites and all
twelve installed-SDK workflow phases in a separate container without the source
checkout mounted. The installed macOS SDK passes all twelve phases, including
file programs, source-deleted replay, standalone packaging and three browser
builds. Its compiler and runtime inputs match the verified sources.

All 21 managed-file cases pass ASan/UBSan/LSan on macOS ARM64, Linux ARM64 and
emulated Linux x86-64; macOS also passes ThreadSanitizer. All 33 genuine historical
fixture files and 34 previous source examples remain unchanged. Task/proof
acceptance intent and the new version's revision/content pins are checked.
The initial regression caught an inaccurate generic-add descriptor; the checker
correctly rejected file addition. Corrected macOS/Linux ARM64 and emulated Linux
x86-64 runs pass all 42 suites. Linux x86-64 also passes all twelve installed-SDK
workflow phases without the source checkout mounted; live x86-64 debugging and
physical x86-64 execution remain unverified.
Current moved/restored SDK archives, general FFI, source async and broader
platform validation remain pending. This is a development checkpoint, not an
accepted release. [Evidence](docs/evidence/source-resources-0.36.0.json) binds
the checked inputs, results and remaining scope.

## Verified milestone: managed file resource values

Toolchain **0.35.0 / language 0.13** adds immutable managed file wrappers and an
internal native streaming boundary. Copies in aggregates/results/captures share
resource identity and close state; JSON rejects resource values. Profile hooks
observe complete owned payload sizes. Native request exit, cancellation, budget
and deadline failures revoke resources across all its explicit host grants,
including values retained by trusted C++ code. Poll callbacks retain their state
and may release handles, replace themselves or end their request safely.

The new managed-value probe passes 20 cases on macOS ARM64 and Linux ARM64/
emulated x86-64 with ASan/UBSan/LSan; macOS also passes ThreadSanitizer. The prior
29-case foundation probe passes again on both Linux architectures. The installed
macOS SDK passes all twelve phases, including real LLDB/DAP and three browser
builds; its runtime inputs and compiler match these sources. Full macOS Debug
regression passes all 40 suites in 728.90 s: 309 Python cases and six C++ probes.
Broader current compiler/distribution validation remains pending. Source resource
types/intrinsics, debugger representation, language migration, FFI and async
remain open; the capability descriptor explicitly keeps `source_support:false`.
This extends the verified 0.34 runtime below; it does not publish source syntax.
[Evidence](docs/evidence/resource-values-0.35.0.json) binds the retained runs.
An additional genuine 0.13 SQL fixture captures future streaming names and a
`file` generic parameter using accepted SDK 0.34. All three 0.13 fixtures replay
through the current compiler with identical revisions and logical IDs; the 31
previous fixture files remain unchanged.

## Verified milestone: resource ownership foundation

Toolchain **0.34.0 / language 0.13** adds a typed internal C++ resource runtime
and streaming regular-file adapter. Physical leases retain payloads across
logical close; ancestor/request domains revoke aliases, reserve physical quotas
before factories and check revocation again before publication. File operations
snapshot callbacks/arguments and retain services before polling. Existing
whole-file replacements retain their commit/cancellation semantics.

The [ownership contract](docs/resources-design.md) records scope, IO errors,
partial cancellation and source/FFI integration requirements. New lifecycle,
race and real-file probe passes all 29 cases on macOS ARM64, Linux ARM64 and
emulated Linux x86-64 with ASan/UBSan/LSan. macOS also passes ThreadSanitizer.
The installed macOS SDK passes all twelve workflow phases, including real
LLDB/DAP, file programs and three browser builds. This is an installed SDK check
with source/external tools available, not a moved/restored isolated bundle check.
Full current macOS Debug regression passes all 39 suites in 657.99 s, including
309 Python cases and five C++ probes. The broader current compiler and
distribution matrix remains pending. Source resource types/streaming intrinsics,
stable FFI and async remain unimplemented. [Evidence](docs/evidence/resources-host-0.34.0.json)
binds the probe inputs and retained reports.
The verified 0.33 distribution below remains a separate historical milestone.

## Development milestone: current SDK distribution

Toolchain 0.33 / language 0.13 now has a maintained macOS distribution helper
and a shared inventory-preserving archive boundary for macOS/Linux. Eight owned
archive cases passed on macOS and Linux ARM64. The full current macOS Debug run
passed all 38 suites in 755.68 s: 309 Python cases and four C++ probes.

The macOS SDK passed all twelve workflow phases after moving and after archive
restoration, with actual LLDB/DAP, all three browser builds, kernel read denial
for the source/Homebrew/MacPorts trees, and SDK write denial. Each denial has an
actual negative control. Linux ARM64 passed both twelve-phase workflows in
containers without source or host LLVM/MLIR/Z3, followed by another complete
bundled-SDK live-debugger workflow using its declared external LLDB prerequisite.
The x86-64 compiler passed all 37 suites and its source-free SDK workflow.
Its moved/restored archive workflows also passed all twelve phases under
emulation. All three current development archives are verified.
Actual archives, hashes and scope are recorded in
[SDK evidence](docs/evidence/sdk-0.33.0.json). These are development bundles;
platform C/C++ SDKs, Python/Node and the stated debugger prerequisites remain.

Genuine language-0.13 SQL/source snapshots were captured with the accepted
restored SDK and replayed through another compiler location, preserving graph
revisions and logical IDs. Candidate resource-related names are ordinary user
definitions in these fixtures; source resources/FFI/async are not implemented.

## Development milestone: source binary integration

Development **0.33.0 / language 0.13** connects `bytes` to checked source types,
explicit UTF-8/base64 codecs, immutable operations, generic add/wire, native and
TypeScript emission, typed JSON/API models and bounded debugger demand. Binary
file calls share the server/fs capability policy. The matching specification,
grammar, model-independent prompt and schemas are validated with genuine
0.12 migration fixtures; the full requested objective remains open.

Host-poll ownership review reproduced a 0.32 adapter use-after-free under ASan
when a trusted callback dropped the last input ByteBuffer. The 0.33 writer retains
its owner until all borrowed views finish. The reproduction now exits cleanly
under ASan/UBSan, and the extended 19-case managed-value probe passes. The 0.32
compiler/SDK cohorts below use their preserved sources; they do not validate this
new source-language version. The 10-case source suite passed,
followed by the native/reference/TypeScript binary browser-state case. Seven
offline binary watch cases and the real macOS LLDB/DAP case passed, including
selected reads of a 4 MiB value, retained-slice previews, paged read-only octets
and source-deleted replay. The generic binary API/OpenAPI/SDK/live-HTTP case
passed, including strict malformed-wire rejection and cleanup after traps.
Apple LLDB's target-wide basic type selected a Swift integer; byte children now
use the actual runtime DWARF i64 type. All six production UI checks passed in
Chromium, Firefox and WebKit. The installed macOS ARM64 SDK passed all twelve
workflow phases in 126.717 s, including actual byte DAP watches, independent
binary-file packages, archived replay and all three locked browser builds.
The first SDK attempt revealed missing manifests in two new acceptance projects;
their corrected explicit projects were exercised by the complete second run.
The full 37-suite macOS Debug invocation finished in 673.14 s: 36 suites passed;
the sole failure was its stale exact add-bound inventory. After adding bytes to
that exact list, all eleven constraints cases passed in a 76.27 s CTest rerun.
Compiler/runtime code did not change for that test correction. This covers 301
declared Python cases and four native C++ probes, including the independent
48-update binary oracle and retained aliases. Both initial and corrective
reports are preserved; the initial invocation remains recorded as failed.
macOS Release then passed all 37 suites directly in 563.23 s. Linux ARM64
passed all 37 in 554.30 s; both frozen cohorts contain 300 Python cases and
four C++ probes, with the later independent oracle separately passing through
each matching compiler/SDK. All nine Linux live-debugger suites passed in
60.145 s. The source-free Linux SDK passed all twelve workflow phases, both
without live debugging (113.735 s) and with real LLDB/DAP (120.542 s).
All nineteen managed ownership cases passed under Linux GCC 13.3
ASan/UBSan/LSan; the preserved Clang image lacked sanitizer libraries, and its
initial linker failure is recorded separately. Production compiler tests use
LLVM/MLIR 22.1. The current emulated x86-64 compiler, installed SDK and all
three moved/restored development bundles have also passed.
The [source binary evidence](docs/evidence/bytes-source-0.33.0.json) records exact
source/binary hashes, browser versions, installed SDK phases and remaining scope.
See [bytes.md](docs/bytes.md).

## Historical 0.32: managed binary values

Development toolchain **0.32.0** retains source language **0.12**. Internal C++
and TypeScript value runtimes now represent immutable binary data, typed JSON
base64 and strict UTF-8 conversions. The POSIX host adapter has bounded binary
reads/writes under the same directory capability, atomic publication and HTTP
isolation as text files. Native allocation accounting and handle cleanup include
the binary subtype; ordinary object layouts retain their size and field offsets.
Generated TypeScript/browser resources include the binary module. This does not
expose a source type or binary intrinsic yet. Targeted managed-value/oracle checks
passed. The full macOS Debug run exercised all 35 suites in 1158.95 s: 34
passed, and web failed only its obsolete exact file inventory. The corrected
inventory retains the exact-set check, adds byte-for-byte module comparison,
and passed all seven web cases in a 5.19 s CTest rerun. No compiler/runtime
code changed for that correction. This covers 281 declared Python cases and
four C++ probes; the original failed invocation remains recorded. The macOS
Release invocation likewise passed 34 suites before the corrected web inventory
passed all seven cases. Both Linux compiler runs subsequently passed all 35
suites (ARM64 488.52 s; emulated x86-64 1747.18 s), and their source-free
eleven-phase SDK workflows passed. The installed macOS SDK workflow passed too.
These preserved 0.32 cohorts do not include the 0.33 host-poll ownership fix.

Source binary syntax, API/debugger support and explicit 0.12 migration were
added in 0.33 above. The [buffer design](docs/bytes-design.md) defines implemented host
semantics and the remaining integration. SDK 0.30/0.31 and genuine historical
stores are preserved. [Managed-value evidence](docs/evidence/bytes-values-0.32.0.json)
records each tested source, binary and correction separately. Initial Linux runs
used old toolchain images without `patchelf`; their failed logs are retained.
The tested packager images have the identical base layers plus that dependency.
The corrected compiler hashes match the initial cohorts; packaging and exact
web-inventory checks passed in the completed corrected Linux runs. Source
toolchain 0.32 retained language 0.12 throughout that internal-runtime milestone.

## Historical 0.31: immutable binary primitives

Development toolchain **0.31.0** retains source language **0.12** while building
the internal buffer representation and strict base64 codec. Native buffers own
immutable contiguous octets, copy mutable host imports/exports, retain slice
owners and allocate new values for updates. The TypeScript primitive uses
private storage with checked constructors and copied host boundaries. Eight native ownership/bounds cases and three cross-runtime codec-oracle checks
passed on macOS ARM64, Linux ARM64 and emulated Linux x86-64. Strict ES2020
TypeScript checking passed; macOS ASan/UBSan and native Linux ARM64
ASan/UBSan/LSan passed. The final JS boundary also rejects constructor/prototype
mutation. All 33 current macOS Debug suites passed in 1013.88 s (278 declared
Python cases and three C++ probes, including one Linux-only skip). The emitted
ES2020 primitive passed 68 assertions each in actual Chromium 156.0.8078.4,
Firefox 157.0 and WebKit 27.2, with no page errors. These are primitive checks;
full source-language binary integration remains pending. [Durable prototype
evidence](docs/evidence/bytes-runtime-0.31.0.json) binds the tested source/binaries.

This is not yet a source `bytes` type. Frontend/interpreter/MLIR/TypeScript,
JSON/API, debugger, file-operation and explicit 0.12 migration integration remain
required before exposing the next language version. [The buffer design](docs/bytes-design.md)
records scope; the verified 0.30 SDKs and genuine 0.12 fixtures remain preserved.

## Development milestone: scoped text files

Development toolchain **0.30.0 / language 0.12** exposes server-only
`file_read_text` / `file_write_text` through the distinct `fs` effect. The
interpreter and native runtime share a POSIX directory-capability adapter with
strict UTF-8, immutable results, bounded paths/text and atomic file replacement.
Standalone access requires an explicit absolute root; writes additionally require
exactly `NEX_FILES_WRITE=1`. Native HTTP scopes deny inherited environment grants;
a trusted C++ host can explicitly grant `FileScope`. File writes are not part of
SQLite rollback. Source-level resources, binary buffers, streaming and general
FFI/async remain open.

The rebuilt compiler passed all 13 source integration cases in 59.358 s:
native Debug/Release/reference agreement, Unicode/NUL/BOM, limits and denial,
evaluation order, snapshot closures, TypeScript exclusion, genuine 0.11 migration,
reserved-name repair, HTTP denial, trusted-host cancellation cleanup, reviewed
task effects and pure-watch rejection. The installed SDK adds a dedicated file
phase covering capability denial and independent packaging. All 31 suites passed
on macOS Debug/Release (1231.14/1073.95 s) and Linux ARM64 (496.79 s), with
275 declared Python cases plus the two C++ probes. macOS records one Linux-only
skip; Linux records seven macOS-only skips. Linux ARM64 also passed eight live
suites and its source-free 11-phase SDK in 83.069 s. Emulated Linux x86-64 also passed all 31 suites in 1812.18 s and its
source-free 11-phase SDK in 271.612 s, without claiming live debugger
coverage. This completes the stated 0.30 compiler/installed-SDK matrix.

The moved macOS Release SDK passed all 11 phases with actual LLDB/DAP and both
locked browser builds in 106.313 s. Its restored archive verified 2411 files and
compiled/ran new projects and file applications with kernel-denied access to the
checkout, Homebrew and MacPorts. A forbidden-read control failed as required.
The Linux ARM64 bundle passed all 11 phases in a source-free image without host
LLVM/MLIR/Z3/Clang, then repeated all 11 after extraction (105.935/108.354 s),
checking all 743 files. The first clean-image attempt exposed a missing packaging
prerequisite, patchelf; the maintained image/guide now declare it. Compiler,
runtime and language-test inputs remain the frozen `c93c4786` set; Linux SDK
resources carry the two documented recipe/guide corrections.

File packages separately passed native Unicode/NUL output, denied writes and
unchanged content in runtime-only Linux ARM64/emulated x86-64 images without SDK
or development tools. Direct runs hid `/usr/bin` and used an unavailable PATH;
the Python negative controls failed and native file execution succeeded.
[Durable 0.30 evidence](docs/evidence/sdk-0.30.0.json) records hashes, exact scopes
and explicit platform limits. The x86-64 bundle verified all 743 files and
passed 11 clean phases in 292.810 s, then repeated 11 after extraction in
271.620 s. This does not complete the broader requested project.

The earlier internal adapter passed 13 direct C++ cases on macOS ARM64, Linux
ARM64 and emulated Linux x86-64; its source-0.11 prototype passed all 30 macOS
suites in 921.16 s. Genuine SDK 0.29 / language 0.11 store/export fixtures retain
old sources/history before migration. These historical results do not substitute
for the new language-version matrix. See [the file guide](docs/files.md) and
[the design](docs/files-design.md).

Genuine SDK 0.30 / language 0.12 SQL fixtures also preserve current generic wire,
server `fs` and callable-reference code before the next language change. The
conflict fixture retains currently valid user names proposed for binary buffers.
[The next buffer design](docs/bytes-design.md) is a plan; buffers are not yet
advertised or accepted by the compiler.

## Development milestone: native application packages

Development toolchain **0.29.0** retains source language **0.11**. `nex package`
builds an application/server (release by default) and assembles its required
non-platform library closure, full notices and hash inventory into a new directory.
It reuses bundled-SDK provenance with byte-integrity checks, supports explicit
notices and Debian package metadata, rewrites copies and never executes the app.
The SDK collector shares its relocation/notice/inventory code with this path.

The compiler built successfully. Five macOS tests passed in 24.762 s: archived
source deletion, output preservation/rejected modes, actual selected SQLite after
deleting its original library/source/build, SDK-inventory reuse plus changed-library
rejection, and a moved HTTPS server with authentication, per-user storage,
persistence across restart and clean exit. An initial `/var` versus `/private/var`
prefix mismatch was fixed by canonicalizing the staging directory; the server
test requires permission to open loopback sockets. Full 0.29 validation passed
on the stated macOS/Linux development matrix. These tests do not establish broader deployment
compatibility, Windows/mobile packaging or completion of the requested toolchain.
See [application packaging](docs/packaging.md) for prerequisites and limits.

Actual numeric, SQLite and HTTPS fixture packages from a moved SDK passed on
macOS ARM64 with kernel-denied access to the checkout/SDK, Homebrew and MacPorts;
the forbidden-read negative control also failed as required. Both Linux ARM64
and emulated x86-64 passed the same native probes in network-disabled runtime
images with no NEX/Clang/GCC/CMake/Node/npm. Every packaged file and actual ELF
library resolution was checked, including authentication, principal isolation,
restart persistence and clean exits. Python is the probe driver rather than an
application dependency. Additional direct container runs hid `/usr/bin` and used
an unavailable PATH: the Python negative control failed, both architectures ran
numeric/SQLite applications, and their HTTPS servers started and exited cleanly.
The corrected installed macOS SDK separately passed all ten phases with actual
LLDB/DAP and both browser builds in 108.719 s.

The new deployment fixture initially used reserved `server` as its module name;
its one-line correction is independently exercised by those native probes.
The verified 0.29 compiler/runtime/tests are the frozen `8cf7621c` inputs.
All 29 suites passed in macOS Debug/Release (1190.77/1007.13 s), Linux ARM64
(490.65 s) and emulated Linux x86-64 (1795.98 s). Linux ARM64 passed all eight
live suites and its ten-phase source-free SDK in 68.174 s; x86-64 passed its
source-free SDK without claiming live debugger coverage. Corrected installed
Linux application drivers directly produced packages that passed the minimal
runtime probe. Both Linux SDK archives repeated all ten phases after extraction.
The macOS Release SDK passed ten phases in 83.333 s, then archive extraction,
all 2402 inventoried file checks and fresh project/build/run/test/package under
kernel-denied source/Homebrew/MacPorts access. Each Linux archive verified 734
files. [Durable SDK evidence](docs/evidence/sdk-0.29.0.json) records hashes,
tested prerequisites and exact validation scope.
[Durable package evidence](docs/evidence/application-packages-0.29.0.json)
records tested images, application manifest hashes and the fixture correction.

The most recent fully verified development checkpoint is toolchain
**0.30 / language 0.12** (function/9, program/10), using compiler/runtime/test tree
`c93c4786` with the recorded Linux recipe/guide resource corrections. Current
0.31 binary-primitive work is separate and retains source language 0.12. Windows/mobile/UI/GPU/Wasm, broader filesystem/resources/FFI/async and the other open plan items remain required work.

The historical accepted checkpoint is toolchain **0.23 / language 0.10**, commit
`e55ee8233b005671f50e193b55256417f1a3d5d1`, with typed
function values, immutable snapshot closures, the generic wire bound and
validated lazy callable watches. Canonical formats are function/8 and program/9.
It passed the macOS ARM64 and Linux ARM64/x86-64 matrix recorded below. Linux
x86-64 execution is emulated; its live debugging remains unverified. Keep SDK
0.22 for its original receipts and frames. This checkpoint does not complete
the broader requested language/development-chain/platform objective.

The checker, interpreter, typed native indirect calls, TypeScript closures,
owned cleanup, graph/cache metadata, strict debug values and callback-safe API
projection are implemented. The model-independent function guide, grammar and
prompt describe the same source semantics. `docs/function-values-design.md`
retains design and prototype evidence. Unsupported platforms and remaining
full-toolchain work stay in scope as listed later in this file.

## In progress: Linux development bundles

Development toolchain **0.28.0** retains source language **0.11**. Linux native
storage/server builds now select configured library directories at execution time,
with an observable SQLite/loader regression for comma/Unicode/percent paths and
explicit rejection of ELF search-list colons. The three macOS native-target,
host-SDK and task-toolchain suites passed in 115.07 s; their Linux/complete 0.28
validation is pending.

ELF assembly copies Clang/llvm-ar/LLD, Clang resources, SQLite/OpenSSL headers
(including multiarch configuration) and non-platform libraries. Copied images get
origin-relative RUNPATH and matching SONAME aliases. GNU loader/glibc/libstdc++/
libgcc and C/C++ development headers/CRT remain external platform prerequisites.
Debian/Ubuntu ownership metadata supplies exact package/source versions and full
copyright/common-license texts; unmanaged files need explicit component notices.
An assembly-only prototype on the preserved 0.27 SDK inventoried 723 files and
23 components. It is not accepted application evidence: ELF application paths
require the current 0.28 compiler.

`tools/linux/bundle.py` freezes an installed SDK/assembler, uses a separate
patchelf image, moves the assembled SDK, runs all ten maintained phases in a
source-free/network-disabled image with no LLVM/MLIR/Z3/Clang, creates an archive
and repeats validation after extracting it elsewhere. The first ARM64 bundle passed all ten phases in 103.287 s in the minimal
runtime and repeated them after archive extraction in 110.364 s. All 726
inventoried files and 23 components were checked; actual compiler/server library
resolutions stayed inside the relocated SDK except the declared GNU platform
runtime. Its 140,555,121-byte archive SHA256 is
`41f3f838ec2438c35ba674b17963ced8a70373e23e9198a17e5a4aa3edf01d8b`
(`build/linux-arm64-028-bundle/verification.json`). It used glibc 2.39/GCC SDK;
observed symbol requirements include GLIBC_2.38 and GLIBCXX_3.4.32, without
claiming untested host compatibility. Linux ARM64 also passed the full 28-suite
regression in 496.89 s, including the selected-SQLite test; live suites continue.

A later metadata review found unchecked SONAME/component path components.
The packager now rejects absolute/escaping SONAME aliases and `.`/`..` component
names. A real ELF fixture with an outside-output SONAME was rejected without
writing that link (`build/boundary-test/report.json`). That check is now a
maintained packaging phase in `tools/linux/bundle_boundaries.py`. A fresh bundle
with the corrected helper resources is being verified. The compiler/runtime/
existing language-test inputs remain the frozen `a979829a` set; these later
changes affect packaging resources/documentation only. The original compiler
images are unchanged.
The final guarded ARM64 and emulated x86-64 bundles each passed ten source-free
phases and repeated ten after archive extraction. ARM64 observed 95.469/88.360 s;
x86-64 observed 263.207/253.742 s. Both verified 727 files and 23 components.
The shared macOS assembler also passed ten phases with actual LLDB/DAP, native
kernel-exclusion checks, and archive extraction with all 2395 file hashes plus
new-project native execution/tests. macOS Debug/Release passed all 28 suites
(257 declared Python cases, including one Linux-only skip) in 1190.63/1003.25 s.
The full emulated x86-64 compiler regression subsequently passed all 28 suites in
1700.52 s, followed by all ten source-free SDK phases in 201.515 s. Live x86-64
debugging remains unverified. [Durable SDK evidence](docs/evidence/sdk-0.28.0.json)
records immutable archive/compiler hashes, tested prerequisites and scope.

All broader language, resource/async/FFI, compiler-cache/LTO and platform work
remains in scope; this step does not complete the requested toolchain.

## In progress: relocatable development SDK

Development toolchain **0.27.0** retains language **0.11**. Relative installed-SDK
tool/dependency selection and explicit archive/debug-tool overrides are implemented.
The compiler reports effective paths, fingerprints selected archive/debug tools,
and rejects invalid/escaping SDK descriptors. Native storage/server executables
record configured macOS library directories as runtime search paths. The dedicated
SQLite regression passed in 3.984 s with a comma/Unicode/percent dependency path;
all three moved-SDK/tool-selection cases passed with real native subprocesses.

The macOS assembler copies Clang/llvm-ar/dsymutil, builtin/runtime/libc++ resources,
available libLTO, SQLite/OpenSSL headers/libraries and the transitive non-system
Mach-O closure. It requires declared component roots and full local license texts,
records original/packaged hashes, rewrites copies and refreshes ad hoc signatures.
Original source installations remain unchanged. Select the external Apple SDK
with `SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"` or an explicit `sysroot`.

The relocated Release bundle passed **all ten maintained phases in 72.493 s**,
including real archived LLDB/DAP, source-deleted replay, both locked Vite builds,
native HTTP/HTTPS authentication, per-principal Unicode storage and persistence
after restart (`build/sdk-027-release-bundle-v3-acceptance/report.json`). The
server probe uses the host's documented `/api/` dispatch prefix. A separate
kernel-sandbox test denied Homebrew, MacPorts, original dependency/SDK and source
resource paths: native numeric tests, an archive, SQLite execution and a newly
compiled HTTPS server passed. A negative control confirmed forbidden reads fail.
It explicitly selected Apple SDK 27.0; Python/Apple tools remain available.
`build/sdk-027-native-isolation-v4/report.json` records that scope. The protected
sandbox launcher strips DYLD tracing, so its empty loader log is not runtime
image evidence. The first bundle's compiler image audit separately loaded all
seven non-system images from its own prefix.

A development archive was created, extracted into another directory and checked
against every one of its **2391 inventoried files**; the restored compiler built,
ran and tested a new native project. Artifact:
`build/releases/nex-sdk-0.27.0-macos-arm64-development.tar.gz` (116,131,561 bytes),
SHA256 `779c2edd2ea1b26b2c100e6c749404d038fec6a6f336999f80cb3ed6af9d16df`.
The companion manifest records compiler tree
`333666ed7c1ad70f9e44f6e6685ea5f292379c46` and the three tested SDK-resource overlays.
Archive verification is `build/sdk-027-archive-verification.json`.

The 0.27 macOS Debug and Release compilers passed all 28 suites in 986.25 s
and 847.04 s respectively (256 declared Python cases plus the C++ probe). The
installed verified Debug SDK passed ten phases in 87.948 s. Linux ARM64 passed
all 28 suites in 429.66 s, all eight live suites and ten source-free SDK phases
in 66.587 s. Its compiler/runtime/test inputs match `333666ed`, with five recorded
SDK validation/document overlays from `7b0f8ca4`; all 64 indexed resources match.
The emulated Linux x86-64 0.27 run passed all 28 suites in 1774.58 s and its
ten-phase source-free SDK in 246.708 s, completing that compiler/SDK matrix
(`build/sdk-host-milestone-027.json`). It does not claim live x86-64 debugging. A first mixed
source-test/old-binary run was explicitly invalidated; it is not accepted evidence.
Current compiler/runtime/test inputs match the frozen `333666ed` source snapshot;
SDK validation later corrected only its `/api/` fixture and packaging resources.
Linux's installed SDK validation must receive that recorded resource correction.
This is a macOS ARM64 development bundle, requiring macOS **27.0**, Apple SDK/tools,
Python, Node/npm for web builds and host LLDB for debugging. Broader machine/OS
coverage, Linux/Windows packaging, mobile SDKs and notarization remain pending.
The complete language/development-chain objective remains open.

## Development milestone: native build overhead

Toolchain **0.26.0** retains language **0.11**. A stack sample
of a warm 0.25 build found complete MLIR generation used only to validate its
entry, plus repeated operation-tree construction. Entry checks are now shared
between the builder/emitter and run before code selection without emitting IR.
One checked operation tree per reachable function provides both debug-site
metadata and the immutable AST-site index used by the native emitters.

The first three cases passed, including already-cached libraries/tests rejected
as invalid application entries, same-file body edits and generic/closure reuse.
Full checking, source/ABI keys, artifact integrity and MLIR/LLVM verification
remain required. Actual reused-function LLDB/DAP passed in 7.872 s. The installed
macOS SDK passed all nine phases in 66.831 s, including archived watches,
source-deleted replay and both locked Vite builds. Reports:
`build/native-build-026-{targeted,live}.log` and
`build/sdk-026-native-build/report.json`. All 27 macOS Debug-compiler suites passed
in 1028.66 s. Linux ARM64 passed 252 declared Python cases (six macOS SDK skips),
all eight live suites and source-free SDK acceptance. The frozen 0.26 Release compiler passed all 27 suites in 910.45 s; its installed
SDK passed nine phases in 58.588 s. Linux emulated x86-64 passed all 27 suites
in 1792.24 s and its source-free nine-phase SDK in 201.835 s. This completes the
0.26 matrix (252 declared Python cases plus the C++ probe per platform; Linux
records six macOS-SDK skips). `build/native-build-milestone-026.json` and
`build/preserved-sdk-026.json` retain reports and four untouched SDK prefixes.

In five interleaved paired observations of the same 13-function workload on a
loaded development host, median warm builds improved from 1.4051 s (0.25) to
1.1736 s (0.26), and single-function edit builds from 2.2056 s to 1.6424 s.
Both versions compiled one/reused twelve functions after each edit and produced
the same checked outputs. The single cold observations were 5.6991 s and
3.7203 s. This is evidence for that workload/configuration, not a general speed
guarantee. All observations and compiler hashes are retained in
`build/native-build-026-comparison/report.json`; before/after stack samples are
`build/function-cache-025-sample` and `build/native-build-026-sample`.

## Development milestone: function object reuse

Toolchain **0.25.0** retains source language **0.11** and its
canonical formats. Native planning gives each concrete function, lifted closure
and generic specialization its own verified object. Call interfaces and
transitive type layouts invalidate consumers, including within one source file.
Owned source text, emitted line/column positions and captured-binding coordinates
participate in keys; unrelated absolute byte-offset changes do not.

Stable virtual DWARF paths map to each build's complete immutable sources.
LLDB uses the direct setting API, DAP receives matching sourceMap pairs, and
profile reports resolve virtual paths back to selected source projections.
Build responses add compiled/reused function counts while preserving module
counts as grouped source units. The complete frontend is still checked.

Initial same-file native/compiler-spy cases and actual LLDB/DAP reuse across
two source-deleted revisions passed. The archived library check also passed
after basing anchors on logical unit/module identity rather than a live physical
library path. The installed macOS SDK passed all nine maintained phases in
61.625 s, including one-function invalidation, both archived outputs, actual
archived DAP, numeric semantics and both locked Vite builds
(`build/sdk-025-function-cache/report.json`). LLDB's value report was checked to
resolve a real frozen file through its source map. The complete regression/platform matrix below passed. Preserve the
verified 0.24 SDKs recorded in `build/preserved-sdk-024.json`; this development
work does not replace that checkpoint or complete the broader objective.

The complete macOS regression passed all 27 suites and 251 Python cases plus
the C++ probe in 1035.82 s (`build/ctest-025-function-cache-full.log`). Linux
ARM64 passed all 27 suites in 422.57 s, with 251 declared Python cases including
six explicit macOS-SDK skips. All eight live suites passed, including actual
reused-function LLDB/DAP after source deletion. Its source-free, network-disabled
SDK passed all nine phases in 53.389 s and required one compiled/two reused
functions after a same-file edit (`build/linux-arm64-025`). The emulated x86-64 run passed all 27 suites in 1587.36 s and its source-free
nine-phase SDK acceptance in 205.889 s; that host does not claim live debugging.
`build/function-cache-milestone-025.json` records the completed matrix.

The new SDK preserves the earlier semantic revision and reviewed task hash.
SDK 0.24 still inspects/replays its own original frame/receipt; 0.25 rejects
them with E_DEBUG_BUILD/E_TASK_COMPILER. The 0.25 numeric browser assets are
byte-identical to those already exercised in Chromium, Firefox and WebKit;
all 62 indexed installed resources match. Evidence:
`build/version-025-old-sdk-compatibility.json` and
`build/sdk-resource-browser-verification-025.json`.

Local single-observation build comparisons do not yet show an end-to-end
latency win. A 13-function workload with 150 checked additions per helper
reemitted 13 functions in 0.24 and one in 0.25, but edit builds took 1.6311 s
and 1.6668 s respectively; cold builds took 2.8119 s and 4.646 s. The small
workload also showed slightly higher latency. These used development compilers
on a host running concurrent validation. Complete source checks took about
0.15 s versus about 1.06 s for warm builds in the larger case; build-pipeline
overhead needs further investigation. Frontend reuse, LTO and portable release
SDKs remain open. Reports: `build/function-cache-025-benchmark{,-large}/report.json`.

## Development milestone: finite binary64

Toolchain **0.24.0 / language 0.11** introduced finite `f64`,
decimal/exponent literals and `number` bounds. Native debug/release, interpreter
and TypeScript examples agree, including generic functions, results, aggregates,
snapshot closures and explicit conversions. Genuine SDK-0.23 SQL migrations
preserve source/history/IDs; an intrinsic-name conflict leaves HEAD unchanged
until an explicit archived-source repair. Task/proof pins were refreshed with
unchanged source hashes and acceptance intent.

Actual macOS LLDB/DAP checks read f64 roots, subnormals, closure captures and
pages and replay after source deletion; offline full/partial watches agree.
Generated API client models preserve f64 with numeric JSON schemas. A native
C++ host exercises real double parameters/results, invalid input rejection,
request trap cleanup and preservation of caller floating flags. The development
matrix below has passed. Broader platform coverage and redistributable SDK
delivery remain pending; the descriptor conservatively retains
`numeric_integration_pending` for full platform/SDK validation. Design and
acceptance scope: `docs/floats-design.md`.

The current source integration has passed all 27 Linux ARM64 CTest suites
(247 declared Python cases, including six explicit macOS-SDK skips, plus the
C++ runtime probe; 389.40 s). All seven opt-in live debugger suites passed,
including the new floating roots, negative aggregate values, subnormals,
captures and DAP pages. Its source-free SDK passed all nine phases with
external networking disabled (`build/linux-arm64-024`). The final macOS ARM64
run passed all 27 suites and 248 Python cases plus the C++ runtime probe in
959.92 s. Emulated Linux x86-64 passed the same 27-suite frozen-input regression
in 1428.14 s, with 247 declared Python cases including six macOS-SDK skips.
The later numeric-browser case passed separately on both Linux SDKs in native
debug/release and TypeScript; all 177 compiler/runtime/adapter/library inputs
remain identical to the frozen tree. Reports:
`build/ctest-024-browser-final.log`, `build/linux-{arm64,amd64}-024` and
`build/linux-numeric-web-supplement-{arm64,amd64}/report.json`.

The production `examples/numbers-web.nex` application passed six Playwright
cases across Chromium, Firefox and WebKit in 3.204 s. It exercises immutable
f64 state/history, generic arithmetic, a captured callback, JSON rounding,
subnormal/maximum values, positive-zero normalization and recoverable rejected
edits. The maintained SDK workflow now requires this example as well as the
earlier callable browser app. The updated macOS SDK passed all nine phases in
64.914 s, including both locked Vite builds and actual archived DAP watches;
all 62 indexed resources are installed. Its numeric browser assets are
byte-identical to the assets used for the browser interactions. Evidence:
`build/numeric-web-024`, `build/sdk-024-browser-final/report.json` and
`build/sdk-024-numeric-browser-artifact-agreement.json`.

The updated source-free Linux SDK workflows, including both browser examples,
passed all nine phases in 49.104 s on ARM64 and 169.091 s on emulated x86-64
(`build/linux-sdk-024-browser-{arm64,amd64}/workflow/report.json`). ARM64
includes actual archived DAP; x86-64 records live debugging false. Their earlier
complete frozen-source workflows are retained separately. These SDKs still
require the documented host development dependencies; they are not portable
redistributable toolchain bundles.

Independent jsonschema 4.23 checks passed current task/proof documents,
operation output, actual archived partial frames and callable wire descriptors,
including f64 captures and full frames with subnormal values. The preserved
0.23 SDK still inspects its old frame and replays its old receipt; 0.24 rejects
them with `E_DEBUG_BUILD` and `E_TASK_COMPILER`, retaining the original bytes.
See `build/version-011-schema-evidence.json` and
`build/version-011-old-sdk-compatibility.json`. These results do not complete
the full language/development-chain/platform objective.

The following foundation evidence predates enabling the 0.11 source type.

The runtime foundation now has finite checked arithmetic, rounding/environment
isolation, normalized zero, explicit integer conversions, distinct aggregate
scalar storage and strict numeric JSON. C++ and JavaScript agree on **4,546
deterministic vectors**, including Python bit-result oracles, gradual underflow,
rounding ties, integer bounds and rejected non-finite inputs. Native checks also
exercise caller rounding/status flags, flush-to-zero modes, threads, trap source
lines and owned cleanup. Optimized checks passed on macOS ARM64 with UBSan
(`build/float-runtime-O3-ubsan.json`), Linux ARM64 and emulated Linux x86-64
(`build/float-runtime-linux-{arm64,amd64}/report.json`). The pinned Linux images
lack compiler-rt sanitizer archives; those two runs used ordinary O3 builds.

The full macOS regression exercised 26 CTest suites: 25 passed, and profiling
passed on rerun after its old empty-notice expectation was updated to preserve
Tracy exclusion while accepting Dragonbox's license. Runtime/compiler bytes did
not change between those runs. Logs: `build/float-runtime-full-ctest.log` and
`build/float-runtime-profiling-rerun.log`. A separate installed SDK passed all nine
acceptance phases, including actual LLDB/DAP, source-deleted archive replay,
scalar proof and a locked TypeScript/Vite build in 76.573 s
(`build/sdk-float-runtime-acceptance/report.json`). These are foundation checks,
not evidence that the new source type or its whole platform matrix is complete.

Dragonbox 1.1.3 is pinned unmodified, with license/hash inventory and native
distribution notices, so formatting preserves the macOS 13.0 build target.
The accepted 0.23 SDKs are preserved and a genuine language 0.10 SQL/source/graph
fixture was captured using that SDK for the upcoming migration. No old source,
task/proof acceptance intent or archived fixture was rewritten.

## Implemented and exercised

- Toolchain 0.23 / language 0.10 adds exact typed function signatures, named/generic references, higher-order calls, immutable transitive snapshot captures, identity equality, owned cleanup, real native indirect calls and TypeScript snapshot closures. Generic wire constraints exclude actual function payloads from JSON/API while allowing serializable phantom contracts. Native/TypeScript/reference agreement, graph/cache invalidation, callable LLDB/DAP, portable SQL migration and source-free SDK checks passed as recorded below. Custom traits, effect/realm subtyping, mutable captured cells, general async and resource FFI remain pending.

- Toolchain 0.22 / language 0.9 adds typed recursive patterns, result/record/exact-list/literal matching, immutable arm bindings, ordered guards, value matches and bounded matrix coverage/usefulness analysis. Native, interpreter and TypeScript preserve selection/order/cleanup; pure watches demand selected paths. The checkpoint matrix and installed SDK workflow passed as recorded below; OR/rest/range patterns and custom extractors remain pending.

- Toolchain 0.21 / language 0.8 adds builtin generic constraints (`add`, `ordered`, `integer`), parametric capability checking and implication-aware abstract forwarding. Bounds are preserved in graph/context/API projections; unsupported custom traits/associated types/function values remain pending. The current evidence is listed below.

- Toolchain 0.20 adds the Linux container build/verification workflow, LLVM LLD selection for ELF DWARF, selected-linker fingerprints (policy 2) and filesystem-independent artifact streaming. Current Linux evidence is recorded below; other OS/mobile targets and full SDK distribution remain pending.
- Toolchain 0.19 adds read-only native toolchain fingerprint discovery, pinned native task selections, foreign artifact acceptance and trusted-catalog replay. Captured configurations, compiler/dependency fingerprints and explicit SDK settings are checked around child execution. Full external SDK/support-tool/environment capture and foreign execution remain pending.
- C++20 compiler with LLVM/MLIR 22.1.8 and SQLite on macOS ARM64 and Linux ARM64/x86-64.
- Toolchain 0.18 adds explicit native target/SDK/dependency configurations, target ABI probes and architecture-isolated module/runtime caches. macOS arm64/x86_64 cross-compilation is configured; foreign runtime/debugger verification remains pending.
- NEX 0.12 lexer/parser, explicit i64/f64/bool/unit types, functions/recursion, let/var, assignments, branches, loops and returns.
- Multi-file modules, logical qualified identities, import aliases, private/public functions and structures, public API visibility checks and cross-module type/effect/realm checks.
- Local library roots, ordinary NEX `std/math` and `std/text` libraries, dependency source-content locks and explicit lock updates. Cyclic imports and remote retrieval are not supported.
- Validated UTF-8 strings with strict escapes, Unicode scalar indexing/slicing, immutable nested lists and nominal structures with typed fields/constructors.
- Automatic managed-value ownership in native code: borrowed parameters, owned returns, temporary cleanup, assignment/scope/early-return cleanup and normal-exit live-value checks.
- Type, mutability, effect, execution-realm and test-definition checks.
- Left-to-right evaluation, logical short-circuiting and checked integer arithmetic in both interpreter and native output.
- Reference interpreter with resource limits and observable output preservation on failure.
- Checked AST/function graph, BLAKE3 identities, SQLite revision history, call edges, import/export and stable logical module/local-name function IDs across entry modules.
- Optimistic function-replacement transactions across multiple files that reject stale HEAD and invalid candidate bundles without committing.
- Complete archived source bundles for each revision, independent of changed/deleted live files or libraries, and relocatable directory export with vendored dependency sources and a generated manifest/lock.
- Structure layouts in semantic revision identity and referenced type definitions in bounded LLM context. Graph database schema migration and explicit language migration preserve old sources/history.
- MLIR verification/conversion, LLVM IR translation, object generation and native linking with preserved intermediate artifacts.
- Whole-program cache with compiler/runtime/profile/source identity and executable integrity check.
- CLI commands for init, discovery, language guides, checking, evaluation, tests, build/run, IR, graph/context/history/patches/import/export and LLDB launch.
- Default NEX tests compare interpreter and native execution. Generated native binaries run independently of the development compiler.
- Immutable entry/imported build source projections and packaged macOS debug symbols. LLDB resolves NEX function symbols and source lines, including library files; the 0.8 checkpoint adds typed parameters/locals, lexical scopes and runtime previews.
- Model-independent language specification, EBNF, system prompt, patch schema, pack manifest and JSON CLI protocol.
- SDK installation with compiler, runtime and language pack; installed tools retrieve their matching guides outside the source checkout.
- Toolchain 0.4.0 adds a TypeScript backend without changing source-language 0.3: checked BigInt arithmetic, Unicode scalar operations, nominal equality, immutable frozen values and scope/evaluation semantics are preserved.
- Browser application contract using ordinary pure initial/update/view/title functions and `std/web.nex` view/event structures, React rendering, controlled form inputs, explicit actions and history/route events.
- `nex web` project generation and real `nex build --target web` package installation/typechecking/Vite asset builds, exact npm lock, bundled runtime notices and complete asset-tree cache integrity checks.
- Client reachability excludes server/unused function bodies and literals from generated source and Vite source maps. Browser and native semantic tests are separate from Playwright interaction checks.
- Toolchain 0.5.0/source language 0.4 add immutable `result<T>`, recoverable error codes/messages and strict typed JSON across interpreter/native/TypeScript. Wire i64 values are canonical decimal strings; duplicate/unknown/missing fields, invalid Unicode and excessive input are rejected.
- Native host archives for selected reachable code and version-matched C++ request scopes. Generated frames unwind traps to a host boundary; budgets, deadlines/cancellation and scope cleanup apply to normal and failing native requests.
- Server-only `io` environment access and `db` capability, prepared SQLite operations, durable per-principal KV data, read-only requests, serialized writer transactions, sticky mutation failure and rollback on non-success/trap/cancellation. The table layout and binary key/principal collation are checked.
- Native HTTP/HTTPS server builds with cpp-httplib/OpenSSL, strict hashed-bearer configuration, identity injection, bounded workers/queue/body/URI/time, sanitized errors, static assets with canonical containment and coordinated shutdown.
- Runtime component object caches with integrity checks and captured source/header projections. Native build metadata identifies output kind and runtime components; embedded JSON/HTTP components retain their license notices alongside output, including explicit `-o` copies.
- Explicit language 0.3→0.4 migration of archived multi-file revisions, retaining both old history and complete sources. New walkthrough/task-template files explain model-independent handoff and the graph/source distinction; they do not implement automatic task contracts or prove cross-model quality.
- Toolchain 0.6.0 retains source language 0.4 and adds the optional pure `commands(before, after, event)` browser entry, `std/net.nex` command/response types and a bounded same-origin HTTP adapter. Response events preserve strict JSON/i64/UTF-8 semantics; network/timeout/cancel/limit failures are explicit values. Existing four-function applications still work.
- A connected client/server example shares public models and supports runtime bearer sign-in, durable per-user task CRUD, URL filters, refresh/cancel, sign-out/re-entry and stale-response rejection. No credentials are embedded by the build or retained across page reload in this example. General source async remains pending; the following checkpoint adds generated endpoint helpers.

- Toolchain 0.7.0/source language 0.5 adds checked endpoint declarations with unique methods/routes/operations, authenticated Context, public wire models, bounded schemas, stable graph IDs/handler edges, endpoint context and atomic declaration/function patches. nex.program/4 identities include contracts; old 0.4 bundles require explicit migration and retain history.
- `nex api` generates and checks frozen server/client projects before atomic materialization. Server routers strictly decode input and encode tagged result/status responses under existing request transactions. Client SDKs extract only required public model declarations and pure request/response helpers. Typed commands validate successful response data before callback delivery. OpenAPI 3.1.1 and exact NEX wire contracts accompany output; fixed routes/JSON are implemented, while path/query parameters and streaming remain open.

- Toolchain 0.8.0 retains source language 0.5 and adds standard MLIR/DWARF types, stack locations, parameter records and lexical binding scopes. Direct LLVM slots and hidden prologue initialization keep source breakpoints and variable ranges accurate. Debug parameter storage borrows values and does not participate in owned cleanup. LLVM module verification runs after translation.
- Native builds capture a versioned debug manifest, original/projected paths, reachable logical/native function mapping and matching LLDB formatter. Previews read stopped values without inferior function calls, use lazy children and bound recursion/item/node/text work. `nex-values` exposes bounded revision-attributed JSON; `nex debug --json`/`--kind dap` generate lldb-dap session settings. Cache validation includes source projections, manifest, formatter and macOS DWARF contents.

- Toolchain 0.9.0 retains source language 0.5 and compiles reachable NEX functions as separate source-module objects. Body-only changes reuse unaffected module objects; consumed function interfaces, effects and transitive record layouts invalidate their consumers. A dependency index records direct/reverse calls and layout providers, including type-only modules. The frontend still checks the loaded graph; finer function/frontend reuse, cross-unit LTO and test-result caching remain open.
- Native object inputs include the compiler's probed target ABI/data layout, profile, runtime ABI, consumed semantic contracts and exact immutable source projection. Content-addressed objects and IR are verified before use and published through atomic indexes; corruption triggers repair. Shared frozen source projections preserve imported-module debugging across unrelated edits and archived builds. `compilation.json` records unit inputs, dependencies and reuse; CLI counters describe the current invocation. The build guide and model-independent language pack document these contracts and limits.

- Toolchain 0.10.0 retains source language 0.5 and instruments reachable native functions in profile builds. Local reports record monotonic inclusive/self/max wall times, calls/completions/aborts, bounded timeline events and managed shallow object/handle allocation pools. Selected graph name/content matching supplies project-local node IDs; a separate link unit embeds exact build/revision identity without invalidating reusable NEX modules. Debug/release output omits the profiler.
- The pinned unmodified Tracy 0.14.1 client supports explicit localhost CPU-zone and named memory-pool capture, with matching distribution notices. Normal local profile reports leave Tracy dormant. Request-boundary cleanup and runtime traps close active frames; report limits and dropped records are explicit. The installed profile guide, descriptor, prompt, protocol and example document measured coverage and pending browser/GPU/dynamic-buffer work.

- Toolchain 0.11.0 retains source language 0.5 and adds snapshot-bound JSON scalar contracts plus linked Z3 verification. Pure i64/bool/unit roots use pre/postconditions, checked arithmetic/assertion VCs, path-sensitive acyclic body expansion and annotated inductive loops with strict nonnegative rankings. Division/remainder encode NEX truncation and MIN/-1 cases explicitly; short-circuiting, argument order, mutable bindings and nested shadows retain source rules.
- Contracts bind the semantic revision, exact source bundle, qualified function content and loop coordinates. Reports distinguish proven, concrete/inductive counterexamples, inconsistent preconditions, unknown, timeout and unsupported scope. Each run saves source/contract/query/result artifacts; graph node IDs come from the selected store. Proofs do not remove runtime guards or insert JSON pre/postconditions into execution. Heap/effect/resource proofs and recursion remain open; task-acceptance linkage is added by the 0.12 checkpoint below.

- Toolchain 0.12.0 retains source language 0.5 and adds model-independent `nex.task/1` contracts: reviewed goals/requirements, qualified graph bindings, target/check linkage, pinned test bodies and formal property intent. Checks cover native/TypeScript differential tests, builds, exact native/reference observations, scalar proofs, effects/realms, defined profile budgets and API generation. Unknown kinds/fields are rejected; unsupported targets/realms, unproven checks, output limits, timeouts and interruptions cannot pass acceptance. Static graph linkage is not dynamic coverage or proof of natural-language completeness.
- Task runs freeze checked multi-program source bundles, derived proof contracts and the selected runtime/lib/web/debug resources without changing project HEAD. Checkpointed receipts, logs, artifacts and SQLite history retain candidate/task/compiler identity. Replay validates every captured input, exact compiler and matching trusted executable resources, rebuilds derived workspaces and reruns checks after live source deletion. Named POSIX process groups clean ordinary descendants on timeout, output overflow, SIGINT/SIGTERM and normal leader exit. External tools/environment are not fully frozen, deliberate process-group escape is outside cleanup, and this is not an OS sandbox or signed attestation.

- Toolchain 0.13.0 retains source language 0.5 and evaluates pure stopped-frame NEX expressions through the existing parser, module resolver, checker and reference interpreter in a separate process. Arithmetic, Unicode, immutable aggregates, result/JSON operations and pure user calls preserve source semantics; frame realm/import visibility and effect restrictions remain checked. Snapshot decoding is lazy for unexecuted short-circuit branches. Expression/step/value-growth/wire budgets fail explicitly. The shared strict JSON validator rejects duplicate/escaped-equivalent keys and malformed UTF-8 before frame normalization, while retaining existing application wire behavior.
- LLDB commands `nex-eval` and `nex-frame` capture exact referenced roots through DWARF and read-only memory access, including long UTF-8 strings and embedded NUL, validating tags/nominal names/field order. Innermost bindings and requested frames are respected; incomplete roots are unavailable, never fabricated zeros or clipped evaluator inputs. The frozen stdio NEX DAP bridge supplies watch/hover evaluation, immutable computed children/paging, independent backend/computed references and stop expiry. Encoded internal commands prevent source newlines becoming debugger commands. At the 0.13 checkpoint large-root partial reads were pending; 0.14 adds the aggregate projections below. Current live coverage remains macOS ARM64/libc++; other host layouts, browser watches and an installed editor extension remain pending.

- Toolchain 0.14.0 retains language 0.5 and the native runtime ABI. Interpreter-only references carry stopped-frame list/record/result paths through pure calls, aliases, constructors, loops and branches. Lengths, nominal layouts, result tags and dynamically selected fields/elements are requested only when evaluated. Whole-value operations still require complete bounded operands; strings and direct large-root DAP paging remain open.
- `nex.debug-frame/2` adds exact shape/value captures and `inspect --kind demand` returns a typed missing-read request for a fixed source/stop. Legacy full `/1` frames remain accepted. The frame validator rejects ill-typed paths, duplicate reads, conflicting full bindings and invalid shapes/wire values. Exact vector reads validate raw begin/end pointers and DWARF element sizes; LLDB location errors never become fabricated empty collections. The live provider checks stop/selection before and after each read and bounds replay to 128 exchanges/ten seconds. Saved partial frames fail explicitly for uncaptured data.

- Toolchain 0.15.0 adds persistent local-store identities for checked parameters, blocks, statements and expressions, separately from Merkle content hashes and deterministic function-content/path site keys. Structural children, lexical binding references (including shadowing initializers/assignments) and qualified call references are exposed through paged `operations`/operation-context queries and an additive graph export. Conservative matching retains unambiguous roles/content, preserves recorded revisions and gives fresh identities to ambiguous duplicates. Imports rederive local identities from checked sources; cross-store reconciliation is pending.
- SQLite schema 2 upgrades transactionally to 3 without changing archived sources, revision hashes, language versions or function IDs. Current-language operation metadata backfills lazily and verifies stored content/site hashes. Candidate identity changes share the checked source transaction. Query pages/children and large-definition omission are explicit. Native MLIR NameLocs, compiled manifests and reachable TypeScript maps carry deterministic sites; `eval` failures add persistent IDs/revision/exact-source hash, and TypeScript trap sites carry the same key. `nex-operation` exposes source-position candidates in actual LLDB/DAP stops. Native optimized instruction identity, native textual trap IDs and operation profiling remain open; language 0.5/function/program/native runtime formats are unchanged.

- Toolchain 0.16.0 / source language 0.6 adds nominal algebraic enums with immutable typed payloads and exhaustive statement matches across the checker, reference interpreter, native MLIR and TypeScript. Scrutinees run once; pattern scopes, discard bindings, all-path returns, effects/realms and cleanup retain source semantics. Recursive enum/record/list values and strict tagged JSON work across backends. API generation extracts public enum models and emits wire/2 descriptors and exact OpenAPI oneOf schemas; typed browser responses reject invalid cases/payloads before event delivery.
- New canonical formats are function/4, enum/1 and program/5. Explicit 0.5→0.6 migration preserves archived sources/history and local function IDs. Runtime-view/2 and debug-expression/2 describe the added enum ordinal. Matching LLDB views validate the actual stopped tag/name/layout; pure match helpers demand only used selected-case payloads, and DAP computed enum children support paging. Operation case identities anchor on names across declaration reordering and nominal layouts invalidate native consumers. Old SDK 0.15 is retained for language 0.5 frames/receipts. Match expressions, nested patterns/guards, builtin result patterns, general user generics and richer data proofs remain pending.

- Toolchain 0.17.0 / language 0.7 adds parametrically checked generic functions, structures and enums, including unused bodies, argument/expected-type inference, finite recursive specialization and explicit resource diagnostics. Every instance carries its source template/arguments. Native/TypeScript use concrete code and retain checked arithmetic, evaluation order, immutable values, effects/realms and cleanup. Generic constraints, higher-kinded types and function values remain pending.
- Function/5, structure/3, enum/2 and program/6 distinguish checked source definitions from derived specializations; source revisions exclude instances. Context links non-editable instances to editable templates; atomic template repairs recheck all callers. Source export emits original declarations once. Native generic body edits reuse unchanged callers while concrete layouts/type arguments participate in dependencies. Public generic API extraction preserves phantom arguments/imports and emits checked wire/2/OpenAPI models. Generic watches resolve frame type arguments and instantiate uncompiled pure helpers without changing revision/stop state. Runtime-view/2 is unchanged; exact matching compiler/resources are still required. Task requirements link actual instances back to their source templates, while profile budgets retain concrete measured names. SDK 0.16 is preserved for old language 0.6 archives, frames and receipts.

## Verification evidence

- **0.23.0 / language 0.10** passed **230 cases in all 24 CTest suites** on macOS ARM64 in 311.20 seconds. Linux ARM64 and emulated Linux x86-64 each ran 230 declared cases: 224 executed and six explicit macOS-SDK skips. Their full CTest runs passed in 383.11 and 1310.15 seconds. Source/build/install verification and logs are retained under `build/linux-ARCH/checkpoints/0.23.0`; macOS evidence is `build/ctest-023-portable-final.log`.
- The installed SDK passed all nine maintained handoff phases on macOS ARM64, Linux ARM64 and Linux x86-64, in 38.247, 29.533 and 101.223 seconds respectively. Linux's second container has no `/src` mount and external network disabled. All 60 indexed resources and seventeen guides are present. The scenario exercises reviewed task failure, fixed-intent graph repair/import, generic snapshot closures and wire roundtrips, native/reference/TypeScript agreement, standalone output, profile attribution/cleanup, archived replay/export, scalar Z3 proof and an actual locked Vite build. Mac/Linux ARM64 additionally verify actual archived callable DAP and offline replay after source deletion. Linux x86-64 records live debugging false. Reports: `build/sdk-handoff-023-verified/report.json` and each Linux `source-free-sdk.json`.
- Installed macOS LLDB/DAP passed the large-capture callable case in 9.241 seconds. Linux ARM64 passed all six live suites, including eleven callable cases in 34.383 seconds. Both validate native function symbols, lazy reads through an unread 32,768-item capture, alias identities, generic closure scopes, source-deleted snapshots, DAP pages and stop expiry. The current closure-state web build passed Chromium, Firefox and WebKit interaction (three cases, 2.2 seconds). Browser dependencies/notices are unchanged. Evidence: `build/sdk-callable-dap-023.log`, Linux `live-function_debug.log`, and `build/function-web-023-browsers.log`.
- Genuine SDK 0.22 archives verify successful 0.9 migration and atomic rejection/explicit wire-bound repair, preserving original source/history and function/operation IDs. The SQL-only fixture path executes on macOS too; its legacy sidecar lacks a database field, so the reader defaults to graph.db without changing archived bytes. The first failed ARM64 and intentionally interrupted x86-64 reports are retained under `evidence-023-*`, superseded by the complete passing runs. SDK 0.22 still inspects its frame and replays its receipt; SDK 0.23 rejects those with E_DEBUG_BUILD/E_TASK_COMPILER. Task/proof pin updates assert unchanged source hashes, clauses, loops and acceptance intent; current schemas pass independent jsonschema 4.23 validation. See `build/version-010-old-sdk-compatibility.json`, `build/version-010-acceptance-pin-migration.json` and `build/version-010-schema-evidence.json`.


- **0.22.0 / language 0.9** passed **201 cases in all 22 CTest suites** on macOS ARM64, most recently in 256.01 seconds after the SDK handoff addition. Linux ARM64 and Linux x86-64 each passed 195 executed cases plus six macOS-SDK skips, in 358.20 and 733.94 seconds respectively; x86-64 executes under Docker emulation. Linux ARM64 also passed the five opt-in live debugger suites, including all 14 matching cases. The installed macOS SDK passed all 14 matching cases; an additional actual NEX DAP matching check passed separately. Evidence: `build/ctest-022-handoff.log`, `build/sdk-matching-022.log`, `build/sdk-matching-dap-022.log` and the Linux `checkpoints/0.22.0` reports/logs.
- The maintained installed-SDK scenario `tools/sdk_acceptance.py` passed its nine phases on macOS ARM64 and both Linux architectures. Linux runs in a second container with only the read-only SDK and fresh evidence mounted, `/src` absent and external networking disabled. All three perform an actual locked TypeScript/Vite build. macOS/Linux ARM64 additionally launch actual NEX DAP/LLDB after original source deletion, evaluate a nested match, capture its partial frame, exit normally and evaluate the saved frame offline. Linux x86-64 explicitly records live debugging false. The workflow requires failure of the wrong reviewed task, then unchanged-task-hash acceptance after graph repair, independent graph import, native/reference/TypeScript agreement, profile content/node attribution and balanced managed pools, archived task replay/export and the installed scalar proof. Expected failure is recorded as `not_satisfied`, never acceptance. All 56 indexed resources and sixteen guides are installed. See `build/sdk-handoff-022-verified/report.json` and Linux `source-free-sdk.json`; negative checks retain old evidence and reject an available forbidden source path (`build/sdk-acceptance-negative-022/verification.json`).

- Toolchain **0.21.0 / language 0.8** passed **188 cases in 21 CTest suites** on macOS ARM64 in 338.48 seconds, and 182 executed cases plus six macOS-SDK skips on each Linux target: ARM64 in 395.66 seconds and x86-64 under Docker emulation in 760.43 seconds. Eleven new normal cases cover builtin bounds, rejected unused/forwarding programs, contextual literals, arithmetic traps, immutable values/order/cleanup, canonical bound order, optimistic graph patches/archives, genuine 0.7 migration, bounded API model extraction, pure watch/scalar proof and pinned task repair/replay. Evidence: `build/ctest-021.log` and the Linux `checkpoints/0.21.0` reports/logs.
- Installed SDK constraint checks passed **12 cases** on macOS ARM64 and Linux ARM64, including real LLDB generic parameter scopes, an uncompiled string helper, rejected bad bounds and unchanged stop state. Linux additionally passed all seven debug, 23 expression and fifteen generic live-suite cases. The pack contains **52 indexed resources** and fifteen guides. A bounded generic browser-state/counter example passed TypeScript/Vite compilation and all three Chromium/Firefox/WebKit interaction cases, with the existing dependency lock unchanged. Evidence: `build/sdk-constraints-021.log`, Linux ARM64 `live-*.log`, `build/constraints-web-build-021.json` and the generated Playwright results.
- Both Linux 0.21 installed-SDK workflows passed with external network disabled: constrained and ordinary generic native/interpreter/TypeScript agreement, strict ELF DWARF, standalone output, profiles, pinned tasks/archived replay, scalar proof and authenticated persistent storage. Separate source-free containers passed project creation, bounded examples, backend agreement and archived execution after source deletion. All 52 indexed files/fifteen guides were synchronized without changing the tested compiler bytes. Evidence: `build/linux-ARCH/checkpoints/0.21.0` and `build/sdk-resource-verification-021.json`.
- Actual **0.20/language 0.7 → 0.21/language 0.8** migration preserved archived sources, history, function IDs and operation IDs after live-source deletion. The preserved 0.20 SDK still evaluated its original frame and replayed its original receipt; 0.21 rejected these with `E_DEBUG_BUILD`/`E_TASK_COMPILER`. Task/proof example snapshot metadata was regenerated while retaining reviewed pre/postconditions, loop invariants and acceptance assertions. Current schemas/examples and Linux SDK task/configuration/catalog documents passed independent jsonschema 4.23 validation. Evidence: `build/sdk-constraints-migration-021.json`. The 0.20 SDK is preserved on macOS and both Linux architectures.

- Toolchain **0.20.0 / language 0.7** passed all **20 CTest suites** on macOS ARM64 (177 cases, no skips, 289.30 seconds), Ubuntu 24.04 ARM64 (171 executed, six macOS-SDK skips, 253.44 seconds) and Ubuntu 24.04 x86-64 under Docker emulation (171 executed, the same six skips, 268.37 seconds). Both Linux runs declare 177 cases; historical 0.5/0.6 migration assertions execute using genuine old-SDK store fixtures instead of attempting to launch Mach-O binaries. Evidence: `build/ctest-020-final-formatter.log` and the retained aggregate `build/milestone-020-verification.json`; retained Linux SDK evidence is under `checkpoints/0.20.0`, while rolling Linux logs now describe the current checkpoint.
- Installed Linux SDK workflows passed on both architectures with external network disabled: all **51 indexed resources** and fifteen guides, generic native/interpreter/TypeScript agreement, strict ELF DWARF verification, standalone execution without NEX/LLVM/Z3 dependencies, measured profiles, pinned task acceptance and archived replay after source deletion, scalar Z3 proof, authenticated per-principal SQLite isolation and restart persistence. Streaming artifact copies also passed native/task/replay checks on Docker/macOS shared storage. Actual task, normalized toolchain and catalog documents passed independent jsonschema 4.23 validation. Separate containers with **no source checkout mounted** created/tested projects, ran native/TypeScript generic tests, executed archived revisions after live-source deletion and ran a copied standalone binary. Evidence: each `build/linux-ARCH/sdk-smoke.json`, `source-free-sdk.json` and `build/linux-schema-validation-020.json`.
- The installed macOS ARM64 and Linux ARM64 SDKs each passed **seven debugging, 23 expression and fifteen generic cases** with real LLDB/DAP; these totals include the corresponding normal cases. They cover source stops/steps, shadows/mutation, exact/partial values, pure watches, large aggregate paging, enum/generic children, archived inspection and clean resume. A Linux libstdc++ summary truncated embedded NUL; length-aware bounded reads fixed it. The new live case verifies short/long NUL strings, literal escape preservation and a UTF-8 scalar crossing the 4096-byte preview boundary. Evidence: `build/live-{debugging,expressions,generics}-020.log` and the Linux ARM64 `live-*.log`. Linux x86-64 live ptrace/debugging remains unverified under emulation.
- Identical Linux objects linked with GNU ld failed strict DWARF string-offset verification; LLVM LLD passed. The bad ELF/intermediate objects and comparison are retained under `build/linux-arm64/debug-evidence`. A separate direct-Clang probe reproduced literal-percent output-path failure, fixed by staging ELF/archive output before streaming it to the destination. Selected linker configuration/hash/cache invalidation and Unicode/percent-path archives linked into a trusted C++ host are regression-tested. Fingerprint policy is now `nex.toolchain-snapshot/2`; old receipts require their captured compiler binary/resources, and changing SDKs requires reviewing/re-pinning new toolchain hashes.

- Toolchain **0.19.0 / language 0.7** passed **175 cases in 20 CTest suites** in 238.96 seconds. Eight task-toolchain cases cover non-executing inspection, stable normalized default/explicit inputs, pinned host native/test/run/profile acceptance, real foreign application/archive output, source-deleted replay with replacement trusted configurations, unsupported foreign execution, compiler/SQLite/OpenSSL/SDK-setting changes, missing current trust and paired schema fields. A rehashed forged receipt cannot select another compiler, and a successful child cannot pass when post-execution fingerprint inspection detects changed inputs; independent checks continue. Evidence: build/ctest-019.log.
- The installed **0.19 SDK** passed all **eight task-toolchain cases** outside source projects in 59.739 seconds. A separate installed-resource workflow loaded all **46 indexed resources**, inspected host/Intel configurations, checked pinned task intent, accepted host tests/application plus an actual x86_64 archive, then replayed the same task after deleting original sources/task/config files using equivalent current trusted configurations. Actual task/catalog/normalized configurations passed independent JSON Schema validation. Evidence: build/sdk-task-toolchains-019.log and build/sdk-task-smoke-019.json. SDK 0.18 is preserved in build/sdk-0.18.0. Full SDK contents/support tools/environment and Intel execution remain outside the verified scope.

- Toolchain **0.18.0 / language 0.7** passed **167 cases in 19 CTest suites** in 190.87 seconds, including six native-target cases. Real x86_64 macOS builds cover generic/JSON programs, release/profile output, every generated/runtime object, static archives and dSYM architecture, cache separation/warm reuse, archived reconstruction after source deletion and SDK SQLite headers/stubs. Rejected cases cover unsupported targets, malformed configurations, mismatching compiler ABI, host dependency fallback and foreign execution commands. Host compiler symlink mode and Darwin/macOS normalization are exercised. Evidence: build/ctest-018.log.
- The installed **0.18 SDK** passed **15 generic cases**, including actual host LLDB/DAP, in 68.141 seconds. A separate project outside the checkout loaded all **45 indexed resources**, discovered the target capabilities/schema, passed host native/TypeScript tests, ran with matching reference output, produced x86_64 executable/library artifacts and rebuilt an archived Intel revision using its native object after deleting its source/build directory. The actual toolchain file and its schema passed independent jsonschema validation. Intel native execution/debugging remains unverified: Rosetta is unavailable. Evidence: build/sdk-generics-live-018.log and build/sdk-targets-smoke-018.json. The previous 0.17 SDK is preserved in build/sdk-0.17.0.

- The final 0.17 build passed **161 cases in 18 CTest suites** in 173.35 seconds. Fourteen generic cases cover parametric rejection of unused invalid bodies, recursive type/function instances, native debug/release/reference/TypeScript equality, implicit/explicit/contextual inference, operator result-vs-operand constraints, unwrap/intrinsic/condition/index propagation, phantom/private types, scopes/aliases/evaluation order, finite expansion limits, abstract-entry rejection, qualified-argument shorthand, template graph repair/archives, actual 0.16 migration, generic API model extraction, watch-only instantiation, scalar instance proofs, native provider/caller reuse, and template-linked task/profile/replay. Evidence: build/ctest-017-final.log.
- A real generic-state app passed TypeScript/Vite production compilation and three Playwright interaction cases (Chromium, Firefox, WebKit). Installed SDK LLDB/DAP verified concrete T scopes, exact Box<i64> captures, uncompiled pure helpers, computed children, same-stop/handle preservation and archived offline inspection after source deletion. Evidence: build/generic-web-build-017.json and build/sdk-generics-live-017.log. These are macOS ARM64/headless engine checks; other hosts remain unverified.
- Installed **0.17.0 SDK / language 0.7** passed an outside-checkout workflow with fourteen guides and 44 indexed resources. A bad first<T> failed pinned native/browser acceptance; a source-template patch preserved its operation ID, fixed all instances, and passed/replayed the same task intent, including a concrete-instance profile budget. Export contained templates once, archived execution survived live source deletion, and standalone native output did not link LLVM/Z3. Generated nested Box<Maybe<i64>> models crossed an authenticated real HTTP server with exact i64 bounds, strict invalid-input rejection, repeated trap cleanup and recovery. Actual 0.16→0.17 migration retained old source/history/function/operation IDs; the preserved 0.16 SDK replayed its old frame/receipt, while 0.17 rejected that receipt. Independent jsonschema 4.23 validation covered installed schemas/responses and nested generic OpenAPI data. Evidence: build/sdk-generics-smoke.json and retained artifacts.

- Installed **0.16.0 SDK / language 0.6** passed an outside-checkout authoring workflow with fourteen guides and 42 indexed resources: wrong enum dispatch failed pinned acceptance, an optimistic graph patch kept operation identity and fixed native/TypeScript output, and the same task intent passed and replayed after source deletion. Installed LLDB captured exact enum paths and pattern bindings at the same stop; offline inspection and exported source tests remained usable. Actual 0.15→0.16 migration retained old sources, function IDs and operation IDs. Preserved SDK 0.15 evaluated its old frame and replayed its old receipt, while 0.16 rejected that receipt with E_TASK_COMPILER. Three real installed protocol responses independently passed Draft 2020-12 JSON Schema validation; generated OpenAPI and valid/invalid enum instances passed separate jsonschema 4.23 checks. Standalone native output did not link LLVM/Z3. Evidence: build/sdk-enums-smoke.json and retained artifacts.
- The complete expression suite with real LLDB/DAP passed **23 cases in 52.742 seconds**, including six live cases. The separate existing native-debug suite passed all six cases (three live) in 25.991 seconds. These cover unchanged string/record/result previews, exact/partial captures, scopes, stop identity, huge aggregates, child paging and clean resume/termination with runtime-view/2.

- The 0.16 build passed all **147 cases in 17 CTest suites** in 169.38 seconds. Eight enum cases cover recursive values, native debug/release/reference/TypeScript agreement, evaluation order and single scrutinee evaluation, fallthrough/return/loop ownership, immutable aliasing, discarded/shadowed bindings, negative coverage/type/effect/realm/visibility programs, special payload field names, exact JSON/depth boundaries, actual 0.15 SDK migration and persistent case identities/native cache invalidation. API checks add generated enum clients/OpenAPI and live authenticated strict input/trap/recovery cleanup. Partial watch tests reject bad tags and prove unused scalar/aggregate payloads are not demanded. Evidence: build/ctest-016.log.
- The enum-state application passed real TypeScript/Vite production compilation and all three browser interaction scenarios (Chromium, Firefox, WebKit), exercising each case, Unicode text, pure transitions and reload. A real stopped LLDB/DAP session validated pattern bindings, selected enum payload reads, a large unread payload, paged computed enum children, identical stop/handle identity and offline replay. Evidence: build/enum-web-build-016.json, build/enum-live-016.log; these are macOS ARM64/headless engine checks, not wider platform certification.

- `cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug` and `cmake --build build -j 4` succeeded.
- `ctest --test-dir build --output-on-failure -j 3` passed all sixteen suites on 17 October 2026: **137 cases** in 157.95 seconds. They comprise 19 core, 13 module/lock/snapshot/migration, seven result/wire/native-host, seven storage, two HTTP/HTTPS, seven TypeScript/web, two browser-command, eight endpoint/API, three native debug metadata/cache/session, eight incremental-compilation, six profiling, ten verification, fourteen task-acceptance, sixteen expression, twelve operation-graph and three DAP-transport cases. Core tests include negative programs, generated arithmetic/Unicode oracles, debug/release traps, ownership, graph conflicts/cache integrity and LLDB source lookup. Native/TypeScript/interpreter result/JSON tests cover strict inputs and identical errors, including canonical decimal integers, Unicode scalar validation and the single optional leading UTF-8 BOM; the pinned vendored-header hashes and copied license notices are checked. Command tests exercise pure transition agreement in TypeScript/interpreter and a shared-realm native projection, signature/library-shape rejection, atomic batch rejection and transport limits/UTF-8/cancel/timeout behavior in Node.
- Expression checks cover scalar/aggregate/result/JSON semantics, exact integer wire values, shadow/context metadata, alias/private visibility and realm/effect gates, arithmetic/bounds traps, lazy unavailable inputs, source integrity after deletion, purity/step/allocation/token limits and native/TypeScript/reference observations. Raw/escaped duplicate frame keys, malformed UTF-8 and optional leading BOM are checked before normalization. DAP transport tests cover bounded UTF-8 framing, source encoding, reverse-request identity and monotonic terminate-disconnect sequencing after client EOF. Partial-capture checks additionally cover large logical lengths, dynamic helper indices, nominal/nested paths, result tags without unused payloads, pure loops/constructors/aliases, complete-value materialization, malformed paths/shapes and missing/invalid captures. The large fixture has equal native/TypeScript/interpreter observations. The final full run includes all three transport cases.
- Twelve operation cases verify editing/reordering/insertion, distinct duplicate identities and conservative rematching, parameter roles, lexical references, historical lookup/reversion, database backfill and stale-patch rollback, foreign derived-ID rejection, semantic annotation equivalence, cross-entry library identity, a 2,000-declaration unchanged function, paging/omission, native MLIR manifests and matching interpreter/TypeScript failure keys. The browser regression now checks all four error-site items against interpreter diagnostics across twelve arithmetic/bounds cases. Four actual installed query/context/export responses independently passed Draft 2020-12 validation with jsonschema 4.23.0 (`build/operations-schema-015.json`).
- Ten opt-in live cases passed: two operation LLDB/DAP cases in 4.596 seconds, five expression cases in 16.135 seconds and three legacy debugging cases in 5.093 seconds. Source-site candidates resolve to archived persistent operations after source deletion without resuming or mutating the inferior. Existing stops/steps, Unicode/NUL, shadowing, large-value projections, computed child pages, nonselected frames, source encoding, stale-reference failure and clean termination still pass on macOS ARM64/libc++.
- The installed **0.15.0 SDK/language 0.5** passed an outside-checkout workflow with fourteen guides and 41 indexed files. A deliberately wrong adjustment returned 43. Exact LLDB source-site/Watch evidence resolved its graph operation; a revision-checked repair retained the persistent ID while changing content/site keys and produced 42. The unchanged reviewed task hash/tests/output criteria then passed native/TypeScript acceptance and replay after original source deletion. Actual NEX DAP candidates resolved to the repaired graph, and the old operation/frame remained queryable. A copied binary ran independently without LLVM/Z3 links. The preserved 0.14 SDK still evaluated its prior partial frame. A project created and run by the actual 0.14 compiler then upgraded under 0.15 with the same semantic revision, source/functions, function IDs and output, plus the new operation index. Evidence: `build/sdk-operations-smoke.json` and its retained external workspaces; the old SDK is retained at `build/sdk-0.14.0`. These are host checks, without cross-platform or general performance certification.

- The installed **0.14.0 SDK/language 0.5** passed an outside-checkout debug/repair/acceptance workflow with all thirteen guides and 38 indexed files. Watch observed 85 in an intentionally wrong imported helper; a revision-checked graph repair produced 84 under the same captured inputs and unchanged task hash/tests/output criteria. One native module compiled and one was reused. The old partial frame/source snapshot still computed 85 after the graph changed and original files were deleted. The installed NEX DAP bridge evaluated the repaired archive and expanded typed records; task replay passed after deletion, and a copied binary ran with the exact reviewed output without LLVM/Z3 links. Evidence: `build/sdk-expression-014-smoke.json` and its retained external workspace.
- A second installed-SDK workspace exercises the large fixture through actual LLDB and NEX DAP: a 32,768-string list, record/result projections and a 2 MiB unread error message. The saved last-element frame is 1,144 bytes with three exact captures; it still evaluates after source deletion. Whole-list/message evaluation explicitly fails its capture limits. Stop identity and the physical list handle stay unchanged, paged computed children work, and the copied binary runs without LLVM/Z3 links. Evidence: `build/sdk-partial-smoke.json`. Both actual installed partial frames and both schema definitions passed independent Draft 2020-12 validation with jsonschema 4.23.0; raw and escaped-equivalent duplicate capture keys were independently rejected by the installed compiler (`build/partial-schema-014.json`). These are macOS ARM64 host checks, not cross-platform certification or a latency guarantee.

- Task tests exercise fixed-intent repair, changed-test/property rejection, no-execution preflight and HEAD preservation, candidate rebinding, multi-program archived selection and conflicting shared modules, independent failure propagation, unsupported scope, Unicode/zero bytes/exit status, profile budgets, exact replay after source deletion, input/resource injection rejection, timeout/output/interrupt checkpoints and real owned-grandchild cleanup. A real Vite application, native HTTP server, archive and generated API/OpenAPI are copied as artifacts; server-only code is absent from browser assets. The task schema/example independently passed Draft 2020-12 validation with jsonschema 4.23.0.
- `python3 tests/debugging.py build/nex --live Live` passed the three additional actual LLDB/DAP/bounded-preview cases in 4.550 seconds for 0.12; the three ordinary debug cases also passed in the full CTest run.
- The installed **0.12.0 SDK/language 0.5** passed an outside-checkout acceptance workflow with all twelve guides and all 34 indexed files. Seven checks/four requirements failed the deliberately broken candidate, then passed a revision-checked graph repair without changing the reviewed task hash, pinned tests or formal pre/postconditions. The original raw proof sidecar remained stale as expected; task-derived metadata was checked separately. Clean exported sources passed native/interpreter/TypeScript tests, a copied binary ran independently without LLVM/Z3 links, and all criteria passed again after original source/task/proof deletion. History retained failure, success and replay receipts. Evidence: `build/sdk-task-smoke.json` and its retained external workspace.
- Scalar verification tests cover branch/call contracts, actual overflow and negative-result counterexample replay in interpreter/native/TypeScript, signed division/remainder and MIN boundaries, short-circuit safety, nested loop invariants/rankings/shadowing, consistency and definedness of preconditions, stale/archived/exported sources with independent graph node IDs, unsupported heap/effect/recursive/missing-loop rules, resource exhaustion and SMT-LIB replay through the actual Z3 CLI. The example proves both increment and loop-based double contracts. The detached JSON schema and example independently passed Draft 2020-12 validation with jsonschema 4.23.0.
- A separate difficult nonlinear postcondition under a 1 ms solver query budget returned timeout with reason timeout; its exact source/contract/SMT/report artifacts remain under `build/verification-timeout-evidence`, indexed by `build/verification-timeout.json`. Resource-limit exhaustion returns unknown in default tests; neither status is accepted as a proof. This records the exercised host response, not a stable timing requirement for other solvers/hosts.
- Profiling tests check observable native/interpreter/TypeScript agreement, recursion/early returns, checked traps, exact graph node/content attribution, event limits with preserved aggregates, archived object reuse and Unicode/percent paths, a bounded 100-function CLI response with a complete 121-function saved report, pinned client inventory/notices and dormant release output. A real four-thread native host exercised normal/error/budget/cancellation requests: all 40 outer and 32 inner calls were balanced as completed/aborted, and every managed allocation was freed.
- Three direct Tracy captures passed with the application listener ready before capture. Upstream 0.14.1 capture/csvexport read the three NEX functions with matching call counts and frozen paths; a separate reader using upstream TracyServer verified the exact embedded build/revision identity, 402 handle allocations/frees and 321 shallow object allocations/frees, with zero active allocations/usage. Evidence: `build/tracy-profile-acceptance/acceptance.json` and its saved traces/CSV. Starting capture before the application listener was ready sometimes failed the initial handshake on this host; the verified startup ordering is documented. Viewer/capture tools remain external to SDK installation.
- Reproducible `tests/profile_benchmark.py` measured nine whole-process samples per mode for the same 50,000 checked-add workload on the host Apple M4 CPU. Observed medians were 2.589 ms in release, 2.778 ms with dormant instrumentation and 7.329 ms with local aggregation/timeline storage disabled. All results and exact call counts matched. These measurements include process launch/report flush and apply only to this workload/host; no general speed or overhead guarantee is claimed. Evidence: `build/profile-benchmark.json`.
- Incremental tests observe actual Clang object-compilation calls as well as build reports. They cover cold/warm builds, body-only edits, effects and return ABI changes, parameter renaming, nested record/JSON layout dependencies, library locks and archived reuse, profile/compiler/runtime inputs, incompatible target rejection, corrupt objects/indexes/local artifacts and concurrent applications sharing a module at Unicode and percent-containing paths. Changed behavior agrees with the interpreter, clean native builds and relevant TypeScript tests.
- Endpoint tests cover rejected declarations, stable graph identity/context, atomic patches, archived generation, explicit 0.4→0.5 migration, transitive model extraction, output atomicity and native HTTP authentication/status/rollback behavior. SDK projection tests include overridden standard libraries and package dependencies: server declarations and unused private code are absent while required client/shared helpers and nominal models remain. OpenAPI output was independently checked against the official OpenAPI 3.1 meta-schema with jsonschema 4.23.0; signed i64 boundaries and trailing line-terminator rejection were also checked with JSON Schema validation.
- The generated typed API client passed **12 Playwright scenarios** (four each in Chromium, Firefox and WebKit) against its compiled generated native dispatcher, including CRUD/isolation/restart persistence and cancellation, malformed schemas, canonical integer strings, optional leading BOM, strict UTF-8, body limits, redirects and timeouts. The latest generated application's Playwright result records `status: passed` with no failed tests. These are macOS headless engine checks, not real-device certification.
- The installed **0.7.0 SDK/language 0.5** passed the temporary-project smoke workflow with all seven matching guides, the documented graph repair and native/TypeScript tests, archived execution after source deletion, endpoint generation/model extraction/context/client transitions, and an independently running authenticated persistent generated native server. The current report is `build/sdk-smoke.json`.
- Native C++ host checks unwind generated-frame traps, bound loops/deadlines/cancellation and verify zero live handles/values across concurrent scopes. Storage checks include principal partitioning, rollback on traps/ignored mutation failure, read-only protection, incompatible schemas and concurrent increments without lost updates. HTTP checks cover trusted self-signed TLS/hostname verification, auth before body reading, oversized-body rejection, malformed models, concurrent creates, trap/budget/timeout rollback, static symlink containment, persistence across restart and shutdown cancellation while a writer transaction is active.
- `nex run examples/arithmetic.nex --json` produced `55\n3628800\n` with exit code 0.
- `nex run examples/modules/main.nex --json` matched the interpreter: `{"name":"NEX","tags":["native","web"]}\nnative + web\n10\n`, exit code 0. All three loaded application/standard-library tests passed in interpreter and optimized native modes.
- `cmake --install build --prefix build/sdk` succeeded for 0.3. In a temporary project outside this checkout, with `NEX_RESOURCE_DIR` set to the installed resources, all four matching guides loaded, the module example passed all three interpreter/native tests in release mode, interpreted/native output matched, its executable ran independently, and the saved revision still ran after both project source files were deleted.
- A separately compiled data example with AddressSanitizer/UndefinedBehaviorSanitizer enabled for its C++ runtime finished with identical output, no reported errors, and zero live managed values. This is a runtime-path check, not a claim that every generated LLVM instruction was sanitizer-instrumented.
- `python3 tests/debugging.py build/nex --live` passed all **six cases** in 17.704 seconds: the three normal debug cases and three additional live LLDB/DAP/bounded-preview cases. Real host launches outside the execution sandbox verified typed parameters at function entry, stopping before a declaration initializer, both shadowed values, scope exit, mutation, source stepping, imported frames, stack inspection and normal program exit. Archived debugging continued after original source deletion. An actual Xcode lldb-dap verified DAP breakpoints, scopes, variables, expandable record children, read-only `nex-values` through its REPL and clean resume/exit. A shared nested collection representing a very large logical tree exercised lazy children and bounded previews. These checks cover macOS ARM64/Apple LLDB with libc++; other debugger hosts remain unverified.
- The installed **0.8.0 SDK/language 0.5** passed an outside-checkout debug smoke check: all eight matching guides and every indexed document/example were present; installed example tests agreed in interpreter/native/TypeScript; the debugger captured the exact installed formatter; archived debugging after original source deletion showed typed shadowed values and completed normally. The separate current report is `build/sdk-debug-smoke.json`.
- The installed **0.9.0 SDK/language 0.5** passed an outside-checkout incremental smoke check with all nine guides and every indexed document/example. A cold module example compiled four objects; a warm build reused four. A model-body edit compiled one and reused three, with matching native/interpreter output and passing native/interpreter/TypeScript tests. After deleting the original sources, old build directory and shared source cache, the archived revision reused all four objects, restored its exact output and supported real LLDB inspection of a typed imported parameter through normal exit. Evidence: `build/sdk-incremental-smoke.json`. This single-host example observed 952 ms for a cold build and 279 ms for the body edit; these are not general performance guarantees.
- The installed **0.10.0 SDK/language 0.5** passed an outside-checkout profile smoke check with all ten guides and every indexed document/example. Installed profile output agreed with interpreter/native/TypeScript tests and a separately copied executable ran without NEX resources, retaining notices. After deleting live sources, the old build and source cache, the archived build reused its module, restored frozen files and retained exact node attribution/output. An installed instrumented HTTP/SQLite server handled authenticated Unicode CRUD and clean shutdown with balanced measured object/handle pools. Evidence: `build/sdk-profile-smoke.json`; temporary servers, credentials, databases and projects were removed/stopped.
- The installed **0.11.0 SDK/language 0.5** passed an outside-checkout verification smoke workflow with all eleven guides, contract schema and every indexed document/example. It proved the installed scalar/loop contracts using Z3 5.3.1, found the overflowing input, applied a revision-checked graph repair and proved the reviewed replacement contract. Stale contracts were rejected; native/interpreter/TypeScript behavior agreed. Exported and archived source snapshots remained verifiable after live source deletion, and independent graph IDs were attributed correctly. A copied native program ran without compiler resources and did not link Z3/LLVM; solver resource exhaustion stayed unknown. Evidence: `build/sdk-verification-smoke.json` and its retained proof artifacts. Z3 is an external development/compiler dependency, not a generated-application dependency.
- `nex build examples/web/main.nex --target web --profile release --json` succeeded with Node 22.22.3/npm 10.9.8, TypeScript 7.0.2, React/React DOM 19.3.1 and Vite 8.3.4.
- `tests/web_build.py` performed real npm/TypeScript/Vite builds outside the checkout. It verified that a server-only sentinel was absent from all assets and source maps, cache hits worked, a corrupted asset triggered a successful rebuild, `-o` copied standalone assets, and an archived revision still built after source deletion.
- Playwright 1.64.1 passed 18 production interaction cases (six each on Chromium 156.0.8078.4, Firefox 157.0 and WebKit 27.2) and three additional development-module rejection cases, one per engine. Production runs skip those direct-module cases and execute them in the separate development run. Scenarios cover Unicode input, add/toggle/delete, immutability-visible transitions, URL/back/reload navigation, keyboard submission/activation, escaped markup and mobile-width layout. macOS WebKit's native Option+Tab traversal is used under its default link-focus preference. These are headless engine checks on macOS ARM64, not real-device/browser-release certification.
- The installed 0.4.0 SDK was checked in a temporary project with `NEX_RESOURCE_DIR` explicitly pointing to installed resources. It exposed the matching web guide/prompt, ran both shared/client example tests, generated a locked application, built release browser assets with notices, and rebuilt the archived revision from cache after source deletion. Both debug (unminified) and release Vite builds were exercised.
- Desktop/mobile screenshots of the actual compiled example were inspected: `build/nex-web-preview.png` and `build/nex-web-preview-mobile.png`. The temporary screenshot server/browser were stopped afterwards.
- The installed **0.5.0 SDK/language 0.4** passed a separate temporary-project check with explicit installed resources. All six guides and every indexed document/example were present. The exact `llm/WORKFLOW.md` program first failed its intended assertion, then its revision-checked JSON patch passed native and TypeScript tests, built/ran with `144` output and exported to a runnable source project. Installed result/JSON tests agreed in all three backends and archived output still ran after source deletion. A server built entirely with installed resources ran independently, retained notices and verified authentication, user isolation, restart persistence and clean shutdown. Evidence: `build/sdk-smoke.json`; temporary projects and servers were removed/stopped. This exercises the workflow deterministically; no cross-provider LLM trial is claimed.
- `examples/fullstack/client.nex` built with locked npm packages and TypeScript checking. `tests/fullstack_browser.py` passed **12 scenarios** (four in each installed engine) against its compiled native API: real CRUD/reload/URL navigation/credential changes, isolation, cancellation/stale replies, network/schema/invalid UTF-8/size/real redirect/timeout failures and recovery, followed by persistence after native server restart. A local forwarding fixture provides a genuine same-origin redirect because WebKit cannot synthesize a 302 with route.fulfill; it confirmed that redirect targets were not fetched. All fixture/server processes stopped cleanly and temporary credentials/databases were removed. The build excluded the server sentinel and runtime-issued tokens from all assets/maps.
- After the 0.6 adapter change, real legacy web build/cache tests passed again: package/type/asset builds, excluded server data, cache hit, corrupted-asset recovery, standalone asset copy and archived-source build after source deletion. The npm lock and bundled dependency notices are unchanged.
- The legacy UI also passed its 21 browser checks again on the 0.6 adapter (18 production interactions plus three development rejection checks). Together with the connected example this gives **33 passed browser scenarios**, independent of the 56 default integration cases.
- The installed **0.6.0 SDK/language 0.4** passed the outside-checkout smoke workflow again. It includes every indexed document/example and matching guides, `std/net.nex`, the transport adapter and the shared-model full-stack sources. The installed client passed interpreter/TypeScript transition tests and generated reachable client output without the server sentinel. The repair/export/result/JSON/archive/native-server persistence checks also passed. Latest report: `build/sdk-smoke.json`. `nex doctor` confirmed toolchain 0.6.0, language 0.4 and the host ARM64 target.

## Required work still open

1. Add richer types, more reusable libraries, resource ownership/lifetimes, external interfaces and asynchronous/concurrent work. Modules, local dependency pinning, strings, immutable lists/structures and their automatic ownership are implemented; they do not complete these remaining capabilities.
2. Extend the endpoint contract where required: typed path/query parameters, streaming/resource bodies and schema compatibility. Explicit contracts now generate server dispatch, typed client helpers, wire descriptors and OpenAPI; the connected example uses these with runtime credentials and durable per-principal data. Application-specific CSS/assets/components, direct NEX source-map chains, broader session/account flows and the optional Wasm path remain open.
3. Extend the operation graph with module/type identities, cross-store reconciliation and revision-checked operation edits. Add finer frontend/function reuse, cross-unit LTO, deterministic test-result caching, stronger cross-project identity/import handling and richer graph edits. Source-module object reuse and dependency-aware invalidation are implemented.
4. Extend debugging with string chunk reads, direct large-root paging, precise optimized-operation attribution, crash/core workflows and additional host verification. Persistent source-operation IDs/candidates, demand-driven list/record/result projections, pure source-expression inspection and a stdio NEX watch adapter are implemented; editor extension packaging and browser watches remain open. Typed parameter/local inspection, bounded runtime previews and LLDB/DAP interaction are implemented on the exercised host. Native function/managed shallow allocation profiling, graph attribution and Tracy capture are implemented on the exercised host. Extend measurements to dynamic buffers, browser/GPU/system events and broader statistical comparisons.
5. Extend task contracts with dynamic coverage, dependent/generated-program steps, richer provenance and broader agent editing/search operations. Run measured cross-model authoring trials. The prompt/protocol pack is available; cross-provider success and token savings have not been measured.
6. Extend the implemented scalar Z3 subset with recursive summaries, richer data/memory/resource proofs and source-level contract/runtime enforcement. Detached snapshot-bound contracts, checked scalar arithmetic, inductive loops/rankings, explicit unproved statuses and trust boundaries are implemented; they do not prove the whole compiler/application chain.
7. Package portable SDKs, extend the verified Linux chain to broader distributions and physical x86-64 hardware, and implement/verify Windows, mobile SDK targets and native UI/GPU adapters. Finish external dependency capture and compatibility/migration procedures. macOS x86_64 cross-build artifacts are checked on ARM64; macOS Intel execution and Linux x86-64 live debugging remain unverified.

Next implementation steps include finer incremental compilation, broader profiling, optimized operation attribution/string chunks and large-root paging and the remaining target platforms, while maintaining the typed API/browser chain. Keep `describe`, specification, interpreter, both backends and tests synchronized as features are added. The full original objective remains open.

## Additional scoped 0.56 acceptance

The unchanged frozen 0.56.0/source0.16 compiler passes all20 installed macOS SDK
phases/310 commands (456.164s), with139 indexed resources and seven editor assets
matching its frozen source. Actual installed IDE acceptance is separately scoped.
See `docs/evidence/editor-integration-0.56.0-sdk.json`.

Twenty-four deterministic generated trait/constructor/closure cases pass the
reference main, native main and all24 native/TypeScript tests. Independent Python
expectations cover i64, exact finite f64, Unicode/NUL strings, empty lists,
immutable aliases, nested associated types and named method references. The
source fixture and exact seed/results are retained in
`docs/evidence/generated-traits-0.56.0.json`. An initial external harness result-key
error is recorded; no compiler change or weakened assertion was needed.
These generated cases complement the separately recorded frozen0.56 full67 and
platform matrix; they do not verify changed0.56.1 distribution helpers.

## Retained first portable-SDK failure and correction

The first0.56.1 macOS relocated workflow passes its first ten phases, then the
live string-range step fails to import its recording script. The external
acceptance command used JSON ASCII escaping for a Unicode path; LLDB interprets
that escape literally. Native debug initialization already loads the actual
UTF-8 formatter and manifest. Both acceptance-script imports now preserve raw
UTF-8 and escaped argument boundaries, matching compiler debug initialization.
The archive suite adds a Unicode/quotes/backslash path contract case. The failed
full workflow and exact stderr are retained in
`docs/evidence/sdk-distribution-0.56.1-initial-failure.json`. Full relocated and
archive-restored acceptance must be repeated; no gate or timeout is weakened.

The corrected editor/archive/host focus passes all3 groups (16 Python cases and
10 Node cases). A real LLDB import from a directory containing Unicode, quotes
and a backslash also passes without launching an inferior. The full moved SDK
workflow is being repeated; these focused checks do not replace it.

A second owned relocation run deliberately includes quotes and a literal
backslash in its parent path. Its editor phase exposes Node22 --test treating
an absolute filename as a glob; test.js exists but its path does not match.
The acceptance helper and source editor test now supply the physical directory
as cwd and the relative test.js pattern. Both actual direct and relative-test
Node probes run all ten contracts successfully from that exact path. The early
0.56.1 full regression was stopped before this correction; it is not a complete
result. The failed relocation, actual probes and interruption are retained in
`docs/evidence/sdk-distribution-0.56.1-node-path-failure.json`. Complete workflow
and full regression must be repeated with the final corrected source.

Toolchain0.60.2 corrects literal-percent Wasm output paths by linking in an owned physical staging directory and publishing the output bytes. The existing moved-SDK workflow found the failure; matching source, SDK and platform acceptance remain pending. Language0.16 is unchanged.


Toolchain0.63 is an isolated candidate extending0.62 with explicit HTTPS API
host metadata and optional exact server CORS origins. Language0.16 is unchanged.
Its native server and browser/network tests, actual mobile API checks and
complete platform/installed SDK acceptance are pending. This entry makes no
root promotion, release or full objective completion claim.

## Toolchain0.71 candidate: checked project builds and CIX hardware evidence

Isolated implementation adds `nex.project-build/1`, component ownership/import DAG checks, named build configurations, read-only plans and actual native/static-archive/server/web orchestration. Dependencies currently compile source; separately built archives are not consumed by those source edges. Full79/installed SDK/platform/root-integration gates remain pending. Earlier0.70 evidence retains its exact source and binary scopes.

On a physical CIX P1 ARM64 board, a private patched0.70 Linux development SDK launches and builds/runs ten language examples in debug/release; all20 native outputs match the interpreter and copied binaries run without NEX/LLVM/MLIR/Z3 dependencies. Checked overflow traps in both profiles. Separately, Mali OpenCL checked196608 integer outputs and a fixed-shape3x2 ONNX fixture passed three Zhouyi NPU runs with CPU EP fallback disabled, actual Zhouyi profile placement and `/dev/aipu` open. Direct accelerator calls from NEX and broad hardware support remain pending.
# Working106 private AST task scheduling

This separate development source is toolchain0.102.0/language0.18. Its reference
scheduler dispatches all ten staged task operations independently of TaskIR and
native TaskGroup. The56 retained source scenarios match expected values/errors
with actual yields/scopes/channels. The private control probe has32 source cases
and243 checks, including aggregate action limits. Focused native scheduler,
frontend, IR and reference checks pass. Current106 full108, sanitizer, installed
SDK and platform gates need their own evidence. Frozen105 full107 and strict
AST/IR sanitizer checks passed. Public task syntax/execution stays disabled;
TypeScript scheduling, region typing,019 migration, asynchronous IO/debug/profile
and delivery remain pending. Primary081 and graph history are preserved.

# Private150: on-demand logical resource authority (validation pending)

Independent AST snapshots now acquire actor/receiver resource authority only
after complete graph validation finds genuine external owners. Task/FFI in both
native and AST adapters captures logical ownership synchronously only for an
actual resource-bearing signature. Pure completion/channel values remain
independent of logical resource revocation; physical grants, cancellation,
late owned admission and ended-owner rejection remain required. Three new
explicit022 AST regressions complement the unchanged legacy request test;
FFI context probes cover skipped data-only acquisition and mandatory owned
acquisition. Public021, public022 migration and installed/platform/device
acceptance are unchanged. Matching full build/regression/sanitizers are pending.
