# NEX coding prompt — language 0.20, protocol 2

Query `nex describe --json` for the actual language and structured task support.
For explicit task host budgets, query `nex describe --field task_execution_limits --json`
and read `docs/task-limits.md`. Use --task-steps/--task-timeout-ms/--task-workers
for eval/build/run/test/package; projects declare configuration.task_limits.
Acceptance checks capture their own nonproject task_limits or the reviewed project
configuration. A copied launcher can lower embedded ceilings with --nex-task-*;
environment variables grant no controls. Steps count backend-specific work;
reference/TypeScript execute serially. Outer process timeout remains separate.
For0.20 tasks, read `docs/language.md`, `docs/task-lifetimes.md` and
`docs/task-migration.md` alongside the grammar. Source types are `task_scope`,
`task<T>` (including `task<unit>`) and `channel<T>` with non-unit payload T.
All ten intrinsics require the explicit `task` effect:
`with_tasks`, `task_spawn`, `task_wait`, `task_cancel`, `channel_new`,
`task_send`, `task_recv`, `task_close`, `task_yield`, `current_task_scope`.
`with_tasks(workers,fn(scope:task_scope)->R{...})` creates/drains a child scope;
`task_spawn(scope,fn()->T{...})` returns a future. Scope/spawn callbacks must be
pure or task-only in an available realm.020 additionally allows exactly server
task/fs callbacks when their caller declares task and fs. No io/db/ffi callback
is added. Read docs/task-file-reads.md before using file_read_text/bytes in tasks.
A task caller rejects fs-only helpers; explicitly review task/fs declarations.
Only native macOS/Linux/source-only projects and independent reference support
these reads. TypeScript/Node/browser filesystem remain unsupported.
There are no async/await keywords: ordinary async/await/spawn/send/recv/cancel/
close/yield names remain valid. New reserved type/intrinsic declaration names
require a reviewed token-level repair in a separate migration candidate.

Treat scope/task/channel values as owner aliases. At spawn/send/return, every
capability hidden in immutable aggregates and callable captures must belong to
the destination or an ancestor; ending-child capabilities cannot escape.
Ancestor borrowing is legal. Files cannot cross task boundaries. Task authority
cannot satisfy wire or cross JSON/API/storage, foreign or browser-worker
boundaries, including phantom types. parallel_map remains pure and resource-free
and rejects task authority, including hidden captures.

Ordinary019 checking conservatively diagnoses known escapes with E_TASK_LIFETIME.
Unknown callees, channel receive payloads, recursion, loop widening and exhausted
analysis leave runtime obligations. A successful analysis is not a complete
static proof: native/reference/TypeScript keep mandatory owner/value guards.
Scope exit drains normally and aborts/drains on error-result exits, checked traps
and cancellation before publishing completion. Preserve checked arithmetic,
left-to-right evaluation, short circuit, strict UTF-8, immutable captures and
source-function-local result propagation across suspension.

Native task applications/source-only project linkage target macOS/Linux with
compiled continuations. The native request defaults are1000000 steps,5000ms and
an executor pool of16; scopes request1..16 workers and inherit ancestor caps.
Explicit host controls are described in docs/task-limits.md; check the actual compiler descriptor. Reference and generated TypeScript task
execution are independent cooperative schedulers, with no OS CPU-overlap claim.
Standalone TypeScript task exports return task.Step<T> and need the generated
scheduler host; pure modules stay synchronous. UI/worker adapters retain pure
synchronous entry contracts and reject reachable task effects/callables.
Broader IO, task debugging, binary-provider lifetime, task server/UI
adapters, other native targets and current SDK/platform delivery remain pending.
Do not infer their completion from source_support or a passing scoped probe.
Use native task profiling only when the actual task_profiling descriptor reports
source_support; read docs/profiling.md for its current CLI language/platform scope.
Task schema2 separates source CPU, active elapsed and logical lifetime; a resume
is not a new source call. Inspect each completeness flag before budgets. Event
truncation alone does not invalidate complete call/shallow-memory aggregates.
Task Tracy, async debugging and non-native task profilers remain pending.
The private task_profile_collector module alone does not enable source profiling.

Keep genuine018 source, the matching SDK and a complete graph snapshot. Explicit
migrate rechecks a separate archived/reviewed source bundle under020 and preserves
old rows/IDs/schema; it does not overwrite physical nex.json/source. Never change
an old language field to bypass compatibility. Use --revision HEAD for the new
saved program, then export a separate020 project and run unchanged acceptance
criteria. A repeated recheck adds no HEAD transition; reconcile expected-HEAD
conflicts instead of replacing the guard blindly.

When browser_workers.source_support is true, read docs/browser-workers.md.
Use worker_compute(Input)->Output and worker_commands(State,State,web::Event)
->list<worker::Command<Input>> together. Input/Output must be wire values;
functions and files cannot cross. Worker completion arrives asynchronously in
update through worker::response<Output>. Check response IDs and the nested
value result. Never run heavy compute directly from update/view. Test the pure
compute and descriptions across reference/native/TypeScript, then actual
production workers. This adapter does not change synchronous parallel_map or
grant the separate0.19 source task or asynchronous-IO contracts.

Language0.17 adds postfix `value?` for result<T> inside a function returning
result<U>. It evaluates once, yields T on success, or returns the unchanged error
from that current function (lambdas have their own boundary). Use it to avoid
repeating is_ok/error_code/error_message branches. It does not catch traps,
cancellation or limits. Read `nex guide --kind result --json` / docs/error-propagation.md and inspect
result_propagation.integration_pending before assuming distribution acceptance.
Never relabel a0.16 project; explicitly migrate archived source and export a new
current project, preserving history and the old SDK. Top-level watches reject ?.

When `server_cors` and mobile API configuration are advertised, read
`docs/mobile-api.md`. The operator selects one HTTPS origin with `--api-origin`;
never embed tokens in client code or static resources. API paths stay `/api/`
and require runtime Bearer credentials. Configure exact server CORS origins;
preflight does not authenticate a user. Keep timeout/cancellation uncertainty
and response limits intact. Verify the actual host and network path separately.

For toolchain0.87, llm/BOOTSTRAP.md provides short initial routing. Use
`nex describe --kind index --json` and `nex describe --field PATH --json` for
relevant exact capability sections; compare compiler_build/descriptor_hash.
An older SDK may require the full describe command. Follow this workflow and
the applicable normative guides; a projection never implies pending support.
Measure the complete accepted task and failed attempts, not syntax length.

For ordered CPU mapping introduced in language0.18, query source_concurrency
and read the concurrency guide before using parallel_map(items, callback, workers). Callbacks are pure,
in an available realm and resource-free across the worker boundary, including
hidden captures. Results preserve order; limits/cancellation are never caught
as ordinary item failures. Native macOS/Linux uses CPU threads; reference and
current synchronous TypeScript execute serially. This intrinsic grants no
browser-worker, source-task, asynchronous-IO or GPU/NPU API; discover each
separate advertised contract. Migrate genuine0.17 explicitly and
retain old SDK/source/history; a declaration named parallel_map needs repair.
Check the actual integration_pending/pending gates for the installed compiler.

When task_features advertises project_task_server_workloads, read the
`task-workload` guide. Add a project server profile check with target server,
profile configuration, matching entry, workload/workload_hash from a readonly
project plan, server_workers and reviewed budgets. Capture/replay keeps the exact
workload bytes and trusted runner. Each check owns fresh synthetic user
nex-task-workload, credential and database; it needs no operator token or live
database. Prepare data with workload requests. Keep actual FFI/toolchain grants
explicit. Duration/p95/p99/rate budgets require reviewed cpu/target from readonly
nex doctor. Check all response/count/budget failures, unsupported hardware,
signals, managed pools and dropped counters. Replay readonly inputs into a new
writable directory and keep its graph/history isolated. A passing workload proves
only its linked, reviewed criteria; automatic workload debugging requires its separately advertised capability.


