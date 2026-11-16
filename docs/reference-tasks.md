---
status: development
applies_to: "toolchain 0.269.0; source0.30; private reference/native task execution"
owner: repository
---

# References in structured tasks: reference/native development

The source-build C++ entry `evaluateManagedTaskReferencePrototype` composes
ordinary checked source0.30 with the independent AST task coordinator and one
owned, thread-affine cell heap. It is the independent oracle for the native
development path and remaining TypeScript integration. Discover
`managed_references.source030_development.reference_tasks`.
**`public_source_enabled` remains false:** ordinary `eval`, native `build` and
TypeScript emission retain `E_CELL_CONCURRENCY` for reference/task execution.
The normal reference-free task and sequential cell paths remain available.

Source0.30 checking now accepts a task callback's `state` effect when its caller
also declares `state`. Server file/foreign callbacks retain complete caller
authorization. Pure callbacks can transport cell identity without claiming a
mutation effect. This adds no production, reserved name or canonical format;
existing source versions, graph history, task ABI7 and public C ABI1 remain
unchanged. A successful check alone does not establish backend support.

## Owned execution context

```cpp
auto program = parseVersioned(source, path, SourceLanguage::References030);
check(program);
auto result = evaluateManagedTaskReferencePrototype(program);
// result.task: value/output, logical work and task statistics.
// result.beforeClose / afterClose: owned heap teardown observations.
```

The private entry requires checked source0.30, no entry parameters and a unit
or immutable wire result. Related AST frames, callbacks, suspended locals,
future results, channels and typed error packets share cell identity. Ordinary
values remain snapshots. Collection observes all live frame/channel/error
owners. Source errors and yielding `finally` keep the original control rules.
Cancellation and fatal traps skip user finalizers while owned cleanup runs.

The coordinator executes source on one thread; physical IO workers retain
their existing raw-data/lease protocol and never use the cell heap. This is
not shared-memory CPU execution. The snapshot graph limits and heap limits
remain independent; collection is not separately step-metered or preemptive.

After source work joins, the heap closes before root resource retirement waits
for physical cleanup. Fatal, deadlock, control and observer-failure exits also
close it. A diagnostic observer may retain an inert cell identity after close;
it must not mutate values or reenter execution. An uncaught source error becomes
a copied host diagnostic, so no live reference packet escapes the owned entry.

## Resource ownership

Snapshot admission validates a cell's heap/thread and walks its current payload
under the existing task-region transfer rules. Cells do not renew file/foreign
authority. A child-created file returned through a future inside a cell receives
the normal ownership transfer. Publishing that file into another cell and
returning an integer does not transfer it; access after its owner ends receives
`E_RESOURCE_SCOPE`. Retained wrappers and cycles still retire physically.
Task scopes, futures and channels remain forbidden inside cell payloads.

## Evidence and remaining work

The [focused0.268 receipt](evidence/reference-tasks-0.268.0-2026-11-16.json)
records the exact compiler, source/resources, core/affected results and relocated
normal installation. It does not qualify a portable SDK.

`tests/reference_tasks.cpp` contains21 scenarios: aliases through waits/channels,
closure captures, retained snapshots and cycles, typed errors/yielding finally,
source contracts, cancellation/limits/deadlock, invalid entries and checked
effects, unexpected observer failures and real file ownership/descriptor cleanup.
The no-Node `reference_tasks_development` group is the17th core group.
`reference_tasks_boundaries` checks ordinary backend rejection and retained
reference/native/TypeScript execution for separate cells and reference-free tasks.

## Native owner-thread continuations

The [focused0.269 receipt](evidence/native-reference-tasks-0.269.0-2026-11-16.json)
records the final source/compiler cohort and its actual checks.

Toolchain0.269's source-build `emitManagedReferenceTasksDevelopmentNative` lowers
checked030 source through verified TaskIR, MLIR and LLVM into a standalone
unit/i64 application. It uses private descriptor ABI`0x4e45585400003001`; published
task ABI7 and all old cohorts retain their identity. The runtime must explicitly
link `NEX_MANAGED_TASKS`. Discover `source030_development.native_tasks`.

An explicit `TaskOwnerExecution` coordinator drives source continuations on the
enclosing request's owner thread. The ordinary worker-pool constructor keeps its
physical CPU workers and rejects cells. Native task frames, future/channel values
and typed errors retain their owned values across parking. A resume borrows the
request's heap while owning separate temporary handles and cancellation state;
unwinding restores the caller's request and resource-binding context. Ending a
joined group does not close its caller's still-live heap.

Retired source frames trigger collection outside scheduler locks. Ordinary yields
do not trigger a whole-heap scan. Physical IO operations keep their separate raw
completion/lease protocol and never acquire cells. Logical scope limits do not
promise parallel mutable source execution. `parallel_map` remains rejected.

The native comparison consumes source and observations emitted by the actual
21-scenario AST probe: nine accepted programs and four runtime failures, each
compiled and executed at O0/O2. These cover identity, snapshots, source errors,
yielding finally, cancellation, budget exhaustion, real file return promotion,
unpromoted file rejection and fatal file/cell-cycle cleanup. A separate seven-case
runtime probe checks owner-thread identity, caller state after joining, typed
packet identity, worker/cohort/thread rejection, budget/cancellation and frame
retirement. Those seven cases also run in the existing core reference-task group.

TypeScript generators, ordinary CLI promotion, persistent application/UI
contexts, source debugging/profiling, host/library/task contexts, parallel
transfer and complete SDK/platform qualification remain open. These private
entries do not qualify an entire SDK or release.
