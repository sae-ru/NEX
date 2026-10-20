# NEX language server: development toolchain 0.66

`nex lsp` runs a stdio [Language Server Protocol 3.17](https://github.com/microsoft/language-server-protocol/blob/gh-pages/_specifications/lsp/3.17/specification.md)
adapter using Python 3.9+ and the selected compiler. Its standard output contains
only Content-Length-framed JSON-RPC. Use it from a trusted physical workspace
with a compatible editor/client; it needs no network, model or provider SDK.
`NEX_PYTHON` selects the Python executable. `nex lsp --json` is invalid because
the protocol owns the stream. Initialization advertises the actual methods.

The development implementation provides full text synchronization, compiler
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

The `nex.analysis/1` result follows `llm/editor-analysis.schema.json`. It contains
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

This development adapter is separate from the existing VS Code debugger.
VS Code language-client activation and actual IDE acceptance, completion,
references, rename, type-annotation/field navigation, parser recovery,
incremental project indexing and the broader IDE/platform matrix remain pending.
The compiler and installed-SDK verification have their own recorded source and
binary scopes. This adapter does not make Windows a supported compiler host.

From a checkout, run `python3 tests/lsp.py /absolute/path/to/nex` for actual
compiler/stdio scenarios, including unsaved Unicode diagnostics, cross-file
overlays, history isolation, cancellation and protocol lifecycle failures.
