# Task HTTP client

The development HTTP adapter uses ordinary language0.24 server `task,ffi`
callbacks and `std/http_client.nex`. It adds no syntax, effect, source ABI or
network builtin. This working candidate is separate from the primary0.81 SDK.
Compiler capability/guide/resource/CMake registration is implemented. Its new
compiler build, full regression and installed delivery acceptance remain pending. Discover actual installed capabilities
before using the adapter in an application.

## Prepare explicit authority

The operator builds pinned static PIC curl8.23.0, nghttp2 1.70.0 and c-ares1.34.9
for the selected host SDK. OpenSSL remains the selected SDK's separately linked
dependency. Matching64-bit macOS/Linux hosts are the intended initial targets.

```sh
python3 SDK/share/nex/tools/dns_provider/build_dependency.py --output NEW_CARES
python3 SDK/share/nex/tools/http_provider/build_dependency.py \
  --sdk SDK --cares-prefix NEW_CARES/prefix --output NEW_HTTP
```

Use absolute paths. Both builders require CMake and a matching C compiler. The
HTTP builder accepts `--curl-archive FILE --nghttp2-archive FILE` for offline
builds and checks exact release sizes and SHA-256. It preserves original and
effective source inventories, complete licenses and patch documents. It does
not claim PGP verification or upstream test execution. The c-ares macOS
alignment patch is described in the DNS guide. A recorded curl patch removes
ambient `SSLKEYLOGFILE` access; HTTP clients must not gain file authority from
that environment variable.

Create an operator-owned policy. Replace the illustrative domain, resolver and
public CA file with deployment values. The preparer validates the full policy;
the companion JSON schema describes its shape.

```json
{"schema":"nex.http-targets/1","maximum_calls":16,
 "resolvers":[{"address":"127.0.0.1","port":5353}],
 "ca_file":"./public-roots.pem",
 "authorities":[{"name":"backend","domain":"api.example.com",
   "subdomains":false,"schemes":["https"],"ports":[443],
   "methods":["GET","POST"],"cross_origin_redirects":false}]}
```

```sh
python3 SDK/share/nex/tools/http_provider/prepare.py --sdk SDK \
  --targets targets.json --http-prefix NEW_HTTP/prefix --output NEW_PROJECT
cd NEW_PROJECT
SDK/bin/nex run --foreign foreign.json --profile release --json
```

The preparer checks actual compiler/doctor/language-pack identities, source
types and typed export signatures. It captures the runtime, source library,
policy, CA bytes, static libraries, headers and complete dependency notices,
builds a hidden-symbol module and pins the complete foreign bundle. Readonly
catalogue checks and preparation do not initialize the module or send requests.
`--check-sdk` checks the source/signature contract without dependencies;
`--diagnostics` enables bounded retirement counters.

The generated program supplies a checked callback and operator catalogue:

```nex
let response:httpc::Response=unwrap(httpc::get(make_client(),"backend",
  "https://api.example.com/items",1000));
let text:str=unwrap(httpc::text(unwrap(httpc::require_success(response))));
```

`Client`, `Request`, `Header` and `Response` are ordinary immutable values. A
client callback or request alone grants no OS authority. Execution requires
the explicit foreign catalogue, correct source/bundle pins, granted export
and compiled operator policy. Credentials are supplied explicitly in request
headers; the adapter reads neither cookies nor credentials from the host.

## Values, HTTP and TLS

`request(authority,method,url,body,timeout_ms)` selects a262144-byte reply limit,
zero followed redirects and protocol `auto`. `with_header` adds a text header;
`limits` selects a smaller/larger reply bound, redirect limit and protocol.
`execute` checks the ordinary source request before invoking the callback. The
native provider independently checks raw requests, including calls that bypass
the source helper. `get` and `post` are convenience operations.

