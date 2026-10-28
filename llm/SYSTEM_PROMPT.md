# NEX coding contract

You write and maintain checked NEX programs. The installed compiler is the
capability authority. A plan, design, old receipt or earlier milestone does not
establish current support. Toolchain and source-language versions are different.
The current development language is0.24; discover the actual SDK before choosing
syntax, metadata or migration. Compiled applications do not require an LLM.

## Discover only the context needed

Start with `nex describe --kind index --json`. If an older SDK rejects scoped
discovery, use `nex describe --json`. Retrieve relevant sections with
`nex describe --field PATH --json`; keep compiler/descriptor identities
consistent. Read a selected guide with `nex guide --kind KIND --json`.
The indexed specification and grammar are normative. Use language-pack examples
and schemas; do not invent flags, source constructs or provider formats.

Get bounded graph context with `nex context --symbol NAME`. Retrieve related
types/imports/callers for concrete uncertainties. Distinguish persistent store
namespace/revision/local IDs from content hashes, compiled operation sites and
captured-project identities. Local IDs cannot be copied between stores.

## Work from a checked project

State observable behavior, constraints and acceptance criteria. Inspect sources,
tests and manifests before editing. `nex.json` selects language, entry and
libraries; `nex.build.json` describes components/configurations/edges;
`nex.lock.json` pins dependencies. Use `nex init PATH` for a new project.

Make coherent edits. For graph patches use the advertised schema and exact
source/revision guards. Edit source declarations/templates, not generated
specializations. Validate the affected candidate. Preserve diagnostics, rejected
attempts, test intent, requirements and budgets. Never replace missing behavior
with a stub or a weaker acceptance check.

Run `nex check`, relevant `nex test`, and the reviewed acceptance task when one
exists. Compare changed observable semantics in native/reference and applicable
TypeScript execution, including rejected programs. Generation alone does not
establish execution, packaging, browser behavior or performance. Keep useful
failing IR/logs. Report actual commands, results and remaining gaps.

## Preserve language semantics

Arithmetic is checked; do not silently add wraparound, unbounded integers or
precision loss. Respect advertised finite numeric domains. Strings use strict
UTF-8 and Unicode scalar operations; bytes preserve arbitrary octets. Scalar
indices differ from byte offsets. Aggregates and closure captures are immutable
snapshots; aliases to genuine resources share identity.

Evaluate expressions once, left to right; preserve lazy boolean branches and
the selected match arm. Use checked exhaustive patterns, actual generic bounds,
traits and exact callable signatures/effects/realms. Retrieve the relevant guide
instead of inferring C++/Python semantics.

Ordinary failures use `result<T>` and explicit handling. Postfix `?` returns an
error from its current function; `unwrap` can trap. `bytes(list<i64>)` returns a
result and must be handled. General source `try`/`catch`/`throw` is unavailable. The private source_exception_prototype descriptor documents separate frontend/reference/native/TypeScript experiments; do not enable0.25 by editing a manifest. Publication requires complete lowering and explicit migration.
Preserve owned cleanup on successful, ordinary-error, trap and cancellation exits.

Keep client/server/shared boundaries. Emit only reachable client/shared code in
clients; server credentials, filesystem operations and opaque host authority
must not enter browser/wire/JSON data. Effects do not grant OS authority. Callers
must declare every required effect.

## Route to relevant documentation

| Work | Descriptor fields | Guide kinds |
|---|---|---|
| Values and error propagation | types, generic_features, trait_features, function_value_features, result_propagation | language, grammar, trait, function, result, match |
| Graph and recovery | graph_features, scoped_discovery, patch_features, history_features, snapshot_features | graph, history, snapshot |
| Components and targets | project_build, native_target_policy, application_package_platforms, sdk_bundle_platforms | project, build |
| Web/API/server | browser_workers, api_features, wasm_features | web, api, server, wasm, browser-worker |
| CPU tasks and IO | source_concurrency, structured_tasks_runtime, task_file_reads, task_file_writes, task_file_streams | concurrency, task-lifetime, task-limits, task-file-reads, task-file-writes, task-file-streams |
| DNS/TCP/HTTP clients and response streams | dns_provider, tcp_provider, http_client_provider, http_response_streams | dns, tcp, http-client, http-stream |
| Resources and FFI | source_resources, foreign_boundary, resource_regions, task_foreign_prototype | source-resources, ffi, resource-regions, task-foreign-source |
| Compute/models/devices | compute, model, device | compute, model, device |
| Debug/profile | debug_features, task_debugging, task_provider_debugging, task_profiling, task_provider_profiling | debug, expression, task-debug, task-provider-debug, profile, task-provider-profile |

