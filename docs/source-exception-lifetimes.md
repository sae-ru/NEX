A dedicated private native task experiment now implements compiled handlers and
physical scheduler delivery. See source-exception-native-tasks.md. The lower-level
stage described below retains its original scope; public025/SDK support is pending.

The private TaskIR machine now consumes this checked source; see
source-exception-task-ir.md. Compiled native TaskGroup integration remains pending.

# Task lifetime flow through source exceptions

This development extends analyzeTaskLifetimes for the compiler-private
parseSourceExceptionTasksPrototype language. Public language stays0.24; native
task exceptions, public025 publication and explicit migration remain unfinished.
The shared authority model still applies to retained task source. Existing public
report serializers remain unchanged; private counters additionally expose
handlers, exceptionalEdges and exceptionalJoins.

The pass is bounded abstract source analysis, not source execution. Binding
identity is separate from a variable's spelling and current value. Lexical
shadowing changes the visible name mapping while preserving hidden outer
bindings. Scope exit restores names without reverting earlier assignments to
those outer bindings. Immutable closure captures keep their original value
provenance even when a source variable is reassigned later.

Each try installs an exceptional-input collector with the bindings alive at
that point. Explicit throw/rethrow, a throwing direct/indirect call and the
conservative task_wait/with_tasks error contracts contribute projected states.
Only active bindings from the handler's baseline survive projection; inner
locals and temporary match bindings do not become catch variables. All possible
exceptional states are joined before analyzing the handler. The normal end state
of a try body cannot replace an earlier state at a throw point. A handler runs
under the outer handler context, so a rethrow captures mutations made in that
handler. Catch strings are fresh plain bindings, including when their names
shadow authority-bearing outer variables.

Function analysis owns its handler stack. A callee's uncaught source-error
outcome contributes the caller's current state, not the callee's locals. A
callee's own catch does not act as a dynamically inherited caller handler.
Spawning analyzes captures and possible task return values but defers child
source-error delivery to wait/close. Unknown callable effects retain explicit
opaque/dynamic obligations. task<T> does not acquire a new source type encoding.

Normal and exceptional outcomes are distinct. An expression proven to always
raise has no normal value; later arguments/initializers and unreachable
continuations are not treated as executed. Short-circuiting, match arms and
branch joins retain normal paths only. Returns still contribute their value
provenance to the enclosing function. Error payloads are code/message strings,
so they carry no task authority. Ordinary Result `?` remains a return operation,
not a source-exception edge; where its payload is unknown, the pass conservatively
retains the existing runtime obligations.

Loops retain bounded analysis and widening. After widening loop-carried state,
the body is traversed again so exceptional collectors see the widened state,
rather than claiming that two finite samples prove the loop. Recursion, opaque
projections/calls, widening and analysis-budget exhaustion remain incomplete
static knowledge. They never permit removal of mandatory runtime snapshot/owner
checks. Existing region/ancestor transfer rules diagnose E_TASK_LIFETIME for a
statically known capability that may outlive its owner; runtime E_TASK_SCOPE
continues to enforce actual transfers independently.

The ordinary conformance probe covers prefix mutation vs repair, hidden and
catch-shadowed bindings, rethrow, immutable captures, indirect/function-boundary
errors, wait/group-close errors, terminating operands, loop-carried states,
opaque calls and exhaustion. Rejected examples are also run in the independent
reference scheduler to confirm the actual scope violation; accepted examples
retain observable results and release values. Shared sequential/task exception
fixtures and the retained lifetime suite verify compatibility. This is compiler
functional validation; user-deferred security campaigns remain off.

Still pending: complete region/lifetime inference, native TaskIR/frame/scheduler
source errors, physical worker and file/resource/FFI/binary integration,
debug/profile/cache/library/SDK/browser acceptance and history-preserving025
migration, along with the original broader language/toolchain/Studio goals.
