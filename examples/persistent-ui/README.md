# Persistent state and structured UI tasks

This example requires a compiler advertising
`managed_references.source030_development.persistent_UI` and language0.30 in
`nex.json`. Use SDK 1.0 or a source build that advertises this capability.

From this directory:

```sh
nex check --json
nex run --profile release
nex test --target web --json
nex build --target web --profile release --json
```

The source CLI demonstration prints41,42,43. The web build reports its generated
directory and `dist`; run `npm --prefix DIRECTORY run preview` to open the UI.
Node/npm and the matching locked web packages are development requirements;
the compiled browser application needs no compiler or LLM at runtime.

The application retains two aliases of one counter cell and a text cell across
events. Add runs a structured child task. Catch handles a cell-bearing error
after suspension. Compute runs a separate Worker through copied wire values.
The initial immutable snapshot stays41. The uncaught-error button deliberately
closes the application and displays a source diagnostic; reload starts a new
context. Transient source cycles are collected between updates.

See the [application contract](../../docs/persistent-ui.md) for event ordering,
limits, cancellation and explicit remaining work.

Пример сохраняет состояние между событиями интерфейса. Кнопки показывают задачу,
обработку типизированной ошибки и отдельный Worker. Исходный снимок остаётся41,
хотя общая ячейка меняется. Последняя кнопка намеренно вызывает необработанную
ошибку и закрывает контекст. Для новой сессии перезагрузите страницу. Это память
текущего приложения; сохранение на диск нужно реализовать явно.
