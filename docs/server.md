# Private source exception HTTP experiment

The dedicated0.25-prototype emitter and trusted HTTP host are documented in
[source-exception-http.md](source-exception-http.md). They retain separate private
entry points. The public025 candidate now supports ordinary sequential/task source exceptions;
private experiment records retain their separate identities. Retained024 tools
keep their original contracts.

# NEX native server and runtime capabilities

Toolchain0.134.4 adds native language0.24 task HTTP handlers in debug/release.
For example, a `server fn handle(Request)->Response !{task,fs}` can schedule
structured CPU work and use whole-file/owned stream operations. The generated
server bridge calls the checked task descriptor rather than a synchronous
function or a standalone process entry. Requests keep the original HTTP
principal, step budget, deadline and disconnect/shutdown cancellation. Their
joined task executor drains admitted work and retires owned resources before
the ordinary HTTP response validation/transaction boundary.

Compile-time `--task-steps`, `--task-timeout-ms` and `--task-workers` embed
immutable ceilings. Launch-time `--nex-task-steps`, `--nex-task-timeout-ms` and
`--nex-task-workers` may only lower them; malformed, duplicate, unknown or
excessive values fail before startup. Existing HTTP `--budget` and
`--timeout-ms` are capped by those effective task limits. HTTP `--workers`
still sizes the request thread pool, separately from each joined task executor.
Ambient `NEX_TASK_*` variables do not select these limits.

In the public025 candidate, grant HTTP handlers file access explicitly with
`--files-root /absolute/existing/directory`. The server pins that directory before
workers start and creates a separate lexical FileScope inside each authenticated
request. It supplies the same capability to synchronous handlers and joined task
execution. Access is read-only by default; add `--files-write 1` to grant writes
or `--files-write 0` to require read-only access explicitly. A write option needs
one root option; duplicate/malformed options and non-directory roots fail before
listening. Images without a filesystem adapter reject a root grant.

For example, launch a matching file-enabled server image with:

```sh
./app --auth /private/auth.json --database /private/data.sqlite \
  --files-root /private/app-data --files-write 0
```

The explicit capability takes precedence over ambient `NEX_FILES_ROOT` and
`NEX_FILES_WRITE`. Effects alone grant no OS root. Without these flags,
synchronous HTTP handlers do not inherit CLI environment authority; the retained
task host's explicitly configured environment bridge remains available for its
original callers. Missing/read-only grants return Result errors at attempted IO,
including after a source exception. File writes do not share SQLite rollback.

The Mac development regression executes four debug/release sync/task images,
36 exception/read/read-only requests and eight explicit write-grant requests.
It also rejects24 invalid startup configurations. This establishes the tested
candidate scope, not installed SDK or cross-platform acceptance.
File effects cannot acquire socket/database authority. The existing HTTP
transport and SQLite transaction wrapper remain blocking; async network/DB,
streaming network responses, task-provider image linking into servers, task
HTTP profiling and logical task debugging remain pending. Profile/task-debug
builds fail explicitly rather than emitting an unverified server path. Retained
pre0.24 task HTTP builds remain rejected and require explicit migration.

The `task_http_server` integration test runs actual HTTP requests in both
profiles, including source-absent execution, two authenticated users, Unicode
and NUL bodies, concurrent requests, task file/stream IO, grant denial and path
containment, traps, budgets, deadlines and disconnect cleanup. Matching full
regression, installed SDK and platform delivery are separate acceptance gates.

Source language 0.4 adds recoverable results, typed JSON, environment access and a SQLite capability. Since toolchain 0.5.0, a checked handler can compile to a native HTTP/HTTPS server. Toolchain 0.6.0 connects browser applications through explicit request commands. The server uses cpp-httplib 0.61.0, OpenSSL 3 and SQLite; the executable does not need NEX, LLVM, a model or Node to run. Those native runtime libraries must be present on its host. See `STATUS.md` for the exact verified environment and tests.

## Build and launch

```sh
./build/nex token --user alice --auth /private/tmp/nex-auth.json --json
./build/nex build examples/server/main.nex --target server --profile release --json
```

The token command appends a SHA256 token hash and principal to a `nex.auth/1` file and returns a newly generated random bearer token once. The file contains hashes rather than raw tokens and is written atomically with owner read/write permissions. Keep the returned token for the HTTP client. Multiple tokens/users may be provisioned; removing an entry and restarting the server revokes it. Authentication configuration is loaded at startup.

Launch the executable path reported by build:

