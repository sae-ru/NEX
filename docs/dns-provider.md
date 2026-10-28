# Public025 preparation candidate

The source preparer now accepts matching compiler/doctor/language-pack cohorts
for public0.24 and0.25. It generates the selected cohort's project and computes
its actual FFI signature hashes. It does not relabel an old project or pin.
The current `--check-sdk` checks are distinct from provider initialization,
network execution, packaging and complete installed SDK acceptance.

# Task DNS provider

Development toolchain0.135.6 adds `std/dns.nex` and a pinned native c-ares
provider for matching64-bit macOS/Linux hosts. It uses existing language0.24
server `task,ffi` callbacks. Syntax, effects, source identities and ABI are
unchanged. Discover `nex describe --field dns_provider --json` and
`nex guide --kind dns --json` on the actual compiler.

## Prepare

Build the pinned public c-ares1.34.9 static PIC dependency in a new directory:

```sh
python3 SDK/share/nex/tools/dns_provider/build_dependency.py --output NEW_CARES
```

This explicit action downloads the official1.08MB archive, checks its pinned
SHA-256, validates/extracts regular bounded source files and builds with CMake.
`--archive FILE` uses the same verified bytes offline. CMake and a host C
compiler are prerequisites. The resulting `NEW_CARES/prefix` contains static
code, headers, complete MIT license and source identity. The builder checks the
GitHub release digest; it does not claim PGP verification or upstream test runs.
On macOS the builder applies the recorded NEX byte-addressed pointer-copy
patch to `ares_sysconfig_mac.c`. Fully instrumented c-ares exposed an alignment
UB while reading Apple packed DNS pointer arrays. The patch preserves pointer
bytes and changes no DNS policy; ASAN/UBSAN/TSAN remain enabled. The builder
checks complete original/patched file hashes and preserves both upstream and
effective source manifests. The exact patch document travels in the dependency
source record. macOS preparation rejects older unpatched prefixes. Linux uses
unmodified upstream source.

The dependency is separate from the base NEX SDK. It is statically linked into
the prepared module, so deployed applications do not need a c-ares installation.

Use operator-owned policy. The following illustrative resolver must be replaced
with the actual service selected for the deployment:

```json
{"schema":"nex.dns-targets/1","maximum_calls":16,
 "resolvers":[{"address":"127.0.0.1","port":5353}],
 "authorities":[{"name":"public","domain":"example.com","subdomains":true}]}
```

```sh
python3 SDK/share/nex/tools/dns_provider/prepare.py --sdk SDK \
  --targets targets.json --cares-prefix NEW_CARES/prefix --output NEW_PROJECT
cd NEW_PROJECT
SDK/bin/nex run --foreign foreign.json --profile release --json
```

Use absolute SDK/dependency paths when changing directories. Preparation checks
the actual compiler/doctor/language pack, the source library and exact typed
export signatures. It captures dependency/header/license bytes, compiles the
operator policy, links static c-ares with hidden symbols and pins the complete
module bundle. Preparation and readonly `nex foreign` perform no DNS lookups or
module initialization. `--check-sdk` checks source/signatures without requiring
the dependency; `--diagnostics` adds bounded channel-retirement counters.

The generated `make_client()` supplies a checked callback:

```nex
let answer:result<list<str>>=dns::lookup(make_client(),"public","api.example.com",1000);
```

`lookup` selects an answer limit of64. Use `execute(ctx,
request(authority,hostname,answer_limit,timeout_ms))` for a smaller bound. `Client`
and `Request` are ordinary immutable values; neither creates OS authority.
Execution additionally requires the explicit operator foreign catalogue,
matching source/bundle pin, granted export and compiled domain/resolver policy.

## Policy and behavior

There are1..4 unique numeric unicast resolvers and1..16 uniquely named domain
authorities. Resolver ports are1..65535. Scoped IPv6, unspecified and multicast
resolver addresses are rejected. A domain permits itself and, when requested,
its strict dot-boundary subdomains. `evil-example.com` does not match
`example.com`. A literal `*` with `subdomains:true` explicitly grants all names.
Authority names are case sensitive; DNS names are lowercased and may have a
final root dot. Labels contain ASCII letters/digits/internal hyphens,1..63
bytes each, with at most253 bytes before the root dot. Use explicit IDNA
A-labels for international names; Unicode-to-IDNA conversion is pending.

Each call has its own resolver channel. Queries use only compiled servers,
DNS lookups without search domains/host aliases/hosts-file fallback, and no
cross-call cache. CNAME resolution belongs to the granted lookup. Returned
IPv4/IPv6 addresses are canonical strings, deduplicated and lexicographically
sorted. Address sorting never probes the returned addresses: `ARES_AI_NOSORT`
disables those c-ares connections. Results do not grant TCP/HTTP access.

