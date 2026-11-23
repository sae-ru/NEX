# Persistent hash containers

Requires a compiler advertising `standard_library.modules.hash_map` and
`hash_set`. The project selects source0.30; the pure containers also work with
source0.28/0.29. SDK 1.0 includes both modules.

From this directory:

```sh
nex check --json
nex run --profile release
nex test --target web --json
nex run tasks.nex --profile release
nex test tasks.nex --target web --json
```

The main example prints `hash-containers-ok`; the cell/task example prints42.
Both retain old map snapshots. Map updates share unchanged trie subtrees.
Enumeration follows hash-trie order; use the existing insertion-ordered or
comparator-ordered modules when that order is part of the application contract.

The lock pins the reviewed hash/helper source modules. Commit `*.nex` source files,
`nex.json` and `nex.lock.json`; generated `.nex/` runtime/build files stay out of
source control. Check rejects changed dependencies; review and explicitly run
`nex lock` to update them. See [the contract](../../docs/hash-containers.md).

Пример использует неизменяемую хеш-карту и множество. Старая версия карты
сохраняет прежние значения после обновления. В `tasks.nex` карта хранится в
ячейке и обновляется из структурированной задачи. Порядок обхода определяется
хешем; исходные Map/Set с порядком вставки сохраняют прежнее поведение.
