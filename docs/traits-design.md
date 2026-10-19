# User traits, associated types and constructor parameters

This is the implementation contract for the next source-language extension.
It is not the specification of an advertised compiler capability. The checked
root remains toolchain 0.54 / language 0.15 while its independent gates run.
Source integration, canonical migration and complete acceptance are required
before this document can become implemented language documentation.

## Source contract

Traits declare named method contracts and associated types. Implementations
bind each method to an ordinary checked function and define every associated
type. The mapping keeps implementation bodies in the existing function graph:

```nex
trait Readable {
  type Item;
  fn first(value: Self) -> Readable::Item<Self>;
}

struct Ints { values: list<i64>; }
fn first_int(values: Ints) -> i64 { return values.values[0]; }

impl readable_ints: Readable for Ints {
  type Item = i64;
  first = first_int;
}

fn first<T: Readable>(value: T) -> Readable::Item<T> {
  return Readable<T>::first(value);
}
```

`trait`, `impl`, `type`, `for` and `Self` are contextual. Previously legal
ordinary functions, locals, nominal types and parameters with these names keep
their meaning. `Self` denotes the trait's implicit first parameter only inside
the declaration. A trait is not a value type, constructor or dynamic object.
Implementation names are explicit, module-local graph declarations. A module
alias may qualify a public trait, associated projection or method selection.
Imports retain normal visibility, unique-module and acyclic-import rules.

Trait parameters can be value types or constructors with explicit arity:

```nex
trait Mapper<Self<_>> {
  fn map<A, B>(values: Self<A>, apply: fn(A)->B) -> Self<B>;
}

fn map_list<A, B>(values: list<A>, apply: fn(A)->B) -> list<B> {
  var output: list<B> = [];
  var index: i64 = 0;
  while index < len(values) {
    output = push(output, apply(values[index]));
    index = index + 1;
  }
  return output;
}

impl list_mapper: Mapper for list { map = map_list; }

fn convert<F<_>: Mapper, A, B>(values: F<A>, apply: fn(A)->B) -> F<B> {
  return Mapper<F>::map<A, B>(values, apply);
}
```

`F<_>` denotes a constructor from one value type to a value type; `F<_, _>`
denotes a binary constructor. `list`, `result` and generic nominal declarations
can be constructor arguments. Constructors are not runtime values. Fully
applied type constructors produce normal existing aggregate layouts. First
integration supports fixed constructor arity up to the existing 64-argument
budget; type lambdas, partial application, dynamic trait objects and overlapping
specialization require a separate design. This does not remove them or any
remaining language/platform requirements from the complete project plan.

## Checking and coherence

All source trait and implementation declarations are checked even when unused.
Every generic method body is checked parametrically, including all effects,
realms, file-bearing types, visibility and ordinary evaluation rules. A bound
permits only its declared methods and associated types. No currently observed
concrete caller can justify an operation on an arbitrary type parameter.

A conformance head identifies the trait and ordered type/constructor arguments,
including Self first. Each generic implementation parameter must occur in its
head so selection determines all arguments. Head patterns contain no associated
projections. Dependencies and associated definitions may contain projections,
but normalization is bounded and must detect cycles.

At most one implementation head can match a concrete request. Reject overlapping
heads before testing their prerequisites: changing constraints or import order
must not change dispatch. Disjoint head shapes can coexist. Do not rank
implementations, silently choose the first one, infer conformance from a
same-named ordinary function or accept a recursive obligation as evidence.
Every prerequisite must have a finite witness. Structural unification has an
occurs check and validates constructor arity before substitution/application.

An implementation is legal only in the declaring trait's module or in the
module of the nominal head type/constructor. Builtin heads therefore require a
local trait. This ownership rule and pairwise head coherence must be checked
over all reachable source, independent of which methods are called.

Method signatures must match after replacing Self, trait parameters and
associated types. Effects and realms are explicit contracts; no implicit
effect/realm coercion is introduced. An implementation method cannot require
stronger generic bounds. Associated types satisfy their declared kind/bounds.
Generic method signatures are compared modulo consistently scoped binder names.

Associated projections spell `Trait::Item<T>` with Self first, preventing
ambiguous `T::Item` lookup when several bounds declare the same item name.
An abstract projection stays a structured type term and retains its declared
bounds. Concrete specialization selects the checked implementation, substitutes
its bindings and normalizes the projection before emitting any runtime code.
Projection identity must never be encoded as an opaque parameter-name string.

## Lowering and graph identity

Concrete trait calls lower to the already checked ordinary target functions;
there is no runtime dictionary or hidden LLM call. Named references preserve
the exact callable contract. Callee/arguments evaluate once, left to right;
logical short-circuiting, checked arithmetic and owned cleanup stay unchanged.
Abstract signatures and constructor/projection terms never reach native or
TypeScript layout generation, the reference executor, API codecs or debuggers.

Trait contracts and named implementations need distinct source declarations,
canonical identities, dependencies, bounded graph context and guarded source
replacement. A call context retains both the declared trait contract and the
selected implementation/target. Instance metadata remains derived and immutable.
Browser reachability starts at selected client/shared targets: an unreachable
server implementation or its foreign pins must not enter emitted clients.

Language 0.16 needs new canonical function/program formats. A genuine 0.54
language-0.15 SQL fixture and matching SDK must be retained before changing the
version. Migration checks archived source explicitly, retains old revisions,
node/operation IDs and journal history, and exports a separate reviewed current
project. Do not globally replace historical language labels or silently upgrade
old manifests, frames, receipts and SDK resources.

## Acceptance gates

Before promotion require actual source programs for direct and forwarded trait
calls; concrete/generic impls; nested associated projections; constructor
parameters for list/result and user nominal types; generic method references and
closures; effects/realm/resource checks; imported public/private declarations;
recursive ordinary functions and finite recursive obligations. Compare native,
TypeScript and reference observations, including evaluation order, traps and
cleanup. Rejected programs must include missing/extra methods and associated
types, wrong signatures/bounds/kinds, phantom impl parameters, overlap,
recursive obligations/projections, missing witnesses and unused bad bodies.

Graph tests must prove source-derived canonical changes, preserved history,
trait/impl/target dependency edges, stale-guard rejection, atomic repair and
derived-instance rejection. The model pack, grammar, schemas, capabilities,
guides and examples must agree with actual implementation. Installed SDK
acceptance must use a real migrated archive, native/browser execution and
source-deleted replay. Current compiler/SDK macOS/Linux gates and broader
release/platform/development-chain requirements remain separate evidence.
