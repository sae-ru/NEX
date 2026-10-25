# Development0.133.4: precise private024 task file requirements

ABI5 image read/write flags and standalone build metadata now classify checked
reachable task instructions consistently. Read/open-read and write/open-write/
append/flush have separate flags; seek/size/close/is_open retain the existing
opened owner without requesting another root read/write grant. All stream
operations set the stream image flag and enable the owning task IO machinery.
Unreachable helpers cannot add grants. Declared effects and image metadata do
not grant OS authority or upgrade a read-only file. Public023/default, retained
ABI3/4 descriptors and their build metadata, grammar and history stay unchanged.
Public024, physical-close offload, provider/capture/package/debug/profile and
matching full/SAN/SDK/platform acceptance remain pending. All original language,
server, accelerator, UI/mobile, Studio and converter requirements remain open.

# Private024 source stream integration (development0.133.3)

Explicit C++ source APIs may select TaskStreams024. Ordinary CLI/default projects
remain language023; changing nex.json does not enable024. The existing stream
syntax suspends inside server task/fs functions. Files created by such opens
have real logical owners, physical request/root grants and retirement fences.
Native ABI5 appends stream requests and requires explicit stream bits. Retained
ABI3/4 masks and public023 stream rejection are unchanged. File-bearing source
captures/results/futures/channels/closures use atomic mixed external/file owner
transfer; no file authority crosses browser/wire/FFI/unstructured parallel paths.
Source/physical conformance, explicit transactional migration, public publication,
provider/capture/package/debug/profile contracts and current SDK/platform delivery
remain pending. This is implemented private code, not a completed language release.

# Private asynchronous file-stream host foundation

Toolchain0.133.2 adds trusted C++ preparation for real opened regular files.
Query `nex describe --field task_file_streams_host --json`. This is a host
foundation for the complete source streaming integration. Language0.23 still
rejects reachable file-bearing task execution and streaming operations; unused
declarations can remain checked while excluded from output. It keeps
its canonical identities, old parsers, effects, realm boundaries and migrations.
The synchronous source [file API](resources.md) remains available.

## Captured authority and opened owners

Capture `FileReadGrant`/`FileWriteGrant` on the authorized coordinator under its
original FileScope and request. `openRead(path)` and `openWrite(path,mode)`
produce immutable `FileOpenLease` instances. Read grants cannot select a write
mode. Write opens support truncate or append. Preparation owns the exact bounded
UTF-8 path and performs no file creation/truncation. A worker uses the retained
root descriptor and revocable resource access, never its environment or TLS.

`PreparedTaskFileOpen` runs this open on the bounded host pool. A new FileResource
is held in a one-shot typed side channel. The raw ticket contains an empty
wakeup/diagnostic; it never contains a fabricated file ID, source Value or C
token. Coordinator-only admission checks the captured grant and moves the real
owner. Duplicate starts/admission, a forged wakeup and moved requests reject.
Destroying/discarding preparation closes an unpublished owner; it cannot revoke
an owner already admitted to the caller.

An abandoned or cancelled operation may still be physically running. Discard
denies publication and arranges cleanup of a later result; it does not claim
the operation has stopped. Wait for pool retirement before completing its task.
If a completed open result still awaits admission, it counts against the real
file quota until admitted or discarded. A future source bridge must discard
unpublished outcomes and drain physical leases before publishing task completion.

## Existing streams

`FileResource::lease()` captures a FileStreamLease retaining the original
descriptor, mode, cursor, logical close state and physical quota. Prepared host
read/write/seek/size/flush operations use this lease. Only the coordinator
constructs source result Values; IO workers carry bounded raw bytes/scalars.
Scalar replies use checked nonnegative little-endian i64, not native pointers.

Reads/writes allow at most1MiB per call, while the complete file may be larger.
Read results contain arbitrary octets; callers handle text decoding and split
UTF-8 sequences explicitly. Empty reads indicate EOF or a zero-byte request.
Writes snapshot exactly the visible input bytes, report the actual possibly
partial count and permit zero-length writes. Append uses the kernel's end
position even after seek. Seek is absolute and checked for representability.
Flush reports actual writeback failure; close alone is not a durability receipt.

Copies share one cursor. Each syscall is serialized by its file's mutex;
independent tasks do not acquire a guaranteed cross-task request order.
Explicit sequencing or application channels are needed when order matters.
Root/path/no-follow/regular-file and existing mode/error precedence remain.

The transport retains the existing ceilings:2 IO workers,64 tickets,8MiB of
declared payload reservation,1MiB reply bytes. Read reserves its requested
maximum; write reserves exact snapshot plus8 reply bytes; seek/size reserve8;
flush reserves0; open reserves the path. Resource/metadata, OS caches and source
frames do not establish a total process-memory bound.

## Cancellation and physical settlement

Logical close/revocation does not destroy an admitted physical lease or return
its quota. Workers recheck their original authority and control. Alias close
can return an ordinary E_RESOURCE_CLOSED result; request/domain revocation and
resource-control failures terminate. Coordinator admission accepts a control
checkpoint and checks it before/after constructing a result. Transport/resource
failures retain precedence over later cancellation.

Cancellation cannot undo cursor movement, a partial write, creation or truncation
that already happened. A post-IO cancellation can suppress delivery while those
effects remain. Use whole-file replacement for its separate atomic-rename
semantics. Neither cancellation nor this foundation promises rollback, bounded
kernel cancellation latency or directory crash durability.

## Verification and next publication

The native host probe exercises actual files larger than1MiB, shared/concurrent
cursors, immutable snapshots, modes, EOF, append/seek/flush, root replacement,
path/FIFO/symlink rejection, typed outcomes and malformed replies. A separately
spawned child uses its own file-size limit to force a real partial write without
changing parent limits. Controlled gates check quota/ticket retention, pre/post
IO cancellation and progress on a single CPU task worker. Old read/write host
and synchronous source behavior require matching regression coverage.

Next integrate genuine file-bearing task ownership, source open/stream/close
admission, independent AST/native lowering, all exit cleanup, explicit language
migration and debug/profile/provider/SDK delivery. None is enabled by a manifest
flag or by the existence of this host header. Network/DB/task HTTP, general
accelerators, UI/mobile/Studio and the full original plan remain unfinished.