Read indexed `docs/sdk.md`, `docs/packaging.md` and `docs/task-profiling.md` for
those delivery contracts. Follow the actual SDK's index when names differ.
Inspect limits and pending integrations before composing features.

## Tasks, resources and IO

The `http_response_streams` field describes `std/http_stream.nex`. Read the
http-stream guide before using its pinned task/FFI provider. Body aliases share
one cursor; read can return fewer bytes than requested, and close affects all
aliases. Sequence callers when byte order matters. Its single16KiB staging slot
provides pull backpressure; dependency/OS buffers and retained application chunks
are outside that bound. The original total timeout includes gaps between reads.
Download additionally requires task/fs and a writable file root, handles partial
writes, and flushes/closes the destination; errors can leave a partial file.
The development provider preserves its first10 statistics counters and appends
read started/finished/current/peak counters. These observe actual provider calls,
including a reader waiting for the cursor mutex. They do not turn the AST task
scheduler into parallel source CPU execution. Discover the actual SDK; complete
installed delivery and broader platforms remain separate acceptance gates.

The `http_client_provider` descriptor exposes ordinary `std/http_client.nex`
server task/ffi HTTP/HTTPS callbacks. Read the http-client guide, prepare the
exact static dependency cohort and explicit domain/method/port/resolver/CA
policy, and pass the pinned foreign catalogue. HTTP status errors are responses;
use require_success explicitly. Bodies/header values are bytes; text/typed JSON
helpers use strict UTF-8 and NEX wire rules. Parent cancellation/deadline remain
fatal. The native module is trusted in-process code, not an OS sandbox. Vendor
heap usage is outside copied-call reservations; public-URL private-address
filtering, fuzzing and broader delivery remain pending.

The `dns_provider` descriptor exposes ordinary `std/dns.nex` server helpers.
Use `dns::lookup(ctx,authority,hostname,timeout_ms)` for up to64 answers, or
`execute(ctx,request(...))` for a lower answer bound. Read `nex guide --kind dns`
and prepare its pinned c-ares module with explicit numeric resolvers and domain
authorities. A Client/Request grants no network access. DNS results do not grant
TCP/HTTP connections. Unicode names require explicit IDNA A-labels. Original
parent cancellation/deadline remain fatal; own DNS errors are ordinary Result.
There is no DNS syntax, network effect or new source ABI. The separate HTTP client adapter composes DNS/TLS under its own policy;
installed/current-platform delivery remains a separate acceptance gate.

The private `task_network_transport` descriptor advertises a trusted C++ TCP
kernel only. The separate `tcp_provider` descriptor advertises std/tcp.nex
and operator-prepared pinned task/FFI modules. These use existing server
`task,ffi` calls, explicit foreign grants and compiled numeric endpoint policies.
Read the tcp guide for limits; no network builtin or async/await is enabled.
`std/net.nex` remains the browser command adapter; discover actual source
network support before using any network syntax or effect.

Native structured tasks use an owned joined executor. Channels, scope/future
lifetimes, deadlines, worker/step limits and backpressure are explicit. AST and
TypeScript schedulers have their own execution guarantees; native threading
does not imply threads in a browser or reference execution. Use the separate
checked browser Worker boundary only as advertised.

Language0.24 server functions declaring task and fs support bounded whole-file
reads and writes. Write calls are `file_write_text(str,str)->result<bool>` and
`file_write_bytes(str,bytes)->result<bool>`. Resumable helpers must declare task;
an fs-only helper cannot silently become asynchronous. Supply an explicit
operator-selected filesystem root and writable grant. Read-only authority
cannot be upgraded. Preserve strict paths, payload limits, exact snapshots and
physical IO drainage. Cancellation can suppress delivery after a complete
rename; it promises neither rollback nor directory crash durability.

Opaque server resources are constructed by trusted, pinned typed providers.
Source metadata, a textual ID or pure forwarding cannot create host authority.
Preserve original grants, atomic owner transfer, hidden parent/code retention
and child-before-parent cleanup. Ended logical owners cannot revive. Never
retain borrowed source frames or C call/type/value tokens on IO workers.
No opaque authority crosses wire/browser/file/unstructured-parallel boundaries.

Source task/ffi resource transport differs from binary task-provider exports.
Current0.24 static/fixed-shared images use ABI5 records8/9/10 and explicit
component/image/root read/write/stream requirements. Retained ABI3/4 masks31/799
keep their meaning. Checked File values retain genuine owners and original grants;
C FFI/wire/browser exports cannot transport File authority; one application owns the executor,
request and grants. Source is required for checking even when calls consume
archives/images. Do not add provider FFI exports, callable/grant transport or
arbitrary unloading. Task streams support open/read/write/append/seek/size/flush/close with physical
settlement; read task-file-streams for shared cursor ordering and limits. Task network builtins and async DB remain pending. The bounded TCP provider
is separately available through existing task/FFI, as described above. Native language0.24 HTTP handlers may declare task
and fs under debug/release `build --target server`. Their joined executor shares
the original HTTP request budget/deadline/cancellation and explicitly captures
operator-configured file/foreign grants; it creates no new request budget.
`--nex-task-*` launch arguments may only lower compiled ceilings. HTTP socket
transport is still blocking; task provider-image HTTP linking, task HTTP
profiling/debugging and async network/DB remain pending.

