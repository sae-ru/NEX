# Native failure diagnostics

Toolchain 0.46 adds operation metadata to checked native runtime failures without
changing language 0.15. `nex run --json` retains process status, stdout and stderr,
and adds `native_diagnostics`. For each report whose metadata matches the selected
checked build, it returns the function, local function/operation IDs, operation
site, exact revision/source hash/build key and source location.

```sh
nex run examples/native-diagnostics.nex --json
nex run examples/native-diagnostics.nex --entry message --json
nex diagnose --revision REVISION --manifest BUILD/debug.json --log stderr.log --json
nex context --operation OPERATION_ID --revision REVISION --json
```

The bundled example deliberately exits with `E_DIV_ZERO` (process status70).
Its `message` entry instead exits with `E_RESULT` and preserves embedded NUL/Unicode
in the human output and escaped bounded JSON record.

`diagnose` reads an existing log and manifest; it does not build or execute an
application. Use a source filename for current checked source, or `--revision`
for an archived graph. Retain the complete source bundle/store and matching
`debug.json`. A graph imported into a different store has different local IDs;
the same checked site can resolve to that store's IDs. Source files may be absent.
Import a graph with `nex import GRAPH.json`, where `GRAPH.json` was produced by
`nex graph -o GRAPH.json`. `nex export -o` exports source text instead.

Standalone executables print the existing human-readable failure followed by
one escaped JSON line beginning `NEX_NATIVE_TRAP `. Its `source` describes a
function-local site; its `application` identifies the linked program. Native
libraries retain a null application identity unless their trusted host provides
`nex_application_identity`. Libraries originating from another build cannot be
mapped using an unrelated application's manifest.

The JSON report is data from the application process. A `mapped` result means
that its compiler/build/revision/source/function/site/offset metadata agrees
with the selected checked manifest and program. It does not authenticate the
process or prove that arbitrary trusted native code reported its true location.
Forged or stale mismatching metadata stays `unmapped`, without local graph IDs.
Malformed marker lines are counted as `ignored`; they do not replace the process
exit status or ordinary stderr. The [schema](../llm/native-diagnostics.schema.json)
describes the bounded response.

Native HTTP servers emit the same record only in operator stderr, with the
request ID. Public error responses retain their existing generic message and
code. Request cancellation, execution-budget/deadline failures and checked
runtime traps keep their operation metadata across exception propagation and
request cleanup. The innermost located failure is preserved. External native
declarations report the checked wrapper's `body` site; this identifies the NEX
boundary, not a source instruction inside the external module.

The compiler emits compact typed constant site descriptors, sharing function
hashes between operations, and passes their addresses to
additive `_at` runtime entry points. Existing helper names/signatures and the
original C++ `Trap` layout remain available. C value ABI 1 is unchanged. JSON serialization occurs only on failure. No
diagnostic allocation or thread-local site update occurs on successful calls.
Whole-program identity is linked separately so an unrelated function edit can
reuse existing function objects. Relative operation offsets and exact function
source hashes are checked against the current manifest before coordinates are
used. Existing cache rules still invalidate changed emitted source coordinates.

Toolchain0.165 retains explicit message lengths through ordinary runtime failures,
reference/task evaluation, native application/request boundaries and frontend
JSON diagnostics. Embedded NUL is part of the message, including when computing
frontend message hashes and diagnostic identities. New derived runtime exceptions
carry the owned text; the original `Trap`/`LocatedTrap` layouts and C-string entry
points remain available. Legacy C-string callers retain their terminator contract.
Source semantics, language0.28, task ABI7 and C ABI major1 are unchanged.

Length-aware transport does not remove protocol bounds. Task IO/resource failure
mailboxes still copy at most4096 message bytes while the producer is leased.
Native structured records retain the limits below and escape embedded NUL as
JSON data. The human-readable stderr message retains the original text, including
NUL. Consumers should use the escaped JSON record for structured display.
The separate trusted C API `raise_trap` still requires NUL-free strict UTF-8,
its original code pattern and at most2048 message bytes; this change grants no
additional foreign authority and does not widen that packet.

Limits are explicit: at most 32 parsed reports are retained, each at most 64 KiB;
older parsed reports are counted in `omitted`. Compiler source descriptors are
bounded to 16 KiB. Runtime code/message inputs are limited to 128/4096 bytes for
the JSON record, with UTF-8-safe truncation and replacement of malformed byte
sequences. Truncation flags describe those input limits. Newlines/control
characters are escaped. The legacy human-readable line can contain the original
message. Report serialization is best effort if memory allocation itself fails;
the process status and legacy line remain authoritative. `diagnose` requires regular, non-symlink UTF-8 inputs, with a 4-MiB log
and 64-MiB manifest limit. Parsed JSON container depth is limited to 64. No FIFO/socket is read. The parser treats longer marker
records as ignored.

This covers checked runtime helper failures in debug, release and instrumented
native builds. OS signals, crash/core PC recovery, arbitrary C/C++ internals,
unique optimized instruction attribution, parser/checker graph identities and
browser profiling remain separate unfinished work. Current test/platform scope
is recorded in `STATUS.md`.
