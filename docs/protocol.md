# NEX CLI and graph protocol 2

Commands are local and model-independent. The compiler handles parsing, checking and transactions; the invoking LLM produces source or a patch. JSON is ordinary UTF-8 with no provider-specific tool format.

## Discovery and diagnostics

`nex describe --json` returns `nex.language/1`. Its `version` and `features` describe implemented behavior. `not_yet_supported` makes the boundary explicit. Specification and prompt paths are repository-relative.

`nex guide --kind prompt|language|grammar|protocol|web|server|api|debug|build|profile|verify|task|expression --json` returns the matching installed document as `nex.guide/1`, with language version and BLAKE3 content hash. This also works outside the compiler's source checkout.

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

Build output lives under `.nex/build/KEY/`, including an immutable entry `source.nex`, imported files in `sources/`, `source-bundle.json`, `program.mlir`, `program.ll`, object files, `app`, `build.json` and a completion marker. A whole-program build key includes the semantic revision, complete source bundle/path, NEX compiler build fingerprint, native compiler identity, profile, target, runtime source, entry and relevant SDK environment. Cache hits validate the executable and its aggregate IR, compilation/build metadata, source bundle, selected NEX objects and debug artifacts. Toolchain 0.9 adds independently reused module objects and immutable source-cache projections; the complete frontend still rechecks the loaded graph.

Native emission now includes the selected entry's reachable closure. Runtime components are captured into `runtime-inputs/` and their verified object cache is shared within the project's build directory. Wire/SQLite/HTTP components link only when needed; SQLite/OpenSSL dependency contents participate in relevant keys. `--library` produces `libnex.a` instead of app. NEX modules now have a separate verified object cache; function-level reuse and cross-unit LTO remain pending.

Native build JSON reports `kind` (`executable`, `static_library`, `http_server`), `metadata` (the `build.json` path) and `notices` (empty if no vendored runtime component requires it). Metadata includes `runtime_components` and `runtime_source_projection`. Builds embedding JSON/HTTP code emit matching MIT license texts beside the artifact and validate that file on cache hits. `-o PATH` copies these notices to `PATH.THIRD_PARTY_NOTICES.txt`; keep them with the distributed program/archive. External toolchain/runtime-library packaging remains separate work.

`nex emit FILE --kind mlir` emits high-level MLIR. `--kind llvm` builds and exposes lowered LLVM IR. `nex build FILE -o PATH` copies the executable to the chosen path. Profiles are `debug` (-O0 with symbols), `profile` (-O2 with symbols/frame pointers and native function/managed shallow allocation instrumentation), and `release` (-O2 with symbols). See the profiling protocol below for local reports and the matching guide for optional Tracy capture.

```sh
nex context --symbol app::sum
nex debug src/main.nex -- -o 'breakpoint set --name nex_3_app_3_sum'
```

Use `native_symbol` from context or the graph for the exact debugger name. Qualified NEX symbols have length-prefixed native components, avoiding collisions among module names. Source line information, including imported files, is emitted through MLIR's LLVM debug scope pass. Toolchain 0.8 adds real typed parameter/local records, lexical binding scopes, bounded LLDB previews and a read-only `nex-values` frame report. `nex debug FILE --kind dap --json` and `nex debug FILE --json` return `nex.debug-session/1` with `adapter`, matching `manifest` and an editor `launch` configuration. Plain `nex debug` loads the captured views and launches LLDB. `nex.debug-values/1` reports revision/function/file/line and bounded `{name,type,value}` previews; duplicate shadowed names stay separate. Native build JSON adds `debug_manifest`. Debug artifacts and source projections are checked on cache hits. Full NEX expression evaluation remains pending. See [the debugging guide](debugging.md).

## Endpoint operations

Language 0.5 adds endpoint declarations to the checked source bundle and program identity (nex.program/4). `graph` exposes an endpoints array with stable IDs, handler-node IDs, canonical definitions and source locations. `context --symbol ENDPOINT` returns nex.context/2 with kind endpoint, its source/imports/checked contract, handler source and referenced models. Function callers also include referring endpoint names. The existing atomic replacements format accepts one endpoint declaration or function per named replacement and rechecks the whole bundle.

