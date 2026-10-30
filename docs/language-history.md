# NEX language development history

These dated notes retain their original scope. They are historical evidence, not
the current capability contract. Read [language.md](language.md) and query the selected compiler.

# Candidate027 graph recovery and scalar Wasm development0.151.0

Explicit C++027 programs can use identity-preserving graph snapshot/recovery.
Mixed026/027 histories keep their schema, all16 tables, namespaces and local IDs;
reloaded source bundles execute through checked AST/TaskIR/native paths without
original files. Snapshot operations copy data; they do not grant a CLI language
upgrade or include external artifacts. See tests/typed_graph_snapshots.py.

Pure scalar027 Wasm uses the existing i64/bool/unit backend and checked BigInt
wrapper. Only reachable pure scalar code is emitted; source throw/catch/finally,
heap values and effects remain unsupported. The earlier026 output is unchanged.
See tests/typed_scalar_wasm.py. Ordinary/default CLI remains026. Matching full
regression, installed SDK/platform acceptance, public027 selection and the
remaining original PLAN are still required.

# Candidate027 checked browser delivery development0.150.0

Explicit C++027 UI/Worker builds now use checked revision/source maps with a
distinct version2 contract. Existing development027 maps and earlier-language
assets preserve their identities. Synchronous pure UI and synchronous/task Workers
retain their realm/wire/error boundaries. Source errors stay generic at worker
transport; callable/data payloads remain inside the checked computation.
Capture/replay and relocated static packaging are tested. Read
[the bounded browser contract](typed-web-delivery.md).

Ordinary/default source remains026. Full integrated/SDK/platform/public027
selection/snapshot gates and the original PLAN remain required.

# Candidate027 native debugger development0.149.0

Explicit C++027 native debugging exposes checked typed and legacy catch bindings
in synchronous DWARF and source/static/shared/mixed task images. LLDB/NEX-DAP
watches retain guard/catch scope, original concrete types and physical source
owners across suspension. Original source files may be absent; the captured
checked bundles and exact image/script/compiler identities remain mandatory.
Large aggregates use the existing bounded/lazy reads. File owners expose only
diagnostic identities; task authority/effectful callables remain opaque under
the existing metadata rules. Watches never grant IO or run inferior callbacks.

Expression diagnostics bind the actual captured source language in their ID.
The existing default diagnostic API retains its prior identity. Stale debugger
frames/variables and sibling-handler bindings remain rejected. See
`tests/typed_error_debugging.py` and `tests/frontend_diagnostics.cpp`.

Public/default source remains026. Integrated full regression, installed SDK,
platform acceptance, public027 selection and the remaining PLAN are still gates.

# Candidate027 native provider development0.148.0

Explicit C++027 selection now develops source/static/shared/mixed native builds
with taskABI7 and versioned provider/application/linkage records. Owned typed
errors preserve their value/key/site across images, suspension and finalizers.
The normal process entry accepts7; the development emitter remains2702 and
retained public/private task families keep their separate identities.
Read [the provider contract](typed-error-providers.md).

The ordinary CLI/default remains026. Public027 selection, graph-snapshot
delivery, bounded typed debugger views, full current regression and matching
SDK/platform acceptance remain required. This does not complete the full PLAN.

# Candidate027 archive/migration development0.147.0

Explicit checked027 source can now round-trip through `nex.program/15` and a
source bundle. Retained026 canonical identities stay on program/14. A guarded
same-store C++ migration rechecks the genuine old parser/revision, validates the
target, and appends a new graph HEAD without removing old rows, IDs or schema.
Expected HEAD and graph namespace are repeated inside the write transaction.
Plans and failed candidates do not open writable state; source materialization
is a separate explicit export. Unversioned save/synchronization cannot switch
into or out of027. See [the migration API](typed-error-migration.md).

Ordinary CLI/default projects remain026. Native027 build/project, provider,
UI/Worker, graph-snapshot and SDK delivery remain pending. The existing explicit
development emitters execute checked027; archival does not turn them into a
published cross-module delivery contract.

# Candidate027 authority transfer development0.146.0

Explicit027 C++ selection admits typed errors containing checked callables,
task scopes/futures/channels and native/reference file/external resource owners,
including nested aggregates and captures. Known owner escapes are rejected by
the exceptional lifetime pass. Unknown channel/call provenance retains mandatory
runtime guards; it does not acquire a longer lifetime from a catch clause.

A task validates its outgoing source outcome before its resource region ends.
Implicit scope close prepares an unobserved child's selected source payload
before retiring scope capabilities or resources. Native prepare runs outside
the scheduler mutex while actor/receiver regions remain live. Mixed file/resource
promotion is atomic after the complete bounded capability graph validates.
Real fatal errors win over a source transfer; cancellation and fatal traps still
skip user finalizers. Resource cleanup and physical settlement still complete.

New native code uses private cohort0x4e45585400002702. Retained2701 and public
88-byte ABI6 keep their identity; cross-cohort calls reject before mutation.
TypeScript027 generators require runTypedSourceErrors with the generated,
immutable sourceErrorContracts. Only included client/shared functions contribute
concrete keys; unknown keys fail E_SOURCE_TYPE. The scheduler uses keyed reads,
never an unkeyed payload getter or host payload callback. Public error details
remain copied code/message/site. Browser file/FFI/server authority remains rejected.

Exceptional analysis retains up to64 concrete error alternatives, then widens
to unknown with a runtime obligation. Rethrow, handler/filter replacement,
finalizer overrides, outer assignments, aggregate projections and future errors
preserve their actual provenance. No static-analysis bypass is shipped.

Tests cover real AST/TaskIR/Node/native results, known rejected escapes, runtime
escapes hidden behind legitimate channel receives, resource retirement and
bounded joins. Full development regression, source027 library/provider delivery,
public CLI/project selection, archive/migration, installed SDK and platform
acceptance remain separate gates. This development capability does not satisfy
those gates or the remaining project plan.

# Candidate027 resumable typed errors development0.145.0

Explicit027 C++ selection lowers ordered typed/legacy handlers through the
independent AST scheduler, TaskIR machine, native continuation frames and
TypeScript generators. Matching and binding share checked concrete type keys.
A declined filter releases its clause bindings and continues with the original
packet; an error from its predicate/body escapes every sibling handler. Typed
values and original source sites remain owned across yields, nested calls,
future observation, finalization and pending outcome replacement.

