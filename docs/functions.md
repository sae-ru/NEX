# Function values — language 0.11 (introduced in 0.10)

NEX function values carry an exact checked parameter/result signature, realm
and effect set. They run in the interpreter, native MLIR/LLVM output and
TypeScript without an LLM. Toolchain 0.23 introduces this source-language
version; `STATUS.md` records which platform and SDK checks have actually passed.

```nex
module callbacks;

fn increment(value:i64)->i64 { return value+1; }
fn apply(callback:fn(i64)->i64,value:i64)->i64 { return callback(value); }
fn make(offset:i64)->(fn(i64)->i64) {
  return fn(value:i64)->i64 { return value+offset; };
}
fn main()->unit !{io} { print(apply(make(2),40)); }
test fn examples()->unit {
  let named:fn(i64)->i64=increment;
  assert(named(41)==42);
  assert(make(2)(40)==42);
}
```

Function types use positional types: `fn(i64)->i64`,
`fn(str)->unit !{io}` or `server fn(str)->result<str> !{db}`. Parameters and
results are explicit, including lambda parameters; parameter inference from an
expected signature is not implemented. Parenthesize a returned function type
when its effects must be separated from the caller's, for example
`fn factory()->(fn(str)->unit !{io}) !{io}`. A function can return unit;
unit parameters, locals and collection elements remain invalid.

Calls accept named references, parameters, locals, returned functions and
function-valued record fields/list elements. Evaluate the callee first, then
each argument once from left to right. A callable local takes precedence over
a same-named global function. A non-callable local preserves the existing
separate named-call namespace; explicitly calling an arbitrary non-function
expression is an error. Operators retain checked arithmetic and short circuiting.

Generic named functions use an expected signature or explicit arguments:
`let id:fn(i64)->i64=identity;` or `identity<i64>`. Their bodies are checked
parametrically even when unused. Tests and builtin/nominal constructors are not
first-class callable references; wrap a constructor in a checked lambda.
Signatures require exact parameter/result types, effects and realm. There is
no implicit variance, effect widening or realm conversion. Taking a reference
or creating a lambda obeys the current realm. Invocation requires the declared
effects and an accessible realm just as a direct call does; callbacks cannot
turn server work into a client call.

## Captures, identity and ownership

A lambda snapshots each free lexical value when created. Captures are
immutable, including a captured outer `var`:

```nex
var offset:i64=40;
let captured:fn(i64)->i64=fn(n:i64)->i64 { return n+offset; };
offset=900;
assert(captured(2)==42);
```

Writing `offset` inside this closure is rejected. Nested lambdas capture their
outer parameters/locals and can transitively capture a grandparent value.
Bindings are unavailable in their own initializer; use ordinary named recursion
for recursive functions. Immutable aggregates and snapshot captures do not
introduce mutable reference cycles or user-defined destructors.

Each reference/lambda evaluation creates a callable object. Copying that value
preserves identity; evaluating another reference to the same named function
creates another object. Equality compares callable object identity, including
inside lists/results/records/enums. Formatting a callable yields `<function>`
without exposing a native code pointer. Automatic native ownership retains
captured heap values through the closure lifetime and cleans them on normal,
early-return and request-trap exits. Native test/application wrappers check
normal-exit managed-value cleanup.

The native backend makes a typed indirect call with a hidden environment.
Named references use bridges emitted only when needed. A newly required bridge
invalidates its defining module's cache contract. The TypeScript backend
snapshots captures in an IIFE rather than retaining a mutable JavaScript binding.

## JSON and generic `wire` bounds

Application JSON and endpoint payloads reject actual function values, recursively.
The contextual builtin constraint `wire` states that a generic value can be
encoded/decoded:

```nex
fn roundtrip<T:wire>(value:T)->T {
  return unwrap(decode_json<T>(encode_json(value)));
}
```

`wire` accepts i64, f64, bool, str, recursive lists/results and nominal stored fields
or enum payloads that satisfy the same rule. Phantom type arguments that are not
stored payloads do not prevent serialization. It rejects a function or an
aggregate containing one. A generic parameter must declare a sufficient bound;
unconstrained T still permits equality/formatting but cannot promise JSON for all
values. `integer` implies `number`, `add`, `ordered` and `wire`; `number` implies
`add`, `ordered`, `wire`; `ordered` implies `wire` over i64/f64. `add` alone does not imply wire because a list may
contain callbacks. Forwarding checks these implications before specialization.

Generated API clients preserve nominal types/imports mentioned only in callback
signatures or phantom arguments. Lifted lambda implementations remain derived;
their original source owner is emitted once. This does not make function
payloads transferable over HTTP.

## Tools and migration

`nex describe --json` advertises `function_value_features`,
`function_value_limits`, `generic_constraints` and the separate debug wire
schema. `nex guide --kind function` provides this guide. Graph context and
operation trees expose captures, callable references and invokes. Lifted bodies
have `closure_owner`, typed `captures` and `editable:false`; edit the source
owner or generic template. Internal `$lambda_`/`$watch_lambda_` names are
compiler metadata and cannot be copied into source identifiers. Pure watches
may derive new closures without changing the saved revision.

LLDB/DAP callable watches use `nex.debug-wire/1`, not application JSON. They
validate checked target/signature/effects/realm, compiled native symbol, object
identity and capture layout, then interpret source in the helper process.
Captures are read only when needed; whole-value results require complete bounded
captures. See [expressions.md](expressions.md) for aliases, cycles, computed
identities, budgets, pages and stop expiry. Scalar proofs explicitly report
callable operations unsupported; a passing scalar proof does not prove a
higher-order program or compiler correctness.

Language 0.11 uses `nex.function/9` and `nex.program/10`; nominal formats remain
`nex.structure/4` and `nex.enum/3`. Program identities include source owners and
exclude derived instances/lifted bodies, while owner canonical expressions
include lambda signatures/bodies. Use `nex migrate` to recheck an older
archive, preserving its original source/history and local IDs. Export the new
revision to obtain current manifests/locks. Existing generic serializers may
need an explicit `wire` bound: migration reports an error and leaves HEAD intact
until source is intentionally repaired. `migrate` reads the stored bundle, so
editing a live file alone does not change that bundle. An intentionally edited
exported graph bundle can be passed to `nex migrate FILE`; its source is fully
rechecked and the old stored source/history remains available. Alternatively,
materialize and repair source, then explicitly check it under the current
compiler. Review task/proof acceptance intent
before regenerating pins. Keep SDK 0.22 for old frames and receipts; source
migration cannot reinterpret their runtime layout.

Limits are 1024 callable parameters/captures, 64 nested lambdas, 4096 lifted
instances and 4096 bytes per canonical callable signature/target name. Other
type, generic, interpreter, native-stack and debugger limits still apply.
Custom traits, function/effect subtyping, mutable captured cells, general async,
resource FFI and effect handlers remain pending.

```sh
nex test examples/functions/main.nex
nex test examples/functions/main.nex --target web
nex build examples/functions/web.nex --target web --profile release
```
