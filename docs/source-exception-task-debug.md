# Private native task checkpoint debugging

Toolchain0.135.18 adds emitSourceExceptionTasksPrototypeNativeDebug for checked
parseSourceExceptionTasksPrototype programs. Public language stays0.24 and
private execution ABI2501 stays distinct from published3/4/5. Source syntax does
not change. Normal025 debug/profile/capture/replay CLI remains unavailable.

The dedicated emitter registers code sites, source points, lexical bindings and
visibility for the explicit exception TaskIR. Generated MLIR/LLVM emits actual
nex_task_debug_checkpoint calls. NativeTaskFrame activations, logical caller
chains and scheduler states use the existing non-owning runtime catalog. The
metadata retains original operation/function/source hashes and source line/column.
It introduces no graph revision or archival identity for private source.

Catch code/message bindings become visible after Catch initializes their slots.
Shadowed outer bindings retain separate slots; leaving catch restores their
visible names without reverting outer assignments. Nested catch/rethrow, direct
calls, yields, future delivery and loops retain the correct source state. A
callee pause exposes its own parameters and the caller's retained locals. Opaque
scope/future/channel/function values remain diagnostic identities rather than
authority granted to the observer.

The functional host supplies a real stop-marker controller on a separate thread.
The owning continuation waits until that controller reads stable catalog records
and explicitly resumes it. The controller reads live top/caller frames and copies
only serialized values; temporary Value leases end before resume. It checks
sequence/frame/task identities and reads again while the worker is still paused
to prove state stability. At source/trap/limit completion every task is terminal,
frame counts and the live-frame pool are zero, and native managed allocations
balance. Debug metadata does not keep source values alive after execution.

Conformance compiles seven actual programs at O0/O2, compares their behavior with
the independent AST scheduler and validates26 expected pauses. Cases cover catch
shadowing and outer mutation, NUL/Unicode strings, nested rethrow, a direct caller
chain, future recovery, repeated loop handlers, uncaught original-site rethrow and
runtime/control traps that bypass source catches. The observer also checks the
site/function/source provenance against compiler-produced metadata.

This stage proves emitted checkpoints and the native catalog's owning-thread
pause/watch/resume behavior. It does not establish process-wide all-stop,
LLDB/DAP/IDE or normal archived source-debug acceptance. Debugger expression
evaluation, private capture/report/replay tooling, file/resource/FFI/provider/
binary integration, current full SDK/browser/platform acceptance and explicit
history-preserving024-to025 migration remain pending. Complete region/effect
inference and the original broader language/toolchain/Studio and measured quality
goals stay open. Stable SDK and primary graph/history pointers are unchanged.
Security audits, sanitizers and fuzzing remain user-deferred.

## Subsequent all-stop integration

Toolchain0.135.19 adds a separate unarchived LLDB/DAP context and explicit loader.
Read source-exception-task-lldb.md for its actual commands and limits. The221
controller conformance above retains its owning-continuation scope.
