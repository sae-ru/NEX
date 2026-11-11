# Current implementation and remaining roadmap — development0.167.0

User instruction,2026-11-11: additional security/instrumentation/fuzz work is
deferred. Do not run or re-enable it without a new explicit instruction. Continue
language functionality and ordinary functional verification. The retained list,
actual outcomes and archive are in [deferred checks](docs/deferred-checks.ru.md).

The working language remains0.28 (task ABI7, C ABI1). The public CUDA compiler
now emits fixed values, bounded immutable lists and packed immutable bytes from
its checked graph. Byte operations include construction, index/slice/updates,
concatenation/equality and conversion from bounded static UTF-8/base64 text.
Explicit `--text-capacity` now enables runtime UTF-8 values, Unicode scalar
operations, byte codecs and per-lane Result diagnostic packets. Source Result faults now travel as managed per-dispatch outcomes to ordinary
source unwrap after resource cleanup. Ordinary fatal message transport now retains
NUL and Unicode through reference/native/task paths and frontend JSON; structured
records keep their explicit byte limits and truncation flags. CUDA str now also
formats finite f64 and supported immutable aggregates with the existing source
representation rules under explicit text capacity. These are
source/backend capabilities; physical device and immutable SDK acceptance retain
their own exact snapshots. See [current status](STATUS.md) and
[the GPU contracts](docs/gpu-codegen.md).

The user-supplied14 improvement proposals have been audited in
[development priorities](docs/development-priorities.md). Current LLM discovery/corpus,
real model-cost measurement, repeatable builds and tiered checks take priority
without dropping any original functional or delivery requirement. Current discovery/
learning work checks all registered shared capability fields and has freshly validated
0.28 labels for9 positive projects/6 counterexamples. The user-selected local
Qwen study now has60 observed trials:4/20 NEX accepted,14/20 C++ and20/20 Python,
with higher NEX token use. [Results and limits](docs/llm-cost-qwen38-27b-2026-11-11.en.md)
retain this negative result. The public nex cost command reuses the offline ledger; ten
comparison contracts,30 generated starting bundles and cross-language executable
controls are prepared. Local Qwen transport, weight pins and scoped macOS
execution isolation now have host evidence and one benign readiness response.
Restricted collection, runtime/template/budget freeze and counted fresh-context
local source review are implemented. Infrastructure pilots retain all failures;
repaired diagnostic feedback passed its real pilot and the60-slot matched study is complete.
The core test layer is implemented (the earlier11 groups took12.36s on the development Mac), with
explicit browser/platform/sdk/scale labels and the original complete registry
preserved. Shared Debug/Release presets and macOS/Linux core/separate Linuxfull
CI definitions are implemented with local evidence. The [SDK build driver](docs/sdk-build.md)
fixes a committed source snapshot and joins the maintained macOS/Linux workflows;
its full source-to-archive execution, hosted CI and final matching SDK acceptance
remain pending.
The user selected only local Qwen3.8 27B Q8_0:60 matched trials, without paid
APIs. Conclusions are scoped to that model; savings were not demonstrated.
The [bounded language entry](docs/diagnostics.md) now adds a compiled103-code
`nex explain` catalogue, a6144-byte quick guide and checked source examples,
without changing language0.28. The new diagnostic controls extend core to12 groups.
Its SDK sub-workflow is part of matching0.166 acceptance; whole-SDK qualification
and a new versioned model observation remain separate gates.

The original objective remains intact. The main unfinished implementation areas
and final delivery work are:

- [ ] General GPU/NPU compilation and backend coverage, including further Metal value/type support,
  GPU operation debugging/profiling and Apple NPU integration.
- [ ] Remaining language/toolchain extensions in the original stages below:
  advanced type-constructor inference/effect handling, graph identity-preserving
  edits and complete source/optimized-machine/core/profile attribution.
- [x] Add a generated documentation index with local-link and current-version checks.
- [x] Add a checked three-backend agreement corpus with valid/rejected/trap cases and a deterministic seed/reproducer generator.
- [x] Add `nex bench --kind runtime` with deterministic output, repeated samples, build/source identity and baseline comparison.
- [x] Add compiler-checked `nex.fix/1` edits for unknown identifiers/fields with preview, apply and rollback.
- [x] Move test targets/registrations into `cmake/Tests.cmake` and make `VERSION` the single toolchain version source.
- [x] Add checked source `std/map.nex` and `std/set.nex` immutable list-backed containers.
- [x] Add inferred effect parameters `?E` to named generic functions and `std/list` callbacks.
- [x] Infer effect parameters for function values with an expected function type.
- [x] Add explicit effect witnesses for single-parameter generic calls.
- [x] Infer `?E` effects for all `std/list` callback helpers and substitute them in cloned lambdas.
- [x] Collect and substitute effect parameters in parameter/result function types.
- [x] Add checked scalar OpenCL C source emission.
- [x] Add finite f64 OpenCL C emission and NVIDIA RTX execution.
- [x] Add trailing type-parameter defaults to nominal declarations and generic functions.
- [x] Add directory-scoped `nex fmt --check/--write`.
- [x] Implement real checked i64 arithmetic in the scalar Wasm runtime.
- [x] Add finite f64 arguments/results and E_FLOAT checks to scalar Wasm.
- [ ] Remaining browser adapter integration, application components/styles,
  asynchronous UI boundaries and browser/debug/profile qualification described
  in [the web contract](docs/web.md).
- [ ] Mobile targets and native UI: Android/iOS toolchains, packages, lifecycle,
  permissions, signing, device launch/debugging and the planned graphics adapter.
- [ ] NEX Studio, the optional task-to-change AI layer and the planned
  [C++/Python conversion pipeline](docs/project-porting-design.md).
- [x] Complete the user-selected local Qwen3.8 27B Q8_0 study:60 trials/479 requests,
  with every failed/budget/review request counted. The result is negative for NEX;
  cache split/monetary cost remain unknown and no cross-model claim is made.
- [x] Implement compiler-validated bounded language entry and diagnostic examples
  in response to observed failures, without changing the original study.
- [x] Expand source text/list/math helpers with checked Unicode/integers, stable
  ordering and explicit nonquadratic copy costs; retain locks and archived source.
- [x] Add parser-aware `nex fmt FILE` preview/check/write, retaining ordered
  comments and literal spelling, idempotence and graph rows. Toolchain 0.168
  functional coverage includes reference/native Debug/Release/strict TypeScript.
- [x] Add compiled per-command help and contextual shell completion from one
  CLI catalogue, with option-type/alias parsing and quiet success summaries.
  Toolchain 0.169 retains JSON/errors/program stdout; Bash 3.2/5.3 and zsh
  callbacks have local execution evidence. Fish/PowerShell execution is pending.
- [ ] Extend formatting to editor requests, directory selection and width-based
  wrapping; these are not part of the current single-file command.
- [x] Implement sequential immutable list construction (count/map/filter/state),
  inferred callback effects and suspension through the existing task machinery.
  Toolchain 0.170 source list generation/map/filter/reverse and stable merge
  outputs now build linearly, without changing existing valid 0.28 identities.
- [x] Implement sequential linear text construction through two-, three- and
  four-argument forms of the reserved `str` builtin: inferred callback effects,
  source errors, task suspension, one private buffer and one final join.
  Toolchain 0.171 keeps language 0.28 and existing valid identities.
- [x] Implement sequential linear byte construction through two-, three- and
  four-argument `bytes(...)` forms: inferred callback effects, typed source
  errors, task suspension, a private `list<i64>` and one validated conversion.
  Toolchain 0.172 keeps language 0.28, identities and the public C ABI.
- [ ] Wider containers, named source-library effect parameters and GPU/Wasm
  constructor lowering remain required work. Later
  versioned model studies preserve the original negative result and use only
  the selected local model.
- [ ] At the final functional milestone, qualify one matching compiler/SDK across
  the supported platform/device matrix, then publish the latest main/release
  and remove obsolete branches/build artifacts with retained useful evidence.

Existing working CPU/server/web features are not pending solely because an old
historical checkbox remains open. The detailed stages below preserve original
scope and historical evidence; use the current descriptor/specification to tell
implemented behavior from unimplemented work. Full regression/stand/SDK cohorts
remain deferred during implementation-first development. Finished functional
blocks receive a build and short affected-behavior checks, not a full suite after
individual edits.

# General GPU code generation — checked Metal and CUDA backends

The public `nex emit --kind cuda` command now shares the implementation with the
[checked-AST CUDA developer harness](experiments/cuda-codegen/README.md). It emits
ordinary checked0.28 functions with explicit64-bit arithmetic, fixed records,
enums/Results and bounded static device text
and rows/columns ABIs, including scalar `match` with ordered guards and one
subject evaluation. Its source controls passed 28 fixtures, 56 layouts and 256
lane outcomes under host UBSan, positive reference/native/TypeScript agreement
and 9 rejected programs. All56 original sources, metadata, lane data and budgets
remain byte-identical after adding finite `f64`. The new floating corpus passed
19 programs /38 layouts /586 lane outcomes in four host FP modes,264 assertions
across actual NEX reference/native/TypeScript and152 verified LLVM IR/PTX variants.
It includes explicit nearest/ties-even operations, normalized zero, subnormals,
exact binary remainder, comparisons, `as_f64`, number generics and guarded matches.
Typed owned f64 transport and original E_FLOAT forwarding are implemented;
reference/native Debug/Release codec and fatal controls passed. Physical f64
execution, NVRTC/ptxas qualification and current owned-module acceptance remain
pending. An earlier32-kernel integer/bool/unit corpus passed actual NVRTC12.1
and RTX3090 execution (186 lanes); its Python sanitizer failed to attach before
any CUDA work, so memcheck remains pending. The backend is connected to the
public compiler; its owned preparation tools
now default to that same compiler and are installed with the SDK. Matching
public source-command checks and new fixed-value CPU/reference/native/TypeScript
agreement passed; current-provider/immutable-SDK hardware acceptance remains separate from the
earlier fixed Windows CUDA provider. A separate
[owned generated CUDA provider](experiments/owned-cuda-codegen/README.md) now has
checked preparation and a C FFI implementation for sessions/buffers/cursors.
Its scalar/parent acceptance runner now has 15 compiler-checked NEX programs
and nineteen false-receipt rejection controls, including per-buffer temporal
checks. A real three-context restoration/rollback probe is built; its local
no-driver control passed, with physical NVIDIA execution still pending.
An explicit bounded device-clock gate and the original cancel/deadline cases
are implemented for later physical execution. Gate configuration is checked
locally; synthetic acknowledgements do not qualify GPU interruption handling.
Offline Clang/LLVM22.1.8 compilation now passed232 IR/PTX variants covering the
28-program/56-layout corpus, separate gate and actual combined preparation at
O0/O2 for sm_52/PTX4.2 and sm_86/PTX7.1. IR and machine instructions are verified;
this adds compiler evidence without qualifying NVRTC or physical execution.
The real module also passed local task capture, source-deleted replay and
relocated standalone packaging in explicit macOS unavailable-driver mode:
160 typed results across five processes, zero CUDA resources and four actual
sandbox read-denial controls. Native NVIDIA delivery remains unqualified.
The generated-provider memcheck runner now retains exact native binaries and
authority/source/PTX pins in a version2 hardware report and reuses all15 cases
plus the physical context probe without changing task budgets. Local controls
checked15 NEX programs,17 synthetic log and7 argument contracts, changed-input
rejection and real POSIX process-tree timeout cleanup. No Compute Sanitizer or
NVIDIA execution is inferred from these local controls.
Actual NVRTC/GPU/memcheck, generated-provider lifetime/cancellation acceptance
and coherent public compiler/SDK delivery remain
pending; no CUDA support is inferred from CPU execution of emitted code.

The separate `experiments/metal-codegen` backend now lowers actual checked NEX
scalar functions to Metal. Twenty reference/native/GPU comparisons and five
physical boundary dispatches cover i64 arithmetic, pure control flow, calls and
source contracts. It is outside the frozen0.163 SDK; see its exact development
evidence and limits in STATUS.md.

- [x] Generate reachable scalar code from the selected compiler's typed graph.
- [x] Preserve checked i64 operations, evaluation order and lazy control flow.
- [x] Compare real generated GPU execution with reference/native NEX and exact oracles.
- [x] Execute generated kernels through persistent owned NEX task/device resources; 38 pairs/122 physical GPU events.
- [x] Forward original fatal-trap codes through the0.164 append-only host API; nine core groups and21 native/reference Metal pairs/36 GPU events passed. `try_apply` retains Results; ordinary unwrap keeps E_RESULT.
- [ ] Qualify that new path through matching full current regression, immutable SDK and remaining platform gates.
- [x] Match malformed-reply/log-stress checks to the generated provider's distinct protocol. The corrected provider passed34 frame/progress/error-packet/UTF-8/control pairs and all preceding corpora:74 native/reference pairs with130 physical GPU kernels. Matching installed delivery and unknown vendor recovery remain separate requirements.
- [x] Add public checked-AST scalar emission, CLI/discovery, source diagnostics, function maps and a versioned JSON contract in development0.165; matching acceptance remains pending.
- [x] Validate the public C++ emitter against reference/native Debug/Release/TypeScript and physical Metal:20 cases, both layouts,48 GPU dispatches and nine host rejections.
- [ ] Complete its full current regression and matching installed SDK/platform qualification.
- [x] Connect public emission to the checkout owned-task provider, retaining exact compiler/emission identities, source maps and physical settlement;96 native/reference pairs and230 physical GPU events passed.
- [x] Install public-emission preparation/verification tools and expose their paths through `gpu_codegen.owned_provider`.
- [ ] Qualify that installed provider through the matching immutable SDK and physical hardware.
- [ ] Implement GPU operation debugging and profiling.
- [ ] Extend supported types/control and GPU/NPU backends and qualify immutable SDK delivery.

