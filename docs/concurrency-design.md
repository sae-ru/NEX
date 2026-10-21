# Structured CPU worker development

Source concurrency is **pending**. Language0.17 has no `parallel_map`, `spawn`,
channel, async/await, GPU or NPU intrinsic. Ordinary native applications and the
TypeScript/reference backends retain their existing source semantics. HTTP host
worker concurrency is an independent implemented server configuration.

Toolchain0.86 develops an internal native worker substrate before exposing a
language operation. `runtime/nex_parallel.h` is a compiler-private trusted-host
interface, compiled only with `NEX_STRUCTURED_WORKERS`; ordinary emitted runtimes
do not enable it. It is not a stable FFI or an installed source capability.
The checker, reference interpreter and TypeScript backend accept no new builtin.

Toolchain0.91 adds a compiler-private compiled-call boundary to this substrate.
`parallelCompiledValues` accepts a closure environment and a trusted pure bridge,
checks scalar/heap ABI kinds, and creates environment/input handles inside each
job. Scalar arguments travel as bits; a heap argument uses one local handle.
The result helpers retain one immutable value without allocating an argument or
result list/record. They reject missing/duplicate returns and a destination from
another thread or nested call. Per-call ownership frames clean temporaries and
unfinished nested frames before handoff, including on exceptions. Returned heap
aliases and closure captures survive through retained values. No caller-owned
handle is handed to a worker. File-bearing graphs remain prohibited.

This boundary requires an existing request and does not grant new capabilities,
refresh a budget/deadline or define a source-language operation. It is compiled
only with `NEX_STRUCTURED_WORKERS`. Native source lowering, checked capture rules,
interpreter/TypeScript semantics and explicit source migration remain pending.
The additional `compiled_workers_native` test builds a code-only archive from
actual NEX functions, then calls its i64/f64/bool/heap/closure targets through the
private bridge. Its host exercises the ABI, not replacement function bodies.
This is separate from SDK or source-concurrency acceptance.

## Internal contract

The prototype `parallelValues` accepts an immutable list, an immutable environment,
1..16 workers and a trusted stateless callback function. It requires an existing
`RequestScope`. Input is limited to65,536 items. Each input/environment/output
value graph is bounded to262,144 objects/members; nested file resources, including
closure captures and nested aggregates, are rejected before crossing a worker
boundary. Data references can be retained across threads; caller-owned `Handle`
pointers cannot. The trusted callback must obey purity and cooperative polling.
Runtime validation alone cannot certify arbitrary C++ callbacks as pure.

Each item has a worker-local request ownership scope. The callback returns a
retained immutable `Value`; temporary native handles and registered worker-local
cleanup functions are released before that job ends. Worker scopes share the
original request's atomic execution counter, exhausted state, cancellation and
absolute deadline. They do not renew a budget/deadline or inherit a root resource
domain. Finishing a job does not end the parent request or revoke parent handles.
Polling keeps the existing single-thread request step/budget behavior, with a
saturating shared counter. Only the coordinator executes the host cancellation
callback, including while it waits; that waiting consumes no language steps.

The group creates at most the requested number of actual operating-system
threads. All threads wait until group construction succeeds before entering a
callback. Partial thread creation, allocation failures, callback exceptions,
cancellation and timeouts join every created thread before destroying captured
state or returning. A callback that bypasses cooperative polling can delay that
join; no forced thread termination guarantee is claimed for trusted native code.

Results retain input order. After joining, global cancellation, budget exhaustion
or an elapsed deadline precedes per-item errors. Otherwise the lowest input index
with an error supplies its original checked diagnostic/source location, even if
a higher-index error finished earlier. Ordinary item errors do not revoke the
parent request. A nested group runs serially on its current worker and cannot
multiply operating-system threads. These are prototype native contracts, not yet
a promised language scheduling or cross-backend error-selection contract.

## Validation and remaining language work

`ctest --test-dir BUILD -R structured_workers_runtime --output-on-failure` runs
the actual C++ runtime probe. It checks four simultaneously executing threads,
ordered Unicode/capture results, immutable input, nested scheduling, parent and
worker ownership, diagnostic ordering, shared limits, cancellation monitor
thread identity/failure, deadlines, file-bearing rejection, allocation failures,
registered cleanup and both managed memory pools. Sanitizer evidence belongs
to the exact tested source/compiler; a successful probe does not establish full
SDK, platform or source-language acceptance.

Before a source operation can be supported, implement and review all of:

- Its type/effect/realm and immutable capture rules, including hidden resources
  in higher-order values, resource-bearing nominal types and rejected programs.
- Interpreter, native MLIR and TypeScript observable result/error agreement.
  Browser workers, serialization and scheduling guarantees need an explicit
  design; a sequential fallback cannot be reported as measured parallelism.
- A bounded native callback ABI, generated ownership transfers, request and
  application integration, nested work and cleanup on every checked native exit.
- An explicit language-version and history-preserving migration path if source
  semantics or reserved intrinsic names change; retain matching historical SDKs, including language0.16 and0.17.
- Specification/grammar, capability discovery, provider-independent prompt,
  language-pack examples, SDK/platform execution and profiling/debugger evidence.

General asynchronous I/O, channels and accelerator placement remain separate
pending work. Fixed CIX hardware FFI probes do not provide any of these APIs.
