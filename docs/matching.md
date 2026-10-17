# Matching — language 0.9

`match` evaluates one value once, then tries arms in source order. A pattern
selects and binds immutable data. An optional boolean guard runs after a pattern
has matched. The first accepted arm executes; later guards/bodies do not run.

```nex
fn parse_number(value:result<i64>) -> i64 {
  return match value {
    ok(n) if n > 0 => n,
    ok(_) => 0,
    err("MISSING", _) => 0,
    err(code, message) => -1,
  };
}
```

Value arms are expressions with one common type. A declaration, return or call
can supply that type; otherwise an inferable arm supplies it (including an empty
list in another arm). Unit-valued matches are valid. To execute statements use
block arms, for example `match value { ok(n) => { print(n); }, err(_,_) => {} }`.
Block matches need no trailing semicolon. Expression statements do. Do not mix
the two arm forms. Block-valued expression arms are not implemented. Ordinary match(...) calls, qualified names and indexed locals named match keep their scrutinee meaning; parenthesize an ambiguous nested match expression.

## Patterns

| Pattern | Meaning |
|---|---|
| `_` | Any value, with no binding or payload demand |
| `name` | Any value, bound immutably within this arm |
| `0`, `-1`, `true`, `"text"` | Exact i64/bool/string value, including strict Unicode/NUL text |
| `Maybe::Some(pattern)` | Declared enum case and recursively matched payload |
| `ok(pattern)` | Successful builtin result |
| `err(code_pattern, message_pattern)` | Failed result; both children have type str |
| `Pair(left_pattern, right_pattern)` | Positional declared structure fields |
| `[]`, `[first, second]` | Exact list length and recursively matched elements |

Constructor arity and nominal identity are checked before execution. Imported
constructors use their existing alias, such as `model::Maybe::Some(n)`. Generic
constructor patterns omit type arguments; the subject supplies them. An opaque
generic parameter permits bindings/wildcards; integer-constrained parameters
also permit integer literals. Bounds introduce no implicit type conversion.

Each named binding can appear only once per arm. An arm may shadow an outer
name. The binding is visible in its guard and body/value, then leaves scope.
Assignments to it fail. `_` introduces no variable. Constructor/record/list
children are checked left to right; an earlier mismatch skips later tests.

## Coverage and guards

Every match must cover every value of its checked subject type. Earlier
unguarded patterns also make subsumed later arms an error. The analysis handles
nested products and enum/result alternatives, including boolean payloads; it
does not just count outer tags. Finite integer/string literals or list lengths
cannot cover their entire domain, so retain an unguarded fallback where needed.

Guards do not establish coverage, even when their expression is `true`.
Overlapping guarded arms remain meaningful and execute in order. Guard effects
and realm dependencies must be declared by the containing function, including
when a current constant would prevent execution. A statement match returns on
all paths only if every arm body returns. Invalid coverage produces
`E_MATCH_EXHAUSTIVE`; a subsumed arm produces `E_MATCH_DUPLICATE`.

The implementation specializes a typed pattern matrix and its default rows,
with explicit resource limits; see the primary description of the
[useful-clause formulation](https://pauillac.inria.fr/~maranget/papers/warn/warn004.html).
No user code or guard is executed by coverage analysis.

Limits: 4096 arms, 10,000 pattern nodes per match, pattern depth 64, 1024 children
per constructor/list pattern, 100,000 coverage states and coverage recursion 128.
Exceeding a limit gives `E_MATCH_LIMIT`. Watch token/value budgets also apply.
OR/range/rest patterns and user-defined extractors remain pending.

## Native, browser and debugger behavior

All backends preserve the single subject evaluation and guard order. Native
temporaries and bindings own their handles; failed tests/guards, normal arm
completion, loop iterations and returns release them. Returned managed values
retain their selected payload independently. Runtime traps still reach the
existing standalone/request boundary and its cleanup.

TypeScript uses checked operations and frozen values, and includes only the
reachable client/shared closure. Matching adds no browser dependency. The
reference interpreter is the behavioral oracle, not the browser/native runtime.

Pure watches accept match expressions and helpers containing matches. Planning
reports free stopped-frame inputs, excluding arm-local bindings. Partial reads
select needed enum/result tags, list lengths and tested/used fields; discarded
payloads remain unread. Whole-string comparisons retain the bounded exact-string
rules. Effectful guards are rejected in watches. No code runs in the inferior.

Canonical function/7 and program/8 definitions include typed patterns, guard/value
indices and bodies. Operation graphs record pattern declarations and references.
Simple legacy enum match paths are retained during explicit 0.8→0.9 migration;
historical sources/IDs remain archived. Preserve the 0.21 compiler/resources for
old frames/receipts and regenerate task/proof pins without weakening intent.

See `examples/matching.nex`; run `nex test` and `nex test --target web`, then use
the debug/expression guides for actual LLDB/DAP checks.
