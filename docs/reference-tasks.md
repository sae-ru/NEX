---
status: development
applies_to: "toolchain 0.268.0; source0.30; private reference-task execution"
owner: repository
---

# References in structured tasks: reference-engine development

The source-build C++ entry `evaluateManagedTaskReferencePrototype` composes
ordinary checked source0.30 with the independent AST task coordinator and one
owned, thread-affine cell heap. It is a development oracle for the remaining
native/TypeScript integration. Discover
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

Native task frames/executors, TypeScript generators, persistent application/UI
contexts, source debugging/profiling, host/library/task contexts, parallel
transfer and complete SDK/platform qualification remain open. The private AST
entry neither enables those paths nor qualifies an entire SDK or release.
