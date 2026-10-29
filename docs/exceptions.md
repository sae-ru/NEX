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
