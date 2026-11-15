---
status: current
applies_to: "language 0.28; toolchain 0.252.0"
owner: repository
---

# Language prerequisites for Java and Python migration

User direction, 2026-11-15: prepare NEX's language/runtime/library foundations
before implementing converters. Java has priority, followed by Python. Converter
implementation is deferred. This is part of item 2 of the
[implementation sequence](implementation-1-6.md); unrelated library expansion
does not take priority over these prerequisites.

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
explicit roots and matching graph-count/collection behavior. The checked
TypeScript source emitter and boxed value facade remain next; ordinary clients
still reject reference source.

| Required behavior | Existing foundation | Missing language/runtime result |
|---|---|---|
| Java `int`/`long`, casts, bits and shifts | Checked i64 and ordinary nominal values | Exact wrapping operations, narrow-width types/conversions and efficient native lowering |
| Java `float`/`double` | Finite f64; zero normalization | Binary32, IEEE special values, signed zero, casts and specified rounding in an explicit domain |
| Java object references and identity | Immutable values; owned opaque resources; private C++ cell/collection kernel and checked reference candidate | Public types/effects/migration, nullability, native/TypeScript/context/ABI integration and qualified collection/lifetime rules |
| Java classes and interfaces | Records, enums, generics, coherent static traits | Constructors/class initialization, virtual/interface dispatch, subtyping and runtime type tests; generic erasure/boxing rules |
| Exceptions | Nominal typed throw/catch, filters, finally, task propagation | Exception subtyping/identity, causes/suppression/stack data and source-specific abrupt-completion rules |
| Java strings/arrays | Scalar-indexed strict UTF-8 strings; immutable lists/bytes | UTF-16 code-unit representation including lone surrogates; mutable aliased arrays and bounds/error mapping |
| Java concurrency | Structured tasks/channels and explicit cancellation | Monitors, atomics, visibility/memory-model rules, interruption, thread-local state and compatible library behavior |
| Python integers/numerics | Checked i64, finite f64 and explicit numeric helpers | Big integers, Python division/remainder/shifts, numeric coercion and boolean-as-integer rules |
| Python objects and containers | Nominal immutable aggregates and callable snapshots | Dynamic values, identity, mutable list/dict/set aliasing, hashing/equality protocol and ordered dict behavior |
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
