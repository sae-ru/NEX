# Windows filesystem adapter

The current Windows GNU/UCRT adapter enables synchronous and task filesystem
calls, and `windows_core_target.files` is true. A direct native Windows/NTFS
probe in `tests/windows_io.cpp` passed24 cases, including actual reparse points,
private ACLs, pinned parents, cross-worker grants and retained physical quotas.
NEX debug/release PE executions separately exercise whole-file/owned streams,
task transport, typed file payloads and cancellation. See the
[machine acceptance](windows-native-acceptance.md) for exact scopes and pending
Windows-hosted SDK/ARM64/FFI work. The0.65 prototype and Wine results below are
historical evidence. Existing macOS/Linux filesystem semantics are unchanged.

The adapter opens the host-selected absolute root once and walks each child
component with `NtCreateFile` relative to the pinned directory handle. Child
opens request `FILE_OPEN_REPARSE_POINT`; handle metadata rejects reparse points
and inappropriate file kinds. It never reconstructs a pathname from a handle.
Windows child names use `/` separators and additionally reject backslashes,
alternate-stream colons, control/invalid characters, trailing dots/spaces and
reserved DOS device names, including superscript COM/LPT aliases. The existing
UTF-8,4096-byte/128-component and1MiB whole-file bounds remain.

Whole writes create a cryptographically named temporary in the pinned parent.
The effective token user receives a protected single-user DACL. Cleanup marks
the temporary for deletion by its handle. Publication uses handle-relative
`FileRenameInformationEx` with replacement/POSIX flags so an already-open reader
can retain the old file. This needs Windows10 version1709 or newer and a
filesystem that implements these operations and persistent ACLs. Unsupported
operations fail; no path-based/non-atomic fallback is supplied. Streaming uses
owned handles, physical quotas, revocation, cursor locks, append-only access and
the existing cancellation/lease rules. Native Windows11 x64/NTFS evidence is
linked above; other Windows versions and filesystems retain separate acceptance.

The direct probe covers Unicode environment/database paths, private ACLs,
no-follow leaf/directory links, parent replacement, pinned roots, atomic writes,
opened readers, byte bounds, cancellation cleanup, stream aliases and quotas.
It must run with permission to create symbolic links, for example an explicitly
configured developer test environment. A link fixture is checked for an actual
reparse attribute; an API success without that attribute is a failure.

Initial x86-64 Wine9 compatibility runs verify ordinary I/O, checked append,
resource/cancellation boundaries and Unicode SQLite. They fail opened-reader
replacement, protected-DACL and actual-reparse fixtures; a parent-race run also
retains an orphan temporary. These results do not certify the filesystem
contract. Wine9's upstream rename implementation explicitly lacks the required
POSIX flag behavior. ARM64 binaries cross-compile; execution has not been tested.

The native probe needed a cancellation checkpoint after pinning a write parent
and before creating a temporary: Windows denies renaming a parent while its
temporary child is open. The original replacement assertion now runs at the
admission boundary and still verifies publication through the pinned handle.
Probe cleanup releases its pinned roots before deleting their container. No
failed reparse/ACL check was skipped or replaced with an emulated link.
Task reads/writes/streams use captured revocable grants and physical leases;
scoped opens reserve logical settlement and owning-executor cleanup before
construction. Keep HTTP request grants explicit; this does not enable Windows
HTTP hosting or grant request access through process environment.

Primary API references: [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[rename flags](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information),
[information classes](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ne-wdm-_file_information_class),
[Windows filename rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).
