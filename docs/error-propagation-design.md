# Historical0.88/language0.16 runtime-stage design

This journal records the completed native ownership groundwork before source
integration. The current language0.17 candidate contract is
[error-propagation.md](error-propagation.md); statements below describe that
earlier0.16 stage and its required next steps.

## Planned source operation

Postfix `value?` should evaluate `result<T>` exactly once: return its successful
payload to the surrounding expression, or immediately return the unchanged
error code/message from the **current function**, whose return type must be
`result<U>`. It must work in nested arguments, aggregate construction, closure
bodies, branches, short-circuit operands and match arms/guards. Earlier
expressions retain their effects; later operands do not execute after propagation.
An error is not a successful payload of another type. No arithmetic/bounds trap,
cancellation or resource limit becomes a recoverable result through this operator.

The postfix spelling reserves no ordinary identifier. Checker diagnostics must
reject a non-result operand, a non-result enclosing function and invalid generic,
effect or realm uses. Lifted closures use their own return type, not their owner's.
Watch expressions and scalar proofs need explicit checked rules; a new operator
must never fall through existing unary-negation implementations.

## Native ownership groundwork

Existing native code releases named locals on a return. A propagation point can
also abandon unfinished expressions: preceding arguments, a partly built list
or constructor, or captures in a partly built closure. Correct cleanup therefore
needs an ownership boundary for the whole function, including these temporaries.

The0.88 draft adds compiler-private `nex_owned_enter/leave` helpers. They require
an existing ApplicationScope/RequestScope. A thread-local intrusive owner retains
only handles allocated after entry; it moves a kept return handle to the parent
and deletes every other temporary on exit. Caller handles remain borrowed. The
existing Handle layout is reused: there is no added per-handle field/registry.
Owner frames are reused by depth; exit/unwind allocate nothing. Distinct monotonic
tokens reject stale, out-of-order and cross-thread exits. Exits must occur in the
same request/application context as entry. Depth is bounded to4096; exhausted
signed64-bit token identities fail instead of wrapping. These are prototype
runtime limits, not yet a source-language contract.

Application/request failure cleanup unwinds only frames created inside that
boundary, before deleting remaining handles. Normal runtime finish still rejects
unbalanced function owners and caller leaks. Worker request scopes clean abandoned
function owners per job. The helpers add no I/O/FFI grants or renewed budget.
Ordinary generated functions do not call these helpers until backend integration.

## Required integration before support

1. Implement parsing, checking, generic specialization and canonical/source/graph
   operation coverage. Set the actual language version to0.17 only when coherent;
   keep genuine0.16 source/export/store fixtures and a matching old SDK.
2. In the interpreter, propagate failure to the nearest function's return path
   with automatic temporary/frame cleanup and unchanged left-to-right order.
3. Native functions containing propagation open one owner. All normal returns
   and failure branches close it, preserving the actual return handle. Success
   unwraps before releasing its result operand. A failure result has no typed
   success payload, so its retained error value can be returned as result<U>.
4. TypeScript needs a private propagation sentinel caught only by that source
   function's result boundary. Checked runtime traps must be rethrown. Preserve
   generated source mappings, lifted closures and realm-reachable browser code.
5. Reject unsupported proof/watch uses explicitly; coordinate specification,
   grammar, capability descriptor, language pack, prompts, examples and migration.
6. Test successes/errors at every expression position, side effects/order,
   short-circuiting, nested calls/closures, typed results and invalid programs.
   Check native/TypeScript/interpreter agreement, all cleanup exits, real files,
   profiles, SDKs and supported platforms. This journal is not proof of completion.
