# Reference tasks in native libraries

This030 example uses one application heap across separately compiled providers.
`leaf` creates/mutates cells and raises a typed cell-bearing error; `mid` calls
it across task continuations; `pure` has no cell/task operations. The application
checks retained aliases, a joined child, a cycle and a caught error, then prints42.

```sh
nex project --kind run --component app --configuration debug --json
nex project --kind run --component app --configuration release --json
nex project --kind test --component app --configuration debug --json
```

The checked architecture currently selects static libraries. Change a library's
kind to `shared_library` and its consuming binary edges to `dynamic` for fixed
shared loading; retain exactly one machine owner for every definition. See
[the ownership contract](../../docs/reference-task-providers.md) for mixed images,
source requirements, retained ABIs and delivery limitations.

По-русски: библиотеки используют общий runtime и одну ссылочную память приложения.
Ссылка после вызова и ожидания задачи указывает на тот же объект. Даже чистая
библиотека получает ABI8, когда входит в эту связанную сборку. Это пример работы
языка и сборщика; полная приёмка SDK и других платформ проводится отдельно.
