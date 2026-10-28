# Private024 physical IO and diagnostic completion

The POSIX C++ host can construct TextFiles with an optional FileIOObserver. It
receives bounded scalar fields only: operation, Before/After, argument, result
and errno. It receives no file descriptor, path, payload, NEX Value, frame or
new authority. Open events cover the actual open/regular-file validation and,
for open_write, truncation. Stream events bracket read/write/lseek/fstat/fsync.
After events run outside the cursor mutex while the real physical lease and
quota remain held. Hosts synchronize their callbacks and must not assume a
cross-task IO order. An absent observer preserves the legacy path and polls.
Unknown observer exceptions become E_TASK_HOST; allocation failures retain
E_MEMORY. A callback cannot upgrade the original grants.

A FileScope can bind an explicit resource subdomain descended from its exact
TextFiles capability. The original host retains that domain and can revoke it
without manipulating another coordinator's TLS. A foreign domain is rejected
before installing lexical state. Captured grants preserve the original quota,
request ancestry and revocation. A read-only scope remains read-only.

The source suite runs actual compiled NEX continuations and an independent AST
scheduler. Twelve native images cover read/seek/size, truncate/write/flush, append,
module/generic File aliases, scope/future owner promotion and source task_cancel.
Six source alias-close cases hold read/write/append/flush/seek/size after real IO.
Another source task closes an alias in an immutable list/result graph; pending
results become E_RESOURCE_CLOSED and a new open still gets E_RESOURCE_LIMIT
until physical drainage. Completed write/append bytes remain observable.
At11 selected syscall completions, the host holds the IO worker before admission
and applies success, request cancellation, deadline, domain revocation or host
failure. A separate source task_cancel case cancels a child only after its real
write has reached the physical gate. While held, execution cannot complete,
quota stays1 and cannot be reused. After release, all IO credits, owning cleanup,
physical quota and managed values must settle. Visible file contents distinguish
actual writes/truncation from skipped source continuation. These62 pairs do not
claim interruption of an arbitrarily blocked OS syscall, rollback after IO or
directory crash durability. The observed gate is after the real call and before
its result is admitted, not inside an uninterruptible kernel operation.

Physical stream/open run state records exceptional exits before transport
publication. Bounded known cancellation/revocation/host diagnostics retain their
meaning in reference admission; they are not misreported as E_TASK_STATE. A
failed result is still admitted at most once. Unknown diagnostics, impossible
shapes and duplicate admission remain rejected. Host tests also exercise
reentrant close/revocation outside cursor locks and fault cleanup.

An instrumented runtime marker may stop before DWARF's pointer-parameter
location is valid. The read-only debugger first uses that parameter; its
fallback accepts only the actual64-byte TaskDebugStop local in the direct,
verified runtime taskDebugPublish caller. The catalog and complete task/frame/
point/visit/publication tuple must still match. It reads no guessed register or
stack offsets and runs no code in the inferior. Marker errors remain visible
when no valid logical task can be selected. Exact formatter, image hashes,
language/ABI and source ownership guards remain mandatory, so a changed reader
requires a newly captured matching debug session.

These are private host/source contracts. The ordinary CLI and LLM contract
remain public023; this adds no source syntax or implicit migration. Full/SAN,
installed SDK and platform receipts are separate. Additional mixed failure conformance, public024 delivery, async network/DB/task HTTP, accelerators and all
other original project requirements remain open.
