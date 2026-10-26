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
result and must be handled. General source `try`/`catch`/`throw` is unavailable.
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
| Resources and FFI | source_resources, foreign_boundary, resource_regions, task_foreign_prototype | source-resources, ffi, resource-regions, task-foreign-source |
| Compute/models/devices | compute, model, device | compute, model, device |
| Debug/profile | debug_features, task_debugging, task_provider_debugging, task_profiling, task_provider_profiling | debug, expression, task-debug, task-provider-debug, profile, task-provider-profile |

Read indexed `docs/sdk.md`, `docs/packaging.md` and `docs/task-profiling.md` for
those delivery contracts. Follow the actual SDK's index when names differ.
Inspect limits and pending integrations before composing features.

## Tasks, resources and IO

The private `task_network_transport` descriptor advertises a trusted C++ TCP
kernel only. It does not enable source network calls or async/await.
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
settlement; read task-file-streams for shared cursor ordering and limits. Task
network/DB remain pending. Native language0.24 HTTP handlers may declare task
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
