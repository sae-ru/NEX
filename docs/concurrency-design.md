# Ordered CPU mapping — language 0.18 candidate

The source operation is implemented in this development source. Complete frozen
regression, installed SDK, platform, editor/debug/profile and migration acceptance
remain pending. Source async/await, general tasks/channels and GPU/NPU execution
are separate unfinished work. Toolchain0.97 adds an explicit browser worker-job
adapter; see [its distinct contract](browser-workers.md). Check actual `nex describe
--field source_concurrency --json`; an older SDK may expose only a private probe.

## Source contract

```nex
let output:list<i64>=parallel_map([1,2,3],fn(n:i64)->i64{return n+40;},3);
```

`parallel_map(list<T>, fn(T)->U, i64) -> list<U>` evaluates the input, callback
and requested worker count once, left to right. T and U are non-unit values.
Named generic callbacks infer from the input and expected result where possible;
explicit arguments and generic higher-order helpers also work. Empty input uses
a known callback argument type. The callback must have no effects and an
available realm: shared or the caller's realm. It cannot acquire io/db/fs/ffi
through a worker operation. Normal effect/realm checks still apply to its body.

Input/output and callback signatures containing file types are rejected, including
nested nominal members and phantom arguments. Function signatures can hide a
resource captured by another function: the runtime traverses actual immutable
input/capture graphs before any callback starts and rejects all hidden file
values. Returned graphs are checked too. Such failure is E_PARALLEL_VALUE;
there is no silent copy or transfer of resource ownership. Trusted embedding
code remains responsible for its own native callbacks; this is not a stable ABI.

Results have input order. Expected `result<U>` errors remain ordinary values;
`?` returns from the callback's own function and cleans its temporaries. Every
callback completes or the group joins before control returns. Ordinary checked
failures select the lowest failing input index. Global cancellation, execution
limits, deadlines and allocation failure take precedence over ordinary item
errors; they are never converted into an element result or silently swallowed.
Different physical resource limits/schedules can cause different resource
failures; no deterministic timing or identical execution-counter claim is made.

## Native execution

The current native target accepts macOS/Linux 64-bit ABIs. Actual execution and
acceptance belong to their recorded compiler/source/hardware receipts; another
OS or cross-build is not a device execution claim. Other CPU targets are pending.
The group requests1..16 threads and accepts at most65,536 items. It starts at
most min(workers, items) operating-system threads, holds them until construction
succeeds and joins every thread on normal/error/partial-construction paths.
Empty input starts no threads. A nested group runs serially on its existing
worker and cannot multiply operating-system threads.

Hosted work shares its existing request's atomic step counter, cancellation and
absolute deadline; it does not renew them or inherit file/foreign authority.
Standalone application groups create a private1,000,000-step/5,000-ms request.
Nested groups reuse that control. Only the coordinator calls a host cancellation
callback while waiting. Limits are checked cooperatively; an individual trusted
native operation can delay cancellation until it polls/returns. No forced thread
termination or strict real-time deadline guarantee is claimed.

Native/reference value graphs are bounded to262,144 objects/members. Per-worker
compiled calls are bounded to256 source call frames. Each job creates its own
handles, retains immutable shared data and uses an owned call frame. Scalar bits
and one retained result avoid argument/result list allocations. Borrowed input
aliases and returned closure captures survive cleanup. All unfinished ownership
frames unwind on failure. The coordinator result is allocated after a standalone
group request ends, under its original application/function owner. Normal group
completion preserves the caller's active profiling frames and resources.

Static/dynamic project providers propagate their actual parallel runtime
requirement. Shared images use one final runtime. Reusable project callables keep
call-scope hooks even when first built without a reachable map; non-worker
runtimes provide inert hooks. Artifact keys bind the instrumentation and runtime
requirements so an incompatible cached function cannot be silently reused.

## Reference and TypeScript execution

The reference interpreter evaluates sequentially as the semantic oracle and
shares its existing interpreter step limit. The current synchronous TypeScript
backend also evaluates sequentially. It has checked capture metadata, bounded
value traversal, a shared1,000,000-poll/5,000-ms monotonic group control, and a256
callback call-depth bound; nested calls reuse it. Both preserve ordered outcomes
and checked error precedence. Representation-specific object/resource counters
are backend policies, not byte-for-byte allocation equivalence.

**These two backends provide no measured or promised parallel execution.**
The0.97 browser worker-job adapter provides an explicit asynchronous application
boundary. It does not make synchronous parallel_map launch browser workers.
Browser output still contains only reachable client/shared code; server code and
capabilities cannot enter it. No npm dependency or bundled notice changed.

## Migration, validation and tools

Language0.17 artifacts require an explicit history-preserving migration. Keep the
matching SDK and a complete graph snapshot. `parallel_map` is newly reserved for
function/nominal declarations; old conflicting definitions are rejected without
rewriting the store. Review a renamed exported candidate and explicitly migrate
it. Genuine017 SQL/JSON fixtures retain actual source/versions/IDs; never relabel
an old graph or bypass the version guard.

`examples/parallel.nex` exercises pure generics, ordered results and `?`.
`parallel_mapping` tests native/reference/TypeScript agreement, actual distinct
native profile thread IDs with overlapping callback intervals, completed calls
and zero live managed pools. It also checks nested captures, returned functions,
scalar tags, single argument evaluation, limits, hidden resources, rejected
programs and genuine017 migration/explicit reserved-name repair. Live debugger,
platform, SDK, captured replay and current full acceptance remain separate gates.
The private26-case runtime suite and actual compiled-closure tests remain useful
boundary checks, and do not by themselves establish source-language acceptance.
