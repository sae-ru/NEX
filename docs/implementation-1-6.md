---
status: current
applies_to: "language 0.28; toolchain 0.254.0"
owner: repository
---

# Implementation sequence: items 1–6

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

The 0.254 runtime block adds [iterative sequential value retirement](value-retirement.md)
for ordinary deep values and snapshots released after heap close. Public reference
migration and a universal concurrent-release stack bound remain open; the private
candidate's thread/task restrictions are unchanged.

| Item | Implemented baseline | Remaining result | Acceptance |
|---|---|---|---|
| 1. Reconcile scope | Versioned source, descriptor, specification and receipts exist; older priority documents contain stale pending claims | Keep this current dependency/acceptance ledger alongside the historical plan; classify actual implementation and qualification separately | Every completion claim links matching source/runtime evidence; original requirements remain visible |
| 2. Language core | Generics, traits, associated types, recursive values, 0.29 constructor kinds, inferred effect parameters, typed errors/finally, structured tasks and owned resources | Remaining higher-rank effects/handlers, type inference and ownership/concurrency requirements; correct specification/grammar drift | Parametric and rejected-program checks; reference/native Debug/Release/TypeScript agreement; explicit history-preserving migration for language changes |
| 3. Standard library | Linear bulk builders; existing list-backed containers; 0.247 source adds persistent AVL map/set | Hash containers, efficient queue/heap structures and remaining application APIs; matching AVL SDK/platform qualification | Correct ordering/equivalence, retained old values, structural invariants, complexity evidence, backend agreement, installed library discovery/pins |
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
