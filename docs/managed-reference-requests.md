---
status: current
applies_to: "toolchain 0.259.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Private native request reference contexts

The matching-runtime C++ `RequestScope` can own a lazy reference heap. A request
has its own attachment even inside an enclosing application. Calls in that
request reuse its heap; different requests do not inherit one another's state.
This extends the [private source/module candidate](managed-reference-modules.md).
It enables no ordinary source version, HTTP adapter, task transfer, graph
migration, source archive or public SDK reference API.

## Generated entry and host ownership

`emitManagedReferencesPrototypeRequestMLIR(program, entry, optimized)` emits the
checked reachable source closure and this compiler-private native symbol:

```cpp
extern "C" int64_t nex_private_reference_request(nexrt::Handle **source_error_out);
```

The source entry takes no arguments and returns unit or i64. Unit produces zero;
i64 retains its full width until a host deliberately converts it to a process
status. A client-realm entry is rejected. A cell/closure/aggregate cannot be a
host result. Source functions may still exchange cells internally.

The host must hold the matching runtime and a live `RequestScope`, supply a
nonnull `Handle **` output slot and consume any returned source-error handle
before its next call or request end. Each call clears that slot before execution
and rejects a missing request, even if an application context is present. Typed
source errors use it; fatal traps unwind to the C++ host. When a source-error
handle is returned, ignore the scalar status. Copy diagnostic
code/message/source/line, release packet data inside the request, then return an
ordinary host response. No live source value is exported as a wire result.

The generated wrapper calls no application entry or `nex_runtime_finish` and
never closes its caller's request. Multiple successful calls can share one
request. End that request after a fatal failure. A host may initialize the
cell/node/edge limits once with `nex_cell_context_limits` before the first cell
operation; otherwise the kernel defaults apply. Reinitialization is rejected.

This entry is for a C++ development host, not a new public HTTP handler ABI.
The normal application emitter retains its own wrapper/lifetime. Starting that
application wrapper inside an active request does not acquire a request heap;
use the explicit request entry. Separate DLL/component reference passing and
reference-valued host returns remain pending.

## Attachment lifetime

Application and request owners use the same opaque factory state machine:
inactive, creating, active, closed. Failed/null creation can retry while the
owner is live. Reuse requires the exact factory/destructor pair. Acquisition
cannot reenter from any attachment factory/destructor, even if a callback ends
its request and exposes an enclosing application. Such an ended creation
retires its candidate and cannot publish it into another owner.

Request teardown first disables acquisition and revokes its resource domain,
then unwinds source frames and deletes tracked handles. It closes the reference
heap afterward, on the owning thread. This invalidates outstanding cells and
detaches their mutable payloads; retained immutable snapshots stay independent.
The enclosing application's cells remain live. C++ hosts must not use borrowed
handles after their request ends or pass cells into another request/heap.

## Cancellation, deadlines and work limits

Native cell creation/read/write/collection polls the current request before and
after the operation. The entry also polls. Cancellation from another thread
marks the request; observation produces the existing fatal cancellation trap
and skips pending user finalizers. Actual destruction stays on the owner thread
when its source/host scopes unwind. A write completed before the post-operation
poll is not rolled back. Budget/deadline failures follow the same cleanup path.

These are cooperative checkpoints. GC/adoption traversal is not preemptive and
has no separate work meter; this does not establish a hard interruption or
real-time pause bound. Request step accounting includes its native polls and is
not an exact AST-step count. General task resumption/state sharing and owned
capabilities inside cells remain separate work. Toolchain0.259 adds sequential
[source fs/ffi coexistence](managed-reference-resources.md) with explicit host
capabilities and the existing request resource bindings.

## Verification

`tests/managed_reference_requests.cpp` checks factory reuse/retry/reentry,
sequential and independent threaded requests, snapshots, handles-before-heap
teardown, budget/cancellation/deadline traps, callback-ended owners and an
unaffected enclosing application. The existing core context group also checks
request-emitter rejection gates and absence of a process/application wrapper.

The native driver runs the manual module corpus through generated request
entries at O0/O2, with two calls per successful request and two requests per
process. It compares a matching-runtime loaded image with an independently
linked executable, checks full-width i64 status, source-error/trap attribution
and zero live values after each request. Additional generated-code controls
check budget, post-write cancellation and deadline cleanup, including skipped
user finalizers. The [qualification evidence](evidence/managed-reference-requests-0.258.0-2026-11-16.json)
records the exact source, tools, results and limits. This is not a complete
platform/SDK or HTTP-adapter release.
