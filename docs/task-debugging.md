# Logical native task debugging

This source-only catalogABI1 debugger was checked in the preserved0.115/language0.20
checkpoint, including actual LLDB/NEX-DAP, composite139 and matching installedSDK27.
See [its exact evidence](evidence/toolchain-0.115.0-task-debug.json). Query
`nex describe --field task_debugging --json` before using it; acceptance remains
specific to the recorded source/compiler/platform cohort. Current126 provider
logical-debug integration has a separate `task_provider_debugging` descriptor,
[guide](task-provider-debugging.md) and separate live/SDK/platform receipts. It does
not reinterpret this standalone/source-only ABI1 contract.

The first slice targets local macOS/Linux64 debug executables and source-only
project applications, launched through the public language0.20 CLI. For example:

```sh
nex debug main.nex --kind nex-dap --task-timeout-ms 60000 --json
nex project --kind debug --component app --adapter nex-dap --json
```

A logical task keeps its ID when it moves between worker
threads. Its source activations have separate IDs and retained call frames.
Ready, running, blocked, draining and terminal states do not by themselves prove
that locals are readable: source execution must be at a published safe point or
an accepted park. A queued task that has not started has no invented source
frame. Its target name before first activation is unavailable in this slice.
Native worker IDs are diagnostic information.

## Preparation and controls

Use a fresh debug descriptor from the matching compiler. It selects the actual
executable, immutable captured sources, manifest and formatter/adapter. Keep
those artifacts for the session. Instrumentation is selected by the task debug
action; an ordinary `build --profile debug` does not enable the logical catalog.
Task launches use manifest `nex.debug/2` and view `nex.task-debug-view/1`.
Execution TaskCodeDescriptor ABI3 is unchanged; the debug catalog has its own
ABI1. Synchronous debug manifests and frame formats keep their existing paths.

The matching LLDB formatter provides these commands:

| Command | Purpose |
| --- | --- |
| `nex-tasks` | List bounded logical task records and their readable state. |
| `nex-task-select TASK_ID` | Select a logical task for subsequent inspection. |
| `nex-task-stack [TASK_ID]` | Read its retained logical call stack. |
| `nex-task-values [TASK_ID [FRAME_INDEX]]` | Preview initialized lexical locals. |
| `nex-task-break function QUALIFIED_NAME` | Set an unconditional function breakpoint. |
| `nex-task-break line FILE LINE` | Set an unconditional captured-source breakpoint. |
| `nex-task-next [TASK_ID]` | Advance the selected logical activation. |
| `nex-task-in [TASK_ID]` | Enter a logical source call. |
| `nex-task-out [TASK_ID]` | Continue until the activation returns. |

The equivalent `nex-task tasks|select|stack|values|next|in|out` forms are also
available. Set breakpoints before `run`, then inspect a fresh stopped process.
Logical stepping resumes all workers so a selected task's dependencies can make
progress. It does not pin the task to the currently stopped OS thread. Source
point visits distinguish repeated loop iterations even on the same line.
Continue/new stop invalidates references from the preceding stop.

The matching NEX DAP bridge uses logical tasks for `threads`, `stackTrace`,
`scopes`, `variables`, `evaluate`, `next`, `stepIn` and `stepOut` when its fresh
launch descriptor selects task mode. Raw `lldb-dap` task launches are rejected.
Conditional/hit-count/log breakpoints and general native helper stepping are
outside this first slice. A pure helper's ordinary DWARF remains available for
native inspection; while its caller is executing, that caller's logical source
publication can be unavailable. An unavailable stack is reported explicitly.

## Locals and pure expressions

At a stable selection, `nex-eval EXPRESSION` and `nex-frame EXPRESSION` use the
existing out-of-process pure watch evaluator. Frame `nex.debug-frame/3` binds
process/stop ID, task ID/generation, frame activation ID, publication sequence,
source-point ID and visit. The compiler independently rederives binding
visibility from the exact archived source and its actual language version.
The initializer of a new local cannot see that new binding; shadowed declarations
have distinct identities, and pattern names appear only on a successful branch.

The formatter reads borrowed values through LLDB memory/SBValue APIs while the
process is stopped. It never evaluates an inferior function, clones a source
Value or retains a source handle. Immutable watch inputs are captured into the
separate compiler process. Task, channel, file, grant and effectful callable
authority remain opaque; they do not prevent unrelated scalar locals from being
inspected. Value previews and captures retain their existing depth/byte bounds.

A publication is rejected if its process stop changed, sequence is odd, frame
activation was retired/reused, slot is disengaged, metadata differs from the
verified image or the bounded catalog overflowed. The reader does not wait for
an odd writer while the inferior is stopped. These cases produce unavailable
data instead of stale values.

## Limits and execution semantics

The preallocated catalog holds at most4096 task tombstones and65536 live frame
records. Stack and returned-local limits are256. Immutable compiler metadata
bounds are16384 code sites,262144 points,65536 bindings,1048576 visibility entries,
16MiB text and64MiB combined metadata. Exhaustion makes affected debugger data
unavailable and preserves source execution.

The host debug manifest keeps its existing8MiB input bound. The64MiB runtime
metadata ceiling does not promise that every maximum-size image fits this host
manifest; both bounds apply independently.

Root deadlines continue advancing while stopped. Choose explicit reviewed
`--task-timeout-ms`, `--task-steps` and `--task-workers` before launch; debugging
does not renew deadlines, widen file authority or change cancellation/fatal
priority. Cancelled tasks still drain physical I/O before completion. Debug
records own no source Values, handles, grants, TaskGroups or coroutines, and
retire borrowed frame addresses before their storage is destroyed.

Browser/TypeScript/reference task debugging, task HTTP handlers, binary-provider
task boundaries, Windows/Wasm, GPU/NPU, core task replay and combined task
debug/profile instrumentation remain pending. Platform and SDK acceptance must
be recorded against the exact source/compiler that was tested.