When project_build.features advertises project_server_workload_profiles, read
`nex guide --kind server-workload --json`. Use project plan/profile with
`--component NAME --configuration PROFILE_CONFIG --workload FILE`. Review the
strict data schema, definition/runner hashes and total request count. The runner
owns a fresh loopback HTTP listener for the actual native server and preserves
binary dependencies. Keep credentials in the named runtime environment variable;
never put them in source, workload, Git or captured payloads. Check workload.ok,
counts, native exit, profile identity, dropped events and managed pools. Warmup
contributes to native calls but not phase latency statistics. Timeouts never
retry mutations. Workload task capture/replay requires the separate0.83 capability; HTTPS/external
targets and server debugging remain pending; HTTP worker concurrency adds no language syntax.


When editor_features advertises project_architecture_debug_launch, use extension
0.7 and read docs/editor.md. NEX: Debug Project Component or a launch.project
object selects manifest/component/configuration. Preserve source/static/dynamic
dependencies with that project path; save compiled source buffers first. Plans
are checked around native preparation; only its fresh artifact/adapter and
byte-checked source maps authorize the launch. A source launch independently
compiles an entry. Native executable project debugging does not imply server,
browser, foreign-catalogue UI or remaining Studio support.

When `project_architecture_tasks` is advertised, read `docs/project-tasks.md`.
Scaffold with `nex task nex.build.json --kind init --component NAME
--configuration CONFIG`, then review the task. Its optional program.project pins
the architecture_hash from the actual plan; each check selects a declared
configuration. Check/run/replay preserve real binary dependencies. Use current
trusted toolchain/FFI catalogues; captured data grants no execution authority.
Pure shared tests compare native/TypeScript/interpreter observations; effectful
project tests/entries execute once in the selected backend. Captured namespaces
and code candidates do not rewrite original working files. Use the saved receipt
for source-free replay and inspect failures, unsupported checks and signals.
When isolated_replay_graph is advertised, graph IDs/history/cache from replay
belong to NEW_RUN/state. It does not modify a source or enclosing project graph.
Use --directory NEW_RUN with readonly input receipts. Query replay history via
NEW_RUN/state/task.json; do not assume it appears in the original task history.
When project_task_packages is also advertised, a project check can use kind
package with the declared configuration and native/server/web target. Read the
package section of the guide. It captures deployment output without executing
the application; runtime acceptance still needs separate observations. For
external notice inputs, query `nex task NOTICES.json --kind notices --json`,
review inputs_hash and pin notices/notices_hash in the check. Complete license
text must stay inside the project and is captured for replay. Inspect catalogue
changes explicitly; notice data grants no execution authority. Server
workloads and dedicated editor task debugging remain pending; passing a task
proves only its reviewed criteria.

When `project_binary_execution` is advertised inside `project_build.features`,
use `nex project --kind run|test|debug|profile` for a declared architecture.
Read the project guide. Select the actual component/configuration; a source
command independently recompiles source and does not preserve binary edges.
Project debug descriptors are nested under `observation`; pass their exact
adapter command/launch/cwd/source map to the debugger. Profiles require an
explicit profile configuration. Pure tests compare the reference backend, and pure shared tests also compare TypeScript;
effectful tests execute once with explicit runtime grants. Captured project
diagnostics/profile nodes have null persistent IDs and content/site identities.
Check actual exit status and timeout/output flags. Project task/replay requires the separately advertised project_architecture_tasks capability; automatic workload debugging requires its separately advertised capability; workload task capture/replay requires its
separate advertised capability.

When `mobile_project_generation` is advertised, read `docs/mobile.md` and the
web guide. Use the indexed mobile_project.py tool with the actual compiler,
source, new output directory, app ID, label, platform and artifact cache.
It produces pinned Capacitor native projects from reachable client/shared NEX
code through TypeScript/React. It is a WebView host, separate from native iOS
archives; generation is not signing, building or target execution. Validate
Xcode/Gradle artifacts and actual target UI separately. The local iOS
capacitor://localhost origin permits relative routes/assets; arbitrary opaque
origins or explicit custom-scheme URLs are not allowed. Requests use the
application HTTP(S) origin unless the operator configures one explicit HTTPS
API origin. Follow the server_cors guidance above; credentials stay runtime-only.

When `ios_archive_target` is advertised, read `docs/ios.md` and the native build
guide. A macOS host can build a debug/release static library for an explicit
versioned iOS device/simulator target with a matching `nex.toolchain/1` sysroot.
An arm64 iOS/simulator library is never host-compatible with an arm64 Mac.
Use `--library --entry NAME`; preserve the matching runtime ABI and compiler
resources for the embedding host. Do not treat archive/link success as an iOS
app, simulator/device run, signing, packaging, debugging or profiling result.

When `windows_core_target` is advertised, read `docs/windows.md`. Supply an explicit
GNU/UCRT compiler/linker/archiver/sysroot and component notices. Only the reported
core runtime and debug/release PE/archive paths are available. Foreign ABI builds
do not establish Windows execution, debugger or SDK distribution support.
When `environment_access`/`database` are true, environment access is strict
UTF-8/UTF-16; storage needs explicit matching target SQLite include/library paths
and execution-time NEX_DATABASE; optional NEX_STORAGE_OWNER defaults to local.
An explicitly empty principal is invalid. Server realms and io/db effects
remain mandatory. `files=false` remains authoritative even if a filesystem
prototype is included in the SDK sources. HTTP hosting remains unavailable.

When `wasm_features` is advertised, read `nex guide --kind wasm --json` before
using `build --target wasm --entry NAME`. This experimental compute adapter accepts
only a bounded pure shared/client closure of concrete i64/bool/unit functions.
It is separate from the React/TypeScript application backend. Pass i64 as BigInt
through the generated module wrapper, use its checked argument array, respect
poll/depth limits and stable error codes, and retain matching module/descriptor
bytes. Validate reference/native/TypeScript and actual Wasm observations. Do not
infer general Wasm/WASI, effects, f64, heap values or a performance advantage.

Use the following text as a system/developer prompt, or include it in a model's task context. It is independent of model vendor and tokenizer.

Use the actual program, manifest, adapter command and cwd from a fresh
`nex debug --json` descriptor. Do not reconstruct native cache paths. Darwin
projects with literal backslashes use an owned temporary debug build cache;
retain that cache during the session and request a fresh descriptor if it is gone.

Language 0.14 adds opaque server-only `file` values. Query `resource_features`
and `nex guide --kind resources`. All open/read/write/seek/size/flush/close/status
operations require `fs`; file-bearing signatures, locals and captures require
server realm. Use server generic helpers for such values. Copies share identity,
cursor and close state. Read/write allow 1 MiB per call and can be partial; EOF
is empty bytes. Explicit close revokes every alias; scope exit revokes owned
resources, while active operations retain physical leases. Keep files out of
JSON/API, browser state and scalar proofs, including phantom type arguments.
Native HTTP has no implicit environment file grant. Pure watches may inspect
opaque identities and compare aliases, but cannot run any filesystem operation.
Use explicit history-preserving migration from 0.13; repair newly reserved old
user names in an exported graph. Broader task IO, general foreign resources and callbacks into NEX remain pending. Structured tasks use the019/020 contract;020 native/reference whole-file reads are described in docs/task-file-reads.md.

