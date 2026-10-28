# Private external completion kernels

Development toolchain0.109 / language0.19 introduces experimental trusted-host
completion kernels in working116, retaining the verified115 transport. Discover their exact scope with
`nex describe --field task_external_completion --json`. This private kernel itself is not a source API. Working117/toolchain0.110
connects exactly two source reads in language020; see [task file reads](task-file-reads.md).
The underlying private transport adds no syntax or public host ABI. Existing task effects, result propagation,
realm boundaries and the [task execution limits](task-limits.md) still apply.

Current116 full regression, installed-SDK and platform acceptance remain pending.
Frozen115 passed122 regression groups and its matching installed SDK24/438.
The preceding113 full gate passed118 tests and its matching installed SDK
passed24 phases/438 commands. Earlier receipts and individual kernel checks
do not establish116
acceptance, Linux116/Windows116 delivery or an accepted release.

## Transport and scheduling

The private transport moves bounded owned host bytes/results and opaque tickets.
An I/O worker receives no source `Value`, raw `Handle`, source capability,
coroutine/frame pointer or borrowed `FileScope` TLS state. Only the owning
scheduler accepts a terminal outcome and resumes the parked continuation.
Callbacks never directly run a source frame. Ticket checks authenticate the
driver/group, logical owner, slot generation and single consumption, rejecting
foreign, stale, forged and repeated completions.

Native and reference host pools accept at most2 I/O workers,64 pending tickets,
8MiB of aggregate reserved payload and1MiB of result bytes. Their configuration
may lower those ceilings. These I/O workers are separate from the source task
executor's worker count. TypeScript uses64 tickets,8MiB of aggregate reservation
and a1MiB per-operation reservation; it executes source and host coordination
serially on one event loop. Host Promise work can complete externally, but the
kernel does not create browser or Node workers.

Reservations bound the transport's declared retained payload, not total process
or host-adapter memory. A small view of a large allocation must be copied or
charged for its full backing storage. Host adapter code, operating-system
buffers, executor stacks and runtime metadata are outside a total-RAM guarantee.
Backend byte-charge models and diagnostics differ; the kernels do not promise
identical quota-exhaustion thresholds.

A parked external operation is a live source of progress. An otherwise empty
ready queue waits for its mailbox, cancellation or the root deadline. The wait
registers and rechecks notifications to prevent a completion from being lost at
the parking boundary. Without any live external operation, genuinely stalled
channel programs retain their existing `E_TASK_DEADLOCK` behavior. Timer progress
alone is not proof of asynchronous filesystem or network execution.

## Cancellation and physical retirement

Logical cancellation prevents new admission, invalidates continuation delivery
and requests cancellation of admitted host work. Queued work that never started
can retire without running the adapter. Running work retains its ticket,
reservation and physical lease until the operation actually returns or its
settlement Promise establishes quiescence. Cancellation or an expired deadline
does not establish that an operating-system call, reader or worker has stopped.

Task/scope/root completion waits for this physical drain. Cleanup may unwind
logical frames first, while the physical ownership ledger remains live. An
error-result scope exit still cancels/drains its unfinished descendants before
returning the original result; cleanup cancellation does not replace that result.
Traps and resource control remain terminating errors. Root deadlines cannot be
renewed by a child, and a timed-out coordinator sleeps while physical work is
still pending instead of spinning on an already-expired deadline.

Fatal host/transport resource failures (`E_MEMORY`, `E_LIMIT`, `E_TIMEOUT`)
reported during physical drain take precedence over cleanup cancellation and
ordinary results. An already selected fatal resource error retains precedence.
This never reopens source admission or resumes the cancelled continuation.
Ordinary host errors and cleanup-requested `E_CANCELLED` outcomes may still be
discarded when cancellation wins before admission.

Acceptance is the linearization point for publication. If cancellation or
revocation wins first, the outcome is discarded after physical retirement and
cannot reach a source continuation. If acceptance wins, the outcome is delivered
at most once; later cancellation remains observable at source checkpoints.
Admission rechecks the host grant before publishing file data. Forced process
termination and an adapter that never acknowledges quiescence provide no clean
drain or hard cancellation-latency guarantee.

## Native host kernel and file-read lease

`runtime/nex_task_external.h` exposes the private `TaskExternalOperation`,
`TaskExternalResult`, `TaskExternalTicket` and `TaskExternalPool` interfaces.
`TaskGroup::submitExternal` and `awaitExternal` in `runtime/nex_tasks.h` park an
owning coroutine while the separate bounded pool runs trusted host work. Worker
results contain owned bytes or bounded diagnostic strings. Operation/lease
destruction precedes publication, and notification runs outside kernel locks.
Conversion to source values belongs to the owning scheduler, outside I/O workers.

The POSIX-only `FileReadLease` in `runtime/nex_files.h` is an explicit private
bridge, captured by `captureFileReadLease(relative, environmentAllowed)` on the
authorized coordinator. It pins the existing `TextFiles` root and a validated
relative path through revocation-aware resource ownership. Workers use that
captured lease; they do not discover a grant from their own TLS or environment.
The host chooses whether existing environment-based capture is allowed; an
explicit `FileScope` remains authoritative. Capture does not open/read the file.

The captured lexical/request domains must remain valid for admission. Revoking
one domain blocks further use and is checked during worker polling and again by
the scheduler after retirement. The physical lease keeps operation-owned storage
alive during drain without restoring a revoked logical grant. The existing
regular-file, relative-path/no-follow,4096-byte path and1MiB data limits remain.
No file handle becomes a source value.

