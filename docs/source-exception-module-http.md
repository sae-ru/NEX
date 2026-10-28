# Private modular HTTP host

Toolchain0.135.26 extends the compiler-private checked-source module workflow
with an explicit HTTP root. Public language stays0.24; no manifest switch
publishes0.25. Read [HTTP source errors](source-exception-http.md),
[physical images](source-exception-frontiers.md) and
[consumer specializations](source-exception-instances.md) first.

Architecture/4 retains the six component fields from/3 and requires a root
`host`: either `application` or `http`. Earlier architectures keep their
original meanings. For example, a root HTTP handler and static route library
may own the standard HTTP unit in the route component:

```json
{
  "schema": "nex.private-task-architecture/4",
  "mode": "mixed-fixed",
  "application": "app",
  "host": "http",
  "components": {
    "routes": {"entry": "routes::handle", "units": ["routes.nex", "@std/http.nex"],
      "exports": [], "dependencies": [], "linkage": "static", "instantiations": []},
    "app": {"entry": "app::handle", "units": ["server.nex"],
      "exports": [], "dependencies": ["routes"], "linkage": "application", "instantiations": []}
  }
}
```

Every checked source import still requires its direct component dependency.
Standard units also need exactly one owner. They may instead belong to a
separate code component with an ordinary public function entry. Static,
fixed shared and mixed images use the same unique physical ownership ledger.
Automatic source/interface placement and general binary-only checking remain
pending.

The HTTP root must be a non-test `server` function with exactly one
`std::http::Request` parameter and a `std::http::Response` result, declaring
`task`. The existing exact record layout validation is shared with the
standalone private HTTP emitter. Normal application roots retain their
no-argument i64/unit entry rule. Provider entries remain code entries.

The plan is `nex.private-task-modules/4`, with the selected `host`. Component
records are `nex.private-task-module/4`, adding `entry_kind` (`http`,
`application` or `code`). The HTTP root also records its `entry_descriptor`.
HTTP emission produces a descriptor accessor and verified task code without a
generated process `main`. An operator-prepared native host calls
`executeConfiguredSourceExceptionTaskHttpRequest` with that descriptor; it
owns server startup, request scope, cancellation and joined shutdown. All code
images use private ABI2502 and one common runtime. Public ABI3/4/5 providers
remain distinct.

The source error channel crosses code images and consumer-owned generic
instances. A caught source exception can return a normal HTTP response.
An uncaught source exception ends that request with500/E_SOURCE_EXCEPTION;
its journal retains the original throw site, function/source hashes, code,
message and request ID. Runtime traps, deadlines, budgets and disconnects keep
their separate control channel. Owned files and foreign resources settle before
the next request or server shutdown. Source origin and machine ownership remain
separate for a template emitted by its consumer.

`source_exception_module_http` is an ordinary functional test. It runs actual
O0/O2 HTTP/HTTPS servers with static/shared/mixed code, compares AST and TaskIR
outcomes, checks loaded descriptor/step owners against the plan, and observes
resource/file/managed-value cleanup. Programs run with their selected source
files and source context temporarily absent. This establishes neither a
security assessment nor broader platform/installed SDK acceptance.

Public build/project/SDK integration, explicit history-preserving025 migration,
module HTTP profiling/logical debugging, async DB and broader platform delivery
remain pending. Security checks are deferred by the user. The original full
language/toolchain/Studio/converter/performance goal remains open.
