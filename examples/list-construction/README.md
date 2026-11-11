# Sequential list construction

Requires a compiler advertising `list_construction` (toolchain 0.170+,
language 0.28). Each example is the exact source used by the corresponding
reference/native Debug/Release/strict TypeScript agreement case.

```sh
nex describe --field list_construction --json
nex run examples/list-construction/main.nex --profile release
nex run examples/list-construction/effects/main.nex --profile release
nex run examples/list-construction/tasks/main.nex --profile release
```

The base example covers generation, map/filter, stateful unfold, generic
inference, nested values, callable captures and immutable aliases. The effects
example records argument/callback order and typed source-error/finally behavior.
The task example suspends callbacks and constructs/waits genuine futures.
Each directory contains `expected.txt` for its observable stdout.

See [the constructor contract](../../docs/list-construction.md). There are no
external dependencies or lock updates in these projects. A TypeScript task entry
is a generator and must use the matching typed-source-error task driver, as
shown in the existing task TypeScript guide; calling the generator alone does
not execute the application. Installed SDK/platform acceptance remains separate.
