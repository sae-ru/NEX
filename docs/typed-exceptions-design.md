# Typed source errors: transport foundation and remaining language work

Toolchain0.140.0 keeps public language0.26 and `typed_payloads: false`.
There is no typed throw/catch source syntax in this compiler. The development
field `source_exceptions.typed_payload_development` describes internal C++
transport only. This document distinguishes that implementation from the
proposed language0.27 design below.

## Implemented foundation

Reference `SourceException` and native `NativeSourceException` can retain one
shared immutable `SourceErrorPayload`. Its value uses ordinary owned `Value`
semantics: copies retain the complete value, rather than a pointer into a dead
function frame. Replacing/discarding the final packet releases that ownership.
The packet retains the original code/message and source location. Fatal errors
are still a separate class; a code string does not select the control category.
A value alone grants no filesystem, module, task or device authority.

The compiler computes `nex.source-error-type/1` SHA256 identities from concrete
types, complete nominal layouts, generic/phantom arguments, constructor arities
and callable realm/effects. Unrelated declarations and physical source paths do
not participate. Module qualification is normalized between checked standalone
source and module loading. Unresolved type variables/projections are rejected;
recursive nominal context uses a visited set and bounded traversal.

The digest identifies a type contract; it is not proof that arbitrary host data
conforms to that type. A checked producer or a validating foreign boundary must
establish that separately. The packet constructor checks key format and basic
Value validity without walking/stringifying the entire aggregate on each throw.
The future generated handler must validate its expected kind as well as the key.

The published88-byte ABI6 task descriptor, C foreign-module ABI and ordinary026
source semantics remain unchanged. The internal C++ exception layout is covered
by the existing runtime-cohort hash, which includes `nex_source_error.h`; it is
not a binary-compatible host exception interface across different runtime builds.
No typed source delivery or mixed old/new runtime claim follows from this work.
Retrieve the bounded contract with `nex guide --kind typed-exception --json`.

Tests exercise nested and phantom layouts, higher-kinded arguments, exact type
mismatch, failed construction cleanup, reference/native copies, exception_ptr
handoff across a real thread, and repeated observation through the actual task
scheduler. They require final destruction and zero retained managed objects.

## Proposed027 source contract: not enabled

A typed raise should evaluate its one operand exactly once:

```nex
throw(LoadError::Missing(path));
```

A typed catch should bind the original value with its concrete type:

```nex
try { perform_load(); }
catch(error:LoadError) if recoverable(error) { handle(error); }
catch(code,message) { handle_other(code,message); }
finally { release_local_state(); }
```

Keep the026 two-string raise, two-binding catch, lexical bare rethrow, filtered
handlers and finally. A typed clause matches its complete concrete type key;
an unmatched/declined clause proceeds to the next clause with the original
packet. A new error from a predicate/handler escapes the whole handler chain.
An unguarded two-string handler remains the universal source-error handler.
A bare rethrow preserves typed value and source site; constructing a new legacy
error intentionally replaces the packet. Result `?` remains a function return.

A typed raise can project a stable type name and generic message to a legacy
catch; the payload must not be implicitly formatted or exposed by HTTP/worker
transport. Only an explicit typed binding exposes the value. Typed filters do
not handle fatal control, and a typed-only handler is not automatically total
for a call with the existing coarse `throw` effect. Precise typed effect rows
belong to the wider effects work; do not infer them from payload support.

## Required before enabling027

- Add version-selected syntax/checking and append semantic AST forms without
  changing retained026 canonical fields or statement ordinals.
- Implement ordered handler clauses, exact typed matching and left-to-right
  operand evaluation in the reference, native, TaskIR/AST and TypeScript engines.
- Carry the same owned value through synchronous native packets, suspension,
  finally outcome replacement, foreign/pure calls and module boundaries.
- Extend lifetime/source-edge analysis to carry payload provenance. Resource,
  closure, file and task authority still require real realm/owner-transfer checks;
  merely retaining a Value must never promote a capability out of its region.
- Define matching task/provider/runtime protocol pins, reject incompatible
  cohorts before execution and preserve existing public/private ABI meanings.
- Keep HTTP/worker failures generic; add bounded debugger/profile views without
  an implicit data leak or execution of source callbacks.
- Implement explicit026-to027 migration using the genuine026 fixture at
  `tests/fixtures/language-0.26-typed-origin.*` (actual0.139.0 compiler, two
  reference revisions plus native Debug/Release);
  preserve every old graph row/schema/local ID and append the checked revision.
- Reconcile specification/grammar/capability pack/LLM contract/examples and pass
  actual engine agreement, rejected programs, cleanup, SDK and platform gates.

Task-finally0.139 acceptance has its own frozen compiler/source receipts. It does
not certify this foundation or future027 behavior. The original full NEX language,
platform, tooling and accelerator plan remains active.
