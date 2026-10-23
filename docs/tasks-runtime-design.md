# Current020 file-read extension

Working117/toolchain0.110 adds exactly file_read_text/file_read_bytes suspension
in actual server task/fs functions, with explicit019 history-preserving migration.
Native macOS/Linux/source-only projects and independent reference use a root
FileReadGrant and physical completion fences; TypeScript/browser filesystem
remains unsupported. Callback/effect rules, first-fatal priority, quotas and
current pending acceptance are specified in [task file reads](task-file-reads.md).
This does not enable broader IO/debug/providers/UI. Native020 task profiling
is a separate toolchain0.114 integration; query `task_profiling` and read the
[profile guide](profiling.md). Toolchain0.115 adds a separate narrow native020
logical debugger; query `task_debugging` and read [its contract](task-debugging.md).
Combined task debug/profile sessions remain pending. The development
stages below retain their original019/private018 scopes and acceptance limits.

# Public019 integration

Language0.19 now uses the checked task frontend for ordinary source programs.
Native standalone applications/source-only projects compile continuations;
reference evaluation and standalone TypeScript use independent cooperative
schedulers. The checker invokes bounded lifetime analysis and runtime authority
checks remain mandatory. See [the current specification](language.md),
[lifetimes](task-lifetimes.md) and [migration](task-migration.md).

The sections below preserve the development history of the private018 stages.
Their statements about disabled public support describe those older stages.
Broader task IO, non-native debug/profile, binary providers, NEX UI adaptation, full installed
SDK/platform acceptance and complete static region inference remain pending.

# Private authority-flow diagnostics (working108)

The bounded analyzeTaskLifetimes pass follows known scope owners through helpers,
aggregates, patterns, aliases and callable factories, diagnosing known escapes
while preserving borrowed ancestor values. Unknown targets, channel payloads,
recursion and loop widening retain mandatory runtime obligations; this is not
complete static region inference. The [lifetime contract](task-lifetimes.md)
defines ownership, effects, cleanup and diagnostic scope. Public source support
stays false;019 migration is required. Invalid private runtime conformance
fixtures remain checkable without running this separate diagnostic pass.

# Private generated TypeScript tasks (working107)

emitTaskTypeScript emits only reachable shared/client checked functions as
resumable generators. Ordinary public emitTypeScript still rejects taskPrototype.
All source calls, including pure helpers, are generated resumable code rather
than an AST/TaskIR interpreter. The independent web/nex-task-runtime.ts scheduler
owns ready/future/scope/FIFO state and returns control through MessageChannel.
Ready jobs and reserved channel buffers use fixed rings with constant-time FIFO
operations; consumed references are cleared immediately. Waiter-index queues
use amortized constant-time operations without reserving4096 entries per channel.
Statement/loop checkpoints charge the shared budget and yield internally every64
polls, so even a pure helper can receive host cancellation. Source task_yield and
the other nine staged operations retain real suspension. No OS parallelism is
claimed. The ordinary parallel_map value validation primitive is reused, while
its private generated callbacks and scheduling remain independently executed.

Generated function try/catch handles only its own result-propagation sentinel;
traps/resource failures propagate. Synthetic match-expression generators have no
extra source return/call boundary. Call depth is limited to256 across callbacks.
Native cancellation ancestry counts the root task as level1. Working107 fixes
the prior AST root level0 and uses the same1..256 limit in TypeScript; checked
depth255/256 descendant fixtures test the last valid nesting and first rejection
against native O0/O2. Earlier106 gates did not include this boundary. The owned
family discriminator is packed next to Data::kind in existing header alignment
space; layout/sanitizer evidence must be recorded for the current source.

Task/scope/channel objects have private owner brands, weak driver references and
canonical WeakRef caches. They have opaque equality/printing semantics without
granting authority through ordinary record tags. Hidden aggregate/closure graphs
are validated at spawn/send/return; closed scopes and ended/foreign drivers
cannot authorize operations. Requests are branded, checked for operation/arity
and consumed once. Cancellation unwinds generator finally boundaries and drains
owned descendants before completion. Logical frame/call cleanup is checked;
JavaScript heap reclamation remains garbage collected, not native pool accounting.

Private source maps use nex.private-typescript-task-map/1 with source coordinates
and ephemeral location/entry-text hashes. They never call public018 revision
canonicalization or promise historical graph IDs. Node strict type checking and
AST/native source comparisons, and production Chromium/Firefox/WebKit timer,
animation and button cancellation probes have separate evidence. The browser
probe is one standalone generated program, not all-language browser conformance
or an asynchronous NEX UI adapter. npm pins and bundled dependency notices are
unchanged. Complete static lifetime/effect contracts,019 migration, async IO,
source debugger/profile, provider lifetime and full current SDK/platform delivery
remain pending. Public source_support stays false.

