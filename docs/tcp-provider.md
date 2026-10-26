# Bounded task TCP provider

Toolchain0.135.1 provides `std/tcp.nex` and an operator-prepared native module.
It uses existing language0.24 server `task,ffi` calls. There is no new network
builtin, effect, async/await syntax, source version or ABI migration. Discover
`nex describe --field tcp_provider --json` and `nex guide --kind tcp --json`.
The private C++ kernel remains separately indexed as `task_network_transport`.
`std/net.nex` continues to provide browser HTTP commands.

## Prepare and use

Install a matching development SDK and its documented C++20 platform tools.
Choose exact service addresses in an operator-owned JSON file:

```json
{"schema":"nex.tcp-targets/1","maximum_connections":16,"endpoints":[
  {"name":"service","address":"127.0.0.1","port":9000}
]}
```

```sh
python3 SDK/share/nex/tools/tcp_provider/prepare.py --sdk SDK \
  --targets targets.json --output NEW_PROJECT
cd NEW_PROJECT
SDK/bin/nex check
SDK/bin/nex run --foreign foreign.json --profile release --json
```

Use an absolute SDK path when changing directories. Preparation compiles the
exact endpoint policy into a native module, hashes its complete bundle and
queries the real compiler for typed export signatures. It checks the library,
example and compiler/doctor/pack language agreement. Preparation and readonly
`nex foreign foreign.json --json` execute no module or network operation. The
operator must start a service implementing the request/EOF/reply/EOF protocol.
The generated example sends `hello` and prints the encoded `result<bytes>`.
`--check-sdk` checks sources/signatures without compiling a native module;
`--diagnostics` adds bounded retirement counters to stderr. Both are explicit.

```nex
let answer:result<bytes>=tcp::execute(make_client(),
  tcp::request("service",utf8_bytes("hello"),4096,5000));
```

`Request` contains endpoint name, immutable bytes, declared reply limit and
timeout. `Client` contains a checked server callback. `client_context` wraps
that callback; neither value creates network authority. The generated callback
calls a pinned typed `exchange` export. Execution still requires the explicit
operator `--foreign` catalogue, the matching source pin and an allowed export.
Environment variables and source strings cannot supply grants. Modifying the
policy requires preparing a new module and updating its source binding pin.

## Execution and limits

The existing task/FFI bridge copies bounded arguments, then creates fresh C
tokens on an IO worker. The provider runs nonblocking TCP inline on that worker
and polls the owning task's original cancellation/deadline. It never forwards
live call tokens to another worker pool. A suspended request allows the single
CPU task worker to make progress. Native debug/release and independent AST
execution use the same explicit provider contract. Browser code cannot invoke it.

The module uses an owned `ResourceDomain` permit before copying the request or
opening a socket. Capacity defaults to16 and must be1..64 per loaded provider
instance; it is not a machine-wide quota. Permits remain occupied through
physical socket settlement and result construction. The root task/FFI pool has
its own independent limits: by default2 IO workers,8MiB reservations and4MiB per
prepared FFI call. Consequently at most2 such copied calls occupy that pool;
the provider limit alone does not promise64 simultaneous exchanges.

There are1..16 unique ASCII endpoint names, numeric IPv4/IPv6 addresses and
ports1..65535. DNS and scoped IPv6 addresses are rejected. Each body/reply limit
is at most512KiB; their combined declared size is at most1020KiB, leaving room
within the existing1MiB copied-value quota. A reply limit is positive. Exchange
timeouts are1..30000ms from provider preparation on its IO worker; the inherited
task budget also includes task/FFI queue time and may expire earlier. This
distinguishes the provider timeout from the kernel's own queue-inclusive host
API. Replies preserve arbitrary bytes; callers explicitly decode text.

