# Public025 integration candidate

Preparation accepts matching public0.24/0.25 compiler, doctor and language-pack
cohorts and computes fresh FFI signature pins for that cohort. It does not
migrate or retag archived source. Generated025 scope/join regressions explicitly
declare throw;024 fixtures retain their original effects. Source preparation,
actual networking and complete installed delivery remain separate gates.

# HTTP response streams (source prototype)

`std/http_stream.nex` is an ordinary server resource library for language0.24.
The compiler must advertise source resources, owned task/FFI transport and task
file streams. The source preflight uses SDK0.135.7. The development0.135.8 source registers
http_response_streams and the http-stream guide; actual compiler/SDK acceptance
is recorded separately.

A Request has authority/method/url/headers/body, total_limit/timeout_ms,
redirect_limit/protocol. Request bodies remain bounded to512KiB. The total
response limit is1..1GiB and the original request timeout is1..30000ms, including
DNS, redirects and time between reads. The source helper uses the same ordinary
HTTP request validation and operator policy as the buffered client.

The provider opens through a granted typed factory and returns Response with
status, individual byte-valued headers, Body, protocol and canonical URL.
Read returns Chunk(data,done), with at most the requested1..65536 bytes; short
reads are valid. EOF permits repeated empty done reads until logical close.
The Body is an immutable alias to one cursor. Explicit close affects all aliases.
A private mutex serializes reads; callers must sequence tasks when ordering
matters. Native call-local tokens and polling closures are not retained between
calls. The connection and private curl buffers are retired at EOF/close; the
logical object/capacity remains until close or owning scope cleanup.

With --diagnostics, the provider records simultaneous read-call admission on
stderr. Its development statistics retain their first10 counters and append
reads started/finished/current/peak at indices10..13. These describe physical
provider calls, including readers waiting for the cursor mutex; they do not
claim simultaneous mutation of one curl handle or source CPU parallelism in the
cooperative AST interpreter. Each call still obtains fresh C tokens.

The pending body slot is at most CURL_MAX_WRITE_SIZE (16KiB in the pinned
build). A full slot pauses curl delivery; a later read resumes it. This bounds
the adapter staging slot, not all dependency/OS buffers or application-retained
chunks. There is no background progress while a caller leaves a paused Body
idle, and no shared connection pool or general reactor.

`download(ctx,request,path)` reads and writes chunks with task file operations,
handles partial writes, explicitly flushes/closes the file and closes Body.
Only2xx responses create/truncate the destination. An explicit writable file
root is required. Errors can leave a partial/truncated destination; the helper
promises neither rollback nor an atomic rename.

The operator preparer is tools/http_stream_provider/prepare.py with --sdk,
--targets, --http-prefix and a fresh --output. It builds a separate pinned module
with open/read/statistics, resource_limit64/resource_bytes64MiB, and the existing
explicit HTTP policy. Use the emitted foreign.json on eval/run/package.

Combined ordinary source preflight receipts pass36 cases per platform on
macOS ARM64 and Linux ARM64: HTTP1, HTTPS/HTTP1 and HTTPS/HTTP2, each with
AST/debug/release large reads, EOF, early close, downloads and child-to-parent
task handoff. The2MiB+17byte downloaded files are compared byte for byte.
HTTPS peers independently record the negotiated protocol. The verifier accepts
--transport http1|https1|https2 and either --sdk or --compiler plus --resources;
CMake exposes its functional groups only with an explicit NEX_HTTP_PREFIX.
The continuation preflight on the actual0.135.8 SDK adds9 simultaneous-reader
cases per platform across all three transports and AST/debug/release. A moved
HTTPS2 download application also passes after deletion of its original project
and public CA, including byte-for-byte file and complete license comparison.
Current matching compiler/SDK acceptance and broader platforms are separate
gates. No security acceptance is claimed.

The concurrent-reads case holds the peer body until two actual provider calls
are observed, then checks both returned chunks in their cursor order and reads
the rest to EOF. Native debug/release images are launched directly after normal
compiler builds so the observer can read stderr immediately; `nex run --json`
returns the native child's collected journal only after execution ends.

The positive --package scenario builds a regular download application, moves
the completed directory, removes its owned source project and the original
public CA file, then compares the downloaded file with all peer bytes. Full
static dependency licenses are retained. It performs no authority rejection or
security audit campaign. File access still uses an explicit writable root.

For a prepared matching SDK and dependency prefix:

```sh
nex describe --field http_response_streams --json
python3 /path/to/sdk/share/nex/tools/http_stream_provider/prepare.py \
  --sdk /path/to/sdk --targets /path/to/targets.json \
  --http-prefix /path/to/http-prefix --output /path/to/new-project
cd /path/to/new-project
nex context --symbol std::http_stream::read --json
nex eval --foreign foreign.json --json
nex run --foreign foreign.json --profile release --json
```

The preparer emits an executable read-loop example and the actual pinned
bindings. Its selected URL must match the explicit operator policy; see the
http-client guide for building the pinned dependency cohort and targets schema.
Keep those generated bindings when replacing main with a download loop.
Downloads declare task/ffi/fs and additionally require operator-selected
NEX_FILES_ROOT and NEX_FILES_WRITE=1 when running the application. Commit the
application's source, manifests, lock and reviewable provider policy; keep local
SDK paths, generated binaries and private operator credentials out of Git.
