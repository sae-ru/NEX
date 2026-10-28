# Result propagation (language0.17 candidate)

Postfix `?` removes repeated result forwarding while preserving typed errors:

```nex
fn display(text:str)->result<str> {
  let value:i64 = decode_json<i64>(text)?;
  return ok("value=" + str(value));
}
```

The operand is a `result<T>`. A success produces T. A failure immediately
returns its original code/message from the **current function**, which must
return `result<U>`; T and U can differ. Lambdas have their own return boundary.
The operator evaluates once, at the same postfix precedence as indexing/calls.
Parentheses can make a mixed expression clearer. No new identifier is reserved.

Operands, arguments and collection members keep their left-to-right order;
short-circuit operators still skip the unused side. Effects already performed
remain, and later operands do not execute. Native early exits clean named locals,
prior arguments and partially constructed values, preserving the returned value
and borrowed caller values. This includes opaque file aliases. It grants no
effect or realm permission, and does not reset budgets. Function owner depth is
bounded to4096 in the native backend; existing interpreter limits still apply.

`?` does not handle arithmetic, bounds, assertion, cancellation or limit traps.
Those retain their checked failure behavior. `unwrap(error)` still traps with
E_RESULT. Source `try/catch/throw`, arbitrary exception recovery and structured
error payloads beyond code/message remain pending. Handle a recoverable error
explicitly with result patterns when a fallback or translation is needed.

Generic bodies are checked even when unused. Applying `?` to a non-result is
E_TYPE; using it in a function without a result return is E_RESULT_RETURN.
An unexecuted top-level watch cannot return from a stopped function and rejects
`?` with E_DEBUG_RETURN. A pure helper or lambda invoked by that watch can use
its own result boundary. Scalar verification and the scalar Wasm subset remain
outside this operation's scope. Checked trap exceptions are never converted to
result failures by the generated TypeScript boundary.

## Migration and preservation

This isolated development compiler reports language0.17. Do not change an old
project's version field to bypass E_LANGUAGE_VERSION. Preserve its matching
SDK0.81, source, application data and full graph snapshot. With that SDK export
the genuine0.16 graph; use the new compiler's explicit `migrate` to recheck its
archived source. Migration creates a current-language revision while preserving
historical revisions, rows and persistent IDs. Validate `--revision HEAD` and
export to a new project directory; migration does not rewrite physical source.
The new expression appends AST kind15. Existing kind ordinals and canonical
function/13, structure/5, enum/4 and program/14 formats stay unchanged; the program
identity includes language0.17. Old artifacts still require their matching SDK.

The0.16 fixture in tests/fixtures was produced by the actual approved SDK0.81,
with native/reference and TypeScript tests, before this extension. Its SQL and
metadata hashes are checked before migration tests. Existing older fixtures are
retained byte-for-byte. Complete regression, platform, installed SDK and editor
gates remain required; this document does not claim release acceptance or parity
with C++/Python. See [quality criteria](quality.md).
