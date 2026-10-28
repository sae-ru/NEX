# Private source exceptions in LLDB and DAP

Toolchain0.135.19 extends emitSourceExceptionTasksPrototypeNativeDebug with an
explicit unarchived debugContext string. Its schema is nex.private-task-debug/1,
language0.25-prototype and archived=false; it has no graph revision. Functions,
original source hashes, lexical binding visibility and code indices come from
the same checked program and TaskIR metadata used by generated checkpoints.
Public language remains0.24 and private ABI2501 remains separate from ABI3/4/5.

The private artifact caller writes debugContext as JSON and supplies program,
formatter, and the actual executable's task_debug.image_sha256/image_uuid after
linking. The conformance probe uses nativeImageUUID for the linked image identity.
The ordinary nex-load-debug loader does not select this private context. Load it
explicitly in LLDB:

```text
command script import /path/to/debug/lldb_nex.py
nex-load-private-task-debug /path/to/private/debug.json
nex-task-break function leaf
run --nex-task-workers 2
nex-task stack
nex-task values
nex-task values 1 1
nex-task next
nex-task out
nex-task continue
```

The numeric arguments select a current logical task ID and optional caller frame
index; query nex-tasks for current IDs. Source line breakpoints are also supported
through nex-task-break line FILE LINE. Inspection requires an actual all-stop
process and borrows the existing catalog/slots without inferior function calls,
variable writes or owned Value retention. Opaque task/scope values stay opaque.
Catch locals appear only after initialization. Stepping out of a throwing callee
selects its retained caller; catch bindings become visible at subsequent source
points. Repeated watches remain tied to the same stop/publication/frame identity.

The existing nex_dap.py bridge can launch the same artifact with nexTaskDebug=true
and initCommands that import the formatter and invoke nex-load-private-task-debug.
Logical threads, stackTrace, scopes, variables, source breakpoints, next/stepOut
and continue use the same all-stop reader. Resuming invalidates old logical frame
and variable references. Private checked expression evaluation is not enabled;
watch retained variables through scopes/variables or nex-task values.

The private emitter accepts an explicit debug timeout ceiling (default5000ms,
valid1..3600000ms). The conformance probe compiles60000ms and application arguments
may lower it. Deadlines continue advancing during a debugger stop. A separate
test lowers the timeout to800ms, pauses longer and proves E_TIMEOUT bypasses a
source catch, followed by complete cleanup. No deadline suspension is implied.

Functional conformance uses actual standalone compiled O0/O2 programs and real
LLDB/lldb-dap processes. It checks catch shadowing, mutated outer and caller
values, Unicode/NUL messages, direct calls, future recovery, loop handlers,
uncaught original-site rethrow, runtime/control exits and logical step-out/next.
An independent native pulse thread remains unchanged while LLDB is stopped,
providing observable process all-stop evidence. After execution, managed values,
tracked allocations and live debug frames are zero and tasks are terminal.

This context is a compiler-private interface. Ordinary025 CLI/build/inspect,
checked watch expressions, IDE integration, archived capture/replay, general
provider/binary/resource boundaries, full current regression/installed SDK and
history-preserving024-to025 migration remain pending. The primary graph and
stable SDK are unchanged. Security audits, sanitizers and fuzzing stay deferred
by the user's instruction.

## Subsequent checked watch/capture integration

Toolchain0.135.20 adds a distinct checked-expression protocol over retained
unarchived source contexts. Read source-exception-task-watch.md. Select exact
function names from debugContext.functions; the raw private parser may use
unqualified names. The earlier222 values-only context remains readable.
