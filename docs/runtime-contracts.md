# Executable scalar pre/post contracts

Development toolchain 0.152 adds an explicit source projection. It uses the
existing `nex.verification-contracts/1` format and language 0.27. Discover it with
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
the original realm, parameter names/types and return boundary. Its deterministic
fresh name avoids existing identifiers; the receipt records its qualified symbol
and content hash. It is not exported from its source module. Postconditions observe original immutable
parameters and the `returns` binding, after all normal body finalizers and return
replacement. Local shadows remain inside the body. A unit function has no return
binding; its fallthrough and explicit returns both reach the postconditions.

Internal direct calls, recursive calls and function references still select the
same guarded function. Preconditions run before the original body. A fatal body
failure does not run postconditions. A false predicate traps with **E_ASSERT**;
overflow/division faults while evaluating a predicate retain **E_OVERFLOW** /
**E_DIV_ZERO**. Source error handlers cannot catch these traps. Fatal outcomes skip
user finalizers while native owned-value cleanup remains mandatory. Checked
operators, left-to-right evaluation and short circuit use the ordinary language
implementations in the interpreter, MLIR/native backend and TypeScript backend.
The runtime needs no Z3 dependency.

This is an explicit transformation, not an invisible execution mode. Stack traces,
debug locations, function hashes and profiling refer to generated source, including
the private body function. It adds a static call and assertions; no closure is
introduced by the projection. The body retains its own ordinary allocations; normal call/step
budgets still apply. There is no promise of identical overhead or maximum accepted
recursion depth. Assertions remain enabled in release builds.

## Supported scope

Roots must be ordinary concrete pure source functions with i64/bool parameters
and an i64/bool/unit result. No effects, tests, externs, generic roots/instances,
trait signatures or compiler-generated closures can be selected. Their bodies
retain ordinary checked source semantics, including loops, local aggregates,
internally handled source errors and `finally`. Recursion is permitted at runtime;
it remains outside the current scalar proof engine.

Predicates support i64/bool literals, parameter names, the fresh postcondition
result name, unary `-`/`!`, checked arithmetic, comparisons, equality and `&&`/`||`.
Calls, heap values, fields/indexing and body locals are rejected. They must type
check to bool. Accepted expressions are emitted from their parsed scalar trees,
so comments in input cannot swallow generated assertions. The existing bounds
remain: at most 64 functions, 64 clauses per list and 4096 UTF-8 bytes per clause;
CLI input is bounded to 1 MiB. Ordinary parser/source limits apply too.

[The checked loop example](../examples/runtime-loop-contracts/README.md) includes
portable sources, pinned contracts and proof/runtime commands.

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
Effectful/aggregate root contracts and source-level contract syntax remain pending;
the separate Z3 verifier and its proof limits are unchanged.

## Evidence and version control

Pre/post-only output retains `nex.runtime-contract-session/1` and
`nex.runtime-contract-candidate/1` with `loop_checks: false`. When any loop is
selected, output uses session/candidate `/2`, `loop_checks: true` and per-function
loop coverage (original coordinates, counts and private helper content hashes).
The CLI includes the generated revision and an absolute receipt path.
All four shapes are defined by the linked schema.

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
