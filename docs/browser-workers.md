# Typed browser worker jobs and structured tasks — toolchain0.120 development

The browser adapter accepts these additional ordinary client/shared entries.
Commands remain pure; compute may be pure or declare exactly `!{task}`:

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
Only empty effects or exactly task are accepted for worker_compute. The existing
realm checker and wire checks prevent server/IO/filesystem/FFI capabilities and
task authority from crossing this boundary. Main-thread UI entries remain pure.

`worker::request(id, input, action, timeout_ms)` describes work. The adapter runs
it in an actual dedicated module Worker and delivers a normal web event to
update. `worker::response<Output>(event)` returns `result<Response<Output>>`;
the response has `id: str` and `value: result<Output>`. Check both results and
the current request ID. If Output is itself a result, its application failure
remains inside a successful transport result. Source tests only construct these
values and execute compute through the selected backend; they do not launch
background workers.

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

## Structured task computation

Use the existing syntax, without a language migration:

```nex
client fn worker_compute(input: i64) -> i64 !{task} {
  return with_tasks(2, fn(scope: task_scope) -> i64 !{task} {
    let job: task<i64> = task_spawn(scope, fn() -> i64 !{task} {
      task_yield(); return input + 1;
    });
    return task_wait(job);
  });
}
```

Each dedicated Worker creates one root scheduler through the generated
`execute` host. Scope/future/channel aliases stay inside it; only strict wire
input/output crosses its messages. The default scheduler limits are1,000,000
steps,5,000ms after scheduler start and a logical worker cap of16. These are
independent of the job's host timeout, which includes queue/startup. The
TypeScript scheduler is cooperative on that Worker's single JavaScript thread;
it does not create16 CPU threads. The job runner still permits at most2 actual
Workers at once. Checked errors/limits are returned as transport failures;
application `result` errors stay nested inside transport success.

Host cancellation/timeout terminates this dedicated realm and emits the existing
completion once. It does not promise native task-cancellation cleanup hooks or
resource finalizers: this worker owns no external filesystem/FFI capability.
Closing the UI suppresses late delivery. React state/update/view and command
construction remain pure and synchronous. General task-driven DOM/network/IO,
shared authority across jobs and a main-thread task adapter remain pending.

[The task-worker example](../examples/task-workers/main.nex) exercises an actual
zero-capacity channel, spawn/send/receive/wait and checked values beyond2^53.
Its production browser checks are separate from source/backend tests.

After building that example, run
`python3 tests/workers_browser.py GENERATED_PROJECT --structured-tasks --browsers-path CACHE`
for the existing five lifecycle cases and the independent scheduler-limit case
in Chromium, Firefox and WebKit. Without `--structured-tasks`, the runner keeps
the original pure worker contract tests.

See [the pure example](../examples/workers/main.nex). Its long task deliberately
loops until cancellation, demonstrating responsive UI rather than benchmarking.
The adapter does not add source async/await, general worker pools, shared
memory, GPU/NPU execution or multi-threaded TypeScript parallel_map. Six focused groups and15 actual production cases in Chromium, Firefox and
WebKit pass on the recorded macOS ARM64 compiler. See [the exact receipt](evidence/browser-workers-0.97.0.json).
Full101 regression, source-free installed SDK and platform/editor acceptance
remain pending. Headless engines are not all released browsers/devices.