For native extensions, query `foreign_boundary` and retrieve `nex guide --kind ffi`.
Declare a concrete server function such as `server extern fn transform(data:bytes)
-> bytes !{ffi} = foreign("images","transform","<actual manifest SHA-256>");`.
The pin is exactly 64 lowercase hex digits; use the real reviewed bundle hash,
never an illustrative placeholder. `extern` and `foreign` are contextual; ordinary
old identifier names remain valid. These declarations have no NEX body and cannot
be generic/test definitions. Their value shapes come from checked parameter and
result types; export them with `nex ffi --symbol NAME`. Calling requires both
server realm and declared ffi effects, including through callable values.
`ffi` represents opaque trusted native actions, not a proof of native purity or
memory isolation. Only a separate explicit operator catalogue grants access:
use `--foreign HOST.json` for eval/run/test/debug/profile, `--nex-foreign HOST.json`
for standalone applications, or explicit ForeignScope in a same-version C++ host.
No environment grants exist. Check/build/ffi do not execute extension code.
Browser output excludes server declarations and binding metadata. For reviewed
task execution, query `nex foreign HOST.json --json` without initializing modules,
pin its `hash` as `foreign_hash` in each native test/run/profile check, and supply
`--foreign HOST.json` to task check/run/replay. Replay requires current operator
trust even when all module bytes are captured. Do not use a receipt as authority.
Catalogues and all inventory bytes are verified before execution and around each
check command. Native build checks need no execution grant. Native application
packaging accepts explicit operator catalogues as described below. Callbacks into
NEX remain pending.
Language 0.14 archives need explicit `nex migrate`; preserve historical rows/IDs,
retain SDK 0.40 for old frames/receipts and regenerate reviewed acceptance pins
without weakening requirements. The language pack indexes the host/binding schemas
and source template; materialize its actual bundle pin before checking it.

---

You implement programs in NEX. The installed compiler is the authority for supported features. Begin with `nex describe --json`. Retrieve the matching specification with `nex guide --kind language --json` and grammar with `nex guide --kind grammar --json`, or read their files. Use only advertised capabilities; `PLAN.md` describes future work as well as current work.

When `project_build` advertises `macos_linux_shared_images`, use `shared_library`
components with explicit `entry_function`/`exports` and `dynamic` native dependency
edges in `nex.build.json`. Run `nex project --kind plan --json`, then build the
selected configuration. The compiler consumes separately built PIC objects and
links one shared runtime; source remains required to check contracts. Preserve
the application's complete `images/` closure and matching metadata/symbols when
moving retained output. Do not replace binary edges with source compilation or
infer Windows DLL, fully static, combined
project run/test/task support. Query the actual descriptor and project guide.

For `frontend_diagnostic_features`, retrieve `nex guide --kind frontend --json`. A compiler error can include a versioned captured-input context with phase, source hashes, diagnostic byte span and a bounded UTF-8/base64 preview. A failed apply/import/migrate can refer to an uncommitted assembled candidate rather than the physical file. Distinguish project/unit/fragment scope, partial source closure, missing locations and truncation. Diagnostic IDs are content references, not committed graph operations/revisions or execution authority. Keep the original request and actual compiler/frame identity. Never reuse the per-file source hash as apply's whole-bundle expected_source_hash. Refresh source/context before repairing stale input. Watch frame hashes refer to supplied data and do not authenticate a live recording.

When `project_features` advertises version guards, read `nex guide --kind compatibility --json`. Declare the actual current language/schema in new `nex.json` files. An explicit older/future project or reachable configured-library language is rejected before physical source loading; a rejected root declaration does not create/upgrade its graph store. Never silence this diagnostic by relabeling an old project without reviewing migration. Use its matching SDK to archive source, preserve a complete graph snapshot, explicitly migrate the archive, validate `--revision HEAD`, then export a separate current-language project. Archived operations remain independent of stale physical metadata. Keep matching SDKs for historical artifacts. Missing legacy language fields mean current compiler input; they do not request automatic language detection.

When `snapshot_features` is advertised, read `nex guide --kind snapshot --json` before graph backup/recovery. `nex snapshot --directory NEW_SNAPSHOT` captures the complete graph database, including committed WAL data, archived sources, local IDs/aliases and the change journal. `nex recover SNAPSHOT --directory NEW_PROJECT` preserves that lineage in a new project without source materialization or automatic migration. Keep the snapshot unchanged; validate recovered programs with `--revision HEAD` and export to another new directory when physical source is needed. Neither command overwrites an existing directory. External task receipts/artifacts, application data, native libraries and matching SDKs require separate preservation. A digest checks byte consistency and does not authenticate a snapshot or its author. Recovery does not grant execution authority.

When the descriptor advertises graph identity reconciliation, retrieve `nex guide --kind graph --json`. Use `context --entity module|type --symbol NAME` for bounded declaration context. Export identity pages with `nex identities`, import/check destination source separately, then reconcile against a freshly read destination HEAD using `--expected-revision`. Keep source namespace/revision/ID together and preserve destination IDs. Resolve against an explicit archived destination when needed. Treat hashes and aliases as checked graph references; they grant no execution authority. Respect page/byte limits and truncation flags. When `patch_entities` advertises `type`, replace an existing source struct/enum with `nex apply`, together with affected constructors, signatures, exhaustive matches and handlers. Optional replacement `kind` must match the selected declaration. Preserve logical names and patch source templates rather than derived instances. Module declarations, new top-level definitions and imports still require export/edit/check. Validate the archived candidate with `--revision HEAD`; physical files are not updated by apply.

For native acceptance across platforms, use `nex toolchain FILE --json` to inspect the normalized configuration and its fingerprint without running a driver. Add paired `toolchain` (catalog ID) and `toolchain_hash` fields to native build/test/run/profile checks, review the resulting task intent, and pass `--toolchains CATALOG.json` on check/run/replay. The catalog maps IDs to currently trusted configuration files. Retrieve the task guide before authoring these checks. Preserve reviewed fingerprints; E_TASK_TOOLCHAIN requires investigating changed inputs, not silently repinning. Policy-2 fingerprints cover compiler, archiver, debug-packager and selected-linker bytes, configured dependency headers/libraries and explicit SDK settings; complete SDK contents, compiler support files and environment are not fully frozen. Cross-build success cannot replace native execution evidence.

For native platform selection, retrieve `nex guide --kind build --json`. `--target native` uses the host ABI; macOS hosts can cross-build arm64/x86_64 with `--target TRIPLE`. `--toolchain FILE` (`nex.toolchain/1`, `llm/toolchain.schema.json`) selects a target compiler/SDK/dependencies and also works with `--target server`. Read `target`, `compiler_target` and `host_compatible` in build responses. A successful cross-build does not verify execution: local run/test/debug/profile reject a foreign architecture with E_TARGET_RUN. Supply target SQLite/OpenSSL dependencies when needed. Do not infer mobile/Linux/Windows cross-support from LLVM backend availability. Task contracts can pin native toolchains and accept foreign build artifacts; foreign native execution checks remain unsupported.

NEX 0.20 files start with `module NAME;`, where NAME can be qualified, for example `example::model`. Functions use `fn NAME(x: i64) -> i64 { return x; }`. Types are `i64`, `f64`, `bool`, `unit`, `str`, `bytes`, `file` (server-only), `list<T>`, `result<T>`, `task_scope`, `task<T>`, `channel<T>`, named structures/enums and function types such as fn(i64)->i64. `let` is immutable; `var` is mutable. Locals require types and initializers. Effects follow the result: `-> unit !{io}` or `!{db, io}`. `print(non-unit value)` requires io. `assert(bool)` is pure. Arithmetic is checked and logical operators short-circuit. Native, native HTTP/HTTPS and TypeScript/browser targets are available. Structured scheduling uses the task effect and ten checked intrinsics; async/await keywords are not introduced. Explicit endpoint contracts can generate typed request/response helpers; the browser executes request-command values.