`nex api FILE --json` returns nex.api/1 with checked method/path/status/effects, optional input and result wire schemas, and generated helper names. `--revision HASH` uses only archived sources. Add `--directory NEW_DIRECTORY` to generate both projects and api.json/openapi.json. The nex.api-generation/1 result reports directory, server_entry, client_entry, contract and openapi paths. Both candidate projects pass the normal loader/checker before final materialization. Generated projects contain matching dependency locks; server code is absent from the client SDK's application model files. See docs/api.md for HTTP semantics and typed browser validation.

## Native compilation report

Native `build --json` adds `compilation`, `compiled_modules` and `reused_modules`. Counters describe this invocation; whole-build hits compile zero units. `compilation` names `nex.compilation/1`, recording the last materialization with module/function names, input/content keys, split toolchain/semantic/source/runtime-ABI fingerprints, source/object/MLIR/LLVM paths, object hashes and per-unit reuse. It includes direct/reverse function dependencies and module call/layout providers/consumers. Type-only modules can appear as providers without emitting an object. `build.json` links this report and records the actual driver `compiler_target` and `data_layout`. The driver ABI is probed and must match the configured 64-bit host. See [incremental.md](incremental.md) for validation and cache boundaries.

## Native profiling protocol

`nex profile FILE [--revision HASH] [--entry NAME] [--events COUNT] [--timeout SECONDS] [--scenario TEXT] [-o REPORT.json] --json` selects the instrumented host-native build. Events range from 0 to 1,000,000; timeout is 1 to 3,600 seconds. Non-profile modes and web/server targets are rejected by this run command. Long-running servers and trusted archives instead use `nex build --profile profile` with the environment described in `docs/profiling.md`.

The result is `nex.profile-session/1`, with process exit status/output, `revision`, `build_key`, workload/host metadata, memory pools and at most 100 functions ordered by `self_ns`; `total_functions` reports the complete count. `output` names a complete `nex.profile/1` JSON file containing all aggregates and Chrome-compatible `traceEvents`. Timings are elapsed wall nanoseconds including instrumentation; allocation bytes are shallow managed structure sizes. Dropped-record fields expose collector bounds. Function `node_id` is attributed only after name/content-hash matching against the selected revision. Failing applications return their nonzero exit status with a usable profile when normal runtime trap flushing succeeds. The matching guide is `nex guide --kind profile --json`.

## Scalar verification protocol

`nex contract FILE --symbol NAME [-o CONTRACT.json] --json` produces a `nex.verification-contracts/1` scaffold tied to semantic revision, exact source-bundle hash, function content and loop coordinates. `nex verify FILE --contracts CONTRACT.json [--revision HASH] [--symbol NAME] --json` verifies all listed roots or the selected root. Use `--solver-timeout MS`, `--resource-limit COUNT` and `--timeout SECONDS` for the bounded solver/run work. Source-language version remains 0.5.

The CLI returns `nex.verification-session/1`; `output` identifies the complete `nex.verification/1` report and source/contract/query artifacts. Each function has its current project node ID and status: proven, counterexample, inconsistent_preconditions, unknown, timeout or unsupported. Only all-proven is exit 0. Counterexample i64 values are decimal strings; booleans are JSON booleans. Inductive-state witnesses are not necessarily reachable inputs. CLI details retain at most 32 non-success obligations per function; the saved report keeps all. See `nex guide --kind verify --json` and `llm/verification.schema.json` for contract fields, exact semantics, limits and proof trust boundaries.

## Task acceptance protocol

`nex task SOURCE --kind init [-o TASK.json]` scaffolds `nex.task/1`. `nex task TASK.json --kind check` returns `nex.task-check/1` with its canonical task hash, checked candidate revisions and statically linked graph bindings. It does not execute tests or build outputs. `--revision HASH` selects one archived program; `--candidates FILE` maps program IDs to archived revisions. `--task-hash HASH` rejects changed acceptance intent. Candidate capture does not move project HEAD.

`--kind run` returns a bounded `nex.task-session/1` with check/requirement outcomes and `output` pointing to the full `nex.task-receipt/1`. The receipt preserves artifact indexes, source/resource input manifests, logs and measurements. Passed requires all checks; unsupported, failed, unproven, skipped and interrupted work never passes. `--kind history` returns `nex.task-history/1`, at most 50 checkpointed runs. A stored running state is not a process-liveness check. `--kind replay` takes a receipt path, verifies captured inputs/compiler/trusted executable resources and reruns in a new directory. It ignores prior pass claims and absolute output paths as execution inputs.

