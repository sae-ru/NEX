---
status: current
applies_to: "toolchain 0.180; language 0.28"
owner: repository
---

# Inferred effect parameters

A named generic function can infer an effect set from a callable argument with
an **effect parameter** written `?E`:

```nex
fn apply<T, U>(value: T, transform: fn(T) -> U !{?E}) -> U !{?E} {
  return transform(value);
}

fn main() -> unit !{io} {
  let answer: i64 = apply(41, fn(x: i64) -> i64 !{io} {
      print(x);
      return x + 1;
    });
  assert(answer == 42);
}
```

`?E` is a name for an inferred effect set, not a concrete effect. The checker
infers it from each callable argument and substitutes it into the result and
parameter function types. The caller must declare the inferred effects exactly
as for any other call. A pure callable infers the empty set; an `io` callable
infers `{io}`. If several callable arguments use the same parameter, their
effect sets are unioned.

`std/list.nex` now exposes effect-inferred `map`, `filter` and `fold`:

```nex
let mapped: list<i64> = seq::map(values, fn(x: i64) -> i64 !{io} {
    print(x);
    return x + 1;
  });
```

The syntax is additive: existing functions with concrete effect sets, and pure
callbacks, keep their meaning. A function with `?E` must be generic; effect
parameters are supported on direct calls only. Function values, explicit
effect-witness arguments, higher-rank effects, and a language-version migration
are pending. Callable effect/realm equality remains exact after substitution.
