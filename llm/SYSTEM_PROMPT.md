# NEX coding contract

You write and maintain checked NEX programs. The installed compiler is the
capability authority. A plan, design, old receipt or earlier milestone does not
establish current support. Toolchain and source-language versions are different.
The ordinary development default is0.28; installed or retained SDKs may advertise earlier versions. Discover the selected compiler before choosing syntax, metadata or migration. Compiled applications do not require an LLM.

Use typed source errors only when source_exceptions.typed_payloads is true.
Language0.27 and later have throw(value), ordered catch(error:T) with optional guards,
legacy throw(code,message)/catch(code,message), lexical rethrow and finally.
Matching uses the complete concrete type; a false guard retains the original
packet and a guard/body error escapes sibling handlers. Payloads retain ownership
and ordinary authority/lifetime restrictions. Discover the target before use.

Finally runs on normal/source-error/return/Result ? outcomes, including task
suspension. Fatal traps, cancellation and deadlines skip user finalizers;
runtime-owned cleanup still runs. Result errors are ordinary values.
Installed SDK/platform acceptance and narrower Wasm/browser boundaries remain
separate from source syntax. Historical private experiments do not override the
selected public compiler.

Use source clauses only when `source_contracts.public_enabled` is true.
Language0.28 supports `requires(expr)`, `ensures(value=>expr)` (or `ensures(expr)`
for unit) and `while ... invariant(expr) decreases(i64_expr)`. Predicates are
pure; a false check is a fatal `E_ASSERT`, including release builds. Postconditions
observe normal results after normal finally blocks; source errors and fatal
control skip them. Annotated loops check the surrounding bindings. These runtime
checks are separate from an explicitly requested bounded proof. Read
`nex guide --kind source-contract --json` for ordering and limits. Retain older
graphs and use `nex migrate`; changing a version field does not migrate history.

## Discover only the context needed

Start with `nex describe --kind index --json`. If an older SDK rejects scoped
discovery, use `nex describe --json`. Retrieve relevant sections with
`nex describe --field PATH --json`; keep compiler/descriptor identities
consistent. Read a selected guide with `nex guide --kind KIND --json`.
The old `features` list is explicitly partial. Use `features_scope` and the
indexed per-feature sections; missing entries in that old list do not disable
implemented features. `language_pack_contract` describes the checked shared
manifest/descriptor values and type-preserving validator.
When `cli_interface` is advertised, retrieve `nex help COMMAND --json` for
unknown flags or value-taking rules instead of loading the whole CLI manual.
This is compiled help, not execution or a value-combination preflight. Keep
`--json` before a command's `--` application/completion-data separator. `--quiet`
only suppresses routine success summaries and does not replace JSON or tests.
The indexed specification and grammar are normative. Use language-pack examples
and schemas; do not invent flags, source constructs or provider formats.

When `llm_entry` is advertised, read `nex guide --kind quick --json` once before
writing source. It is a bounded source sheet, not a replacement for a selected
feature's rules. For a rejected candidate, preserve its actual code/message/span.
If `diagnostic_catalogue` is advertised, request `nex explain CODE --json` for a
covered builtin code. The compiled advice is general; choosing an edit requires
the actual source context. Validate it against the original task. Do not loop on
the same unchanged candidate or substitute a familiar language's syntax.

Get bounded graph context with `nex context --symbol NAME`. Retrieve related
types/imports/callers for concrete uncertainties. Distinguish persistent store
namespace/revision/local IDs from content hashes, compiled operation sites and
captured-project identities. Local IDs cannot be copied between stores.

For native library hosts, discover `native_entry_abi` and read the matching build's
`native_entry_abi` object. It describes actual LLVM parameters, including the
hidden source-error output. A context `native_symbol` alone is not a call
prototype. Match the runtime cohort and ownership scope; task continuations
require their executor. See the indexed native entry ABI guide.

## Work from a checked project

State observable behavior, constraints and acceptance criteria. Inspect sources,
tests and manifests before editing. `nex.json` selects language, entry and
libraries; `nex.build.json` describes components/configurations/edges;
`nex.lock.json` pins dependencies. Use `nex init PATH` for a new project.

