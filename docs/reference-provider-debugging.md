---
status: current
applies_to: "toolchain 0.279.0; language 0.30; task ABI8"
owner: repository
---

# Reference tasks across debug library images

The [0.278 receipt](evidence/reference-provider-debugging-0.278.0-2026-11-17.json)
records24 passing core/affected groups,139 retained metadata checks and actual
source/moved-install LLDB/DAP/capture/package/replay observations. Its platform
and compiler/image identities bound that evidence.

Ordinary030 source-backed project components support logical task debugging in
static, fixed shared and mixed native builds. One application/runtime owns the
cell heap and source executor. Connected pure helpers also use ABI8; they do not
create an independent reference context. Read the
[ordinary provider contract](reference-task-providers.md) and
[cell inspection guide](reference-task-debugging.md).

```sh
nex project nex.build.json --kind plan --component app --task-debug --json
nex project nex.build.json --kind debug --component app --adapter nex-dap --json
```

Use a debug-profile configuration and the matching compiler, formatter and
actual launch descriptor. `--task-debug` selects instrumented build/package
artifacts; a normal debug-profile run remains uninstrumented. Source imports,
component dependencies and actual fixed code images determine the closure.
Changing library kind/linkage is a project build choice, not a source migration.

## Separate execution and tooling identities

Debug reference provider records use `nex.native-task-provider/18`; ordinary
reference providers retain17. Enriched static/shared debug plans use
`nex.project-task-linkage/18`, including `mode:static` for static ownership.
Ordinary static plans retain `nex.project-static-task-linkage/6`, shared plans17.
All select the same88-byte execution descriptor ABI`0x4e45585400000008` and
requirements mask16159. A record cannot be relabeled as an ABI7 cohort.
The matching debugger also checks borrowed frames and pure-helper source under
their actual component identity; watches do not call the inferior.

Instrumentation retains debug catalogABI2, `nex.debug/3`, task view2, frame4 and
expression2. The root explicitly records `execution_task_abi`; every original
code descriptor is checked against that cohort and its actual code owner.
Source/registry/image/source-union identities, DWARF, UUID/build-ID and original
byte pins keep their existing independent meanings. No source production,
source version, canonical graph history or public C ABI changes.

The formatter follows the retained logical stack across components. It reads
borrowed slots from the common runtime's frame layout and keeps each frame's
checked source identity. Pure watches are evaluated by the matching external
compiler using that component's actual030 source. `nex-task-inspect` and DAP
cell children remain copied read-only diagnostics with explicit alias/cycle and
truncation information. Continue/step invalidates prior selections/references.
Neither inspection nor a copied file identity grants authority or mutates source.

## Source errors, waiting and lifetime

Source continuations stay on the heap owner thread while physical IO retains
its separate completion workers. The example spawns a child capturing cells;
its parent waits on a future. The leaf library updates a cell and throws a
nominal error carrying that same cell. The middle library catches it and reads
the updated value. Logical step-out crosses that error boundary while retaining
the caller's source frame and shared state.

All images stay loaded through source frame/value/error retirement. Arbitrary
hot unload, imported function values and foreign-provider authorization are not
introduced. Existing effect/realm/resource cleanup and control priorities remain
unchanged; deadlines continue advancing while stopped.

## Capture, replay and packages

A native build acceptance check may set `task_debug:true` to prepare a launch
descriptor without executing an interactive debugger. Capture recognizes plan18
and retains the actual ABI8 source/debug/image closure. Replay restores that
selection explicitly. Packages preserve the original pinned metadata and derive
relocated launch paths, keeping original-to-owned image/symbol mappings.

`tests/task_provider_debugging.py` exercises actual LLDB in all three linkage
modes, real DAP through a mixed image, typed-cell error propagation and
capture/package/replay after removal of the original source/cache directories.
Retained ABI7 provider-debug tests keep their own formats and scenarios.
These are focused functional checks; full source/platform/portable SDK release
qualification remains separate. [Reference task profiles](reference-task-profiling.md) use separate record19/plan19.
HTTP reference debugging/profiling,
parallel reference transfer and cell graph reconstruction for pure watches
remain open.

По-русски: один объект может проходить через несколько статических и динамических
библиотек, а отладчик сохраняет его идентичность и логический стек. Можно перейти
из библиотеки к вызывающему коду, увидеть cell и обработку типовой ошибки.
Упакованные отладочные материалы работают независимо от исходного каталога.