All remaining original language/platform/device/mobile/UI/Studio/conversion,
measurement and publication/cleanup requirements remain part of the objective.

# Owned Metal SDK tools — development0.163.0

Install the provider/precondition tools in the SDK and expose their actual
experimental scope in the compiler descriptor. Source-only preparation must
not require Apple's SDK or a GPU; all27 fixture programs and the missing-effect
rejection are checked with the actual selected compiler. Complete SDK acceptance
requires the installed tools, exact source/compiler pins and every named check.
Fresh source/full SDK, relocation and physical hardware delivery gates remain
required. Language0.28, taskABI7 and graph migration rules are unchanged.

# Owned Metal experiment — development0.162.2

Connect the existing `std/device` resource API to a pinned persistent Metal
worker, retaining exact U8 Add/Affine, checked overflow, explicit placement,
parent retention and physical completion before cancelled-call cleanup.
[Actual hardware evidence](docs/evidence/macos-owned-metal-0.162.2-2026-11-09.json)
records native/reference execution on Apple M5 Max. The provider is currently
built separately from the checkout. Matching installed SDK delivery, general
Metal kernels/code generation, other operations/dtypes and Apple NPU remain
open, along with every other unfinished original roadmap item below.

# Selected ELF runtime search — development0.162.1

Share SONAME-aware runtime-directory planning between standalone and component
links. Preserve explicitly selected runtime images; reject missing aliases and
conflicting search requirements. Static archives add no runtime directory.
Language0.28/ABI7 and all original unfinished requirements remain unchanged.
Mac full301 and Linux native/package checks plus exact union303 are recorded in
the [development evidence](docs/evidence/native-runtime-search-0.162.1-2026-11-08.json).
Complete matching installed/platform acceptance remains a separate gate.
Existing0.162.0 archives and stand runs keep
their immutable source identities; this correction does not relabel them.

# Windows HTTP/HTTPS/HTTP2 candidate0.162

Port native dependency preparation, socket ownership and source/package/stream
checks without changing language0.28 or task ABI7. Selected HTTP87 and Mac HTTP90
passed. Positive Windows IPv6, current coherent compiler/full regression and
complete installed/moved SDK acceptance remain required. Every original unfinished
roadmap requirement remains open.

# Windows DNS development0.162

Add native Windows static c-ares preparation and a Winsock/select DNS provider,
retaining exact operator resolver/authority policy, UDP/TCP fallback, task control,
bounded answers, capacity and physical channel retirement. Source language0.28
and task ABI7 remain unchanged. The Windows static dependency,45 selected
source comparisons and source-deleted package passed; Mac DNS51 and HTTP90 plus
15 HTTP/1 stream cases passed. Matching full/current compiler, positive Windows
IPv6, sanitizer and complete SDK acceptance are still required.
Every unfinished original roadmap item remains open.

# Windows TCP development0.161

Port the private TCP kernel and pinned source provider to real Winsock2 while
retaining source language0.28/task ABI7, endpoint authority, cancellation,
queue-time deadlines, quotas and physical socket retirement. The default full
kernel test retains IPv4/IPv6; selected cases remain explicitly partial.
Windows selected kernel/source IPv4 and source-deleted package checks passed;
intentional IPv6 denial is handled in reference/Debug/Release with balanced sockets.
Successful IPv6, complete installed SDK delivery, HTTP/DNS provider dependencies
and every unfinished original requirement remain open.
The accepted local Mac0.160 cohort and published0.159 SDK retain exact identities.

# Integrated source development0.160

Combine native entry ABI discovery, debugger fixes and quality runners, then
run fresh full regression and build a new immutable SDK with the updated helpers.
Keep the original failed Mac/full-SDK gate and the passed parent Linux298 scope.
Finite Q1–Q5 source acceptance does not replace matching installed delivery,
quiet-host performance, multi-model token measurement or other original work.

# Quality-runner source follow-up for language0.28

Port the complete Q1–Q5 chain to actual compiler-selected0.28, retaining0.21
corpora, original expectations and fresh history. Source runners now select the
version explicitly, propagate it to Q5 and declare required task source-error
effects. Short checked-core Mac/Linux agreement and the finite Q1–Q5 chain passed,
including100x10000 with9900/0/1 LLVM calls, source-deleted replay and three physical
fence modes. [Source evidence](docs/evidence/quality-language-0.28-source.json)
records the scope and intentional leak/race controls. Matching full regression,
updated helpers' installed delivery and quiet-host performance/LLM measurement
remain required; generated provider LLVM IR is not sanitizer-instrumented.
Every original unfinished language/platform/device/UI/Studio/conversion item remains.

# Linux debugger and UTF-8 follow-up — source development 0.160

Pin the Linux debugger independently of the LLVM/MLIR22.1.8 compiler. LLDB23
passed four exact preserved binaries. Explicit UTF-8 metadata decoding and
actual C-locale/Unicode-path regressions passed on Mac; retained Linux0.159
compiler checks passed three debugger groups and a separate full watch group.
The first combined run's intermittent `lost connection` remains unresolved and
preserved in the [scoped record](docs/evidence/linux-debugger-0.160.0.json).
Fresh full/current Linux and portable SDK0.160 qualification are still required.
No remaining original PLAN item is removed by this checkpoint.

# Native entry ABI — source development 0.160

Selected native library entries now describe their actual verified LLVM ABI in
build JSON: hidden source-error output, physical types/order/attributes,
target/layout, matching runtime and task-executor boundaries. Four focused
cases passed, including 2000 native host calls and owned cleanup checks across
Debug/Release, repaired metadata, archived sources and a real task-provider
project. Full/current installed acceptance remains a separate gate. No source
syntax, graph migration or language 0.28 change is introduced.

The exact public 0.159 SDK separately passed 1400 native iOS Simulator calls and
cleanup checks. Its scoped evidence is in docs/evidence/0.159.0-ios-native;
UIKit, physical iPhones and complete mobile/UI delivery remain original open work.
Every other unfinished item below, including general devices, Studio, conversion
and measured LLM token savings, remains in scope.

# Platform cohort preparation after SDK 0.159

Windows CPU/storage/TypeScript and CUDA preparation now select supported027/028
from matching doctor/index identities. Feature envelopes and ABI7 are checked;
resume preserves physical source/manifests and existing graphs. Linux smoke also
accepts028. CUDA --source-only checks seven real FFI signatures without claiming
Windows binaries or hardware execution. Four focused cases passed on actual
Python3.10/3.14; full regression, installed helper and current Linux/Windows gates
remain separate. The public159 immutable SDK below is unchanged. General device,
mobile/UI/Studio/converter/LLM measurement and every unfinished original item remain.

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

Project source templates with parametric pure predicates, explicit phantom and
constructor arguments, ordinary trait bounds and all-instantiation coverage.
Derived instance edits remain rejected; candidate/session4 records parameter
kinds and bounds while earlier receipt families retain their shapes. All-target
build, targeted scalar15/loop15/value14 and final generic9 cases passed, including
native/reference/TypeScript agreement, future instantiations, owned files and
typed source errors. Full288 regression and matching installed SDK remain pending.
The0.155 Python-floor SDK qualification continues on frozen670e1fd separately;
all original platform, language, GPU/NPU, UI and tooling requirements remain.

# SDL Metal/Retina example correction — 0.155.0 compiler

Map the board to physical presentation pixels, retain readback surfaces through
RAII, and validate bounded smoke sizes. Eight native/relocated Metal scenes,
independent bitmap counts, ten refusals and source/SDK-denied package checks
passed. The exact source overlay and scope are recorded in
`docs/evidence/sdl-metal-retina-0.155.0.json`. Parent ce72e9f full/SDK checks remain
separate; current Windows/Linux graphics, general GPU/NPU/mobile/UI and every
unfinished original requirement below remain open.

# Runtime value contract development — 0.155.0 / language 0.27

Broaden executable contracts to concrete effectful/value signatures and ordinary
pure source-expression predicates. Preserve exact lexical aliases and inner/outer
callable effects, normal return/finally/Result boundaries, original history and
owned cleanup. New receipt/session3 records original signature/effects; scalar1
and loop2 remain compatible. Loop annotations retain scalar observations.
All-target builds and targeted development checks passed after retained fixture
repairs. Full287 regression, installed SDK,
current Windows delivery and every unfinished item below remain required.
The separate0.154 source remains frozen for its ongoing full/SDK checks.

# Windows/runtime integration — 0.154.0 / language 0.27

Combine native Windows acceptance bfe4486 with Mac runtime loop contracts7272ebc.
The merge retains language0.27/taskABI7 and both parents' pinned evidence.
Current work: fresh integrated build, complete Mac regression, relocated/restored
SDK qualification, then current Windows acceptance. Parent passes do not accept
this combined compiler. General GPU compilation, complete Windows SDK, remaining
language/platform/tooling capabilities below are still unfinished.

# Runtime loop contract development — 0.153.0 / language 0.27

Selected while rules now project invariant entry/back-edge checks, nonnegative
iteration rankings and strict descent into ordinary checked source. Early
returns, source errors, finally and lexical bindings retain their boundaries;
no closure or language/ABI change is introduced. Pre/post-only receipts retain1;
loop coverage uses2. A preexisting native pure typed-catch/finally CFG emission
gap was reproduced in0.152.1 and is corrected with the existing unmatched type
guard. Build and nine targeted groups have passed (separate retained attempts).
Full regression, matching SDK and platform acceptance remain pending.
Effectful/aggregate roots, source syntax and all other original PLAN work remain.

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

Текущая разработка0.151 открывает обычный CLI языка0.27: типизированные ошибки,
упорядоченные catch/finally, ABI7, проверенные карты2, снимки и явная миграция026.
Полный прогон, установленный SDK, платформенная приёмка и незавершённые пункты
исходного плана ещё обязательны; прежний основной проект0.81 не обновляется.

## Историческая подготовка 0.151 до включения публичного CLI

Кандидат 0.151 готовил проверенное восстановление смешанных026/027 графов
и чистые скалярные027 Wasm-модули. Исходная история/ID и ограниченный Wasm ABI
сохраняются; обычный CLI остаётся026. Полная приёмка151, SDK/платформы,
публичный027 и все незавершённые пункты исходного плана остаются обязательными.

# Development0.150: checked027 browser delivery

Explicit C++027 browser UI/Worker builds now carry checked revision/maps, keep
private development maps separate, and retain realm/wire/error boundaries.
Production builds, actual module Workers in three engines, reference/native/Node
agreement, source-absent relocated static packages and genuine026 asset identity
are separate checks. Full integrated/SDK/platform/public027/snapshot gates and
every remaining original plan item still require completion.

# Development0.149: typed native debugger views

Explicit C++027 LLDB/NEX-DAP views now cover typed/legacy handler bindings,
guard/catch suspension, source/image identity and source-absent inspection.
Synchronous DWARF remains separately tested. Diagnostic IDs bind the actual
watch language; default callers retain their old metadata. Full integrated
regression, installed SDK/platform delivery, public027 CLI/Web/Worker/snapshot
gates and every remaining original plan item still require completion.

# Candidate027 native provider development0.148.0

Explicit C++027 selection now develops source/static/shared/mixed native builds
with taskABI7 and versioned provider/application/linkage records. Owned typed
errors preserve their value/key/site across images, suspension and finalizers.
The normal process entry accepts7; the development emitter remains2702 and
retained public/private task families keep their separate identities.
Read [the provider contract](docs/typed-error-providers.md).

The ordinary CLI/default remains026. Public027 selection, graph-snapshot
delivery, bounded typed debugger views, full current regression and matching
SDK/platform acceptance remain required. This does not complete the full PLAN.

# Typed027 archive/migration development0.147.0

The checked C++ API now archives027 with program/15 and performs an explicit
same-store026-to027 migration while retaining old canonical revisions, schema,
IDs and namespace. Candidate, source and expected-HEAD guards are rechecked
before publication, with HEAD/namespace checked again inside the transaction.
Physical source/manifest export is separate; no ordinary CLI upgrade is enabled.

Full147 regression and matching native project/library/provider contracts,
public027 selection, bounded debugger/profile integration, graph snapshots,
SDK/platform/accelerator acceptance and all original plan requirements below
remain required. The previous146 compiler passed its276-group full regression;
that receipt does not certify this new compiler or an installed SDK.

# Typed027 authority transfer development0.146.0

Exceptional provenance and runtime guards now carry callables, task capabilities
and native/reference file/resource owners through typed errors. Native implicit
scope close prepares the selected payload before retirement, outside scheduler
locks. TypeScript uses bounded compiler-keyed contracts and private capability
brands; browser file/FFI/server authority remains rejected. New native code uses
private2702 while retaining2701 and public ABI6 identities.

Development conformance includes known rejected escapes, dynamic escapes through
legitimate channel receives, AST/TaskIR/Node/native agreement and physical cleanup.
Full current regression,027 source library/provider contracts and delivery,
genuine026-to027 graph migration/public selection, bounded debugger/profiler
integration, SDK/platform acceptance and every original plan item below remain
required. This is progress toward that complete scope.

# Typed027 resumable task development0.145.0

Ordered typed/legacy clauses and owned data now traverse AST/TaskIR continuations,
native frames and TypeScript generators. Native candidate cohort0x2701 stays
separate from public ABI6; public entry and mixed calls reject mismatched cohorts.
Source-edge lifetime traversal retains outer assignments and finally paths.
Actual multi-engine/worker agreement is tested by tests/typed_source_tasks.py.
Authority-bearing payload provenance/transfer, project/library/provider delivery,
explicit026-to027 graph migration, SDK/platform gates and the full original
language/toolchain/accelerator plan below remain required. This is development,
not public027 publication or overall completion.