Catch dispatch has one protected boundary and one retained lexical packet.
Native descriptors use unpublished cohort0x4e45585400002701, distinct from the
unchanged88-byte public ABI6 and previous private025 cohorts. Cross-cohort native
calls and public application entry reject this development descriptor. New frame
helpers require that exact cohort; no existing provider contract is widened.
Existing runtime source hashes pin the matching implementation.

Payloads containing callable/file/task/resource authority remain rejected until
payload provenance and owner-transfer checks are complete. Lifetime traversal
preserves exceptional outer assignments and finalizer paths for ordinary typed
data; unknown throw effects conservatively retain unmatched edges. Public CLI,
projects/libraries/providers,027 graph migration, SDK and platform delivery
remain pending. tests/typed_source_tasks.py compares actual AST/TaskIR/Node and
native O0/O2 at1/4 workers, including real worker overlap and physical Data/Handle
retirement. These development tests do not certify the remaining delivery gates.

# Candidate027 synchronous native development0.144.0

Explicitly version-selected027 source now emits sequential pure/io/throw native
MLIR. Typed raises retain the original owned Value and complete concrete key.
One protected handler selects ordered typed/legacy clauses; declined filters
clean only their clause locals and retain the original packet. New predicate/
handler errors escape siblings. Bare rethrow and finally preserve source sites.
Bindings, captured snapshots and pending outcomes follow native owner cleanup.

The private runtime validates keys and scalar/heap kinds before binding. Result
accepts success or failure without erasing its concrete key. An impossible packet
mismatch after statically total coverage is a checked E_SOURCE_TYPE trap rather
than an undeclared source exit. Real O0/O2 LLVM/native execution and heap retirement
are exercised by tests/typed_source_native.py; packet helpers also have ASan/UBSan
coverage. Scalar Wasm, native projects/libraries, tasks and authority transport
remain explicitly pending. Ordinary CLI/projects stay026;027 graph publication
and genuine history-preserving migration are not enabled by this raw emitter.

# Candidate027 synchronous TypeScript development0.143.0

The explicitly version-selected027 program can now emit synchronous TypeScript
with typed raises and one ordered catch chain. The same concrete keys and
base-kind checks bind immutable values; predicate/handler errors escape siblings.
Source identity, original site, Result propagation and finally agree with the
reference engine. Only reachable client/shared code is emitted.

Typed data lives in private WeakMaps; public error details retain only copied
code/message/site. JSON serialization of those details or the error cannot
implicitly include the typed value. Matching plus a checked base kind is not a
full foreign aggregate validator; typed host/authority integration remains pending.
The generated development map has no public revision and makes no graph migration,
browser UI/worker delivery or installed SDK acceptance claim. Ordinary projects
remain026. Native, task/lifetime/protocol integration and027 publication remain open.

# Version-selected027 frontend/reference development0.142.0

Public CLI/projects remain0.26; typed_payloads stays false. The explicit C++
parseVersioned(..., SourceLanguage::TypedErrors027) selection adds throw(value)
and ordered catch(value:Type)/legacy catch(code,message) clauses. This is
unarchivable development syntax, not an enabled027 project or delivery claim.

The operand is evaluated once. Exact concrete keys select typed clauses;
nonmatching clauses skip their predicate. A false predicate tries the next
clause with the original owned packet. Errors from predicates/handlers escape
all sibling clauses. Bare rethrow preserves the packet/site; legacy replacement
creates a new packet. Legacy projection uses the stable type name and generic
message, without formatting the payload. Finally and Result ? keep026 semantics.
Handler values are immutable scoped bindings and may be captured as snapshots.

Only an unguarded/literal-true matching typed clause handles a directly known
raise for effect checking. Calls with coarse throw require an outward effect or
universal legacy handler; typed clauses never erase unknown throw effects.
Handler coverage resets across functions and closures. All handler predicates
and bodies use the enclosing coverage, excluding their siblings. New AST kinds
and conditional key fields are appended; retained026 canonical fields/ordinals
are unchanged.

Synchronous native and TypeScript generation implement these clauses in the
development API; graph archiving and public project selection still reject027
explicitly. Task functions and payloads carrying callable/file/task/resource
authority remain rejected until their continuation/provenance integration is
implemented. These are pending development gates, not the final027 contract.
See [typed error design](typed-exceptions-design.md) and tests/typed_source.cpp.

# Internal typed-payload transport0.141.0

Public source syntax remains0.26. `typed_payloads` stays false. Internal owned
packets/type identities and managed native roundtrips do not enable typed
throw/catch or authority transfer. Matching-key accessors also check the scalar
tag or top-level object kind before binding a value.
Read [the implemented foundation and proposed027 contract](typed-exceptions-design.md).
The resumable-finally rules below remain current; full139/140 receipts have
separate compiler/source scope.

# Resumable finally development (toolchain0.139.0 / language0.26)

`try { ... } finally { ... }` and `try { ... } catch(c,m) if guard { ... }
finally { ... }` are native/reference/TypeScript development features, including
resumable tasks. Complete acceptance and typed payloads remain pending. The portable `source_exceptions.finally` capability stays false; query
`source_exceptions.finally_development` for the exact engine scope.

The finalizer runs once after normal protected/catch completion, return, Result
`?` return, or an escaping explicit source error. The protected/catch lexical
scope ends before the finalizer; its locals and catch bindings are unavailable.
Outer mutable bindings remain visible. The return expression is evaluated before
the finalizer. A return, Result propagation or explicit source error from the
finalizer replaces the pending outcome. Nested finalizers run from inside out.
Bare throw keeps the enclosing lexical catch; a finalizer introduces no implicit
catch binding. An unchanged escaping source error retains its payload and site.

Fatal traps, allocation failure, cancellation and execution limits do not run
user finalizers. Runtime-owned resource cleanup remains independent. Finalizer
effects and realms are checked normally; this construct never catches a fatal
error or makes a Result error into a source error. Finally is appended as a new
statement kind; old026 AST ordinals and canonical identities are unchanged. Native emission
and TaskIR bound duplicated finalizer bodies to4096 per function (E_FINALLY_LIMIT).
The scalar Wasm backend rejects finally before tool invocation.

