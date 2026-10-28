# NEX editing and debugging: development toolchain 0.81

Extension0.6 adds project debugging above the existing source launch. Open a
trusted physical workspace containing `nex.build.json`, then use **NEX: Debug
Project Component**. Select a native executable and declared configuration.
The configured matching compiler prepares the real source/static/dynamic
architecture. Server workloads, browser debugging and other project commands
remain pending in this editor integration.

An explicit launch configuration provides the same workflow, including custom
manifest filenames:

```json
{
  "type":"nex", "request":"launch", "name":"Debug NEX project",
  "cwd":"${workspaceFolder}",
  "project":{"manifest":"nex.build.json","component":"app","configuration":"debug"},
  "stopOnEntry":false, "args":[]
}
```

Choose either `source` or `project`. The source workflow compiles an independent
entry; use the project workflow to preserve binary dependencies. Save participating
source buffers first: dirty compiled documents prevent launch registration.
The project plans before and after native debug preparation must agree, including
architecture/configuration and source identities. The final artifact/build key
and captured source manifest must match the fresh session. Retargeted entry or
manifest aliases require a new launch. Workspace spellings, including macOS
`/var` aliases, are retained for byte-matching project/provider breakpoints.

The compiler's captured adapter, initialization and source maps supply the
debugger. Saved `program` or adapter fields cannot select an executable independently
of a fresh checked session. Stop and relaunch after source/architecture edits;
these preparation checks are not a continuous editor revision lock. The command
reads a manifest of at most256KiB, up to128 components and32 configurations.
An explicit foreign runtime catalogue is still configured through the CLI;
this launch selection does not infer FFI authority.

The historical editing/source-debug contracts below retain their original scope.

Extension 0.6 activates when a physical .nex document opens in a trusted
workspace. Set `nex.compilerPath` to the matching installed compiler. The
extension starts `nex lsp`, sends unsaved document versions and displays compiler
diagnostics, checked type hover, source definitions, declaration outlines and checked references.
Use **NEX: Restart Language Server** after replacing a compiler installation.
`nex.languageServer.enabled` controls these editing features per resource.

The client uses the compiler's UTF-16 LSP positions, preserves argument
boundaries and checks document versions before displaying replies. Changes are
debounced; a navigation request first sends every open buffer tracked by that connection. Replies are discarded if any connected document changes before delivery. Closing/restarting
an entry cleans up its process, pending requests and diagnostics. Oversized or
non-scalar document text is reported locally and cannot reuse an older index.
The client requires the same 1 MiB/document, 8 MiB/workspace and 128-document
limits as the adapter. File changes notify the server to recheck imports and
physical project/lock metadata. It starts no compiler in restricted or virtual
workspaces. See [the language server guide](lsp.md) for exact semantic coverage.

The adapter analyzes source without saving a buffer or synchronizing the graph.
Normal editor saves still write the user's file. Compiler check/test/task and
reviewed graph patches remain explicit development actions. Language 0.16,
source grammar and canonical identities are unchanged.

Runtime client code uses Node built-ins and the VS Code API; no runtime npm
package is required. The separately locked development dependencies package and
test the VSIX. Installed-SDK Node/server acceptance, the compiler's full suite
and actual installed VS Code acceptance have distinct evidence scopes. Current
0.70 integration is a candidate until its recorded checks pass. Identifier hover
uses analysis/3 source signatures, lexical parameters, aliases and trait members;
builtin types have no physical definition. References use
the coverage/limits in lsp.md. Completion/rename, parser recovery/incremental indexing, other editors/platforms
and NEX Studio remain pending.

The existing native debugger workflow follows. Its historical 0.56 results keep
their original compiler/source scope.

# NEX editor integration

Toolchain0.56 keeps source language0.16 unchanged and installs the VS Code
extension sources under `share/nex/editor/vscode`. The extension registers the
`nex` launch type and `.nex` source files. Native debugging uses the matching
compiler, Python, LLDB and existing pure-watch bridge on the extension host.

From a source checkout, run:

```sh
cd editor/vscode
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run package -- --out /absolute/output/nex-language-tools.vsix
```

The same packaging commands work in the installed `share/nex/editor/vscode`
directory, except its focused tests use `node --test test.js`. Node22+ and npm
are development prerequisites. The separate npm lock pins the official packager
and test harness; packaging includes no runtime npm dependencies. It creates a
VSIX without installing it or publishing to the Marketplace.

Install through VS Code's **Extensions → Install from VSIX**, or explicitly run
`code --install-extension /absolute/output/nex-language-tools.vsix`. Set
`nex.compilerPath` to the installed compiler's `bin/nex`, or use PATH. Compiler
paths and program arguments are separate process arguments, never shell commands.

In a trusted physical workspace, use this launch configuration:

```json
{
  "version": "0.2.0",
  "configurations": [{
    "type": "nex", "request": "launch", "name": "Debug NEX",
    "source": "${workspaceFolder}/main.nex",
    "cwd": "${workspaceFolder}", "stopOnEntry": false, "args": []
  }]
}
```

Save sources before launching. The extension asks the selected compiler for a
fresh `nex debug SOURCE --kind nex-dap --json` response. The session's manifest,
build key and revision must agree. It retains the compiler's formatter and
explicit foreign execution arguments. A saved manifest alone cannot choose
an arbitrary adapter command. Restricted and virtual workspaces cannot compile
or debug through this extension.

Original-file breakpoints map individual compiler debug paths to physical files
only after byte equality with their frozen projections. Changed/missing library
files retain frozen source mappings. If the selected entry changed during
preparation, save it and launch again. Stop and relaunch after any source edit;
the preparation check is not a continuous editor revision lock. The underlying
compiler/watch evaluator continues to use its captured sources and exact build.

The extension configures the verified source mappings with escaped LLDB arguments
before the compiler's pre-run commands. It does not pass them through lldb-dap's
unescaped `sourceMap` command construction. This keeps quotes, backslashes and
Unicode in original-file paths intact. For a source checkout, run the actual
native breakpoint/watch regression with `python3 tests/editor.py build/nex --live`;
the regular editor suite also checks launch validation and source-byte matching.

Breakpoints, stack/scopes, stepping and continuation use LLDB. Ordinary watches
and the debug console evaluate pure NEX expressions with bounded captured
values. Missing data is unavailable; no effectful watch executes in the inferior.
An explicitly backtick-prefixed console request is a native LLDB command.
See `expressions.md` for exact stop/handle and paging rules.

The separate extension0.1 prototype has an actual installed VSIX acceptance run
on macOS ARM64 / VS Code1.142.0. That report uses its recorded0.55 compiler.
Current0.56 compiler/source/SDK acceptance is recorded separately in STATUS.md.
These0.56 statements describe that historical cohort. Current support and
remaining Windows/mobile host, IDE/platform, NEX Studio and optimized-PC/core
work are recorded in STATUS.md. Project licensing and
public Marketplace publication are separate decisions.

Primary API references: [debugger extensions](https://code.visualstudio.com/api/extension-guides/debugger-extension),
[workspace trust](https://code.visualstudio.com/api/extension-guides/workspace-trust),
[VSIX packaging](https://code.visualstudio.com/api/working-with-extensions/publishing-extension).

The development toolchain 0.66 adds a separate stdio LSP adapter and readonly compiler analysis, described in [lsp.md](lsp.md). Debugger activation remains independent. Later0.67 adds actual installed client/debugger checks; current0.68 validation retains its own scope.

Frozen debugger source projections retain their captured debugger context. The client excludes internal .nex files and the projections reported by a fresh debug session from live source analysis.
