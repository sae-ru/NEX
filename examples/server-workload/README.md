# Profile an actual native server

Read [the workload guide](../../docs/server-workload.md). Copy this directory to
an owned workspace before building; commit the source and workload JSON files.
The checked plan pins the workload bytes and trusted runner. The `core` component
is a separately linked dynamic library with one shared application runtime.

Generate local credentials with `nex token --auth /tmp/nex-workload-auth.json
--user bench --json`, then set `NEX_WORKLOAD_TOKEN` to its token in your shell.
Do not commit that value, credential file or database.

```sh
nex project --kind plan --component api --workload workload.json --json
nex project --kind profile --component api --workload workload.json --profile-output /tmp/nex-server-profile.json --json -- --auth /tmp/nex-workload-auth.json --database /tmp/nex-workload.sqlite --workers 4
```

The first phase measures two requests and the second twelve, after two warmup
requests. Expected bytes include the Unicode scalar character 🧠. This is a
small reproducible correctness example; its timings are not a capacity claim.