A task may suspend in the protected body, catch/filter and finalizer. Its pending
return or original source error remains owned across pauses. The protected
lexical scope is cleaned before finalization. A saved error is separate from
lexical catch state, so bare throw still names the enclosing source catch.
An overriding finalizer outcome discards the prior outcome. Lifetime analysis
runs the finalizer on normal, return, Result-propagation and explicit-error
states before admitting authority transfers. Scheduler cancellation, deadlines
and fatal traps skip user finalizers, including a finalizer which has paused
while an earlier return is pending; runtime-owned cleanup still completes.
The TypeScript host follows the same rule when it closes generators. Task
instruction ordinals and the public88-byte ABI6 descriptor layout are retained;
matching runtime sources provide the additive save/restore helpers.


---

# Language0.26 handler development

`catch(code,message) if predicate` evaluates a checked bool exactly once after
a source error enters that catch. Its immutable bindings are in scope in the
predicate and body. False rethrows the original error, preserving payload and
source site; a source error raised by the predicate replaces it. Runtime traps,
cancellation and limits remain separate fatal control. Guards keep left-to-right
and lazy expression semantics and may suspend only in an actual task function.

A filtered catch requires an outward `throw` effect or an enclosing handler.
Literal `true` is total and needs no outward throw effect. Predicate calls keep
their ordinary effect/realm checks. Result `?` returns from the current function;
it does not turn a Result error into a source error.

Native debug/release, reference/AST tasks and TypeScript use these rules. This
is an unaccepted development version; complete026 delivery is pending. Resumable
finally support is described above. Typed
payloads and the remaining original language/toolchain plan remain open.

Explicit025-to026 migration rechecks the genuine025 parser and revision first.
A025 declaration named finally needs a reviewed rename in the candidate. Old
revisions, rows, schema and local IDs remain unchanged; physical source/manifest
export is separate. The actual025 fixture is stored under
`tests/fixtures/language-0.25-handler-origin.*` and installed at the same paths in the SDK. Prior compiler/resource receipts retain
their original scope. See `examples/exception-filters`.

---

# Source exceptions — public025 integration candidate

The ordinary candidate frontend selects language0.25. The frozen Mac cohort
`c591f2d` passes all263 CTest groups and the installed SDK's39 phases, including
native/provider/debug/profile and browser workflows. These receipts apply to
that exact compiler/source cohort, not later changes or other platforms.
The accepted source233 and stable SDK209 remain separate0.24 tools. Inspect
source_exceptions and matching platform evidence before selecting a delivery.

`throw(code,message);` evaluates two str expressions once, left to right.
`try { ... } catch(code,message) { ... }` handles only explicit source exceptions.
Its immutable lexical bindings preserve strict UTF-8, Unicode scalars and NUL.
`throw;` is a lexical rethrow within the current function's catch; it preserves
the original payload/source site. A new throw has its own payload and site.
Functions/lambdas have independent effect and catch boundaries.

Throwing or calling a throw-effect function requires !{throw} unless a lexical
handler covers that expression. A catch does not handle its own new throw.
with_tasks/task_wait can deliver child errors and require throw or a lexical
handler. Runtime bounds/arithmetic/assertion traps, cancellation, deadlines,
allocation failures and Result errors never become catchable source errors.
Postfix ? still returns a Result error from its current function.

The ordinary native build now lowers sequential source errors and structured
task errors with public descriptor ABI6 (0x4e45585400000006). The descriptor keeps
its88-byte layout and ABI offset40. ABI3/4/5 and private2501/2502 retain their
meanings. Native task calls reject mixed source-error descriptor families.
TypeScript emits synchronous or resumable functions with ordinary public revision
maps; its scheduler classifies branded source errors separately from host traps.
Dedicated browser worker compute functions may declare task/throw and catch
child errors. Uncaught source errors cross the worker boundary as a generic
E_SOURCE_EXCEPTION transport failure; source payloads stay inside the worker.
Pure parallel_map callbacks may catch their own source errors; escaping throw
remains incompatible with a pure callback signature.

The Mac ARM64 development checks execute nine observable scenarios in native
debug/release and TypeScript, plus original uncaught payload/site and fatal trap
checks. Four normal-CLI HTTP images (sync/task, debug/release) pass24 real POST
requests; uncaught and rethrown source errors return HTTP500/E_SOURCE_EXCEPTION.
The server records the original source site and request ID and keeps the payload
out of the HTTP error body. Request cleanup and subsequent requests pass.
Explicit HTTP `--files-root` grants now feed synchronous/task handlers; read-only
is the default and `--files-write 1` grants writes. The expanded Mac regression
passes36 exception/file requests plus eight explicit grant requests and24 rejected
startup configurations; see server.md. Full delivery remains open.
These checks establish this development scope, not full delivery acceptance.

Ordinary ABI6 source providers now support static/shared/mixed project images,
profile catalogs, pure-helper logical frames and source-absent captured replay.
See source-exception-providers.md. Current Mac regression and installed SDK
receipts include these workflows; Linux and other platform delivery have
separate gates. Wasm rejects reachable source try/throw until its transport is
implemented. Retained origins keep their original source versions and canonical
identities; current fixture updates do not relabel older projects.

See examples/exceptions. From that project run nex check, nex test and
nex test --target web with the025 candidate. Installed024 SDKs use their own
advertised language and cannot check this025 project directly.

024-to025 migration rechecks the archived024 program under its retained parser
and original canonical revision before checking025. try/catch/throw were valid
contextual identifiers in024 and become reserved in025. Conflicts or missing new
throw effects fail before mutable destination access. Repair an exported copy
explicitly; do not rewrite the old manifest or retag old revisions. Successful
migration appends the new revision and retains every old row/schema/local ID.
Physical source/manifest changes remain a separate explicit export operation.

Typed payloads, handler filters/finally and general algebraic effects remain
unfinished requirements. Broader platforms including native Windows still need
actual acceptance; cross-builds and Wine are separate evidence.

---

# HTTP storage transaction start233

Toolchain0.135.30 starts an HTTP SQL transaction at the first storage operation.
Handlers without DB access hold no writer lease. Actual storage keeps its
method-based read/write policy,1000ms busy timeout, atomic commit/rollback and
principal isolation. The old C++ constructor remains eager. Source syntax,
public language0.24, graph history and task/provider ABIs are unchanged.
Public025 integration, complete SDK/platform acceptance and PLAN work stay open.
Sanitizers are authorized; security audit/fuzz campaigns remain deferred.

# Private modular HTTP debugging232 experiment

