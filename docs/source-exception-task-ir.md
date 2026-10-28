A dedicated private native task experiment now implements compiled handlers and
physical scheduler delivery. See source-exception-native-tasks.md. The lower-level
stage described below retains its original scope; public025/SDK support is pending.

# Private exception-aware TaskIR

Toolchain0.135.15 extends the compiler-private0.25-prototype task experiment.
Public language remains0.24. This stage lowers and executes explicit TaskIR
instructions in a C++ semantic machine. It does not execute emitted native
machine code or physical source CPU workers. Ordinary evaluateTaskReference
continues to use checked AST actions and never selects TaskIR implicitly.

The dedicated evaluateSourceExceptionTaskIRPrototype entry uses TaskMachine
under the existing serial coordinator. Its scope/future/channel ownership,
observed-future state, close/cancel/join and root request control are therefore
shared coordinator mechanisms, not a second independent scheduler. AST and IR
control traversal, lexical cleanup and function calls are independent. Native
compiled-frame/scheduler integration and worker retirement remain required.

TaskInstruction appends PushHandler, PopHandler, Catch, EndCatch, Raise and
Rethrow after the retained instruction ordinals. PushHandler records a Catch PC,
the first slot allocated inside the try, and the current caught-error depth.
On a source error, the machine walks function frames iteratively. At the first
handler it drops slots allocated inside the try, restores caught-error depth and
enters Catch. Existing slots preserve previous outer assignments, hidden outer
bindings and enclosing match inputs. Normal paths explicitly pop their handler;
function return disposes the complete frame. Catch strings have their own slots.

Each caught error is a distinct immutable SourceException snapshot with full
code/message strings and original Span. Nested catches may suspend and rethrow
their own error; leaving an inner catch restores the outer caught error. Rethrow
preserves the original span rather than using the rethrow instruction's location.
Errors from a caller are delivered through a separate resumeSourceException
ticket channel, never as a normal Value. Invalid/duplicate tickets and private
source-error injection into a retained-language machine are rejected without
consuming a valid pending response.

Private mode lifts every direct and indirect source call into an explicit Call,
including pure helpers. No source function body hides inside an Eval atom.
Arguments and throw code/message operands run once, left to right; match and
short-circuit control remain explicit. Partial arguments and abandoned temporary
values are released during unwinding. Closure captures retain immutable value
snapshots. Result `?` remains an ordinary function return, not an exception edge.
Eval atoms retain the existing checked value operations. parallel_map workers
remain rejected by this private lowering stage.

The machine preserves the combined256 call-depth ceiling, bounded262144 retained
state entries, scheduler-tightened step budgets, inherited request cancellation
and deadlines. Control failures and checked traps bypass source catches. The
existing handler-aware lifetime pass and runtime owner checks remain mandatory;
this stage does not claim complete region inference. AST and IR instruction
accounting differ, so exhaustion must remain fatal but can occur at different
in-flight instructions. Functional comparisons preserve exact results, output
and original source-error spans; limit tests compare fatal outcome separately.

The ordinary conformance fixtures exercise source errors across calls/yields,
repeated waits, observed/unobserved futures, joined close, runtime/control priority,
lexical shadowing, nested caught state, match temporaries, closure snapshots and
Result returns. Separate machine tests inspect IR rejection, ticket state,
original-span rethrow and bounded live values over1000 handler iterations.
No security audit, sanitizer or fuzz campaign is run by these tests.

Publication still requires native compiled frames, physical TaskGroup source-error
storage/delivery/drain precedence and retirement; file/resource/FFI and binary
boundaries; debug/profile/cache/library/SDK/browser acceptance; explicit
history-preserving024-to025 migration; full current platform acceptance and the
broader original language/toolchain goals. Public manifests, build commands and
archival continue to reject0.25-prototype. Stable SDK pointers are unchanged.