`runtime/nex_task_file_read.h` provides the private `PreparedTaskFileRead` adapter.
Its constructor captures a lease; `operation()` returns a host operation that
reads owned bytes. Its reservation includes the maximum data and retained path.
After waiting for retirement, the owning scheduler calls `admit(result)` to
recheck the lease and construct the existing text/bytes result. Text admission
uses strict UTF-8. Ordinary file failures remain result values; cancellation,
timeout and resource exhaustion remain terminating control failures. This adapter
does not add source lowering for `file_read_text` or `file_read_bytes` in tasks.
It provides no asynchronous write, stream or Windows file lease.

## Independent reference host hook

`include/nex/task_reference_external.h` defines an independent
`TaskReferenceExternalMailbox`, its authenticated tickets and
`TaskReferenceExternalHost`. It reuses the bounded raw host-operation contract,
not native `TaskGroup` or compiled-frame dispatch. Checked AST source execution
remains serial; its separate I/O pool can run at most2 host operations.

The optional private host parameter to `evaluateTaskReference` may intercept a
checked `task_yield` through `prepare(owner, span)`. Returning no request preserves
ordinary yield. A returned operation parks that AST continuation until physical
retirement. The coordinator's `admit` hook may validate the host result/lease;
the source response is always unit. This is not a general typed source-I/O
binding, and it does not widen fs/db/ffi effects or admit file-bearing source
values. The020 fixed typed read adapter is separate and does not call this
unit hook; reads do not require a synthetic host parameter.

## TypeScript trusted-host bridge

`web/nex-task-runtime.ts` exports private host helpers `hostPending` and
`hostAwait`, with brands separate from source requests and invocation values:

```ts
function* fromTrustedHost(start: () => task.HostOperation): task.Step<nex.Result<string>> {
  const ticket = task.hostPending(start, raw => {
    if (typeof raw !== 'string') throw new Error('expected host text');
    return nex.ok(nex.string(raw));
  }, 4096);
  return yield* task.hostAwait(ticket);
}
```

The ticket is created inside its owning active generator. The factory reserves
capacity; the host operation starts only when its branded wait is admitted.
Unawaited tickets retire at owner or callback exit. A pending ticket is not a NEX
value and cannot escape through source results, snapshots, callbacks or channels.
It cannot be substituted for a source request or task invocation.

`start()` returns `{settled: Promise<unknown>, cancel: () => void}`. Settlement
must mean physical quiescence, including operation-owned readers and temporaries.
`start` may throw only before physical work exists; after starting, an adapter
must return its settlement Promise even on eventual failure. A known Promise
with a malformed cancellation hook is still drained before protocol rejection.
The cancel hook is a request and is called at most once for running work. Trusted
start/admit/cancel callbacks execute outside the active source generator context.

Promise handlers enqueue a raw terminal outcome. Before publication, the
coordinator calls the trusted decoder to establish the expected concrete result
schema, then validates/copies a bounded immutable NEX graph. It accepts checked
scalars, bytes, lists and nominal records/enums. It rejects source authority,
functions, private tickets, malformed Unicode/numbers, cycles, holes/accessors
and unsupported host objects. Copying is bounded by depth64,65536 nodes and the
operation's reservation; it charges8 units/node,2 per UTF-16 unit for text and
metadata, and byte-buffer data length. These are transport accounting units.
Trusted decoder allocations do not become a total host-memory claim.

Ordinary host errors can be explicitly decoded to `nex.err` values. Host
rejection/start failures are sanitized to `E_HOST`; decoder failures use
`E_HOST_VALUE`. Scheduler validation/control errors preserve their checked codes.
The final statistics include pending tickets, reserved bytes, mailbox entries,
physical starts/settlements and peak reservations. Clean completion requires zero
pending ownership, mailbox entries and logical frames/calls; `actualWorkers` is1.

## Unsupported boundaries

These experiments enable no public source filesystem/network asynchronous call,
new builtin, db/FFI task bridge, binary-provider task ABI, general async exception
syntax, task debugger/profiler integration or async write/stream contract.
TypeScript still emits reachable shared/client code only and rejects server,
filesystem and foreign dependencies. Browser filesystem support and task-facing
network, UI and browser-worker external-IO bridges remain pending. The separate
toolchain0.120 dedicated task-worker host executes task-only compute without
external authority; see browser-workers.md. Main-thread pure UI and ordinary
filesystem APIs retain their contracts.

## Explicit root grant foundation (private116)

`captureFileReadGrant(environmentAllowed)` runs once on the authorized root
coordinator after its RequestScope exists and before task workers start. The
resulting host-only FileReadGrant retains the pinned filesystem and revocation
access. Its `lease(path)` and explicit PreparedTaskFileRead(grant,path,text)
constructor never discover worker TLS, environment or a temporary resume
RequestScope. Missing authority stays an unavailable snapshot and reports
CAPABILITY only when a read is attempted. Revocation and fatal control errors
remain terminating. A grant captured before a request is only bound to its
original lexical lifetime; it must not stand in for a request-bound source host.

The retained relative path uses an exact owned byte array up to4096 bytes,
including the boundary where std::string capacity may exceed logical length.
The existing whole-read transport reservation remains1MiB+4096, allowing seven
maximum reservations in the default8MiB pool. Temporary parser allocations and
allocator metadata are outside the declared retained-payload bound.

This foundation adds no source fs lowering, callback permission or language
semantics. Public task/fs integration requires a separate explicit version and
history-preserving migration; language0.19 keeps its existing boundaries.

The preceding private116 foundation retains019 semantics. Public117 uses a separate020 identity and explicit019 migration; its current acceptance is pending.