Toolchain0.135.29 adds matching HTTP debug hosting, actual request-ID watches
and a terminal-step marker outside scheduler/debug locks. Public language stays
0.24; the private ABI2502/catalogABI2 keep their sizes and meanings. Static,
shared and mixed HTTP programs use the same source/consumer/image context/2.
Read [the module debug guide](source-exception-module-debug.md).
Public025 migration, full SDK/platform delivery and remaining PLAN work stay open.
Sanitizers are authorized; audit/fuzz campaigns remain deferred.

# Private module debugging231 experiment

Toolchain0.135.28 adds architecture/6 debug instrumentation, records/6 and an
explicit unarchived source/consumer/image context. Static/shared/mixed application
frames use the common catalog ABI2, LLDB/DAP and checked watch/capture. Public
language stays0.24. Read [the module debug guide](source-exception-module-debug.md).
HTTP debug hosting/request selection, public build/debug CLI/SDK, broader delivery
and explicit025 migration remain pending. Sanitizers are user-authorized;
audit/fuzz campaigns remain deferred. The full goal stays open.

# Private module profiling230 experiment

Toolchain0.135.27 adds architecture/5 profile instrumentation and per-component
registries. Static/shared/mixed applications and HTTP hosts use one collector;
the catalog retains actual source/template, machine component and image owners.
Public language stays0.24. Read [the module profile guide](source-exception-module-profile.md).
Request-ID attribution, module logical debug, public build/profile CLI/SDK,
broader delivery and explicit025 migration remain pending. Sanitizers are
user-reauthorized; audit/fuzz campaigns remain deferred. The full goal stays open.

# Private modular HTTP229 experiment

Toolchain0.135.26 adds explicit architecture/4 host selection and module/4 HTTP
root descriptors. Source errors and owned cleanup cross static/shared/mixed
code images, including consumer-owned trait instances, under one ABI2502 runtime.
Public language stays0.24. Read [the modular HTTP guide](source-exception-module-http.md).
Public build/SDK, module profile/logical debug, broader platform delivery and
explicit history-preserving025 migration remain pending. Security checks are
user-deferred; the original full goal remains open.

# Private consumer-owned template instances228 experiment

Toolchain0.135.25 adds architecture/3 and module/3: checked concrete templates,
nested generic helpers and closures can be emitted by their consumer with the
actual local trait targets. Records retain source/machine ownership, template
identities, selected witnesses and derived private support interfaces. Earlier
architecture/1 and /2 keep their meanings. Public language stays0.24. Read
[the consumer instance guide](source-exception-instances.md). Automatic placement, module
HTTP/profile/logical debug, public build/SDK, full platform delivery and explicit
history-preserving025 migration remain pending. Security checks are user-deferred.

# Private mixed native task images227 experiment

Toolchain0.135.24 adds explicit architecture/2 mixed-fixed and source module/2
records with checked component/function physical image ownership. Static code is
absorbed once at its application/shared frontier; static diamonds inside one
image are deduplicated and duplicate loaded incarnations are rejected. One runtime
serves all ABI2502 code images. Public language stays0.24. Read
[the mixed-image guide](source-exception-frontiers.md). Consumer-owned trait specializations, module
HTTP/profile/logical debug, public build/SDK, full platform delivery and explicit
history-preserving025 migration remain pending. Security checks are user-deferred.

# Private source task modules226 experiment

Toolchain0.135.23 adds checked private code modules with static/fixed-shared
linkage, one runtime, uniform private ABI2502 and source-derived records.
Callbacks, owned file/foreign values, scope/channel/future interfaces and source
errors cross the checked module boundary. Public language stays0.24. Read
[the private module guide](source-exception-modules.md). Public build/SDK,
mixed frontiers, HTTP/profile/logical debug and explicit history-preserving025
migration remain pending. Security-specific checks remain user-deferred.

# Private source exception HTTP225 experiment

Toolchain0.135.22 adds a dedicated private Request-to-Response native emitter
and joined HTTP host source-error channel. Caught errors return ordinary
responses; uncaught source errors produce HTTP500/E_SOURCE_EXCEPTION and retain
original source diagnostics. Public language remains0.24. Read
[the private HTTP guide](source-exception-http.md). Source binary providers,
HTTP profile/logical debugging, asynchronous DB, complete SDK/platform delivery
and explicit history-preserving025 migration remain pending. Security-specific
checks remain user-deferred.

# Private task host bridges224 experiment

Toolchain0.135.21 composes private source exceptions with server task/fs file
operations and task/ffi opaque resources. Host images use private ABI2502;
pure private images retain ABI2501. Public language remains0.24. Read
[the host bridge guide](source-exception-host.md) and actual discovery.
HTTP hosting, binary providers, TypeScript host effects, complete SDK/platform
acceptance and explicit history-preserving025 migration remain pending.
Security-specific checks remain user-deferred.

# Private checked watch/capture223 experiment

Toolchain0.135.20 adds explicit inspect-private-task and shared checked expression
inspection over unarchived source contexts, including snapshot-only module imports.
Private LLDB/DAP watches use actual retained values, type/effect checking, bounded
lazy reads and out-of-process evaluation. Captured frames can be inspected after
execution without source files or a graph revision. Public language stays0.24;
ordinary025 publication, IDE/crash-capsule/replay, full SDK/platform acceptance and
history-preserving migration remain pending. Read source-exception-task-watch.md
and the actual descriptor. Security-specific campaigns remain user-deferred.

# Private source LLDB/DAP222 experiment

Toolchain0.135.19 emits an explicitly unarchived private task debug context.
An opt-in nex-load-private-task-debug loader connects private ABI2501 frames to
actual all-stop LLDB and the existing logical DAP stack/locals/step bridge. Catch
shadowing, caller values, rethrow, cleanup and deadlines while stopped have
separate functional conformance. Public language stays0.24. Read
source-exception-task-lldb.md and the actual descriptor. Checked expressions,
private IDE/capture/replay integration, full SDK/platform acceptance and explicit
history-preserving025 migration remain pending. Security checks stay deferred.

# Private source task debug221 experiment

Toolchain0.135.18 adds emitSourceExceptionTasksPrototypeNativeDebug with actual
native checkpoints and lexical catch/caller visibility. A separate controller
pauses the owning continuation, reads stable live frame values and resumes it;
source/control exits retire the non-owning catalog. Public language stays0.24.
Read source-exception-task-debug.md and the actual descriptor. Public025,
process all-stop/LLDB/DAP/IDE, debug/capture/replay CLI and complete SDK/platform
acceptance plus history-preserving migration remain pending.

