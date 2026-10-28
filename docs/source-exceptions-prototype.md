# Private source exception prototype

The public language remains0.24. `nex check`, project manifests and stored
revisions do not enable this syntax. The compiler-private C++ entry point
parseSourceExceptionsPrototype selects the distinct0.25-prototype identity
before checking. There is no public025 migration or executable SDK support. Private checked traps retain their
original diagnostic/span without attempting an archival revision lookup.

The intended language extension adds explicitly raised user errors and a
throw effect. Ordinary Result values and postfix `?` retain their meaning.

```nex
module sample;
fn read_number()->i64 !{throw}{throw("INPUT","expected a number");}
fn main()->i64{
 try{return read_number();}
 catch(code,message){return 42;}
}
```

`throw(code,message);` evaluates two str expressions once, left to right, and
terminates the current path. A catch-all `catch(code,message)` binds two immutable
strings, preserving every Unicode scalar including U+0000. The binding scope is the handler; ordinary shadowing and snapshot
captures apply. `throw;` is a lexical rethrow in the current function's catch,
preserving the original code/message/source span. A new throw in a handler has
its own payload and source. There is no dynamic inherited catch context in a
nested lambda or another function.

A throw or a call with effect throw requires that effect on its current function,
unless a lexical try body in that function handles it. Handlers do not inherit
their own try body's effect allowance; a new throw/rethrow must be handled by
an outer try or declared. Lambdas and named functions establish independent
effect boundaries. A try statement terminates every normal path only when both
its body and handler do. Statements after an unconditional throw are rejected.

Only the separate SourceException class enters these handlers. Arithmetic,
bounds/assertion failures, execution budgets, cancellation, allocation failure
and host/runtime traps keep their existing behavior. A Result error is data;
`?` still returns from the current function and never enters a source catch.
The reference implementation uses RAII to drop lexical and match-arm values
before handler entry, including early return and exceptional exits.

Current implementation includes a private sequential frontend, independent
reference evaluator and dedicated experimental native emitter for pure/io/throw
functions. Generic calls, exact callable effects, captures and nested handlers
participate. Dedicated experimental TypeScript emission now shares the sequential semantics.
Public native/TypeScript builds and Wasm still reject the private identity. Discovery continues to report source_support:false and native:false;
private_native_sequential_experiment and private_typescript_sequential_experiment
describe the separate C++ experiments.
Parallel_map is rejected at these experimental native/TypeScript boundaries until worker/runtime
exception integration is implemented; ordinary public024 support is unchanged.
No checked trap is reclassified as an ordinary exception.

emitSourceExceptionsPrototypeMLIR adds a hidden error output pointer only to
functions/callable bridges with effect throw. Callers initialize the slot, invoke
once, release completed argument values and branch on the error. Normal values
keep their existing representation. Explicitly thrown errors contain immutable
length-preserving code/message strings and a copied original native source site.
Bare rethrow preserves this record. Only the application boundary reports an
uncaught source error as NEX_SOURCE_EXCEPTION JSON and exit70; it remains distinct
from NEX_NATIVE_TRAP.

Each private native function and try/handler body owns temporary handles.
An exceptional branch cleans its inner lexical slots and leaves the relevant
ownership frames before handler entry. Handles assigned to outer variables move
to those variables' enclosing owners, preserving earlier assignments and escaped
snapshot captures. Normal returns, Result `?`, nested rethrows and partially
evaluated expressions all leave their active frames. Source errors cross direct
and indirect generated calls through the explicit output slot; they do not use
C++ exception unwinding between NEX functions.

The private test host compiles real MLIR/LLVM, loads the generated native image
against the matching runtime and checks reference agreement at O0 and O2. This
is ordinary semantic validation, separate from public build/SDK acceptance and
from the user's deferred security campaigns.

emitSourceExceptionsPrototypeTypeScript emits only the reachable client/shared
closure, using a separate nex-source-exception-runtime.ts helper. Its unexported
SourceException class brands user errors. Catch guards inspect this identity;
NexError traps, host failures and the ResultPropagation sentinel are rethrown.
Throw payload expressions use ordinary left-to-right JavaScript argument
semantics. The helper freezes the payload and a copy of its original source site;
lexical rethrow uses the same error object. Catch bindings are immutable strings,
and existing snapshot captures preserve escaped values. The JavaScript engine
manages ordinary value reachability; source files/tasks/resources remain gated.

The dedicated writer copies the new helper only for private exception modules.
Normal024 modules and the existing runtime, npm pins, lock and third-party
notices retain their existing contract. Private source maps carry checked
canonical function/operation sites but no published graph revision. A private
map is not an archived revision or a public browser UI integration. Node execution
and strict checking against the repository's pinned TypeScript compiler are
ordinary functional evidence, separate from production browser/SDK acceptance.

Remaining required work before publication:

- Full native build/cache/library/SDK integration and platform acceptance of
  the experimental transport and owned cleanup, including debug/profile behavior.
- Structured task handlers/futures/drain and worker/runtime semantics, plus
  original request control; supported source/binary/FFI boundary rules.
- Resource/file cleanup receipts, debug/profile/source mapping, contracts and
  every relevant frontend/backend/generic/realm/effect integration.
- An explicit history-preserving024-to025 migration, retained parser/canonical
  identities and real original histories. Merely changing a manifest is invalid.
- Matching compiler regressions, installed/moved SDK and platform acceptance.

Full typed exception payloads, handler filters/finally and general algebraic
effect handlers are separate unfinished design work. This prototype does not
complete the language or the original development objective. Security campaigns
remain deferred by the user's request.

The separate private parseSourceExceptionTasksPrototype entry point now enables
checked-AST/reference task errors, waits and joined drain. Read
[source-exception-tasks-prototype.md](source-exception-tasks-prototype.md).
Native/TypeScript task continuation and lifetime integration are still pending.
