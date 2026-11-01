# Runtime contracts over values and effects

Development toolchain0.155 generates ordinary checked source for the reviewed
`contracts.json`. `complete` keeps its IO effect and runs once. Pure pre/post
conditions observe immutable strings, structures and lists; they do not inherit
IO authority. The original input remains unchanged.

```sh
nex contract --kind runtime --contracts contracts.json --directory /tmp/nex-value-guarded --json
cd /tmp/nex-value-guarded
nex test --json
nex test --target web --json
nex run --profile release --json
```

The application prints `NEX🙂` and `[1,2,42]`. Generation produces a distinct
source revision and a candidate/session3 receipt; it is not a proof or an implicit
execution option. Keep generated sources, manifest, lock and receipt together.
See [the guide](../../docs/runtime-contracts.md) for bounds and delivery status.

В примере функция с эффектом IO получает структуру с текстом и списком.
Контракт проверяет вход и результат чистыми выражениями; тело выполняется один
раз, исходный список сохраняется. Команды выше создают отдельный проверенный
проект. Это runtime-проверки, а не формальное доказательство свойств программы.
