# Private source exceptions in HTTP handlers

Toolchain0.135.22 extends the explicit `0.25-prototype` task experiment.
Discover `source_exception_prototype.private_task_native_http_*`. Public projects
remain language0.24; ordinary build/project commands reject private025.

`emitSourceExceptionTasksPrototypeNativeHttp` checks a server handler declaring
`task` with exactly `std::http::Request -> std::http::Response`. The same layout
validator serves public and private HTTP emission. It emits reachable native
task descriptors and source sites, without a standalone process main.

```nex
module example;
import "std/http.nex" as http;
server fn handle(req:http::Request)->http::Response !{task} {
  try {
    task_yield();
    throw("INVALID", req.body);
  } catch(code,message) {
    return http::text_response(400,code+":"+message);
  }
}
```

An uncaught source error requires declared `throw`. Server task/fs and task/ffi
handlers can use the file and opaque-resource bridges from
[source-exception-host.md](source-exception-host.md). Calls, futures, lexical
rethrow and scope drain preserve the original error payload and producing site.

The trusted host calls `executeSourceExceptionTaskHttpRequest` with its existing
RequestScope, borrowed Request and captured host context. The configured variant
`executeConfiguredSourceExceptionTaskHttpRequest` captures the operator's file
and foreign configuration inside that request. The joined executor inherits its
budget, deadline and cancellation and drains admitted work before returning or
propagating an error. It does not replace the parent RequestScope. A handled
source error can return a normal Response. Returned file/resource owners keep
the existing region rules; HTTP Request/Response remain ordinary wire records.

Private2501 pure images and2502 host images are accepted only by these private
entry points. The public HTTP entry still requires ABI5 and retains its existing
behavior. A matching C++ bridge supplies the descriptor and compiled task limits
to the existing HTTP adapter. This is a version-matched experimental embedding;
there is no public private025 server build option or installed SDK promise.

The private HTTP adapter is compiled explicitly with `NEX_SOURCE_EXCEPTION_HTTP`.
Uncaught source failures produce HTTP500 with generic `E_SOURCE_EXCEPTION`.
The server journal retains exact code/message, original native source site and
request ID. A source code such as `E_TIMEOUT` remains user data. Actual runtime
deadlines, budget failures and cancellation retain504,429 and499 behavior and
bypass source catches. One failed request does not terminate the server. The
normal database transaction wrapper and response validation still enclose the
handler; source task database operations remain unsupported.

`source_exception_http_request_host` checks the trusted runtime boundary,
private/public ABI separation, inherited control, repeated recovery, eight
concurrent requests and owned cleanup. `source_exception_http` compares AST
and TaskIR outcomes with actual compiled O0/O2 HTTP and HTTPS servers. It uses
valid local requests to check catch/rethrow, source-site diagnostics, file/FFI
owners, future delivery, promotion, Result, runtime traps, client disconnect,
deadlines and subsequent requests. Selected source/context files are absent
during execution. These are ordinary functional tests. Security-specific checks
remain deferred at the user's request.

Source-backed binary providers, public025 publication/history migration,
full compiler/SDK/platform acceptance, HTTP profiling and logical debugging,
asynchronous database/network transport and streaming responses remain pending.
This experiment does not complete the original language/toolchain objective.
