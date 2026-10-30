# NEX source errors (language0.27)

Discover `source_exceptions` in the selected compiler. Toolchain0.151 develops
ordinary027 CLI execution, checked archival/migration, native/TypeScript delivery,
provider images and bounded debugging. Matching full regression, installed SDK
and platform acceptance are separate gates. Older SDKs retain their advertised
language; this guide does not upgrade projects automatically.

## Raise and handle

```nex
module errors;
struct LoadFault<T> { value: T; }
fn load(path: str) -> unit !{throw} { throw(LoadFault<str>(path)); }
fn main() -> unit !{io} {
  try { load("input"); }
  catch(error: LoadFault<str>) if error.value == "input" { print(error.value); }
  catch(code, message) { print(code); }
  finally { print("finished"); }
}
```

`throw(value)` evaluates once and retains the original owned value with its
complete concrete type key after specialization. Matching includes nominal
identity/layouts, generic/phantom arguments and callable realm/effects. A typed
catch binds the immutable value; no inheritance, string conversion or structural
coercion occurs. Unapplied constructors and unsupported value kinds are rejected.

`throw(code,message)` raises the legacy pair of strings. A legacy catch handles
either source-error form through copied code/message metadata; a typed value is
not serialized into that projection. Native/reference typed errors use the type
name as code and the generic message `typed source error`. Use a typed catch when
the value is needed. Bare `throw;` requires a lexical catch and preserves the
original packet, concrete key and source location.

Clauses run in source order. The guard executes once after a type match; false
continues with the original packet. A source error from a guard or handler escapes
all siblings. A catch with no guard or literal true can establish total coverage;
otherwise the uncovered source-error effect still needs an outer handler or
`throw` declaration. Bindings retain ordinary scope, immutability, effects and
realm rules. Generic handlers use the concrete specialized type at execution.

## Finalization and other outcomes

`finally` runs once after normal completion, return, Result `?` return and an
escaping source error. Pending values/errors remain owned across task yields.
A return, `?` or source error in the finalizer replaces the pending outcome and
releases its prior owner. Catch/protected locals are unavailable there; outer
locals remain visible. A finalizer introduces no implicit catch for rethrow.

Checked arithmetic/bounds/UTF-8/assert traps, allocation/control failures,
cancellation and deadlines are separate outcomes. They bypass source catches
and user finalizers. Runtime resource/owned-value cleanup and joined physical
settlement still complete. Merely throwing a string code named E_TIMEOUT or
E_DIV_ZERO does not change an explicit source error into a runtime trap.

A Result error is an ordinary value. `?` returns from the current function;
`unwrap` can trap. Neither is an implicit source throw.

## Ownership and delivery

An error owns its immutable value, including nested aggregates and captures.
Copying/observing it does not grant authority or extend a scope. Known resource/
file/task escapes are rejected statically; uncertain paths retain runtime owner
checks before transfer/retirement. Native/reference support only the existing
authorized operations. Browser code continues to reject file/FFI/server authority
and wire values containing callables or task/resource capabilities.

Native task delivery selects ABI7. Retained025/026 ABI6 and private2701/2702
cohorts remain distinct; old records/images cannot be relabelled. Source-required
static/shared/mixed providers use the matching checked contracts in
[typed-error-providers.md](typed-error-providers.md).
Public TypeScript delivery uses `nex.typescript-map/2` and keyed immutable
sourceErrorContracts. The explicit development emitter retains map027-3.
Synchronous UI stays pure; worker-local typed values do not cross messages.
Uncaught/rethrown Worker errors become generic E_SOURCE_EXCEPTION, while checked
trap codes remain distinct. See [browser delivery](typed-web-delivery.md).
Pure scalar Wasm supports its existing i64/bool/unit subset; reachable source
errors/finally and effects are still rejected there.

## Migration and tools

Use [guarded migration](typed-error-migration.md) for an archived026 graph.
Old rows, local IDs, namespaces and source remain available; physical export is a
separate explicit step. Data snapshots preserve mixed histories and do not
perform a language upgrade. Source-only old Git projects without a graph need
an origin snapshot/export or their matching SDK before this archived-graph
migration path; automatic source-only bootstrap remains pending.

Use `nex context --symbol NAME` and the compiler's guide/descriptor rather than
inventing exception APIs. The [language specification](language.md) and
[grammar](grammar.ebnf) define syntax; [development history](exceptions-history.md)
preserves earlier scoped work without overriding the current contract.
