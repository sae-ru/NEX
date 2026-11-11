# Containers example

Run with the current toolchain:

```sh
nex run --profile release --json
nex test --target web --json
```

`std/map.nex` and `std/set.nex` are immutable, insertion-ordered, list-backed
containers; lookup and update are O(n). See [docs/containers.md](../../docs/containers.md).
