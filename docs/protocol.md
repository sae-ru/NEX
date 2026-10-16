# NEX CLI and graph protocol 2

Commands are local and model-independent. The compiler handles parsing, checking and transactions; the invoking LLM produces source or a patch. JSON is ordinary UTF-8 with no provider-specific tool format.

## Discovery and diagnostics

`nex describe --json` returns `nex.language/1`. Its `version` and `features` describe implemented behavior. `not_yet_supported` makes the boundary explicit. Specification and prompt paths are repository-relative.

`nex guide --kind prompt|language|grammar|protocol|web|server|api --json` returns the matching installed document as `nex.guide/1`, with language version and BLAKE3 content hash. This also works outside the compiler's source checkout.

Language 0.4 supports multi-file programs and structured values in `eval --json`: strings, lists, records and tagged result objects are returned as JSON values. Ordinary native application entries return i64/unit; HTTP and native library entries use their explicit contracts. `nex.graph/2` and `nex.context/2` identify definitions by qualified logical module/name. Other response schemas retain their individual versions. Typed wire JSON is separate from eval/display JSON: i64 wire values are decimal strings.

With `--json`, frontend errors return a nonzero process status and an object containing `schema: nex.diagnostic/1`, `ok: false`, `code`, `message`, `file`, `line`, and `column`. File keys identify imported sources; columns count bytes. Runtime process failure from `run --json` is reported as `exit_code`, `stdout`, and `stderr`; native arithmetic/assertion errors currently use a textual diagnostic in stderr. LLVM's own compilation diagnostics also go to stderr. Successful JSON output is written to stdout.

## Source workflow

```sh
nex check src/main.nex --json
nex eval src/main.nex --json
nex test src/main.nex --json
nex build src/main.nex --profile release --json
nex run src/main.nex --json
```

These commands load the selected entry and all reachable imports, check the complete program, then synchronize its source snapshot into graph HEAD. Without an explicit file they use `entry` from the nearest `nex.json`, or `main.nex` in the current directory. Without a manifest the explicit source's directory is its root. Source paths with spaces and Unicode filenames are supported; arguments are passed to tools without a shell. See the language guide for import syntax and `libraries` configuration.

`eval` reports the full i64 result and captured output. Its process exit status reports whether evaluation succeeded. `run` uses the native program's exit status. `run --json` captures its output with a 30-second execution timeout; direct `run` does not impose that capture timeout.

`nex lock [FILE]` records loaded library/standard-library source hashes in the project root's `nex.lock.json`; `-o PATH` selects another output. Source-based commands enforce an existing project lock and return `E_LOCK` for changed or unpinned loaded dependencies. `lock` explicitly refreshes loaded pins after dependency review and retains unused pins for other entry points. Own-project source files are not locked. This is local source pinning; remote package discovery, downloads and version solving are pending.

## Browser workflow

`nex web FILE --directory NEW_DIRECTORY` generates a checked React/TypeScript/Vite application project, including locked package metadata, styles, a renderer, source mapping metadata and Playwright smoke tests. It returns `nex.web/1` with the semantic revision, generated file hashes, content key and output directory. The entry module must satisfy the four-function application contract in `docs/web.md`. Generation does not install packages and requires a new/empty destination.

Toolchain 0.6.0 additionally recognizes an optional pure `commands(State, State, std::web::Event) -> list<std::net::Command>` entry. The generated adapter executes bounded same-origin HTTP/cancel commands and sends typed response envelopes back as events; four-function applications remain supported. This is a versioned tool/standard-library contract without a language-grammar change. The web guide specifies state sequencing, schema validation, credentials, cancellation and resource limits.

`nex build FILE --target web --profile release --json` performs a real package installation, TypeScript check and Vite build, returning `nex.web-build/1` with `directory`, static `dist`, `revision`, `build_key`, `cached`, tool identities and profile. `-o NEW_DIRECTORY` copies the assets. Cache hits verify the complete asset tree's content hashes. Source-based builds enforce dependency pins; `--revision HEAD` builds the archived bundle. Packages use the installed adapter's exact lock. The compiler does not deploy assets or implement an HTTP API. Generated npm scripts provide dev/preview servers and browser tests; direct `nex run`/`debug` currently remain native commands.