# Private independent AST scheduler (working106)

evaluateTaskReference drives TaskAstMachine on one coordinator with its own
ready queue, future dependencies, lexical scope records and FIFO channel deques.
All ten private requests are dispatched here without TaskIR, native compiled
frames or TaskGroup calls. Cooperative turns model asynchronous source effects;
they do not establish OS thread overlap or execution of simultaneous IO.
with_tasks still checks1..16 workers; a serial reference never exceeds that cap.

Normal scope exit drains children, including descendants forked during drain.
An error result, trap or cancellation aborts/drains owned scopes before completion
is visible. Unobserved child failures propagate on normal scope exit. Future and
scope-drain dependency cycles report E_TASK_CYCLE. If every task is parked on
channels with no possible progress, this private reference reports
E_TASK_DEADLOCK; native wall-clock timeout behavior remains a separate contract.
Channels support rendezvous and bounded FIFO queues, closed-send false and
closed-receive err(E_CHANNEL_CLOSED). There are4096 task slots,1024 scopes,
1024 channels and65536 total reserved channel slots, with256 nested calls/scopes
and262144 pending actions across all machines of one task. One shared step budget
charges traversal, atoms, requests and snapshot validation across spawned jobs.

Reference capabilities have private final owned payloads, an immutable reference
family tag and weak scheduler identity. Canonical weak caches preserve equality
while aliases remain. Native casts require the native family first. Both reject
base slicing and forged ordinary Data tags. Independent graph traversal checks
hidden aggregate/closure capabilities against current and destination scope
ancestry on spawn, send, task completion and callback return. Files are rejected.
Closing scopes revoke authority and release queued values; expired copies cannot
authorize a later scheduler. No reference scope extends native TaskGroup lifetime.

The private reference probe checks cleanup, capability-family rejection and
source results/errors. The native continuation suite also executes each complete
program through this reference, retaining task_yield and all structured requests.
Public task integration, complete region typing, explicit019 history-preserving
migration, async IO/debug/profile and full target/SDK delivery remain pending.
Public source support stays false and language0.18 identities/grammar are unchanged.

## Independent AST control machine

TaskAstMachine traverses the checked AST through owned action, lexical-scope,
evaluation and function stacks. It never calls lowerTaskFunction or executes
TaskIR. Direct/indirect calls, branching, loops, guarded patterns, short circuit,
returns and result propagation have independent control traversal. Ordinary
already-evaluated atoms reuse checked data primitives through evaluateTaskAtom.
All source user calls and suspension are handled outside that atom boundary.

TaskTransition is a shared transport interface, separated from the IR machine.
Requests contain owned arguments, source spans and one-use response tickets.
A machine requires exclusive ownership while advancing/resuming; it can transfer
between joined OS threads. It retains no native Handle. At most256 source call
frames and262144 aggregate pending actions are permitted; a shared machine step budget
charges traversal and atom work. Failure clears retained frames; abandoning a
parked machine releases owned values. Responses and explicit call arguments have
checked value kinds. File authority and fs/db/ffi execution are rejected.

The original30 AST source scenarios and240 checks use an ordinary AST oracle
where yield is erased. Two additional checked wide-function scenarios exercise
aggregate pending-action exhaustion and early-return allowance release. This
control-machine probe is distinct from the asynchronous scheduler/native
comparison. Working105 full107 and strict AST/IR sanitizer gates passed before
this separate106 work began;106 validation must use its own current sources.

# Private structured source execution (working104)

The compiler-private probe now emits real native continuations for all ten
staged operations below. Public source_support remains false and language0.18
retains its existing syntax/identity/archive contracts. This is not a release.

with_tasks(n,callback) creates a logical scope on the current executor, with a
1..16 concurrency cap. Every ancestor cap applies to a resumed task. Nested
scopes create no worker-owned pool. Normal callback return waits for all owned
children; an error result cancels/drains them before returning that error.
Checked traps and cancellation cancel/drain before the failed owner becomes
joinable, including cancellation before its next coroutine resume. Coroutine
frames are destroyed outside the scheduler mutex before completion publication.
Existing descendants may fork during a normal drain. Scope/future dependency
cycles fail with E_TASK_CYCLE; bounded graph-walk storage is reserved in advance.
There are at most1024 logical scopes and256 nested scopes in one executor.

