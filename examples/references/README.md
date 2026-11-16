# Sequential references — language0.30

This example prints `42`. Two names and a captured closure share one typed cell;
an earlier payload read remains an immutable snapshot. A typed error retains the
same cell, and a recursive cell graph exercises cycle collection.

With a compiler advertising project language0.30, run from this directory:

```sh
nex check
nex eval
nex run --profile release
nex test
nex test --target web
```

`nex.json` explicitly selects0.30. Ordinary `state` functions use one sequential
context; this does not enable shared mutable references across tasks or threads.
The [reference guide](../../docs/references030.md) describes migration, ownership
and remaining SDK/platform boundaries. Retained SDK0.246.1 does not support this
source version.