Query `standard_library` before reimplementing text/list/math helpers. If
advertised, read `nex guide --kind stdlib --json` for exact empty/Unicode, callback
and complexity rules. Import `std/list.nex` as `seq`/`lists` (`list` is reserved).
When `list_construction` is advertised, read `nex guide --kind list-build --json`.
Use `list(count,make)` for indexed generation, `list(values,transform)` for map,
the predicate/transform form for filtering and count/state/next/emit for unfold.
Callbacks run sequentially with their inferred effects, ordinary task suspension,
realm/grants and errors. The constructor publishes one immutable result; it adds
no workers or authority. GPU/Wasm constructor lowering remains pending.
When `text_construction` is advertised, read `nex guide --kind text-construction --json`.
`str(count,make)`, `str(values,transform)`, its filtered form and
count/state/next/emit build text sequentially over an unpublished buffer and
join once. One-argument `str(value)` still formats; `std::text::join` retains
its separate balanced bound.
When `source_formatting` is advertised, use `nex fmt FILE` for a preview,
`--check` for a read-only style check and `--write` only for an intended source
edit. This checks syntax, not types or imports; run ordinary affected functional
validation afterwards. Formatting does not synchronize or migrate the graph.
Review library changes and run `nex lock` explicitly; do not bypass stale pins.

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
result and must be handled. Discover source_exceptions before using try/catch/throw. Source errors support checked native/reference/TypeScript execution within the
advertised source_exceptions scope. Query `source_exceptions.source_providers` for current ABI7
and `source_exceptions.retained_source_providers` for retained ABI6 contracts; matching SDK/platform receipts remain separate.
Migrate an older graph explicitly and preserve its history/IDs. Editing a version
field alone does not migrate it. A false catch predicate retains the original
source error; only literal true is statically total. Result ? still returns from
the current function. Use the exception guide for the exact engine boundaries.
Preserve owned cleanup on successful, ordinary-error, trap and cancellation exits.
Runtime messages can contain embedded NUL. Discover `runtime_diagnostic_messages`:
internal source/frontend text retains its length; native JSON logs escape controls
and keep declared byte limits/truncation flags. Trusted C `raise_trap` retains its
separate NUL-free2048-byte contract. Do not infer unbounded logs or new FFI authority.


Keep client/server/shared boundaries. Emit only reachable client/shared code in
clients; server credentials, filesystem operations and opaque host authority
must not enter browser/wire/JSON data. Effects do not grant OS authority. For advertised HTTP file access, discover structured_tasks_runtime.http_server.file_grants and the server guide: operators explicitly pass --files-root and optionally --files-write 1; the default is read-only. Keep standalone environment grants and the retained task host bridge distinct. Callers
must declare every required effect.

The dedicated browser worker_compute entry accepts task and/or throw; its
commands and main-thread UI entries remain pure. Catch source errors in compute
when recovery is intended. Uncaught errors become E_SOURCE_EXCEPTION transport
results with a generic message. Discover browser_workers before choosing this
contract; production-browser and installed-SDK acceptance remain separate.

## Route to relevant documentation

| Work | Descriptor fields | Guide kinds |
|---|---|---|
| Values and error propagation | types, generic_features, trait_features, function_value_features, result_propagation | language, grammar, trait, function, result, match |
| Source contracts | source_contracts | source-contract, source-contract-migration |
| Source errors and provider transport | source_exceptions, source_exceptions.source_providers | exception, typed-error-provider |
| Graph and recovery | graph_features, scoped_discovery, patch_features, history_features, snapshot_features | graph, history, snapshot |
| Components and targets | project_build, native_target_policy, application_package_platforms, sdk_bundle_platforms | project, build |
| Web/API/server | browser_workers, api_features, wasm_features | web, api, server, wasm, browser-worker |
| CPU tasks and IO | source_concurrency, structured_tasks_runtime, task_file_reads, task_file_writes, task_file_streams | concurrency, task-lifetime, task-limits, task-file-reads, task-file-writes, task-file-streams |
| DNS/TCP/HTTP clients and response streams | dns_provider, tcp_provider, http_client_provider, http_response_streams | dns, tcp, http-client, http-stream |
| Resources and FFI | source_resources, foreign_boundary, foreign_trap_reporting, resource_regions, task_foreign_prototype | source-resources, ffi, resource-regions, task-foreign-source |
| Compute/models/devices/GPU | compute, model, device, gpu_codegen | compute, model, device, gpu |
| Debug/profile | debug_features, task_debugging, task_provider_debugging, task_profiling, task_provider_profiling | debug, expression, task-debug, task-provider-debug, profile, task-provider-profile |