```sh
SERVER --auth /private/tmp/nex-auth.json --database /private/tmp/nex-tasks.sqlite --port 8080
```

The default bind address is `127.0.0.1`; `--host` changes it and `--port 0` allocates a port. Add `--cert CERTIFICATE.pem --key PRIVATE_KEY.pem` for HTTPS. Add `--static DIST_DIRECTORY` to serve a built browser client and an extensionless SPA route fallback. Point it at browser build assets; database, authentication file and TLS files must be outside that root. Static file paths stay within the configured root, including symlink resolution. Static/health routes are public; application `/api/` routes require a valid bearer token. CORS, cookie sessions and account registration are not implemented by this adapter.

`nex run FILE --target server -- --auth ... --database ...` builds and launches the server directly. Server run is long-lived and has no captured `--json` mode; `build --json` is available. SIGINT/SIGTERM stops acceptance, cooperatively cancels handlers and joins workers before checking managed-value cleanup. No deployment is performed.

For a client request, send `Authorization: Bearer TOKEN`. `/health` reports basic liveness. The included API example supports GET/POST/PUT/DELETE at `/api/tasks` and reports injected identity at `/api/me`. It validates request models with `decode_json<T>` and keeps committed tasks across restarts, partitioned by authenticated user. IDs use JSON strings, for example `{"id":"1"}`. `examples/fullstack/client.nex` and `server.nex` now share models and connect via the browser command contract in `docs/web.md`; `examples/web` remains the local-memory UI example.

## Handler contract

The selected entry defaults to `handle` and must have this signature:

```nex
import "std/http.nex" as http;
server fn handle(request: http::Request) -> http::Response !{db} { /* ... */ }
```

The compiler checks the exact library type layouts:

```nex
pub struct Request {
  method: str;
  path: str;
  query: str;
  body: str;
  user: str;
  request_id: str;
}
pub struct Response { status: i64; body: str; content_type: str; }
```

The host supplies method, decoded path, raw query, valid UTF-8 body, authenticated principal and a generated request identifier. JSON body fields cannot replace the principal capability. `http::json_response(status, encode_json(value))` and `http::text_response(status, text)` construct responses. Body validation and application rules belong in the handler; this adapter does not yet generate RPC dispatch/schema/client stubs automatically. Direct client-to-server calls remain forbidden.

Each request borrows a database capability and executes in a bounded runtime scope. Source cannot access or retain socket/connection pointers. Normal parameters are borrowed, results are owned, and the host releases its argument/result handles. The scope also reclaims all outstanding generated handles if execution traps. Native functions carry unwind tables so a trap can reach this boundary. An error is returned for that request, while other requests continue. This is runtime ownership for these capabilities; general source FFI/resource types remain pending.

The defaults are 8 workers, a queue of 64, a 1 MiB request/response body limit, one million function/loop polls and a 5-second handler deadline. Options are `--workers`, `--queue`, `--budget` and `--timeout-ms` within bounded ranges. HTTP read/write inactivity timeouts are separately five seconds; SQLite busy waits are bounded to one second. The URI limit is 2048 bytes, and regex-routed path length retains the upstream 256-byte limit. Function/loop polling checks deadline/budget and periodically checks disconnect/shutdown, with a forced cancellation check before commit. Cancellation is cooperative; a response lost after a successful commit does not imply rollback. Automatic mutation retries/idempotency are not implemented.

## Storage and transactions

```nex
server fn save(text: str) -> result<bool> !{db} {
  return store_put("document", text);
}
```

Keys are nonempty valid strings of at most 1024 bytes without NUL. Prefixes for `store_keys` may be empty and are matched literally, not as SQL patterns. Values are valid UTF-8 strings up to 1 MiB and may contain embedded NUL. Use typed JSON to store models. `store_get` returns `NOT_FOUND` for an absent key; `store_put` returns success true; `store_remove` returns whether a row existed; keys are ordered by SQLite binary collation and limited to 10,000 results.

