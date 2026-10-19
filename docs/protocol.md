# NEX CLI and graph protocol 2

Commands are local and model-independent. The compiler handles parsing, checking and transactions; the invoking LLM produces source or a patch. JSON is ordinary UTF-8 with no provider-specific tool format.

## Discovery and diagnostics

`nex describe --json` returns `nex.language/1`. Its `version` and `features` describe implemented behavior. `not_yet_supported` makes the boundary explicit. Specification and prompt paths are repository-relative.

`nex guide --kind prompt|language|grammar|protocol|web|server|api|debug|build|profile|verify|task|expression --json` returns the matching installed document as `nex.guide/1`, with language version and BLAKE3 content hash. This also works outside the compiler's source checkout.

Language 0.4 supports multi-file programs and structured values in `eval --json`: strings, lists, records and tagged result objects are returned as JSON values. Ordinary native application entries return i64/unit; HTTP and native library entries use their explicit contracts. `nex.graph/2` and `nex.context/2` identify definitions by qualified logical module/name. Other response schemas retain their individual versions. Typed wire JSON is separate from eval/display JSON: i64 wire values are decimal strings.

With `--json`, frontend errors return a nonzero process status and an object containing `schema: nex.diagnostic/1`, `ok: false`, `code`, `message`, `file`, `line`, and `column`. File keys identify imported sources; columns count bytes. Runtime process failure from `run --json` is reported as `exit_code`, `stdout`, and `stderr`; native arithmetic/assertion failures retain a textual line and bounded operation records as described below. LLVM's own compilation diagnostics also go to stderr. Successful JSON output is written to stdout.

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

`nex build FILE --library --entry NAME` emits a native static archive and no C main wrapper. The archive contains the selected closure and required runtime components. Its matching trusted runtime ABI is documented in `docs/server.md`; source-level FFI declarations remain unsupported.

Native `build` and `emit --kind llvm` accept `--target TRIPLE` or `--toolchain FILE` (`nex.toolchain/1`, schema `llm/toolchain.schema.json`). A manifest also works with `--target server`. Configured targets are the 64-bit host ABI and macOS arm64/x86_64 cross-builds on macOS. Build responses add `target`, `compiler_target`, `host_compatible`; the same ABI/SDK flags apply to generated and runtime objects and linking. Foreign `run/test/debug/profile` fail with E_TARGET_RUN, absent target dependencies with E_TARGET_LIBRARY, invalid configurations with E_TOOLCHAIN. See `nex guide --kind build` for SDK/dependency selection, metadata, cache isolation and execution-verification limits.

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

`nex apply --patch patch.json --json` replaces existing function, endpoint and (toolchain 0.45) source struct/enum definitions. Each source defines exactly the requested local declaration; include the required `pub`, realm, test marker and effects. Optional `kind` is `function`, `endpoint` or `type` and must match the selected definition. Additional top-level definitions and imports cannot be injected. Patch names can be fully qualified or entry-module shorthand; duplicate resolved symbols and unknown JSON fields are rejected. Multiple files and definition kinds can change in one patch. The complete candidate bundle is reparsed and checked before a transaction commits. HEAD is checked before preparing the candidate and again inside the write transaction; stale context returns `E_CONFLICT` and changes nothing. The revision must be a lowercase 64-character digest.

Type replacements preserve logical type IDs and retained snapshots. Generic instances are derived: patch their source template together with affected constructors, signatures and matches. Struct-to-enum changes are allowed when the complete replacement bundle type-checks. See [the graph guide](graph.md) and `examples/type-patches`.

The patch changes the graph, leaving source files unchanged. To validate/build the graph, use:

```sh
nex test --revision HEAD --json
nex build --revision HEAD --json
nex export --revision HEAD --directory recovered-project
```

Directory export requires a new or empty directory and materializes all archived sources, a manifest, and a dependency lock. It vendors standard/library sources under a collision-free `_nex_deps` directory and maps those roots in the exported manifest, so the project remains usable without the original library installation. Source keys become their paths inside the new project. Run file-based commands from that project's directory to adopt edits. These snapshots include NEX source; asset packaging is not implemented.