# Typed027 synchronous native development0.144.0

Reference, TypeScript and sequential native emitters now implement ordered typed
handlers and ordinary owned payloads. Native O0/O2 agreement, source-site fidelity,
cleanup across declines/rethrow/finally and packet sanitizer probes cover this
scope. Public/default source stays026. Full native project/library/provider,
task and authority/provenance integration, versioned protocols, genuine027 graph
migration, SDK/platform delivery and every original NEX plan requirement remain
open; this is not completed publication of027 or the whole toolchain.

# Typed027 synchronous TypeScript development0.143.0

Ordered typed/legacy handlers, exact matching, owned immutable data and source
sites now agree in reference and generated TypeScript. Payload data stays outside
public error metadata. Actual Node, strict TypeScript and retained025 tests cover
the new runtime; public/default source remains026. Native, TaskIR/AST/TS/native
suspension, authority/provenance, versioned providers and genuine027 migration,
SDK/platform/browser delivery and the full original project plan remain required.

# Typed027 frontend/reference development0.142.0

Version-selected parsing/checking and synchronous reference execution now cover
typed raises and ordered handlers, exact keys, filters/replacement/rethrow,
known versus coarse throw effects, immutable bindings and retained026 identities.
Public/default source stays026. Complete native/TypeScript/task lowering, typed
payload authority/provenance, explicit027 graph migration and delivery gates
remain required before publication. All original language/toolchain/platform/
accelerator requirements below remain active.

# Native typed-error packet roundtrip0.141.0

Managed native packets now retain typed values across exception/handle conversion
and the real unhandled boundary. Kind-checked accessors accompany exact type keys;
legacy packet layout stays unchanged. No typed source syntax or authority transfer
is enabled. Ordered handlers, source-edge provenance, all engine integration,
explicit027 migration and the full language/toolchain/platform plan remain open.

# Owned typed-error foundation0.140.0

Implemented internal retained payloads and complete concrete type identities;
real source typed throw/catch, handler provenance/authority transfers, ordered
clauses, matching engine/protocol integration and explicit027 migration remain
open. The026 source language is unchanged. The concrete contract and gates are
in docs/typed-exceptions-design.md. This remains progress toward the original
full language/toolchain goal, not a reduced definition of completion.

# Resumable finally implementation (0.139.0 development)

TaskIR/native and independent AST control now preserve pending outcomes across
suspension; lifetime analysis visits finalizers before outgoing transfers.
TypeScript distinguishes normal/source-error completion from scheduler close.
The source tests compare actual engines, traps/cancellation and physical resource
cleanup. Full compiler, installed SDK and platform acceptance remain gates;
typed payloads, general effects and the original platform/accelerator/tooling
requirements below remain open. This is progress, not completion of NEX.

# Finally lexical DWARF scope / toolchain0.138.2

Return-path finalizers use the lexical debug scope recorded outside their
protected block. A real LLDB regression checks outer42 rather than expired
inner0. Synchronous ownership/semantics remain; task finally and full delivery
are pending, alongside all remaining original plan requirements.

# Synchronous native finally / toolchain0.138.1

Native finally now lowers ordinary completion, pending return/Result return and
source-error propagation/replacement with distinct protected/finalizer ownership
frames. TaskIR/AST/lifetime and scheduler finalization, typed payloads and all
matching delivery gates remain pending alongside the full original plan.

# Finally foundation / toolchain0.138.0

Synchronous checker/reference/TypeScript finally is implemented in its isolated
worktree. Native/task finalization, engine agreement, complete acceptance and
the full remaining plan stay open. Compiler/SDK39 checks for0.137.1 keep their
separate frozen tree and original compiler.

# Active language0.26 handler work

Catch-filter lowering and checked025 migration are implemented in the new
worktree; first focused execution checks pass. Finish finally, complete all
matching regression/SDK/platform gates, then continue typed payloads and every
remaining language/platform/product requirement below. Nothing here marks the
full objective complete or reinterprets older receipts.

# Active public025 integration

Ordinary frontend, retained024 migration, native/TypeScript source-error transport
and standalone task ABI6 are implemented in the mutable234 candidate. Mac
cohort `c591f2d` passes all263 CTest groups and the complete installed SDK's39
phases, including source/static/shared providers, capture/replay, debugger,
profiling and browser builds. These receipts describe that exact Mac cohort;
later Linux harness/prompt corrections have their own focused checks.
The0.136.1 Windows adapter adds ordinary GNU/UCRT64 CPU task executables;
both target/profile cross-builds and x64 Wine task/error paths pass focused
checks. Matching full0.136.1 regression and actual Windows OS execution remain
separate gates. Windows task files/FFI/providers/debug/profile stay pending.
Next: complete Linux full/live/source-free acceptance and remaining platform
delivery. Typed errors, finally/filter handlers and the remaining language,
platform and product plan below are still requirements of the full goal.

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

TCP198 progress: bounded server TCP is available through the existing typed
task/FFI bridge and an operator-prepared pinned std/tcp provider. It introduces
no new source syntax, effect or language migration. DNS/TLS/HTTP protocols,
persistent streaming, reactor multiplexing, async DB and dedicated network
profile/debug integration remain pending. Current installed acceptance now
requires38 phases; matching full/platform/distribution proof is still required.
This does not complete the network roadmap or the full original objective.

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

# Development0.133.11: private in-flight IO and verified marker records

The maintained physical IO suite has56 native/AST pairs on6 compiled images,
11 host observation/one-shot tests and10 marker-provenance boundaries. It checks
actual source task_cancel while IO is held, not only host-request cancellation.
Actual TSAN/DAP, full regression, SDK and platform acceptance remain separate
until their receipts pass. Genuine mixed023 File/FFI histories, explicit public024
migration/CLI, async network/DB and every other original requirement remain open.

# Development0.133.10: genuine023 histories and pure helpers

The private024 history suite covers five actual SDK1335 archives and all15
revisions, including pure generic callables and File identity helpers. A native
requirement-classification bug exposed by this suite is fixed. This does not
complete controlled in-flight IO, mixed FFI histories, public024 migration/CLI,
matching full/SAN/SDK/platform acceptance or the remaining full project plan.

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

The native host IO bridge now supports revocable, snapshotted, atomic whole-file
writes. Public source task writes, independent-reference/native adapters,
provider integration, migration, streams/network/DB and matching SDK/platform
delivery remain pending. This precursor does not replace any original language,
compute/NPU/UI/mobile/Studio or quality requirement.

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

# Current development0.132.1: reference physical completion handoff

- [x] Reproduce false reference deadlock at a controlled physical finalizer handoff.
- [x] Keep unconsumed retirements as progress until coordinator publication; exclude terminal jobs/scopes.
- [x] Check root/scope/future/cancel handoffs,384 async stress cases and real channel deadlock.
- [ ] Complete matching frozen regression, ASAN/UBSAN/TSAN, actual GPU and installed SDK.

All owned GPU/NPU, runtime/platform/Studio and original full requirements remain.

# Current development0.132: owned devices

- [x] Add ordinary checked Session/Buffer/Tensor library and persistent pinned OpenCL worker.
- [x] Test real GPU ownership/hidden parents and cancellation/deadline after physical enqueue.
- [ ] Complete matching frozen regression, sanitizers and installed SDK acceptance.
- [ ] Verify matching Linux/stand delivery, recovery/reset, owned NPU and remaining operations.

The original full project scope below remains active.

# Current152: publish source task/FFI and owned transfer in language022

- [x] Enable ordinary022 parse/load and retain old semantic parsers/IDs.
- [x] Extend deliberate provider/debug/version formats without widening ABI3.
- [ ] Verify real public CLI021->022 migration, actual C11/C++20 calls/owners,
  native/reference agreement, client isolation and rejected boundaries.
- [ ] Complete matching full regression, installed SDK and platform delivery.
- [ ] Continue all original IO/device/GPU/NPU/UI/mobile/Studio/converter and
  quality/multi-LLM requirements; this release is not the full objective.

# Current141: logical resources in the private native scheduler

- [x] Separate logical ancestry from bounded physical grants; retain256 native scope depth.
- [x] Track complete physical cleanup fences, including invisible failed publication; integrate private native scope/root retirement and explicit promotion.
- [ ] Complete exact compiler/installed SDK/platform delivery for this stage.
- [ ] Connect the independent reference scheduler, source value cleanup/transport, request-parent transfer and trusted FFI completion; preserve all original device/platform/quality requirements.

# Current140: physical resource executor integration

- [x] Implement a bounded owning-thread host executor, pre-reserved cleanup and complete physical owner retirement.
- [ ] Complete cancellation/physical fence/module unload/quota tests and strict sanitizers, matching compiler/SDK/platform delivery.
- [ ] Connect logical source-task ownership, trusted FFI completion and actual model/device resources; retain all remaining original requirements.

Development0.123/language021 now implements opaque source resource declarations,
checked native/reference operations, graph/editor context and explicit migration.
Focused source, genuine020-history and installed-resource-phase acceptance are
recorded separately; full current delivery is still required. Logical task/device
ownership, actual resource debugging and the remaining full plan below stay open.

# Current private135 resource integration

- [x] Verify the host owned-value/byte-budget/module lifetime foundation and existing file/C compatibility under sanitizers.
- [ ] Connect opaque source declarations, graph identities, typed FFI construction and genuine020 migration.
- [ ] Implement device executor cleanup/fences and task/ffi completion ownership, then verify actual devices and complete delivery gates.

# Current0.122 model SDK integration

- [x] Install `std/model.nex` and provider preparation with matching describe/guide/prompt.
- [x] Verify public import, finite F32, response/precision/fallback and rejected boundaries across native/reference/TypeScript.
- [ ] Verify source-free installed SDK model phase, full matching regression and platform delivery.
- [ ] Continue owned model/device resources, task/async bridge and all remaining original PLAN requirements.

# Current development: toolchain0.121 / language0.20

- [x] Implement ordinary-source checked Tensor/Request/Response/Device/Context and CPU operations.
- [x] Check native/TypeScript/reference numerical semantics, overflow/limits, provider selection/response/fallback and realm/wire boundaries.
- [x] Build LLVM/MLIR22.1 compiler and verify compute/discovery/SDK-report contract focused groups.
- [x] Verify local0.121 via composite153 (148 original +4 TypeScript and actualWasm repeats), installedSDK32/584 and actual three-engine18 browser cases; original failures retained.
- [x] Verify the common source Context against actual RK3588 GPU/NPU with pinned leafworkers using compatible0.120/language0.20:49GPU calls,21NPU calls. This is not full0.121 platform acceptance.
- [x] Extend experimental OpenCL U8 Add/Affine to scales0..255,262144 elements and explicit overflow; verify real device, malformed frames, cancellation/reap and CPU oracle.
- [x] Generate common-GPU projects with an explicitly selected installed OpenCL loader; matching CIX and RK3588 numerical/native/profile/replay/standalone and worker boundary tests passed.
- [x] Verify an experimental named static-tensor ONNX model contract, finite F32 bytes, explicit MatchCPU/Vendor precision and pinned CPU/Zhouyi child dispatch on CIX; retain unsupported MatMul placement, explicit fallback and17 process cases. This is outside installed0.121 and is not arbitrary-model NPU support.
- [ ] Add remaining operations/providers, owned buffers/resources, async/task bridge and general kernels/models.

The original complete PLAN scope below remains active. Primary081 is preserved.

# План разработки NEX

Обновлён: 23 октября 2026 года.

Статус: выполняется. Фактические возможности и результаты проверок фиксируются в `STATUS.md`; пункты плана не означают автоматически реализованную поддержку. Объём проекта — сам язык и полная цепочка разработки, без разработки крупных прикладных продуктов.

## Текущий шаг: toolchain0.120 / язык0.20

- [x] Соединить task-only worker_compute с отдельным scheduler в Web Worker,
  сохранив чистые main-thread UI/command entries и wire-only boundary.
- [x] Проверить реальные каналы/spawn/wait, ошибки, отмену/timeout, отзывчивость
  UI и отсутствие server-кода в Chromium/Firefox/WebKit, затем matching SDK.
- [x] Проверить новый SDK на Astra x86-64 и CIX ARM64; GPU/NPU fixed adapters
  имеют отдельную область и не означают завершение общего accelerator API.
- [ ] Продолжить общий GPU/NPU API и остальные платформенные этапы после этого блока.

Дополнительный RK3588S: CPU/web/packaging и30 GPU-вызовов прошли;
NPU bytes-FFI после исправления DMA прошёл30 вызовов/6400 значений,
min/max формы и fullint8 — отдельные6 вызовов/16448 значений. Все результаты
и отличия documentation/experimental additions от frozen0.120 приведены в
[текущей приёмке](docs/stand-acceptance-0.120.md). Общая цель остаётся активной.

## Сохранённый126–127: toolchain0.119 / язык0.20

- [ ] Связать checked component source union и original runtime registries с
  LLDB/NEX-DAP для static/fixed-shared provider task frames.
- [ ] Проверить реальные locals/watch42, next/in/out через yield/call/return,
  stale/image/source rejection и source-deleted delivery до public enablement.
- [ ] Пройти точные regression/SDK/platform gates нового snapshot. ExecutionABI3,
  исходный язык020 и миграция не меняются; runtime unload/profile+debug pending.

## Сохранённый125: toolchain0.118 / язык0.20

