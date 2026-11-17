---
status: current
applies_to: "language 0.28; language 0.29; language 0.30; toolchain 0.279.0"
owner: repository
---

# Implementation sequence: items 1–6

The0.279 SDK workflow adds a required [installed030 phase](sdk-reference030.md)
with live-debug/profile/library delivery, native host sessions and persistent
browser consumption. Focused normal-install preparation has passed; matching
full source/distribution/archive acceptance remains next.

Toolchain0.279 adds [native reference task profiling](reference-task-profiling.md)
for standalone030 and source-backed static/shared/mixed provider builds. ABI8
profile record19/plan19 preserve source invocation, component/image attribution
and owned cyclic-state cleanup. HTTP/profile integration and complete current
SDK/platform delivery remain separate.

Toolchain0.278 adds [reference provider debugging](reference-provider-debugging.md):
checked ABI8 state and source errors cross static/fixed-shared/mixed images with
logical stacks, copied cell inspection and captured/relocated replay. HTTP/debug
profile integration and full SDK/platform delivery remain separate.

Toolchain0.277 adds [source-only native reference task debugging](reference-task-debugging.md)
with live cell inspection, read-only DAP expansion and version-aware scalar
watches. Provider/HTTP/profile integration, cell watch reconstruction and full
SDK/platform qualification remain open.

Toolchain0.276 adds [persistent native task sessions](native-task-sessions.md)
for matching-runtime C++ hosts: checked030 exports retain application state and
returned file/error owners across serialized calls, with fresh execution controls
per call. Native UI controllers, parallel cell transfer, logical debugging/profile
and complete SDK/platform qualification remain open.

User authorization: 2026-11-15. Continue the language, library, backends,
developer tools and platform delivery. The original [PLAN](../PLAN.md) remains
the full objective. Studio, model studies and project conversion follow this
sequence; Java conversion has priority over Python, with C++ retained afterward.
Additional sanitizer/fuzz/security work remains explicitly deferred. Subsequent
user direction puts [language migration prerequisites](migration-readiness.md)
first; converter implementation is deferred until these foundations are ready.

## Evidence baseline

The starting checkout is main `c15fefae`, toolchain 0.246.1. Compiler default
language is 0.28; explicit 0.29 projects support partial type lambdas and
higher-order constructor kinds. New projects select 0.29 explicitly.
The [0.246.1 delivery](releases/0.246.1.json) records 351 macOS source groups and
41 phases each for moved/restored macOS SDKs. The Linux integrated test step
passed; artifact retention was corrected and checked separately. These receipts
retain their exact source/platform scopes and do not qualify later changes.
The old implementation worktree has no commits absent from current main.

## Executable backlog

User direction, 2026-11-16: prioritize a compact, predictable language for LLM
application development, rich ordinary libraries and gradual project migration.
The immediate sequence is:

1. Complete reference/object state across structured tasks, cancellation and
   persistent application/UI contexts, with matching backend behavior.
2. Complete practical library gaps, including efficient hash containers,
   queues/heaps and adapters needed by an actual application.
3. Improve bounded LLM discovery, examples and diagnostics using observed
   failures; measure the complete cost of accepted work on the current compiler.
4. Qualify one committed source cohort through SDK installation, relocation,
   archive restoration and matching macOS/Linux/Windows development tools.
5. Exercise a coherent application with a server, browser, SQLite, files and a
   background task; then manually port a bounded part of a real Java project
   before implementing converters.

This orders the work; it does not mark the original PLAN complete or discard
its remaining requirements. Full Java/Python runtime emulation, reflection and
metaclass compatibility are later, project-driven requirements. Exact source
behavior remains mandatory for each advertised migrated subset.

Toolchain0.275 adds [native030 task-provider images](reference-task-providers.md)
with one application-owned heap and propagated ABI8 across connected static,
fixed shared and mixed components. Native UI lifecycle, reference task
debug/profile, full delivery and the remaining application/LLM work stay open.

Toolchain0.274 adds [persistent work containers](sequence-containers.md):
indexed/deque AVL sequences, FIFO queues, linked stacks and leftist heaps. They
retain old snapshots and compose with030 cells/tasks/errors. Existing flat-list
layouts stay supported; their copy-cost descriptions are corrected. Whole source/
SDK/platform acceptance, remaining application APIs and the original PLAN remain
required.

Toolchain0.273 adds [persistent hash map/set](hash-containers.md), stable hash
helpers and explicit callback/ordering/collision contracts as ordinary source
libraries. Efficient queues/deques/heaps, native task-provider lifetimes,
debug/profile and full SDK/platform delivery remain required.

