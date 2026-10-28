Private emitted checkpoints, native catalog and owning-continuation pause/watch/
resume now have separate conformance. See source-exception-task-debug.md. Full
LLDB/DAP/all-stop/IDE and archived CLI acceptance remain pending.

Private canonical resource control, implicit scope exit and real native profiling
are now covered by source-exception-task-control-profile.md. The original native
stage below retains its scope; public profile CLI/SDK and debug remain pending.

# Private native source exceptions in tasks

Toolchain0.135.16 adds emitSourceExceptionTasksPrototypeNative for separately
checked parseSourceExceptionTasksPrototype source. Public language remains0.24.
Public projects, ordinary emitTaskNativeStep/build/archive/Wasm and025 manifest
selection remain gated. This compiler-private experiment is not an accepted SDK.

The emitter consumes the explicit exception TaskIR described in
source-exception-task-ir.md, generates verified MLIR/LLVM and runs compiled
continuations through the physical TaskGroup. Its descriptor uses the distinct
private ABI0x4e45585400002501; published ABI3/4/5 records keep their existing
layout and requirements. The ordinary application entry rejects private records.
Direct calls, callbacks and coordinator selection check the private mode.

NativeTaskFrame owns the handler stack, caught errors and pending error across
suspension. PushHandler saves the catch PC, inner-slot floor and caught depth.
Unwinding releases inner values while preserving assigned outer slots, hidden
bindings and enclosing match inputs. Source calls are explicit continuations,
including pure helpers. Return releases the complete frame. Handles remain
resume-local leases; parked frames retain owned immutable Values.

NativeSourceException owns full code/message strings, copied original native
site JSON and source line. It is separate from Trap/DataError and ordinary
result<T>. Catch/rethrow preserve original payload/site, including embedded NUL
and Unicode. The host facade explicitly passes this private type through; other
host exceptions retain their checked runtime handling. A code such as E_LIMIT is
user data when raised as a source exception, never a runtime-limit discriminator.

Jobs and regions retain source failures separately from runtime failures.
task_wait marks a future observed and delivers its original error; repeated
waits repeat that error. Normal group close selects a completed unobserved
source-error member in creation order at that close poll, cancels remaining work
and joins physical completion before delivering the error to the owner. A body
source error takes precedence over child source errors. Already produced runtime
failures and parent cancellation/deadline/budget take priority; cancellation from
cleanup cannot replace a source error. Result error returns keep their existing
abort behavior. Source errors do not supervise a body blocked outside wait/close.

Error delivery across a with_tasks activation first drains its closing scope,
then unwinds to the caller's handler. A failed future's frames, managed values and
retirement fences settle before completion is published. Handler-aware lifetime
analysis runs before emission and runtime owner checks remain mandatory. Every
activation keeps the existing root request and control limits; nested groups do
not create a new request. Full region inference remains unfinished.

Functional tests compare real generated nativeO0/O2 with AST results, output and
original errors. Serial worker selection gives deterministic AST scheduling
comparisons; additional two/four-worker cases exercise recovery and group close.
A generated-code observer synchronizes two source-error continuations on distinct
OS workers and checks joined zero retained values/allocations. Separate physical
coordinator cases check repeated waits, body/child/runtime/control precedence and
retirement, including synchronized produced failures. These allocation hooks are
test observers, as in the retained native task suite, not profiling acceptance.
Client-realm source remains a native-entry rejection; it is covered by the
TypeScript experiment instead. Security campaigns remain user-deferred.

Private mode currently supports pure/io/task/throw, with the existing task
callback IO restrictions. Files, resources, FFI, db/network, parallel_map workers,
provider/binary integration, task debug/profile and full cache/library/SDK/browser/
platform acceptance remain pending. Explicit history-preserving024-to025 migration
and broader language/toolchain/Studio and measured-quality goals still precede
publication. Stable SDK pointers and primary graph/history stay unchanged.
