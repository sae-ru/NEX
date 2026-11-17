# Persistent native host session

This language030 project supplies real ABI8 exports for a matching-runtime C++
host. `core` creates/updates cells, returns immutable views and typed errors;
`mid` calls `core` across a separate image; `files` demonstrates explicit file
authority and ownership across calls. The ordinary application prints `42`.

```sh
nex project nex.build.json --kind build --configuration release --json
nex project nex.build.json --kind run --component app --configuration release --json
```

Run commands from a writable copy of this directory. Project build artifacts
and graph/cache files belong in `.nex/`, which is not source version history.
Commit the `.nex` source files, `nex.json`, `nex.build.json`, tests and any explicit
dependency locks; keep generated outputs out of Git.

The integration harness `tests/native_task_sessions.py` consumes the checked
PIC-stage archives and their `task-provider.json` accessor records, links code-only
images and invokes them through `nexrt::NativeTaskSession`. Images resolve runtime
operations to one matching C++ host; loading ordinary project shared libraries
with their separate common runtime into that host is not equivalent.

Read [the session contract](../../docs/native-task-sessions.md). It specifies
per-call controls, image/heap ownership, error outcomes and file grants. This
example does not supply a stable C ABI, native UI event pump or portable SDK.