# Private task control/profile220 experiment

Toolchain0.135.17 fixes canonical child resource-fatal delivery to blocked owners
and implicit owned-scope source cleanup. Native source-failed tasks now profile
as Aborted. A dedicated emitSourceExceptionTasksPrototypeNativeProfile produces
registered native task instrumentation and real raw schema2 reports. Public
language stays0.24; private ABI2501 is unchanged. Read
source-exception-task-control-profile.md and the actual descriptor. Public025,
profile CLI/replay, debug, host-resource integration and full SDK/platform
acceptance/history-preserving migration remain pending.

# Private native task exception219 experiment

Toolchain0.135.16 adds emitSourceExceptionTasksPrototypeNative: explicit exception
TaskIR becomes verified MLIR/LLVM and executes on physical TaskGroup workers.
Owned handlers and source failures survive calls/yield/wait; future/drain delivery
preserves original payload/site and runtime/control priority. The descriptor uses
private ABI0x4e45585400002501; published ABI3/4/5 remain distinct. Public language
stays0.24. See docs/source-exception-native-tasks.md and actual capabilities.
This is a compiler-private experiment; resource/FFI/binary/debug/profile and full
compiler/SDK/platform acceptance plus history-preserving025 migration are pending.

# Private exception TaskIR218 experiment

Toolchain0.135.15 adds explicit handler/unwind instructions and an independent
TaskIR machine selected through evaluateSourceExceptionTaskIRPrototype. It shares
the existing serial coordinator; ordinary AST reference execution stays AST-only.
This stage does not execute compiled native task code or physical CPU workers.
Public language remains0.24. See docs/source-exception-task-ir.md and actual
source_exception_prototype capabilities. Native frames/scheduler, full platform/
SDK acceptance and explicit history-preserving025 migration remain pending.

# Private exception lifetime flow217

The shared task lifetime pass now uses binding identities and projected source
exception paths, with explicit normal/throw flow and widened loop states.
Known escapes are rejected; unknown paths retain dynamic runtime obligations.
Public024 and canonical histories remain unchanged. Native task exception
lowering, complete region inference and025 migration remain pending. Read
source-exception-lifetimes.md and the actual prototype capability descriptor.

# Private TypeScript task exception216 experiment

emitSourceExceptionTasksPrototypeTypeScript adds private resumable source-error
execution with per-root classification, future delivery and joined group close.
It agrees with the independent AST/reference task path. Native task/lifetime
integration, public025/migration and full SDK/browser acceptance remain pending.
See source-exception-tasks-prototype.md; ordinary public language remains0.24.

# Private task/reference exception215 experiment

parseSourceExceptionTasksPrototype separately enables task/throw typing and
independent AST/reference wait/drain delivery. Public024 and the sequential
private parser retain their existing contracts; native/TypeScript task and
lifetime integration remain pending. See source-exception-tasks-prototype.md.

# Private source exceptions025 experiment (public language remains024)

The private parseSourceExceptionsPrototype entry point enables try/catch,
explicit user throw effects and lexical rethrow for sequential reference work.
It selects0.25-prototype before checking; ordinary CLI/projects retain024 and
reject this private identity. A dedicated C++ native experiment adds direct and
indirect error transport and lexical owned cleanup. Public native/SDK acceptance,
A dedicated TypeScript experiment adds branded immutable user errors and private
source mapping. Public TypeScript/browser integration, task lowering and
history-preserving migration remain pending. See source-exceptions-prototype.md
and actual source_exception_prototype discovery; source_support remains false.

# Development0.135.8: ordinary HTTP response streams

`std/http_stream.nex` adds an opaque server Body, incremental byte Chunk reads,
explicit close and a chunked download helper. It uses existing language0.24
resources, callbacks and task/ffi/fs operations. Syntax, source ABI, canonical
identities, frontend and backend semantics and historical migrations stay the
same. Read [HTTP response streams](http-streams.md) and discover the actual
compiler's `http_response_streams` field. Registration, installed SDK delivery
and each platform's execution receipts have separate acceptance scopes.

# Development0.135.7: ordinary HTTP client library

`std/http_client.nex` uses existing language0.24 records, bytes, Result and
server task/ffi callbacks. No syntax, builtin, source ABI, canonical identity
or migration changes are introduced. Network execution requires explicit
operator-prepared pinned native code; pure validation is portable.
Read [the HTTP client guide](http-client.md) and the actual compiler descriptor
`http_client_provider`. Current compiler and SDK acceptance remain pending.

# Development0.135.6: ordinary DNS library

`std/dns.nex` uses existing immutable records, callbacks, Result and server
`task,ffi`; it adds no syntax, builtins, realm/effect rules or source ABI. Pure
request validation is portable; executing lookups requires a pinned native
provider and explicit operator policy. See [DNS provider](dns-provider.md).
Current matching delivery/platform acceptance remains a separate gate.

# Development0.134.0: public source language0.24 candidate

Ordinary source/project commands select TaskStreams024. Checked server task/fs
functions support opened File IO and genuine File owner captures/results across
structured tasks. Static/fixed-shared source providers use ABI5 records8/9/10;
read/write/stream requirements never grant OS authority. The same source semantics
are executed by native continuations and the independent AST interpreter.

Explicit migration verifies retained018..023 origin identity before checking024
and before opening a writable Store. Original rows/schema/IDs and physical files
remain; export creates a separate current-language project. Merely editing a
manifest does not migrate a graph. Retained023 parsing and ABI3/4 stay intact.
See [source file streams](task-file-streams.md). Current compiler, full/SAN,
installed SDK and platform acceptance remain independent pending gates. The
accepted SDK0.133.5 and primary081 have not been replaced. All original broader
language/server/accelerator/UI/mobile/Studio/converter requirements remain open.

# Development0.133.12: source alias-close and genuine mixed histories

The private024 physical IO suite covers source alias-close during read, write,
append, flush, seek and size, in addition to existing host/source controls:
62 native/independent-AST pairs on12 compiled NEX images. A closed alias loses
logical access while physical leases and quotas remain until IO retirement.
Visible completed writes are retained; cancellation/close promises no rollback.

