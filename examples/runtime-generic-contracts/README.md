# Generic runtime contracts

Development toolchain0.156 projects the reviewed `maximum<T:ordered>` and
`identity<T>` templates. Their pure postconditions check every specialization.
Each private implementation preserves the original bounds; selecting a derived
instance for replacement is rejected.

```sh
nex contract --kind runtime --contracts contracts.json --directory /tmp/nex-generic-guarded --json
cd /tmp/nex-generic-guarded
nex test --json
nex test --target web --json
nex run --profile release --json
```

The application prints `42` and `🙂`. Keep the generated sources, manifest, lock
and candidate4 receipt together. These are executable checks with ordinary
checked trap and cleanup behavior. They do not extend the scalar proof engine.
See [the guide](../../docs/runtime-contracts.md) for exact limits and acceptance.

Контракт ставится на исходный generic-шаблон. Сгенерированные проверки выполняются
для i64, f64, строк и других допустимых специализаций. Предикаты проверяются
параметрически по ограничениям типа, включая ещё не использованные шаблоны.
История исходного проекта сохраняется; результат генерации — отдельный проект.