- [x] Связать checked component registries с единым task collector через
  static/shared provider boundaries, сохранив once-per-source-call semantics.
- [x] Проверить source-count oracle, zero-call provider-only generics, actual
  component/image attribution, limits/grants и cleanup без подмены RAM/CPU metrics.
- [x] Проверить строгие raw3/catalog/image negatives, self-consistent wrong-owner
  ledgers, canonical cache-parent aliases, physical fence и отдельные sanitizers.
- [x] Проверить matching actual10 и reviewed capture/replay/raw package provenance;
  точное тело SDK30 отдельно прошло15 командами, с каждым actual CWD/build key.
- [x] Сохранить явный Mac composite148 (147 original groups + corrected boundary55/39),
  scoped Linux composite11 (10 + corrected boundary) и установленный SDK30/557 команд.
  Original failures сохранены; pristine full148/fullLinux/kernel isolation не заявлены.
  См. docs/evidence/toolchain-0.118.0-task-provider-profiling.json.
  Язык020, explicit migration и execution ABI3 не меняются. Profile test/build-test,
  provider logical debugging, runtime unload, Tracy/HTTP/foreign остаются pending.

## Сохранённый124d: toolchain0.117.2 / язык0.20

- [x] Связать конкретные task-экспорты через OS startup-loaded shared images,
  смешанные static/shared frontiers и один общий runtime/root executor.
- [x] Проверить symbols/loader, per-application owners, immutable/result/Unicode,
  grant/limits, независимые roots и source-deleted retained replay/package/copy.
- [x] Исправить реальный124b cache-image SIGSEGV atomic publication и124c literal
  parent-path regressions; сохранить все исходные failures и loaded-image test.
- [x] Пройти новый pristine full144, установленный SDK29/542 команды и семь
  scoped LinuxARM64 groups; см. docs/evidence/toolchain-0.117.2-task-shared-providers.json.
  Это отдельный development checkpoint; full Linux/installed Linux SDK, kernel
  source isolation и root promotion не заявлены. Язык020/execution ABI3 прежние.

## Сохранённый123: toolchain0.116 / язык0.20

- [x] Связать конкретные task-экспорты через настоящие статические архивы,
  сохранив checked source, единственного machine-owner и один root executor.
- [x] Проверить provider chains, immutable aggregate/result/Unicode semantics,
  root file grant/limits, pins/cache, captured replay и standalone package.
- [x] Проверить fail-closed границы authority/callable и неподдержанные режимы;
  сохранить существующие синхронные File/callback архивы.
- [x] После действительного native proof включить точную candidate discovery;
  пройдены17 permanent cases и отдельное тело SDK-фазы19 командами.
- [x] Сохранить честный composite141:140 исходных passed groups плюс исправленный
  integration21 на том же frozen compiler; исходная ошибка не удалена.
  Установленный SDK28/523 и отдельные Linux4/17 прошли; см.
  docs/evidence/toolchain-0.116.0-task-providers.json.
  Shared providers,
  task profile/debug через provider и unload не входят в этот шаг.

## Сохранённый122: toolchain0.115 / язык0.20

- [x] Добавить отдельный bounded debug catalog ABI1 без удержания значений программы;
  private runtime109 проверок/614 остановок прошёл строгие sanitizers.
- [x] Сохранить лексические binding IDs и реальные source safe points при TaskIR lowering;
  9 случаев/183 проверки подтверждают неизменность инструкций исполнения.
- [x] Подключить логические задачи, стеки, locals и шаги в LLDB/nex-dap;
  10 настоящих LLDB/DAP сценариев и39 native-команд пройдены.
- [x] Проверить archived-source inspection, явные лимиты и cleanup;
  новая фаза установленного SDK отдельно пройдена с настоящим DAP.
- [x] Сохранить composite139:138 исходных passes и один исправленный9-case
  workload group на том же компиляторе, с исходной ошибкой без сокрытия.
  Установленный SDK27/504 и отдельные три LinuxARM64 группы с10 LLDB/DAP
  случаями пройдены; см. docs/evidence/toolchain-0.115.0-task-debug.json.

## Зафиксированный121: toolchain0.114 / язык0.20

- [x] Проверить private bounded task-profile collector: once-per-invocation,
  перенос между потоками, TLS, CPU/elapsed clocks, ownership и явные drops.
- [x] Подключить проверенный collector к task driver/compiler и public CLI
  для native020; проверить реальные вызовы, отчёты, проектные лимиты и replay.
- [x] Проверить точный121:134 группы, установленный SDK26/498 команд,
  строгие sanitizers и отдельные9 групп Linux с GCC sanitizer runtime probe.
  Эти платформенные результаты имеют собственные ограниченные области проверки.

- [x] Соединить public019 parser/checker/graph с native compiled continuations,
  независимыми AST/TypeScript schedulers и conservative lifetime checking.
- [x] Проверить настоящую018 миграцию с сохранением истории и явными отказами
  неподдержанных task ABI; сохранить первичный проект081 без изменения.
- [x] Добавить явные лимиты шагов, дедлайна и task workers в CLI, проектные
  конфигурации и acceptance tasks. Точный113 прошёл118 групп регрессии;
  его установленный SDK прошёл24 этапа и438 команд.
- [x] Подготовить private host-completion kernels и явную file-read lease:
  ограниченная очередь, билеты владельца и поколения, физическое завершение
  после отмены. Публичные асинхронные файловые операции ещё не подключены.
- [x] Исправить воспроизводимые отказы114 и проверить точный115: full122,
  sanitizers, три браузерных движка и21 группа Linux; SDK24/438 пройден.
- [x] Подготовить explicit root FileReadGrant, проверить45/42 сценария
  и независимо проверить код без изменения семантики языка019.
- [x] Завершить общий прогон116:122 группы и installedSDK24/438.
- [x] Подключить два whole-file source read в явной версии020 с миграцией019,
  согласованными эффектами и backend'ами. Точный119b прошёл128 групп
  регрессии и установленный SDK25/486 команд на macOS.
- [ ] Проверить текущую файловую интеграцию на полной платформенной матрице;
  завершить provider logical debugging и NEX UI task adapter. Source-only native
  task debugger/profile и static/fixed-shared provider profiling имеют отдельные
  реализованные slices выше; arbitrary runtime load/unload остаётся pending.
- [ ] Завершить общий GPU/NPU API, оставшиеся платформы и измерения
  качества/суммарной стоимости задач для нескольких LLM.

## История этапов

## Сохранённый этап: toolchain0.96 / язык0.18

- [x] Найти задержку настоящей095warm10k-сборки и заменить посимвольное чтение
  compiler inputs блочным64КиБ с проверкой ошибок и RAII закрытием файла.
- [x] Проверить17целевых групп, реальные rawbinary/FIFO/UTF8-boundary/rejection
  сценарии и все байты трёх настоящих146МБ/24МБ/15МБ артефактов в18наблюдениях.
- [x] Сохранить096 native10000 cold9900/warm0/edit1 и обе архивные ревизии после
  удаления исходников; см. docs/evidence/native-scale-0.96.0.json.
- [ ] Оставшаяся на момент096 приёмка full100/SDK/платформ/IDE/истории хранится
  как исторический статус. Текущий SDK требует собственного matching gate.
- [x] Позднейшие этапы отдельно подключили browser workers и structured
  tasks/channels; их точные текущие границы сообщает describe. Оптимизация096
  сама по себе не была завершением языка или всей цепочки.

## Сохранённый кандидат: toolchain0.95 / язык0.18

- [x] Найти причину медленного кэшированного плана на настоящем проекте
  из10,000 функций; добавить индекс только на время readonly-планирования.
- [x] Сравнить точные байты планов семи программ с настоящими библиотеками094,
  включая9,900 функций, generic/local names, layouts и callable bridges.
- [x] Сохранить полный native100x10000 результат094 и узкий NEX/C++/Python
  эксперимент; добавить воспроизводимый opt-in runner.
- [x] Проверить полный независимый native cold9900/warm0/edit1/standalone
  и обе архивные ревизии после удаления исходных путей проекта.
- [ ] Завершить окончательный095: full99/SDK/платформы/IDE/история
  и оставшиеся требования качества/языка.

## Сохранённый кандидат: toolchain0.94 / язык0.18

- [x] Исправить реальный E2BIG после компиляции9,900 функций: GNU response files
  для native build/image tools с сохранением буквальных аргументов приложений.
- [x] Проверить настоящие Clang/LLVM ar сверх лимита ОС и сохранённые9,900
  NEX-объектов: линковка, проверка DWARF и исполнение верного результата.
- [x] Завершить независимый native100x10000 cold/warm/edit/standalone
  и обе архивные ревизии после удаления исходных путей проекта.
- [ ] Завершить полные98 групп, SDK, платформы, редактор и миграцию истории.

## Сохранённый кандидат: toolchain0.93 / язык0.18

- [x] Вынести повторный анализ callable/CPU-замыкания из генерации отдельных
  объектов, сохранив нормальную проверку MLIR/LLVM и локальный emit/Wasm путь.
- [x] Проверить12 целевых групп, одинаковый IR1,980 функций с точным учётом
  идентичности компилятора, реальные вызовы Clang, warm reuse и правку1 функции.
- [ ] Завершить нативную проверку100 модулей/10,000 функций, полные97 групп,
  установленный SDK, платформы, редактор и остальные критерии качества.

## Сохранённый кандидат: toolchain 0.92 / язык 0.18

- [x] Подключить ordered CPU map к checker/reference/native/TypeScript;
  actual native threads и serial semantics других backend'ов различаются явно.
- [x] Сохранить настоящую0.17 фикстуру с двумя ревизиями, включая конфликт
  нового имени; проверить миграцию, старую историю и resource/capture guards.
- [x] Исправить приоритет resource errors; проверить scalar/generic/value matrix,
  binary-provider reuse, реальные worker debug/profile и три браузера.
- [ ] Завершить полную приёмку точного0.92 SDK/платформ/редактора/миграции.
- [ ] Добавить реальную асинхронную интеграцию browser workers и общие задачи,
  каналы/async, CPU/GPU/NPU и оставшиеся платформенные/качественные проверки.

## Сохранённая основа: toolchain 0.91 / язык 0.17

- [x] Подключить private-границу вызова скомпилированного замыкания к CPU workers:
  локальные handles, scalar bits, один retained result и очистка всех выходов.
- [x] Добавить проверки настоящих NEX-функций, возвращённых замыканий,
  checked-ошибок и результата `?`, отрицательные ABI/ownership-сценарии.
- [x] Завершить sanitizers, Mac/Linux full96, SDK24, Linux live, пять IDE-профилей
  и полную миграцию основной истории0.16 в язык0.17 для точного снимка0.91.
- [ ] Подключить source-операцию: типы/эффекты/захваты, reference и TypeScript,
  native lowering, явную миграцию, SDK/debug/profile и документацию для LLM.
  Private-прототип не является готовой многопоточностью исходного языка.

## Сохранённая основа: toolchain 0.90 / язык 0.17

- [x] Реализовать типизированный `?` во frontend, interpreter, native и TypeScript,
  правила cleanup и явную миграцию из настоящих архивов 0.16.
- [x] Проверить на прототипе полную копию основного графа: все 47 исторических
  ревизий и строки всех 16 таблиц сохранены; четыре ревизии 0.16 явно мигрированы.
- [x] Исправить подтверждённое падение Python DAP при завершении; проверять
  нормальный exit адаптера в SDK и тестовых клиентах.
- [x] Исправить повторный обход statement-match и актуализировать учебный patch.
  Пять целевых групп 0.90 прошли; полный прогон 0.89 сохранил четыре отказа.
- [x] Проверить frontend/interpreter/историю/контекст проекта из 100 модулей
  и 10 000 функций. На момент0.90 нативная сборка ещё не была проверена;
  отдельные094–096 receipts выше фиксируют последующую проверку.
- [x] Заморозить и сохранить точный 0.90 в проверенной резервной ветке.
- [ ] Завершить full95, installed SDK24,
  Linux live/source-free, установленный редактор и повтор миграции через SDK.
- [ ] Проверить cold/warm/edit нативную сборку крупного проекта и реальные
  baseline C++/Python; измерить полную стоимость задач для нескольких LLM.
- [ ] Подключить безопасную source concurrency ко всем backend'ам; завершить
  необходимые границы обработки ошибок, общие CPU/GPU/NPU и платформы.
- [ ] После готовности языка реализовать [конвертер C++/Python](docs/project-porting-design.md)
  для явного подмножества с отчётом о неподдержанных конструкциях.

Одобренный основной проект 0.81 / язык 0.16 сохранён отдельно. Его историческая
приёмка не проверяла нормальный shutdown DAP и не закрывает найденный дефект.
Нижележащие этапы — дорожная карта и исторические записи; актуальный набор
возможностей нужно получать от фактического `nex describe`.

## 1. Цель проекта

Создать язык и инструментарий, в котором программа представлена семантическим графом, а человек и ИИ могут читать, проверять и изменять отдельные компоненты этого графа.

Название: **NEX — Neural Execution Language** («язык нейронного исполнения»). Главная идея — минимальное количество токенов для передачи максимального количества точного смысла при максимальной производительности и безопасности исполняемой системы.

Результат сборки — самостоятельное приложение, которому для исполнения не требуется модель ИИ или подключение к сервису NEX. Для веб-цели результатом служат браузерные файлы и, при необходимости, отдельно запускаемый сервер.

Долгосрочные цели:

- Веб-приложения: браузерный интерфейс, серверный API и общие модели данных.
- Серверные приложения, настольные программы, мобильные приложения и игры.
- Windows, Linux, macOS, Android и iOS; основные архитектуры — x86-64 и ARM64.
- Общая логика приложения и платформенные адаптеры для системных возможностей.
- Встроенные проверки, отладка и профилирование с привязкой к графу программы.
- Уменьшение суммарных затрат ИИ на создание и сопровождение программ.

Скорость исполнения, расход памяти и экономия токенов — проверяемые гипотезы. До проведения сопоставимых экспериментов не обещаем превосходства над другими языками.

## 2. Границы первой версии

Первый результат — небольшой рабочий инструмент командной строки, который проходит весь путь:

```text
Структурированная программа
  → семантический граф
  → проверка типов и эффектов
  → MLIR
  → LLVM
  → объектный файл и компоновка
  → нативный исполняемый файл
```

Первая целевая платформа: macOS ARM64, после проверки доступного оборудования и инструментов. Следующие цели — Linux x86-64 и Windows x86-64. Это порядок реализации; фактическую поддержку подтверждаем сборкой и запуском тестов на каждой цели.

Веб — отдельная обязательная цель продукта. Границы браузерного и серверного исполнения заложены в модель. Реализованы браузерное приложение с локальным состоянием и связанный пример с явными асинхронными HTTP-командами, нативным API и постоянными данными. Декларации endpoint уже генерируют клиентские помощники, серверную диспетчеризацию и OpenAPI. Нативные модули уже компилируются отдельно с инвалидацией по контрактам и типам; следующие шаги — реальное профилирование и расширение отладки. Первая браузерная версия использует генерацию TypeScript/JavaScript; WebAssembly подключаем отдельным шагом для вычислительных модулей.

Минимальный язык:

- Целые числа фиксированной разрядности, логические значения и отсутствие возвращаемого значения (`unit`).
- Локальные значения, арифметика, сравнения, ветвления, циклы и вызовы функций.
- Явные типы на границах функций.
- Разделение чистых вычислений и разрешённых внешних действий.
- Минимальная библиотека исполнения для вывода и измеряемых примеров.

Полные обработчики алгебраических эффектов, универсальная система владения памятью, GPU-компиляция, редактор NEX Studio и мобильные пакеты относятся к следующим этапам.

## 3. Готовые компоненты

| Компонент | Роль | Когда подключаем |
|---|---|---|
| MLIR + LLVM | Представление вычислений, преобразования, оптимизация и машинный код | Первый нативный компилятор |
| LLD / системный компоновщик | Получение исполняемых файлов | Первый нативный компилятор |
| SQLite | Хранение графа/ревизий и серверных данных в разделах пользователей | Уже подключён |
| nlohmann/json | Строгий JSON-кодек по проверенным моделям NEX | Уже подключён, язык 0.4 |
| cpp-httplib + OpenSSL | Нативный HTTP/HTTPS host и TLS | Уже подключены, инструментарий 0.5.0 |
| BLAKE3 | Хеши содержимого и ключи кеша | Основа графа |
| LLDB и `lldb-dap` | Исполнение под отладчиком и интерфейс подключения | Диагностика MVP |
| Tracy | Инструментирование и просмотр профилей | Диагностика MVP |
| Z3 | Решение логических условий для поддерживаемых контрактов | Подключён для чистых скалярных контрактов, инструментарий 0.11.0 |
| SDL3 | Окна, ввод и платформенная основа графических примеров | Графические приложения |
| wgpu / wgpu-native | Графика и GPU-вычисления через библиотечный интерфейс | Графические приложения |
| TypeScript + React | Генерируемые клиентские модули и интерфейс на основе HTML DOM | Первая веб-версия |
| Vite | Сервер разработки и сборка браузерных ресурсов | Первая веб-версия |
| Playwright | Проверки пользовательских сценариев в браузерах | Первая веб-версия |
| LLVM WebAssembly backend + LLD | Чистые скалярные Wasm-модули и адаптер BigInt | Проверены в 0.60.2 в границах `docs/wasm.md` |

Проверенный стек реализации компилятора — C++20, CMake и LLVM/MLIR 22.1.8. На текущей машине используется Unix Makefiles; Ninja не установлен и для сборки не требуется. Версии зависимостей и архитектурные решения записаны в `docs/architecture.md` и `THIRD_PARTY.md`.

Библиотеки исполнения приложения и инструменты разработки учитываем отдельно. В готовое приложение включаем только необходимые ему компоненты.

### Проекты, из которых заимствуем архитектурные решения

| Проект | Что изучаем | Решение для NEX |
|---|---|---|
| Unison | Код как структурированные объекты, адресация по содержимому и зависимости | Собственная модель графа и ревизий |
| Koka | Типы с эффектами и обработчики эффектов | Сначала простая проверка разрешённых эффектов, затем расширение модели |
| Mojo | Организация компилятора, память, специализация и CPU/GPU | Проверка пригодности отдельных частей; обязательную зависимость пока не вводим |
| Dafny / Boogie | Контракты и генерация условий корректности | Собственный ограниченный проверяющий модуль с Z3; Boogie оцениваем отдельно |
| GlyphLang | Компактное представление и работа ИИ с программой | Эксперименты с полными затратами токенов и частотой ошибок |

Перед заимствованием исходного кода фиксируем конкретную ревизию, лицензию файла, необходимые уведомления и транзитивные зависимости.

### Архитектура веб-приложений

Граф NEX описывает экраны, состояние, действия пользователя, модели данных, API и серверные операции. Компилятор проверяет эти части и формирует несколько связанных результатов:

```text
                        Граф приложения NEX
                                  │
                 Проверка типов, эффектов и границ исполнения
                                  │
          ┌───────────────────────┼────────────────────────┐
          ▼                       ▼                        ▼
     Интерфейс и состояние   Серверные операции     Вычислительные модули
          │                       │                        │
     TypeScript + React       MLIR → LLVM              MLIR → LLVM
          │                       │                        │
          Vite                Нативный сервер       WebAssembly + адаптер JS
          │                       │                        │
     HTML / CSS / JS  ←──── HTTP API ────→ База данных      │
          └────────── вызовы из браузерного JS ─────────────┘
```

Решения для первой реализации:

- Интерфейс — семантические HTML-элементы, CSS и React-компоненты. Предусматриваем формы, клавиатурную навигацию, доступность, адаптивную вёрстку и навигацию по URL.
- Браузерная логика — отдельный backend генерации TypeScript из поддерживаемого подмножества графа NEX. LLVM используется в нативной и Wasm-ветках; преобразование NEX в TypeScript требуется разработать самостоятельно.
- Общая логика — переносимые модели и функции без платформенных эффектов. Для каждого backend сохраняем семантику чисел, строк, ошибок и асинхронности; проверяем совпадение поведения. Для 64-битных целых отдельно фиксируем представление в JavaScript и кодирование в API.
- Сервер — нативная программа с HTTP-runtime. Запросы к базе, серверные ключи и операции с привилегиями остаются на серверной стороне графа и не попадают в клиентскую сборку.
- API — генерируемые обработчики, клиентские вызовы и схема сообщений. Проверка входных данных и прав выполняется на сервере независимо от клиентских проверок. Вызов сервера является явной сетевой операцией с ошибками, тайм-аутами и отменой.
- WebAssembly — дополнение для обработки изображений, аудио и других вычислительных задач. Браузерные возможности доступны через адаптеры; наличие Wasm-модуля не заменяет интерфейс и Web API.
- Долгие вычисления переносим в Web Worker, если это оправдано измерениями; учитываем стоимость обмена и копирования данных между JS, worker и Wasm.
- Изменения вносим в граф NEX и заново генерируем затронутые файлы. Пользовательские JS/TS-компоненты подключаем через явные точки расширения, чтобы повторная генерация не стирала ручную работу.
- Первый режим доставки — клиентское приложение со статическими ресурсами и опциональным API. Предварительную генерацию страниц и серверный рендеринг добавляем отдельным шагом для сценариев с требованиями к индексации и первому отображению.

Результаты веб-сборки: HTML/CSS/JS, ресурсы, опциональные `.wasm`, описание API и опциональный серверный бинарник. Результат можно разместить на обычном статическом хостинге и/или сервере приложения; доступ к ИИ во время работы не требуется. Сетевые функции приложения требуют доступности своего API.

## 4. Порядок работ

### Этап 0. Проверить технологическую основу

- [x] Проверить локальное оборудование, компиляторы, SDK и CMake; записать доступность Ninja и выбранную ему альтернативу.
- [ ] Выбрать совместимые стабильные версии LLVM, MLIR, LLD и LLDB.
- [x] Проверить минимальную сборку приложения с API LLVM/MLIR.
- [x] Зафиксировать версии и способ получения зависимостей.
- [x] Подготовить перечень лицензий и уведомлений для подключённых компонентов; завершить уведомления для переносимого SDK при его упаковке.
- [x] Записать архитектурные решения: язык реализации, структура графа, неизменяемые значения с автоматическим владением и границы MVP.
- [x] Зафиксировать границы `client`, `server` и переносимой общей логики; учесть браузерный backend при проектировании типов и эффектов.

Критерий готовности: минимальный эксперимент собирается воспроизводимым способом; определён проверенный набор зависимостей.

### Этап 1. Описать формат графа и создать хранилище

- [x] Описать узлы функций, параметров, блоков, инструкций и выражений; хранить структурные связи и ссылки на лексические объявления/вызываемые функции.
- [x] Добавить самостоятельные постоянные узлы модулей и типов и согласование идентичности между хранилищами.
- [x] Добавить атомарную замену исходных struct/enum вместе с зависимыми функциями и endpoint; сохранять ID типов и архивные ревизии. В 0.45 пройдены 52 группы и оба установленных SDK на macOS/Linux ARM64; точные границы — `docs/evidence/type-patches-0.45.0.json`.
- [x] Завершить точные атомарные правки исходных выражений, инструкций и patterns по ID операции с защитой ревизии/исходников. В 0.48 пройдены 56 групп и оба SDK на macOS/Linux ARM64; точные границы — `docs/evidence/operation-patches-0.48.0.json`.
- [x] Разделить постоянные идентификаторы функций/операций и хеши содержимого; сохранять ревизии и явно выдавать новые ID неоднозначным дубликатам.
- [x] Определить каноническую сериализацию и версию формата.
- [x] Описать, как зависимости участвуют в хешировании, включая рекурсию при хешировании всей программы.
- [x] Реализовать хранение функций, связей и ревизий в SQLite.
- [x] Добавить endpoint-узлы со стабильными идентификаторами, рёбрами к обработчикам, каноническими контрактами и атомарными правками.
- [x] Сделать экспорт и импорт в читаемый структурированный формат.
- [x] Реализовать транзакционную замену функций с проверкой ожидаемой исходной ревизии.
- [x] Добавить команды создания проекта, просмотра графа и применения изменений.
- [x] Добавить модули, импорты, публичные границы, локальные библиотеки и фиксацию содержимого зависимостей.
- [x] Архивировать все исходники ревизии и экспортировать переносимый многофайловый проект с зависимостями.

Критерий готовности: программу можно сохранить, экспортировать, восстановить и изменить; частичная или конфликтующая операция не повреждает граф. Одинаковое каноническое содержимое даёт одинаковый хеш.

### Этап 2. Определить семантику и эталонное исполнение

- [x] Зафиксировать поведение арифметики, переполнения, деления на ноль и преобразований типов.
- [x] Описать области видимости, порядок вычислений и правила вызова функций.
- [x] Реализовать проверку типов и ссылок между узлами.
- [x] Ввести минимальную проверку эффектов: чистая функция не может неявно выполнять ввод-вывод.
- [x] Реализовать простой эталонный интерпретатор для поддерживаемого подмножества.
- [x] Подготовить корректные программы и примеры ожидаемых ошибок.
- [x] Добавить номинальные enum с данными и исчерпывающий statement match во все backend, wire/API и отладчик с явной миграцией 0.5→0.6.
- [x] Добавить параметрически проверяемые generic-функции/struct/enum, вывод аргументов и конкретные специализации в native/TypeScript, JSON/API и watch.
- [x] Расширить match выражениями, вложенными patterns/guards и result; проверить типизированное покрытие, литералы, структуры и точные списки.
- [x] Добавить встроенные generic-ограничения операций, проверку неиспользуемых шаблонов и передачи ограниченных параметров между объявлениями.
- [ ] Добавить пользовательские traits/реализации, связанные типы, higher-kinded типы и значения функций.
- [x] Добавить к ошибкам проверенного интерпретатора код, ID операции, ревизию и хеш точных исходников; сопоставить ключи ошибок с TypeScript.
- [x] Связать текстовые нативные runtime traps с проверенным графом и точной сборкой; в 0.46 пройдены 54 группы и оба SDK на macOS/Linux ARM64. Границы — `docs/evidence/native-diagnostics-0.46.0.json`.
- [ ] Завершить идентификацию для диагностики parser/checker и остальных путей исполнения, включая signal/core и точное optimized-PC восстановление.
- [x] Описать правила доступности операций на клиенте и сервере и отклонять недопустимые прямые зависимости, включая импорты.

Критерий готовности: поведение минимального языка описано и проверяется независимо от машинного backend. Некорректные графы отклоняются до исполнения.

### Этап 3. Собрать первый нативный компилятор

