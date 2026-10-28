Private emitted checkpoints, native catalog and owning-continuation pause/watch/
resume now have separate conformance. See source-exception-task-debug.md. Full
LLDB/DAP/all-stop/IDE and archived CLI acceptance remain pending.

# Private task control and native profiling

Toolchain0.135.17 extends the compiler-private0.25-prototype task experiment.
Public language stays0.24 and private descriptor ABI0x4e45585400002501 stays
distinct from published ABI3/4/5. Source syntax and normal public behavior do not
change. This is functional runtime/compiler work, not a security campaign.

Private source groups now apply the existing global canonical resource-fatal
policy even without filesystem operations. A child E_MEMORY, E_LIMIT or E_TIMEOUT
interrupts a body parked on unrelated work; the original error/line survives
joined cancellation and retirement. It does not wait for the body's own timeout.
The classifier uses runtime error types. A NativeSourceException whose code is
E_MEMORY or E_CANCELLED remains source data and can be recovered normally.

Implicit task termination also records a body's source outcome in every open
owned region before aborting it. Draining those regions can then select an
already produced child runtime failure ahead of that source outcome, just as an
explicit native-frame scope exit does. Body source errors still precede child
source errors, cleanup cancellation cannot replace source, and all physical
frames/values settle before completion. Retained public groups keep their earlier
policy selection. Regression fixtures use tiny canonical C++ errors and fixed
synchronization; they do not cause actual memory exhaustion.

The dedicated emitSourceExceptionTasksPrototypeNativeProfile entry emits the
same private native task semantics with registered function sites and logical
invocation instrumentation. It uses the existing real task collector, allocation
hooks, steady/thread CPU clocks and bounded raw runtime schema2. No custom
allocation observer replaces the profiler in this mode. Source-failed tasks are
Aborted even though their ordinary runtime failure slot is empty. A child error
with code E_CANCELLED is Aborted rather than Cancelled; a recovering caller can
still complete. Invocation/function records likewise settle across rethrow,
future wait and group drain.

Private conformance captures generated nativeO0/O2 return, caught/uncaught source,
trap and cancellation-label fixtures. It verifies terminal tasks, no active
invocations, balanced shallow managed memory, zero dropped/invalid records and
matching source outcomes. Native site metadata retains the original operation,
function/source hashes, function-relative byte coordinates and AST line/column.
The private build record explicitly has no graph revision. Collector backing
memory and shallow managed allocations are not a total-process RAM measurement.

This adds a compiler-private emitter and raw runtime report, not ordinary `nex
profile` support for025 projects. CLI build/replay/capture/profile acceptance,
private task debug metadata, resource/file/FFI/provider/binary integration, full
SDK/browser/platform delivery and history-preserving024-to025 migration remain
pending. Full region inference, richer effects/payloads and the original broader
language/toolchain/Studio and measured quality goals remain open. Stable SDK and
primary source/graph/history pointers stay unchanged. Security audits, sanitizers
and fuzzing remain user-deferred.
