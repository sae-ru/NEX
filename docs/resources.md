# File resources — language 0.14

`file` is an opaque reference to an opened regular file. It is available only
inside server functions, including nested aggregate types, generic arguments and
captures. Native CLI programs and trusted native hosts can grant access; browser
code cannot contain file values. Copies share one identity, cursor and close
state. Use `server` on pure helpers that accept or return file-bearing values.

```nex
module streams;
server fn main() -> unit !{fs,io} {
  let output:file = unwrap(file_open_write("message"));
  assert(unwrap(file_write(output,utf8_bytes("Я🧠"))) == 6);
  assert(unwrap(file_flush(output)));
  assert(file_close(output));
  let input:file = unwrap(file_open_read("message"));
  print(unwrap(decode_utf8(unwrap(file_read(input,1024)))));
}
```

Run with an explicit directory and an optional write grant:

```sh
NEX_FILES_ROOT=/absolute/data NEX_FILES_WRITE=1 nex run main.nex
```

| Operation | Result |
|---|---|
| `file_open_read(str)` | `result<file>` |
| `file_open_write(str)` | `result<file>`; creates or truncates |
| `file_open_append(str)` | `result<file>`; creates or appends |
| `file_read(file,i64)` | `result<bytes>`; up to the requested byte count |
| `file_write(file,bytes)` | `result<i64>`; bytes actually written |
| `file_seek(file,i64)` | `result<i64>`; absolute byte position |
| `file_size(file)` | `result<i64>`; current file size |
| `file_flush(file)` | `result<bool>`; explicit writeback |
| `file_close(file)` | `bool`; true only for the first logical close |
| `file_is_open(file)` | `bool`; a momentary status snapshot |

All these operations require `!{fs}` and server realm. Open defaults to read-only
capabilities; write/append/flush require an explicit write grant and writable
mode. Read requires read mode. Read/write allow at most 1 MiB per call, while the
total file can be larger. Empty read means EOF (or a zero-byte request). Writes
can be partial; use the returned byte count. Append writes at the kernel's end
position even after seek. Seek rejects negative/unrepresentable positions.

Paths follow the same bounded UTF-8, relative-path, regular-file and no-follow
rules as [whole-file IO](files.md). Streaming writes are incremental. Cancellation
or failure can leave created/truncated files or already-written bytes; use the
whole-file replacement API when its atomic replacement semantics are needed.
`flush` observes writeback errors; close is an ownership transition, not a
durability receipt. Platform restrictions remain macOS/Linux.

Resource copies may occur in immutable lists, records, enums, results and server
closures. Equality compares identity, including after close; formatting emits
`<file>`. Closing any alias revokes every alias. Dropping the last owning value
also closes it. A retained result or capture is still an owner. An in-flight IO
lease delays physical destruction and quota release until it finishes, even
after logical close. No source descriptor, pointer, default/null file value,
constructor or custom destructor exists.

Newly opened files belong to the active host capability and native request (or
CLI/evaluation file scope). Request exit/cancellation/budget/deadline failure
revokes escaped owners. The default physical quota is 64; closed but leased
objects still count. Trusted C++ hosts can grant a `TextFiles` capability with
`FileScope`. Native HTTP continues to deny implicit environment grants; the
stock HTTP executable does not yet expose a file-root configuration option.
The [ownership design](resources-design.md) specifies domains and host limits.

Files and file-bearing types, including phantom generic arguments, are excluded
from application JSON/API and scalar proofs. This prevents authority from
crossing a wire boundary. TypeScript generation rejects server entries; emitted
browser modules include only reachable client/shared code and no file runtime.
The interpreter and native debug/release paths share file semantics.

Debugger previews and pure watch expressions use a separate opaque
`{"file":"17"}` identity marker in `nex.debug-wire/1`. IDs are nonzero canonical
decimal u64 values, not OS descriptors. Equality, nested inspection and formatting
are allowed; every filesystem operation, including status/close, remains an
effect and is rejected in a pure watch. Diagnostic file values carry no IO
authority and cannot be used as live handles.

## Migration from 0.13

Language 0.14 uses function/11 and program/12 canonical formats. Existing stores
and graph imports require explicit `nex migrate`. Old source/history remains
available, and failed checks leave HEAD unchanged. The contextual type name
`file` and the ten streaming function names above are newly reserved for
declarations/generic parameters. Local variables and import aliases named `file`
remain possible, like `bytes`.

If old code declared those names, export its old graph, explicitly rename its
user definitions/types/parameters and references, then migrate that corrected
graph. Migration does not silently reinterpret or rename old code and does not
overwrite source files. Preserve reviewed test/proof intent when updating
snapshot pins. Genuine 0.13 SQL fixtures retain such old declarations, including
ordinary `file_size` functions and a generic parameter named `file`; never retag
those fixtures. Keep SDK 0.35 for old builds, frames and receipts.

General resource types, stable FFI, source async/await and additional platforms
remain pending; `file` is the first source resource adapter.
