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

Breakpoints, stack/scopes, stepping and continuation use LLDB. Ordinary watches
and the debug console evaluate pure NEX expressions with bounded captured
values. Missing data is unavailable; no effectful watch executes in the inferior.
An explicitly backtick-prefixed console request is a native LLDB command.
See `expressions.md` for exact stop/handle and paging rules.

The separate extension0.1 prototype has an actual installed VSIX acceptance run
on macOS ARM64 / VS Code1.142.0. That report uses its recorded0.55 compiler.
Current0.56 compiler/source/SDK acceptance is recorded separately in STATUS.md.
Editor support does not add unsupported native targets. Windows/mobile compiler
support, wider IDE/platform verification, LSP, NEX Studio, direct large-root DAP
pages and exact optimized-PC/core mapping remain pending. Project licensing and
public Marketplace publication are separate decisions.

Primary API references: [debugger extensions](https://code.visualstudio.com/api/extension-guides/debugger-extension),
[workspace trust](https://code.visualstudio.com/api/extension-guides/workspace-trust),
[VSIX packaging](https://code.visualstudio.com/api/working-with-extensions/publishing-extension).
