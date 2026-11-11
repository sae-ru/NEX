# NEX language server: development toolchain 0.192

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

The matching VS Code0.5 client is described in [editor.md](editor.md). Its
server requires matching0.70 compiler/resources and analysis/3; retain the
matching older SDK/extension for an older installation. The earlier0.67 actual installed IDE
checks retain their exact scope in STATUS.md; current0.68 full SDK/platform/IDE
acceptance is separate. This adapter does not add Windows compiler-host support.
Toolchain 0.192 adds `textDocument/formatting`: the server formats the open
document through the same checked source formatter, returns one full-document
`TextEdit`, returns an empty array when already formatted, and never writes the
physical file. Completion, rename, parser recovery/incremental indexing and the
broader IDE matrix remain pending.

## Checked references

Toolchain0.68 adds `textDocument/references` with a required boolean
`context.includeDeclaration`. Results use exact name-token ranges, canonical
physical file URIs and deterministic ordering. Names are resolved by the checker
and lexical scopes. Identical spelling does not merge different parameters,
locals or structure fields. Structure calls/patterns reference their nominal declaration. From0.69, enum
constructor calls/patterns reference the exact variant declaration; the enum
qualifier separately references its type. Implicit closure capture machinery creates
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
field reads. Toolchain0.69 also covers nominal annotations and explicit type
arguments, lexical generic parameters (including constructor parameters), trait
bounds, associated type/method contracts, implementation bindings, endpoint
handler names and file-local import aliases. In `m::Content<T>::get`, `m`,
`Content`, `T` and `get` retain separate targets. A trait method points to its
source contract; the implementation's explicit RHS names the selected ordinary
function. Implicit `Self` uses point to the trait name, while written
`Self<_>` uses point to that explicit `Self` token. Constructor placeholders
and builtin bounds create no physical declarations. Different generic scopes
never merge by spelling. Parser/module-binder metadata is opt-in and excluded
from Type equality, source/semantic serialization and revision hashes.

The strict analysis/1 and analysis/2 shapes and roles remain unchanged. In
analysis/2, exact occurrence targets take precedence for LSP definitions;
legacy expression-definition fields retain their earlier behavior. Toolchain0.70
adds the separate identifier-description contract below. Complete rename,
parser recovery and incremental indexing remain pending. The search uses successfully checked project/import
indices and separately checked open files; it does not scan closed unreachable
files or merge unsaved buffers from another client/workspace connection.
Conflicting captured contents/binding contexts fail explicitly. Superseded or
cancelled requests produce no stale locations. Results are bounded to10000
unique locations and8MiB; exceeding either limit fails without a partial result.
Name intervals are grouped by file in one pass and converted to UTF-16 in one
pass per captured source. Cancellation also applies during grouping/conversion.

From a checkout, run `python3 tests/lsp.py /absolute/path/to/nex` for actual
compiler/stdio scenarios, including unsaved Unicode diagnostics, cross-file
overlays, history isolation, cancellation and protocol lifecycle failures.

Toolchain0.68 extends the VS Code0.3 client described in editor.md with checked references. Its document versions, cancellation, local size/Unicode guards and trusted physical workspace gate are independent of ordinary debug launches. Actual installed IDE and SDK checks retain exact source/compiler identities.

## Exact identifier descriptions

Toolchain0.70 uses a new explicit projection for hover and definitions:

```sh
nex analyze /project/main.nex --details --overlay /private/overlays.json --json
```

It returns `nex.analysis/3` following `llm/editor-identifiers.schema.json`.
`--details` and `--references` are mutually exclusive; default analysis/1 and
explicit analysis/2 keep their original strict schemas. Analysis/3 retains the
same captured files, canonical revision, symbol and expression fields, adds the
checked occurrences and an `identifiers` array. Signature parameters and enum
payload fields also receive their real physical declaration occurrences here.
These source metadata never enter source serialization, Type equality or graph IDs.

Every actual lexer word token receives an exact file/byte range, `kind`,
`detail` and `definition`. Semantic descriptions come from parsed/bound source
declarations and checked value types. Functions show their qualified source
signature with generic arity/bounds, realm, visibility and effects. Generic call
hover keeps the source template signature; a concrete field read can show its
checked instantiated value type. Source generic parameters, nominal headers,
variants/payload fields, aliases, traits, associated members and implementation
bindings retain their own meanings. A trait method describes its source
contract, including on an implementation's left-hand binding. The ordinary
function on the right retains its own signature. An implicit trait `Self` has a
distinct description while its physical target remains the trait anchor.

Builtin type/constructor and constraint tokens have a description and a null
physical definition. Genuine builtin function calls show the builtin name and
checked result type, without inventing a source declaration or full signature.
Boolean words show `bool`. Other syntax words have null descriptions and null
definitions. These nulls are intentional: the LSP must not substitute the type
or declaration of a containing expression. Thus `i64` in `id<i64>(42)` cannot
navigate to `id`, and `return` has no function-type hover. Literal/punctuation
positions outside word tokens retain the earlier expression fallback.

The selected word, target and captured contents must agree across checked
entries; a conflict fails explicitly. UTF-8 intervals convert to exact UTF-16
ranges, and cancellation/version checks apply during lookup. The projection
shares the 200000 combined-entry/16MiB captured-source bounds, and additionally
bounds each detail to16KiB of UTF-8 and the compact identifiers JSON array,
including separators, to8MiB. An exceeded bound fails without a partial result.
No source, Store, cache or application execution is performed. Readonly
metadata does not authorize rename or graph synchronization. Closed unreachable
files, cross-workspace buffers, completion/rename and parser recovery/incremental
indexing remain pending; validation scope is recorded in STATUS.md.