All operations use prepared statements and a runtime-injected principal partition. A request cannot choose another user's partition by changing its JSON, a key or an ordinary Request value. The HTTP scope validates its database/principal immediately, but starts its SQL
transaction at the first `store_*` operation. A handler that never accesses the
KV store opens no transaction and takes no SQLite writer lease, including POST
handlers performing file/FFI/CPU work. GET/HEAD/OPTIONS start read transactions
and reject mutation. Other handled methods use `BEGIN IMMEDIATE` from their first
storage operation, so read/modify/write sequences retain a consistent serialized
writer transaction. The first storage operation can return `STORE_BUSY`; the
handler is never replayed automatically. The final commit of an unused scope
succeeds without issuing SQL. The existing three-argument runtime C++ Database
constructor retains eager transaction start for other hosts. A 2xx response commits after the final scope check; other statuses, traps, cancellation and storage mutation failures roll back. Ignoring a failed write cannot commit earlier partial writes. Missing-key reads are ordinary recoverable outcomes. SQLite WAL and per-connection FULL synchronous mode are used; conflicts/timeouts return `STORE_BUSY`, other SQL failures return `E_STORE`, and an already failed transaction returns `TRANSACTION_ABORTED`. The KV table shape and binary principal/key collation are checked; incompatible tables return `E_STORE_SCHEMA`. The host does not replay a handler after a failed/uncertain commit.

Outside an HTTP request, server-realm source may use storage from the interpreter/native CLI by setting a filesystem `NEX_DATABASE` path and optional `NEX_STORAGE_OWNER` (default `local`). In-memory/URI database modes are rejected for this durable capability. Each standalone operation is then individually atomic; a sequence of CLI calls is not one transaction. Missing configuration returns `CAPABILITY`. `read_env(name) !{io}` is also server-only and returns a result. Runtime configuration is not compiled into browser assets. Request budgets are cooperative checks, not a process or memory sandbox for arbitrary hostile native code.

Writer admission has a bounded wait and does not promise a fair queue. Concurrent
callers must handle `STORE_BUSY` rather than assume every attempt commits. Native
conformance accounts for each contending attempt as either a committed mutation
or a busy rejection before source execution, then checks the durable counter
against successful commits. A separately held writer forces the rejection path;
no mutation is retried automatically and the one-second SQLite timeout is unchanged.

## Native runtime archives

`nex build FILE --library --entry NAME` creates a native static archive containing the selected function's reachable closure and only the runtime components it needs. No C main wrapper is generated. A trusted C++ host can use the matching installed `runtime/nex_host.h`, the symbol reported by `nex context`, and request scopes to contain traps. Heap arguments/results use opaque handle pointers; immutable values may be read by trusted host helpers. Release owned handles or let their request scope reclaim them. This is an internal/version-matched host ABI, not source-level unsafe FFI syntax or a stable ABI promise across versions. Storage consumers additionally link the configured SQLite library. Target selection and target-specific dependencies use `--target TRIPLE` or `--toolchain FILE` from the native build guide; the host embedding the archive must match its architecture/runtime ABI.

Native builds cache runtime component objects by captured source/header contents, compiler/profile/target and relevant native dependencies, checking object integrity. Exact runtime input projections accompany compilation, so edits to live runtime sources do not alter a build already in progress. NEX function compilation remains whole-program for the selected closure; separate NEX compilation is still pending.

Build JSON reports `kind` (`executable`, `static_library` or `http_server`), `metadata` and `notices`. Metadata records selected runtime components and their captured input directory. Native outputs that embed nlohmann/json or cpp-httplib include the full matching MIT license texts in `THIRD_PARTY_NOTICES.txt`; `-o PATH` copies these to `PATH.THIRD_PARTY_NOTICES.txt`. Distribute the companion notices with those outputs. Pure programs omit them. This does not package external SQLite/OpenSSL libraries or their distribution requirements; portable SDK/runtime dependency bundles remain pending.

## Exact cross-origin API configuration

Toolchain0.63 adds optional repeated `--cors-origin ORIGIN` (maximum16 exact
origins). Without it the existing server behavior is unchanged. With it,
allowed API responses carry that exact Origin and `Vary: Origin`, including
401/errors. Approved OPTIONS preflight validates the method and requested
Authorization/Content-Type headers without entering NEX or a transaction.
Other API calls still require the runtime Bearer token. Disallowed origins are
rejected before authentication/body buffering or mutation. Same-origin browser
calls and clients without Origin retain their normal authenticated behavior.
Wildcards, `null`, credentials, paths and cookies are unsupported. See
[mobile API setup](mobile-api.md) for the origin format and TLS requirements.
SDK0.134.4 delivery additionally requires the installed `structured-task-http`
phase. It checks HTTP and verified HTTPS task servers in both profiles, actual
retained responses, explicit File grants, disconnect E_CANCELLED and clean
server shutdown. See sdk.md for its37-phase contract and the separate
compiler-source fallback isolation requirement. Source syntax and the runtime
HTTP adapter are unchanged by this SDK delivery update.

