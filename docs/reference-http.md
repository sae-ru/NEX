---
status: current
applies_to: "toolchain 0.271.0; language 0.30"
owner: repository
---

# Ordinary030 tasks in HTTP requests — development0.271.0

Checked030 native debug/release handlers may combine cells, structured tasks,
source errors and the existing server IO contracts. Each HTTP request retains
one thread-affine heap; its source continuations run cooperatively on that owner
thread. Concurrent HTTP requests own independent heaps. Physical IO workers keep
their raw completion/lease protocol and do not acquire cells.

Reference handlers with tasks select public native ABI8 and an explicit matching
owner-thread coordinator. Request, output and diagnostic boundaries retain their
existing immutable wire contracts. Uncaught cell-bearing source errors become
copied diagnostics before leaving the request context. Build metadata records
`reference_context.task_transfer:true` for these handlers; sequential handlers
retain false. This does not enable async database/network calls, persistent
application state, task-provider images or logical reference task debugging/
profiling. See [ordinary task qualification](reference-tasks.md).

The preceding sequential implementation and receipts below retain their original
scope. Current full SDK/platform acceptance remains separate.

# Sequential reference objects in native HTTP requests

Ordinary030 projects and C++ build APIs accept sequential `state` handlers in the
existing native HTTP adapter. For a C++ host, select a checked030 program, set `BuildOptions.target` to
`"server"` and select a server function with the ordinary signature:

```nex
server fn handle(req: http::Request) -> http::Response !{state} {
  let value: cell<str> = cell_new(req.body);
  let alias: cell<str> = value;
  cell_write(alias, cell_read(value) + "!");
  return http::text_response(200, cell_read(value));
}
```

The program imports `std/http.nex` through the normal checked module loader.
Archived `nex.sources/1` inputs include that library's actual `@std/http.nex`
source, as well as their application units. `nex.json` selects0.30 for ordinary
CLI builds; portable SDK delivery and full platform acceptance remain pending. The existing
028/029 server behavior and task ABI7 are unchanged.

## One request owns its reference graph

The adapter creates one thread-affine `RequestScope` for each authenticated
request. The generated reference dispatch bridge requires that scope, polls its
control state, and calls the checked handler without starting an application
wrapper or opening a nested request. Reference heaps are created lazily and
retire when their owning request closes. Concurrent requests have separate
heaps and ownership frames; they do not share cell state.

Within one request, source modules and compatible code-only native libraries
can exchange cells, retained immutable snapshots, closure captures and typed
source-error payloads under the [library ownership contract](reference-library-abi.md).
Static archive producers and consumers need matching target/profile/toolchain,
PIC/call-scope settings and the actual `libraryABI`. Reference-bearing task or
parallel execution still fails with `E_CELL_CONCURRENCY`. This is not a shared
mutable memory model or persistent application/UI object heap.

## Responses, errors and resources

The HTTP response keeps its existing immutable `std::http::Response` shape:
status, body and content type. A live cell or callable is not a response field.
Explicit wire encoding keeps i64 values as decimal strings; strict UTF-8 and
Unicode scalar operations retain their existing meanings, including embedded
NUL. Ordinary body-size/status/content-type checks are unchanged.

A source catch can read and mutate an error payload's cell while the request
is live. For an uncaught source error, the bridge copies code/message/source/
line, drops its live payload and releases the packet before propagating the
independent host diagnostic. The HTTP adapter then closes the request and emits
its existing `E_SOURCE_EXCEPTION` response. No live error payload is sent over
HTTP or retained by the diagnostic after request close.

Cells may retain owned file/external values under the existing resource rules.
Each request retains its normal filesystem, foreign and storage capabilities;
reference retention does not renew them. Closing a request retires its handles
and reference cycles, including cycles containing genuine file owners. Storage
commit/rollback still follows the ordinary response/error transaction boundary.

Budget exhaustion, deadline expiry and disconnect/shutdown cancellation use the
existing fatal path. They skip source finalizers, unwind generated ownership
and close the request before another request proceeds on that worker. Cell
operations poll cooperatively before/after work; collection has no hard
real-time interruption or pause guarantee.

## Build metadata and qualification

Reference HTTP builds record `reference_context.schema` as
`nex.reference-http-context/1` in their retained `build.json`. It describes the
request owner, thread affinity, independent heaps, copied errors and immutable
response boundary. Captured build inputs include the actual cell kernel/bridge
sources and headers. Warm reuse checks the retained completion record as usual.

`tests/reference_http.py` compares a shared logic module with reference and
strict executed TypeScript, builds normal and archive-linked Debug/Release
servers, and calls real local HTTP and HTTPS adapters. It includes handlers
with/without declared `throw`, concurrent requests, snapshots/captures/cycles,
caught/uncaught errors, file-owning cycles, storage rollback and fatal controls.
Invalid handler signatures and reference task contexts are explicit rejections.
Shutdown checks ordinary runtime value cleanup. This is focused functional
qualification; debugger/profile, full platform and portable-SDK gates remain
separate.
Foreign-resource HTTP adapters retain their separate matching-runtime
qualification; this matrix exercises genuine file owners.

По-русски: ссылочные объекты живут внутри одного HTTP-запроса. Его модули и
совместимые библиотеки видят одни и те же изменения, а другие запросы получают
отдельную память. В ответ и журнал ошибки попадают обычные независимые данные;
завершение запроса освобождает его ссылочный граф и ресурсы.