For a one-file revision, `nex export --revision HEAD -o PATH` writes just that source; omitting `-o` prints it. Multi-file revisions require `--directory`. `--revision HASH` recovers an earlier source snapshot. Semantically equivalent whitespace/alias/path edits can share a revision represented by its first stored source projection.

`nex import graph.json` requires the current language and `nex.graph/2`. It reparses/checks the archived bundle and recomputes its revision; a mismatched declared revision or conflicting root-source projection is rejected. Derived nodes are regenerated. Node IDs are allocated in the destination store, with stable identity for the same logical module/local name within that store, including when another entry imports the module. Toolchain 0.44 adds explicit snapshot-scoped identity reconciliation after import; see [the graph guide](graph.md). Import itself ignores foreign identity claims.

## Language/database migration

The graph database migrates schema 1 to schema 2 transactionally, retaining stored sources and recording older revisions as language 0.1. Stored 0.1/0.2 source is preserved and wrapped as a single-file bundle on recovery/migration; 0.3/0.4 bundles retain all their files. Current language is 0.15. Viewing/building an old-language graph requires explicit migration; export remains available for recovery. Newly reserved builtin names can require explicit source edits.

`nex migrate --json` reparses and checks the archived HEAD under the current language, atomically adopts its new revision if HEAD is unchanged, and preserves the old revision. `--revision HASH` selects another retained snapshot. `nex migrate GRAPH.json --json` accepts legacy `nex.graph/1` single-file source or a `nex.graph/2` bundle and explicitly adopts its checked source. That operation treats the old hash as declared metadata, not as a verified current hash. Ordinary `import` rejects a language mismatch or an incorrect recomputed revision. Migration does not overwrite source files; materialize the chosen result with `export`.

Structure definitions currently change through the source workflow. Function replacement patches preserve the source's structure definitions and recheck all affected types.

## Build artifacts and debugging

Build output lives under `.nex/build/KEY/`, including an immutable entry `source.nex`, imported files in `sources/`, `source-bundle.json`, `program.mlir`, `program.ll`, object files, `app`, `build.json` and a completion marker. A whole-program build key includes the semantic revision, complete source bundle/path, NEX compiler build fingerprint, native compiler identity, profile, target, runtime source, entry and relevant SDK environment. Cache hits validate the executable and its aggregate IR, compilation/build metadata, source bundle, selected NEX objects and debug artifacts. Toolchain 0.9 adds independently reused module objects and immutable source-cache projections; the complete frontend still rechecks the loaded graph.

Native emission includes the selected entry's reachable closure. Runtime components are captured into `runtime-inputs/` and their verified object cache is shared within the project's build directory. Wire/SQLite/HTTP components link only when needed; SQLite/OpenSSL dependency contents participate in relevant keys. `--library` produces `libnex.a` instead of app. Toolchain 0.25 gives each concrete function/closure/specialization a verified object; frontend reuse and cross-unit LTO remain pending.

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

Native `build --json` adds `compilation`, `compiled_functions`, `reused_functions`, `compiled_modules` and `reused_modules`. Counters describe this invocation; whole-build hits compile zero units. A module counts as compiled when any selected function was compiled, otherwise reused. `compilation` names `nex.compilation/1` with `granularity: function`, recording the last materialization with qualified function identities, source modules, input/content keys, split toolchain/semantic/source/runtime-ABI fingerprints, virtual debug paths, source/object/MLIR/LLVM paths, object hashes and per-function reuse. It includes direct/reverse function dependencies and module call/layout providers/consumers. Type-only modules can appear as providers without emitting an object. `build.json` links this report and records the actual driver `compiler_target` and `data_layout`. The driver ABI is probed and must match the configured 64-bit host. See [incremental.md](incremental.md) for validation and cache boundaries.