URLs require explicit HTTP/HTTPS schemes and ASCII transport spelling. Use
`url_component` to percent-encode UTF-8 path/query component values. It does
not build a whole URL or perform IDNA conversion. Explicit A-labels are required
for international hostnames. Userinfo and scoped IPv6 URLs are rejected.
Names are canonicalized and matched exactly or at a strict subdomain boundary.
An operator may explicitly grant `*` with `subdomains:true`. Literal addresses
are permitted only by the selected authority; unspecified, multicast and
broadcast target addresses are rejected. Resolver configuration uses1..4 unique
numeric unicast addresses, with no system DNS/search/hosts-file fallback.

Only the selected authority's scheme, port and case-sensitive method are
allowed. `CONNECT` is unavailable. The adapter resolves granted names with
c-ares, pins those answers into the individual curl handle and checks opened
sockets against their addresses and port. DNS answers are used for this
request; they create no separate persistent connection authority.

Request/response bodies are bytes, including NUL and invalid UTF-8. Response
headers preserve individual fields and opaque value bytes, including repeated
fields. `text` applies strict UTF-8 decoding. `json<T:wire>` applies NEX's strict
wire JSON rules, including string-encoded i64; it is not an untyped external
JSON-number coercion. HTTP4xx/5xx are ordinary responses; `require_success`
explicitly converts non-2xx status into `HTTP_STATUS`.

HTTPS verifies the certificate chain and hostname against the captured public
CA bundle. There is no automatic system trust, fallback insecure mode or client
certificate API. `auto` negotiates HTTP/2 over TLS when offered; `1.1` requests
HTTP/1.1; `2` selects curl's HTTP/2 prior-knowledge mode. HTTP/2 connection reuse,
h2c interoperability and persistent stream delivery require separate acceptance.
Ambient proxy, netrc, TLS keylog and CA variables do not grant authority. Content
decompression is disabled; callers receive the bounded encoded body.

Redirect following defaults to disabled, returning the3xx response. The caller
may allow0..8 hops. Each hop is reauthorized and resolved under the same total
request deadline. HTTPS-to-HTTP downgrade is rejected. Origin changes require
the operator's explicit `cross_origin_redirects:true`; authorization, cookie,
origin and referer headers are removed when the origin changes. POST301/302 and
non-HEAD303 change to GET with an empty body and removed content headers.
Redirect cycles exhaust the hop bound. There is no application retry policy.

## Tasks, limits and cleanup

The provider drives a private curl multi event loop on the existing task/FFI
IO worker. It checks original parent cancellation/deadline at most each20ms
poll interval, subject to scheduling and dependency work. It closes its curl
handles, sockets and DNS channel before publishing physical completion. The
source scope waits for that retirement. Cancellation cannot retract a request
or undo a server-side operation already performed.

Own timeout1..30000ms begins on the IO worker and includes DNS, TLS and redirects.
The inherited task deadline includes queue time and can expire sooner.
`VALIDATION`, `CAPABILITY`, `E_DNS`, `E_DNS_LIMIT`, `E_HTTP`, `E_TLS`,
`E_HTTP_LIMIT`, `E_HTTP_TIMEOUT`, `E_HTTP_REDIRECT` and `E_HTTP_BUSY` are ordinary
result errors. Original parent `E_CANCELLED`/`E_TIMEOUT` remain fatal host
diagnostics. Header/body conversion and allocation failures preserve their
existing FFI/runtime diagnostics.

Request and reply bodies are each bounded by512KiB; their combined copied
request/reply budget, including reserved response headers and metadata, is
1020KiB. There are at most64 request fields and64 response fields, with64KiB
header budgets; request field names are1..128 bytes and values at most8192.
Transport-owned headers, CR/LF injection and other control bytes are rejected.
The response header bound also accounts for intermediate HTTP status blocks.
URLs are at most8192 bytes, methods1..32 token bytes, authority names1..64 bytes.
The connection callback tracks at most16 sockets per hop. Dependency-internal
allocations are separate from NEX's copied-value reservations.

