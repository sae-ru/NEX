# Traits, associated types and constructors — language 0.16

Language0.16 implements the mechanisms described here: user traits, associated
value types and fixed constructor parameters. The compiler reports their exact
capabilities and limits. Source/compiler-specific regression, SDK, platform and
adapter evidence is recorded in STATUS.md and docs/evidence; the descriptor's
conservative integration-pending tracking does not disable checked declarations
or certify a platform test result. Keep the earlier language-0.15 constructor
core and its archived artifacts distinct.

```nex
trait Content {
  type Item: wire;
  fn get(value: Self) -> Content::Item<Self>;
}
struct Box<T> { value: T; }
fn extract<T>(value: Box<T>) -> T { return value.value; }
impl boxed<T: wire>: Content for Box<T> {
  type Item = T;
  get = extract<T>;
}
fn read<T: Content>(value: T) -> Content::Item<T> {
  return Content<T>::get(value);
}
```

A trait has an implicit `Self` parameter, named method signatures and optional
associated value types. A named implementation binds every method and associated
type exactly once. Its methods name ordinary checked NEX functions, including
concrete external declarations with the same explicit realm/effects and normal
operator-grant requirements. There is no implicit execution authority.
`trait`, `impl`, `type`, `for` and `Self` remain contextual; old ordinary names
are preserved. A trait is not a runtime value or nominal data constructor.

Write a bound `<T: Content>` and select a method with
`Content<T>::get(value)`. The checker also infers Self from value arguments when
no explicit type arguments are supplied. Associated projections spell
`Content::Item<T>` and require the corresponding bound or finite implementation
witness. They are structured types; they do not infer Self from an expected
associated result because that mapping need not be injective.

All generic bodies and implementations are checked even when unused. A trait
bound permits its declared methods and associated types, without assuming the
types of current callers. Method parameter/result types and realm/effects must
match exactly after substitution. A target's bounds cannot be stronger than
the trait's method contract. Associated values satisfy their declared bounds;
`unit` and unapplied constructors are not associated value types.

Implementation heads must not overlap, including when their bounds differ.
Each implementation parameter occurs in its head. The trait or outer nominal
head must belong to the implementing module; builtin heads require a local
trait. Import order does not select a preferred implementation. Recursive
obligations and associated aliases need finite normalization; cycle and budget
failures are diagnostics. Associated projections are not allowed in heads.

```nex
trait Mapper<Self<_>> {
  fn map<A, B>(values: Self<A>, apply: fn(A)->B) -> Self<B>;
}
// map_list<A,B> has the matching ordinary list implementation.
impl list_mapper: Mapper for list { map = map_list; }
fn convert<F<_>: Mapper, A, B>(values: F<A>, apply: fn(A)->B) -> F<B> {
  return Mapper<F>::map<A, B>(values, apply);
}
```

`F<_>` is a constructor accepting one value type; `F<_,_>` accepts two. `list`,
`result` and eligible generic nominal constructors can be explicit arguments.
Applications such as `F<A>` are value types. A bare constructor cannot be a
local/parameter/result value. Generic structures/enums can also take constructor
parameters and store fully applied fields. A constructor whose own slots accept
constructors has a different kind from `F<_>`; higher-order kind signatures
remain unsupported. Partial applications such as `Pair<i64,_>` are accepted as
explicit constructor arguments and fill their holes when applied. Inference from
an applied argument uses its trailing arguments for the explicit value parameters
and fixes the leading arguments as holes; ambiguous positions still need an
explicit lambda.

For a generic trait method the implementation binding supplies any target
prefix arguments, followed implicitly by the trait method's parameters in
declaration order. For example, `get = extract<T>` supplies an implementation
parameter; `map = map_list` receives `A,B` from the method. Calls may supply Self
only and infer the method parameters, supply both lists, or infer all arguments.
Named method references use the same exact function-value contract.

Concrete dispatch selects an ordinary target before lowering. Callee and
arguments evaluate once, left to right; checked arithmetic, short-circuiting,
strict UTF-8, immutable aggregates, effects, realms and native owned cleanup
retain their existing rules. No dictionary, model or native inferior call is
introduced. Abstract signatures and constructors cannot become runtime values.

Use `context --entity trait|impl --symbol NAME` for bounded declaration context.
Contract method nodes and specializations are derived. Replace the owning trait
or named implementation with a revision-guarded declaration patch, together
with affected functions/types. Graph edges retain the contract, selected
implementation and actual target. Stale guards and failed candidates preserve
the previous graph. Export explicitly to materialize archived changes.

Limits include 64 type arguments/constructor arity, 64 Self-plus-method
parameters, 1024 members per trait, 4096 traits/implementations, 64 obligation
levels and 4096 obligation steps. Generic expansion and graph limits also apply.

Language 0.16 uses function/13, structure/5, enum/4 and program/14 canonical
formats. Retain SDK 0.54 for language-0.15 frames, receipts and archives. Use
explicit `migrate`, preserving original revisions/IDs/history, then export a
separate current project and validate its behavior. Task/proof metadata needs
reviewed new canonical pins while preserving requirements, tests, conditions,
invariants, effects and measured budgets. Do not relabel old artifacts.

`examples/traits` contains source examples and a genuine older SQL fixture.
API extraction retains required associated contracts/witnesses and real
client/shared method targets, including captured libraries. Server trait members,
bindings and function bodies are excluded. Both projected projects are checked;
see api.md for realm/import boundaries and STATUS.md for exact validation scope.
General source async, dynamic trait objects, specialization priority and all
remaining platform/development-chain requirements remain separate work.
