# Runtime loop contracts / Runtime-контракты циклов

This checked source example doubles a bounded nonnegative integer. Detached
contracts pin its exact revision, source bundle, function and while coordinates.
The invariants describe the counter/accumulator; `n - i` is its decreasing measure.
The original source has no hidden contract mode. Toolchain0.153 develops the
runtime projection; matching SDK/platform acceptance is a separate gate.

```sh
nex check --json
nex verify --contracts contracts.json --json
nex contract --kind runtime --contracts contracts.json --directory ../guarded-loop --json
cd ../guarded-loop
nex eval --json
nex run --profile release --json
nex test --json
nex test --target web --json
```

Choose an unused output directory. The generated main prints `10`. Verification
and runtime projection are independent: a successful proof does not silently
instrument the original source. Receipt2 identifies selected loops, checks and
private helpers. The generated source project can be moved and built normally.
Commit source, manifest, reviewed contracts and tests; when distributing generated
source, keep its lock and receipt together. Keep `.nex` stores/caches out of Git;
export graph snapshots separately when history is needed.

Пример удваивает ограниченное неотрицательное целое и печатает `10`. Контракт
закрепляет ревизию, исходники, функцию и координаты while. Инварианты описывают
счётчик и накопитель; мера `n - i` должна убывать. Команды выше отдельно проверяют
доказательство и создают обычный проект с исполняемыми проверками. Выберите новый
каталог назначения. История исходного проекта сохраняется; готовая программа не
требует LLM или Z3. Точные правила и ограничения: [руководство](../../docs/runtime-contracts.md).