Per-module simultaneous call capacity defaults to16, configurable1..64, and
stays leased through result construction. The source FFI pool independently
has2 IO workers and8MiB reservations, at most4MiB per call. Capacity is not a
machine-wide quota or a promise of64 concurrent source calls. Diagnostic
statistics are `[dns_opened,dns_closed,dns_live,dns_maximum_live,
sockets_opened,sockets_closed,sockets_live,sockets_maximum_live]`; independent
atomic counters do not provide a simultaneous snapshot.

`tools/http_provider/verify.py` exercises actual AST/native debug/release
clients against owned loopback DNS, HTTP/1.1 and HTTPS/HTTP2 peers. Its checks
include binary bodies/headers, HTTP status, redirect policy, credentials,
authority rejection before DNS, own timeouts, single-worker progress,
in-flight parent cancellation/deadlines, occupied capacity and physical
retirement. A passed report states its exact compiler and captured inputs.
Source preflight does not establish a final current compiler or installed SDK.

The source candidate passes90 cases on macOS ARM64 and90 on Linux ARM64 using
the verified0.135.6 SDK:30 scenarios in AST/native debug/native release. These
include physical retirement on HTTP/1.1 and HTTP/2 cancellation/deadlines.
The corresponding delivery preflight on each host rejects18 foreign authority
violations, checks client pruning and realm rejection, and executes an actual
relocated HTTP/HTTPS package after deleting its project and original CA file.
All three complete static dependency licenses and source records survive.
These are source-provider preflight receipts, not a new0.135.7 compiler/SDK
release acceptance or actual non-ARM64 hardware acceptance.

## Typed host and dependency sanitizers

The maintained `tools/http_provider/sanitizers/run.py` accepts a frozen source
directory, compiler and the three pinned offline public release archives. It
builds separate normal, ASAN/UBSAN and TSAN cohorts. Each cohort instruments
the13 runtime translation units, typed host, actual pinned provider module and
static curl/nghttp2/c-ares. Actual compiler-generated signatures and the normal
foreign catalogue/binding/task-copy/admission path are used; the host does not
call transport helpers in place of the FFI boundary.

The source cohort passes126 case executions on macOS ARM64 and126 on Linux
ARM64:21 checks, two repetitions, three modes. Checks include copied record/body
snapshots, binary HTTP, HTTP2 repeated headers, hostname rejection, IPv4/IPv6,
limits, own HTTP/TLS timeouts, overlapping IO, HTTP/HTTP2 cancellation and
original deadlines, queued cancellation, scope/module revocation, late result
admission, abandoned pools and occupied capacity/reuse. Managed values, file
descriptors, IO reservations and physical DNS/socket retirement are checked.
The workflows verify sanitizer hooks in all three static dependency archives.
Linux leak detection is enabled; macOS leak detection is disabled.

The selected OpenSSL binary, NEX compiler and generated NEX IR are not
instrumented by this receipt. Fuzzing, malicious HTTP2/TLS peer campaigns and
complete dependency instrumentation remain separate gates. Normal/reference
NEX source execution and this typed host receipt retain their distinct scopes.

`check_inputs.py --http-prefix PREFIX --output NEW` runs48 malformed-policy
checks and9 incompatible dependency-cohort checks without network IO or module
initialization. It preserves rejected inputs and tool identities. Preparation
also checks full release/patch/license identities and actual selected file
hashes. The dependency record is operator-selected provenance; it is neither
a signature of a trusted build nor permission to initialize arbitrary code.

Native modules currently execute in the application process. Their source
policies and copied-value reservations do not sandbox arbitrary C/C++ behavior
or bound every vendor allocation. Untrusted providers require a future separate
process/OS sandbox. A public-URL policy must additionally constrain private,
loopback and metadata address ranges; a domain allowlist alone is insufficient.

Final current-compiler/installed-SDK acceptance, Windows/mobile targets, automatic
IDNA, persistent streams/backpressure, shared connection pools/reactor,
network debug/profile, finer dependency-memory quotas and async database
drivers remain pending. This adapter does not complete the full NEX objective.
