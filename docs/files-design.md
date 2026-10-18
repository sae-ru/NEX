# Filesystem adapter and language integration plan

Development toolchain 0.30 integrates the POSIX `TextFiles` adapter into language
0.12 through server-only `file_read_text` / `file_write_text` and the `fs` effect.
The checker, interpreter, native backend, migration and model-independent pack
now describe the same operations. [files.md](files.md) is the normative guide;
STATUS.md separates targeted checks from the pending full compiler/SDK matrix.

The host owns a directory capability and an explicit writable bit. NEX values
will contain immutable text/results, never descriptors. A capability pins its
opened root. Paths below it must be valid UTF-8, relative and at most 4096 bytes
and 128 components; empty/dot/parent components and symbolic-link traversal are
rejected. The host-selected root may itself use a trusted platform alias.
Only regular files are accepted. Text is strict UTF-8, preserves embedded NUL
and has a 1 MiB byte limit, including when a file grows during a read.

The adapter walks each parent with descriptor-relative `openat` and
`O_DIRECTORY|O_NOFOLLOW`; Linux documents that `O_NOFOLLOW` applies to the final
component of each open, so checking only the last component is insufficient.
Descriptors use close-on-exec and RAII. See [open(2)](https://man7.org/linux/man-pages/man2/open.2.html).

Writes create a private exclusive temporary file in the already-open parent,
write bounded chunks, sync the file and publish it with `renameat`. Readers of
NEX-produced files observe complete replacements. Cancellation before publication
unlinks the temporary and preserves the previous file. Concurrent writes may
replace one another; no transaction/compare-and-swap is promised. Rename's
replacement behavior is documented in [rename(2)](https://man7.org/linux/man-pages/man2/rename.2.html).
Publication is not a power-loss durability promise: the parent directory is not
synced. OS interruption/termination and arbitrary filesystem drivers are outside
the cooperative poll mechanism. Existing open readers are not immutable snapshots
of files modified in-place by other software.

Source integration maintains left-to-right evaluation, immutable owned results
and cleanup on traps/cancellation. Interpreter and native code call the same
adapter. Reachable client code rejects these operations and unreachable server
definitions remain absent from TypeScript/browser output. HTTP request scopes
do not inherit the CLI environment capability; a trusted C++ host must explicitly
grant `FileScope`. The standard server exposes no file-grant option. File
mutations are not part of SQLite rollback.

New builtin names/effects require language 0.12 with an explicit history-preserving
0.11 migration. Genuine SDK 0.29 store/export fixtures were captured first. Old sources,
revisions, local IDs, task/proof acceptance intent and their matching SDK must be
preserved. Advertise the new syntax only after specification, EBNF, capability
descriptor, language pack, schemas, examples and differential/rejection tests agree.

Acceptance must cover Unicode/NUL roundtrips, missing/invalid/oversized files,
read-only denial, symlinked leaves/parents, traversal, FIFO/device rejection,
atomic replacement, cancellation cleanup, pinned roots and repeated-operation
descriptor counts on macOS and Linux. Then test interpreter/native agreement,
effect/realm/function-value rejection, archived sources/migration, installed SDK,
package independence and actual HTTP policy. Binary buffers, streaming, exposed
resources, FFI, general async and other platforms remain separate open work.

The internal adapter passed all 13 direct C++ cases on macOS ARM64, Linux ARM64
and emulated Linux x86-64. Actual ELF machine tags were checked for both Linux
probes. [Prototype evidence](evidence/files-adapter-0.30.0.json) records source
hashes and genuine SDK-0.29/language-0.11 historical fixtures. Its macOS full
30-suite prototype regression passed in 921.16 s. These are historical adapter
results from before source exposure; language 0.12 requires its own complete
compiler and installed-SDK verification.
