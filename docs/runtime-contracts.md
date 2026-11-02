# Executable pre/post contracts

Toolchain0.152 introduced explicit runtime source projection;0.155 extended it
to effectful functions and owned values, and0.156 added generic roots. The
ordinary0.159 CLI selects language0.28 and can compose detached contracts with
[inline source clauses](source-contracts.md). SDK0.156 retains language0.27.
The `nex.verification-contracts/1` format remains version-selected: generate the
actual source/revision/content pins with the selected compiler. Retained
contracts and histories keep their original language; use an explicit reviewed
migration for older graphs. Discover the selected scope with
`nex describe --field runtime_contracts --json` and read this guide with
`nex guide --kind runtime-contract --json`.

```sh
nex contract main.nex --symbol increment -o contracts.json
# Review requires/ensures and their exact snapshot pins.
nex contract main.nex --kind runtime --contracts contracts.json --directory guarded --json
cd guarded
nex check --json
nex test --json
nex test --target web --json
nex run --profile release --json
```

The destination must be new or empty. Generation checks the original complete
source bundle, semantic revision and qualified function content pins. It then
checks every predicate and the entire generated source bundle before exporting.
It preserves the selected original source and graph. The output is an ordinary
NEX project with **a distinct source revision** and ordinary build/cache keys.
Generation does not execute the application or prove its properties.

For each selected function, the generator inserts ordered `assert` calls for
`requires`, invokes the original body once through a private ordinary source function, inserts
ordered assertions for `ensures`, and returns the actual value. The body function keeps
the original realm, parameter names/types, declared effects and return boundary.
The original lexical signature is retained, including imported type aliases and
parenthesized callable result types. Its deterministic
fresh name avoids existing identifiers; the receipt records its qualified symbol
and content hash. It is not exported from its source module. Postconditions observe original immutable
parameters and the `returns` binding, after all normal body finalizers and return
replacement. Local shadows remain inside the body. A unit function has no return
binding; its fallthrough and explicit returns both reach the postconditions.

Internal direct calls, recursive calls and function references still select the
same guarded function. Preconditions run before the original body. A fatal body
failure or escaping source error does not run postconditions. Cancellation and
deadlines also skip them. A Result error is an ordinary completed result and
does run postconditions. A false predicate traps with **E_ASSERT**;
overflow/division faults while evaluating a predicate retain **E_OVERFLOW** /
**E_DIV_ZERO**. Source error handlers cannot catch these traps. Fatal outcomes skip
user finalizers while native owned-value cleanup remains mandatory. Checked
operators, left-to-right evaluation and short circuit use the ordinary language
implementations in the interpreter, MLIR/native backend and TypeScript backend.
The runtime needs no Z3 dependency.

This is an explicit transformation, not an invisible execution mode. Stack traces,
debug locations, function hashes and profiling refer to generated source, including
the private body function. It adds a static call and assertions; the body wrapper
does not require a closure. User-written predicates may create ordinary pure
closures and other values. The body retains its own ordinary allocations; normal call/step
budgets still apply. There is no promise of identical overhead or maximum accepted
recursion depth. Assertions remain enabled in release builds.

## Supported scope

Roots must be ordinary concrete or generic source functions. Signatures may use checked
strings, bytes, finite f64, aggregates, results, callables and genuine resource/task
values under their existing realm and lifetime rules. Declared effects are
preserved in both the wrapper and the private body. Tests, externs, derived generic instances,
trait signatures and compiler-generated closures are rejected. Selected bodies
retain ordinary checked source semantics, including loops, local aggregates,
internally handled source errors and `finally`. Recursion is permitted at runtime;
it remains outside the current scalar proof engine.

Pre/post predicates are ordinary source expressions, checked in the selected
function's module with **an empty effect set**. They may observe immutable
parameters and the fresh postcondition result binding, use fields/indexing,
construct values, match enums/results, call pure helpers and pure callbacks, and
use pure closures. Imported visibility and exact callable realm/effect rules still
apply. Body locals are out of scope. Root IO/fs/ffi/task/throw effects do not
authorize predicate effects, including in a statically checked lazy branch.
Direct result propagation is rejected because a predicate cannot return from
the selected function; a pure helper may handle its own Result normally.

Predicates must type check to bool. Their checked lexical tokens are emitted
without comments, so input comments cannot swallow generated assertions. Strings
retain their literal escapes. Ordinary checked bounds, UTF-8, arithmetic and
ownership behavior applies. Pure calls may trap, allocate or fail to terminate;
they are not mathematical proofs or guaranteed zero-cost observations.
The existing bounds
remain: at most 64 functions, 64 clauses per list and 4096 UTF-8 bytes per clause;
CLI input is bounded to 1 MiB. Ordinary parser/source limits apply too.

[The checked loop example](../examples/runtime-loop-contracts/README.md) includes
portable sources, pinned contracts and proof/runtime commands.
The [value/effect example](../examples/runtime-value-contracts/README.md) includes
reviewed pins for a structure/list function with IO and portable runtime tests.

Selected while annotations now execute their complete invariant/ranking rule.
Use the exact line/column emitted by `nex contract`. Each selected loop requires
one or more bool invariants and a nonempty i64 `decreases` expression. These
expressions may use visible scalar parameters/locals, including enclosing match
and typed-catch bindings; a loop body's own locals are out of scope. Other
loops remain unchanged. Missing/incomplete rules are rejected before output.