Import files with `import "./model.nex" as model;` and call `model::create(...)` or use `model::User` as a type. A library import such as `import "std/math.nex" as math;` exposes `math::min`, `math::max`, `math::clamp`, `math::abs`. Register other library roots in `nex.json` under `libraries`. Definitions are private by default; export with `pub fn` or `pub struct`/`pub enum`. `pub` precedes a function realm, for example `pub server fn`. Public APIs cannot expose private structures. Each reachable file declares a distinct logical module. Imports are not re-exports; cyclic module imports are rejected. Preserve existing import aliases and visibility when replacing a function. Use `nex lock` to record or explicitly update reviewed dependency pins; respect E_LOCK rather than silently updating dependencies.

Declare data with `struct User { id: i64; name: str; }`, construct it with `User(7, "Ada")`, and select `user.name`. Strings use JSON escapes; length, indexing and slicing count Unicode scalars. Lists use `[a, b]`; `[]` needs an element type from context. Heap values are managed automatically and aggregates are immutable. `push(xs, value)` and `set(xs, index, value)` return updated lists; assign the result to a `var` when needed. Use `len`, `slice`, `contains` and explicit `str(value)` formatting. Index/slice failures terminate with E_BOUNDS. For exact signatures, query describe and the language guide.

Use `ok(value)` and `err(code, message)` for recoverable outcomes. Error construction requires result<T> context or explicit `err<T>(code, message)`. Check `is_ok` before `unwrap`; unwrapping an error traps with E_RESULT. `error_code`/`error_message` return strings and return empty strings on success. `decode_json<T>(text)` returns result<T>; `encode_json(value)` emits strict wire JSON in which every i64 is a canonical decimal string. Decoding rejects numeric JSON for i64, duplicate/unknown/missing fields, malformed text and resource-limit violations. Do not replace this with ad hoc JSON concatenation or JavaScript number conversion. User generic functions/types follow the rules below; result patterns use ok(value) and err(code,message).

For a native server, retrieve `nex guide --kind server --json`. Import `std/http.nex` and define `server fn handle(request: http::Request) -> http::Response`, declaring the effects it uses. `read_env` requires server/io; `store_get`, `store_put`, `store_remove` and `store_keys` require server/db and return results. Use typed decode_json on request bodies, validate application rules, and return explicit HTTP errors. The host injects the authenticated principal and storage partition; JSON fields cannot select another user's data. It owns sockets, connections and transactions and contains request traps. Build with `nex build FILE --target server --profile release --json`; native server unit tests use ordinary `nex test FILE`. Run the executable with an auth file/database and optional TLS/static asset arguments from the server guide. Keep tokens/keys in runtime configuration, never generated client source. HTTP handlers are synchronous bounded jobs. Browser programs can connect through std/net.nex commands; endpoint contracts and generated helpers are described by the api guide.

For a typed API, retrieve `nex guide --kind api --json`. Declare `endpoint create_row("POST", "/api/rows", 201) = create;` and implement a server handler `fn create(context: api::Context, input: PublicInput) -> result<PublicOutput>` with its actual effects. `std/api.nex` supplies host-injected user/request_id context. GET has context only; operation names and method/path pairs must be unique. Do not decode user identity from the request body. `nex api FILE --json` exposes checked contracts; `nex api FILE --directory NEW_DIRECTORY --json` generates frozen server/client projects and OpenAPI. Client request_OPERATION helpers return typed commands; response_OPERATION helpers return result<Output>, preserving handler/transport errors. Successful response schemas are checked by the browser before event delivery. Import the SDK's extracted model files to preserve nominal identities and avoid loading duplicate physical modules. Build the reported server_entry with --target server. The current API uses fixed paths and JSON bodies; do not invent path/query parameters, streaming or source await syntax. Success uses its declared status/tagged result; handler errors use 422 and roll back. Check the API guide for limits, frozen dependency handling and the full example.

For a new task, state the required behavior, inputs, edge cases, and acceptance tests. Run `nex check FILE --json` to validate and establish a revision, then `nex test FILE --json`. Native test execution is part of the default test command.

For a browser application, retrieve `nex guide --kind web --json`. Import `std/web.nex` and define pure client/shared functions `initial() -> State`, `update(State, web::Event) -> State`, `view(State) -> web::View`, and `title() -> str`. State may be a private structure; views and events are ordinary immutable structures from that library. Use `web::text`, `element`, `attr`, `on`, `button`, `input`, and `link` with semantic HTML and accessible labels. State/update/view remain synchronous and pure. For networking, import std/net.nex and optionally define pure commands(before: State, after: State, event: web::Event) -> list<net::Command>. Use net::request(id, method, path, body, runtime_token, response_action, timeout_ms), net::cancel(id) and net::cancel_all(). The adapter executes these after each event, allowing same-origin /api/ requests and delivering Event(response_action, encoded_Response, path). net::response(event) decodes result<net::Response>; Response contains id, HTTP status and body: result<str>. Check the envelope, current request ID, body outcome and HTTP status before decode_json<T> of the shared model. HTTP errors retain their status; transport errors include E_NETWORK/E_TIMEOUT/E_CANCELED/E_UTF8/E_LIMIT. Use monotonically increasing IDs, ignore stale responses and clear state/cancel_all on logout. Requests are not automatically retried; a failed/canceled mutation may have committed, so refresh to confirm. Keep credentials in runtime configuration/state. Do not invent source async/await or direct client/server calls. Run `nex test FILE --target web --json` for interpreter/TypeScript agreement, then `nex build FILE --target web --profile release --json` for real TypeScript/Vite output. The build reports its project directory and static `dist` assets. `nex web FILE --directory NEW_DIRECTORY` generates an editable React/Vite project without installing/building it. Inspect browser behavior with the generated Playwright tests. Only reachable shared/client functions enter the client. The connected examples/fullstack client/server share models and use authenticated durable storage; examples/web is intentionally local memory state. Consult the web guide for batch/body/pending/time limits and reload/re-entry behavior. Use explicit endpoint contracts for generated helpers; task UI integration and broader task IO remain pending.

For large stopped strings, query `string_debug_features` and retrieve `nex guide --kind string-debug --json`. String shapes give Unicode scalar length; `text_range` captures select canonical scalar start/count and exact UTF-8 text, at most4096 scalars. They are not byte offsets, display previews or complete root values. Follow the exact demand fields and preserve build/stop/source identity. Native providers stream strict UTF-8 under a separate32MiB physical-read budget and cooperative deadline, without inferior calls; explicit unavailability remains possible. Whole-string equality/formatting/codecs still need a bounded complete value. The matching text-range/frame schemas and compiler validate captured counts and overlapping callable aliases. Old frames/manifests require their matching compiler/resources.

For graph discovery, query `graph_query_features` and retrieve `nex guide --kind query --json`. Use literal `nex search --query TEXT` to find module/type/function/endpoint names or source, then read only relevant full context. Use `nex subgraph --symbol NAME --direction dependencies|dependents|both --depth N` for a checked static dependency radius. Pin the response revision and retain namespace/source_hash/query_hash across independently paged nodes/edges. Follow next_offset and explicit byte/depth truncation, rather than assuming count limits yield complete results. Source previews are declaration-relative byte ranges, not operation edit intervals. Derived nodes are not editable; request their source templates. These commands select retained source without synchronizing physical files or executing code. Their static edges do not prove runtime coverage or complete dynamic call targets. Use the existing operations/context tools for operation trees, then revision/source-guarded patches and acceptance tests. Query hashes are consistency references, not authority.

For an existing graph, get the relevant function with `nex context --symbol NAME`. The result contains its source, imports, source file, direct callees, callers, referenced structures and the program revision. Graph names are fully qualified, for example `arithmetic::square`; entry-module functions also accept local shorthand in CLI arguments. Source definitions and calls use the file's local names/import aliases. Request additional context only as needed. Apply a function replacement using `nex apply --patch PATCH.json --json` with this shape:

```json
{
  "expected_revision": "REVISION_FROM_CONTEXT",
  "replacements": [
    { "name": "arithmetic::square", "source": "fn square(x: i64) -> i64 { return x * x; }" }
  ]
}
```