## Native profiling protocol

`nex profile FILE [--revision HASH] [--entry NAME] [--events COUNT] [--timeout SECONDS] [--scenario TEXT] [-o REPORT.json] --json` selects the instrumented host-native build. Events range from 0 to 1,000,000; timeout is 1 to 3,600 seconds. Non-profile modes and web/server targets are rejected by this run command. Long-running servers and trusted archives instead use `nex build --profile profile` with the environment described in `docs/profiling.md`.

The result is `nex.profile-session/1`, with process exit status/output, `revision`, `build_key`, workload/host metadata, memory pools and at most 100 functions ordered by `self_ns`; `total_functions` reports the complete count. `output` names a complete `nex.profile/1` JSON file containing all aggregates and Chrome-compatible `traceEvents`. Timings are elapsed wall nanoseconds including instrumentation; allocation bytes are shallow managed structure sizes. Dropped-record fields expose collector bounds. Function `node_id` is attributed only after name/content-hash matching against the selected revision. Failing applications return their nonzero exit status with a usable profile when normal runtime trap flushing succeeds. The matching guide is `nex guide --kind profile --json`.

## Scalar verification protocol

`nex contract FILE --symbol NAME [-o CONTRACT.json] --json` produces a `nex.verification-contracts/1` scaffold tied to semantic revision, exact source-bundle hash, function content and loop coordinates. `nex verify FILE --contracts CONTRACT.json [--revision HASH] [--symbol NAME] --json` verifies all listed roots or the selected root. Use `--solver-timeout MS`, `--resource-limit COUNT` and `--timeout SECONDS` for the bounded solver/run work. Current source-language version is 0.9.

The CLI returns `nex.verification-session/1`; `output` identifies the complete `nex.verification/1` report and source/contract/query artifacts. Each function has its current project node ID and status: proven, counterexample, inconsistent_preconditions, unknown, timeout or unsupported. Only all-proven is exit 0. Counterexample i64 values are decimal strings; booleans are JSON booleans. Inductive-state witnesses are not necessarily reachable inputs. CLI details retain at most 32 non-success obligations per function; the saved report keeps all. See `nex guide --kind verify --json` and `llm/verification.schema.json` for contract fields, exact semantics, limits and proof trust boundaries.

## Task acceptance protocol

`nex task SOURCE --kind init [-o TASK.json]` scaffolds `nex.task/1`. `nex task TASK.json --kind check` returns `nex.task-check/1` with its canonical task hash, checked candidate revisions and statically linked graph bindings. It does not execute tests or build outputs. `--revision HASH` selects one archived program; `--candidates FILE` maps program IDs to archived revisions. `--task-hash HASH` rejects changed acceptance intent. Candidate capture does not move project HEAD.

`--kind run` returns a bounded `nex.task-session/1` with check/requirement outcomes and `output` pointing to the full `nex.task-receipt/1`. The receipt preserves artifact indexes, source/resource input manifests, logs and measurements. Passed requires all checks; unsupported, failed, unproven, skipped and interrupted work never passes. `--kind history` returns `nex.task-history/1`, at most 50 checkpointed runs. A stored running state is not a process-liveness check. `--kind replay` takes a receipt path, verifies captured inputs/compiler/trusted executable resources and reruns in a new directory. It ignores prior pass claims and absolute output paths as execution inputs.

`nex contract --kind intent --contracts FILE` returns `nex.verification-intent/1` and `intent_hash`. Task verification fixes these pre/postconditions while rebasing only source/revision/function hashes in a separate derived contract. Loop annotations remain checked proof strategy. `nex test --symbol NAME` selects one test and rejects ordinary functions. `--build-directory PATH` selects a build workspace (default remains project `.nex/build`), allowing task workspaces to reuse validated module objects.

See `docs/tasks.md` and `llm/task.schema.json` for fields, bounds, POSIX group cleanup, hardware budgets, external-tool trust and replay limitations. Static linkage is not dynamic coverage or proof of prose requirements. Current source language/graph protocol are 0.15/2.

