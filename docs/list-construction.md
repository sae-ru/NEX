---
status: current
applies_to: "toolchain 0.170; language 0.28"
owner: repository
---

# Sequential immutable list construction

Discover `list_construction` in the selected compiler. Toolchain 0.170 adds these
four forms, using the already-reserved source name `list`:

```nex
list(count, make)                     // make(index), index 0..count-1
list(values, transform)               // transform once for each element
list(values, predicate, transform)    // transform only selected elements
list(count, initial, next, emit)      // emit(state), then advance for the next item
```

All arguments are evaluated once, left-to-right before count validation or any
callback. Generation counts are checked i64 values; a negative count is fatal
`E_ASSERT`. Zero produces an empty list without calling make/next/emit. The
initial state and callback expressions still run as ordinary arguments.

Mapping and filtering visit the input in order. A filtered construction calls
predicate once per input, then transform once if true, before moving on. The
stateful form calls emit exactly count times and next exactly max(0,count-1)
times. The first emission uses initial; the final state is never advanced.
State and output element types must be non-unit; next returns the same state type.
Ordinary generic-reference inference uses the input and expected output type.
There are no explicit type arguments on this constructor; callback signatures
or a receiving type provide the needed context.

```nex
module example;
fn main() -> unit !{io} {
  let squares: list<i64> = list(4, fn(i:i64)->i64 { return i*i; });
  let selected: list<str> = list(squares,
    fn(x:i64)->bool { return x>0; },
    fn(x:i64)->str !{io} { print(x); return str(x); });
  assert(selected==["1","4","9"]);
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
execution. Unlike `parallel_map`, it introduces no 65536-item/parallel graph
limit. Existing allocation, step, deadline, ownership and representation limits
still apply. Do not replace explicit parallel execution with this operation when
actual concurrency is required.

Input lists and aliases stay unchanged. Element/resource identity is ordinary
immutable aggregate identity: construction does not deep-copy resources or grant
new lifetimes. Task/resource-bearing outputs remain subject to the normal static
and runtime owner checks; a list cannot extend an ended task scope.

## Construction model and cost

The frontend lowers construction into an ordinary checked closure and loop with
the inferred types, realm and effects. It uses three compiler-private operations
on an unpublished accumulator. Source cannot name these operations or access the
buffer. Internal len/assert calls bind to their compiler builtins even when
caller locals shadow those names; callbacks keep their original lexical bindings.
The accumulator is returned only after construction; TypeScript freezes
that same array when publishing it. Existing public push/set/concatenation remain
immutable and retain their original semantics.

There is one loop iteration per input/count and one append per emitted element.
Native/reference vectors provide amortized O(iterations+results) construction;
TypeScript also avoids repeated full-prefix array copies, with array-storage
complexity controlled by its JavaScript engine. Callback, comparison, state and
value construction costs are additional. These structural bounds are not a
throughput or LLM-token speedup measurement.

The source list helpers now use this construction path: generate/map/filter/
reverse traverse linearly; stable sort builds each merge linearly with an
immutable cursor. Sort retains O(n log(n+1)) comparisons/reference construction.
Text builders and generic named source-library effect parameters remain pending.
The current named std/list wrappers still declare pure callbacks; use the direct
constructor when callback effects are needed.

## Compatibility and backend scope

Language remains 0.28, checked program format 16 and task ABI 7. The name list was
already reserved, so this adds no conflicting user identifier or changed meaning
to a previously valid source program. Older compiler builds need not implement
it merely because they also advertise language 0.28: query the constructor field.
The new operation is not enabled in retained earlier source-language versions.
There is no automatic graph/version migration or dependency-lock update.

The reference engine, native backend and TypeScript use the checked expansion.
CUDA/Metal/Wasm constructor lowering is pending; existing narrower GPU/list
capabilities do not imply this new operation is supported there. The native
runtime reuses existing private list allocation/append calls; no C/task ABI is
added. Complete matching SDK/platform/device qualification is a separate gate.

The [examples](../examples/list-construction/README.md) materialize the exact
source/expected output used in the value, effect and task agreement cases.
Construction also has checks for lexical shadowing, Result callback boundaries,
existing graph IDs and partial-buffer retirement on fatal/task-budget exits.
Native profiling checks managed allocation/free balances; it is not a sanitizer
or a claim about unmeasured backing-vector bytes/RSS. Deferred optional checks
remain under the separate [user instruction](deferred-checks.ru.md).