Four real installed SDK1335 histories add12 original023 revisions combining
File/whole-file IO with C11/C++20 opaque resources and task captures. Explicit
migration retains all16 tables and original identities, rechecks external
signatures and ownership, and records any new-platform binary-pin projection
only in the new024 candidate. Original pinned runtime execution is reported
only when actually available. See docs/task-stream-ffi-histories.md.

This adds conformance and test-host integration, with no compiler/runtime source
semantics, syntax, canonical identities, public023 or historical rule changes.
Matching full/SAN/SDK/platform acceptance and public024 delivery remain open,
as do all original language/server/accelerator/UI/mobile/Studio requirements.

# Development0.133.11: private physical IO completion

A trusted POSIX host can observe actual file calls without receiving source
values or descriptors, and bind a lexical FileScope to its exact revocable
resource subdomain. Exceptional physical exits retain one-shot completion and
original cancellation/revocation/host diagnostics before Value admission.
A debugger can read the actual verified publisher-local checkpoint record when
an instrumented prologue hides its pointer parameter; all catalog/publication
checks remain. No grammar, effects, grants, canonical identities, public023 or
historical source interpretation changes. See task-stream-inflight.md.

# Development0.133.10: private024 pure-helper conformance

The native task file requirement classifier accepts concrete reachable pure
helpers, consistently with actual continuation lowering. This corrects native
builds of already checked pure generic callables and File identity helpers.
No syntax, effects, grants, canonical identities or public023 rules change.
See task-stream-histories.md for genuine023 history conformance and its scope.

# Development0.133.9: explicit private024 project delivery

Compiler-owned source selection now rechecks024 physical projects and their
matching locks without deriving the parser from untrusted metadata or opening
a graph Store. Ordinary CLI/default projects retain023. ABI5 project linkage
records distinguish read/write/stream requirements, task-code/5 imports and
strict retained ABI3/4. Captures recheck the selected language, source ownership
and exact plan before replay; native packages record the checked program language.
Native profile readers and source-backed LLDB/DAP accept ABI5. Private024 File
bindings expose only diagnostic identities in pure watches; filesystem/effectful
operations remain rejected. No File IO authority is reconstructed by a watch.
Read docs/task-stream-project.md. Public024 publication, explicit migration,
remaining in-flight source IO/history cases and matching full/SAN/SDK/platform
acceptance remain pending. The entire original project scope remains open.

# Development0.133.8: private024 mixed file/resource conformance

Actual NEX programs retain a genuine File and a genuine C11/C++20 opaque
resource in the same immutable graph. Twenty-four native/independent-AST pairs
exercise captures, futures, sibling channels, returned closures, nested aliases,
scoped cleanup/quota reuse, function-local errors, readonly grants, checked
abort and source task_cancel. Nine invalid FFI/wire entry checks retain the
existing rejection; public023 and client-only pruning stay unchanged. This adds
conformance, not C FFI File transport, arbitrary in-flight syscall cancellation,
public024 publication or platform acceptance. Read docs/task-stream-mixed.md.
Compiler/runtime/spec/grammar/language-pack semantics match175; the toolchain
identity and test registry change. Matching full/SAN/SDK acceptance keeps its
separate evidence and all original project requirements remain open.

# Development0.133.7: private024 native source file providers

Private024 source providers have explicit ABI5 records8/9/10 and root stage3.
Checked File parameters/results, including immutable aggregates, cross static
and fixed shared source boundaries under the same application runtime and
resource-region guards. File-bearing retained task values request the stream
image flag independently of read/write operations. Image/component/root flags
never grant OS authority. ABI3/4, public023 and provider masks31/799 stay strict;
ABI5 provider mask3871 excludes standalone source FFI bits. Profile/debug source
metadata accepts explicit024; full CLI project-plan/capture/replay/package/
debug/profile and public024 delivery remain separate pending work. Compiler,
source/provider conformance, full/SAN/SDK/platform acceptance must be verified.
All original language/server/accelerator/UI/mobile/Studio/converter/measurement
requirements remain in scope. There is no grammar or public language change.

# Development0.133.5: owning cleanup for private024 source files

Every private024 source open reserves an owning executor cleanup slot before
physical file construction. Native host contexts and the independent AST
scheduler provide this executor explicitly. Logical close revokes all aliases
immediately; the last physical lease queues the complete payload/destructor,
file quota and settlement fence on that executor. No cleanup admission or
allocation is needed at final release, including after the executor closes.
Cancellation, discarded opens, factory failure and resource-region retirement
retain physical settlement. A missing source cleanup executor is rejected;
legacy host opens without an executor preserve their existing inline contract.
This does not promise bounded OS close latency, rollback or directory durability.
Public023/default, retained ABI3/4 and syntax/history remain unchanged. Controlled
source cancellation, ABI5 provider/capture/package/debug/profile, public024 and
matching full/SAN/SDK/platform acceptance remain pending. All original language,
server, GPU/NPU, UI/mobile, Studio, converter and measurement work remains open.

# Development0.133.4: precise private024 task file requirements

ABI5 image read/write flags and standalone build metadata now classify checked
reachable task instructions consistently. Read/open-read and write/open-write/
append/flush have separate flags; seek/size/close/is_open retain the existing
opened owner without requesting another root read/write grant. All stream
operations set the stream image flag and enable the owning task IO machinery.
Unreachable helpers cannot add grants. Declared effects and image metadata do
not grant OS authority or upgrade a read-only file. Public023/default, retained
ABI3/4 descriptors and their build metadata, grammar and history stay unchanged.
Public024, physical-close offload, provider/capture/package/debug/profile and
matching full/SAN/SDK/platform acceptance remain pending. All original language,
server, accelerator, UI/mobile, Studio and converter requirements remain open.

# Private024 source stream integration (development0.133.3)

Explicit C++ source APIs may select TaskStreams024. Ordinary CLI/default projects
remain language023; changing nex.json does not enable024. The existing stream
syntax suspends inside server task/fs functions. Files created by such opens
have real logical owners, physical request/root grants and retirement fences.
Native ABI5 appends stream requests and requires explicit stream bits. Retained
ABI3/4 masks and public023 stream rejection are unchanged. File-bearing source
captures/results/futures/channels/closures use atomic mixed external/file owner
transfer; no file authority crosses browser/wire/FFI/unstructured parallel paths.
Source/physical conformance, explicit transactional migration, public publication,
provider/capture/package/debug/profile contracts and current SDK/platform delivery
remain pending. This is implemented private code, not a completed language release.