Invariants run at entry, even if the condition is initially false, and after each
normally completed iteration, before the next condition evaluation. A ranking is
evaluated once after a true condition, must be nonnegative, and is saved before
the body. On the next head visit the new ranking must be strictly smaller; this
includes the final back edge whose next condition is false. A negative final
ranking is allowed if the loop then exits. Initial false conditions do not
execute the ranking. Predicate arithmetic and boolean short circuit remain
checked; undefined expressions retain E_OVERFLOW/E_DIV_ZERO rather than becoming
E_ASSERT. Checks run in annotation order, before the strict-decrease check.

Early return or an escaping source error leaves the loop without a back edge;
there is no trailing check in an unreachable body. Ordinary finally behavior
still applies. An error handled inside the iteration permits its normal back
edge; a finalizer's mutations are observed there. Fatal contract traps skip user
handlers/finalizers while runtime-owned cleanup remains mandatory.

The projection adds two fresh scalar loop locals and a private pure head helper
with only the scalar bindings used by the rule. It introduces no closure. The
original condition executes once per head visit, after the invariant/back-edge
checks, and the original body/return boundaries remain in the private body
function. This adds ordinary checked source steps and calls; step/call budgets,
source locations and profiles include them. There is no zero-overhead promise.
Loop annotations still use only visible i64/bool bindings and the scalar
expression subset; these compose with effectful/aggregate and generic roots.
Source-level contract syntax remains pending. The separate Z3
verifier retains its narrower scalar proof subset and limits.

## Generic roots (development toolchain 0.156)

Select the source template, for example `library::identity`, rather than a
derived `library::identity<i64>` instance. The original generic signature,
bounds, constructor arities, realm and effects are retained in the wrapper and
the private body. The wrapper passes every type parameter explicitly, including
phantom parameters that cannot be inferred from value arguments.

Predicates are checked parametrically against the declared bounds, even if the
template is unused or all current callers select i64. An unconstrained `T`
therefore cannot acquire arithmetic from the current set of callers. Explicit
type annotations and calls in predicates can refer to the template's parameters,
including constructor parameters and trait-associated projections. The ordinary
purity, visibility, ownership and generic expansion limits still apply.

The projected source template enforces its checks for existing specializations
and for specializations added by later ordinary source edits. This is a runtime
property of the generated template; a later edit still changes its checked
project revision. The receipt pins the exact generated snapshot and does not
approve that later revision. Direct instance replacement remains prohibited.

Generic projections use candidate/session `/4`, with
`generic_root_scope: "source_template_all_instantiations"`. Each function records
ordered `type_parameters` containing original qualified names, constructor
arities and bounds; concrete roots in a mixed projection record an empty array.
At least one selected root is generic. Receipt/session `/1`, `/2` and `/3`
remain unchanged. Generic runtime checking adds no source keywords, runtime ABI,
language migration or new Z3 proof support.

## Evidence and version control

Pre/post-only output retains `nex.runtime-contract-session/1` and
`nex.runtime-contract-candidate/1` with `loop_checks: false`. When any loop is
selected, output uses session/candidate `/2`, `loop_checks: true` and per-function
loop coverage (original coordinates, counts and private helper content hashes).
The CLI includes the generated revision and an absolute receipt path.
These legacy shapes remain available for scalar roots/predicates. Effectful or
non-scalar roots, or predicates outside the original scalar subset, use
session/candidate `/3` with `predicate_scope: "pure_source_expressions"`.
Each `/3` function records its original checked realm, effects, parameter/result
types and loop coverage (possibly empty); `loop_checks` states whether any loops
were selected. These six legacy shapes and the two generic shapes are defined
by the linked schema.

The destination contains `nex.json`, a matching `nex.lock.json`, exported sources
and `runtime-contracts.receipt.json` ([receipt schema](../llm/runtime-contracts.schema.json)). `intent_hash` retains the normalized pre/post acceptance intent; `contract_hash`
pins the complete document, including loop coordinates, invariants and rankings.
The receipt records origin and generated
revisions/source hashes, exact contract and intent hashes, per-function content
hashes/check counts, compiler identity and both complete source bundles. Its
`proof_performed: false` is explicit. Loop checks are reported separately. It is reproducibility
evidence, not an authenticated certificate and not a substitute for a separate
`nex verify` run. Original contract pins do not automatically certify the generated
revision; regenerate/review proof metadata when proving generated code. Ordinary
nonrecursive scalar body calls remain inside the current verifier subset. Its
other limits still apply; loops in body helpers need separately reviewed helper
annotations at their generated coordinates.

Commit original sources, reviewed contracts and tests. When distributing the
guarded project, commit its generated sources, manifest/lock and receipt together,
or regenerate them from a pinned compiler and compare recorded hashes. A receipt
is data: executing edited sources does not automatically validate it. Generation exports the selected source closure and a source-project manifest.
It does not copy component architecture manifests or physical host grants. It
does not copy original Git/SQLite history; the original project retains it.
Use normal [graph snapshots](snapshots.md) when transferring that history.

The historical 0.151.1 SDK predates this command. The
[0.152.1 delivery record](releases/0.152.1.json) covers matching full Mac regression,
moved/restored SDK delivery and 15 runtime-contract scenarios in each SDK.
Native Windows/CUDA and other-platform acceptance remain separate.

Toolchain0.153 develops loop projection. Matching full regression, SDK and platform
acceptance for that extension remain separate from the accepted0.152.1 SDK.

The [0.156 Mac delivery](releases/0.156.0.json) records full288 regression,
40 maintained phases plus15 scalar,15 loop,14 value,9 generic and4 debugger-protocol
cases in each moved/restored SDK. The published archive is the exact payload used
by both workflows. OpenCL hardware and source-memory profiles have a separate
[scoped receipt](evidence/macos-opencl-0.156.0.json). Current Windows/Linux,
source contract syntax, broader proof models and other PLAN work remain open.
