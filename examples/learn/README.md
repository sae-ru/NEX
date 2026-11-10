# Learn NEX / Примеры NEX

These are language0.28 projects with source, manifests and observable tests.
[Current corpus labels](../../llm/corpus.json) pin every source/project/import
file, expected stdout, rejected diagnostics and the actual validation compiler.
[The validation workflow](../../docs/learning-corpus.md) is maintained as a tool.

| Project | What it teaches | Main stdout |
| --- | --- | --- |
| [hello](hello/main.nex) | Typed functions, checked arithmetic, IO and a test | `42` |
| [typed-errors](typed-errors/main.nex) | Owned typed error, catch guard and finally | `caught`, then `finished` |
| [cpu-map](cpu-map/main.nex) | Ordered pure CPU mapping | `14` |
| [contracts](contracts/main.nex) | Preconditions/postconditions, loop invariant/ranking | `55` |
| [values](values/main.nex) | Generic records/enums, match, Result and finite f64 | `values` |
| [text-bytes](text-bytes/main.nex) | Unicode scalars, NUL, immutable bytes and codecs | `text/bytes` |
| [traits](traits/main.nex) | Associated types, generic impl and method references | `🧠` |
| [tasks](tasks/main.nex) | Joined scope, spawn/yield/wait and task cleanup | `42` |
| [modules](modules/main.nex) | Imported checked public interface | `42` |

From one project directory:

```sh
nex check --json
nex eval --json
nex test --interpreter-only --json
nex test --profile release --json
nex test --target web --json
nex run --profile release --json
```

The TypeScript tests run under Node and do not qualify a browser UI. The corpus
validator also emits and executes each TypeScript main and checks its stdout.
Native parallel_map uses bounded workers; reference/TypeScript preserve ordered
results through their own sequential execution. This finite corpus does not
establish complete platform, provider, GPU/NPU or immutable SDK support.

Это проекты языка0.28. Метки создаются только после фактической проверки frontend,
main и тестов в reference/native/TypeScript. Пропущенный тест не считается успехом.
Преднамеренно ошибочные программы из `llm/rejected` имеют отдельные labels;
копировать их как корректные шаблоны не следует. Прежний корпус0.27 и исходные
входы сохранены [отдельно](../../llm/history/learning-0.27-0.152.1/README.md).