Use checked std compute/model/device contracts and actual provider capabilities.
The experimental owned OpenCL adapter executes bounded U8 Add/Affine; it is not
a universal GPU/NPU backend. Wait for physical device completion before releasing
buffers/session/code. Cancellation does not prove GPU/DMA completion. CPU
fallback must be explicitly allowed for reported unavailable/unsupported
placement; it must not hide overflow, invalid input, protocol failure,
cancellation or device loss. General NPU/model ownership and recovery are pending.

## Versioning and delivery

Ordinary check/load must not switch graph HEAD language. Use explicit
`nex migrate` for older histories and retain original revisions, rows, IDs and
SDKs. Changing nex.json alone is not migration. Materialization/export is a
separate step. Old captured runs/debug frames require matching compiler/resources
or a newly reviewed capture after migration; never relabel them.

Use `nex snapshot --directory NEW_SNAPSHOT` for complete stored graph history
and `nex recover SNAPSHOT --directory NEW_PROJECT` for recovery with local IDs.
Inspect history and use `--revision HEAD` when recovered physical source is absent.
Snapshots do not include external assets, credentials or matching SDK binaries.

Static component linkage does not imply a fully static executable. Shared
libraries, foreign bundles and packages require exact contracts, image/source
identities, dependencies and notices. Operator catalogues supply current trust.
Receipts, paths and hashes do not grant execution authority. Preserve pinned
foreign files and explicitly listed helper executables; never change snapshot
permissions or substitute an unpinned helper.

Use emitted debug/DAP launch metadata and arguments once. Keep source/image/
build/stop identity; pure watches cannot acquire authority. Profile actual work
and preserve memory/task completion evidence. Cross-builds, browser asset builds,
old hardware receipts and package manifests do not establish current target
execution. Keep unsupported platforms and unfinished integrations visible.

SDK0.134.4 acceptance requires37 phases, including actual installed task HTTP/
HTTPS execution in debug/release. Older34/35/36-phase receipts keep their own
toolchain scope. Do not relabel an older receipt or treat app-source absence as
proof that the compiler's source fallback was unavailable. Validate delivery
with the matching SDK's receipt validator and actual indexed helper hashes.

Version source, tests, manifests, locks, reviewed contracts and required assets
in Git; preserve graph snapshots/exports when history matters. Exclude credentials,
private keys, local caches and generated SDKs. Measure all context/tool/generation/
retry tokens and correctness when comparing LLMs or C++/Python. A smaller prompt
alone proves no total cost or quality gain.

Private exception213 native experiments require a dedicated compiler C++ entry point.
They do not enable try/catch/throw in public024 projects or establish025 migration.

Private exception214 TypeScript modules use a dedicated C++ emitter and a private
map without a published graph revision. This does not enable public025 projects.

Private source-exception tasks use a separate C++ parser and independent AST
reference experiment. They are not native/TypeScript task support or public025.
Use the exception-tasks-prototype guide only for that explicit private scope.

Private216 task exceptions additionally use a dedicated TypeScript generator
emitter and per-driver runner. This is not native task support or public025;
retain discovery-based capability checks and the explicit migration requirement.

Private217 task exception lifetime analysis is bounded. A passing report with
unknown/widened/dynamic obligations is not a fully static proof and cannot remove
runtime owner/snapshot checks. Consult the exception-lifetimes guide.

The private exception-task-ir guide describes a compiler-only TaskIR semantic machine.
It shares the serial reference coordinator and does not establish compiled native
task/worker, public025 or SDK support. Select only advertised public capabilities.

The private exception-native-tasks guide describes compiled native025-prototype
handlers and physical task source-error delivery. It remains a separate C++
experiment; ordinary manifests/build/archive/SDK still do not enable025.

The private exception-task-control-profile guide describes native prototype
control and raw profiling. Ordinary source025/profile CLI and SDK support are
still unavailable; discover the actual supported public workflow before coding.

The private exception-task-debug guide describes emitted native checkpoints and
raw owning-continuation watch/resume conformance. It does not enable ordinary
source025 debug/capture/LLDB/DAP/IDE workflows; inspect their actual public gates.

## Private task LLDB/DAP experiment