## Stopped-frame expressions

`nex debug FILE --kind nex-dap --json` retains `nex.debug-session/1` and adds an explicit `adapter_command` for the frozen stdio bridge. Legacy direct sessions retain adapter lldb-dap and gain `nex_adapter` with the bridge command/launch data. Clients must register that command for launch type nex; this is not an automatically installed editor extension. `NEX_LLDB_DAP`/`NEX_PYTHON` select trusted development executables.

`nex inspect [FRAME.json] --manifest DEBUG.json --expression TEXT [--kind plan|value] --json` checks matching compiler/build/source/frame identity, source-module visibility, types, effects and realms. Without a filename it reads a frame from stdin. Plan returns `nex.expression-plan/1` with referenced names/types/wire schemas; value returns `nex.expression/1` with exact typed wire value, bounded display, read names, stop metadata and limits. Errors use the normal diagnostic schema and nonzero status. Graph HEAD is not opened or modified.

`nex-frame EXPR` exports `nex.debug-frame/2`; `nex-eval EXPR` evaluates against freshly captured values. The compiler still accepts full `nex.debug-frame/1` snapshots. Version 2 adds a bounded `captures` array of `{binding,path,kind,value|unavailable}` entries. The checked path selects record fields, list indices or result `ok`/`code`/`message`. Shape reads carry an exact list length, nominal record name or result tag. Value reads carry a complete typed value at that path.

`inspect --kind demand` interprets the pure expression until the first missing read and returns `nex.expression-demand/1` with a typed `request`. A capture provider reads that path from the same stopped frame and replays; normal completion is `nex.expression/1`. Ordinary value mode fails on missing reads. This supports dynamic indexing and pure helper calls without inspecting unrelated payloads. Raw JSON, frame/build identity, path types, uniqueness, shapes and wire values remain checked. Complete values may satisfy their descendants; full binding values cannot be mixed with captures for that binding. Unused unavailable values do not break short-circuiting.

Wire i64 values and shape lengths are canonical decimal strings; previews never become evaluator input. NEX DAP evaluate responses add `body.nex` with the full structured result and actual read paths, while normal DAP fields supply type, display, immutable children and paging. References expire on execution/new stops; source is encoded as a single internal command argument. The compiler's pure interpreter and its resource limits run outside the inferior. See docs/expressions.md and both llm/debug-frame schema files for limits, unsupported whole-value/string reads and provenance/host boundaries.

## Operation graph (toolchain 0.15)

`nex operations --symbol NAME [--offset N] [--limit N] --json` returns `nex.operations/1`. `nex context --operation ID` or `--site KEY` returns `nex.operation-context/1`, with explicit revision/source identity and ancestors. Both use saved HEAD unless `--revision` selects an archive; they do not advance HEAD. `nex.graph/2` includes an additive complete `operation_graph`. Matching is local to the store; imports derive new IDs from checked sources and ignore foreign identities. The operation guide/schema define paging, omitted data and conservative identity rules.

Interpreter `eval` failures from checked operations add `operation_id`, `operation_site`, `revision` and `source_hash` to `nex.diagnostic/1`. Source-only frontend errors retain their existing fields. TypeScript trap sites add an optional fourth deterministic key. Native manifests/MLIR carry source-site metadata, and stopped LLDB/DAP REPL `nex-operation` returns `nex.debug-operation/1` candidates. Native textual runtime failures and optimized-PC attribution remain limited as described in the operation guide.

## Source-operation patches (toolchain 0.48)

`patch_entities` includes `operation`. Use the same `nex apply --patch FILE`
command with an additional root `expected_source_hash` from the selected
archived context. An operation replacement has `operation_id` and `source`,
with optional `kind:"operation"`; it cannot contain declaration `name` or byte
coordinates. See `llm/patch.schema.json` for the two strict replacement variants.
Existing declaration-only patches remain compatible without the new source
hash. If supplied, that hash is always checked. Both digests are exact lowercase
64-character values and local operation IDs have 32 characters.