The provider runs its event loop inline on the existing task/FFI IO worker.
Fresh C tokens stay on that worker; c-ares callbacks retain only private host
state. No c-ares event thread is enabled. Polling checks the original parent
cancellation/deadline. Each channel is destroyed and its sockets closed before
physical completion, including timeout/cancellation/error exits. Source scope
completion still waits for physical IO retirement; cancellation cannot unsend
queries already transmitted.

Answer limits are1..64; excess results fail rather than truncate. The adapter
checks at most512 address nodes and tracks16 socket-event entries per channel;
overflow closes the channel with `E_DNS_LIMIT`. The dependency's internal heap
is separate from NEX copied-value reservations. Per-provider simultaneous-call
capacity defaults to16, configurable1..64, and remains leased through result
construction. The existing source FFI pool independently allows2 IO workers
and8MiB reservations with4MiB per call. The provider limit is not a machine-wide
quota or a promise of64 simultaneous source calls.

The own timeout is1..30000ms from entry into the resolver on its IO worker;
the inherited task budget includes queue time and may expire earlier. Ordinary
errors include `VALIDATION`, `CAPABILITY`, `E_DNS`, `E_DNS_LIMIT`,
`E_DNS_TIMEOUT` and `E_DNS_BUSY`. Original parent `E_CANCELLED`/`E_TIMEOUT`
remain fatal host diagnostics and are not converted into DNS result errors.
`statistics` exposes diagnostic `[opened,closed,live,maximum_live]` channel
counters, without an atomic cross-counter snapshot guarantee.

## Verification and pending delivery

Configure `-DNEX_CARES_PREFIX=/absolute/NEW_CARES/prefix` to register actual
`task_dns_source` and `task_dns_delivery` CTest checks. Without that explicit
dependency selection, only `dns_policy` and portable `dns_library` are registered;
this is not an operational DNS acceptance result. `verify_delivery.py` rejects
malformed policies and foreign grants/pins/signatures, checks client isolation,
then executes a relocated package after deleting its original project.


`tools/dns_provider/verify.py` uses owned loopback UDP/TCP name servers and
actual AST/native debug/release execution. Cases include both address families,
deduplication, explicit wildcard/exact/suffix policies, malformed requests,
NXDOMAIN, excessive answers, TCP fallback, wrong-source/transaction replies,
own timeout/reuse, single-CPU progress, parent cancellation/deadline, capacity
and physical channel retirement. It performs no external DNS queries.

Initial source preflight passes45 cases per macOS/Linux ARM64 host using the
verified0.135.4 compiler and the new provider sources. This does not establish
the current0.135.6 compiler, sanitizer, installed/moved SDK, package delivery or
broader platform acceptance. Only reachable client/shared code may enter web
output. Server pins and operator policy must remain absent from emitted clients.

TLS/HTTP clients, DNS integration into TCP connections, automatic IDNA,
DNSSEC/DoT/DoH, cache/reused-channel/reactor policies, finer copied-call quotas,
network debug/profile, async database drivers and broader platform delivery
remain open. The original language/toolchain objective is not complete.

## Typed runtime and dependency sanitizers

`tools/dns_provider/sanitizers/run.py --source SOURCE --compiler NEX
--cares-archive ARCHIVE --output NEW` builds normal/ASAN-UBSAN/TSAN typed C-API
hosts, actual pinned modules and a separately instrumented c-ares per mode.
It uses only owned IPv4/IPv6 loopback DNS servers. `--repeats` defaults to2;
`--modes` selects explicit modes. The compiler and generated NEX IR are not
instrumented. Linux enables leak detection; macOS leak detection remains off.
Checks cover input snapshots, canonical A/AAAA/deduplication, TCP fallback,
forged replies, explicit authority/limits, NXDOMAIN/answer bounds, own timeout,
coordinator progress, queued/in-flight cancellation, original deadlines, nested
scope/late admission, abandoned pools and module revocation. Managed values,
IO reservations, file descriptors and channel retirement are checked.

Exact208 runtime/module/library inputs passed120 normal/ASAN-UBSAN/TSAN Linux
case executions, with138 channels retired. macOS original unpatched c-ares
failed UBSAN; the recorded diagnostic patch passed80 ASAN-UBSAN/TSAN cases.
Those records establish the dependency fix, not yet the final209 installed SDK
or matching new-builder/package/platform acceptance.
