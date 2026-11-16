---
status: current
applies_to: "toolchain 0.256.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Private checked references and state effects

This is an internal language-integration candidate built on the
[managed heap kernel](managed-references-design.md). It is selected through C++
`parseManagedReferencesPrototype`, ordinary `check`, then
`evaluateManagedReferencesPrototype`, declared in the source checkout's
`include/nex/managed_references.h`.
It requires a source/compiler development checkout; it is not a public SDK API.

Its identity is **`0.30-refs-prototype`**, not public language 0.30. Ordinary
`parseVersioned`, `nex.json`, CLI language selection and existing projects still
support their advertised versions. The private candidate cannot create stored
revisions, source bundles or dependency locks. Ordinary reference evaluation,
MLIR/native, Wasm and TypeScript emission reject it. The dedicated 0.251
[native candidate](managed-reference-native-prototype.md) has a separate C++
entry point. Public promotion still
requires all source backends, execution-context/ABI ownership and an explicit
history-preserving migration. No converter is implemented.
The dedicated 0.253 [TypeScript candidate](managed-reference-typescript-prototype.md)
emits this checked source through its own C++ API. Ordinary TypeScript emission
still rejects it; no CLI/project language version is promoted.

## Checked source behavior

The [private grammar](managed-references-prototype.ebnf) adds `cell<T>` and
`state`. The following is input to the **private C++ parser**, not a program to
run with the ordinary CLI:

```nex
module private_counter;
fn make() -> cell<i64> !{state} { return cell_new(0); }
fn increment(value: cell<i64>) -> i64 !{state} {
  cell_write(value, cell_read(value) + 1);
  return cell_read(value);
}
fn main() -> unit !{io,state} {
  let value: cell<i64> = make();
  let alias: cell<i64> = value;
  print(increment(alias));
  assert(value == alias);
}
```

Creation, read, write and explicit collection each require the `state` effect.
Read also requires it: a pure function must not observe changing contents through
an alias. Effects propagate through named/indirect calls, closures and inferred
generic effect arguments. Pure contract predicates cannot read or mutate cells.
Passing a reference or comparing its identity does not read its payload and
requires no `state` effect by itself.

| Operation | Checked result | Behavior |
|---|---|---|
| `cell_new(value)` | `cell<T>` | Infer T from the input/context and create a fresh identity |
| `cell_new<T>(value)` | `cell<T>` | Check the explicit T and its input, including an empty aggregate |
| `cell_read(value)` | T | Retain the current immutable payload snapshot |
| `cell_write(value, next)` | unit | Check next as exactly T, then replace the shared cell's payload |
| `cell_collect()` | unit | Trace current source/host roots; does not expose collection counts |

Argument evaluation remains once, left to right, before the operation. Boolean
short-circuiting skips the unselected branch. Ordinary local `var` captures keep
their immutable snapshot behavior; capturing a cell retains the identity, so
closures intentionally observe later writes. A returned cell or closure stays
valid across ordinary source function returns within the same execution context.

The candidate supports cells inside immutable records/lists/results/enums,
parametric functions and the unary `cell` constructor in higher-kinded generic
arguments. Explicit owned file/external/task payload types are rejected; generic
substitution rechecks these restrictions. The runtime also checks actual nested
payloads/captures. Cycles may pass through cells. Existing immutable containers
are never converted into shared mutable values.

Typed source throws/catches can retain cell identity within the context,
including finally, early return and Result `?` paths. An uncaught source error
becomes an `E_SOURCE_EXCEPTION` diagnostic at the private host entry. Its owned
payload does not escape that context: the host lifetime ABI remains unfinished.
Fatal traps keep their existing cleanup/skip-finally rules.

### Generic composition in 0.256

The single-unit frontend gives each declaration's type parameters its own
identity before checking. Reusing `T` or `F` in another declaration cannot
overwrite the first declaration's kind or bounds. Trait methods bind their own
parameters and `Self`; associated projections and the second type-argument list
in `Mapper<cell>::map<i64,str>(...)` are resolved before specialization.

This composes the private cell candidate with 0.29 partial type lambdas,
whole-type constructor inference and higher-order signatures. Examples include
`Pair<cell<i64>,_>`, `Wrap<cell>` and `H<Wrap,cell>` when `H` declares
`F<_<_>>,G<_>`. Static trait methods can read/create cells with declared `state`,
and their method references can be stored in cells. Generic typed throws keep
cell identity through inferred callback effects and `finally`.

The source corpus checks these combinations in reference, native O0/O2 and
strict executed TypeScript, including retained snapshots, explicit collection,
effect rejection and phantom constructor arguments that must not enter JSON.
This binding correction changes no public source version or graph format.

There are no tasks, parallel execution, imported projects, endpoints or
fs/db/ffi execution in this candidate. These are pending integration work,
not newly removed capabilities of ordinary NEX. The private host entry can
return unit or an immutable wire value; cells, cell-containing types (including
phantom arguments) and closures cannot escape through JSON. Source debugging,
profiling, watch execution, device lowering and native module lifetimes are not
qualified by this interpreter.

## Context ownership and bounds

One reference interpreter owns one `CellHeap`, spanning all source calls and
closure invocations. Source frames and caught packets retire before heap close.
Collection sees their ordinary strong roots. The private result reports heap
counts before/after a final collection for development evidence; these counters
are not source-language results. Tests require no remaining cell/data nodes
after a completed unit/wire entry. Error/trap exits also close the heap.

The existing AST step budget and call-depth limit remain. Heap cell/node/payload
slot limits use `CellHeapLimits`, with the kernel's default values or explicit
private C++ limits. GC traversal is not currently charged as AST source steps;
this interpreter does not establish a hard CPU budget or real-time pauses.
Deep external snapshots and host-returned reference lifetimes remain part of
the broader context ownership work described in the kernel guide.

## Compatibility and verification

The private builtin constructor uses an internal discriminator. It does not
reserve or reinterpret a public project's user-defined `struct cell<T>` or
`fn cell_new`. A frozen [public baseline](../tests/fixtures/managed-references/public-baseline.json)
records actual 0.249 results and revisions for the same higher-kinded nominal
program in 0.28/0.29. The new probe must retain both revisions and value 42.

[`tests/managed_references.cpp`](../tests/managed_references.cpp) exercises source
aliasing/identity, argument order, short-circuiting, snapshots, returned closures,
generic constructors/effects, cycles and source-error/finally exits. It rejects
missing effects, wrong payloads, owned payload types, wire export, pure contract
reads, unsupported execution modes, unchecked input and archival attempts.
The ordinary grammar and source versions stay unchanged. Full native/TypeScript
agreement and installed/current-platform SDK acceptance remain required before
public use; a passing reference candidate cannot establish them.

[Focused 0.250 evidence](evidence/managed-reference-source-0.250.0-2026-11-15.json)
records 13 accepted and 38 rejected probe scenarios with no residual live values,
the 13-group core selection and eight affected groups. The final core took
21.09 s; affected public-language checks took 80.87 s on the recorded Mac.
These are bounded development checks, not full compiler/SDK qualification.

[Focused 0.256 evidence](evidence/managed-reference-generics-0.256.0-2026-11-16.json)
records 19 accepted and 41 rejected reference scenarios, 16 core groups,
84 native O0/O2 comparisons and 44 strict executed TypeScript scenarios.
Each native comparison also runs an independently linked executable. The final
corpus includes generic statement matches, contracts and defaults. Full current
SDK/platform qualification and public source promotion remain pending.