`nex contract --kind intent --contracts FILE` returns `nex.verification-intent/1` and `intent_hash`. Task verification fixes these pre/postconditions while rebasing only source/revision/function hashes in a separate derived contract. Loop annotations remain checked proof strategy. `nex test --symbol NAME` selects one test and rejects ordinary functions. `--build-directory PATH` selects a build workspace (default remains project `.nex/build`), allowing task workspaces to reuse validated module objects.

See `docs/tasks.md` and `llm/task.schema.json` for fields, bounds, POSIX group cleanup, hardware budgets, external-tool trust and replay limitations. Static linkage is not dynamic coverage or proof of prose requirements. Source language/graph protocol remain 0.5/2.

## Stopped-frame expressions

`nex debug FILE --kind nex-dap --json` retains `nex.debug-session/1` and adds an explicit `adapter_command` for the frozen stdio bridge. Legacy direct sessions retain adapter lldb-dap and gain `nex_adapter` with the bridge command/launch data. Clients must register that command for launch type nex; this is not an automatically installed editor extension. `NEX_LLDB_DAP`/`NEX_PYTHON` select trusted development executables.

`nex inspect [FRAME.json] --manifest DEBUG.json --expression TEXT [--kind plan|value] --json` checks matching compiler/build/source/frame identity, source-module visibility, types, effects and realms. Without a filename it reads a frame from stdin. Plan returns `nex.expression-plan/1` with referenced names/types/wire schemas; value returns `nex.expression/1` with exact typed wire value, bounded display, read names, stop metadata and limits. Errors use the normal diagnostic schema and nonzero status. Graph HEAD is not opened or modified.

`nex-frame EXPR` exports `nex.debug-frame/2`; `nex-eval EXPR` evaluates against freshly captured values. The compiler still accepts full `nex.debug-frame/1` snapshots. Version 2 adds a bounded `captures` array of `{binding,path,kind,value|unavailable}` entries. The checked path selects record fields, list indices or result `ok`/`code`/`message`. Shape reads carry an exact list length, nominal record name or result tag. Value reads carry a complete typed value at that path.

`inspect --kind demand` interprets the pure expression until the first missing read and returns `nex.expression-demand/1` with a typed `request`. A capture provider reads that path from the same stopped frame and replays; normal completion is `nex.expression/1`. Ordinary value mode fails on missing reads. This supports dynamic indexing and pure helper calls without inspecting unrelated payloads. Raw JSON, frame/build identity, path types, uniqueness, shapes and wire values remain checked. Complete values may satisfy their descendants; full binding values cannot be mixed with captures for that binding. Unused unavailable values do not break short-circuiting.

Wire i64 values and shape lengths are canonical decimal strings; previews never become evaluator input. NEX DAP evaluate responses add `body.nex` with the full structured result and actual read paths, while normal DAP fields supply type, display, immutable children and paging. References expire on execution/new stops; source is encoded as a single internal command argument. The compiler's pure interpreter and its resource limits run outside the inferior. See docs/expressions.md and both llm/debug-frame schema files for limits, unsupported whole-value/string reads and provenance/host boundaries.

## Operation graph (toolchain 0.15)

`nex operations --symbol NAME [--offset N] [--limit N] --json` returns `nex.operations/1`. `nex context --operation ID` or `--site KEY` returns `nex.operation-context/1`, with explicit revision/source identity and ancestors. Both use saved HEAD unless `--revision` selects an archive; they do not advance HEAD. `nex.graph/2` includes an additive complete `operation_graph`. Matching is local to the store; imports derive new IDs from checked sources and ignore foreign identities. The operation guide/schema define paging, omitted data and conservative identity rules.

Interpreter `eval` failures from checked operations add `operation_id`, `operation_site`, `revision` and `source_hash` to `nex.diagnostic/1`. Source-only frontend errors retain their existing fields. TypeScript trap sites add an optional fourth deterministic key. Native manifests/MLIR carry source-site metadata, and stopped LLDB/DAP REPL `nex-operation` returns `nex.debug-operation/1` candidates. Native textual runtime failures and optimized-PC attribution remain limited as described in the operation guide.
