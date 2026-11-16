---
status: current
applies_to: "language 0.28; language 0.29; language 0.30; toolchain 0.273.0"
owner: repository
---

# Language prerequisites for Java and Python migration

Toolchain0.273 adds ordinary [persistent hash map/set](hash-containers.md)
with explicit stable hash/equality callbacks. They are a typed collection
foundation; Python dynamic protocols/insertion-ordered dicts and JDK collection
compatibility still need their own contracts.

Toolchain0.272 adds [persistent030 browser state](persistent-ui.md) across
serialized source-task invocations. Native persistent application/provider
lifetimes, Java/Python class/dynamic compatibility and complete delivery remain
open.

Toolchain0.271 enables ordinary [owned reference-task execution](reference-tasks.md)
in evaluation, native applications/HTTP and TypeScript exports. ABI8/map4 retain
older cohorts without source/history relabeling. Persistent application/UI state,
library/task host lifetimes, parallel transfer, debug/profile and complete
SDK/platform qualification remain open. These execution contexts do not supply
Java/Python class, reflection or dynamic runtime compatibility.

User direction, 2026-11-15: prepare NEX's language/runtime/library foundations
before implementing converters. Java has priority, followed by Python. Converter
implementation is deferred. This is part of item 2 of the
[implementation sequence](implementation-1-6.md); unrelated library expansion
does not take priority over these prerequisites.

The 2026-11-16 direction prioritizes a compact practical core, ordinary libraries
and a usable SDK before exhaustive source-language emulation. The matrix below
retains the full compatibility backlog; it is not a requirement to implement
every Java/Python facility before writing a new NEX application. A selected
migration must preserve the behavior it uses, through checked NEX operations,
explicit compatibility code or a declared transitional adapter. Unknown behavior
must remain visibly unsupported.

## Audited baseline

Source main `4b5ba60f`, toolchain 0.247.0, default language 0.28 and explicit
0.29. The compiled descriptor reports immutable records/lists, snapshot
closures, static trait dispatch, finite f64, checked i64, Unicode scalar strings,
typed source errors, owned external resources and structured tasks. Owned opaque
resources are server/FFI capabilities, not a general application object heap.
No converter or general Java/Python runtime compatibility is implemented.

The first 0.248 source block adds the explicit
[Java int value domain](java-integers.md). Its nominal checked-i64 representation
establishes 32-bit behavior; machine i32 lowering and the other rows below stay
open. The 524-case prototype already agreed with a real JDK21, an independent
mathematical model and NEX reference/native Debug/Release/strict TypeScript.
Matching integrated-build/installed qualification is recorded separately.

This block also corrects selected-language attribution in parse/check diagnostics
and archived graph operations. Version 0.29 contexts, declaration contexts,
revision reads, patches, restore/import/export and runtime-contract projections
must use the stored/selected language instead of the compiler's 0.28 default.
These corrections preserve canonical program formats and existing revisions;
they do not automatically migrate or reset a graph.

The 0.249 [managed-reference kernel](managed-references-design.md) establishes a
private C++ foundation for identity, aliased mutation, retained immutable
snapshots and collection of unreachable cycles. The 0.250
[private candidate](managed-references-prototype.md) adds checked `cell<T>`/`state`
and sequential reference execution; 0.251 adds dedicated private native emission
and an application-owned heap. Public source versions, complete native/TypeScript
agreement, migration and the ownership/concurrency/ABI contracts below stay open.
No ordinary source version or converter is introduced by this candidate.
The 0.252 [TypeScript heap kernel](managed-reference-typescript-heap.md) adds
explicit roots and matching graph-count/collection behavior. The 0.253
[private source emitter](managed-reference-typescript-prototype.md) adds boxed
values, expression/lexical roots and return/error ownership. Ordinary clients
still reject reference source; public migration and entry/module/ABI integration
remain next.

Toolchain 0.254 made ordinary sequential graph retirement iterative, including
snapshots dropped after the cell heap closes. The 0.255
[atomic owner](value-owners.md) removes the concurrent last-release race and
carries synchronous retirement across modules, preserving genuine typed
destructors. Public promotion and a shared mutable memory model remain open.

Toolchain0.256 fixes declaration-local type binding in the private candidate:
0.29 partial/higher-order constructors, static traits and associated projections
compose with cell identity, snapshot payloads and typed errors. This remains one
unarchived sequential unit. Public version/migration, modules, host-returned
references and Java/Python object semantics are still pending.

Toolchain0.257 adds private source-module binding and execution in one application
context. Imported functions, nominal identities, traits, errors and closures use
the same heap and existing visibility rules. This does not define separate
DLL/component/host reference lifetimes or promote a public source version.