Toolchain0.272 adds [persistent030 browser application state](persistent-ui.md),
serialized task-driven UI/command invocations, copied wire views/events and owned
close/abort/failure cleanup. Native persistent provider lifetimes, parallel
transfer, debugger/profile and full SDK/platform delivery remain required.

Toolchain0.271 enables ordinary030 owner-thread reference tasks in evaluation,
native debug/release applications and HTTP requests, async TypeScript host
exports and CLI tests. ABI8/map4 preserve ABI7, private descriptors/maps and
source graph history. Captured replay and immutable host boundaries join focused
qualification. Persistent application/UI contexts, task-library lifetimes,
parallel transfer, debug/profile and full SDK/platform delivery remain required;
see [the task contract](reference-tasks.md).

Toolchain0.270 adds the third private engine: generated TypeScript on the existing
cooperative scheduler, with per-job roots in one invocation heap. Independent
AST comparisons and explicit host-control checks cover suspended captures,
channel/future/error owners, cancellation and unexpected host failures. Ordinary
CLI integration, persistent application/UI contexts and full delivery gates remain
next. See [the three-engine contract](reference-tasks.md).

Toolchain0.267 adds a separate internal [IEEE numeric kernel](ieee-numeric.md)
for binary32/binary64 bits, primitive arithmetic/comparisons and Java casts.
It preserves signed zero and special values while ordinary NEX f64 stays finite.
The fixed31,748-observation JDK/mathematical corpus qualifies its stated runtime
scope. Source types, all backend/wire/debugger/ABI bindings, explicit versioned
migration and complete SDK/platform qualification remain open.

Toolchain0.268 starts the first practical block with a private
[reference-task context](reference-tasks.md). Checked030 stateful callbacks,
suspended frames, future/channel/error transfers and genuine file owners share
one cooperative heap. The21-scenario source-build probe covers cleanup/control
and ownership, including unexpected host failures. It is the17th core group.
Ordinary reference/native/TypeScript execution of cells with tasks remains
`E_CELL_CONCURRENCY`; native/TypeScript/app/UI integration is the next work.

