# Java long arithmetic — source0.30

This example prints `java-long-ok`. It covers signed64 wraparound, MIN/-1,
multiplication, logical right shift, narrowing and a typed division error.

From this directory, using a compiler advertising `standard_library.modules.java_long`:

```sh
nex check
nex run --profile release
nex test
nex test --target web
```

`nex.json` selects source0.30. Commit the source, manifest and reviewed lock;
keep `.nex/` out of Git. The [API guide](../../docs/java-long.md) describes the
nominal representation, exact arithmetic and remaining migration requirements.
The immutable SDK0.246.1 does not ship this development module.