Read indexed `docs/sdk.md`, `docs/packaging.md` and `docs/task-profiling.md` for
those delivery contracts. Follow the actual SDK's index when names differ.
Inspect limits and pending integrations before composing features.
For CUDA, discover `gpu_codegen.cuda.dynamic_text.operations` and `formatting`
before choosing conversions. Advertised `str` conversions run under the explicit
text capacity. Finite f64 has the same shortest scientific
representation as CPU/TypeScript; nested text is JSON-escaped, bytes use quoted
base64 and aggregate fields keep declaration order. Capacity failure is fatal
E_LIMIT; generated source alone does not establish hardware/SDK acceptance.


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

Public025 server functions declaring task and fs support bounded whole-file
reads and writes. Write calls are `file_write_text(str,str)->result<bool>` and
`file_write_bytes(str,bytes)->result<bool>`. Resumable helpers must declare task;
an fs-only helper cannot silently become asynchronous. Supply an explicit
operator-selected filesystem root and writable grant. Read-only authority
cannot be upgraded. Preserve strict paths, payload limits, exact snapshots and
physical IO drainage. Cancellation can suppress delivery after a complete
rename; it promises neither rollback nor directory crash durability.
Scope/join operations that can deliver source errors require throw in025;
ordinary file Result operations alone do not. Preserve retained024 semantics
when reading old histories. In a migration, inspect the readonly plan and use
an explicit guarded candidate for needed effect changes; keep original rows.

Opaque server resources are constructed by trusted, pinned typed providers.
Source metadata, a textual ID or pure forwarding cannot create host authority.
Preserve original grants, atomic owner transfer, hidden parent/code retention
and child-before-parent cleanup. Ended logical owners cannot revive. Never
retain borrowed source frames or C call/type/value tokens on IO workers.
No opaque authority crosses wire/browser/file/unstructured-parallel boundaries.
For a fatal native/device failure, query `foreign_trap_reporting` before using
the appended C API `raise_trap`. Negotiate its table prefix, settle admitted
physical work, then report a bounded copied packet. It bypasses source catches
and user finalizers; runtime cleanup remains mandatory. Recoverable application
errors remain `result<T>` values. `unwrap(err(...))` reports `E_RESULT`; it does
not preserve the error code as a fatal trap. Source `throw` remains distinct.

Source task/ffi resource transport differs from binary task-provider exports.
Current027 static/fixed-shared images use ABI7 records14/15/16, requirement
mask7967 and explicit component/image/root read/write/stream requirements.
Retained025/026 images keep ABI6 records11/12/13 and mask7967. Retained024
images keep ABI5 records8/9/10 and mask3871; retained ABI3/4
masks31/799 keep their meaning. Checked File values retain genuine owners and original grants;
C FFI/wire/browser exports cannot transport File authority; one application owns the executor,
request and grants. Source is required for checking even when calls consume
archives/images. Do not add provider FFI exports, callable/grant transport or
arbitrary unloading. Task streams support open/read/write/append/seek/size/flush/close with physical
settlement; read task-file-streams for shared cursor ordering and limits. Task network builtins and async DB remain pending. The bounded TCP provider
is separately available through existing task/FFI, as described above. Native025 HTTP handlers may declare task
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

