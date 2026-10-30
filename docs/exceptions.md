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

# Candidate027 frontend/reference development0.142.0

Typed raise, ordered typed/legacy handlers and matching effect checks are
implemented behind the explicit C++ SourceLanguage::TypedErrors027 selection.
Public projects/CLI stay026. Native/TypeScript, authority payloads, task handlers
and graph migration remain pending and explicitly rejected. Read the candidate
semantics in language.md and typed-exceptions-design.md; this is not027 delivery.

# Typed-payload transport native roundtrip0.141.0

The compiler retains an internal owned value with its complete concrete type key.
Native managed packets now preserve that value on conversion to/from a native
exception, including the unhandled boundary. Checked accessors require the
expected scalar tag or object kind as well as the key. Typed source throw/catch
and027 remain disabled. This is a foundation for the
remaining language work, not completed typed exception support. See
[the transport and language design](typed-exceptions-design.md).

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

Use `nex migrate --kind plan --json` to verify the genuine origin and preflight
025 without writing graph state. The returned candidate envelope contains exact
origin revision/language/source guards and the target source bundle. A rejected
target is returned as target_valid:false with its actual diagnostic. Explicitly
repair only candidate.sources, save that envelope and review its changes. Apply
with `nex migrate --candidate FILE --expected-revision HASH --json`. Origin
verification always precedes candidate/target checking; malformed guards or a
stale destination head cannot mutate the graph. When selecting an older stored
revision, repeat the same `--revision OLD_HASH` on planning and application,
alongside `--candidate FILE`; the candidate guards must match that selected
origin. For an exported origin graph, keep the graph filename on both commands.
The destination `--expected-revision` guards its current HEAD independently.
Physical source/manifests remain unchanged; export the new revision to author a
current project. Candidate files are bounded to
64MiB and the ordinary loader enforces source/import/type/effect constraints.
This is a checked migration, not a proof of semantic equivalence of repairs.