- [x] Определить минимальное представление операций NEX в MLIR.
- [x] Реализовать преобразование проверенного графа в MLIR и далее в LLVM IR.
- [x] Получать объектные файлы и компоновать их с минимальной библиотекой исполнения.
- [x] Реализовать команды проверки, сборки и запуска.
- [x] Добавить режимы `debug`, `profile` и `release` с документированными флагами; `profile` включает зоны функций и shallow-учёт управляемых выделений.
- [x] Собирать выбранное замыкание функций в нативный статический архив для доверенного C++ host с ABI совпадающей версии; стабильный внешний ABI остаётся открытым.
- [x] Заложить экспериментальный интерфейс вызова внешних функций через C ABI: типизированный транспорт ABI 1, явные host-разрешения и source `extern` в языке 0.15. Стабильность ABI, упаковка зависимостей и полная текущая матрица ещё проверяются.
- [x] Сравнивать результаты нативного исполнения с эталонным интерпретатором.

Критерий готовности: арифметический пример и пример с циклами и вызовами функций собираются в самостоятельные нативные программы и дают ожидаемый результат без ИИ.

### Этап 4. Реализовать инкрементальную сборку

- [x] Построить индекс прямых и обратных зависимостей функций и модулей-поставщиков layout.
- [x] Определить гранулярность кеша: модуль с достижимым набором функций; внутримодульный кеш функций остаётся отдельным улучшением.
- [x] Включать в ключ кеша всей программы исходники зависимостей, версию компилятора и runtime, целевую платформу, параметры оптимизации и релевантные настройки.
- [x] Кешировать выбранные компоненты нативного runtime с проверкой целостности объектов и сохранять точную проекцию входных исходников/заголовков.
- [x] Пересобирать затронутые нативные модули и инвалидировать потребителей по контрактам/типам.
- [x] Проверить тело/сигнатуру/эффекты, layout/JSON, закреплённую библиотеку, профили, compiler/runtime ABI и отказ неподдерживаемой цели на хосте.
- [ ] Кешировать тесты только при зафиксированных входах и допустимых условиях детерминизма.

Критерий готовности: инкрементальная и чистая сборки проходят одинаковые проверки поведения; локальное изменение не вызывает ненужную перекомпиляцию независимых модулей.

### Этап 5. Добавить отладку и профилирование

- [x] Создать текстовое представление функций и постоянные узлы операций; связать исходные позиции, MLIR NameLoc и TypeScript с детерминированными ключами.
- [x] Проверить LLDB/DAP-кандидаты операций по строке/столбцу и разрешение ключей в постоянные ID архивной ревизии без продолжения процесса.
- [ ] Завершить точное сопоставление оптимизированного машинного кода, нативных traps, профиля операций и core-файлов; несколько исходных кандидатов остаются явными.
- [x] Подключить LLDB; проверить остановку, шаги, локальные значения и стек вызовов на macOS ARM64.
- [x] Добавить типизированные параметры/локальные значения, области видимости, ограниченный просмотр runtime-значений и read-only JSON кадров.
- [x] Проверить настоящий lldb-dap: breakpoint, стек, scopes/variables, дочерние поля, продолжение и завершение. Другие платформы требуют отдельных проверок.
- [x] Вычислять чистые выражения NEX по точным снимкам кадра отдельным интерпретатором: типы/эффекты/realm, Unicode, поля/списки/results, вызовы, явные лимиты и unavailable без исполнения кода в процессе.
- [x] Добавить stdio DAP-мост для NEX Watch: выбранный кадр, дочерние значения и страницы, read-only результаты и отказ устаревших ссылок. Точный снимок проверяется до нормализации JSON; неоднозначные поля отклоняются.
- [x] Добавить выборочное чтение заголовков списков/записей/results и нужных полей/элементов без захвата всего корня; проверить динамические индексы внутри чистых функций, LLDB/DAP и сохранённые частичные снимки после удаления исходников.
- [ ] Добавить чтение строк по частям, прямые страницы больших корней в DAP, установочный пакет расширения редактора и дополнительные host/layout-проверки.

Чтение Unicode-окон строк проверено в 0.54, установленное расширение — в 0.56.
Изолированная 0.57 добавляет ограниченные прямые страницы нативных list/bytes:
поздние индексы, фильтры, лимит1000 и истечение ссылок. Полная новая матрица,
крупные именованные/строковые корни и дополнительные host/layout остаются открыты.
- [x] Записывать идентификатор сборки, ревизии и параметры, нужные для разбора сбоя.
- [x] Подключить Tracy 0.14.1 для зон нативных функций и именованных shallow-пулов объектов/дескрипторов; буферы, GPU и системные события остаются открытыми.
- [x] Сохранять локальный профиль с ревизией/ключом сборки, узлами графа, сценарием и CPU/целевой платформой; Tracy получает точную build identity.
- [x] Измерить накладные расходы на фиксированном сценарии с повторениями и тем же результатом; другие нагрузки/платформы требуют отдельных измерений.

Критерий готовности: можно остановить программу на выбранной операции, найти её узел и определить затратный участок по реальному профилю. Первые измерения CPU не выдаются за полноценную поддержку GPU, энергии или системной трассировки.

### Этап 6. Проверить MVP

- [x] Подготовить чистый вычислительный пример с фиксированным результатом.
- [x] Подготовить примеры с вводом-выводом, восстанавливаемыми ошибками и проверкой входных JSON-данных.
- [x] Повторить путь от импорта графа до запуска на чистом окружении: установленный SDK проверяется в отдельном Linux-контейнере без исходного дерева и внешней сети.
- [x] Проверить изменение одного компонента, повторную сборку, отладку и профиль: поддерживаемый `tools/sdk_acceptance.py` проходит ошибочную задачу, правку графа, нативную/TypeScript-проверку, профиль, архивный DAP и повторение после удаления исходников. Live-проверка требует поддерживаемого host.
- [x] Записать поддерживаемые возможности и известные ограничения.

Критерий готовности MVP: этапы 0–6 пройдены; есть воспроизводимый сквозной пример и инструкция, по которой другой разработчик получает тот же результат.

### Этап 7. Добавить постановку задач и интерфейс для ИИ

- [x] Описать текстовый формат задачи: цель, входы/выходы, ограничения, платформы и критерии приёмки (`llm/TASK_TEMPLATE.md`); добавить машинную форму `nex.task/1` и схему `llm/task.schema.json`.
- [x] Выполнять явные критерии приёмки по снимкам нескольких программ, сохранять отчёты/артефакты/историю и повторять проверки после удаления рабочих исходников; фиксировать тела тестов и intent формальных свойств.
- [x] Поддерживать версионируемый пакет языка для разных LLM: спецификацию, EBNF, системный промпт, примеры, машинное описание возможностей и протокол правок с диагностикой.
- [x] Описать передачу пакета чат-модели и агенту с терминалом; привести воспроизводимый цикл исправления, проверки и экспорта (`llm/WORKFLOW.md`).
- [ ] Провести сопоставимые испытания на разных LLM и измерить успешность, число исправлений и полный расход токенов.
- [x] Связать требования с компонентами графа, целями и проверками. Статическая достижимость не считается динамическим покрытием или доказательством полноты человеческого требования.
- [x] Предоставить ограниченные инструменты поиска, чтения подграфа, просмотра зависимостей и транзакционных правок с проверкой ревизии. Статическая достижимость не считается динамическим покрытием.
- [x] Возвращать компактные структурированные результаты проверки, сборки и тестов.
- [x] Хранить локальное происхождение изменений и обеспечивать возврат к прежней ревизии. В 0.49 атомарный журнал HEAD, объявленные автор/заметка, ограниченные страницы и восстановление архивов с проверкой ожидаемой HEAD прошли 57 групп, оба SDK и Linux live-проверки на macOS/Linux ARM64. Авторство остаётся объявленным; точная область — `docs/evidence/change-history-0.49.0.json`.
- [ ] Добавить необязательный ИИ-слой, переводящий задачу в изменения и запускающий инструменты.
- [x] Проверить цикл ограниченного задания: требование → ошибочный кандидат → правка графа → прежние критерии проверки → сборка → измерение → повторение по снимкам, включая установленный SDK вне репозитория.

Критерий готовности: ограниченную задачу можно выполнить через инструменты графа; обязательные проверки работают детерминированно и доступны без модели.

### Этап 8. Развить runtime и поддержку платформ

В 0.43 добавлена упаковка native loader-зависимостей на совпадающем хосте:
явные разрешения, лицензии, новые pins после relocation, проверенная производная
ревизия с сохранением исходной истории и каталог относительно исполняемого
файла. Проверки этого этапа идут. Произвольные динамические загрузки из C,
cross-target packaging, общие ресурсы и стабильный FFI остаются открытыми.

- [ ] До добавления динамических объектов зафиксировать модель владения, времени жизни, ресурсов и ошибок FFI. В 0.34 добавлена внутренняя основа C++: домены, физические leases/квоты, отмена и потоковые файлы; в 0.35 — управляемые файловые значения, нативные операции и объединение разрешений с областью запроса. Контракт — `docs/resources-design.md`. В 0.36 / языке 0.14 первый исходный тип `file` подключён к checker, интерпретатору, native backend, отладке и явной миграции; браузерные и wire-границы запрещают перенос владельцев. Матрица 0.36 пройдена на macOS ARM64 Debug/Release, Linux ARM64 и эмулируемом Linux x86-64; результаты и границы текущей 0.37 — в `STATUS.md`. В 0.37 добавлена экспериментальная C-граница значений: копирование данных, владельцы на время вызова, ошибки, квоты и отмена; исходные extern-декларации и загрузчик ещё не подключены. В 0.38 добавлены экспорт типовой схемы, проверка входных/возвращённых значений и типизированные nominal-конструкторы с сохранением старого C-префикса. В 0.39 реализован host-загрузчик: отдельный C-дескриптор модуля, явные разрешения на библиотеку/экспорт, pins манифеста и типовой схемы, проверяемая частная копия до инициализации, отмена и физические leases. В 0.40 добавлены явный операторский каталог, метаданные привязки, лексические контексты и общий адаптер со входом через управляемые native-значения; кеш метаданных не обходит область запроса, а нативное завершение отзывает владельцев модулей. В 0.41 / языке 0.15 подключены исходные server extern-вызовы, эффект ffi, интерпретатор/native backend, явная миграция, исключение из браузерного кода и установленный SDK-сценарий. В 0.42 добавлены readonly-отпечаток каталога, foreign_hash в приёмочных проверках и захват бинарных членов с повторной проверкой текущих разрешений при replay. Упаковка полного замыкания зависимостей, общие виды ресурсов и стабильный FFI остаются открытыми; фактическая матрица проверок — в STATUS.md.
- [x] Добавить UTF-8 строки, неизменяемые списки и именованные структуры с автоматическим управлением памятью и проверками границ.
- [ ] Добавить специализированные буферы и правила владения внешними ресурсами. В 0.33 / языке 0.13 реализован неизменяемый `bytes`: владение срезами, кодеки, generics, JSON/API, бинарные файлы и ограниченные watch-выражения. Общие внешние ресурсы, FFI и потоковые буферы остаются открытыми.
- [x] Определить ограниченную модель серверного host: пул синхронных обработчиков, бюджеты, кооперативную отмену и транзакцию на запрос. Исходные async/await и общие конкурентные ресурсы остаются открыты.
- [ ] Добавлять файловую систему, время, сеть и системные вызовы через платформенные адаптеры. В 0.30 / языке 0.12 реализованы текстовые операции с отдельным `fs`, явным каталогом и атомарной заменой; полная матрица компилятора и SDK пройдена на macOS ARM64, Linux ARM64 и эмулируемом Linux x86-64. В 0.31 проверены внутренние бинарные примитивы; в 0.32 добавлены управляемые значения и адаптер. В 0.33 / языке 0.13 открыт исходный `bytes`, подключены API, отладчик и явная миграция 0.12. Проверены macOS Debug, двенадцать этапов установленного SDK и браузерный пример в трёх движках; новая Linux/Release/изолированная SDK-матрица выполняется. Ресурсы, потоковый ввод-вывод и остальные адаптеры остаются открыты.
- [x] Проверить цепочку компилятора/нативных программ и установленного SDK на Linux ARM64 и Linux x86-64 (для x86-64 зафиксирована эмуляция Docker).
- [x] Добавить `nex package` для нативных программ и HTTP/HTTPS: переносимые каталоги с зависимостями, лицензиями и хешами проверены на macOS ARM64, Linux ARM64 и эмулируемом x86-64 без NEX SDK; системный runtime остаётся внешней зависимостью. Полная регрессия 0.29 пройдена; остальные платформы остаются открыты.
- [ ] Подключить Windows x86-64/ARM64 и проверить macOS x86-64 в исполнении; дополнить Linux физическим x86-64 и более широкой матрицей окружений.
- [ ] Для каждой цели зафиксировать SDK, ABI, компоновщик, зависимости и способ доставки.
- [x] Создать нативный HTTP/HTTPS-сервис с проверкой протокола, хешированными bearer-учётными данными, изоляцией пользователей, конкурентными запросами и откатом при сбоях.
- [ ] Измерить пропускную способность и распределение задержек HTTP-сервиса по фиксированному нагрузочному сценарию.
- [ ] При развитии серверного примера оценить OpenTelemetry для трассировки запросов.

Критерий готовности: на заявленных платформах запускается общая логика приложения; серверный пример проходит проверки ошибок, конкурентных запросов и измерения задержек.

### Этап 9. Реализовать веб-приложения

