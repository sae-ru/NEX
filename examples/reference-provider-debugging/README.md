# Debugging cells across native libraries

This ordinary language030 project prints `42`. A child task captures application
cells and calls `mid`, which calls `leaf` and the pure helper. `leaf` changes a
cell and throws `Fault(cell)`; `mid` catches it and returns the new value.

```sh
nex project nex.build.json --kind run --component app --json
nex project nex.build.json --kind debug --component app --adapter nex-dap --json
```

For LLDB, use `--adapter lldb`, then set a logical breakpoint on
`ref_debug_leaf::work`. At the stop, `nex-task-inspect state` shows41 and
`nex-eval input+pure::offset()` yields42. `nex-task-out` crosses the library/error boundary;
inspecting `state` in the caller shows42 with the same diagnostic identity.

The checked-in configuration uses static libraries. For fixed shared libraries,
set component `kind` to `shared_library` and consuming dependency linkage to
`dynamic`. A mixed layout can keep `mid` static and make `leaf` shared, with the
pure helper embedded statically in `leaf`. The permanent live suite executes all
three modes and a source-absent captured/packaged/replayed launch.

Keep source files, `nex.json`, `nex.build.json` and explicit locks/tests in Git;
generated `.nex/` caches and build/package outputs are disposable artifacts.
See [the contract](../../docs/reference-provider-debugging.md) for ABI, source,
image ownership and remaining delivery boundaries. A normal debug-profile build
does not automatically enable logical instrumentation.
