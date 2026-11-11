---
status: current
applies_to: "toolchain 0.171; language 0.28"
owner: repository
---

# Sequential immutable text construction

Discover `text_construction` in the selected compiler. Toolchain 0.171 adds these
four forms to the already reserved builtin name `str`:

```nex
str(count, make)                     // make(index), index 0..count-1
str(values, transform)               // transform once for each element
str(values, predicate, transform)    // transform only selected elements
str(count, initial, next, emit)      // emit(state), then advance for the next item
```

The one-argument `str(value)` form keeps its existing meaning: explicit
formatting of any non-unit value. Two to four arguments select the constructor.
No new keyword, type or grammar production is introduced.

All arguments are evaluated once, left-to-right before count validation or any
callback. Generation counts are checked i64 values; a negative count is fatal
`E_ASSERT`. Zero produces `""` without calling make/next/emit or the transform.
The initial state and callback expressions still run as ordinary arguments.

Mapping and filtering visit the input in order. A filtered construction calls
predicate once per input, then transform once if true, before moving on. The
stateful form calls emit exactly count times and next exactly max(0,count-1)
times. The first emission uses initial; the final state is never advanced.
State must be non-unit; each callback takes exactly one argument. Transform and
emit return `str`; predicate returns `bool`; next returns the state type.
Ordinary generic-reference inference uses the input and expected callback types.
There are no explicit type arguments on this constructor.

```nex
module example;
fn main() -> unit !{io} {
  let squares: str = str(4, fn(i: i64) -> str { return str(i*i); });
  let selected: str = str([0,1,4,9],
    fn(x:i64)->bool { return x>0; },
    fn(x:i64)->str !{io} { print(x); return "["+str(x)+"]"; });
  assert(squares=="0149");
  assert(selected=="[1][4][9]");
}
```

## Effects, tasks and ownership

The constructor infers the union of its callback effects. The caller must allow
that union under ordinary effect/handler rules, and each callback must be callable
from the caller's realm. Typed/legacy source errors escape at the failing item;
later callbacks do not execute. Normal finally behavior is unchanged. Fatal
traps and request cancellation retain their existing cleanup/control rules.

Callbacks may suspend through the existing task machinery. In a task caller,
fs/ffi helpers still require their explicit task effects and original grants.
The constructor creates no task scope, workers, host authority or parallel
execution. Existing allocation, step, deadline, ownership and string limits still
apply. Input lists and aliases stay unchanged. Element/resource identity is
ordinary immutable aggregate identity; construction does not deep-copy resources
or grant new lifetimes. Task/resource-bearing outputs remain subject to the
normal static and runtime owner checks.

## Construction model and cost

The frontend lowers construction into an ordinary checked closure and loop. It
appends each emitted `str` to an unpublished private `list<str>` accumulator
using the same compiler-private append operation as the list constructor. One
final `$text_join` operation copies the pieces once into a new immutable string.
Source cannot name these operations or access the buffer. Internal len/assert
calls bind to their compiler builtins even when caller locals shadow those names;
callbacks keep their original lexical bindings.

For `k` emitted pieces and `B` output UTF-8 bytes, construction performs one loop
iteration per input/count, one amortized append per piece and one linear join:
O(iterations + k + B) copying work, excluding callbacks, comparisons, state and
piece construction. It does not build a balanced concatenation tree and does not
repeatedly copy a growing prefix. This is a structural bound, not a measured
throughput or token-cost claim.

Native output uses one new private runtime symbol, `nex_text_join` (and its
source-site variant). The public C ABI major and the source language version are
unchanged. TypeScript joins that same unpublished array once; its engine controls
array storage. The reference interpreter performs the same single-pass copy.

## Limits and pending work

GPU (Metal/CUDA) and scalar Wasm do not lower this heap constructor; their
existing unsupported-type diagnostics remain. Wider containers, named
source-library effect parameters, and measured runtime benchmarks remain pending.
A failed construction releases its partial private buffer on normal, source-error
and fatal native exits through the ordinary owned-value cleanup.