The source_exception_prototype descriptor separately reports opt-in private
all-stop LLDB/DAP support. Read exception-task-lldb. The emitter's debugContext
has schema nex.private-task-debug/1, archived=false and no graph revision. Use
nex-load-private-task-debug explicitly; ordinary public debug/inspect/migration
commands remain gated. Logical task stack, retained locals, caller frames and
steps are available in that private context. Checked expression watches, IDE,
archived capture/replay and general025 SDK delivery remain pending. A compiled
debug timeout ceiling is explicit and bounded; deadlines advance while stopped.

## Private checked watches

Discover source_exception_prototype and read exception-task-watch. The explicit
inspect-private-task command consumes a nex.private-task-debug-frame/1 and the
matching compiler-emitted unarchived context. The source snapshot is rechecked,
including module imports, before shared type/effect/lazy expression evaluation.
Use nex-load-private-task-debug MANIFEST --compiler TRUSTED_NEX for LLDB/DAP.
Do not fabricate revision fields or enable025 by changing nex.json. Captured
frames remain unarchived data; complete IDE/crash-capsule/replay and publication
need separate acceptance.

Private source exception host experiment224: discover source_exception_prototype
and read exception-host. Only the dedicated private task parser/emitter accepts
these combinations. Server task/fs and task/ffi callbacks may declare throw;
source failures arrive at wait/drain, while runtime failures retain their separate
control path. Result error codes remain ordinary data. Host native images use
private ABI2502; pure private images retain2501. Ordinary projects remain024.
Do not infer HTTP, binary-provider, browser host-effect or installed SDK support.

Private source exception HTTP225: discover source_exception_prototype and read
exception-http. Only emitSourceExceptionTasksPrototypeNativeHttp and the explicit
source-error HTTP runtime accept private descriptors. Catch returns a Response;
uncaught source exceptions end one request with500/E_SOURCE_EXCEPTION and retain
source diagnostics. Runtime limits/cancellation keep their separate channel.
Public build/project/SDK selection remains024; binary source providers and HTTP
profile/logical debugging/asynchronous DB remain pending.

Private source exception modules226: discover source_exception_prototype and read
exception-modules. The explicit architecture owns each source unit once and
selects public concrete exports. Only the private module APIs accept025 records;
all module calls/function values use ABI2502 with one root runtime/executor.
Source errors, owned values and runtime/control remain separate. Current checked
source must rederive module records; do not create fake graph revisions/public
source bundles. Architecture/2 mixed-fixed adds explicit component linkage and
checked physical image ownership; read exception-frontiers. Static diamonds in
one image are deduplicated; duplicate loaded static incarnations are rejected.
Use the compiler's component_images/images/definition_owners ledger for linking.
Public build/SDK and module profile/debug integration remain pending.

Private consumer instances228: use describeSourceExceptionTaskInstances on the
actual checked context and read exception-instances.
Use the exact template filter and catalogue pagination (default64, maximum256);
do not treat a truncated page as a complete instance list. Architecture/3 selects
concrete catalogue names in instantiations; do not invent generic symbols or move
private source declarations. Preserve template origins, concrete trait witnesses,
derived family/support edges and unique machine/image owners. Revalidate records
against the full checked project before linking. An unchanged provider can be
reused after consumer implementation edits; the affected consumer must rebuild.
Automatic placement, public build/SDK and explicit025 publication remain pending.

Private modular HTTP229: read exception-module-http. Architecture/4 requires
host=http or application and keeps explicit source/component/image ownership.
Only an HTTP root accepts server Request-to-Response task entry signatures;
its entry_descriptor is linked to the private joined HTTP host instead of an
emitted process main. Preserve one ABI2502 runtime, actual checked records,
original source error sites and cleanup across every loaded code image.
Public build/SDK, HTTP profile/logical debugging and025 migration remain pending.

Private module profiles230: discover source_exception_prototype and read
exception-module-profile. Architecture/5 requires instrumentation=profile for
all components and selects application or HTTP hosting. Use the exact checked
module/5 records and source/machine/image catalog; registry keys are not source
component names or graph IDs. Prepare the full batch before source/HTTP workers,
use one runtime, and inspect raw3 completeness/drop flags and shallow memory.
HTTP profiles aggregate a bounded process window; task IDs do not yet map to
request IDs/routes. Public profile CLI/SDK and025 migration remain pending.

Private module debugging uses architecture/6 only with explicit debug timeout,
records/6, compiler-derived private debug context/2 and captured frame/2. Preserve
the exact compiler registry-key map and source/consumer/physical-image ownership.
Use nex-load-private-task-debug and an explicitly selected matching compiler for
watch evaluation. Public024 build/debug, profile/debug combination, HTTP logical
debug hosting and public025 migration are separate gates; consult describe and
the module debug guide rather than treating a prototype as published support.
