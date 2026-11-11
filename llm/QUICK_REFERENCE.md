# NEX 0.28: bounded source reference

First query `nex describe --kind index --json`. Preserve the project's declared
language and graph history. This sheet describes0.28; the specification/grammar
and the selected compiler decide support. Retrieve it once, then request a
feature guide only for a concrete uncertainty. For a rejection, use the code,
message and byte location; `nex explain CODE --json` gives bounded builtin advice.

## Syntax to copy

```nex
module example;
fn identity<T>(value:T)->T { return value; }
fn main()->unit !{io} {
  var index:i64=0;
  while index<4 { index=index+1; }
  let original:list<i64>=[3,5];
  let changed:list<i64>=set(original,0,9);
  assert(original[0]==3 && changed[0]==9);
  let text:str="xЯ🌍";
  assert(len(text)==3 && slice(text,1,1)=="Я");
  let value:result<i64>=ok(identity<i64>(index));
  print(unwrap(value));
}
```

- Each source file has one `module name;`. Functions use explicit parameter and
  result types. Use `return value;` on every normal path of a non-unit function.
- `let` and parameters are immutable. `var` permits reassignment with
  `name=expression;`. There is no `+=`, `++`, `let mut`, `:=` or Python block
  syntax. Use `while` for ordinary loops.
- `var` does not make aggregates mutable. `set`, `push` and `slice` produce new
  values. Reassign a `var` to keep an update; old aliases/captures stay snapshots.
- If `list_construction` is advertised, use `list(3,fn(i:i64)->i64{return i*i;})` or
  `list(values,transform)` for sequential bulk construction; callbacks retain
  their effects. See `nex guide --kind list-build`.
- If `text_construction` is advertised, `str(count,fn(i:i64)->str{...})`,
  `str(values,transform)`, filtered and state/next/emit forms build text
  sequentially; one-argument `str(value)` still formats. See
  `nex guide --kind text-construction`.
- If `bytes_construction` is advertised, `bytes(count,fn(i:i64)->i64{...})`,
  `bytes(values,transform)`, filtered and state/next/emit forms build bytes
  linearly; one-argument `bytes(list<i64>)` remains `result<bytes>`, and an
  octet outside 0..255 traps `E_RANGE`. See `nex guide --kind bytes-construction`.
- Strings are strict UTF-8. `len(text)`, `text[index]` and
  `slice(text,start,count)` use Unicode scalars; the third slice argument is a
  **count**, not an end index. Scalars are not grapheme clusters. Bytes preserve
  arbitrary octets; `decode_utf8` returns `result<str>`.
- Arithmetic is checked; no implicit bool/numeric conversion or wrapping.
  Expressions evaluate left-to-right once, boolean branches short-circuit.

## Types, imports and outcomes

Scalar types are `i64`, finite `f64`, `bool`, `str`, `bytes`; `unit` is a result
type, not an ordinary parameter/local/collection element. Values include
`list<T>`, `result<T>`, records, enums and checked callable types.

Import with `import "./values.nex" as values;` and call `values::identity<i64>(4)`.
The other file must declare its own distinct module and a `pub fn identity`.
An interface edit must update its signature, implementation and **all callers**.
Generic operations require their actual bounds; `+` on an unconstrained `T`
is invalid. Associated projections do not automatically infer their Self type.
Use the trait guide for constructors/associated types instead of inventing syntax.

An enum case is constructed with `Type::Case(...)`, including `Empty()`.
Statement match arms have blocks; expression arms produce one common type.
Do not mix those two arm forms. Match is ordered, exhaustive and evaluates its
subject once; retrieve the match guide for nested patterns/guards.

`ok(value)` / `err<T>(code,message)` make ordinary result values. Handle them
with `match`, `is_ok` or `?`; postfix `?` needs a result-returning current function.
`unwrap` on an error is a fatal `E_RESULT`, not a source error caught by try/catch.

Typed source errors use `throw(value)`, `catch(error:Type)` and optional `finally`
with declared `throw` effects. Matching uses the complete concrete type.
Finally runs for normal/source-error/return/Result outcomes; fatal checked traps,
cancellation and deadlines skip user finally while runtime-owned cleanup remains.

## Effects and tasks

Declare required effects after the result: `!{io}`, `!{task,throw}`, etc.
Declarations do not grant filesystem/network/foreign authority. Shared/client/
server boundaries still apply; browser clients must not contain server code.

Source task primitives are `with_tasks`, `task_spawn`, `task_wait`, `task_yield`
and the advertised channel operations. There are no async/await/spawn keywords.
Scope/spawn/wait can deliver source errors: declare `throw` alongside `task`
or handle them in a lexical try; task callbacks must retain matching effects.
Keep futures/channels inside their genuine owner scope. Structured tasks do not
mean every source expression runs on a separate CPU thread; `parallel_map` is a
separate explicit CPU batch operation. Query `structured_tasks_runtime` and
`source_concurrency` before composing IO or parallel callbacks.

The runnable [multi-module example](../examples/llm-quick/nex.json) combines
immutability, scalar strings, generics, enums, typed catch/finally and a joined
yielding child. From that directory use `nex check`, `nex test`, `nex eval` and
`nex run --profile release`. Reference/native/TypeScript observations and source
rejections must be checked separately; producing code is not acceptance.

For0.28 source clauses query `source_contracts` and its guide before using
requires/ensures/invariant/decreases. Runtime checks are distinct from bounded
proof. Keep unknown integrations pending. This sheet does not establish LLM
token savings; retain the published negative Qwen study when improving it.

If `standard_library` is advertised, query it before writing text/list/math
helpers. Import `std/list.nex` as `seq`/`lists`; `list` is reserved. The `stdlib`
guide defines Unicode/empty cases, pure callbacks, stable sort and copy costs.
Review dependency changes and update existing pins explicitly with `nex lock`.