`nex emit FILE --kind typescript --entry NAME --directory PATH` writes a standalone checked TypeScript module, runtime and line mapping without requiring the application contract. Without `--directory` it emits only source to stdout or `-o FILE`. Server entries are rejected; only the reachable client/shared closure is emitted. `nex test --target web` compares shared/client tests with the interpreter and reports server tests as skipped. Node-based semantic checks do not replace browser tests.

## Native server and library workflow

`nex build FILE --target server --profile release --json` checks the HTTP contract (entry `handle` by default), emits its reachable native closure and links the HTTP/TLS/SQLite host. Its native build result reports an executable. Launch that binary with `--auth FILE --database FILE`, optional bind/limit/TLS/static arguments from `docs/server.md`, or use `nex run FILE --target server -- ARGS` without `--json`. Ordinary native unit tests check server functions; the server target itself is not a unit-test entry.

`nex token --user USER --auth FILE --json` appends an authentication entry and reports a newly generated bearer token. Only its SHA256 hash is stored, and the update is atomic. It does not deploy/configure a running server.

`nex build FILE --library --entry NAME` emits a host-native static archive and no C main wrapper. The archive contains the selected closure and required runtime components. Its matching trusted host ABI is documented in `docs/server.md`; source-level FFI declarations remain unsupported.

## Bounded context

After establishing a revision with `check`:

```sh
nex context --symbol app::sum
```

The `nex.context/2` object includes the current semantic revision, qualified symbol, local name, owner module, source file, native symbol, source text, the file's import aliases, direct callees' source, callers' qualified names, and needed structure definitions. Source declarations retain local names and import aliases. A model can request another function's context when it needs that file's imports or callers. `--symbol sum` is shorthand for the entry module's `sum`; library functions require their qualified name.

`nex graph -o graph.json` exports `nex.graph/2`: the complete graph, module/import metadata, derived definitions/dependency IDs and a `nex.sources/1` bundle:

```json
{
  "schema": "nex.sources/1",
  "entry": "src/main.nex",
  "files": {
    "src/main.nex": "module app; import \"std/math.nex\" as math; fn main() -> i64 { return math::max(1, 2); }",
    "@std/math.nex": "module std::math; pub fn max(a: i64, b: i64) -> i64 { if a > b { return a; } else { return b; } }"
  }
}
```

Project files have normalized relative keys; library keys use `@std/FILE` or `@pkg/NAME/FILE`. A bundle contains every reachable source and rejects unreachable/missing files and escaping paths. `nex history` lists retained revisions and HEAD. Stored-revision operations use archived source text, independent of live files, configured package roots and live lock files.

## Optimistic patches

```json
{
  "expected_revision": "64-character revision hash from context",
  "replacements": [
    {"name": "app::sum", "source": "fn sum(n: i64) -> i64 { return n; }"}
  ]
}
```

`nex apply --patch patch.json --json` replaces existing function definitions. Each source defines exactly the requested local function, preserving required `pub`, realm, test marker and effects. It cannot inject imports, structures or additional functions. Patch names can be fully qualified or entry-module shorthand; duplicate resolved symbols are rejected. Multiple files can be changed in one patch. The complete candidate bundle is reparsed and checked before a transaction commits. The transaction verifies HEAD against `expected_revision`; stale context returns `E_CONFLICT` and changes nothing.

The patch changes the graph, leaving source files unchanged. To validate/build the graph, use:

```sh
nex test --revision HEAD --json
nex build --revision HEAD --json
nex export --revision HEAD --directory recovered-project
```

Directory export requires a new or empty directory and materializes all archived sources, a manifest, and a dependency lock. It vendors standard/library sources under a collision-free `_nex_deps` directory and maps those roots in the exported manifest, so the project remains usable without the original library installation. Source keys become their paths inside the new project. Run file-based commands from that project's directory to adopt edits. These snapshots include NEX source; asset packaging is not implemented.

For a one-file revision, `nex export --revision HEAD -o PATH` writes just that source; omitting `-o` prints it. Multi-file revisions require `--directory`. `--revision HASH` recovers an earlier source snapshot. Semantically equivalent whitespace/alias/path edits can share a revision represented by its first stored source projection.

`nex import graph.json` requires the current language and `nex.graph/2`. It reparses/checks the archived bundle and recomputes its revision; a mismatched declared revision or conflicting root-source projection is rejected. Derived nodes are regenerated. Node IDs are allocated in the destination store, with stable identity for the same logical module/local name within that store, including when another entry imports the module. Portable ID reconciliation is pending.

