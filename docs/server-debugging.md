# HTTP server debugging (candidate toolchain0.85)

Use a matching host SDK with LLDB/Python and `lldb-dap`. This extends native
debugging to HTTP servers without changing language0.16, source effects, graph
history or native ownership. Preparation builds/checks the selected application;
it does not start a listener, read its auth file or create its runtime database.
Platform and installed extension acceptance are recorded separately.

## Project launch

```sh
nex project --kind debug --component service --configuration debug \
  --adapter nex-dap --json -- \
  --auth private/auth.json --database private/debug.sqlite \
  --port 0 --timeout-ms 60000
```

The `service` component must have `kind: server`. It consumes its declared source,
archive and shared providers, one runtime, and the same checked entry/ABI as a
normal server build. A plain interactive `project --kind debug` opens LLDB with
the captured formatter and runtime arguments installed. Use the exact native
symbol from `observation.manifest` for a function breakpoint, or the captured
source path for a line breakpoint. `--json` returns a `nex.project-session/1`;
its `observation` is `nex.debug-session/1`. The latter names the actual final
artifact, `application_kind: http_server`, manifest and matching adapter command.

Start that adapter and pass its returned launch object through DAP. Preserve
all compiler/editor `initCommands`, `preRunCommands` and source maps. They bind
the right program, source and previews. An HTTP client sends a request after
the server reports its listener. At a stop use the reported thread ID for
stack/scopes/watch requests: a request normally runs on a worker thread.
Watches inspect stopped values without running inferior code. Discard old
frame/value references after continuing.

## VS Code0.7

Open a trusted physical workspace with the matching compiler configured. Add:

```json
{
  "type": "nex", "request": "launch", "name": "Debug NEX server",
  "cwd": "${workspaceFolder}",
  "project": {"manifest":"nex.build.json","component":"service","configuration":"debug"},
  "args": ["--auth","private/auth.json","--database","private/debug.sqlite",
           "--port","0","--timeout-ms","60000"]
}
```

Place a breakpoint in the handler or a provider's original `.nex` file, launch,
then send an authenticated HTTP request. The extension checks plans before/after
compilation, the actual server artifact, source aliases and dirty compiled
buffers. Source maps are byte-checked against the captured projection.
**NEX: Debug Project Component** also offers server components; its runtime JSON
input accepts `args` and optional `foreign`. Cancellation or lost workspace
trust prevents launch. The command does not save those runtime settings.

For an independent source launch use `source: "service/main.nex"` and
`target: "server"` instead of `project`. That invokes the source build path;
use a project launch when preserving declared binary dependencies matters.
The CLI source descriptor is `nex debug FILE --target server --kind nex-dap
--json`. Its legacy interactive arguments after `--` remain LLDB arguments;
editor `args` and project arguments are application runtime values.

## Authority, limits and lifetime

Supply auth, storage, TLS and CORS settings explicitly at runtime. Keep operator
files and credentials out of application Git sources. Preparation does not
generate or capture a bearer token, auth file or application database. The
example below uses a separate synthetic development user; choose suitable
runtime data for your application.

For source foreign calls supply CLI `--foreign HOST.json`, or editor
`foreign: "operator/host.json"`. The compiler checks current pins/signatures/
grants before tools/execution. The editor passes this field to the compiler,
preserves its returned runtime grant and rejects conflicting grant flags in
`args`. A saved manifest/receipt never grants native authority. Native modules
remain trusted code. Preparing a descriptor initializes none of them.

Runtime arguments are at most128 UTF-8 strings without NUL,4 KiB each and64 KiB
total, including compiler-supplied grant arguments. The actual executable/server
and host ABI must match its captured build.

Request budgets, cancellation, database ownership and deadlines remain active.
Time spent stopped counts toward the request deadline. `--timeout-ms 60000`
selects the existing maximum60second deadline; it does not disable checks.
After an expired stopped request resumes, the normal timeout response and
transaction rollback apply. Start a new request for another observation.
Graceful SIGTERM shutdown retains ordinary request cleanup; forced debugger
termination has the same limits as killing any native process.

Automatic workload-driven debugger/task replay, browser debugging, packaged
deployment-image debug provenance and other platform debugger support retain
their separate pending status. See [debugging](debugging.md),
[editor](editor.md), [project builds](project-build.md) and the executable
[server example](../examples/server-debug/README.md).
