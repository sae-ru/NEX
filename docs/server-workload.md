# Profile a native server with a bounded workload

Toolchain0.82 adds `--workload FILE` to `nex project --kind plan|profile`.
Use a `server` component and a configuration whose profile is `profile`.
This is external development metadata; language0.16 is unchanged.

```sh
nex project --kind plan --component api --configuration measured --workload workload.json --json
nex project --kind profile --component api --configuration measured --workload workload.json --profile-output profile.json --timeout 30 --json -- --auth /path/to/auth.json --database /path/to/state.sqlite --workers 4
```

Keep compiler flags before `--`; arguments afterwards belong to the server.
Generate the local runtime credential with `nex token --auth /path/to/auth.json
--user bench --json`. Set the workload's named environment variable to that
token in the invoking shell. Keep credentials and mutable databases outside Git.
Commit the workload, NEX sources, `nex.json`, `nex.build.json` and lock files.

The workload must be a regular, non-symlink file inside the project, outside
`.git` and `.nex`. Readonly planning validates its bytes before loading sources
or inspecting native tools, and does not read the authorization environment,
execute tools, create build caches or open a graph Store. The plan records the
definition SHA-256 and trusted runner SHA-256. The compiler checks original
inputs around planning and execution, copies exact bytes into owned temporary
files and checks the returned metrics against the definition. A changed file,
alias target or trusted helper is rejected.

```json
{
  "schema": "nex.server-workload/1",
  "requests": [
    {"method":"GET","path":"/api/compute","expect":{"status":200,"text":"4704 🧠"}}
  ],
  "warmup": 2,
  "phases": [
    {"concurrency":1,"iterations":2},
    {"concurrency":4,"iterations":3}
  ],
  "authorization_env": "NEX_WORKLOAD_TOKEN",
  "request_timeout_ms": 1000,
  "startup_timeout_ms": 5000
}
```

Each worker in a phase executes every request definition in order, once per
iteration. Workers run concurrently. Warmup runs each definition sequentially
before the measured phases. The example makes16 total requests: two warmup,
two in phase1 and twelve in phase2. This is client-generated HTTP concurrency;
it adds no source-language concurrency syntax. Server `--workers` independently
selects its existing native request pool.

Requests may use GET, HEAD, POST, PUT, PATCH, DELETE or OPTIONS. `method` defaults
to GET, `body` to empty UTF-8 and `content_type` to application/json. A target
starts with exactly one slash and uses ASCII33..126 without `#` or backslash;
absolute URLs are rejected. Each expectation requires a status100..599 and may
also require exact UTF-8 response bytes, a lowercase SHA-256, or both. Conflicting
text/hash expectations are rejected. Unexpected responses fail the observation.
Mutations are never retried; a timeout can leave their application effect uncertain.

The compiler chooses the actual native artifact under the declared source,
static and dynamic dependency edges. The trusted Python3 runner starts that
artifact on `127.0.0.1` with an OS-assigned port and uses direct HTTP connections
without redirects or retries. The workload cannot select an executable,
external host, arbitrary headers, command, or environment values. Optional
`authorization_env` names a runtime Bearer credential; only its name is recorded.
Operator `--host`, `--port`, `--cert` and `--key` arguments are rejected for this
flow. HTTPS, external servers and browser/UI workloads remain pending.

The runner inherits the compiler supervisor's process group. On normal completion
it requests graceful server shutdown, allowing native profile and managed-value
cleanup. The compiler bounds elapsed time and output and stops descendants on
completion, timeout or interruption. Profile-owned native temporary files are
removed after the process group stops, including captured FFI modules. Forced
termination cannot promise normal language destructors or a complete profile.
Explicit current `--foreign HOST.json` grants remain required for external calls;
workload data never grants them.

`observation.workload` and the full `--profile-output` report contain
`nex.server-workload-result/1`: pinned hashes, expected/completed request counts,
warmup count, each completed phase's duration, request rate, latency samples and
min/p50/p95/p99/max latency in nanoseconds. p50 is the ordinary median; p95/p99
use nearest rank. Latency ends after reading the bounded response on a fresh connection;
expectations are checked before accepting the sample. Throughput covers the
complete concurrent phase, including expectation validation. Warmup is
excluded from phase statistics but included in profile function calls and memory.
Metrics contain no request/response payloads or credential values. Native
stdout/stderr remain ordinary captured program output.

The ordinary profile also binds the final executable build key, captured
provider function hashes and memory measurements. Project identities have null
persistent graph IDs and `identity_scope:"captured_project"`. Check `ok`, process
status, memory pools and dropped-event counters before using measurements.
Instrumented timing under shared-machine load is not an uninstrumented capacity
claim. Source-free [task capture/replay](task-workloads.md) requires the separately
advertised `project_task_server_workloads` capability. Server debugging remains
pending and is not implied by this command.

Limits:1MiB strict UTF-8 JSON, unique keys, depth32, integer numeric tokens,
1..128 definitions,1..16 phases,1..64 workers per phase,1..4096 iterations,
0..128 warmup iterations, and at most4096 total requests including warmup.
Bodies/expected text are at most64KiB UTF-8, target2048bytes, content type128bytes,
response1MiB and forwarded server output4MiB. Per-request timeout is50..5000ms
(default1000); startup50..15000ms (default5000). The outer `--timeout 1..3600`
seconds (default30) bounds the complete observation after native preparation.
Python3 is needed at runtime, with an optional operator `NEX_PYTHON` override.

See [input schema](../llm/server-workload.schema.json),
[metrics schema](../llm/server-workload-result.schema.json) and
[complete dynamic-library example](../examples/server-workload/README.md).