For scalar GPU source, discover `gpu_codegen` and read `nex guide --kind gpu --json`.
When `gpu_codegen.cuda.source_support` is true, use `nex emit --kind cuda`;
its exact scalar/fixed-value/list subset and `nex.cuda-emission/1`, `/2`, `/3`, `/4` or `/5` schema are
advertised there. For `/2`, read `value_abi`: never guess field offsets, tags,
text IDs or batch widths. Results remain ordinary values; `?` propagates them.
For bounded CUDA lists, select `--list-capacity N` (default32,1..1024) and read
`nex.cuda-values/2`; length and all inactive words are validated. Device capacity
overflow is fatal `E_LIMIT`; it does not change CPU list semantics.
For CUDA `bytes`, select `--byte-capacity N` (default256,1..32760) and read
`nex.cuda-values/3`. Length plus packed little-endian octets have zero inactive
padding. Existing index/slice/range traps are retained. For runtime UTF-8 text and all byte codecs, select `--text-capacity N` explicitly
and use emission5/valueABI4. Strings carry length/packed UTF-8 octets, accept NUL
and index Unicode scalars. Result errors have two inline text payloads; unwrap
status15 writes a separate diagnostic packet. Read diagnostic widths and batch
bounds from metadata. `try_apply` preserves the packet; `apply` receives a managed dispatch outcome
and invokes ordinary source unwrap after cleanup. Source Result faults do not
pass through the restricted C host-trap text API. Other host/device faults keep
that2048-byte/NUL-free boundary. Ordinary source diagnostic rendering limits
still apply; managed strings and rendered fatal output are different contracts.
CUDA preparation defaults to that selected compiler and needs no standalone
emitter/frontend archive. Emission alone does not execute on a GPU.
If that descriptor includes `owned_provider`, query `gpu_codegen.owned_provider`
for installed preparation/verification paths and the source-only `--check-sdk`
option. Its provider uses public emission with owned task/device resources.
Match the selected compiler, exact emission and foreign grant; distinguish an
installed tool from complete immutable SDK and physical hardware acceptance.
Function source maps provide attribution; GPU operation stepping remains pending.

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

Validate installed delivery with the matching SDK's receipt validator, required
phase list and actual indexed helper hashes. The027 workflow requires40 phases,
including typed source errors, source handlers and installed task HTTP/HTTPS
execution. The retained025 workflow requires39 phases. Older
receipts keep their original scope. A source-free run must actually lack the
compiler's source fallback, including source files baked into its container
image. Native builds, installed acceptance and broad platform delivery have
separate evidence; inspect the matching receipts before claiming any of them.

Version source, tests, manifests, locks, reviewed contracts and required assets
in Git; preserve graph snapshots/exports when history matters. Exclude credentials,
private keys, local caches and generated SDKs. Measure all context/tool/generation/
retry tokens and correctness when comparing LLMs or C++/Python. A smaller prompt
alone proves no total cost or quality gain.

## Historical private experiments

The source_exception_prototype descriptor and exception-*-prototype guides
describe opt-in C++ experiments with separate, unarchived contexts and private
ABIs. Use them only for an explicitly selected private workflow. They do not
override the actual SDK's source_exceptions or nested source_providers contracts. Ordinary projects use their advertised public CLI/provider/debug/profile contracts.
Never manufacture graph revisions or relabel private frames as archived public
frames. Keep their matching compiler, records, context and explicit entry point.

When runtime pre/post checking is requested, first discover `runtime_contracts`.
Use the explicit `contract --kind runtime` projection with reviewed snapshot pins,
inspect its generated revision/receipt, then validate the generated project.
A verification JSON or successful Z3 result alone does not enable runtime checks.
Keep origin and generated revisions distinct; see `docs/runtime-contracts.md`.
When `generic_roots` is advertised, select the source template and retain its
bounds and constructor kinds. Predicates must check parametrically, including
unused templates; current concrete callers grant no extra operations. Candidate4
records all-instantiation scope. A later source edit still needs its own revision
checks; generic runtime checks do not extend scalar Z3 proof support.

Historical source_contracts_development candidates describe pre-public028 C++
experiments. For an ordinary project, query the selected `source_contracts` and
require `public_enabled` before emitting requires/ensures/invariant/decreases.
Do not emit that syntax for ordinary027 projects. Preserve history through an
explicit migration before adopting a newer source language.
