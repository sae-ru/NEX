A dedicated private native task experiment now implements compiled handlers and
physical scheduler delivery. See source-exception-native-tasks.md. The lower-level
stage described below retains its original scope; public025/SDK support is pending.

The private TaskIR machine additionally executes this source under the shared
serial coordinator. See source-exception-task-ir.md for explicit instructions,
cleanup and its boundary from compiled native task execution and physical workers.

# Private source exceptions in cooperative tasks

Public language remains0.24. This is a separate compiler-private checked-AST
experiment selected by parseSourceExceptionTasksPrototype. It preserves the
0.25-prototype identity and sets the existing checked task frontend flag. A
manifest cannot select it. The sequential exception parser keeps its original
pure/io/throw boundary. Public projects, archival and explicit025 migration
remain unavailable; no SDK or production platform support is claimed.

The private task parser permits pure/io/task/throw functions and task/throw
callbacks. The existing task callback IO restrictions remain. Files, opaque
resources and FFI are separate pending integration. The independent AST machine
and evaluateTaskReference scheduler implement this experiment. The dedicated
emitSourceExceptionTasksPrototypeTypeScript entry point now emits resumable
TypeScript functions with private operation maps. Native TaskIR, workers and publication remain unfinished. Bounded handler-aware
lifetime analysis is described in source-exception-lifetimes.md. Sequential native/TypeScript
emitters continue to reject task mode.

```nex
module task_error;
fn main()->i64 !{task,throw}{
 return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
  let child:task<i64>=task_spawn(scope,fn()->i64 !{task,throw}{
   task_yield();throw("INPUT","invalid value");
  });
  try{return task_wait(child);}
  catch(code,message){return 42;}
 });
}
```

A source throw follows the checked lexical handler stack across direct and
indirect calls and suspension. The AST machine removes pending inner actions,
partially evaluated values, match state and lexical scopes before entering the
handler. It preserves previous assignments to outer variables and captured
immutable values. Catch/rethrow state is local to a function frame; it does not
leak into another lambda or function. Rethrow keeps the original code/message
and Span, including embedded NUL/Unicode strings. Handling is iterative rather
than recursively restarting the AST evaluator.

A failed child stores a distinct immutable source error alongside its future.
It does not cancel siblings immediately while the body is running. task_wait
marks the future observed and delivers its source error through the waiting
machine's source-error channel. The current handler may recover, wait again
(repeating that same error), or spawn replacement work. A source error is not a
normal result value and does not become a runtime/control trap.

On normal group close, the coordinator selects the first completed, unobserved
source-error member in creation order at that close poll. It cancels remaining
members and joins their completion before delivering the error to the owner of
with_tasks. The selected member can depend on scheduling when completions race;
this is not a promise of global wall-clock error ordering. A body source error
is retained ahead of unobserved child source errors and similarly cancels/joins
children before reaching the caller's handler. Existing Result error returns
keep their abort/return behavior. Observed source errors do not resurface at
normal group close. A body waiting indefinitely on unrelated work still follows
the scheduler's existing deadlock/cycle rules; source errors are not supervisor
signals outside explicit wait/close boundaries.

Checked runtime errors remain distinct and do not enter source catches. Already
produced child runtime failures take precedence over a group source error;
cleanup cancellation cannot replace that source error. Parent cancellation,
resource exhaustion, deadlines and shared work limits retain priority through
drain. The reference experiment inherits the original RequestScope budget,
deadline and cancellation without creating a replacement request or file grant.

Because task<T> currently does not encode a latent error effect, private
source-exception task_wait and with_tasks conservatively require the current
function's throw effect or a lexical try. task_spawn defers its callback's throw
effect until wait/close. Ordinary task/realm/type requirements still apply. A
handler in the spawning function does not implicitly handle code inside a child;
the callback declares throw, or handles it within its own lexical try.

The TypeScript experiment uses the existing event-loop driver with an explicit
runSourceExceptionPrototype entry. Its source classifier belongs to that driver;
there is no ambient registration shared between simultaneous roots. Public run()
keeps its existing host-error path. The private host selects the unexported class
in nex-source-exception-runtime.ts by calling details(error), not by matching
code/message fields or treating NexError as a source exception. A user code such
as E_LIMIT remains ordinary source data when explicitly thrown.

Each future retains its original branded error separately from normal values
and runtime failures. Completion injects it into the suspended generator through
iterator.throw. The generated lexical catch may recover, and rethrow keeps the
same immutable payload/site. Group activation and member source errors follow
the reference close/cancel/join and precedence rules above. All source and
control exits close delegated generators and execute the existing finally/leave
boundaries. Options, deadlines and cancellation belong to the original root;
with_tasks creates an activation in that same driver, never a fresh execution.

Ordinary functional receipts compare generated TypeScript with independent AST
tasks, use the exact pinned TypeScript compiler for strict checking, and check
zero retained frames/calls/host operations at completion. Separate concurrent
private/public root, host-error, AbortSignal and deadline cases exercise the
per-driver boundary. This is Node execution, not production browser, physical
worker, native-task, public SDK or migration acceptance. npm pins, lock and
third-party dependencies are unchanged; the maintained NEX task runtime itself
contains the explicit private source-error mode.

Required before publication: handler-aware native TaskIR/frame/scheduler and
full current TypeScript/runtime/browser/SDK acceptance, complete region/lifetime inference, native
worker/control/retirement integration, file/resource/FFI/binary boundaries,
debug/profile support, explicit history-preserving025 migration, complete
compiler/SDK/browser/platform acceptance and the broader original project goal.
Security audits/sanitizers/fuzzing remain deferred by the user.

The shared analyzeTaskLifetimes pass now analyzes exceptional states for this
private mode. See [source-exception-lifetimes.md](source-exception-lifetimes.md);
this does not establish complete region inference or native task execution.
