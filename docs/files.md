# Text files — language 0.12

```nex
module example;
server fn main() -> unit !{fs, io} {
  assert(is_ok(file_write_text("message.txt", "Я🧠\u0000text")));
  print(unwrap(file_read_text("message.txt")));
}
```

`file_read_text(str) -> result<str>` and
`file_write_text(str, str) -> result<bool>` require a server function and the
distinct `fs` effect. `io` alone grants neither operation. Server functions can
be standalone native entries as well as HTTP handlers. For a standalone program:

```sh
NEX_FILES_ROOT=/existing/directory NEX_FILES_WRITE=1 nex run main.nex
```

The root is an explicit absolute host directory capability. Without it, operations return
`CAPABILITY`. Writes additionally require exactly `NEX_FILES_WRITE=1`; other
values retain read-only access. A successfully opened root is pinned for the
evaluation/native session, even if its pathname is subsequently replaced.
Interpreter evaluation owns its scope; native normal/fatal runtime exit cleans
the default session. No descriptor becomes a NEX value.

Paths below the root must be valid UTF-8, nonempty and relative, with at most
4096 bytes and 128 components. Absolute paths, NUL, empty components, `.`/`..`,
trailing separators and symlink traversal are rejected. The host-selected root
may itself use a trusted platform alias. Only regular files are accepted;
FIFO/device/directory inputs are rejected. Text is strict UTF-8 and preserves
embedded NUL/BOM without normalization. Both input and output have a 1 MiB byte
limit, including files that grow during a read. OS filename/component limits
still apply.

Missing files/parents return `NOT_FOUND`; invalid paths/file kinds return
`VALIDATION`, invalid text returns `E_UTF8`, permission errors return
`PERMISSION`, oversized text returns `LIMIT`, and other I/O failures return
`E_FILE`. Messages omit host paths. Failure results do not trap unless unwrapped.

Writes create a private 0600 temporary file in the already-open parent, write
bounded chunks, sync the file and atomically replace the destination. Parent
directories must already exist. A cancellation/trap before publication closes
and removes the temporary and preserves the previous file. NEX writers publish
whole replacements; concurrent writes may replace one another. This is not a
filesystem transaction or a power-loss durability guarantee: the parent directory
is not synced. Host filesystem operations can block despite cooperative polling.
Other software's in-place changes are not immutable read snapshots.

Native HTTP requests do **not** inherit `NEX_FILES_ROOT`/`NEX_FILES_WRITE`.
Without a trusted host `FileScope`, these calls return `CAPABILITY`, including
when the process environment configures standalone access. A C++ host can
explicitly scope a `TextFiles` capability with `FileScope`; it owns authorization,
partitioning and lifetime. The standard server currently has no file-grant flag.
File writes are not part of SQLite rollback. Do not describe them as transactional
request mutations. This rule prevents an inherited CLI environment from silently
granting handlers file access.

The interpreter and native runtime use the same adapter. Native builds link it
only for reachable file operations and do not require SQLite/OpenSSL for file
access. Client/shared code cannot invoke these server intrinsics or declare `fs`.
Unreachable server definitions stay absent from TypeScript/browser output.
Pure debugger expressions and scalar proofs cannot perform filesystem effects.

Language 0.11 archives need explicit `nex migrate`, retaining their sources,
history and unchanged logical function IDs. New builtin names may conflict with
old user definitions; a rejected migration leaves HEAD unchanged. Repair an
exported source bundle explicitly and migrate that candidate without replacing
the original archive. Keep SDK 0.29 for old receipts/debug frames and review new
task/proof pins without weakening their acceptance intent. Function/9, program/10,
structure/4 and enum/3 formats remain; the language version changes revision identity.

Binary buffers, streaming, exposed resources, general FFI/async, HTTP file policy
and other platforms remain pending. The underlying adapter design and direct
native probes are recorded in [files-design.md](files-design.md).