Toolchain0.258 adds request-owned heap lifetime and a private native request
entry for repeated scalar-status/source-error calls. Cancellation, budget and
deadline checks close source ownership on the request's thread. HTTP/source
resource integration, task transfer and reference-valued host returns stay open.

Toolchain0.259 composes private references with sequential server fs/ffi calls and
their existing owned file/external resources in local/call/typed-error paths.
An enclosing explicit reference-host file capability is respected. Owned values
remain forbidden inside cells, including actual captured values. This does not
qualify database/task/HTTP adapters or Java/Python resource finalization semantics.

Toolchain0.260 adds genuine owned resource payloads/captures to private cells,
snapshot-preserving resource aliases and collection of visible cell/resource
cycles. It guards native cleanup reentry and callback-ended heap owners. Source
finalizers, opaque callback cycles and public migration remain separate contracts.

Toolchain0.261 adds private TypeScript host-value entries with checked immutable
arguments/results, per-call owned heaps and independent copied diagnostics.
Persistent UI state, live reference host returns, worker transfer and public
version/history migration remain open; see [value exports](managed-reference-value-exports.md).

| Required behavior | Existing foundation | Missing language/runtime result |
|---|---|---|
| Java `int`/`long`, casts, bits and shifts | Checked i64 and explicit nominal Java32/Java64 domains with wrapping/cast/bit/shift behavior | Primitive widths/specialized lowering, remaining Java numeric conversions and their SDK/platform qualification |
| Java `float`/`double` | Finite f64; separate internal binary32/binary64 kernel with IEEE special values, signed zero, primitive operations and Java integral casts | Source types/literal rules, checked binding, all backend/wire/debugger/ABI paths, versioned migration and SDK/platform qualification |
| Java object references and identity | Immutable values, owned resources; ordinary030 sequential cells, static components and HTTP request contexts | Nullability/class layouts, reference task integration and full SDK/platform qualification |
| Java classes and interfaces | Records, enums, generics, coherent static traits | Constructors/class initialization, virtual/interface dispatch, subtyping and runtime type tests; generic erasure/boxing rules |
| Exceptions | Nominal typed throw/catch, filters, finally, task propagation | Exception subtyping/identity, causes/suppression/stack data and source-specific abrupt-completion rules |
| Java strings/arrays | Scalar-indexed strict UTF-8 strings; immutable lists/bytes | UTF-16 code-unit representation including lone surrogates; mutable aliased arrays and bounds/error mapping |
| Java concurrency | Structured tasks/channels and explicit cancellation | Monitors, atomics, visibility/memory-model rules, interruption, thread-local state and compatible library behavior |
| Python integers/numerics | Checked i64, finite f64 and explicit numeric helpers | Big integers, Python division/remainder/shifts, numeric coercion and boolean-as-integer rules |
| Python objects and containers | Nominal immutable aggregates, callable snapshots and sequential030 typed cell identity | Dynamic values, Python object identity/protocols, mutable list/dict/set aliasing, hashing/equality and ordered dict behavior |
| Python calls/classes | Typed functions/closures and static traits | Attribute/method lookup, descriptors, multiple inheritance, keyword/default/variadic calls and runtime type operations |
| Python control flow | Explicit loops, typed errors and structured tasks | Generators/iterators, context-manager exits, async generator/coroutine semantics and truth-value protocols |
| Libraries and native boundaries | Explicit native FFI and provider boundaries | Defined JDK/Python library contracts and reviewed native adapters; no implicit JVM/CPython dependence |
| Development chain | Source/graph identities, native/TypeScript/debug/profile tooling | Representation-aware debugger/wire/ABI/SDK support for each new type and effect |

