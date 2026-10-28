# Private task exception watches and frame capture

Toolchain0.135.20 adds the opt-in inspect-private-task command. Public language
remains0.24, private execution uses ABI2501, and public025 migration is pending.
The compiler's private debug context keeps schema nex.private-task-debug/1,
archived=false and no revision. Its expression protocol is now
nex.private-task-debug-expression/1; earlier values-only contexts stay readable.

The native debug emitter supplies source_context with schema
nex.private-task-source/2: the original source/file, entry unit and complete
unit sources/paths. Its source_hash covers that exact context. The private
snapshot loader selects the separate task/exception parser before checking.
Modules resolve from retained texts; source files, project manifests and the
graph are not opened for expression evaluation. No public bundle loader or
archival/migration guard is relaxed.

The inspector requires the matching compiler_build, source identity, metadata
table and selected binding/point identity. It shares the existing checked
expression engine with ordinary inspection: canonical types, lexical binding
IDs, effect/realm checks, lazy demand reads, bounded Unicode-scalar captures,
checked arithmetic and fixed step/value/byte limits. Catch code/message bindings
are immutable strings; an outer variable can have a different type under the
same name. A throwing or IO/task/FFI call requires an effect unavailable to a
watch. Pure helpers can handle their own source exceptions. Computation occurs
in a compiler subprocess, without invoking an inferior function or changing
stopped values.

Use the actual emitted function names and current task IDs:

```text
command script import /path/to/debug/lldb_nex.py
nex-load-private-task-debug /path/to/debug.json --compiler /trusted/nex
nex-task-break function leaf
run --nex-task-workers 2
nex-task stack
nex-eval len(message)
nex-frame code
nex-task continue
```

The example expressions require their named local variables to be visible at
the current point. DAP uses the same trusted compiler with the existing
nexTaskDebug launch configuration; watch expressions can select a caller frame.
Opaque task/scope/resource authority remains unavailable as a watch value.
Source/control/runtime error transport and deadline advancement stay unchanged.

nex-frame prints a real nex.private-task-debug-frame/1 capture, including exact
stop/publication/frame and source identities, the selected bindings and demanded
wire captures. Save that JSON, then inspect it after execution:

```sh
nex inspect-private-task FRAME.json --manifest DEBUG.json --expression 'code' --json
```

The expression can use the values actually captured in FRAME.json. Further
uncaptured reads report unavailable. The frame and retained source context stay
explicitly unarchived. This is offline frame inspection; a complete crash capsule,
core export, deterministic execution replay and IDE delivery remain separate work.

Functional conformance runs actual O0/O2 native programs through LLDB/DAP,
temporarily hides each owned entry source during watches, checks repeat reads
without resuming, and evaluates the genuine captures after process exit. Cases
cover shadowed catch locals, Unicode/NUL, caller frames, future/opaque values,
short-circuit reads, type/effect/name errors, immutable records/lists/results/
bytes, a pure helper with a handled exception and a private watch lambda.
A retained module context is also compared across AST/native/TypeScript with
strict pinned TypeScript checking. Native frames and managed values retire.

The ordinary public inspect/debug paths and graph identities retain their
contracts. General025 source/build/SDK publication, IDE and complete capture/
replay, resource/file/FFI/provider/binary integration, full current platform/SDK
acceptance and history-preserving migration remain pending. Security audits,
sanitizers and fuzzing stay deferred by the user's instruction.
