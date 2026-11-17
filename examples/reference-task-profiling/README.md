# Reference task profiling

This language0.30 project requires a matching compiler advertising
`managed_references.source030_development.native_task_profiling`.

```sh
nex eval app/main.nex --json
nex profile app/main.nex --task-timeout-ms 10000 --json
nex project nex.build.json --kind profile --component app --configuration measured --json
```

The program prints42. A spawned child captures cells; its parent waits. The leaf
library updates the shared integer and throws a typed error carrying the same
cell. The middle library catches it. A separate cell self-cycle is retired at
application teardown. Each named source function runs once; the throwing leaf
invocation is aborted while the caller completes normally. Yields create source
segments without adding calls.

`measured` selects profile instrumentation. `debug` and `release` retain ordinary
execution. Components default to static libraries. Shared and mixed builds use
explicit `shared_library` kinds and `dynamic` dependencies, with each static
component assigned one physical image owner. See the
[profile contract](../../docs/reference-task-profiling.md) for attribution,
measurements, capture/replay and delivery limits.

Commit `.nex` source, `nex.json` and `nex.build.json`; generated `.nex/` caches
and profile outputs are disposable build artifacts. Retain selected reports
separately when they are needed as benchmark evidence.

По-русски: пример показывает профилирование задач с изменяемым состоянием,
типовой ошибкой и циклом объектов. Отчёт различает вызов функции и её
многократное возобновление, сохраняя принадлежность к библиотеке.
