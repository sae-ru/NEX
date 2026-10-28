# Native scheduler owned-value retirement

Toolchain0.128 moves discarded native scheduler Value roots outside its mutex.
Query `nex describe --field task_value_retirement --json` and read this guide with
`nex guide --kind task-value-retirement`. Language0.21, source grammar, checked
effects/realms, canonical identities and explicit migration rules are unchanged.
Source input/result/channel/capture resource transport and the task/FFI adapter
are still unavailable. This private kernel cleanup does not expose authority.

Cancelled blocked sends, delivered events that will never resume, failed owner
results, completed scope member results and scope channel buffers all have an
explicit retirement path. Each admitted job contains three retained Value root
slots and intrusive queue links. Pipes retain their existing admitted buffer for
retirement. Scope/job completion uses a separate deduplicated queue, preallocated for every
admitted task slot and1024 scope slots. Closing256 nested scopes uses this queue
instead of recursive native calls. Queueing cleanup allocates nothing and cannot run a managed payload's
destructor under the scheduler mutex. Moved-empty Values and scalar fields retain
their normal cheap reset paths. Coroutine frames still leave outside the lock.

A worker extracts a batch under the lock, releases it, destroys all retained
roots and actual buffer storage, then records completion under the lock. Cleanup
may reenter runtime queries and may enqueue further cleanup. A job with pending
retirement cannot resume or publish completion. A logical scope stages member
results and buffers once and publishes closure only after its own batches settle.
API guards tag only roots retired by their own mutation. Their stack-owned
fences and intrusive per-fence links allocate no heap storage. A guard processes
only those roots and waits for any of its batches taken by another worker; the
fence remains alive until actual destruction and quota release complete. It
never drains unrelated global cleanup on a still-running source stack. A
suspending call transfers its queued links to an admitted Job-owned fence before
unlocking; it releases the source worker and cannot resume or publish completion
until that fence settles. General worker cleanup runs between source turns.

Unrelated ready work remains schedulable; an ordinary synchronous destructor can
occupy its worker, while thread-affine/device destruction still needs the owning
resource executor and actual physical fence.

Channel capacity stays charged until the retired buffer storage is destroyed.
Group drain includes queued and in-flight retirement before stopping workers.
Root buffers still leave during final group cleanup. Successful root results
remain joinable while their group exists. Independently retained passive aliases
are not revoked by dropping a scope's own references. Resource-region revocation
and physical settlement remain separate and continue to apply to genuine host
resources; a discarded wrapper is not proof of a device fence.

The maintained fifteen-case probe uses actual managed allocations whose real
destructors reenter scheduler queries. It checks cancellation and channel close,
cancelled delivered events, scoped and failed results, retained passive aliases,
buffer destruction/capacity ordering, nested reentrant cancellation, multiple
workers, API guard isolation, stolen completion fences,256 nested scopes, root-buffer shutdown and joinable root-result lifetime. These objects
contain no external/file/task authority and do not bypass source snapshot guards.
The installed SDK compiles and runs the same probe from installed runtime sources.

```sh
cmake -S experiments/task-value-retirement -B build-task-value-retirement
cmake --build build-task-value-retirement -j 4
ctest --test-dir build-task-value-retirement --output-on-failure
```

Matching full compiler regression, SDK workflow, sanitizers and platform receipts
have their own delivery scope. Before source resource task transport, complete
request-parent ownership transfer, typed physical completion admission, captured
FFI grants and an explicit history-preserving language migration.
