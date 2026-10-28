# Task authority and lifetime contract (0.19)

This contract applies to public language0.19 checking and its compiled native,
independent AST and generated TypeScript task executors. Ordinary checking runs
the bounded analysis for task-effect programs before archival or execution.
Known violations are rejected early; unresolved flow retains mandatory runtime
guards. Complete static region typing remains pending. Explicit migration from
0.18 preserves its original source/history/IDs; see [task migration](task-migration.md).
The working108 private analysis was an earlier stage, with separately scoped
historical receipts; it did not add task types to public0.18.

## Ownership and transfers

Each `with_tasks` invocation creates a fresh logical child scope. A scope owns
its spawned tasks and channels. Copies are aliases of the same opaque resource;
immutable aggregates and closure captures do not extend an owner's lifetime.
Operations require an active owner from the current invocation and an accessible
ancestor scope. Foreign, ended and forged capabilities fail despite matching types.

At a transfer to scope D, every capability in the actual value graph must be
owned by D or an ancestor of D. Traverse record/enum fields, list/result payloads
and callable captures. Phantom type arguments do not manufacture capabilities,
but signatures containing authority cannot satisfy `wire` or cross foreign,
storage or browser worker boundaries. Files cannot cross task value boundaries.

Checked boundaries are callback captures, spawn captures, channel sends, task
completion, scope callback return and the outer invocation result. Task results
are validated before publication. `with_tasks` drains descendants and validates
its return against the parent; a resource from the ending scope cannot escape.
An outer invocation result cannot expose any task authority. A future does not
waive its payload checks. Borrowing an ancestor remains legal:

```nex
module ancestor_borrowing; // Language0.19.
fn main()->i64 !{task}{
  return with_tasks(1,fn(outer:task_scope)->i64 !{task}{
    let borrowed:task_scope=with_tasks(1,fn(inner:task_scope)->task_scope !{task}{
      return outer;
    });
    assert(borrowed==outer);
    return 42;
  });
}
```

Returning `inner` instead is an escape, also when hidden in a record, list,
result, returned callable, future or send to an outer channel. Aliases, generic
helpers and immutable snapshots retain actual origins. Selecting a safe field
does not transfer other unused fields of its containing aggregate.

## Early source diagnostics

`analyzeTaskLifetimes` consumes a checked Program. Ordinary0.19 checking invokes
it for programs with task effects, including unused concrete functions, before
opening a migration destination. Physical analysis/checking and archived bundle
rechecks retain the same lifetime diagnostics. No pass result removes runtime
validation or grants authority to a callable.

The development probe `nex_task_lifetime_probe SOURCE [ENTRY [BUDGET]]` remains a
separate diagnostic tool, not a public `nex` command. ENTRY analyzes that
invocation and known callees; omitting it separately analyzes concrete named
functions with unknown borrowed parameters. The pass changes no source, checked
nodes, canonical data, store or runtime values. Private raw018 conformance probes
can still check deliberately invalid transfers to exercise runtime rejection;
those programs cannot be archived as0.18 source tasks.

The pass follows fresh scope ancestry, direct/indirect calls, known callable
factories/captures, generic specializations, record/result/list projections,
patterns, assignments, branches and snapshot creation. Known escape diagnostics
use `E_TASK_LIFETIME` at the transfer site; known hidden files use `E_TASK_VALUE`.
Lexical shadowing and constant boolean short circuit are preserved. The pass
does not execute source code to determine control flow.

Recursive re-entry, unknown callable targets, unresolved projections, channel
receive payloads and loop widening leave dynamic obligations. Two abstract loop
iterations are followed by widening; they do not prove arbitrary loop behavior.
Exploration is limited to128 distinct active functions and joins to32 levels.
A shared default262144 step budget (selectable1..1048576) bounds traversal.
Exhaustion records a deferred obligation, never a complete static proof.

Reports use `nex.private-task-lifetime/1`, always `fully_static:false` and
`mandatory_runtime_guards:true`. Counts include invocations, regions, transfers,
proved transfers, dynamic obligations, opaque calls, widening and charged steps.
A successful report permits guarded execution, not removal of ownership checks.
Opaque transfers can still fail with runtime `E_TASK_SCOPE`/`E_TASK_VALUE`.

## Effects, failure and delivery

Every task intrinsic/indirect task call requires the explicit `task` effect.
`with_tasks`/`task_spawn` callbacks admit pure or task-only functions in
an available realm, granting no `io`, `fs`, `db` or `ffi` authority. The frontend
rejects known file signatures/captures; executors validate hidden graphs. An
effect annotation alone is not captured authority. Synchronous `parallel_map`
remains pure and resource-free, including hidden captures.

Scope exit drains children normally and aborts/drains on traps, cancellation and
result-error exits before publishing completion. Limits/cancellation remain
traps. Postfix `?` propagates only ordinary result errors at the current source
function boundary. Call order, short circuit, checked arithmetic, UTF-8 and
immutable snapshot semantics continue across suspension.

Native application tasks target macOS/Linux and source-only project linkage.
Their shared request defaults are1000000 charged steps and5000ms, with an
executor pool of16 and per-scope worker caps1..16 inherited by descendants.
Per-application CLI controls remain pending. The independent reference and
TypeScript schedulers are cooperative; neither is evidence of OS CPU overlap or
asynchronous IO. Scope/future/channel operations retain their checked limits
and cleanup on normal returns, result errors, checked traps and cancellation.

Early analysis and runtime comparison are separate evidence. Complete static
region inference, asynchronous IO, task debugger/profile attribution, binary
provider lifetime, task server/UI adapters, other native targets and current
installed SDK/platform delivery need further implementation/acceptance. Never
relabel an0.18 project; recheck an explicit source candidate and export a separate
0.19 project after preserving history and the matching old SDK.
