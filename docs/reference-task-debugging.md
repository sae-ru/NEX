---
status: current
applies_to: "toolchain 0.279.0; language 0.30; task ABI8"
owner: repository
---

# Native reference task debugging

Toolchain0.278 adds [source-backed provider images](reference-provider-debugging.md)
with debug catalogABI2. The standalone contract below retains catalogABI1.

The [0.277 receipt](evidence/reference-task-debugging-0.277.0-2026-11-17.json)
records25 distinct passing core/affected groups and actual LLDB/NEX-DAP sessions
from the source compiler and a moved normal installation. It retains the
original failures and a1000-item DAP observation with unchanged source limits.

Ordinary030 source-only task applications can select logical LLDB/NEX-DAP
debugging. Their source continuations and cell heap stay on the execution owner
thread. Debugging preserves source semantics, step budgets and deadlines; time
spent stopped still consumes the selected deadline.

```sh
nex debug main.nex --kind nex-dap --task-timeout-ms 60000 --json
```

Use the returned launch descriptor and matching compiler/formatter. The
[logical debugger](task-debugging.md) supplies task selection, retained stacks,
source breakpoints and next/in/out across yields and calls. The030 manifest
explicitly records `execution_task_abi: "0x4e45585400000008"` when it selects
reference tasks. A030 reference-free task retains ABI7; old manifest/canonical
source identities are not relabeled. Debug catalogABI1 and source-only
`nex.debug/2` retain their layouts. This is not the provider catalogABI2 path.

## Reading cells

At a published stable source point, `nex-task-values` includes cell identity and
a bounded preview. `nex-task-inspect BINDING [TASK_ID [FRAME_INDEX]]` returns a
copied diagnostic graph with schema `nex.task-value-inspection/1`; the encoded
logical request is `{"command":"inspect","arguments":{"binding":"state"}}`.
It accepts one initialized visible binding in the selected logical frame, and
can inspect a cell or an aggregate containing cells.
The live fixture also captures cells in a spawned child while its parent waits
on the future, then observes state across yield and a nested source call.

A cell node has `kind`, a stopped-process diagnostic `identity`, `live` and its
copied `value`. Repeated cell nodes in that graph have `alias:true`, terminating
cycles while preserving their identity. A retired payload is displayed as
closed. Native values/handles and addresses are never reconstructed or renewed
from this JSON; an identity is not an IO or mutation capability.

The inspector reads borrowed DWARF/SBValue/memory while the process is stopped.
It never executes an inferior expression, invokes a callback, clones or retains
a source Value, grants access, or changes a cell. It checks the original
process/stop/task/generation/frame/publication/visit again before returning.
Changed or unavailable publications fail instead of publishing stale state.

Bounds are256 visited nodes, depth8,16KiB cumulative exact text,64 items per
collection and256 decoded bytes per byte prefix. Truncation/unavailable children
are explicit. Each values response shares its cell-inspection budget across
locals. File and external-resource nodes expose diagnostic identity only;
functions, tasks, channels and scopes remain opaque.

NEX-DAP exposes direct cell locals as read-only expandable values, including a
visible truncation marker when a snapshot omits children. Child
expansion uses only the copied snapshot. Cell identity/live/value, nested record
fields, list elements and repeated aliases are available within these limits.
Continue or a new stop invalidates every prior variable reference. Changes
through `setVariable`/`setExpression` remain rejected.

## Watches and boundaries

Existing pure scalar/resource-free watches work in a030 frame containing cells.
The compiler parses frame types and expressions under the actual checked source
version. A watch does not gain `state`: `cell_read`, `cell_write`, allocation and
collection cannot execute through pure watch evaluation. Use inspection to read
the stopped payload. Reconstructing live cell graphs for watch calls remains a
separate contract, including alias identity, lazy paths and cycles.

[Reference task profiles](reference-task-profiling.md) use a separate profile build.
HTTP logical debugging/profiling,
persistent native host-session debug launches, parallel reference transfer and
matching complete SDK/platform delivery remain open. Existing sequential raw
native inspection and reference-free logical debugging keep their contracts.
Focused live execution evidence does not qualify another platform or a portable
SDK release.

По-русски: остановленные задачи030 можно просматривать и выполнять по шагам.
`nex-task-inspect state` показывает текущее содержимое объекта, алиасы и циклы;
в NEX-DAP объект раскрывается как дерево. Отладчик читает снимок и не меняет
программу. Выражения watch сохраняют прежние ограничения на побочные действия.
