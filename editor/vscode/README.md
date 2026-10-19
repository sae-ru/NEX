# NEX Language Tools for VS Code

Development extension for the installed NEX native debugger. It registers the
`nex` debug type and `.nex` files. Breakpoints, stepping, stack/scopes and pure
NEX watches use the compiler's existing stdio bridge and LLDB backend.

The matching NEX development SDK, LLVM/native compiler, Python and `lldb-dap`
must already be installed on the extension host. Set `nex.compilerPath` to its
`bin/nex` executable, or put it on PATH. A path containing spaces remains one
executable. No tool is downloaded automatically. Native target/platform support
is the compiler's actual support; this package does not add Windows or mobile
execution. Remote development runs tools on the workspace extension host.

Use a trusted physical workspace. Add this to `.vscode/launch.json`:

```json
{
  "version": "0.2.0",
  "configurations": [{
    "type": "nex",
    "request": "launch",
    "name": "Debug NEX",
    "source": "${workspaceFolder}/main.nex",
    "cwd": "${workspaceFolder}",
    "stopOnEntry": false,
    "args": []
  }]
}
```

Start debugging. The extension asks that compiler to build a fresh debug-session
descriptor, then uses its frozen executable, captured formatter, source map and
adapter command together. Original-file breakpoints use exact file mappings only
when the original bytes equal the corresponding frozen projection. Changed or
missing library files retain the frozen source fallback; a changed selected entry
requires a fresh launch. Stop and relaunch after editing a running program.
A `.nex` source is required; a saved manifest alone
cannot launch an arbitrary adapter. Compiler diagnostics are displayed before
launch. Unsaved buffers must be saved before starting the debug session.

Watches are pure NEX expressions over captured stopped values. Missing/unavailable
data remains explicit. An explicit backtick-prefixed debug-console request is an
LLDB command. This extension does not add mutation, IntelliSense, an LSP, hot
reload or NEX Studio. Current acceptance status is recorded separately; adapter
tests are not an actual VS Code UI acceptance run.

This extension source has no third-party runtime npm dependencies. Project license
selection and public Marketplace publication remain pending. No publishing or
installation is performed by source generation or packaging.

API references: [debugger extensions](https://code.visualstudio.com/api/extension-guides/debugger-extension),
[workspace trust](https://code.visualstudio.com/api/extension-guides/workspace-trust),
[VSIX packaging](https://code.visualstudio.com/api/working-with-extensions/publishing-extension).