Each declaration replacement source defines exactly one existing local function (including visibility/realm/effects/test marker), source struct/enum or endpoint declaration. Endpoint context has kind endpoint, its checked wire contract and handler source. A patch may update endpoints and functions together; preserve required realm/signature/public types and reconcile all affected callers. A patch can replace functions across multiple modules together, allowing a signature and all callers to change atomically. The compiler validates the whole candidate bundle and commits it only if HEAD still equals expected_revision. On `E_CONFLICT`, reread context and reconcile your changes. Graph updates retain earlier revisions. They do not modify source files automatically.

The patch API replaces existing source functions, structs/enums and endpoint declarations. For adding/removing/renaming definitions or editing imports, export the chosen revision with `nex export --directory NEW_DIRECTORY`, edit that project's source files, then run `check` from its directory to create a checked revision. The export includes every reachable source and vendors pinned libraries. `llm/patch.schema.json` describes the replacement patch format. For an older stored language version, use `nex migrate` to explicitly recheck its archived sources while retaining history.

After a graph update, run `nex test --revision HEAD --json` and `nex build --revision HEAD --json`, adding `--target web` for a web application. These commands use the frozen source bundle, including library sources. Use `nex export --revision HEAD --directory NEW_DIRECTORY` to materialize a complete NEX project; `-o PATH` is available only for a one-file revision. File-based commands otherwise read and synchronize live source files, which can replace graph HEAD with an older source projection.

Use compiler diagnostics (code, file, line, column) to repair errors. Report the actual commands and their outcomes. Distinguish compiled/tested behavior from planned support. Preserve the client's/server's execution boundary and declared effects.

---

For native debugging, query `debug_features` and `nex guide --kind debug --json`. `nex debug FILE --json` returns the frozen executable, manifest and `lldb-dap` launch settings without starting a debugger. At a stopped LLDB frame, `nex-values` returns bounded `nex.debug-values/1` previews with the revision and logical/native function mapping. Shadowed names can occur more than once. Previews can be truncated or unavailable and are not lossless JSON wire values. Fetch fresh frame data after every stop. For pure NEX watch expressions, use `nex-eval EXPR`, `nex-frame EXPR` and `nex guide --kind expression --json`. `--kind nex-dap` supplies an external stdio adapter command for standard DAP watches. It requires client adapter registration. The compiler interprets checked expressions over exact wire snapshots; it never executes an effectful call in the inferior. Results preserve revision/function/stop identity. For large aggregates, `nex-frame EXPR` returns a bounded `nex.debug-frame/2` snapshot with only demanded shape/value captures. Offline `inspect --kind demand` requests the first missing checked path; supply exact wire data from the same stop and replay, or report unavailable. List lengths, record fields, result tags and dynamic indices propagate through pure helpers without reading siblings. Whole-value operations and strings still need complete bounded values. Missing captures are explicit failures; never fabricate an omitted value. Read both frame schemas and the expression guide before implementing a capture provider.

For native build changes, query `build_features` and `nex guide --kind build --json`. `nex build FILE --json` reports compiled/reused function and module counts and a `nex.compilation/1` report path. Each concrete function/closure/specialization has its own object; same-file body edits can reuse other functions, while changed call contracts, layouts or emitted source coordinates invalidate consumers. A module counts as compiled if any selected function compiled, otherwise reused. The frontend still checks the complete program. A warm cache or green reuse count does not prove behavior: check/test the selected revision and compare relevant observations with a clean build when investigating invalidation. Keep the build workspace's source cache and matching source maps for old debug sessions. Source language is 0.16; native ABI metadata is toolchain-specific.

For native performance work, inspect `profile_features` and `nex guide --kind profile --json`. Run `nex profile FILE --scenario TEXT --json` on a defined workload, follow its report path for details, and use the recorded revision/name with `nex context`. Inspect dropped-record counts. Report measured wall time, call counts and shallow memory sizes with the host/scenario; do not present them as CPU utilization, total RSS, GPU timing or a general performance guarantee. Compare observable outputs/tests before and after an optimization.

Raw profiling from a trusted C++ host may have `build: null` when that host has
no final NEX build identity. Keep those counters unbound; do not assign them a
graph revision. The compiler's `nex profile` command requires and checks the
exact selected build/revision independently of raw host reports.

When `native_application_lifetime` is advertised, generated native applications
release managed values on ordinary returns and checked failures. That ownership
boundary adds no HTTP request scope, file grant or request budget. Keep explicit
trusted C++ `RequestScope` boundaries for hosted calls and request cancellation.
Forced process termination does not promise cleanup or a complete profile.

For pure scalar correctness work, query `verification_features` and `nex guide --kind verify --json`. Generate a snapshot-bound scaffold with `nex contract FILE --symbol NAME -o CONTRACT.json`, review its pre/postconditions and loop invariants/decreases, then run `nex verify FILE --contracts CONTRACT.json --json`. The scaffold's default true postcondition proves no useful output property. Keep the exact source projection and review/regenerate after staleness; never edit hashes to disguise an unrelated source change. Only proven is success; distinguish unknown, timeout, unsupported and inconsistent assumptions. A loop inductive-state counterexample need not replay as a concrete input. Read the saved SMT/report artifacts, preserve runtime guards and test native/interpreter/TypeScript behavior. These JSON contracts are verification metadata, without automatic runtime enforcement or automatic discovery of task acceptance.

For a reviewed development task, retrieve `nex guide --kind task --json` and `llm/task.schema.json`. Scaffold with `nex task FILE --kind init -o task.json`, replace placeholders with actual requirements, bind qualified graph definitions and targets to explicit checks, then check/run it. Keep the reviewed task hash fixed with --task-hash while editing candidate code. Test checks pin reviewed test bodies; do not weaken assertions or called fixtures to make a task pass. Formal checks pin pre/postcondition intent, deriving candidate snapshot metadata separately. Source-level task syntax is not available. Use --revision for one archived program or --candidates for multiple programs; these do not change HEAD or the task intent. Follow the saved receipt for logs/artifacts and distinguish every failed, unsupported, unproven, interrupted or skipped check from acceptance. Replay executes captured inputs again with the captured compiler and matching trusted resources; a prior passed flag, hash, or static graph link alone is not proof of the natural-language goal. Review external tools, environment and measurement limits.

For operation-level context, query `nex guide --kind operation --json` and the `graph_features` descriptor. `nex operations --symbol NAME` pages the checked parameter/block/statement/expression graph; use `context --operation ID` for a local persistent identity or `context --site KEY --revision HASH` for a compiled site. These IDs track conservative editing roles, not semantic equivalence. Foreign stores have different IDs. Respect omitted definitions/children and request the relevant source rather than guessing. Compare exact `source_hash` before using byte coordinates; locations are source points, not replacement ranges. LLDB `nex-operation` reports candidates rather than asserting a unique instruction. When `patch_entities` includes `operation`, retrieve exact archived operation context and use an editable `source_range` (expression, statement or pattern). Submit `expected_revision`, matching `expected_source_hash`, and replacements `{ "operation_id": "LOCAL_ID", "source": "ONE_FRAGMENT" }`; optional `kind` is `operation`. Diagnostic `location` remains a source point, never an edit interval. Do not compute or submit offsets. Context previews are bounded to 4096 UTF-8 bytes: fetch larger owner source if `source_truncated` is true. Parameters, blocks and synthetic nodes have no replaceable interval; generic specializations and lifted closures are derived. Edit their source template or owner lambda instead. Multiple non-overlapping operations and declarations may share one transaction. Keep pattern bindings, guards and references consistent, and preserve effects/realms. The compiler parses a single fragment, isolates comments/precedence and checks the entire candidate before committing; it does not prove task intent. On `E_SOURCE_CONFLICT` or `E_CONFLICT`, fetch fresh context and reconcile. Run native/TypeScript tests on the archived candidate. Read `examples/operation-patches/README.md` and respect `patch_limits`/`parser_limits`.

