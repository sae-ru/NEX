---
status: current
applies_to: "toolchain 0.172; language 0.28"
owner: repository
---

# Sequential immutable byte construction

Discover `bytes_construction` in the selected compiler. Toolchain 0.172 adds
these four forms to the already reserved builtin name `bytes`:

```nex
bytes(count, make)                     // make(index) -> i64 octet, index 0..count-1
bytes(values, transform)               // transform once for each element
bytes(values, predicate, transform)    // transform only selected elements
bytes(count, initial, next, emit)      // emit(state) -> i64 octet, then advance
```

The one-argument `bytes(list<i64>) -> result<bytes>` conversion keeps its
existing meaning, including recoverable `E_RANGE` for an invalid octet. Two to
four arguments select the constructor, whose emitted octets must be in `0..255`;
an out-of-range octet is a fatal `E_RANGE`, matching `push(bytes, octet)`. No new
keyword, type or grammar production is introduced.

All arguments are evaluated once, left-to-right before count validation or any
callback. Generation counts are checked i64 values; a negative count is fatal
`E_ASSERT`. Zero produces empty bytes without calling make/next/emit or the
transform. Mapping and filtering visit the input in order; the filtered form
calls predicate once per input, then transform once if true. The stateful form
calls emit exactly count times and next exactly max(0,count-1) times; the first
emission uses initial and the final state is never advanced. State must be
non-unit; each callback takes exactly one argument. Transform and emit return
`i64`; predicate returns `bool`; next returns the state type.

```nex
module example;
fn main() -> unit !{io} {
  let header: bytes = bytes(4, fn(i:i64)->i64 { return i; });
  let selected: bytes = bytes([0,1,2,3],
    fn(x:i64)->bool { return x%2==0; },
    fn(x:i64)->i64 { return x+10; });
  assert(len(header)==4 && header[0]==0 && header[3]==3);
  assert(len(selected)==2 && selected[0]==10 && selected[1]==12);
}
```

## Effects, tasks and ownership

The constructor infers the union of its callback effects. The caller must allow
that union under ordinary effect/handler rules, and each callback must be callable
from the caller's realm. Typed/legacy source errors escape at the failing item;
later callbacks do not execute. Normal finally behavior is unchanged. Fatal
traps and request cancellation retain their existing cleanup/control rules.
Callbacks may suspend through the existing task machinery; the constructor
creates no task scope, workers, host authority or parallel execution.

Input lists and aliases stay unchanged. Construction does not deep-copy
resources or grant new lifetimes. Task/resource-bearing outputs remain subject to
the normal static and runtime owner checks.

## Construction model and cost

The frontend lowers construction into an ordinary checked closure and loop. It
appends each emitted octet to an unpublished private `list<i64>` accumulator using
the same compiler-private append operation as the list constructor. One final
`$bytes_finish` operation validates all octets once and publishes a single
immutable byte buffer. Source cannot name these operations or access the buffer.
Internal len/assert calls bind to their compiler builtins even when caller locals
shadow those names; callbacks keep their original lexical bindings.

For `k` emitted octets, construction performs one loop iteration per input/count,
one amortized append per octet and one final conversion: O(iterations + k) work,
excluding callbacks, comparisons, state and piece construction. It does not build
an intermediate list visible to source and does not repeatedly copy a growing
prefix.

Native output uses one new private runtime symbol, `nex_bytes_from_octets` (and
its source-site variant). The public C ABI major and the source language version
are unchanged. TypeScript validates and freezes the same unpublished array once;
the reference interpreter performs the same single-pass conversion.

## Limits and pending work

GPU (Metal/CUDA) and scalar Wasm do not lower this heap constructor; their
existing unsupported-type diagnostics remain. Wider containers, named
source-library effect parameters, and measured runtime benchmarks remain pending.
A failed construction releases its partial private buffer on normal, source-error
and fatal native exits through the ordinary owned-value cleanup.

[Recorded 0.172 validation](evidence/bytes-construction-0.172.0-2026-11-11.json)
pins the compiler, source commit, focused test scope, retained corrections and
remaining limits.
