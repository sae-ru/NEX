# Learn NEX / Примеры NEX

These are fresh language 0.27 projects. Each includes source, a manifest and an
observable test. [Corpus labels](../../llm/corpus.json) record source hashes,
expected stdout, diagnostics and the compiler used for validation.

| Project | What it teaches | Main stdout |
|---|---|---|
| `hello` | Typed functions, checked arithmetic, IO and a test | `42` |
| `typed-errors` | Owned typed error value, catch guard and finally | `caught`, then `finished` |
| `cpu-map` | Ordered pure CPU mapping and result agreement | `14` |

From one project directory:

```sh
nex check --json
nex eval --json
nex test --json
nex test --target web --json
nex run --profile release --json
```

The web test checks TypeScript/reference behavior under Node; it is not a browser
UI execution test. Native `parallel_map` uses its bounded thread implementation;
reference/TypeScript preserve results through sequential evaluation.

Это новые проекты языка 0.27. В каждом есть исходник, манифест и проверка поведения.
Запускайте команды из папки выбранного примера. Преднамеренно ошибочные программы
находятся отдельно в `llm/rejected` и помечены в corpus.json; использовать их как
корректные шаблоны не следует.