# Current language0.23

Language023 retains the existing grammar and adds checked whole-file text/byte
write suspension in server functions declaring task and fs. Ordinary CLI source,
independent reference execution, native builds and checked static/shared images
use this rule. Runtime authority remains an explicit revocable operator grant;
read-only grants cannot be upgraded. Strict UTF-8, exact immutable snapshots,
left-to-right evaluation, lazy branches, local result propagation and physical
drain before completion remain mandatory. A cancellation after a complete rename
can suppress delivery without rolling the file back.

The program language participates in semantic revision identity. Explicit
migration verifies original022 source with its retained parser and appends a
separately checked023 revision. Original history, all16 tables/schema and IDs
remain. Ordinary live synchronization refuses a HEAD language mismatch before
opening a writable Store and checks again in the transaction. Old022 task writes
retain their E_TASK_UNIMPLEMENTED interpretation under explicit retained APIs.

Native execution uses ABI4; source FFI remains distinct from resource-free
binary provider exports. Provider records5/6/7 and versioned ABI4 plan/capture
metadata explicitly record image/component/root write requirements. Old ABI3
records and masks are not widened. Browser/Wasm source cannot acquire filesystem
authority, and emitted clients contain only reachable client/shared code.

Source implementation is enabled in this candidate; complete compiler/SDK/
platform acceptance is a separate unfinished delivery gate. The current023
rules above extend the retained022 core below; older development notes preserve
their original scopes. Read task-file-writes-prototype.md and task-write-providers.md.

Toolchain0.132.1 fixes reference retirement publication without changing syntax,
canonical identities or the language022 contract: physical fence readiness must
remain scheduler progress until task/scope completion is published.

Toolchain0.132 adds ordinary `std/device.nex` source contracts without syntax,
canonical identity or language-version changes. Session/Buffer remain server
resources; task/ffi operations retain physical dependencies and completion rules.
The experimental OpenCL provider and delivery limits are described in device.md.

# Retained language0.22 core

The development host C API can construct dependent opaque resources through a
pinned server/ffi extern. Existing task transfers promote their hidden parent
closure; native and independent AST execution share this C boundary. This adds
no NEX constructor, syntax, canonical identity or migration. Query
`resource_regions.dependency_graph`; read resource-regions.md for bounds and
physical parent retention. Actual GPU/NPU resource bindings remain pending.

Language022 retains the syntax below and enables server task/ffi callbacks,
direct checked extern suspension and genuine external-resource transport through
task captures/results/futures/channels/closures. Calls preserve original physical
grants; complete value graphs are checked before atomic ancestor owner transfer.
Ended logical regions cannot be revived. Cleanup and admitted C operations must
physically settle before completion. File authority, unstructured parallel and
wire/browser resource transport remain rejected; fixed binary providers retain
their separate resource-free ABI. See [the task/FFI contract](task-foreign-prototype.md).

Explicit migration rechecks retained018/019/020/021 source before producing022
revisions. Original rows/schema/IDs remain; changing nex.json alone is not a
migration. SDK/platform acceptance is separate from enabled compiler support.
Earlier development notes below retain their historical scopes; this section
and the current semantic sections govern022.

Private150 resolves logical resource authority only for actual resource-bearing
task snapshots or FFI signatures. Pure snapshots do not consult that authority;
physical FFI/request grants and ordinary execution cancellation still apply.
The owner provider runs synchronously once during owned-call preparation and
is never retained by an IO operation. Ended owners remain rejected. No syntax,
public021 identity or migration changes; read task-foreign-prototype.md.

Private149 explicit022 C++ APIs add genuine resource capture/result/future/channel
and closure transfer with atomic ancestor ownership and original physical grants.
Files, unstructured parallel_map and browser/wire authority remain rejected;
public021 source semantics and public022 migration stay separate. Runtime guards
remain mandatory for dynamic resource ownership; task capability escapes retain
their own static/runtime checks. Read task-foreign-prototype.md.

Private148 explicit022 C++ APIs add task-local opaque resource calls through a
separate typed owned-completion channel. Ordinary task helper frames can retain
these owners; source callback captures/results and channel/future transfer remain
rejected. Public CLI language021, its canonical identities and migration rules
stay unchanged. Read task-foreign-prototype.md for authority, cleanup and bounds.

Toolchain0.128 retires native scheduler-owned Value roots outside its mutex and fences task/scope publication and buffer-slot reuse. This changes no source syntax, language0.21, canonical identity or migration; source resource transport stays unavailable. See task-value-retirement.md.

Toolchain0.127 adds private independent AST reference resource-region scheduling and physical cleanup fences. Source task/FFI transport stays unavailable; language0.21, canonical identities and migration remain unchanged. See resource-regions.md.

Toolchain0.126 adds private host logical resource regions in native TaskGroup; source task/FFI transport and reference integration remain unavailable. Language0.21/canonical identities/migration stay unchanged. See resource-regions.md.

Toolchain0.125 adds a private trusted host cleanup executor, without changing source syntax, canonical identity, language0.21 or migration. Source task/FFI/device bridges remain unavailable; see resource-executor.md.

Language0.21 adds `[pub] server resource Name<T...>;` and server/ffi
resource_close/resource_is_open operations on genuine opaque owners. Explicit
018/019/020 parsers and history-preserving migration remain available; never
relabel old metadata. Read [source resources](source-resources.md) for graph/editor
context, grants, cleanup, migration and remaining task/device/debug delivery gates.
This0.123 development source is separate from the approved primary0.81 checkout.

Toolchain0.122 adds the ordinary-source `std/model.nex` contract and provider preparation tooling; no syntax, canonical identity, language0.20 or migration change. See models.md.

Toolchain0.121 adds the ordinary-source checked `std/compute.nex` library: immutable
row-major tensors, typed request/response/device contracts, exact integer CPU
operations and server/ffi provider contexts with explicit fallback. No syntax,
reserved name, effect/realm rule, canonical identity format or language0.20
migration changes. See [the compute contract](compute.md); actual device providers
and acceptance have their own scopes.

Toolchain0.120 lets the browser worker adapter host an existing client/shared
`worker_compute(Input)->Output !{task}` in its own cooperative scheduler.
Only wire input/output crosses the dedicated Worker boundary; task authority
stays internal. Main-thread UI entries remain synchronous and pure, and task
filesystem/FFI/network operations remain unavailable there. This changes no
syntax, checked effects/realms, language0.20 identity or migration.
See [the worker contract](browser-workers.md).