Ordinary errors include `CAPABILITY`, `VALIDATION`, `LIMIT`, `E_NETWORK`,
`E_NETWORK_LIMIT`, `E_NETWORK_TIMEOUT` and `E_NETWORK_BUSY`. Parent task
`E_CANCELLED`/`E_TIMEOUT` keep their original fatal host diagnostics. Sockets
close before physical completion; cancellation does not undo bytes already sent.
There is no automatic retry or remote transaction guarantee. `statistics` gives
diagnostic `[opened,closed,live,maximum_live]` counters, not an atomic snapshot
across competing requests. Diagnostic retirement logging is off by default.

## Delivery and verification

Only reachable client/shared code enters TypeScript output. Server callbacks,
module pins and native endpoint policy must remain absent from emitted clients.
Use the existing native `nex package --foreign foreign.json --notices FILE
--directory NEW_PACKAGE` workflow with complete dependency provenance, then
execute the moved package on its intended host. The module retains the exact
compiled operator endpoints. Package assembly alone does not prove execution.

`tools/tcp_provider/verify.py` executes actual loopback IPv4/IPv6 exchanges in
AST, native debug and release: binary/size boundaries, rejected endpoints,
overflow/reset, own timeout and reuse, single-CPU progress, parent cancellation
and deadline, capacity pressure and physical retirement. `verify_delivery.py`
checks malformed/symlink/FIFO policy rejection, missing grants, export/pin/type
and bundle integrity, client exclusion and a moved package after deleting its
original source, graph, catalogue and provider image. Explicit output directories
retain logs and input identities. A source projection is not installed SDK
acceptance. Sanitizers of the private kernel do not instrument every C FFI call.

DNS, TLS, HTTP protocol clients, persistent connections, streaming/backpressure,
reactor multiplexing, finer copied-call reservations, async database drivers and
dedicated network debug/profile integration remain pending. So do matching full,
sanitizer, installed/moved SDK and broader platform acceptance for this provider.
The original language/toolchain objective remains open.

## Optional typed-host sanitizer matrix

The installed `tools/tcp_provider/sanitizers/run.py` builds the actual pinned
provider and a C++ host using the real typed C API, `PreparedTaskForeignCall`
and `TaskExternalPool`. Supply matching compiler/resources and platform C++20,
OpenSSL3, CMake and LLVM22.1 sanitizer runtimes:

```sh
python3 SDK/share/nex/tools/tcp_provider/sanitizers/run.py \
  --source SDK/share/nex --compiler SDK/bin/nex --output NEW_REPORT
```

The default matrix runs normal, ASAN/UBSAN and TSAN twice. Each mode executes
15 transport/authority cases and a separate capacity case per repetition:
32 checks and36 actual peer connections per mode. It covers copied input
snapshots, binary/IPv6/size boundaries, rejection before connection, overflow,
reset, timeout/reuse, IO overlap, cancellation, original parent deadline,
queued cancellation, physical grant revocation, late result admission and
abandoned-pool drainage. Every process must retire all opened sockets.

The test's operator catalogue explicitly permits two simultaneous lexical
module authorizations. It keeps the product preparer's default of one intact.
Scope destruction revokes both its logical context and physical domain; either
of these concurrent checks may reject in-flight work first. A completed result
must separately fail late admission with `E_FFI_SCOPE`. Revocation never becomes
an ordinary successful/error result. The capacity case limits the provider to
one live exchange, rejects an overlapping call without connecting, then checks
cancelled physical retirement before reuse.

The identical C++ host/kernel/module sources pass all six macOS ARM64 and Linux
ARM64 variants with192 check executions and216 actual connections. Reports
retain compiler, runtime/header, provider, wrapper and binary hashes, commands,
flags and diagnostics. The maintained wrapper additionally checks actual024
source task/FFI discovery and selects its advertised OpenSSL prefix.

This instruments the NEX C++ host/runtime and loaded provider, not the NEX
compiler or generated LLVM IR. Linux additionally enables LeakSanitizer;
macOS LeakSanitizer is unsupported and remains disabled. Platform/runtime
requirements and unsupported hosts are explicit. This optional matrix does not
replace the complete compiler/installed SDK/distribution acceptance workflow.
