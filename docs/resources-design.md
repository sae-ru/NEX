# External resource ownership

Toolchains 0.34/0.35 established the typed C++ ownership foundation and native
streaming boundary. Toolchain 0.36 / language 0.14 integrates the first source
resource, `file`, with interpreter/native execution, browser/wire exclusion and
bounded diagnostic identities. [The resource guide](resources.md) specifies
source semantics and explicit migration. General resource kinds, stable FFI
and async/await remain pending.

## Identity and ownership

Immutable NEX aggregates remain immutable. An external resource is a separate
identity with mutable host state; copying a handle aliases that identity. The
internal `ResourceOwner<T>` owns a typed shared control, never an untracked
integer descriptor. Its nonzero 64-bit identity never repeats in that runtime
image; exhaustion fails before invoking the factory. Default handles are closed
with identity zero. Dropping the last owner or lease destroys the payload once.
Payload destructors must be nonthrowing. Trusted payloads must not form strong
ownership cycles; the file payload contains no handle backreferences.

`close()` is an idempotent logical transition shared by every alias. New
operations fail with `E_RESOURCE_CLOSED`, including zero-length operations.
An operation acquires a `ResourceLease<T>` before borrowing its payload. Closing
cannot destroy the payload while any lease exists, so a descriptor cannot be
recycled underneath an in-flight operation. A lease retains storage, not
continuing authority: it checks domain activity and close status before new IO.
Raw payload references are trusted C++ borrows bounded by their lease; source
code receives neither payloads nor pointers.

Toolchain 0.35 adds the internal `FileData` subtype. Its immutable payload owns
a `FileResource`; aliases inside lists, records, results and closure captures
retain that resource. The shared-pointer control block invokes the complete
subtype destructor. Ordinary `Data` keeps its previous layout; constructing or
copying an owned payload as base `Data` is rejected. Managed wrapper allocations
use the profiling hooks with their actual subtype size. Equality compares the
resource identity, display is the opaque `<file>`, and application JSON rejects
file values through nested aggregates. Language 0.14 gives them the server-only source type `file`. Debugger identities
are non-authoritative; browser representation remains forbidden.

`isOpen()` is a diagnostic snapshot, never an authority decision. Concurrent
close/revocation can change it immediately. Controls synchronize const operations;
hosts must not concurrently assign/destroy a wrapper another thread is accessing.
Copies may be used independently. Callbacks run without domain/control/cursor
locks. A host may release a wrapper from its callback after the method has
retained its operation state.

## Domains and physical quotas

A uniquely owned `ResourceDomain` revokes its bound resources on destruction or
`revoke()`. Moving transfers responsibility; move assignment first revokes the
replaced domain. A child binds to every ancestor, with at most eight domains.
Multiple locks follow a consistent address order. Revocation marks a domain
inactive under its lock, then closes registered controls outside domain locks,
allowing cleanup to re-enter the host.

Every factory reserves a physical slot in each domain before creating an
external object. Limits are 1..4096 per domain, default 64. The slot covers
pending factories and closed payloads retained by leases. Logical close does
not return quota early. A factory runs outside locks with a `ResourcePermit`
for revocation checks. Publication rechecks activity while registering with
all ancestors; raced revocation closes the unpublished object and rolls back
reservations. Throwing/null factories and allocation failures also unwind
through owned cleanup. Registry pruning never acquires a last strong control
reference under a domain lock, where its destructor could re-enter that lock.

`E_RESOURCE_SCOPE` takes precedence over closed status after revocation;
`E_RESOURCE_LIMIT` reports quota or hierarchy limits. Cancellation is cooperative:
an operation authorized before revocation may finish its current syscall.
Regular filesystem calls are not guaranteed to stop immediately. A post-call
check may report cancellation after observable IO.

Independent capability and native request domains can be joined. Shared ancestor
states are deduplicated, with the same depth bound and total lock order. Each
native request owns one domain and retains its joined capability scopes. File
opens are charged against both the host grant and that request, so multiple
grants cannot bypass the request's physical resource limit. Request exit,
explicit cancellation, budget exhaustion and deadline errors revoke escaped
managed file values even if a trusted C++ host retains them. The native request
installs a thread-local runtime binder; the reference interpreter leaves it
empty and uses its own lexical file scope. Ordinary native programs therefore
need no filesystem component merely to link the request runtime.