# NEX language specification 0.21

Toolchain0.119 provides development source-backed native task-provider logical debugging
with separate component catalogs/source unions and debug protocols. Discover
`task_provider_debugging` and read [its bounded tooling scope](task-provider-debugging.md).
This changes no source syntax, effect/realm rule, canonical field, operation ordinal,
language identity or explicit migration. Actual generated-image LLDB/NEX-DAP preflights precede enablement; complete
regression/SDK/platform receipts remain specific to each compiler/resource delivery.

Toolchain0.118 enables development checked task-provider profiling with separate
metadata/report schemas. Discover `task_provider_profiling` and read
[its tooling contract](task-provider-profiling.md). This changes no source syntax,
effect/realm rules, canonical field, language identity or migration.

Toolchain0.117 enables candidate fixed startup-linked shared task images. Discover
`task_shared_providers` and read [the shared contract](task-shared-providers.md)
for actual enablement and per-application ownership. This external build slice
adds no syntax, effect, canonical field, language version or migration.

Toolchain0.116 enables candidate concrete static task provider linkage with checked
source and code-only archives; discover `task_providers` and read
[the provider contract](task-providers.md). This is external build metadata,
with no source syntax, effects, canonical format or migration change. Current
enablement and acceptance are reported separately from source semantics.

Toolchain0.115 is integrating external logical task debug metadata and controls.
Discover `task_debugging` for current enablement and read
[the task debugger contract](task-debugging.md). This tooling adds no source
syntax, effect, realm, operation ordinal or canonical field; language0.20 and
explicit history-preserving migration stay unchanged.

Language0.20 adds asynchronous whole-file reads in actual server functions
that declare task and fs. The existing read operations keep their types; there
is no new syntax or reserved name. Native macOS/Linux applications, source-only
projects and the independent reference scheduler implement this subset. See
[task file reads](task-file-reads.md). Complete current regression, SDK and
platform acceptance are pending for this development candidate.

Language0.19 introduced structured scopes, futures, channels and task effects.
Explicit018/019 rechecks retain their original rules and identities. The020
checker creates distinct revisions and requires history-preserving migration;
never relabel an old project. Native continuations and independent AST/TypeScript
schedulers remain separate implementations. Complete static lifetime inference,
write/stream/db/ffi/network task bridges, non-native task debugging/profiling, dynamic provider lifetime,
Broader UI integration and other task platforms remain pending.

Toolchain0.114 adds native020 task profiling without changing source semantics
or canonical identities. Query `task_profiling` and read the [profile guide](profiling.md)
for CLI/project scope, separate CPU/elapsed/lifetime measurements and completeness.

This document describes the implemented language, independently of any LLM provider. Planned features live in `PLAN.md`. The compiler's `nex describe --json` reports its language version and capabilities.

Toolchain 0.64 adds an explicit [Windows GNU/UCRT core target](windows.md); the0.65
candidate adds strict Unicode environment access and explicit target SQLite storage.
Its target/runtime restrictions add no syntax, canonical changes or language
migration. Windows execution and development-host support have separate status.

Toolchain 0.61 adds explicit [iOS static archive targets](ios.md) on macOS.
This changes no source syntax, canonical format or language version. Device and
simulator SDK/ABI validation does not provide an application host or local run.

The experimental [scalar Wasm compute target](wasm.md) in toolchain 0.60 adds no
source syntax or language-version change. Its reachable-code restrictions and
resource/JavaScript ABI limits are narrower than the full language.

Native core capsules are external development artifacts described by
`docs/core-debugging.md`; they introduce no source type, effect, syntax or
canonical-format change. Their tooling version does not migrate language 0.16.

Physical projects can declare `nex.project/1` and language `0.22` in `nex.json`. Toolchain 0.51 rejects explicit noncurrent root or reachable configured-library language declarations before source loading. Root preflight occurs before store initialization; archived operations/migration retain their own version checks independently of physical metadata. See [compatibility](compatibility.md) for legacy omitted metadata and the explicit migration/export workflow. The project metadata guards themselves do not change source syntax; the 0.16 source/canonical extension is described below.

Language 0.16 adds [traits, associated value types and constructor parameters](traits.md).
Its canonical formats are function/13, structure/5, enum/4 and program/14.
Explicit migration from0.15 preserves historical revisions/IDs; keep SDK0.54 for
old artifacts. Current source integration and remaining validation scopes are
advertised by `trait_integration_pending`; the earlier language 0.15 constructor
core is separate evidence. The declarations use contextual names and do not
reserve ordinary old `trait`, `impl`, `type`, `for` or `Self` identifiers.

Toolchain 0.62 adds an external [mobile project generator](mobile.md) using the
existing pure web application contract. Its platform hosting and relative URL
policy change no source syntax, type/effect rules or canonical format.

Toolchain 0.63 adds external HTTPS host configuration and exact server CORS
origins ([mobile API](mobile-api.md)); this changes no language syntax, effects,
realms, canonical format or migration requirements.

Toolchain0.68 adds opt-in readonly source-reference projection and editor lookup
([LSP](lsp.md)). This adds no source syntax, semantics, canonical change or
language-version migration; default analysis/1 consumers remain supported.

Toolchain0.69 extends the same opt-in editor projection to type/trait/member/import
names. This is source metadata only; language0.16 and canonical formats are unchanged.

Toolchain0.70 adds opt-in identifier descriptions (`analyze --details`, analysis/3)
for editing. These are captured source metadata, not a new type, source syntax,
semantic identity or language-version migration. Legacy analysis/1 and analysis/2
remain available independently; see [LSP](lsp.md).

The0.72 candidate adds checked project archive consumption and multiple concrete
library exports as external build metadata ([project builds](project-build.md)).
Its native ABI is compiler-private; language0.16, ownership, effects, realms and
canonical formats are unchanged. Source remains required for checking.

Toolchain0.75 extends external native frame/core metadata to captured shared images.
It changes no source syntax, canonical identity, language0.16 semantics or graph
history; [core debugging](core-debugging.md) states the matching-SDK/host limits.

Toolchain0.76 packages checked project architectures as external artifacts.
This changes no language0.16 syntax, semantics or canonical identity.

