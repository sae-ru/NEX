# Typed source errors: current development status

Toolchain 0.151.0 selects language 0.27 in the ordinary CLI. Typed errors,
ordered handlers, filters and finally are implemented in the reference,
native and TypeScript paths, including task suspension and owned payloads.
Native public delivery uses task ABI7; the explicit development emitter
retains cohort2702. Checked TypeScript delivery uses map2, while the private
C++ emitter retains its separate development map contract.

Graph snapshots preserve mixed026/027 histories, schemas, all16 tables,
namespaces and local IDs. Recovery does not migrate a graph. Pure scalar027
Wasm supports i64/bool/unit and rejects reachable source exceptions, finally,
heap values and effects. Earlier language identities remain separate.

Read the current [language specification](language.md),
[error guide](exceptions.md), [migration contract](typed-error-migration.md),
[native providers](typed-error-providers.md) and
[browser delivery](typed-web-delivery.md). Full current regression, installed
SDK and platform acceptance remain required, alongside the remaining PLAN.

## Historical implementation stages and original design

The dated notes below describe their own development snapshots. Statements
about a default026 CLI or C++-only027 selection apply to those snapshots.

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

# Typed source errors: transport foundation and remaining language work

Toolchain0.147.0 keeps public language0.26 and `typed_payloads: false`.
Typed syntax is only available through an explicit C++ version selection;
public CLI/projects remain026. The explicit checked C++ API archives027 and
supports [guarded graph migration](typed-error-migration.md). The development field `source_exceptions.typed_payload_development` describes internal C++
transport and version-selected frontend/reference/synchronous native/TypeScript scope. This document distinguishes that implementation from the
proposed language0.27 design below.

The current explicit027 development selection also carries authority in source
errors: exceptional provenance plus mandatory runtime checks cover callable
captures, scopes/futures/channels and native/reference file/resource owners.
Native scope close prepares the selected outcome outside scheduler locks before
resource retirement. Its new private cohort is2702;2701 and public ABI6 retain
their identities. TypeScript uses compiler-emitted keyed transfer contracts,
keeps data out of public metadata and continues to reject browser file/FFI/server
authority. See the current rules in [the language specification](language.md).
Public027 projects, source library/provider protocols and full
SDK/platform delivery remain pending. The proposed public contract below is not
a claim that those remaining delivery gates have passed.

## Implemented foundation

Reference `SourceException` and native `NativeSourceException` can retain one
shared immutable `SourceErrorPayload`. Its value uses ordinary owned `Value`
semantics: copies retain the complete value, rather than a pointer into a dead
function frame. Replacing/discarding the final packet releases that ownership.
The packet retains the original code/message and source location. Fatal errors
are still a separate class; a code string does not select the control category.
A value alone grants no filesystem, module, task or device authority.

The compiler computes `nex.source-error-type/1` SHA256 identities from concrete
types, complete nominal layouts, generic/phantom arguments, constructor arities
and callable realm/effects. Unrelated declarations and physical source paths do
not participate. Module qualification is normalized between checked standalone
source and module loading. Unresolved type variables/projections are rejected;
recursive nominal context uses a visited set and bounded traversal.

The digest identifies a type contract; it is not proof that arbitrary host data
conforms to that type. A checked producer or a validating foreign boundary must
establish that separately. The packet constructor checks key format and basic
Value validity without walking/stringifying the entire aggregate on each throw.
Internal getScalar/getObject accessors validate the expected scalar tag or
top-level object kind as well as the key. Full nested conformance still belongs
to the checked producer or foreign validator.

Managed native transport keeps the legacy V1 record (two strings plus copied
site/line) unchanged. A distinct internal V2 record additionally owns the concrete
key and original Value. makeSourceErrorHandle/readSourceErrorHandle and the
actual nex_source_error_unhandled boundary roundtrip that payload without
formatting it. Scalar tags, binary64 bits and aggregate identity are retained.
Malformed records remain runtime failures; they cannot become source errors.
These records are compiler-private and do not define a wire or foreign ABI.
They grant no authority. The explicitly selected027 synchronous native emitter
uses V2 records for typed raises; ordinary026 raises retain V1 records.

The published88-byte ABI6 task descriptor, C foreign-module ABI and ordinary026
source semantics remain unchanged. The internal C++ exception layout is covered
by the existing runtime-cohort hash, which includes `nex_source_error.h`; it is
not a binary-compatible host exception interface across different runtime builds.
No typed source delivery or mixed old/new runtime claim follows from this work.
Retrieve the bounded contract with `nex guide --kind typed-exception --json`.

