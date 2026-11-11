# Sequential text construction

Requires a compiler advertising `text_construction` (toolchain 0.171+,
language 0.28). The one-argument `str(value)` form remains ordinary formatting;
two to four arguments select the sequential constructor.

```sh
nex describe --field text_construction --json
nex run examples/text-construction/main.nex --profile release
nex run examples/text-construction/effects/main.nex --profile release
nex run examples/text-construction/tasks/main.nex --profile release
```

The base example covers count/map/filter/state forms, generic inference, empty
input, nested values and immutable aliases. The effects example records
argument/callback order and typed source-error/finally behavior. The task
example suspends callbacks through the existing task machinery. Each directory
contains `expected.txt` for its observable stdout.

See [the constructor contract](../../docs/text-construction.md). There are no
external dependencies or lock updates in these projects. Installed SDK and
platform acceptance remain separate.