`source_range` is additive operation metadata, independent of `location`.
Nonnull ranges identify `expression`, `statement` or `pattern`, complete UTF-8
byte intervals in the archived unit, and editability. Context adds a bounded
preview, total source bytes and a truncation flag. Old responses may omit ranges;
never treat diagnostic source points or an omitted/truncated preview as edit
coordinates/source. Null ranges and derived owners cannot be edited.

Mixed declaration/operation patches reject duplicate or overlapping targets,
parse exactly one fragment, isolate precedence/comments and recheck the entire
bundle before a final expected-HEAD write transaction. `E_PATCH_SOURCE` means a
missing exact-source guard, `E_SOURCE_CONFLICT` a changed source bundle,
`E_PATCH_TARGET` a synthetic/noneditable interval, `E_PATCH_OVERLAP` overlapping
edits, and `E_PATCH_SPECIALIZATION`/`E_PATCH_CLOSURE` a derived owner. Physical
files are not materialized. `patch_limits` and `parser_limits` report file,
JSON, replacement, token, preview and recursion limits. See the operation guide
and its installed example. Language/canonical formats and protocol 2 are retained.

## Generic source and derived instances (language 0.7)

In language 0.7, function/structure/enum canonical definitions carry type_parameters, template and type_arguments. Context for a function instance identifies its source template, concrete arguments and editable:false. Patch the source template; direct instance replacements return E_PATCH_SPECIALIZATION. All callers and template bodies are rechecked before committing. Program/6 hashes include checked source definitions and exclude derived instances; function/5, structure/3 and enum/2 retain per-instance definitions for context/cache/site attribution. Source exports contain each original declaration once. Explicit 0.6 migration preserves old history and local function/operation IDs. Preserve SDK 0.16 for old frames/receipts, and review/regenerate acceptance pins under 0.7.

Toolchain 0.19 adds `nex toolchain FILE --json` (`nex.toolchain-report/1`) for read-only normalized native configuration/fingerprint discovery. `--toolchains CATALOG.json` provides current trusted configurations to task check/run/replay. Native checks pair `toolchain` with `toolchain_hash`; captures and receipts retain target/fingerprint identity. Changed inputs or missing current trust fail with E_TASK_TOOLCHAIN. The task guide defines fingerprint scope, replay validation and foreign-build versus execution evidence.

## Bounded generic declarations (language 0.8)

Canonical function/6, structure/4 and enum/3 definitions add sorted `type_bounds`; program/7 revisions include them. Function context exposes the same map keyed by scoped type-parameter name. `describe.generic_constraints` reports builtin domains/implications. Bounds are checked on unused declarations and abstract forwarding before specialization. Protocol 2 is retained. Explicit 0.7→0.8 migration preserves historical sources and local identities; old frames/receipts require their original 0.20 compiler/resources.

Language 0.9 uses canonical function/7 and program/8 definitions for typed patterns and ordered guard/value arguments. Structure/4 and enum/3 remain unchanged. Pattern bindings and guard/value operands appear in the operation tree; simple legacy enum arm paths retain their identity through explicit 0.8 migration. `match_features`, `match_limits` and the match guide expose supported syntax and bounds.

## Function values (language 0.10)

Canonical function/8 and program/9 represent callable types, references, invokes
and inline lambda signatures/bodies. Lifted bodies record closure_owner/captures
and are derived, excluded from source revision identity and not directly
editable. Patch their source owner/template. The descriptor exposes function
capabilities/limits and the separate debug-wire schema. Query `nex guide --kind
function`; protocol 2 and nominal structure/4, enum/3 are retained. Task linkage
and bounded contexts include callback parameter/result types and nominal
phantom arguments. Genuine 0.9 archives require explicit migration with original
history/source/IDs retained. Task/proof snapshot pins must be reviewed/regenerated
without weakening acceptance intent; old frames/receipts need SDK 0.22.

