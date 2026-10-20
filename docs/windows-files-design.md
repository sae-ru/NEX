# Windows filesystem prototype — validation pending

The0.65 source includes a Windows runtime prototype and a direct C++ regression
probe in `tests/windows_io.cpp`. The NEX CLI continues to reject reachable
filesystem/resource calls for Windows, and `windows_core_target.files` is false.
Do not infer availability from the prototype's presence or from a successful
cross-compilation. Existing macOS/Linux filesystem behavior is unchanged.

The prototype opens the host-selected absolute root once and walks each child
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
the existing cancellation/lease rules. This is the intended contract, awaiting
native execution evidence.

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

Before enabling this adapter, run the unchanged probe on actual Windows/NTFS,
inspect any failures and repeat actual NEX debug/release programs after enabling
the guarded backend. Record compiler, target libraries, OS/filesystem, artifacts
and source hashes. Keep HTTP request file grants explicit; process environment
must not implicitly grant request access.

Primary API references: [NtCreateFile](https://learn.microsoft.com/en-us/windows/win32/api/winternl/nf-winternl-ntcreatefile),
[rename flags](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information),
[information classes](https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/wdm/ne-wdm-_file_information_class),
[Windows filename rules](https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file).
