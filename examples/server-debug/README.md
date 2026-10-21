# Debug a server and its actual shared provider

Candidate toolchain0.85 / language0.16. Run commands in this directory with a
matching macOS/Linux host SDK and LLDB/Python. Keep `private/` and `.nex/` out
of your application's Git source.

```sh
mkdir -p private
nex token --user developer --auth private/auth.json --json
nex project --kind debug --component service --json --adapter nex-dap -- \
  --auth private/auth.json --database private/debug.sqlite --port 0 --timeout-ms 60000
```

The token command displays a development bearer token. Keep it in your HTTP
client's runtime state. Debug preparation returns the exact native descriptor;
it starts neither the server nor a database. VS Code0.7 can use a project launch
with the same arguments. Place a breakpoint at `core/main.nex:4`, start the
debugger, and send a POST body to `/api/debug` at the reported loopback port with
the development bearer token. The stopped worker's `prefix+body` watch reads
the actual values; continue to receive the JSON string `Я🧠:` plus your body.

The provider is an actual shared library. The final server uses one runtime and
normal checked request/storage semantics. Stopped time counts toward the
existing request deadline; an expired request rolls back its write on resume.
Follow [the server debugger guide](../../docs/server-debugging.md) for source
launches, FFI authority, DAP lifecycle and the separate platform verification
limits. This is a development example, not a deployment configuration.