Task/scope/channel values have real owned final payloads with weak owner
identity. Canonical weak caches preserve opaque identity while aliases live.
A capability can move into a descendant scope. Spawn captures, send payloads,
callback returns and task results traverse actual hidden aggregate/closure
graphs: a descendant capability cannot escape to an ancestor. Borrowed ancestor
capabilities can return through an inner scope. File authority remains excluded,
and synchronous parallel_map rejects task authority even through hidden values.
Ending a scope revokes access, closes/frees its pipes and releases retained child
outcomes. These runtime owner checks are not a complete formal region type
system; phantom/lifetime semantics still require explicit cross-backend work.

channel_new creates FIFO rendezvous(capacity0) or bounded queues. task_close is
idempotent within its live scope. Queued values drain before receive returns
err<T>("E_CHANNEL_CLOSED","channel is closed"); closed sends return false.
Future wait returns its immutable outcome or propagates its checked failure.
current_task_scope outside with_tasks fails with E_TASK_SCOPE. task_yield may
also suspend the private root task. Source callbacks retain the existing
pure/task-only effect contract, with no asynchronous I/O authority added.

The compiler emits owned request arguments and saves the continuation PC;
no raw Handle crosses suspension. Scheduler waits park the coroutine and carry
rich NativeSite records. Some runtime guards retain legacy line0 while their
operation/function source metadata remains precise. All callable descriptors
currently require monolithic image lifetime; provider unload/reload is pending.

Current validation includes53 complete native source scenarios atO0/O2, plus
three subsequent pure-callback/task<unit> cases. The full maintained set now has56
scenarios and needs final exact-source acceptance. Older ordinary AST24 and
TypeScript21 mirrors erase yield; none is an independent asynchronous backend.
The current C++ scheduler/capability probe has65 cases. An earlier62-case
revision passed three strict ASan/UBSan/LSan and three TSan runs; final65/native56
sanitizer/full/SDK/platform gates remain pending.

Independent asynchronous AST/TypeScript, complete region semantics, explicit019
history-preserving migration, async debugging/profiling and I/O, provider ABI,
SDK delivery and target/quality acceptance remain required before enabling
public source support. The following sections retain earlier stage contracts.

# Prior compiled continuation stage (working103)

`emitTaskNativeStep` compiles checked source through verified MLIR/LLVM. The
private probe links actual native programs, without enabling public task builds.
Each step retains owned Value slots and closes its temporary Handle boundary
before returning to the coroutine bridge. Yield parks the coroutine. A direct
or indirect task call pushes a separate logical frame; return copies its owned
result to the caller and pops the frame. Calls do not use native stack recursion.

Task callables have an immutable, versioned TaskCodeDescriptor with a distinct
step pointer and typed slot/parameter/capture tables. The compiler emits these
as constant globals. A closure records the descriptor separately from its
ordinary native code pointer; task-only closures have no ordinary code pointer.
Pure closures may carry both explicitly. Ordinary invocation rejects a task-only
callable. Only the monolithic private native experiment is supported; descriptors
must outlive retained values, and shared-image unloading is not integrated.

The logical stack has at most256 frames. During each resume, its depth contributes
to the existing checked pure-helper call depth. Generated step/helper entry and
exit guards enforce the combined budget; an RAII baseline restores worker state
on traps. This fixes a reproduced101 defect where a finite300-level pure helper
inside a task bypassed the guard. Limit traps retain rich operation/function
source records, even when their legacy reported_line is0.

Checked expressions, left-to-right arguments, short circuit, immutable closure
captures, Unicode, f64, guarded patterns and result propagation keep their
ordinary semantics. Scope/channel operations and task/file capability slots,
client entries and captured root entries are rejected. Native source-task
profiling/debugging, independent asynchronous AST/TypeScript execution, the
complete scope/channel bridge and explicit history-preserving migration remain
pending. Language0.18 public syntax and archive/build guards are unchanged.

Native checks support `tests/task_native.py NEX PROBE --sanitizer address`
(ASan/UBSan/LSan) or `--sanitizer thread` (TSan). They instrument compiled source
modules, runtime and the C++ driver. Ordinary yield-erased AST/TypeScript mirrors
are independent value/output checks, not asynchronous scheduling evidence and
not sanitizer-instrumented.

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
At that earlier stage independent reference/TypeScript scheduling still followed.
Working106/107 implement those private schedulers; explicit migration remains pending.

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
