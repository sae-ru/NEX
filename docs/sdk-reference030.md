---
status: current
applies_to: "toolchain 0.279.0; language 0.30"
owner: repository
---

# Installed030 SDK consumption

The [focused preparation](evidence/sdk-reference030-preparation-0.279.0-2026-11-17.json)
records the moved normal installation and original checker failures.

The first full0.279 source attempt at `482f4334` exposed a stale boundary
fixture in `task_foreign`: its fixed input count omitted the captured
`program-languages.json` sidecar. The corrected fixture measures a complete
baseline snapshot, fills the remaining8192-input budget, and verifies8193
physical files including the index before successful replay. The runtime's
limits are unchanged. [Focused repair evidence](evidence/sdk-input-limit-0.279.0-2026-11-17.json)
does not qualify the full source run or a portable archive; the original failed
attempt remains retained.

The maintained SDK workflow adds a required `reference030` phase starting with
0.279.0. Earlier versioned SDKs retain their original phase lists and receipts.
The compiler fallback language remains0.28; this phase creates explicit030
projects and verifies that `nex init` selects030 for a new project.

`tools/sdk_references.py` exercises the installed compiler and resources through
the same retained command ledger as the other SDK phases. It consumes:

- Native Debug/Release execution and profile builds across static, fixed shared
  and mixed code images. Cells, child captures, typed cell-valued errors and a
  self-cycle keep their source behavior. All related descriptors select ABI8;
  instrumented providers retain record19/plan19.
- Standalone native profiling, exact named source-call counts, multiple source
  segments per invocation and balanced tracked-value cleanup. Step/deadline
  exits retain the same cleanup. Captured profiles deliberately omit timeline
  events while preserving full aggregates; absence of that timeline is explicit.
- Profile acceptance-task capture, replay and ordinary/profile packages after
  deleting the original source/cache directory. Original metadata is retained
  separately from relocated images.
- A genuine matching-runtime C++ host compiled from the SDK's runtime and test
  fixtures. Its14 kernel cases and13 compiled cases per Debug/Release image
  exercise persistent state, typed errors, cycle collection, controls and file
  ownership across invocations. This is the matching-runtime development API,
  with the [documented lifetime rules](native-task-sessions.md).
- The persistent030 browser controller, including its complete named controller
  case set, source error/control cleanup, queued events and immutable published
  views. Browser qualification additionally requires a production web build and
  actual TypeScript execution of the source task example.
- ABI8/catalog2 debugger preparation. With `--live`, an actual NEX-DAP child stops
  in the leaf image, expands a cell, evaluates an owning-source pure watch and
  steps through the typed error back to its caller before normal exit.

The examples, helper, host fixtures and runtime source inputs are SHA256-bound
to the SDK resource inventory. The final receipt validator requires the phase
and its mode, outcome, cleanup, browser/debugger and resource evidence; a subset
cannot stand in for the complete SDK workflow.

For focused development, `tests/sdk_references.py COMPILER --resources ROOT
--output NEW --browser --live` invokes only this sub-workflow and explicitly does
not claim full SDK acceptance. CTest's `sdk_reference030` group uses the browser
path; the distribution workflow chooses its declared live-debugger scope.
Full qualification still requires [the committed SDK build](sdk-build.md), all
source groups and the complete moved/archive-restored workflows.

No source grammar, language version, runtime ABI or npm dependency changes are
introduced by this workflow. HTTP logical debugging/profiling, parallel cell
transfer and native-platform/device delivery keep their separate limits.

По-русски: новая обязательная фаза проверяет именно установленный SDK030 —
библиотеки, профиль, replay, C++-сессии и постоянное состояние UI. Программы
собираются из поставляемых ресурсов. Отладчик выполняется при выборе live;
полный SDK считается проверенным после всех фаз, переноса и восстановления
архива. Один отдельный сценарий не заменяет полную приёмку.
