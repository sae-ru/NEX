# Server runtime design

This is the implementation contract for the next server milestone. It does not claim that all items below are available yet; `STATUS.md` records tested capabilities.

## Values, failures and external resources

Introduce `result<T>` with explicit success/error values. Invalid input, unavailable capabilities, missing storage keys and database failures must be recoverable data. Arithmetic/collection/assertion failures remain traps, with a server request boundary that contains them. `unwrap` on an error is an explicit trap. Error values carry a stable code and a separate message.

SQLite connections, transactions, sockets and credentials belong to the runtime. NEX source cannot copy, forge, retain or close their raw handles. A server request borrows those capabilities for its lifetime; a result may contain immutable NEX values but cannot make a resource escape. Native handles created during a request are tracked and reclaimed even if execution traps. Normal native ownership checks remain in force. General user-defined resource/FFI ownership is separate future work.

## Wire data

Use a versioned strict JSON codec driven by checked NEX types. Every `i64` is a canonical decimal JSON string, preserving its full range in browsers. Booleans and strings keep their JSON types, lists are arrays, and records require their declared fields and reject unknown ones. Decoding reconstructs nominal types. Reject malformed UTF-8, unpaired surrogate escapes, duplicate object keys, missing/extra fields, out-of-range integers and excessive input/depth/collection sizes. Decoding returns `result<T>` and never silently repairs data.

The same supported type contract must be checked in the interpreter, native backend and TypeScript backend. API boundaries validate data on the server independently of browser checks.

## Concurrency and transactions

Use a bounded HTTP worker pool/queue. Each handler executes synchronously in its own request scope, with immutable values and request-local mutable variables. Runtime counters shared among workers must be atomic; no mutable NEX value is shared between requests. Poll at function entries and loop iterations for request budgets/deadlines/shutdown. A trap or cancellation unwinds to the host boundary, releases request-owned handles and rolls back its transaction.

Database handles are RAII-owned. Writes use a request transaction; commit only after a successful response and a final cancellation/budget check. Roll back on a trap, storage failure or error response. Use prepared statements and bound values. SQLite serializes writers; a bounded busy timeout produces a recoverable error rather than an unbounded wait. Do not replay a handler automatically after an uncertain commit. Non-request CLI storage operations have individual atomic operation boundaries.

## Identity and isolation

The host authenticates a request before invoking NEX and injects the principal. Storage partitions by that runtime principal, not a user identifier supplied in request JSON. Treat authorization as a server property. Keep runtime credentials/configuration outside static assets. Client emission remains limited to reachable client/shared definitions; server bodies and secrets do not enter client source maps.

## Browser effects

Keep rendering/state transitions pure. Add an explicit command/event boundary for asynchronous requests, with request identity, loading, success/error, cancellation and bounded timeouts. Validate typed responses before delivering them to state transitions. Do not hide a synchronous server call behind an ordinary client-to-server function call. Language-level concurrency beyond this host-managed request/command model remains an explicit later extension.

Implementation checkpoint (toolchain 0.6.0): the `std/net.nex`/optional `commands` contract implements request identity, bounded HTTP work, cancellation and explicit failure envelopes. The example's pure update validates application bodies against shared checked models before accepting them into state. Automatic endpoint declarations/stubs, including endpoint-specific validation before callback delivery, remain a later step; the current generic transport does not claim that generator.

Implementation checkpoint (toolchain 0.7.0/language 0.5): endpoint declarations now generate checked native dispatch, an extracted client model SDK, typed request/response helpers and OpenAPI. Typed commands validate successful response bodies against generated schemas before callback delivery; handlers decode inputs independently and receive injected Context. Generic commands remain supported. General source concurrency/resource FFI and the platform roadmap remain open.