Toolchain 0.27 adds relative installed host-SDK selection (`nex.sdk-host/1`).
`doctor` reports effective native compiler/archive/debug/linker and SQLite/OpenSSL
paths plus `sdk_manifest`. Native toolchain configurations accept optional
`archiver` and `debug_packager`; read-only snapshot/2 fingerprints include their
bytes. The SDK guide defines bundle assembly versus moved-directory acceptance
and prerequisites. Source language and graph canonical formats are unchanged.

Toolchain 0.29 adds native `package FILE --directory NEW --json`, with optional
`--target server`, native toolchain/profile/entry/revision selection and explicit
dependency notices. The `nex.package/1` response reports directory, executable,
manifest, build key, revision and file count. `application.json` uses
`nex.application-package/1` (indexed JSON schema), with exact artifact/component
hashes and `execution_verified:false`. Assembly never executes the application.
Separate `nex.application-execution/1` acceptance evidence verifies relocated
fixture execution; preserve that distinction when reporting results. Query the
descriptor's `application_package_*` fields and read `docs/packaging.md`.

## Text files (language 0.12)

Discovery advertises `fs`, exact server builtin signatures, `file_features`,
`file_limits`, `file_platforms`, `file_environment` and `file_guide`. Retrieve
`nex guide --kind files --json` before generating file code. `eval` owns a scoped
capability; native standalone entries use a session capability. An absolute
`NEX_FILES_ROOT` is required and writes require exactly `NEX_FILES_WRITE=1`.
HTTP request scopes ignore these environment grants unless a trusted host
explicitly supplies `FileScope`. Task effects checks accept `fs` only when
reviewed `allowed_effects` includes it; pure watches reject filesystem calls.
File mutations are not SQLite transaction mutations.

Language 0.11 stores require explicit history-preserving migration. Genuine
SDK 0.29 fixtures cover ordinary migration and new builtin-name collisions.
Rejected candidates leave HEAD and old sources untouched; an explicitly repaired
exported bundle can be migrated without replacing the original revision. Keep
the matching old SDK for receipts/frames. Function/9, program/10, structure/4
and enum/3 remained unchanged in that migration; the language version changes program revision identity.

## File resources (language 0.14)

Opaque `file` values and streaming intrinsics require server realm and `fs`.
They share identity/close state and cannot enter JSON/API or client code.
Pure debug values use a separate non-authoritative opaque identity marker.
See [the resource guide](resources.md) for ownership, limits, callbacks and
explicit history-preserving migration from 0.13.

## Source foreign calls (language 0.15)

Concrete server `extern fn` declarations carry `ffi` and a checked
`foreign(library, export, manifest_sha256)` body. Canonical `nex.function/12`
includes this binding; `nex.program/13` revisions include the new language and
function definitions. Graph/context protocol 2 remains unchanged. Function
context adds `foreign` with library/export/pin, or null for ordinary functions.
`nex ffi --symbol NAME --json` exports the actual `nex.foreign-signature/1`.
Signature export and compilation do not load modules or confer execution rights.

`eval`, `run`, `test`, `debug` and `profile` accept an explicit `--foreign
HOST.json`. Standalone binaries accept `--nex-foreign`; HTTP servers accept
`--foreign` and create per-request contexts. The binding and host catalogue
must agree; no environment variable grants authority. Loader errors preserve
their public `E_FFI_*` codes. See [the FFI guide](ffi-design.md).

Language-0.14 migration is explicit and retains original snapshots and local
identities, including ordinary identifiers `ffi`, `extern` and `foreign`.
Current example acceptance pins must be reviewed/regenerated without weakening
their properties. Keep SDK 0.40 for old receipts/frames. Toolchain 0.43 connects
matching-host package dependency closures, described below. Toolchain 0.42 connects reviewed task
catalogue capture and current-trust replay, described below.

## Reviewed task foreign inputs (toolchain 0.42)