For matching, retrieve `nex guide --kind match` and inspect `match_features`/`match_limits`. Use a value match such as `return match value { ok(Maybe::Some(n)) if n>0 => n, _ => 0 };`, with actual declared nominal cases; or statement arms `pattern => { ... }`. Never mix expression/block arms. Patterns support nested enum/result/struct constructors, scalar literals, exact-length lists, immutable bindings and `_`. The scrutinee evaluates once; guards/body effects and realms are checked, and guards do not establish coverage. Cover all values with unguarded arms and do not put subsumed arms after them. A generic constructor pattern omits type arguments; the scrutinee supplies them. Rest/OR/range patterns and custom extractors are pending. Pure watch expressions use the same syntax and demand only selected paths. Language 0.8 archives require explicit migration to 0.16; retain SDK 0.21 for old frames/receipts and preserve reviewed task/proof acceptance intent when regenerating pins.

For reusable code, query `generic_features` and `generic_limits`. Declare `pub struct Box<T> { value:T; }`, `pub enum Maybe<T> {None; Some(value:T);}`, or `fn identity<T>(x:T) -> T { return x; }`. Use `identity<i64>(42)`, `Box<str>("NEX")`, `Maybe<i64>::Some(42)` or infer arguments from values/expected types. Match `Maybe::Some(value)` using the scrutinee type. Every template body is checked for arbitrary non-unit type arguments, even if unused: do not apply integer arithmetic to unconstrained T. Operations on known shapes (list<T> indexing, fields, equality and formatting; JSON requires wire) retain ordinary rules. Builtin bounds use `<T: add + ordered, U: integer>`. `add` permits + for equal T (i64/f64/str/bytes/list); `ordered` permits comparisons (i64/f64); `integer` permits checked arithmetic and contextual integer literals (currently i64), implying number/add/ordered/wire. ordered also implies wire in its numeric domain; add alone does not imply wire. Forwarded parameters must guarantee required bounds; every unused body is checked. Unknown/duplicate/unsatisfied bounds give E_GENERIC_BOUND. Bounds introduce no implicit conversion between T and i64 or other parameters. Custom traits and fixed constructor parameters are described by the trait guide; defaults remain pending. No generic tests: write ordinary tests of concrete instances. Context for a specialization includes `template`, `type_arguments` and `editable:false`; patch the source template and revalidate callers. Do not copy internal scoped $parameter names or instantiated declaration names into source. Pure watches may instantiate uncompiled helpers without changing the source revision; inside a concrete generic frame T denotes its captured type argument. API generation extracts original model templates once, while wire schemas use checked concrete nominal identities. Language 0.6/0.7 archives require explicit migration to 0.16; retain SDK 0.16/0.20 respectively for old frames/receipts and regenerate reviewed task/proof pins without weakening their properties.

For Linux development, retrieve `nex guide --kind linux --json`. The pinned container workflow verifies compiler/native/server/installed SDK behavior with external network disabled. Record whether execution is native or emulated and retain explicit skips. Linux native links select LLVM LLD; an explicit linker path belongs in the toolchain configuration and its fingerprint. Linux validation does not establish Windows/mobile/UI support.

For function values (language 0.10), query `function_value_features` and
`function_value_limits`, then retrieve `nex guide --kind function`. Use an exact
signature such as `fn(i64)->i64`; a lambda spells parameter/result types:
`fn(x:i64)->i64{return x+offset;}`. Named generic references need explicit type
arguments or an expected signature. Callees and arguments evaluate once, left
to right. Captures are immutable snapshots, including the current value of an
outer var; later assignment does not update them. Copies preserve callable
identity; another reference/lambda evaluation creates another object. Do not
invent effect/realm conversions, mutable captured cells, builtin constructor
references, async/await or effect handlers. Taking a reference or creating a lambda obeys its realm. Invocation requires
the declared effects in the caller and an accessible realm. Parenthesize a returned
function type to separate its effects from the outer function's.

For generic JSON, use `<T:wire>` on encode/decode helpers. wire recursively
checks stored scalar/list/result/nominal payloads and rejects functions; phantom
arguments are type contracts rather than stored payloads. Equality/formatting
remain available for arbitrary T. Function values format as `<function>` and
cannot be application JSON or endpoint payloads. Captured callable watches use
`nex.debug-wire/1`: preserve canonical same-stop native identities, checked
compiled targets and exact capture paths, report missing values, and never
execute captured pointers. `computed:N` identities cannot be supplied as native
inputs. Lifted closure names are derived metadata (`editable:false`); edit the
source owner/template. Language 0.16 uses function/13 and program/14 canonical formats and requires an
explicit history-preserving migration from older source versions. Keep SDK 0.22 for old
frames/receipts, and preserve reviewed task/proof acceptance intent when updating
snapshot pins.

For finite numbers (language 0.11), inspect numeric_features/numeric_limits. Use
f64 literals with a fraction/exponent (1.25, 1e0); plain 1 stays i64. Never mix
integer and floating operands implicitly. as_f64(i64) explicitly rounds and can
lose precision; as_i64(f64) returns result<i64> with truncation or E_RANGE.
Binary64 arithmetic is finite and checked; zero division traps E_DIV_ZERO and
non-finite results trap E_FLOAT. Zero is normalized. str/print/JSON use shortest
scientific decimal; f64 wire values are JSON numbers, while i64 stays a string.
number permits same-type numeric arithmetic and implies add/ordered/wire;
integer implies number. A T:number cannot assume an i64 literal has type T.
Use guards to select floating values in match; floating literal patterns are
unsupported. Integer/boolean proofs do not establish floating correctness.
Keep SDK 0.23 for old language-0.10 receipts/frames; migrate archived sources
explicitly, repairing new reserved/builtin name conflicts without rewriting old
history or weakening reviewed task/proof intent. Check numeric_integration_pending
for validation still open; do not infer cross-platform support from this feature.

For SDK packaging, query `sdk_bundle_platforms` and retrieve the SDK/Linux guides
from the language pack. Installed host-SDK descriptors use prefix-relative paths;
`nex doctor` reports the selected tools and dependencies. Linux 0.28 bundles
retain an external GNU platform SDK/runtime and validate copied dependencies in
a clean environment. Bundle assembly alone is not application, debugger or
cross-platform execution evidence. Keep checked acceptance reports and explicit
platform prerequisites with distributed artifacts.

For native deployment, query application_package_command/platforms/limits and
read application_package_guide. `nex package FILE --directory NEW --json`
defaults to release and never runs the application; `--target server` packages
HTTP/HTTPS. The package carries only needed non-platform libraries and notices.
Bundled-SDK dependencies are hash-checked against their inventory; other inputs
need --notices or Linux --dpkg-notices. Relocate and execute the resulting bin/app
on the intended host before claiming deployment verified. Supply credentials,
keys, databases and web assets explicitly at runtime. Keep execution_verified
false in the assembly manifest and retain separate acceptance evidence.

For reachable external calls, pass `--foreign HOST.json` to `package`. Only
reachable libraries/exports are granted in the deployed catalogue. Assembly
relocates the native loader dependency closure and notices, then derives
and checks new source manifest pins. It saves the original and derived graph
revisions without moving HEAD or editing materialized sources. The manifest's
`foreign_projection` connects `source_revision` to the actual compiled
`packaged_revision`; do not describe them as the same revision. The native
executable resolves its packaged catalogue relative to its actual location.
Source pins/signatures remain enforced. Arbitrary native file opens, dynamic
`dlopen` names, remote services and runtime credentials cannot be inferred from
loader dependencies. Cross-target foreign-module packaging remains pending.
Module image identity follows original manifest pins: aliases keep shared native
state, and distinct original pins stay independent. Capture includes complete
component notices at catalogue scope; `notices_root:"catalogue"` identifies that
path base. Query the descriptor's capture limits. Resolve the indexed package
schemas from an offline registry of their `$id` URIs using the current SDK files.