Toolchain0.269 adds a matching private [native task emitter](reference-tasks.md#native-owner-thread-continuations)
using verified TaskIR/MLIR/LLVM and explicit owner-thread execution. It preserves
the enclosing request heap across resumes while IO retains its physical
completion protocol. The independent AST source corpus supplies accepted and
fatal/resource cases for O0/O2 execution. Ordinary CLI/TypeScript promotion,
persistent app/UI contexts, debugger/profile and full SDK/platform acceptance
remain next; the private descriptor cohort does not change published task ABI7.

Toolchain0.266 adds an explicit [Java long domain](java-long.md), including
wrapping64 arithmetic, bits/shifts, narrowing/sign extension and typed division
errors. The790-vector JDK fixture covers its supported primitive operations;
machine-type specialization, IEEE values, class/nullability, library compatibility
and Python protocols remain open. No converter or source grammar is introduced.

Toolchain0.265 adds ordinary030 CLI selection, guarded migration preserving
the namespace and old rows, static project components, API source projection,
version-aware formatting/editor metadata and source-deleted task replay.
New projects select0.30. The compiler fallback0.28 and retained028/029 project
semantics are unchanged. Reference task transfer, persistent UI state, class/
nullability and Python dynamic/numeric contracts remain open, together with full
source/debugger/profile/platform/portable-SDK acceptance.

The0.264 [native HTTP reference contexts](reference-http.md) bind sequential030
handlers to independent request heaps, compatible static libraries and copied
uncaught diagnostics. Ordinary030 CLI publication, reference task transfer,
persistent UI state, foreign-resource HTTP acceptance and full debugger/profile/
platform/portable-SDK gates remain open.

The0.263 source030 code-only [native reference libraries](reference-library-abi.md)
share live aliases, returned captures and typed error packets in one enclosing
host/application context. This is a sequential matching-runtime C++ API step;
ordinary030 CLI publication, HTTP/task transfer, arbitrary image unload and
portable SDK/platform acceptance remain open.

The0.262 version-selected030 C++ APIs add canonical reference archives, normal
backend entry points and guarded retained029 migration. Ordinary CLI publication,
reference library/HTTP/task contexts, persistent UI state and matching full
SDK/platform delivery remain open. See [source030 development](references030.md).

The0.261 private TypeScript emitter adds checked ordinary host-value entries:
immutable arguments/results, separate per-call heaps, independent diagnostics
and synchronous nested host calls. This prepares an entry boundary; it does not
promote references or implement persistent UI state, worker transfer or ordinary
graph/project migration. See [the contract](managed-reference-value-exports.md).

The 0.254 runtime block added iterative sequential value retirement for ordinary
deep values and snapshots released after heap close. The 0.255
[atomic owner](value-owners.md) removes its check-then-drop race and carries
retirement across module boundaries. Public reference migration and the shared
mutable memory model remain open; the private candidate's thread/task
restrictions are unchanged.

The0.256 private frontend scopes independent type binders and trait Self before
checking, composing cells with 0.29 kinds, projections and static methods. Its
public version/history migration and module/host lifetime work remain next.

The0.257 private module loader uses the shared import/visibility/type binder and
one application heap across source units, with reference/native/TypeScript
agreement. Separate DLL/host lifetime, public version/history migration and the
remaining object/numeric/class/concurrency semantics stay open.

The0.258 native request context owns its heap independently of an enclosing
application. A private generated entry preserves source errors and scalar
status across repeated calls, with request polling and owner-thread cleanup.
Public source/HTTP integration, owned payloads, task transfer and DLL/reference
returns remain open; see [the request contract](managed-reference-requests.md).

The0.259 private candidate also accepts sequential server fs/ffi calls alongside
cells. Ordinary locals, closures and error packets retain existing owned-resource
cleanup; cells still reject owned payloads. See [resource coexistence](managed-reference-resources.md).

The0.260 private heap/checker accepts genuine owned payloads in cells, with
independent resource authority, retained snapshots, visible cycle cleanup and
callback reentry/closed-owner guards. [Owned-payload semantics](managed-reference-owned-payloads.md)
keep source finalizers, opaque host cycles and public migration explicit.

| Item | Implemented baseline | Remaining result | Acceptance |
|---|---|---|---|
| 1. Reconcile scope | Versioned source, descriptor, specification and receipts exist; older priority documents contain stale pending claims | Keep this current dependency/acceptance ledger alongside the historical plan; classify actual implementation and qualification separately | Every completion claim links matching source/runtime evidence; original requirements remain visible |
| 2. Language core | Generics, traits, associated types, recursive values, 0.29 constructor kinds, inferred effect parameters, typed errors/finally, structured tasks and owned resources | Remaining higher-rank effects/handlers, type inference and ownership/concurrency requirements; correct specification/grammar drift | Parametric and rejected-program checks; reference/native Debug/Release/TypeScript agreement; explicit history-preserving migration for language changes |
| 3. Standard library | Linear bulk builders; existing list-backed containers; persistent AVL and hash map/set | Remaining application APIs and matching complete SDK/platform qualification for the tree/hash/work-container families | Correct ordering/equivalence, retained old values, structural invariants, complexity evidence, backend agreement, installed library discovery/pins |
| 4. Backends/devices | Native CPU, structured tasks, scalar i64/f64 Wasm, bounded checked Metal/CUDA/OpenCL emission, versioned hardware providers | Wider Wasm/type coverage, general device execution, transfers/cancellation, GPU operation attribution and Apple NPU integration | Actual device execution with matching source/provider identities; declared supported operations and explicit unsupported/fallback results |
| 5. Developer tools | LSP navigation/completion/format/rename, identifier/field fixes, source debugging/profiling/core capsules | Remaining diagnostic edits and LSP actions, optimized machine/source attribution, async/device debugging and profiling | Real editor/debugger/profiler behavior; correct source/graph/image attribution; retained diagnostics and original graph history |
| 6. Platforms/delivery | Recorded macOS SDK; cross-platform source builds and native/web application packaging in their recorded scopes | Matching Windows/Linux SDKs, remaining static/DLL policies, complete dependency reports, mobile/native API lifecycle and delivery | Same-source build/install/move/archive/restore cohorts per platform; actual applications, resource cleanup and required external signing identities |

## First functional block

0.247 adds [persistent balanced-tree map/set](ordered-containers.md) source
modules. Existing insertion-ordered list containers keep their API. This uses
existing finite recursive types, immutable values and callable types; it adds
no source syntax or language migration. Recursive value prototypes passed
reference/native Release/executed strict TypeScript before library integration.
The deterministic container oracle covers ordering, updates/removals, retained
versions, comparator equivalence and representation invariants; acceptance is
recorded separately from the prototype. Hash containers and the other rows
stay open. Grammar drift for already implemented trailing defaults, higher-order
constructor kinds and explicit effect witnesses is corrected against the parser.

Existing list-backed map updates/enumeration and set removal now use the linear
bulk builder. This removes quadratic repeated-prefix copying while preserving
insertion order and the behavior of manually supplied duplicate entries. The
list-backed set algebra still has its documented quadratic bounds; ordered set
algebra is a separate comparator-based API.

[Focused 0.247 acceptance](evidence/containers-0.247.0-2026-11-15.json) records
12 core groups, five affected CTest groups, the public catalogue and actual
local install/relocation consumption. Full source/platform/portable SDK gates
remain at the later integration milestone.

For Java/Python migration, record the source semantic differences before adding
compatibility operations. Preserve NEX checked arithmetic, immutable aggregates
and scalar-string semantics. A compatibility runtime must be explicit; keeping
the original interpreter/JVM is a transitional boundary, not a completed port.
See the [conversion design](project-porting-design.md).

## Work and verification cadence

The 0.248 language-readiness block supplies explicit Java int semantics and
correct 0.29 diagnostic/archived-graph language selection. Converter code remains
deferred. General typed mutable references/identity, object dispatch, machine
integer/IEEE domains and Python dynamic/big-integer support remain open in the
[prerequisite matrix](migration-readiness.md).

The 0.249 [managed-reference kernel](managed-references-design.md) supplies
private C++ cell identity, snapshot-preserving writes, root/cycle collection,
deep registry teardown and heap/thread/transfer rejection. It enables no source
reference type or state effect. The next integration must cover checked types,
an explicit history-preserving version migration, all source backends and whole
execution-context ownership across calls/returns before public promotion.
[Focused kernel evidence](evidence/managed-references-runtime-0.249.0-2026-11-15.json)
records 19 C++ scenarios, 12 core groups and three affected groups. Its scope
does not include source-reference execution or a matching complete SDK.

The 0.250 [private checked candidate](managed-references-prototype.md) adds
`cell<T>`, explicit `state` effects, generic/closure behavior and sequential
reference execution in one context. Its distinct internal identity is not an
ordinary CLI/project version and cannot be archived. Native/TypeScript lowering,
cross-module/host ownership and history-preserving public migration remain next.
[Focused source-candidate evidence](evidence/managed-reference-source-0.250.0-2026-11-15.json)
records its reference behavior and rejection gates. Core now includes this
no-Node probe (13 groups); eight additional affected groups pass. The earlier
[0.249 hosted core](evidence/core-ci-0.249.0-2026-11-15.json) passed on macOS/Linux
with the previous 12-group scope and does not qualify the new candidate.

The 0.251 [native candidate](managed-reference-native-prototype.md) shares one
application-owned heap across generated source calls. Its
[focused receipt](evidence/managed-reference-native-0.251.0-2026-11-16.json)
records 26 reference/O0/O2 comparisons through matching host images and separate
executables, including cleanup and reported source locations. Core now has
14 no-Node groups, adding context lifecycle/reentry checks. Public native
project/module ownership, public TypeScript integration, migration and complete SDK qualification
remain open. [Hosted 0.250 core](evidence/core-ci-0.250.0-2026-11-16.json) passed
on macOS/Linux at its own 13-group source commit.

The 0.252 [TypeScript heap kernel](managed-reference-typescript-heap.md) adds
explicit root frames, operand/builder/return roots, allocation identities and
bounded collection/admission behavior. It is compared step-by-step with the
actual C++ kernel, including deep graphs and distinct/shared string nodes.
At that milestone the private candidate still reported `typescript: false`. The
[focused kernel receipt](evidence/managed-heap-typescript-0.252.0-2026-11-16.json)
keeps these results separate from source-backend/SDK acceptance.
[Corrected 0.251 hosted core](evidence/core-ci-0.251.0-corrected-2026-11-16.json)
passed macOS/Linux after bounded dependency-download retries and clearer failure
logging; the original network failure remains recorded.

The 0.253 [private TypeScript source candidate](managed-reference-typescript-prototype.md)
adds the boxed facade, expression/lexical/builder roots and ownership of pending
return/source-error completions. A shared source corpus feeds reference,
native O0/O2 and strict executed TypeScript; host results preserve decimal i64
and immutable snapshots. [Focused acceptance](evidence/managed-reference-typescript-0.253.0-2026-11-16.json)
records the actual comparisons, exact heap accounting, API rejection gates and
the preceding fixture failures. Ordinary languages/graph histories remain
unchanged; public migration, entry/module/host lifetimes and matching complete
SDK/platform qualification remain next.

[0.248 focused evidence](evidence/java-int32-language-0.248.0-2026-11-15.json)
records the numerical and selected-language graph/diagnostic block. The earlier
[0.247 hosted core CI](evidence/core-ci-0.247.0-2026-11-15.json) and
[0.248 hosted core CI](evidence/core-ci-0.248.0-2026-11-15.json) passed on macOS
and Linux at their exact source commits; neither qualifies the later kernel.

Implement complete functional blocks, build with `cmake --build build -j 4`,
then execute affected semantic/backend/descriptor tests. Do not rerun already
qualified unrelated suites after documentation or evidence-only changes.
Run unfiltered CTest and coherent platform/SDK suites at integration milestones.
Preserve original failures. A green narrow check never closes a broader row.
The published 0.246.1 SDK remains immutable while later source work continues.