`nex foreign HOST.json --json` returns `nex.foreign-catalogue-report/1` with a
content fingerprint, platform, normalized catalogue, bounded inventory size and
`module_initialization:false`. Its `hash` covers `nex.foreign-catalogue/1` using
BLAKE3; the embedded bundle/member pins remain SHA-256. All member bytes are
verified, without dlopen. Native module ABI/behavior is checked during execution.

Native task `test`, `run` and `profile` checks accept `foreign_hash`. Reachable
external calls require that field and explicit current `--foreign HOST.json`
for task check/run/replay. Other targets/check kinds reject the field. Task schema
1 and language 0.15 are retained; old documents without external execution retain
their meaning. Receipt replay still requires its captured compiler/build.

Captured `inputs/foreign/host.json`, `identity.json` and `bundles/PIN/` participate
in the ordinary task integrity index. Current operator trust is compared against
the captured normalized policy and all binary bytes before replay; command-time
checks detect changed captures. Receipts/summaries expose `foreign_catalogue`
hash/platform and selected execution rows record `foreign_hash`. See the task
guide for quotas and the native trust/dependency boundary.

## Native foreign package projection (toolchain 0.43)

`nex package FILE --foreign HOST.json --directory NEW --json` selects only
reachable libraries/exports, verifies operator intent and native signatures,
collects native loader dependencies/notices and repins relocated module images.
The compiler derives and checks a source bundle with only reachable manifest
literal tokens changed. Both graph revisions remain available; materialized
source and HEAD are preserved. No language-version migration is needed.

`nex.package/1` reports the actual compiled derived `revision`, additionally
`source_revision` and the deployed `foreign_catalogue` path. `application.json`
adds `foreign_projection` (`nex.foreign-projection/1`), identifying both source
hashes/revisions, changed bindings and `nex.foreign-package/1` preparation
evidence. Top-level file/component inventories cover both application and module
dependencies/notices. Internal preparation is not a compiled or execution-verified
application. Assembly retains `execution_verified:false`.

The native executable defaults to its own `../foreign/host.json`, resolved from
the actual executable location. Ordinary builds retain explicit-only grants;
environment variables confer no authority. Explicit standalone/HTTP catalogue
flags retain their meanings and source pins/signatures remain exact. Matching
host-target preparation is supported; cross-target module closure assembly and
arbitrary native dynamic loads remain pending. See the packaging guide for the
complete trust, dependency and deployment boundary.

Relocation preserves module image identity as well as binding types: original
aliases share state and distinct source pins remain independent. Preparation
records `source_identity_file` within the code inventory. Additional component
notices use catalogue-relative paths when `notices_root` is `"catalogue"`;
absence retains the older bundle-relative convention. Package schema references
resolve through canonical `$id` URIs registered from the indexed local files.

## Native diagnostic logs

`nex run --json` adds a bounded `native_diagnostics` response while retaining
`ok`, `exit_code`, `stdout`, `stderr` and `build_key`.
`nex diagnose [file] --manifest DEBUG.json --log STDERR.log [--revision HASH]`
reads retained logs without compiling or executing them. Retrieve
`nex guide --kind diagnostic --json` and
[`native-diagnostics.schema.json`](../llm/native-diagnostics.schema.json). Only
`mapped` records carry local graph IDs; preserve the reported revision and exact
source hash when requesting context. `unmapped` records carry no verified local
identity.


Toolchain 0.49 adds graph schema 4 with a local HEAD-transition journal and
expected-HEAD restoration of retained, rechecked current-language source. The
upgrade retains old rows and starts an empty journal at the actual HEAD; it
does not infer unknown prior provenance. See [the history guide](history.md) for
`nex changes`, `nex restore`, declared labels, bounds and older-SDK compatibility.
The installed SDK backend-agreement scenario restores both source-deleted
operation-edit revisions and verifies their four actual transitions.

## Complete local graph snapshots (toolchain 0.50)

