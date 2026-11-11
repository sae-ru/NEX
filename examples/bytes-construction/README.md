# Sequential byte construction

Requires a compiler advertising `bytes_construction` (toolchain 0.172+,
language 0.28). The one-argument `bytes(list<i64>)` conversion remains an
ordinary `result<bytes>` operation; two to four arguments select the sequential
constructor and trap `E_RANGE` for an octet outside `0..255`.

```sh
nex describe --field bytes_construction --json
nex run examples/bytes-construction/main.nex --profile release
nex run examples/bytes-construction/effects/main.nex --profile release
nex run examples/bytes-construction/tasks/main.nex --profile release
```

Each directory contains `expected.txt` for its observable stdout. See
[the constructor contract](../../docs/bytes-construction.md). There are no
external dependencies or lock updates in these projects. Installed SDK and
platform acceptance remain separate.