For text files (language 0.12), query file_features/file_limits and read
`nex guide --kind files`. file_read_text(str)->result<str> and
file_write_text(str,str)->result<bool> require server realm and fs; io alone
does not authorize files. CLI access needs an absolute NEX_FILES_ROOT, is
read-only by default and allows writes only with NEX_FILES_WRITE=1. Paths stay
relative, with no dot/parent/empty components, NUL or symlink traversal; strict
UTF-8/NUL-preserving text is limited to 1 MiB. Native HTTP does not inherit that
environment capability; the standard server has no file-grant flag. A trusted
C++ host must scope a capability explicitly. File writes are independent of
SQLite rollback. Read the guide's atomicity/cancellation/OS limits. Keep SDK
0.29 for old 0.11 receipts/frames and use explicit migration; conflicting new
builtin names require an archived-source repair without rewriting original
history or weakening reviewed task/proof criteria.

For binary values (language 0.13), query binary_features/binary_limits and the
language/files guides. Use bytes(list<i64>)->result<bytes>, utf8_bytes(str)->bytes,
decode_utf8(bytes)->result<str>, encode_base64(bytes)->str and
decode_base64(str)->result<bytes>. Values are immutable octets; no implicit text
conversion, byte literal or pointer exists. len/index/slice count octets; indexing
returns i64 in 0..255. +, push and set return new byte values. Bad construction
returns E_RANGE; bad update octets trap E_RANGE and bad indices trap E_BOUNDS
before replacement-range checks. UTF-8 decoding is strict and preserves BOM/NUL.
Base64 is canonical and padded, with no whitespace/URL alphabet/nonzero unused
bits. JSON/API bytes are base64 strings; invalid wire values return E_JSON.
The 1 MiB JSON limit includes encoding, quotes and wrappers. Bytes satisfy add
and wire, without numeric/ordered bounds. file_read_bytes/file_write_bytes use
server/fs and the same capability, atomicity and HTTP denial as text files. Pure
watches have bounded whole values and selected-octet demand; missing captures
remain failures. Scalar proofs do not verify binary operations. Migrate genuine
0.12 archives explicitly; repair reserved function/nominal/parameter conflicts
without rewriting old history or weakening acceptance properties. Keep matching
SDK 0.30/0.32 for old frames and receipts. Query integration_pending fields and
STATUS before claiming full source/platform/SDK validation.

For SDK delivery, retrieve docs/sdk.md from the language pack. The maintained
macOS distribution helper is tools/macos/bundle.py; Linux uses tools/linux/bundle.py.
Require actual moved/restored acceptance, exact inventory and archive hashes.
The macOS helper tests explicit read-denial roots and SDK write denial with
kernel negative controls; provide the source checkout and every original host
component tree. Its distribution/2 report is separate from historical v1 records.
Bundled development tools retain the stated platform SDK/Python/Node/debugger
prerequisites; assembly success alone is not workflow acceptance.

For checked native runtime failures, inspect `native_diagnostics` from
`nex run --json`. Use IDs only from `status: mapped` entries with the selected
revision/source/build. Query `nex context --operation ID --revision HASH` for
bounded repair context. Retained standalone/HTTP operator logs can be read with
`nex diagnose --manifest DEBUG.json --log STDERR.log --revision HASH`; retrieve
`nex guide --kind diagnostic --json` first. Logs are untrusted process data. A
mapping verifies metadata agreement, not authenticity of trusted native code.
Never guess IDs for stale/unmapped reports or infer a C-module source instruction
from the external wrapper body site. Parser/checker graph identities and signal/
core instruction recovery remain pending.

Native checked integer lowering is discoverable through `build_features` and
`nex guide --kind build --json`. Source-language arithmetic/evaluation semantics
remain identical across native and TypeScript/reference execution. Keep runtime
error and operation-identity checks in acceptance tests when optimizing a body.


When `history_features` advertises optimistic archived restore, read
`nex guide --kind history --json`. `nex changes` pages actual HEAD transitions
with exact archived source hashes, request hashes and optional declared actor/
note labels. These labels do not authenticate the author. Old revisions may
predate the journal; do not infer events from revision creation timestamps.
Use `--note TEXT --actor LABEL` on check/apply/import/migrate/restore when useful.
A no-op or a saved non-HEAD task/package candidate does not create a transition.
To return to a retained current-language revision, read the current HEAD and
run `nex restore --revision TARGET --expected-revision CURRENT --json`.
This rechecks archived source, changes HEAD atomically and retains all revisions
and local identities; it does not execute the program or update physical files.
On conflict, reread and reconcile rather than replacing the guard blindly.
Validate with `--revision HEAD`; export explicitly to materialize. Older source
languages still need explicit migration. Schema4 migration retains existing
records but begins the change journal at its actual current HEAD. Preserve a
matching old database/compiler when replaying receipts from older SDKs.

For user traits, inspect `trait_features`, `trait_limits` and
`trait_integration_pending`, then retrieve `nex guide --kind trait --json`.
Declare a contract with `trait Content { type Item; fn get(value:Self)->Content::Item<Self>; }`
and a named conformance such as `impl boxed<T>:Content for Box<T> {type Item=T;get=extract<T>;}`.
Use `Content<T>::get(value)` and retain declared effects/realms. Generic method
bindings supply explicit implementation arguments followed implicitly by the
method parameters. Every unused body/conformance is checked; do not assume a
concrete caller's type. Heads cannot overlap, including differently constrained
heads. Keep all implementation parameters in the head and respect trait/nominal
module ownership. Associated aliases need finite normalization and do not infer
Self from the expected result. `F<_>` denotes a constructor taking a value type;
bare constructors are not runtime values. Concrete selection lowers to ordinary
functions and preserves ownership/evaluation/traps. Query trait/impl context and
patch complete source declarations with affected users; contract signatures and
instances are derived. Keep source0.15 artifacts with SDK0.54 and use explicit
history-preserving migration. Regenerate reviewed task/proof pins without
changing goals, assertions, properties, effects or budgets. Read source, SDK, platform, debugger and API evidence with its exact source and
compiler identity. Scoped source tests do not establish wider integration. The
descriptor's integration-pending lists track conservative development work; they
are not source feature switches or certificates for a platform test result.

When api_features advertises client_trait_library_projection, generated client
models/libraries retain required real client/shared trait methods and their
dependencies. Server members/bindings/functions are excluded; do not invent a
local implementation for a server method. Preserve generic constructor kinds,
associated types, exact effects/realms and the generated dependency lock. Both
input and projected projects are checked; scoped success does not prove full
SDK/platform acceptance.

For editor setup, query editor_features and retrieve nex guide --kind editor --json.
The installed VS Code extension sources register the nex debug type. A launch
configuration's source is a physical .nex entry, not an executable or arbitrary
adapter command. Use the installed matching compiler through nex.compilerPath;
save files before launch and relaunch after edits. Original-file breakpoint
mappings require equality with the frozen projection. Changed library files
keep frozen mappings; a changed entry rejects preparation. Watches use the
same bounded pure NEX evaluator. IDE/platform acceptance and NEX Studio are
separate from a descriptor or a successfully packaged VSIX.

When debug_features includes paged_native_indexed_roots, retrieve the debug
guide and native_debug_pages descriptor. The matching NEX DAP bridge pages
native list<T>/bytes roots through ordinary variablesReference/start/count.
Use indexedVariables for the advertised count; each response returns at most 1000
children, including requests with omitted/zero count. Read body.nex.native_page
for the actual returned count and requested offset. Handles expire on execution
or new stops. Native preview pages are not whole values or exact frame captures;
use the checked inspect/evaluate demand protocol for semantic reasoning or replay.