Request cancellation may come from another thread while the wrapper remains
alive; other request methods and scope lifetime changes belong to its owner
thread. Polling retains request state and copies its callback before invocation,
so a callback may replace itself or end its own scope. After scope destruction
polling aborts with cancellation without dereferencing the released wrapper.
Native streaming calls likewise retain file/byte arguments before polling.

## Streaming file contract

`TextFiles` pins an opened host root directory and has a root domain for direct
handles. `resourceScope(limit)` creates a child; `openIn(scope, path, mode)`
rejects unrelated domains. `FileScope` retains an explicit host grant and creates
a request child for `fileOpen()`. Scope exit revokes escaped handles even while
the host root remains alive. Thread-local scopes must end in reverse lexical
order on the creating thread. Resetting the cached environment grant revokes
its handles. Native HTTP still denies implicit environment grants.

Modes are read, write with truncation, and append. New files use 0600 subject
to umask. Quota/write permission checks precede creation/truncation. Descriptor
relative traversal uses `O_NOFOLLOW`; empty/absolute/dot/dot-dot/NUL/invalid-UTF8
paths and nonregular files are rejected. Existing destinations are checked
without following links and opened descriptors checked again before truncation.
The root is host-selected. This directory capability is not a kernel sandbox:
normal hardlinks and privileged filesystem changes retain their OS meaning.

Read/write accept at most 1 MiB per call; total file size is not capped at 1 MiB.
Read returns up to the requested bytes, empty at EOF. Write returns its actual
byte count and can be partial. Aliases share a cursor serialized per syscall.
Absolute seek rejects negative/unrepresentable offsets; size reports current
file size. Append uses the kernel append flag even after seek. Read/write modes
are enforced; `flush()` calls `fsync` for writable files. Streaming writes are
incremental: canceled open/write may leave a created/truncated file or written
bytes. Whole-file writes retain their separate temporary-file/rename behavior
and cancellation-before-commit semantics.

Bytes, path/text strings, callback targets and the host service are retained or
snapshotted before polling. Callbacks may drop the caller's last reference,
close/revoke a resource or re-enter operations. Polling occurs outside cursor
locks, with authority checked again before each syscall and after success.
EINTR retries poll again. Whole-file callbacks use the same input-lifetime rule.

`nex_file_abi.h` declares the internal native handle boundary for future checked
lowering: open/read/write/seek/size/flush return managed results; close and status
return boolean scalars. Recoverable IO errors remain results; cancellation,
budgets and deadlines preserve native traps and source lines. This boundary is
tested directly, and language 0.14 lowers its checked file intrinsics to these calls. It is not a
stable FFI.

Logical close reports a state transition, not durability. Physical cleanup calls
`close` once after the last lease; it does not retry a possibly recycled
descriptor after an error. This adapter targets macOS/Linux, not every POSIX
implementation. Use explicit flush to observe writeback errors before close.
Platform behavior and partial transfers are documented in the [Linux close
manual](https://man7.org/linux/man-pages/man2/close.2.html), [read
manual](https://man7.org/linux/man-pages/man2/read.2.html) and [write
manual](https://man7.org/linux/man-pages/man2/write.2.html).

## Further resource integration and FFI gates

File integration implements these boundaries for language 0.14. Further resource
kinds and FFI/async must preserve them:

- Add an opaque handle across the checker, runtime, interpreter, native lowering
  and TypeScript browser rejection/reachability together. File operations require server realm and
  `fs`. Handles cannot enter browser/shared state, including through captures.
- Use identity equality and bounded opaque diagnostics without raw descriptors.
  Exclude handles from JSON/API and scalar proof models through nested generics,
  captures and models. Immutable captures do not remove IO effects.
- Bind source handles to capability/request domains. Verify cleanup on returns,
  traps, cancellation, rejected calls and aggregate/closure lifetime changes;
  test executable backend agreement and rejected programs.
- Add explicit history-preserving migration. Genuine 0.13 SQL fixtures contain
  ordinary resource-related user names: never retag old stores or silently steal
  those identifiers.
- Define FFI signatures, transfer versus borrowing, calling convention, error
  mapping and thread/cancellation rules before exposing calls. This internal C++
  interface is not a stable C FFI ABI.
- Build async task cancellation on physical leases. Do not close a descriptor
  under concurrent IO or count closed in-flight objects as free quota.

`tests/resources_runtime.cpp` exercises lifecycle and real files;
`tests/resource_values.cpp` exercises managed payloads, native calls, profiling,
joined request scopes, cancellation, callbacks and cleanup. These do not
prove source integration, other operating systems, a stable FFI or scheduling.
Current verification is recorded in `STATUS.md`.
