# Native profiling

Toolchain 0.10 instruments reachable native NEX functions in `--profile profile` builds. Language 0.5 semantics, effects and source syntax are unchanged. Debug/release builds do not include the profiler or its hooks. TypeScript/browser and GPU profiling remain separate pending work.

```sh
nex profile examples/profiling/main.nex --scenario "sum and labels" --json
nex profile examples/profiling/main.nex --events 1000 --timeout 30 -o /tmp/nex-profile.json --json
```

`nex profile` builds and executes a host-native application. It writes a complete `nex.profile/1` report and returns a bounded `nex.profile-session/1`: at most 100 functions ordered by self time, output path, exit code, captured stdout/stderr, source revision, build key, scenario, start time and host CPU/target/thread count. The saved report retains all function aggregates and its `traceEvents` timeline can be imported by a Chrome trace-compatible viewer. Concurrent runs get different default output names. `-o` deliberately replaces the requested report file.

Each measured function includes its logical name, immutable source path/line, canonical content hash and graph node ID. The CLI matches name/content against the selected saved graph before attributing measurements. Object reuse does not embed another application's revision or project-local node ID. An archived revision can be profiled after deleting live source files. Use `nex context --revision REVISION --symbol NAME` to inspect a measured function.

`calls`, `completed` and `aborted` distinguish normal and failing invocations, including recursion. `inclusive_ns`, `self_ns` and `max_ns` are measured monotonic **elapsed wall time**; self time subtracts nested instrumented NEX calls. They include instrumentation/runtime/OS scheduling overhead and are not CPU utilization or cycle counts. Recursive inclusive times overlap and must not be added as total runtime. Traps close active zones before host cleanup or process exit; request boundaries also close zones for cancellation/deadline/budget exceptions. Normal and early returns are balanced.

The two memory pools count actual live native handle and `Data` object allocations and their **shallow** `sizeof` bytes. They exclude strings/vector backing buffers, shared ownership control blocks, allocator overhead, SQLite/OpenSSL/Tracy allocations and total process RSS. Function allocation totals identify allocation sites. Ordinary successful application wrappers still enforce zero live managed values independently of profiling. A standalone trap exits immediately, so its report can show retained allocations; a trusted request scope cleans them on unwind. Host code that constructs managed `Data` values for an instrumented archive must compile with `NEX_PROFILE_ENABLED` for matching hooks.

The local collector bounds timeline events (default 100,000, option range 0..1,000,000), unique functions (16,384), active frames per thread (4,096) and tracked live allocations (1,000,000). Aggregate timings continue when timeline storage fills. Dropped events/functions/frames/allocations and untracked frees are explicit fields; inspect them before treating a report as complete. The CLI timeout is 1..3,600 seconds, default 30; a killed/crashed process may not flush a report and is reported as a process/profile failure. Instrumentation changes execution costs and memory use; measurements are observations for the named workload/hardware, not optimization guarantees.

## Tracy

The unmodified [Tracy 0.14.1 client](https://github.com/wolfpld/tracy/tree/v0.14.1/public) is pinned under `runtime/third_party/tracy`, including a SHA256 inventory and license notices. Its C API receives function zones with NEX names, frozen file/line and content hash text, and named memory pools. Native profile output contains the client; ordinary execution leaves it dormant. `nex profile` explicitly disables Tracy and produces its local report without opening a listener.

Build a program, then connect the matching upstream Tracy viewer or `tracy-capture`:

```sh
nex build examples/profiling/main.nex --profile profile --json
# Start the application first; replace EXECUTABLE with the reported path.
NEX_TRACY=1 NEX_TRACY_WAIT_MS=60000 EXECUTABLE
# In another terminal, connect within that wait:
tracy-capture -a 127.0.0.1 -o /tmp/run.tracy
```

Tracy listens only on localhost, disables broadcast, source-code transfer, crash hooks, callstack sampling and system tracing. `NEX_TRACY_WAIT_MS` waits up to 60,000 ms for a collector (default 5,000); a missing collector emits a diagnostic and execution continues. Only explicit `NEX_TRACY=1` starts its worker threads. Memory frees are sent only for allocations observed in the current connection; allocations predating a connection are not retroactively known. A separate link unit supplies exact toolchain/language/revision/build-key identity to Tracy application information without invalidating reused NEX modules. The bundled manual-lifetime client flushes on ordinary exit. Preserve `THIRD_PARTY_NOTICES.txt` with distributed profile executables/archives, including explicit `-o` copies.

For long-running servers or trusted host archives, build with `--profile profile` and set the same environment when launching the server/host. `NEX_PROFILE_OUTPUT=/absolute/report.json` additionally writes raw `nex.profile-runtime/1` aggregates at normal process exit; this raw file includes the exact build/revision identity and function content hashes; join it with the matching graph for project-local node IDs. Stop servers cleanly to flush. Per-request timing is represented by nested handler calls and separate thread lanes; application-specific request payloads/credentials are not captured by the NEX hooks. A forceful signal does not guarantee a complete report.

The viewer/capture/csvexport executables are upstream tools, not installed by the current NEX SDK. GPU/energy/system events, dynamic buffer allocation coverage, operation IDs, browser timelines and automated statistical before/after comparisons remain open.

On the exercised macOS host, starting upstream capture before the application listener was ready sometimes failed its initial handshake. Automated capture validation starts the application and confirms its localhost listener before launching capture; three consecutive direct captures then passed without a proxy. Keep this startup ordering when reproducing those checks.

`python3 tests/profile_benchmark.py build/nex` records repeated whole-process timings for release, dormant instrumentation and local aggregation on the same checked-add workload. It verifies the result/call counts and reports all samples/medians and the host/revision; it has no speed assertion.

Optional upstream acceptance: `python3 tests/tracy_capture.py build/nex --capture PATH_TO_TRACY_CAPTURE --export PATH_TO_TRACY_CSVEXPORT` performs three direct captures, checks exact function/call agreement and frozen source paths, and saves traces/CSV plus `acceptance.json`. `--inspect PATH` additionally checks named pool balance and embedded build identity with the helper in `tests/tracy_inspect.cpp`, linked against the same upstream TracyServer/headers/configuration. These tools are not prerequisites of the default CTest suite or installed SDK.
