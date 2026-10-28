# Current025 native task IO contract

The025 candidate uses public task ABI6, including ordinary HTTP request hosting.
File operations still require server task/fs declarations and explicit physical
grants. with_tasks/task_wait additionally require a source throw effect or a
lexical handler in025. Source-provider records are11/12/13; retained ABI3/4/5
formats and old parser identities stay unchanged. See exceptions.md and
source-exception-providers.md. Complete regression/SDK/platform acceptance remains
pending. The versioned introduction and examples below describe their original
024-or-earlier scope; inspect current examples and compiler capabilities.

# Asynchronous whole-file write host bridge

Toolchain0.132.4 adds `FileWriteGrant`, `FileWriteLease` and
`PreparedTaskFileWrite` for trusted native C++ hosts on macOS/Linux. These are
the physical IO foundation used by language0.23 source task writes. The frontend,
independent interpreter, native continuation adapter and checked static/shared
providers use explicit write requirements and operator grants. Retained
language0.22 still rejects whole-file writes inside tasks; its historical
semantics does not change. Source enablement is separate from complete compiler,
installed SDK and platform acceptance. Streams, networking, DB and task HTTP
handlers remain unfinished work.

The coordinator captures `captureFileWriteGrant` while its authorized
`FileScope` and root `RequestScope` are active. The grant shares the root and
request revocation lineage and resource quota of reads. It never upgrades a
read-only capability. Capture is lazy: an absent or read-only grant is rejected
only when actually used. An IO worker never discovers authority in its TLS or
environment. The root directory is retained by descriptor, so replacement of
its original pathname does not redirect admitted writes.

`PreparedTaskFileWrite(grant, relativePath, byteSpan, text)` snapshots only the
visible input bytes into exact immutable owned storage on the coordinator.
Text preparation checks strict UTF-8, including Unicode scalar validity, before
any write. Byte writes preserve every octet. The worker receives a physical
revocable lease and bounded bytes/path storage, with no NEX value, handle,
source frame, mutable borrowed payload or new filesystem permission.

Submit `prepared.operation()` with `prepared.reservation()` through the existing
bounded `TaskExternalPool` or `TaskGroup::submitExternal`. An owning coordinator
calls `prepared.admit` after physical settlement and control checks. Success
constructs the existing `result<bool>`; ordinary filesystem failures construct
its error variant. Fatal control/resource failures abort rather than becoming
ordinary write results. Preparation failures are host exceptions; a future
source adapter must map only ordinary errors at the attempted source call.

Files are at most1MiB and paths at most4096 UTF-8 bytes/128 components. Relative
paths cannot traverse symlinks or dot/dotdot. Preparation charges exactly its
owned input bytes plus retained path bytes, not a small view hiding a larger
backing allocation. The existing pool limits remain2 IO workers,64 tickets and
8MiB aggregate declared payload. These are transport payload limits, not a
bound on total process RAM or arbitrary copies retained by a trusted host.

The worker reuses the checked synchronous implementation: create a private
temporary in the destination directory, write all bytes with checkpoints,
fsync the temporary, check authority/control and atomically rename it. Before
commit, errors/cancellation remove the temporary and preserve the old file or
the destination's absence. Concurrent complete replacements use last rename
wins. Directory fsync/crash durability is not promised by this operation.

Cancellation can race the last pre-rename check and publication. After that
boundary a complete file can be committed even if cancellation or revocation
suppresses source result admission. No rollback is promised. A cancelled
ticket/task still waits for physical operation and adapter destruction before
returning transport credits or publishing completion. Late revocation also
blocks admission after a successful physical write without pretending to undo
the committed file.

`task_external_file_write_host` exercises real disk IO, strict data/path limits,
atomic replacement, wrong-worker authority, shared physical quotas, controlled
pre/post-commit cancellation, revocation/deadline and one-CPU-task progress.
Its normal/sanitizer/full SDK and platform receipts have separate scopes. This
private bridge does not establish public source writes or general platform
delivery. See [task reads](task-file-reads.md) for the existing public subset.