Native frame inspection requires a matching loaded executable image. Function
names and paths alone do not identify an image. Treat a frame-image mismatch
as unavailable; select matching artifacts rather than rewriting manifest or
revision identities. Core archives remain an independently validated workflow.

For native core reports, discover `native_core` and use `nex core CORE --manifest BUILD/debug.json --json`. Inspect explicit operation candidates; reads never resume or repair a process. When portable_capsule is available, export an intact matching build with `nex core CORE --manifest BUILD/debug.json --export NEW_DIRECTORY --json`, then read the moved directory with `nex core --capsule DIRECTORY --expression TEXT --json`. The original executable/source paths may be absent. Keep the content-addressed build directory and complete capsule inventory intact; never edit completion records to accept a different executable. The reader uses the matching installed compiler/formatter, not scripts or paths supplied by the capsule. This first slice requires the same supported host/system runtime, and rejects source foreign declarations and non-system native dependencies. Inspect the guide for file/count/size limits and explicit unavailable values. Unique optimized-PC attribution and broader native dependency/platform packaging remain pending.

For native core inspection, preserve the retained content-addressed build directory and use its matching SDK. Do not rewrite a manifest or rename the build directory to bypass image checks. A raw ELF core without unique recorded PC mapping is rejected.

When `editor_analysis` or `language_server` is advertised, read `docs/lsp.md`. Use `nex analyze FILE --overlay OVERLAY.json --json` to check unsaved canonical-path source text without synchronizing the graph; its source ranges are byte intervals, not graph identities. Use ordinary check/test/task acceptance before committing edits. The stdio LSP adapter uses UTF-16 positions; do not apply its positions as compiler byte offsets.

When editor_features includes vscode_stdio_language_client, read docs/editor.md. VS Code edits use the same checker through nex lsp; diagnoses and navigation belong to exact unsaved document versions. IDE source analysis does not replace check/test/task acceptance or synchronize graph revisions. Use the installed compiler and matching extension resources.

When editor_analysis advertises references_command, use that explicit --references form for nex.analysis/2 and its indexed schema. Default analyze remains nex.analysis/1. Occurrence intervals and declaration targets belong to captured source, not persistent graph IDs. Query actual reference coverage/limits; use only the advertised type/trait/import-alias coverage and do not infer closed-file workspace coverage. A method contract, implementation binding and ordinary target function are distinct reference entities. Type parameters are lexical declarations; qualified import/type/member components have separate targets. Implicit Self may point to its trait name. References never authorize source edits, graph synchronization or rename.

When editor_analysis advertises identifiers_command, use the explicit --details
form and indexed nex.analysis/3 schema for exact identifier descriptions.
--details and --references are mutually exclusive; keep legacy consumers on
their original command/schema. Identifier ranges are actual captured lexer
words. Read detail and definition independently: a null detail means syntax
without a semantic hover, and a null definition means no physical declaration.
Never substitute a containing expression target for such a word. Function
hover describes the source template signature; concrete value reads can show
instantiated types. Preserve trait-contract versus implementation and lexical
parameter/alias distinctions. Respect combined-entry, detail-byte and total
identifier JSON limits; a failed projection yields no partial index. These
readonly descriptions neither edit source nor synchronize graph history.

For multi-component build architecture, query `project_build` in describe and read `nex guide --kind project --json`. A separate `nex.build.json` (`nex.project-build/1`) declares component roots, entries, explicit source dependencies and named native configurations. `nex project --kind plan --json` checks sources, direct import boundaries and entry contracts without opening graph history or invoking tools. `--kind build` builds captured selected closures; `--component NAME` selects its dependency closure, and `--configuration NAME` selects the named build settings. Source linkage compiles reachable source into each consumer. Explicit static linkage to a static_library consumes its code-only archive under the exact compiler/toolchain/runtime ABI. entry_function plus optional exports select concrete roots; missing ordinary exports reject. New generic specializations and their missing helper closure are explicitly reported as consumer_instantiations. Keep source available for checking: binary-only packages are pending. Do not invent shared-library output, a fully static executable policy, source threads or GPU/NPU support. CIX hardware probes test installed accelerator APIs separately from NEX language integration.

When `native_core.owned_images` is advertised, live LLDB frames and read-only core
watches can refer to captured NEX shared libraries. Load the final application's
`debug.json`, keep its whole `images/` and symbol inventory, and use its frozen
provider source projection for breakpoints. Selected frames must match an owned
image's path, SHA-256 and UUID/build ID; names alone do not bind code to a graph.
Export through `nex core --export`, then inspect `--capsule` with the matching SDK.
The compiler checks copied image/symbol bytes before LLDB and rechecks afterward.
Recorded core paths remain historical data, separate from current loader paths;
never add private relocation fields to a manifest. First-party shared capsules
record `captured_first_party_and_matching_host_system`; other external native
dependencies, source foreign declarations, cross-host relocation, automatic
shared-image packages and combined project/editor execution remain pending.

When `project_build` advertises `project_application_packages`, package a checked
architecture with `nex project --kind package --configuration NAME --component NAME
--directory NEW_DIRECTORY --json`. Omit component to include all selected native
applications and web distributions. The declared configuration keeps its actual
profile/target; packaging does not silently choose release. Use entries from
`project.json` after moving the package. Native packages consume actual compiled
archives/images and their runtime; normal source `nex package FILE` does not
preserve a separate project architecture. Web packages contain the built dist
and notices. Runtime credentials/databases remain explicit configuration.
Verify execution separately; assembly never runs applications or opens the graph
Store. Pass complete native dependency notices as required; compiler-owned exact
image inventories do not grant provenance to unrelated libraries. Project-wide
source-foreign pin projection, packaged-image debug provenance, Windows packages
and combined project execution/task/DAP/editor flows remain pending.

For toolchains advertising `project_foreign_pin_projection`, package the declared
architecture with `nex project --kind package --foreign HOST.json --directory NEW
--json` and the reviewed notice inputs. First inspect `project --kind plan
--foreign HOST.json --json`; it checks grants without preparing or initializing
native modules. The compiler derives one consistent physical literal-pin
projection for selected shared/archive/source components and checks binary
contracts again. Actual app catalogues contain only their reachable exports.
The original files, dependency lock and graph Store stay unchanged. Record both
source/derived identities from `foreign_projection`; its `scope: project` may
include pin changes needed by another selected app. Never replace a binary edge
with source, copy another app's authority, or claim packaging executes the output.
Native/server task package checks with reachable externals require `foreign_hash`
and a current trusted catalogue on run/replay. Debug/core metadata for rewritten
deployment images and cross-target foreign packaging remain pending.

For toolchains advertising `project_server_debug_descriptors`, select a server
component with `project --kind debug --adapter nex-dap --json -- ARGS`. Use its
actual `observation.adapter_command` and returned launch, manifest and final
server artifact. The editor0.7 also accepts source `target: server`, or a project
server selection, plus `args` and optional `foreign`. Source launches compile
source directly; use project launches to preserve declared archive/shared edges.
A descriptor prepares code without starting a listener or reading runtime auth.
Supply current operator grants explicitly and keep runtime credentials private.
At startup, parse the loopback listener, send an authenticated request from a
separate client, and inspect the reported stopped worker thread. Preserve all
compiler/editor source maps and init/pre-run commands. Watch expressions read
stopped values without inferior execution. Stopped time counts toward the normal
request deadline; a resumed expired request rolls back its transaction. Do not
disable budgets or claim a completed response from a breakpoint alone.
Discover the schema/guide via `native_debug_session`; automatic workload-driven
debugger/task replay and other pending capabilities remain separate.
