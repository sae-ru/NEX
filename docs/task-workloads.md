# Server workload acceptance tasks

Toolchain0.83 advertises `project_task_server_workloads` in `task_features`.
A project-backed profile check can select a server, pin a bounded HTTP workload
and repeat it from captured inputs after the original project is deleted.
Source language0.16 and existing task/compiler replay identities are unchanged.
Read [the workload format](server-workload.md) and [project tasks](project-tasks.md).

First inspect a readonly project plan with `--component api --configuration
measured --workload workload.json`. Its `server_workload.sha256` is the SHA-256
of the exact workload bytes, including whitespace. Add a reviewed check to a
task generated for that component, and link it to the appropriate requirement:

```json
{
  "id": "measure",
  "program": "app",
  "kind": "profile",
  "target": "server",
  "configuration": "measured",
  "entry": "workload_example::service::handle",
  "scenario": "local authenticated compute requests",
  "workload": "workload.json",
  "workload_hash": "SHA256_FROM_REVIEWED_PLAN",
  "server_workers": 4,
  "timeout_seconds": 180,
  "budget": {
    "max_peak_handles": "100000",
    "max_calls": {"workload_example::core::render": "16"}
  }
}
```

The hash placeholder must be replaced. Numbers in this example are acceptance
choices to review, not guarantees or automatically inferred user requirements.
Keep the ordinary `program.project` architecture pin and the selected profile
configuration. Server workload checks require an explicit entry matching the
component, `target:"server"`, workload/hash together, and a nonempty budget.
`server_workers` is the native request pool1..64 (default8), independent of the
workload's client concurrency. Source-only/server debug/browser workload tasks
are not introduced by this feature.

```sh
nex task task.json --kind check --json
nex task task.json --kind run --task-hash REVIEWED_TASK_HASH --directory /path/to/new-run --json
nex task /path/to/new-run/receipt.json --kind replay --directory /path/to/replayed-run --json
```

Check validates and pins the definition and current trusted runner without
reading credential environment values, creating credentials/databases, running
native programs or invoking build tools. Its existing task graph preparation
semantics still apply. A changed definition fails before native preparation;
changing whitespace also changes its hash. Paths follow task input containment
rules and cannot use symlinks. Workload data cannot supply a command, external
host, arbitrary headers or runtime environment values.

Each executing check creates a new private authentication file, random synthetic
credential for user `nex-task-workload` and empty database. The parent supplies
the credential through the workload's named `authorization_env`, overriding any
inherited value at that name. It never reads an operator authentication file or
uses an existing database. Prepare test data with reviewed workload requests;
state does not carry between checks or replays. A definition without an
authorization environment sends no credential, which permits explicit401 tests.

The task parent builds the declared final image and supervises its workload
runner/native descendants directly. Source/static/dynamic provider edges remain
intact. Timeout includes native preparation and observation under the existing
check deadline; normal completion, failed responses, interruption and timeout
all clean up the owned synthetic state. Forced termination cannot promise a
complete runtime profile or language destructors. Explicit reviewed foreign
hashes and a current `--foreign HOST.json` are still required for FFI execution;
the synthetic HTTP credential grants no foreign authority.

Inputs contain `inputs/workloads/CHECK/workload.json` and the trusted workload
runner among compiler resources. The normal8192-file/128MiB input index covers
them. The definition SHA-256 and trusted runner identity are checked around
commands and measurement. Native preparation receives the captured project
namespace, and replay uses captured workload bytes with a newly generated
credential/database. Original files and environment values cannot replace the
reviewed workload. Replay retains the existing exact compiler/build/resource
checks, current operator toolchain/FFI grants and isolated output graph/history.
Readonly input receipts work with an explicit writable new output directory.

`artifacts/CHECK/profile.json` contains the ordinary native profile plus
`nex.server-workload-result/1` request metrics. Command receipts retain the chosen process timeout and elapsed nanoseconds.
The profile command receipt includes the actual trusted launcher/native command,
build key and captured revision; runtime
environment values are omitted. `workload_runtime` in a check records only
`nex.task-workload-state/1`: synthetic user, fresh-state scope, worker count and
the fact that credential/database snapshots are not captured. Temporary paths
can occur in commands, but their authentication/database files are removed.
Program stdout/stderr retain their ordinary capture semantics.

Existing native profile budgets apply to the entire observation, including
warmup and actual provider calls. An unobserved `max_calls` symbol fails rather
than treating its count as zero. Workload checks additionally accept unsigned
decimal strings for `max_p95_latency_ns`, `max_p99_latency_ns` and
`min_requests_per_second`. Each completed phase must satisfy the selected
limits; warmup is excluded from phase statistics. Rate checks compare the exact
integer request count and phase duration, avoiding floating-point threshold
rounding and uint64 multiplication overflow.

Duration, latency and rate limits require explicit `hardware:{"cpu":...,"target":...}`.
Obtain the CPU and host target from readonly `nex doctor --json` (`cpu`, `host`),
then review the criterion on that equipment. A mismatch is unsupported and cannot
satisfy a requirement. Instrumented elapsed timings under machine load do not
establish an idle-machine production capacity. Profiles with incomplete request
counts or dropped tracked functions/allocations cannot pass acceptance.

Commit task/source/build/lock/workload files. Keep generated receipts and caches
outside source control unless deliberately distributing reviewed test evidence.
There is no reusable operator token or database to commit for this flow.