- [ ] Описать узлы страниц, компонентов, состояния, событий и маршрутов.
- [x] Реализовать генерацию TypeScript/React и базового CSS с учётом семантики NEX. Расширения пользовательских стилей/ресурсов остаются открыты.
- [x] Подключить Vite, проверку типов и сборку браузерных ресурсов с зафиксированным npm lock и проверкой целостности кеша.
- [x] Описать начальное состояние, обновление, представление и события через обычные функции/структуры NEX; добавить формы и события истории URL.
- [x] Добавить чистую функцию `commands` с описаниями HTTP-запросов/отмены, сериализацию типизированных ответов, лимиты и адаптер браузерного исполнения.
- [x] Исключать недостижимые серверные определения/литералы из клиентского кода и source maps.
- [x] Добавить `result<T>` и строгую JSON-схему i64/строк/списков/структур с одинаковыми результатами интерпретатора, нативного и TypeScript backend.
- [x] Генерировать API-схемы, клиентские помощники запросов/ответов, серверную проверку сообщений и OpenAPI из явных endpoint-деклараций; проверять успешные ответы до передачи события браузерному приложению.
- [x] Реализовать явную обработку загрузки, сетевых ошибок, отмены, тайм-аутов, устаревших ответов и повторного входа в приложение.
- [ ] Обеспечить исключение серверных секретов и привилегированных операций из клиентского результата.
- [x] Создать веб-пример учёта задач: список, создание, изменение текста/состояния, удаление, API, общие модели и база данных.
- [x] Проверить корректность данных и авторизацию операций для многопользовательского браузерного сценария, включая смену учётных данных, перезагрузку страницы и перезапуск сервера.
- [x] Проверить серверный API: строгие входные модели, постоянные данные, изоляцию пользователей, конкурентное изменение, ошибки/отмену и перезапуск. Связанный браузерный сценарий также реализован и проверен в трёх headless-движках.
- [ ] Проверить доступность форм, клавиатуру, навигацию по URL и разные размеры экрана.
- [ ] Запускать сценарии Playwright на Chromium, Firefox и WebKit; отдельно проверять заявленную поддержку на реальных целевых браузерах и устройствах.
- [x] Проверить базовые браузерные сценарии на трёх headless-движках: Unicode-ввод, создание/переключение/удаление, URL/back/reload, клавиатуру и мобильную ширину. Реальные устройства и вспомогательные технологии остаются отдельной проверкой.
- [ ] Связать ошибки и профили браузера с узлами графа через source maps и идентификаторы сборки; связать клиентский запрос и серверную трассировку.
- [ ] Завершить проверку вычислительной функции в Wasm: LLVM/LLD 22.1, ABI BigInt, передача данных и равенство результатов. Изолированная реализация 0.60 проходит проверки границ и пример в трёх браузерах; текущие full/SDK/platform gates остаются обязательными. Emscripten не нужен первому модулю без host imports; более широкая интеграция требует отдельной проверки.
- [ ] Сравнить JS и Wasm на одном вычислительном сценарии с учётом загрузки модуля и обмена данными; выбирать вариант по измерениям.
- [x] Добавить статическое размещение клиента и отдельный запуск сервера с настройками окружения, TLS и проверкой границ каталога ресурсов.
- [ ] Следующим расширением оценить предварительную генерацию HTML, серверный рендеринг и PWA/offline для конкретных требований.

Критерий готовности базового веб-этапа: приложение генерируется из графа NEX, собирается и проходит браузерные сценарии; API повторно проверяет входные данные и права, а серверные секреты отсутствуют в клиентской сборке. Поддержка Wasm подтверждается отдельным вычислительным примером и измерениями.

### Этап 10. Добавить графику, GPU и мобильные приложения

- [ ] Подключить SDL3 и wgpu через ограниченный и проверяемый интерфейс runtime.
- [ ] Создать пример с окном, вводом, отрисовкой и GPU-вычислением.
- [ ] Подготовить небольшие интеграционные примеры библиотек UI и обработки изображений: формы, события, отрисовка и проверка преобразований тестового буфера.
- [ ] Зафиксировать сценарии измерения задержки ввода, памяти и времени кадра.
- [ ] Проверить Android ARM64 с Android SDK/NDK: жизненный цикл, ввод, разрешения и сборка пакета.
- [ ] Проверить iOS ARM64 с Apple SDK: жизненный цикл, графика, разрешения, подпись и запуск на устройстве.
- [ ] Определить подход к интерфейсам приложений: виджеты, текст, доступность, ввод и интеграция с платформой.
- [ ] Проверять графический backend фиксированными сценами и вычислительными тестами без разработки отдельной игры.

Критерий готовности: примеры запускаются на фактически проверенных устройствах; результаты производительности привязаны к конкретному оборудованию и сценарию. Возможность генерировать код для CPU сама по себе не считается поддержкой ОС.

### Этап 11. Добавить контракты и подготовить устойчивую версию

- [x] Выбрать первый класс контрактов: JSON для чистых i64/bool/unit-функций, привязанный к ревизии и точным исходникам; предусловия, постусловия, инварианты и убывающие меры циклов.
- [x] Переводить поддерживаемые скалярные операции в условия корректности: checked i64, деление/остаток, порядок вычисления, короткое замыкание, assert, ациклические вызовы и индуктивные циклы. Память, эффекты и рекурсия остаются за границей этого доказательства.
- [x] Различать доказательство, контрпример входа/индуктивного состояния, противоречивые предусловия, неизвестно, тайм-аут и неподдерживаемую конструкцию; сохранять SMT-запросы и полный отчёт.
- [x] Добавлено явное runtime-исполнение скалярных pre/post-контрактов через отдельно проверенный source-проект; исходная история сохраняется, арифметика/assert остаются проверяемыми независимо от Z3. См. docs/runtime-contracts.md и приёмку 0.152.
- [x] Расширить runtime-контракты на поддержанные effectful/aggregate и generic source roots, исполнение loop-контрактов и исходный синтаксис0.28. Приёмка Mac0.159 закреплена в docs/releases/0.159.0.json; соответствующие модели доказательств и новая платформенная приёмка остаются отдельной работой.
- [x] Документировать границы доверия: Z3 и перевод условий доверены; результат не доказывает компилятор/backend/runtime/память/внешние библиотеки и не заменяет испытания.
- [ ] Установить правила совместимости формата графа, библиотек и инструментов.
- [ ] Подготовить миграции, резервное копирование, документацию и воспроизводимые сборки.
- [ ] Только после этого оценивать необходимость большого интерфейса NEX Studio.

Критерий готовности: заявленные гарантии ограничены проверенным подмножеством; проект можно обновлять, восстанавливать и сопровождать по документации.

## 5. Как проверяем преимущества NEX

### Корректность

- Сравниваем эталонное и нативное исполнение на одних входных данных.
- Проверяем граничные значения, ошибки типов, эффекты и повреждённые ссылки графа.
- Используем генерацию небольших программ для поиска расхождений backend.
- Проверяем чистую и инкрементальную сборки при изменениях зависимостей.

### Скорость и ресурсы

- Используем одинаковые алгоритмы, входные данные и сопоставимые настройки оптимизации для NEX и эталона на C++ или Rust.
- Отдельно измеряем сборку, запуск, время вычислений, пиковую память и размер результата.
- Для серверов измеряем пропускную способность и задержки p50/p95/p99.
- Для графики измеряем задержку ввода, распределение времени кадра и потребление CPU/GPU/RAM.
- Для веба измеряем загрузку и первое отображение, отзывчивость интерфейса, объём JS/Wasm, браузерную память и время API-запросов. Сравниваем холодный и повторный запуск, настольные и мобильные устройства.
- Фиксируем оборудование, ОС, версии, число повторов и разброс результатов.

### Затраты ИИ

- Сравниваем одни и те же задачи создания, изменения и исправления программ.
- Фиксируем модель, токенизатор, настройки и предоставленный контекст.
- Считаем весь цикл: входной контекст, генерацию, обращения к инструментам, диагностику и исправления.
- Учитываем успешность задачи и число попыток вместе с числом токенов.
- Компактность записи отдельно не считаем доказательством экономии разработки.

## 6. Ограничения объёма и отложенные направления

- Разработка отдельных крупных прикладных продуктов не входит в объём этого проекта.
- Универсальный точный record/replay для потоков, сети и GPU.
- Автоматическую оптимизацию произвольного кода с гарантией улучшения.
- Собственный низкоуровневый профилировщик для каждой ОС.
- Embedded и RISC-V как заявленные поддерживаемые цели.
- WebAssembly подключаем в запланированном веб-этапе; универсальное исполнение в любых WASI-средах требует отдельного плана.
- Переиспользование крупных частей сторонних компиляторов до проверки их соответствия семантике NEX.

## 7. Ближайшая конкретная задача

Рабочая основа — разрабатываемый NEX 0.15 и инструментарий 0.42: параметрические типы и ограничения, вложенные patterns/match, callback-функции и неизменяемые замыкания, конечные `f64`, неизменяемые `bytes`, файловые операции, нативный и браузерный backend, API/хранилище, граф операций, отладка, профиль, проверки Z3, контракты задач и установленный SDK. Это рабочий этап; язык и полная цепочка ещё разрабатываются. Фактические результаты — в `STATUS.md`.

1. Конечные числа `f64` проведены через разрабатываемую версию 0.11: синтаксис/типы, три пути исполнения, JSON/API, отладку, миграцию и пакет для LLM. Проверены 27 наборов на macOS ARM64 и Linux ARM64/x86-64, установленные SDK и числовое веб-приложение в трёх движках. Linux x86-64 работает под эмуляцией; остальные платформы и переносимая поставка SDK остаются открытыми. Границы проверки — `docs/floats-design.md` и `STATUS.md`.
2. Проверка кеша отдельных native-функций 0.25 завершена на macOS ARM64 и Linux ARM64/x86-64, включая сохранённые ревизии и живую отладку на ARM64. Инструментарий 0.26 уменьшает повторную работу при сборке; 0.27 проверяет перемещаемый macOS SDK и относительный выбор инструментов. Завершить текущую матрицу, затем добавить повторное использование frontend, опциональную межмодульную LTO и обоснованный кеш детерминированных тестов; эти части пока не реализованы.
3. Продолжить атрибуцию операций, чтение строк по частям, прямые страницы больших корней и расширение профилирования на буферы, браузер и GPU.
4. Расширять типизированные API-контракты: path/query-параметры, совместимость схем и ресурсные сценарии; текущие фиксированные маршруты и JSON уже работают.
5. Сохранять совпадение семантики интерпретатора, нативного и браузерного backend; расширять проверки изоляции клиента и сетевых границ.
6. Развивать владение ресурсами, внешние интерфейсы, асинхронность и библиотеки; подключать и проверять остальные целевые платформы, SDK и адаптеры.

Отладка отдельных операций и больших значений, расширение профилирования, дальнейшее развитие инкрементальной компиляции, контракты и остальные целевые платформы сохраняются в объёме проекта. Параметры/локальные значения, точные ограниченные снимки, чистые выражения и LLDB/DAP проверены на macOS ARM64. Выполненные части ранних этапов не означают завершённость MVP.

## 8. Основные источники

