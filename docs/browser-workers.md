# Typed browser worker jobs — toolchain0.97 development

The browser adapter accepts two additional ordinary pure client/shared entries:

```nex
client fn worker_compute(input: Input) -> Output { /* pure computation */ }
client fn worker_commands(before: State, after: State, event: web::Event)
  -> list<worker::Command<Input>> { /* pure descriptions */ }
```

The typed list<worker::Command<Input>> return of worker_commands opts into this
contract and requires worker_compute. Old ordinary helpers using either name
remain valid when they do not return this new nominal command type.
Import `std/worker.nex`. Input and Output
must pass the existing strict wire schema rules: checked i64, finite f64,
Unicode scalar strings, bytes, immutable lists/records/enums/results. Functions,
file handles and unit cannot cross this boundary. The compiler checks the exact
generic command input against the compute argument and validates library layout.
Empty effects and the existing realm checker prevent server/IO/FFI capabilities.

`worker::request(id, input, action, timeout_ms)` describes work. The adapter runs
it in an actual dedicated module Worker and delivers a normal web event to
update. `worker::response<Output>(event)` returns `result<Response<Output>>`;
the response has `id: str` and `value: result<Output>`. Check both results and
the current request ID. If Output is itself a result, its application failure
remains inside a successful transport result. Source tests only construct these
values and execute pure compute; they do not launch background workers.

The main and worker closures are emitted separately. Each contains only its
reachable client/shared code, nominal models and mapping metadata. The worker
does not import the React/UI module. Main code does not contain the compute
body unless it explicitly calls/references that function too. Archived source
bundles remain development data and do not enter deployed assets. Existing
locked npm versions and third-party notices are unchanged. Vite handles the
[static module-worker URL](https://vite.dev/guide/features.html#web-workers).

At most2 jobs execute and32 may be pending; one event describes at most64
commands. IDs/actions are nonempty scalar strings up to128 UTF-8 bytes without
control characters. IDs cannot be reused while pending or awaiting delivery.
The whole worker batch, and both network/worker batches in the application
event, are validated before an external action. Inputs/outputs use the strict
1MiB wire codec; nested response envelopes may hit that limit earlier.

Timeout is1..60000ms from acceptance, including queue/startup time. Each running
job has its own worker. `worker::cancel<Input>(id)` and
`worker::cancel_all<Input>()` terminate the affected dedicated workers and
deliver `E_CANCELED`. Queued jobs never start if canceled/expired. Host timers
produce `E_TIMEOUT`; timer scheduling is not a real-time guarantee. Worker
termination is safe here because the checked worker has no file/FFI authority
or shared mutable NEX state. It is not a native-thread cancellation policy.

Checked compute traps preserve their error code. Startup/runtime worker errors
produce `E_WORKER`; malformed/wrong-ticket/invalid-output messages produce
`E_WORKER_PROTOCOL`. A completion is delivered at most once. Close/unmount
terminates remaining jobs and suppresses late messages/events; stale messages
cannot affect a reused ID. Work is not automatically retried.

See [the example](../examples/workers/main.nex). Its long task deliberately
loops until cancellation, demonstrating responsive UI rather than benchmarking.
The adapter does not add source async/await, native tasks/channels, general
worker pools, shared memory, GPU/NPU execution or change synchronous TypeScript
parallel_map. Six focused groups and15 actual production cases in Chromium, Firefox and
WebKit pass on the recorded macOS ARM64 compiler. See [the exact receipt](evidence/browser-workers-0.97.0.json).
Full101 regression, source-free installed SDK and platform/editor acceptance
remain pending. Headless engines are not all released browsers/devices.