Discover `snapshot_features` and read [the snapshot guide](snapshots.md). `nex snapshot --directory NEW_SNAPSHOT` uses a consistent SQLite backup and a SHA-256 database manifest. `nex recover SNAPSHOT --directory NEW_PROJECT` preserves all database rows and local UUID lineage without changing an existing project, materializing source or migrating schema. Use `--revision HEAD` to validate recovered source. These commands preserve local identity, unlike source/graph import; they do not include external receipt/artifact files, SDK dependencies or application data. `llm/graph-snapshot.schema.json` describes the manifest and results.

## Declared physical project versions (toolchain 0.51)

Query `project_features` and retrieve [compatibility](compatibility.md). Explicit
root/reachable configured-library source languages must match the compiler.
Root metadata is checked before graph initialization for physical workflows;
archived `--revision`, migration and recovery keep their own independent guards.
`llm/project.schema.json` describes current manifests. Omitted legacy language
means current compiler input. Explicit migration retains old archives and
requires validation/export before using a current physical projection.

## Captured frontend error context (toolchain 0.52)

The existing `nex.diagnostic/1` envelope can include a versioned `frontend`
object. Read [its guide](frontend-diagnostics.md) and schema from the language
pack. It identifies actual captured source/fragment input and bounded previews;
failed candidate bytes may differ from physical files. Runtime operation metadata
is retained, and diagnostic IDs are not graph node/revision authority.

## Archived graph discovery (toolchain 0.53)

`search --query TEXT` returns `nex.graph-search/1`; `subgraph --symbol NAME`
returns `nex.subgraph/1`. Both select archived HEAD or explicit `--revision` and
reject physical filenames. Request the [query guide](queries.md) for literal
filters, checked static-edge meaning, minimum-hop radius, independent bounded
node/edge pages and exact byte/query identity. Responses follow the matching
local-reference `llm/graph-query.schema.json`. They do not execute code, apply
changes or grant native-library authority. Language/canonical/graph schemas
remain unchanged. Current validation scope is recorded in `STATUS.md`.

## Stopped-string ranges (toolchain0.54)

The matching build's nex.debug-frame/2 captures add text_range with canonical
nonnegative decimal start/count strings and an exact UTF-8 value or unavailable
reason. Counts and indices use Unicode scalars. Existing full/value/shape forms
remain accepted. The compiler validates type paths, metadata, lengths and alias
overlaps; [the guide](string-debug.md) describes separate physical scan bounds
and trust. Old compiler/manifests retain their own matching build requirement.

## Native indexed debugger pages (toolchain 0.57)

The matching NEX stdio DAP bridge exposes indexed children beyond the native
32-element text preview for list/byte roots. Native variables replies add
`body.nex.native_page` with `start`, `requested_count`, `returned_count` and
`limit:1000`; the schema is `llm/dap-native-page.schema.json`. Omitted/zero count
and larger requested counts return at most1000 children. Negative, Boolean or
non-signed32 page arguments are rejected. The advertised count is bounded to
2147483647 children; a page start outside the actual collection returns empty.
Native pages retain ordinary preview semantics, not exact wire/frame values.
Execution or a new stop expires references; a late response cannot revive them.
The debug guide describes direct-LLDB and remaining named/string boundaries.

## Native core capsule data (development0.59)

`nex core CORE --manifest DEBUG.json --export NEW_DIRECTORY --json` publishes a
checked `nex.core-capsule/1` directory and returns `nex.core-capsule-export/1`.
`nex core --capsule DIRECTORY --json` returns `nex.core-report/1` with a checked
`capsule` binding. The receipt/export schema is `llm/core-capsule.schema.json`;
read reports retain `llm/core-report.schema.json`. Relative inventory paths,
bytes, SHA256 and original build/compiler/runtime identities are checked before
LLDB. The matching installed SDK supplies executable tooling. Unsupported
capsule formats/hosts/inputs use `E_CORE_CAPSULE`; build/core mismatches retain
their existing diagnostics. See `docs/core-debugging.md` for exact limits.