- [MLIR](https://mlir.llvm.org/), [LLVM](https://llvm.org/), [LLD](https://lld.llvm.org/), [LLDB](https://lldb.llvm.org/).
- [Лицензирование LLVM](https://llvm.org/docs/DeveloperPolicy.html#copyright-license-and-patents).
- [SQLite](https://sqlite.org/whentouse.html), [условия распространения SQLite](https://sqlite.org/copyright.html).
- [BLAKE3](https://github.com/BLAKE3-team/BLAKE3), [Tracy](https://github.com/wolfpld/tracy), [Z3](https://github.com/Z3Prover/z3).
- [Unison](https://github.com/unisonweb/unison), [Koka](https://github.com/koka-lang/koka).
- [Исходники Modular / Mojo](https://github.com/modular/modular), [объявление об открытии Mojo](https://www.modular.com/blog/mojo-open-source).
- [Dafny](https://github.com/dafny-lang/dafny), [Boogie](https://github.com/boogie-org/boogie), [GlyphLang](https://github.com/GlyphLang/GlyphLang).
- [SDL3](https://github.com/libsdl-org/SDL), [wgpu](https://github.com/gfx-rs/wgpu), [wgpu-native](https://github.com/gfx-rs/wgpu-native).
- [React](https://react.dev/learn), [TypeScript](https://www.typescriptlang.org/docs/handbook/typescript-from-scratch.html), [Vite](https://vite.dev/guide/), [Playwright](https://playwright.dev/docs/intro).
- [Emscripten](https://emscripten.org/docs/introducing_emscripten/about_emscripten.html), [цели WebAssembly и интеграция с Web API](https://webassembly.org/docs/high-level-goals/).

### Нативные платформы: текущий шаг

Инструментарий 0.18 добавляет выбор ABI и JSON-конфигурацию компилятора, SDK и зависимостей. На macOS настроена сборка arm64/x86_64 с раздельными кешами. macOS Intel-артефакты проверяются на ARM64; запуск и LLDB/DAP на macOS Intel ещё нужно проверить. Инструментарий 0.19 фиксирует конфигурацию и отпечатки целевых инструментов в задачах и сверяет их с текущим доверенным каталогом при повторе. Шаг Linux 0.20 описан ниже. Далее нужны полная упаковка инструментов/SDK, упаковка библиотек/подпись, Windows, мобильные SDK и переносимый дистрибутив. Поддержка генератора LLVM сама по себе не завершает поддержку платформы.

### Linux: инструментарий 0.20

Добавлен зафиксированный контейнерный рецепт для ARM64 и x86-64 и проверка установленного SDK без внешней сети. Для Linux выбран LLVM LLD с проверяемыми ELF/DWARF, отпечатки инструментов учитывают явно выбранный компоновщик. Отчёты сохраняют архитектуру исполнения, эмуляцию и пропуски. Это не завершает переносимые дистрибутивы, все Linux-окружения, Windows или мобильные/графические адаптеры; состояние фактических проверок записывается в STATUS.md.

- [ ] Завершить проверку снимков графа (изолированный 0.50) и явных версий проектов/достижимых библиотек (изолированный 0.51); отдельные результаты и точная область сохраняются в `STATUS.md`.
- [ ] Завершить контекст ошибок frontend: в изолированном 0.52 добавлены хеши захваченных исходников, фаза/область, ограниченный preview и отдельный ID диагностики, включая отвергнутые кандидаты и статические watch-выражения. Полная проверка и остальные пути диагностики ещё не завершены.

- [ ] Проверить разрабатываемые в0.53 ограниченный поиск деклараций и подграф статических зависимостей/входящих ссылок: сохранённая ревизия, отдельные страницы узлов/рёбер, явные границы глубины/байтов, согласованные ID и пакет для разных LLM. Это очередная часть инструментов графа, а не завершение полной цепочки.

- [x] Проверено в отдельном снимке0.54 чтение больших остановленных строк по диапазонам Unicode-символов:64 группы macOS/Linux ARM64, оба SDK18,12 живых отладочных наборов Linux, реальный захват4МиБ и повтор после удаления исходника. Перенесено в корень с отдельными текущими проверками. Причина прежнего сбоя0.53 — устаревший объект после переноса дат; чистая пересборка проходит тот же тест, исходный неудачный полный прогон сохранён. Прямые страницы больших корней, пакет редактора и дополнительные платформы остаются незавершёнными.

- [ ] Завершить интеграцию и полную проверку исходных traits/impls, связанных типов и параметров-конструкторов по `docs/traits-design.md`. В изолированном 0.55 / языке 0.16 реализованы синтаксис, параметрическая проверка, статический выбор методов, проекции, граф и явная миграция с сохранением истории. Ранее прошли 14 целевых Python-проверок и 20 нативных групп инвариантов; отдельно мигрированы пять проектов и два контракта без ослабления приёмки. Последующая библиотечная/API-интеграция0.55 прошла все66 групп macOS/Linux ARM64, оба SDK19 и12 живых отладочных наборов Linux;0.56 добавил проверенные SDK20 и установленное расширение VS Code. Текущая поправка0.56.1 проходит отдельно описанные проверки SDK; перенос в корень и его собственная полная проверка остаются обязательными. Расширенная матрица, Release/sanitizers и остальная цепочка открыты в STATUS.md.

### Расширение редактора: текущий шаг0.56

Отдельный VSIX-прототип регистрирует NEX в VS Code и прошёл настоящий тест
установленного расширения на macOS ARM64/VS Code1.142.0: breakpoint в исходном
файле, стек/scopes, чистые обычные и generic-trait watches, продолжение и выход.
Исходный файл сопоставляется с debug-path только при совпадении с замороженными
байтами. В0.56 добавлены установка исходников расширения вместе с SDK, guide и
дополнительные compiler/SDK-проверки; их фактическая матрица — в STATUS.md.
NEX Studio, LSP, остальные редакторы/платформы и точное optimized-PC/core
сопоставление остаются открытыми. Это не завершает полную цепочку разработки.

### Текущая поправка проверки переносимого SDK

В разрабатываемой 0.56.1 валидаторы macOS/Linux используют общий контракт всех
20 этапов установленного SDK. Старый список из12 этапов, пропущенные проверки,
дубликаты, неправильный порядок и незавершённые команды отвергаются. Одиннадцать
проверок архива/контракта проходят; текущая сборка, полная регрессия и настоящий
перенос/восстановление SDK остаются отдельными условиями приёмки.

В замороженном снимке588 файлов пройдены Linux ARM64 full67,12 живых отладочных
наборов и SDK20 без исходников/сети. macOS66/67 и повтор единственного теста с
offline npm-кэшем сохранены отдельно. Перенос выявил потерю модулей Darwin LLDB
при обратной косой черте в пути executable; последующее исправление выбирает
отдельный закрытый debug-cache и прошло настоящую остановку/watch42/exit0.
Перенос/восстановление SDK пройдены. Полная проверка актуального корня после
переноса остаётся обязательной; критерии приёмки и лимиты не ослаблялись.

Уточнение текущей приёмки0.56.1: переносимые SDK macOS/Linux ARM64 прошли все20
этапов после перемещения и восстановления архива. Точное состояние полного
компилятора и отличие последней Crypto-поправки от macOS full67 зафиксированы
в docs/evidence/sdk-distribution-0.56.1.json. Обновление корня требует его
собственной сборки, full67 и SDK20; полный объём PLAN не объявлен завершённым.

### Текущая привязка отладочного кадра к образу0.57.1

Базовый снимок0.57.0 прошёл все68 групп macOS/Linux ARM64, установленный
macOS SDK21 и оба переносимых macOS SDK21. Проверка чужого core выявила
ложную привязку к ревизии при одинаковых именах функций в разных образах.
Поправка0.57.1 проверяет фактический загруженный модуль до чтения значений
и выдачи ID графа; её живые проверки и новая полная матрица69 выполняются
отдельно. Переносимый формат core, точное optimized-PC сопоставление,
расширенные платформы и остальные незакрытые пункты плана остаются открытыми.

### Разбор native core: изолированный шаг0.58

- [ ] Проверить `nex core` на macOS/Linux: сохранённая сборка и её исходники, реальный core, bounded stack/PC metadata, точные чистые выражения, запрет чужого image, изменённых артефактов и запуска процесса. Новая команда не закрывает переносимый формат core и точное optimized-PC сопоставление.

### Linux core image correction: isolated0.58.1

- [ ] Validate the core-recorded mapping in addition to SBModule identity,
  including different executables at the same path. Linux LLDB minidump input
  needs bounded format/64-bit stream checks. The preceding Linux negative
  control failed; prototype formatter checks pass. Current full/SDK/platform
  gates remain required before root promotion.

### Kernel ELF mapping: isolated0.58.2

- [ ] Validate bounded NT_FILE PC mapping and content-addressed retained build
  binding using a matching installed SDK, actual kernel ELF/minidump/Mach-O cores
  and wrong-image controls. The reader prototype and11 provider cases pass;
  complete current compiler and platform gates remain pending.

### Текущий шаг0.59: перенос native core

В отдельной копии разрабатываются экспорт и чтение капсулы core с исполняемым
образом, символами и замороженными исходниками. Копирование/проверка инвентаря
проверены прототипом, C++-интеграция и фактические moved-core проверки ожидаются.
Оригинальные пути могут отсутствовать; Linux сохраняет проверку записанной
PC-карты, а loaded-module/UUID проверки остаются обязательными. Первое сечение
ограничено совместимым macOS/Linux host и системными зависимостями без source
foreign declarations. Это не закрывает optimized-PC, GPU, async и весь PLAN.

### Проверенный шаг 0.60.2: скалярный WebAssembly и поставка SDK

Реализован `build --target wasm --entry NAME`: чистые
shared/client функции с i64, bool и unit, MLIR/LLVM с настоящим wasm32 layout,
LLD и независимый JS-адаптер с BigInt. Сохраняются checked arithmetic,
left-to-right и short-circuit; глубина вызовов, память и число проходов ограничены.
Восемь тестов backend входят в полный прогон 72 групп. Текущий корневой
компилятор собран начисто; его SDK проходит 23 этапа и 329 команд. Проверены
перенос и восстановление SDK macOS/Linux ARM64, source-free SDK и core capsule,
установленное расширение VS Code, React-приложение и Wasm-пример в трёх
браузерах. Измерения одного графа в JS/Wasm сохраняют загрузку, первый вызов и
повторные вызовы отдельно. Область Linux-регрессии и двух последующих изменений
Python-упаковщика явно указана в `docs/evidence/toolchain-0.60.2.json`.
Язык остаётся0.16; общие Wasm-приложения, WASI, heap values, f64 и GPU не
объявляются поддержанными. Точное состояние описывает `nex describe --json`.


### Проверенные исправления 0.60.1–0.60.2

- [x] Исправить передачу путей исходников, сборки и SDK с кавычками, запятыми
  и переводами строк в Docker. Исходный сбой штатного запускателя воспроизведён;
  отдельная реализация общего CSV-helper проходит два реальных mount-сценария
  и 13 SDK/archive contracts; последующие полные регрессии и SDK проходят.
- [x] Сохранить readonly-изоляцию исходников/SDK и writable-область доказательств;
  проверить установку helper в SDK, сборку и текущие регрессии без ослабления
  критериев или таймаутов. Язык остаётся0.16.
- [x] Исправить literal-percent путь временного Wasm-файла; проверить debug/release,
  кеш и экспорт с кавычками, Unicode, обратной косой чертой и переводом строки.
- [x] Упаковывать ELF multicall-алиасы `ld.lld` и `wasm-ld` с отдельной
  релокацией зависимостей и сохранением argv0; сохранить отказ коллизий.

### Следующие обязательные платформенные работы

- [ ] Реализовать и проверить нативные цели iOS/device и iOS Simulator,
  платформенный ABI/runtime, приложение, установку, запуск и отладку. В0.61
  реализованы и проверены архивы device/simulator; в0.63 проверено WebView-
  приложение на iOS27.1 Simulator. Связь нативного архива с UI, физическое
  устройство, signing и мобильный отладчик остаются открытыми.
- [ ] Реализовать Android toolchain/NDK, пакеты, запуск и отладку; проверить
  ARM64 и заявленные дополнительные архитектуры.
- [ ] Реализовать Windows toolchain/runtime/пакеты и проверить фактическое
  исполнение. Дополнить проверки Intel на физической целевой машине.

Эти пункты остаются открытыми после успешной приёмки 0.60.2. Наличие LLVM
backend, SDK другой платформы или браузерного теста само по себе их не закрывает.

### Изолированный шаг 0.61: нативные библиотеки iOS

Реализованы явные SDK/target для ARM64 device и ARM64/x86-64 Simulator,
проверка платформы/диапазона deployment и реального ABI драйвера, отдельные
кеши/архивы debug/release и запрет локального запуска/host dependencies.
Фокусная приёмка и полные регрессии требуют отдельного результата.
Этот шаг не закрывает приложение, signing, установку, запуск и отладку iOS.
Язык остаётся 0.16; формат графа не мигрируется.

### Изолированный шаг0.62: мобильные проекты

Сгенерированы Xcode/Android-проекты из проверенного NEX web-графа, отдельно
собраны .app и debug APK. Реальный iOS запуск выявил отказ относительных
URL в capacitor://localhost; добавлена точная политика локального origin и
отрицательные проверки. Инструмент tools/mobile_project.py закрепляет Capacitor
8.5.3, локальные проверенные XCFramework, npm lock и уведомления. Генерация,
нативная сборка и запуск имеют разные результаты. Исправленный UI на устройствах,
полная текущая регрессия, SDK, внешние мобильные API и остальные платформы
остаются открытыми; наличие .app/APK само по себе их не закрывает.


### Интеграция0.63: проверенный мобильный HTTPS API

- [x] Явный HTTPS origin оператора, runtime Bearer credentials и точные CORS
  origins сервера; проверены preflight,401 и отказ запрещённых мутаций.
- [x] Реальные0.63 .app/APK сохраняют все6 итоговых web-ресурсов с записанной
  производной конфигурацией index.html. UI использует TypeScript/React/WebView.
- [x] iOS27.1 ARM64 Simulator XCTest:1 тест,0 ошибок/пропусков; Android16/API36
  ARM64 WebView:7 API/UI проверок. Ввод токена iOS — нативная клавиатурная
  вставка; ранние неуспешные input fixtures сохранены.
- [x] Тот же HTTPS API проверен в Chromium/Firefox/WebKit с перезапуском сервера.
- [x] Перенести0.63 в основной каталог и проверить его build/full74/SDK23,
  исправленный промпт LLM и генерацию обоих мобильных проектов установленным
  SDK. Linux проходит full74/live16/source-free SDK23; все47 ревизий и таблицы
  корневого графа сохранены. Точные когорты исходников/документации и область
  результатов записаны в docs/evidence/toolchain-0.63.0.json.

Windows, физические мобильные/Intel-цели, Android NDK/native bindings и стабильный
мобильный ABI остаются обязательными последующими платформенными работами.

## Toolchain0.64 Windows core candidate

- Explicit GNU/UCRT64-bit PE/archive target, ABI/cache/notices and runtime rejection boundaries: verified cross-builds; root75/SDK23 and x64 Wine6 pass. Actual Windows OS/ARM64 execution remains unverified.
- Actual Windows OS/ARM64 execution, Windows-hosted compiler, debugger/profiler, platform I/O, GUI/plugin binding and signed distribution remain pending.

### Toolchain0.71 project architecture candidate

- [x] Implement separate versioned component/build metadata, strict field/capability validation, disjoint physical source ownership, checked direct import edges and cycle rejection.
- [x] Implement a read-only source-checked plan and selected/native/web artifact orchestration without synchronizing graph HEAD.
- [ ] Complete full regression, installed SDK and platform gates before root integration.
- [ ] Add actual component archive consumption, shared-library exports/ownership ABI, explicit full-static policy and resolved binary dependency reports.
- [ ] Add safe structured CPU tasks/channels and separate asynchronous I/O.
- [ ] Implement GPU/NPU adapters callable from NEX and verify actual device placement/fallback policy. CIX P1 OpenCL and Zhouyi probes have passed separately; probes alone do not complete NEX integration.

## Proposed C++/Python project porting tool (pending)

See [the design](docs/project-porting-design.md). No converter command is
implemented. Start with a defined typed subset, deterministic AST conversion,
explicit unsupported diagnostics, optional reviewed native bridges and original
vs NEX differential validation. LLM repairs require bounded context, compiler
checks and unchanged acceptance criteria. Complete the language/development
chain first; measure complete task cost rather than claim automatic full ports.
