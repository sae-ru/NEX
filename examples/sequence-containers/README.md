# Persistent work containers

Use a compiler advertising `standard_library.modules.sequence`, `fifo`, `lifo`
and `heap`. This project selects source0.30 for its task example; pure modules
also work with source0.28/0.29. Published SDK0.246.1 predates these APIs.

From this directory:

```sh
nex check --json
nex run --profile release
nex test --target web --json
nex run tasks.nex --profile release
nex test tasks.nex --target web --json
```

The main program prints `sequence-containers-ok`. It exercises indexed sequence
replacement, FIFO dequeue, LIFO peek and priority sorting while retaining old
versions. `tasks.nex` prints42: a child task updates cell-held queues, a stack
and a heap, then a caught heap-bearing packet survives suspension/collection.

The lock records reviewed source dependencies. Commit `*.nex`, `nex.json` and
`nex.lock.json`; generated `.nex/` graph/runtime/build files stay out of Git.
Check rejects changed pins. Review and explicitly run `nex lock` to update them.
See [the contracts](../../docs/sequence-containers.md) for bounds and ordering.

Пример показывает последовательность с индексами, FIFO-очередь, LIFO-стек и
приоритетную очередь. Старые версии сохраняют значения после обновления.
В `tasks.nex` данные хранятся в ячейках, обновляются из задачи и сохраняются
при приостановке и обработке типизированной ошибки.
