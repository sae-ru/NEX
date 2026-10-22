# Structured task runtime — internal0.98 prototype

This is a development runtime foundation, not a NEX source feature. Compile the
private nex_task_scheduler_probe with NEX_ASYNC_TASKS and NEX_STRUCTURED_WORKERS.
Ordinary generated applications do not enable it. Language0.18 types/effects,
syntax, canonical identities, value ABI and migration stay unchanged.

## Implemented runtime contract

TaskGroup owns1..16 OS workers, a preallocated runnable ring and up to65,536
task slots (default4096). TaskBody is a C++20 coroutine returning a NEX Value.
Factories receive input/capture Value snapshots by value. Validation rejects
file resources, including hidden aggregate/callable captures. A task owns its
coroutine frame; its body starts only after the scheduler accepts it. Nested
spawn uses the same pool. Creating a new independent pool from a worker is
rejected. A full task slot quota fails explicitly instead of blocking a worker.

await/yield/send/receive suspend coroutine evaluation and return the OS worker
to the runnable queue. Only the scheduler resumes frames. While a resume call
is still returning, a concurrent completion records a reschedule request; it
cannot resume that frame on another worker yet. This publication ordering is
required by the [C++ coroutine rules](https://eel.is/c++draft/dcl.fct.def.coroutine).
Futures retain immutable outcomes and propagate checked failures. Direct and
indirect future-wait cycles produce E_TASK_CYCLE. Channel deadlocks remain
bounded by the request deadline; no general deadlock detector is claimed.

Channels are FIFO, with zero-capacity rendezvous or bounded storage. A group
has at most1024 channels and65,536 reserved buffer slots in total. Full sends
and empty receives park tasks. Close is idempotent: queued data drains before
receive EOF, while pending/future sends return false. Waiting sender/receiver
links are removed on cancellation, so a canceled operation cannot steal or
inject a later message. All channel/frame/queue state is group-owned.

The group shares its enclosing request's atomic step budget, absolute monotonic
deadline and cancellation. Each resume consumes a step; ordinary runtime polls
and graph validation also charge the existing control. Waiting does not renew
the deadline or consume steps. Only the coordinator calls the host cancellation
callback. Parked tasks are woken on deadline, exhausted budget or cancellation.
Cancellation nodes propagate down nested spawn trees without canceling siblings.
Explicit cancellation is cooperative and does not force-stop native threads.

Every resume has a private worker RequestScope. Handles and unfinished native
ownership frames are released before the coroutine parks. Only retained Value
objects may cross suspension; retaining a raw Handle pointer is outside this
private API contract. Nested parallel_map runs serially on the current worker
and cannot multiply OS threads. Located native traps retain their source data.
The task/channel wait queues and ready ring need no allocation when waking.

finish drains tasks, joins every OS worker, destroys frames, revokes channel
operations and reports unobserved failures. Resource failures take priority
over ordinary unobserved item errors. Explicitly canceled branches are drained.
Immutable completed results remain joinable while the group object exists.
Destruction cancels/drains outstanding work and cannot replace an exception
already being unwound. Tickets/channels carry weak group identity; foreign or
expired identities fail with E_TASK_SCOPE. Constructor failure joins every
successfully created worker before releasing captured scheduler state.

The runtime trusts its C++ factories to use immutable Value data and poll/yield
during long computation. It does not preempt arbitrary C++ code. Current tests
check managed value/handle/frame cleanup, not complete asynchronous source
profiling or debugger attribution. No async file/network/FFI authority is added.

## Reproduce the runtime sanitizer checks

From this source checkout, using a compiler with its sanitizer runtimes installed:

```sh
python3 tests/task_scheduler_sanitizers.py --cxx /path/to/clang++ --sanitizer thread --output /new/tsan
python3 tests/task_scheduler_sanitizers.py --cxx /path/to/clang++ --sanitizer address,undefined --output /new/asan
```

The runner retains all commands/stdout/stderr, compiler version, source and
binary hashes. It refuses to replace evidence and enables leak detection and
halt-on-error. GCC can be selected explicitly with --cxx for ASan/UBSan. Missing
sanitizer libraries are a failed environment check, never a passing runtime test.
This runner requires the source tests and is not an installed SDK source feature.

## Required source integration

Working100 adds compiler-private TaskFunctionIR and TaskMachine as a lowering
test harness. The public language is still0.18 and source_support remains false.
No native task program or public reference/TypeScript scheduler is emitted.
The ordinary native, TypeScript, reference and archival guards still apply.

The IR splits expressions into typed slots and pure atoms. Atoms refer only to
already evaluated slots. Direct and indirect task calls, all ten task intrinsics,
returns and result-error exits have explicit instructions. Branches preserve
short-circuiting, guarded/nested patterns and while loops. Source locals and
captured values retain their lexical identities; temporary operands are dropped
after consumption, and lexical locals at block exit. A return or trap releases
the whole owning frame. Retained state uses Value objects, never raw Handles.
Function entry/loop heads have explicit poll instructions for the eventual
native cancellation/budget bridge. Compilation is bounded to65,536 slots and
262,144 instructions per concrete function.

The test harness executes this IR with a logical call stack (limit256), emitting
owned wait descriptors and one-use response tickets. A parked machine cannot be
advanced or resumed with an obsolete ticket. Pure atoms use the existing AST
interpreter/data primitives; independent ordinary AST execution of the same
program with yield statements removed checks lowering control flow and output.
This is not an independent async reference implementation. Its resource effects
are limited to pure/task/io semantics; fs/db/ffi require a later host bridge.
Typed task/channel/scope operations are lowered, but their scheduler descriptors
are not implemented by this harness. No fabricated task capability establishes
actual channel, future or scope execution. The native runtime remains separate.

Current source cases exercise recursion, captures/returned closures, generics,
module-qualified calls, loops, left-to-right calls, Unicode/NUL, f64 state,
result propagation across different payload types, guarded patterns, early
failure during aggregate construction, traps and owned cleanup. Resume calls
also transfer sequentially to real OS threads. These are continuation-state
tests, not proof of parallel native NEX execution or async debugger/profile
support. A real lost-output-on-trap bug in the new harness was caught by comparing
the failed helper's output with the ordinary AST interpreter and corrected.

The next step is MLIR step functions and runtime frame/descriptor helpers that
reuse this IR while retaining only state needed across suspension. Native code
must execute compiled expressions, not invoke the compiler/interpreter. The
bridge must provide logical nested scopes on the existing worker pool, genuine
capability values, scoped cleanup/cancellation and strict result validation.
Independent reference/TypeScript scheduling and explicit migration still follow.

The working099 integration adds private parseTaskPrototype/loadTaskPrototype
entry points and a typed frontend probe. These are not public CLI commands or a
language release. Program provenance keeps this mode separate from language0.18:
native/Wasm/TypeScript emission, reference execution/inspection, source archival,
revision identity and dependency locking reject it with E_TASK_UNIMPLEMENTED
before creating executable output. describe.source_support remains false.

The staged types are task<T>, channel<T> and task_scope. task<unit> is allowed;
channel payloads and ordinary generic type arguments remain non-unit values.
All three capability kinds are opaque heap identities, excluded from wire
constraints/JSON even through phantom generic arguments or callable signatures.
They also cannot cross foreign declarations or synchronous parallel_map input,
callback signatures or known closure captures. Actual hidden capture graphs and
scope ownership must additionally be checked by the eventual runtime bridge.

Suspension uses the explicit task effect, propagating through existing direct
and indirect call checking. No redundant async declaration marker is introduced;
ordinary names async/await/spawn/send/recv/cancel/close/yield retain their meaning.
Only the new intrinsic and contextual type names will need explicit migration.
This typing contract is still private and must not be used in ordinary0.18 code.

| Staged operation | Checked contract; each requires task effect |
| --- | --- |
| with_tasks(workers,callback) | i64, fn(task_scope)->T -> T |
| task_spawn(scope,callback) | task_scope, fn()->T -> task<T> |
| task_wait(pending) | task<T> -> T |
| channel_new<T>(scope,capacity) | task_scope, i64 -> channel<T>; T can come from expected channel type |
| task_send(queue,value) | channel<T>, T -> bool |
| task_recv(queue) | channel<T> -> result<T> |
| task_close(queue) | channel<T> -> bool |
| task_cancel(pending) | task<T> -> bool |
| task_yield() | unit |
| current_task_scope() | task_scope |

Callbacks must have an available realm and only pure/task effects, with no file
types or known file captures. Existing generic inference, constructor matching,
result propagation, lambda boundaries and effect diagnostics apply. Scope escape,
structured cleanup, scheduling, runtime bounds and cancellation outcomes are
not established by these typing tests. They require the continuation bridge and
independent native/reference/TypeScript execution before public source support.

The next language revision must define scoped Task<T>/Channel<T> capabilities
and explicit task effects; they cannot masquerade as pure serializable data.
Resource traversal must inspect generic aggregates and closure captures, and
wire/storage/browser boundaries must reject task/channel authority. Scope exit
must drain/cancel children on normal return, result propagation and every trap.
Source names should remain contextual where possible. A genuine0.18 archived
fixture and complete row/schema/ID comparison are required for explicit,
history-preserving migration; changing nex.json alone is insufficient.

MLIR lowering must lift live locals into retained continuation state and release
resume-local handles before suspension. One possible bridge is a compiled
resume function returning checked continuation state plus a typed wait
descriptor; the private C++ coroutine owns scheduler waits and invokes the next
resume. This route can reuse normal MLIR-generated synchronous functions and
checked arithmetic. It is a proposed lowering, not implemented compiler output.

The reference interpreter needs a runnable continuation queue as semantic oracle;
the TypeScript backend needs matching asynchronous scheduling and bounded
channels. Semantic agreement does not require identical OS scheduling. Existing
synchronous parallel_map and explicit browser worker jobs retain their contracts.
Native function/data ownership, left-to-right evaluation, short-circuiting,
sticky global limits and strict Unicode rules must hold across suspension.

Debugger/profiler async task identity, archived replay, static/dynamic providers,
installed/source-free SDKs and actual target platforms need separate current
acceptance. Asynchronous I/O needs its own capability/cancellation/commit rules.
The private runtime probe alone completes none of these remaining requirements.

## Current evidence

The exact [0.98 receipt](evidence/task-runtime-0.98.0.json) records13focused
groups and38runtime cases. Three strict ASan/UBSan and three TSan runs pass on
macOS after fixing an actual spawn/suspend data race. Linux ARM64 passes Clang
normal and GCC normal/ASan/UBSan checks; Clang sanitizer linking failed because
its libraries are absent from the pinned image. That failure is retained.
The maintained runner has its own actual TSan CLI smoke. These checks prove
the stated private runtime scenarios, not source async or currentfull102/SDK
acceptance. Installed097SDK archive-built workers separately pass15actual
production browser cases after deletion of their source file.