## Language/database migration

The graph database migrates schema 1 to schema 2 transactionally, retaining stored sources and recording older revisions as language 0.1. Stored 0.1/0.2 source is preserved and wrapped as a single-file bundle on recovery/migration; 0.3/0.4 bundles retain all their files. Current language is 0.5. Viewing/building an old-language graph requires explicit migration; export remains available for recovery. Newly reserved builtin names can require explicit source edits.

`nex migrate --json` reparses and checks the archived HEAD under the current language, atomically adopts its new revision if HEAD is unchanged, and preserves the old revision. `--revision HASH` selects another retained snapshot. `nex migrate GRAPH.json --json` accepts legacy `nex.graph/1` single-file source or a `nex.graph/2` bundle and explicitly adopts its checked source. That operation treats the old hash as declared metadata, not as a verified current hash. Ordinary `import` rejects a language mismatch or an incorrect recomputed revision. Migration does not overwrite source files; materialize the chosen result with `export`.

Structure definitions currently change through the source workflow. Function replacement patches preserve the source's structure definitions and recheck all affected types.

## Build artifacts and debugging

Build output lives under `.nex/build/KEY/`, including an immutable entry `source.nex`, imported files in `sources/`, `source-bundle.json`, `program.mlir`, `program.ll`, object files, `app`, `build.json` and a completion marker. A whole-program build key includes the semantic revision, complete source bundle/path, NEX compiler build fingerprint, native compiler identity, profile, target, runtime source, entry and relevant SDK environment. A cache hit checks the executable's content hash. This is currently whole-program caching; separate compilation of unaffected modules/functions is pending.

Native emission now includes the selected entry's reachable closure. Runtime components are captured into `runtime-inputs/` and their verified object cache is shared within the project's build directory. Wire/SQLite/HTTP components link only when needed; SQLite/OpenSSL dependency contents participate in relevant keys. `--library` produces `libnex.a` instead of app. This runtime-object reuse does not yet implement separate NEX function compilation.

Native build JSON reports `kind` (`executable`, `static_library`, `http_server`), `metadata` (the `build.json` path) and `notices` (empty if no vendored runtime component requires it). Metadata includes `runtime_components` and `runtime_source_projection`. Builds embedding JSON/HTTP code emit matching MIT license texts beside the artifact and validate that file on cache hits. `-o PATH` copies these notices to `PATH.THIRD_PARTY_NOTICES.txt`; keep them with the distributed program/archive. External toolchain/runtime-library packaging remains separate work.

`nex emit FILE --kind mlir` emits high-level MLIR. `--kind llvm` builds and exposes lowered LLVM IR. `nex build FILE -o PATH` copies the executable to the chosen path. Profiles are `debug` (-O0 with symbols), `profile` (-O2 with symbols/frame pointers), and `release` (-O2 with symbols). Instrumented profiling is pending; the profile build option does not claim a completed profiler.

```sh
nex context --symbol app::sum
nex debug src/main.nex -- -o 'breakpoint set --name nex_3_app_3_sum'
```

Use `native_symbol` from context or the graph for the exact debugger name. Qualified NEX symbols have length-prefixed native components, avoiding collisions among module names. Source line information, including imported files, is emitted through MLIR's LLVM debug scope pass. Full NEX expression evaluation and local-variable formatters are pending.

## Endpoint operations

Language 0.5 adds endpoint declarations to the checked source bundle and program identity (nex.program/4). `graph` exposes an endpoints array with stable IDs, handler-node IDs, canonical definitions and source locations. `context --symbol ENDPOINT` returns nex.context/2 with kind endpoint, its source/imports/checked contract, handler source and referenced models. Function callers also include referring endpoint names. The existing atomic replacements format accepts one endpoint declaration or function per named replacement and rechecks the whole bundle.

`nex api FILE --json` returns nex.api/1 with checked method/path/status/effects, optional input and result wire schemas, and generated helper names. `--revision HASH` uses only archived sources. Add `--directory NEW_DIRECTORY` to generate both projects and api.json/openapi.json. The nex.api-generation/1 result reports directory, server_entry, client_entry, contract and openapi paths. Both candidate projects pass the normal loader/checker before final materialization. Generated projects contain matching dependency locks; server code is absent from the client SDK's application model files. See docs/api.md for HTTP semantics and typed browser validation.