Tests exercise nested and phantom layouts, higher-kinded arguments, exact type
mismatch, failed construction cleanup, reference/native copies, exception_ptr
handoff across a real thread, and repeated observation through the actual task
scheduler. The native-packet probe also crosses real lexical owner/request and
thread boundaries, checks legacy code/message projection without payload
formatting, rejects malformed records, and injects handle-allocation failure.
They require final destruction and zero retained managed objects/handles.

## Candidate027 source contract: public delivery not enabled

A typed raise should evaluate its one operand exactly once:

```nex
throw(LoadError::Missing(path));
```

A typed catch should bind the original value with its concrete type:

```nex
try { perform_load(); }
catch(error:LoadError) if recoverable(error) { handle(error); }
catch(code,message) { handle_other(code,message); }
finally { release_local_state(); }
```

Keep the026 two-string raise, two-binding catch, lexical bare rethrow, filtered
handlers and finally. A typed clause matches its complete concrete type key;
an unmatched/declined clause proceeds to the next clause with the original
packet. A new error from a predicate/handler escapes the whole handler chain.
An unguarded two-string handler remains the universal source-error handler.
A bare rethrow preserves typed value and source site; constructing a new legacy
error intentionally replaces the packet. Result `?` remains a function return.

A typed raise can project a stable type name and generic message to a legacy
catch; the payload must not be implicitly formatted or exposed by HTTP/worker
transport. Only an explicit typed binding exposes the value. Typed filters do
not handle fatal control, and a typed-only handler is not automatically total
for a call with the existing coarse `throw` effect. Precise typed effect rows
belong to the wider effects work; do not infer them from payload support.

The version-selected frontend/reference implementation exercises these ordered
semantics with ordinary owned data. Native project/library delivery, task/authority payloads,
public selection and graph migration are still gated. Tests/typed_source.cpp
checks the candidate while the genuine026 fixture verifies retained identities.

## Required before enabling027

- Add version-selected syntax/checking and append semantic AST forms without
  changing retained026 canonical fields or statement ordinals.
- Implement ordered handler clauses, exact typed matching and left-to-right
  operand evaluation in the reference, native, TaskIR/AST and TypeScript engines.
- Carry the same owned value through synchronous native packets, suspension,
  finally outcome replacement, foreign/pure calls and module boundaries.
- Extend lifetime/source-edge analysis to carry payload provenance. Resource,
  closure, file and task authority still require real realm/owner-transfer checks;
  merely retaining a Value must never promote a capability out of its region.
- Define matching task/provider/runtime protocol pins, reject incompatible
  cohorts before execution and preserve existing public/private ABI meanings.
- Keep HTTP/worker failures generic; add bounded debugger/profile views without
  an implicit data leak or execution of source callbacks.
- Implement explicit026-to027 migration using the genuine026 fixture at
  `tests/fixtures/language-0.26-typed-origin.*` (actual0.139.0 compiler, two
  reference revisions plus native Debug/Release);
  preserve every old graph row/schema/local ID and append the checked revision.
- Reconcile specification/grammar/capability pack/LLM contract/examples and pass
  actual engine agreement, rejected programs, cleanup, SDK and platform gates.

Task-finally0.139 acceptance has its own frozen compiler/source receipts. It does
not certify this foundation or future027 behavior. The original full NEX language,
platform, tooling and accelerator plan remains active.

Synchronous candidate TypeScript uses a private typed-payload WeakMap and real
source-error branding. Its ordered clauses share one protected catch boundary;
false predicates keep the original packet, and newly raised handler errors escape
siblings. Metadata JSON excludes payload data. Actual Node/strict-TypeScript
agreement and retained025 compatibility are in tests/typed_source_typescript.py.

Sequential candidate native lowering follows the same single ordered catch
boundary, with distinct protected/common-packet/clause owners. A declined clause
cleans its bindings before the next match. The complete owned packet is retained
through ordinary source-call out-parameters and finalizer paths. Private scalar
wire tags0/1/2 and heap-kind checks are covered by the runtime-cohort hash, not a
published foreign/task ABI. Task/provider protocol publication and migration
remain pending. See tests/typed_source_native.py and source_error_native_packet.cpp.

Candidate0.145 task engines lower ordinary owned typed values through AST,
TaskIR, native frames and TypeScript generators. Native helpers require the
separate0x2701 development cohort and retain one lexical packet across ordered
clauses. Public ABI6/025 provider and archive contracts are unchanged. Payloads
containing authority remain rejected; payload provenance/transfer, provider
publication, bounded debugger/profile views and genuine027 migration are still
mandatory before public delivery. See tests/typed_source_tasks.py.
