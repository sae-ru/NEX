# NEX language server: development toolchain 0.68

`nex lsp` runs a stdio [Language Server Protocol 3.17](https://github.com/microsoft/language-server-protocol/blob/gh-pages/_specifications/lsp/3.17/specification.md)
adapter using Python 3.9+ and the selected compiler. Its standard output contains
only Content-Length-framed JSON-RPC. Use it from a trusted physical workspace
with a compatible editor/client; it needs no network, model or provider SDK.
`NEX_PYTHON` selects the Python executable. `nex lsp --json` is invalid because
the protocol owns the stream. Initialization advertises the actual methods.

The adapter introduced in0.66 provides full text synchronization, compiler
diagnostics, checked expression types, document declarations and definitions
for checked function/constructor calls and lexical value reads. Positions use
UTF-16 code units, with explicit conversion from compiler UTF-8 byte intervals.
CRLF and supplementary Unicode scalars are handled. Invalid positions that
split a surrogate pair are rejected. Diagnostics include the open version;
replaced analysis results never publish for a newer editor version.

The server checks the declared project entry and its reachable imports. Open
files not reachable from a successfully checked entry are analyzed separately.
Edits to imported open files are included, including new unsaved .nex files.
An invalid project provides diagnostics without an obsolete semantic index.
The checker still enforces project/library versions, import containment, locked
dependencies, effects, realms and all ordinary type rules. Analysis does not
grant file, database, network or foreign execution authority.

The compiler command behind the adapter is also usable independently:

```sh
nex analyze /project/main.nex --json
nex analyze /project/main.nex --overlay /private/overlays.json --json
```

An overlay follows `llm/editor-overlay.schema.json`: `nex.overlay/1` with a
`files` object mapping canonical absolute .nex paths to UTF-8 source text.
Unreferenced overlays do not import extra code. Normal root/package containment
checks still apply. Manifests and lock files remain physical inputs; an editor
must save their changes and notify `workspace/didChangeWatchedFiles`.

Default `nex analyze` retains the strict `nex.analysis/1` result, which follows `llm/editor-analysis.schema.json`. It contains
the exact captured files/paths/hashes/text, checked revision, declaration ranges
and typed expression ranges/definition targets. These ranges are source byte
intervals, separate from persistent graph node or operation IDs. Successful
analysis never initializes a Store or writes physical source, history or caches.
Frontend failures retain their diagnostic contract. A captured optional SHA-256
lets the adapter verify the exact source before mapping a diagnostic to text;
historical diagnostic reports can omit that field.

The adapter supports initialize/initialized, shutdown/exit, cancellation and
workspace file-change notifications. Work runs outside the protocol reader;
new edits cancel superseded compiler processes. It bounds each open document
to 1 MiB, all open text to 8 MiB, documents/overlays to 128, input frames/overlay
JSON to 16 MiB, headers to 8 KiB and each compiler analysis to 30 seconds.
The compiler projection bounds source text to 16 MiB and entries to 200000.
Timer scheduling and executor shutdown are serialized. Invalid JSON-RPC
messages receive an error with a null ID; input bodies must be strict UTF-8.
Document symbols cover source functions, struct/enum, trait, impl and endpoint
declarations. No code is executed by hover or definition lookup.

The matching VS Code0.3 client is described in [editor.md](editor.md). It
requires a matching0.68+ compiler/resource set; retain the0.67 SDK/extension0.2
for older language-server installations. The earlier0.67 actual installed IDE
checks retain their exact scope in STATUS.md; current0.68 full SDK/platform/IDE
acceptance is separate. This adapter does not add Windows compiler-host support.
Completion, rename, parser recovery/incremental indexing and the broader IDE
matrix remain pending.

## Checked references

Toolchain0.68 adds `textDocument/references` with a required boolean
`context.includeDeclaration`. Results use exact name-token ranges, canonical
physical file URIs and deterministic ordering. Names are resolved by the checker
and lexical scopes. Identical spelling does not merge different parameters,
locals or structure fields. Constructor calls/patterns currently reference their
nominal structure/enum declaration. Implicit closure capture machinery creates
no invented source occurrence; physical reads inside a closure are included.
A wildcard pattern `_` declares nothing and does not shadow an ordinary outer
value named `_`, matching the checker and all execution backends.

The compiler exposes these data explicitly:

```sh
nex analyze /project/main.nex --references --overlay /private/overlays.json --json
```

This opt-in result is `nex.analysis/2`, described by
`llm/editor-references.schema.json`. It adds exact occurrence intervals,
declaration targets and declaration/read/write/call/pattern roles. Default
`nex analyze` keeps `nex.analysis/1` and its original schema unchanged; clients
must opt into the new projection. The two projections share captured sources,
checked semantics and canonical revision. Neither writes source/graph/cache nor
executes code; source language0.16 and graph formats require no migration.

Builtins without a physical source declaration have no source-reference target.
References cover source function calls/values, parameters and locals (including writes,
lambdas and match bindings), nominal constructor calls/patterns and structure
field reads. Type annotations, trait/implementation syntax and import-alias
references remain pending. The search uses successfully checked project/import
indices and separately checked open files; it does not scan closed unreachable
files or merge unsaved buffers from another client/workspace connection.
Conflicting captured contents/binding contexts fail explicitly. Superseded or
cancelled requests produce no stale locations. Results are bounded to10000
unique locations and8MiB; exceeding either limit fails without a partial result.
Name intervals are converted to UTF-16 in one pass per captured source.

From a checkout, run `python3 tests/lsp.py /absolute/path/to/nex` for actual
compiler/stdio scenarios, including unsaved Unicode diagnostics, cross-file
overlays, history isolation, cancellation and protocol lifecycle failures.

Toolchain0.68 extends the VS Code0.3 client described in editor.md with checked references. Its document versions, cancellation, local size/Unicode guards and trusted physical workspace gate are independent of ordinary debug launches. Actual installed IDE and SDK checks retain exact source/compiler identities.
