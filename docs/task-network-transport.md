# Private task TCP transport

Toolchain0.135.0 adds a trusted C++ host kernel for asynchronous TCP work in
`TaskExternalPool`. Public source language remains0.24. No network builtin,
effect, async/await syntax, continuation instruction or migration is enabled.
The separate [pinned TCP provider](tcp-provider.md) uses existing task/FFI source
calls from toolchain0.135.1; no kernel builtin is implied. `std/net.nex` still
describes browser commands. Discover the private boundary
with `nex describe --field task_network_transport --json` and this guide with
`nex guide --kind task-network-host --json`.

## Authority and immutable requests

An operator constructs `TaskNetworkGrant` from a genuine `ResourceAccess` and
1..16 named endpoints. Each endpoint has a numeric IPv4/IPv6 address and a port
in1..65535; DNS names, embedded NUL and duplicate names are rejected. Preparing
an exchange selects an already granted name. Source strings, environment, worker
TLS and a textual endpoint ID cannot construct authority.

Preparation copies the complete input bytes and retains revocable access, not
the unique domain wrapper. Destruction/revocation of any parent domain therefore
invalidates later checks. A copied grant cannot revive it. The worker receives
bounded host data and a fixed operation; no source Value, frame, coroutine address,
borrowed C FFI token or source callback crosses this boundary.

```cpp
ResourceDomain request;
TaskTcpEndpoint endpoint{"service", "127.0.0.1", 9000};
TaskNetworkGrant grant(request.access(), std::span(&endpoint, 1));
std::vector<uint8_t> input{1, 0, 255};
PreparedTaskTcpExchange work(grant, "service", input, 4096, 5000);
TaskExternalPool io;
auto ticket = io.submit(1, work.operation(), work.reservation(), parentControl);
// The coordinator can execute other work until io.ready(ticket).
auto result = work.admit(io.take(ticket), parentControl);
```

`parentControl` is the owning host's existing request checkpoint. The pinned source provider captures the existing task/FFI request control;
other bridges must likewise retain owned control without creating a new budget
or borrowing a source frame. This example is C++, not NEX source syntax.

## Physical protocol and limits

The kernel opens a nonblocking socket, connects to the exact admitted endpoint,
sends the copied request, closes its write direction and receives through peer
EOF. Short sends/receives and interrupted syscalls are handled. There is no
automatic retry, redirect, endpoint switching or fallback. Replies contain
arbitrary bytes; text decoding belongs on the coordinator.

Input and declared reply limit are each at most1MiB; a reply limit must be
positive. An exact-limit reply is accepted only after peer EOF; an additional
byte is a fatal `E_LIMIT`. Reservations include actual retained input capacity,
reply capacity and grant/endpoint metadata. The existing pool defaults to2 IO
workers,64 tickets,8MiB aggregate reservations and1MiB maximum result storage.
These payload limits do not describe total process RAM or OS socket buffers.

An exchange deadline is1..30000ms and starts at preparation, including time in
the queue. Parent cancellation/deadline and authority are checked before and
after physical waits; the parent may impose an earlier limit. Poll waits use
at most10ms intervals between checks, without a hard scheduling-latency promise.
Connection/transport failures are ordinary `E_NETWORK` outcomes. Cancellation,
revocation and fatal execution/storage limits remain exceptional host outcomes.

Cancellation or revocation cannot roll back bytes already sent. A nonblocking
call admitted just before revocation may complete before the next checkpoint.
This transport provides no message transaction, delivery acknowledgement or
remote rollback guarantee. Higher protocols must define those semantics.

The socket closes on every success/error/cancel path before the pool publishes
physical completion. A queued cancelled or expired request opens no socket.
Pool destruction cancels and joins admitted physical work. Retained authority
is checked again at coordinator admission, including an optional parent control;
forged or over-capacity outcomes are rejected before source construction.

## Verification and remaining integration

`experiments/task-network` builds the same runtime sources independently of the
compiler; the main CMake build also registers `task_network_transport`. The
suite uses actual loopback IPv4/IPv6 sockets, split binary transfers and exact
reply limits, connection refusal/reset, concurrent IO, queued cancellation and
deadlines, parent expiry, domain revocation, late admission, reservation pressure
and abandoned-pool drainage. Sanitizer results retain their platform/compiler
and instrumentation scope; they do not instrument the entire NEX compiler.

Current retained Linux images may lack compiler-rt. The maintained Dockerfile
installs the exact LLVM22.1.8 runtime package; `tools/linux/Sanitizers.Dockerfile`
can derive a separate image from an existing verified image without replacing it.

The separate source provider reuses existing typed server task/FFI contracts
and native/independent AST transport without a source language migration.
DNS, TLS/HTTP, persistent sockets, streaming, dedicated debug/profile integration
and complete matching SDK/platform acceptance remain open. Asynchronous database IO is separate remaining work. This kernel
does not establish a finished async network language feature or the full goal.