Use the source project's actual language/runtime version for acceptance. The
[Java numeric specification](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.2.2)
and [operator rules](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.17.2)
describe wraparound, division and shift requirements. Java's
[character API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Character.html)
uses UTF-16 code units; [Python built-in types](https://docs.python.org/3/library/stdtypes.html)
define unbounded integers, identity, mutable collections and operand-returning
`and`/`or`. NEX's current scalar strings and boolean operators cannot silently
replace these domains.

Toolchain0.262 introduces distinct030 semantic archives and explicit guarded
history migration through C++ APIs, together with normal sequential backend
entries and inherited reference-free029 task behavior. Ordinary030 CLI/project
publication, nullable/class layouts, library/HTTP/task reference contexts and
debugger/SDK/platform acceptance remain open; see [source030 development](references030.md).

Toolchain0.263 adds sequential code-only [native reference libraries](reference-library-abi.md).
One matching host/application runtime and enclosing context retain cell aliases,
returned captures and typed error payloads across related calls. This closes a
bounded native library lifetime step; HTTP/task contexts, public030 selection,
class/nullability layouts and Python protocols remain open.

Toolchain0.264 connects030 references to sequential native HTTP contexts with
independent request heaps and copied uncaught diagnostics. Compatible static
archives, response/error cleanup and file-owner cycles have focused functional
coverage. Task transfer, foreign-resource HTTP acceptance, class/nullability
layouts and the remaining Java/Python semantics stay open.

Toolchain0.265 exposes ordinary030 CLI projects, graph authoring/migration,
static components, API source projection and source-deleted task replay.
New projects explicitly select0.30; retained028/029 keep their semantics.
Task acceptance protocol0.28 remains separate from each captured source version.
This closes project selection, not the Java/Python object models or a new
portable SDK release.

## Python-specific preparation

Toolchain0.268 adds a private [AST reference-task context](reference-tasks.md)
for shared cell identity through captures, waits, channels and source errors.
It keeps the existing file/foreign region rules and owned-context teardown.
This prepares logical semantics; ordinary backends, parallel transfer and the
Java/Python object/concurrency models remain separate requirements.

Toolchain0.267 adds the internal [IEEE numeric kernel](ieee-numeric.md).
Its explicit binary32/binary64 operations, comparisons and Java casts are a
runtime foundation. No source type/operator, wire representation or language
version is introduced. Python's division/errors and integer/object protocols
retain their separate requirements; IEEE arithmetic alone does not supply them.

Toolchain0.266 adds the [Java long value domain](java-long.md): wrapping64
arithmetic, masked shifts, signed division/remainders and integral conversions.
It is ordinary source over existing i64/Int32, not a new primitive, Java boxed
object or complete numeric runtime. IEEE domains and specialized lowering remain
open. Python's unbounded integers require their own implementation.

Python migration requires more than translating syntax. The current cell
foundation can express typed identity and shared mutation; it does not provide
Python's dynamic attribute lookup, special-method dispatch, mutable collection
contracts or unbounded integers. Generators, context managers and async source
semantics also need explicit lowering and error/exit rules.

Keep static NEX code directly compiled where source behavior can be established.
Define any dynamic compatibility layer separately, with explicit runtime cost
and supported facilities. Library adapters need their own contracts; native
FFI alone does not establish Python package compatibility. A complete Python
project cannot yet be accepted for automated conversion, and equivalent speedup
across static code, dynamic code and native extension workloads is unmeasured.

## Implementation order

1. Specify exact numerical contracts and implement an explicit Java integer
   domain. First qualify 32-bit arithmetic, casts, bit operations, masked shifts
   and division errors against a real JDK. An ordinary nominal value/API can
   establish these semantics without changing existing NEX arithmetic. Record
   its representation and cost honestly; it does not establish native i32 or
   complete Java numeric support. Follow with long/IEEE domains and machine
   types/lowering, keeping checked NEX arithmetic as the ordinary default.
2. Add the general typed object/reference foundation: identity distinct from
   structural equality, explicit mutation effects, nullability and an ownership/
   collection design that handles cyclic graphs. Define closure capture,
   aliasing and cross-task/thread behavior before making references transferable.
   Opaque FFI handles alone do not close this requirement.
3. Add runtime interface/class dispatch, constructors, initialization and type
   tests; extend typed exceptions to the required hierarchy and exit rules.
   Keep immutable value types useful alongside reference-based objects.
4. Add compatible mutable arrays/collections and UTF-16/string domains. Qualify
   thread synchronization and memory visibility after the reference model.
5. Prepare Python's big-integer and dynamic-object/protocol layers using the same
   defined ownership, dispatch and error foundations, with Python-specific
   behavior. Preserve source versions and list unsupported dynamic facilities.
6. Qualify new capabilities in all applicable compiler backends, debugger,
   profiling, ABI/wire/build/SDK paths before converter implementation starts.

Do not introduce a global "Java/Python mode" that changes existing NEX operators,
strings, value equality or cleanup. New core types/effects/syntax require an
explicit source-language version and history-preserving migration; ordinary
library APIs require reviewed dependency-pin updates instead. Dynamic values
must not bypass the checker or turn unknown behavior into a silent default.

## Acceptance before conversion

For each feature, retain a small manual source-language program and equivalent
NEX program with edge cases. Compare actual outputs, mutation/alias observations,
errors and cleanup using the selected JDK/CPython, NEX reference, native Debug/
Release and applicable strict TypeScript. These are language compatibility tests,
not project converters, sanitizer/fuzz campaigns or a completeness percentage.

Keep the existing regression baseline. Run affected checks for completed blocks;
run full compiler/platform/SDK gates at integration milestones. A supported
numeric subset does not qualify objects, frameworks or arbitrary projects.
