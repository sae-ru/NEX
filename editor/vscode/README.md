# NEX Language Tools 0.3

Open a .nex file in a trusted physical workspace. Select an installed NEX0.68+
compiler with `nex.compilerPath`; its matching resources provide `nex lsp`.
The extension displays unsaved-source diagnostics, type hover, definitions, references and
an outline through that server. **NEX: Restart Language Server** restarts the
connection; `nex.languageServer.enabled` enables editing features per resource.

References distinguish lexical bindings and nominal fields, using the coverage
and limits in docs/lsp.md. A query flushes all connected open buffers; a reply
from an older document context is discarded.

The client starts one literal executable per workspace/compiler configuration,
uses full document versions and cancels superseded requests. Diagnostic source
ranges use UTF-16. Source analysis does not save files, write graph history or
execute a NEX program. Documents are limited to 1 MiB each, 8 MiB total and128
open documents per connection. Invalid/oversized text gets a local diagnostic
and cannot display an older semantic result. Check/test/task acceptance remains
part of ordinary project development.

This extension uses no runtime npm dependencies. Current source/server coverage
and pending completion/rename and broader reference coverage are in the installed docs/lsp.md guide.
Compiler, installed SDK and actual IDE checks have separate evidence scopes.

The native debugger usage and packaging instructions follow.

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
Verified source mappings use escaped LLDB arguments, including when original
paths contain quotes, backslashes or Unicode characters.
With the matching toolchain 0.57 bridge, native list/byte roots expose indexed
children beyond the text preview. Page requests return at most1000 children;
large named/string expansion retains its separate limits. Native previews are
distinct from exact pure-watch captures.
A `.nex` source is required; a saved manifest alone
cannot launch an arbitrary adapter. Compiler diagnostics are displayed before
launch. Unsaved buffers must be saved before starting the debug session.

Watches are pure NEX expressions over captured stopped values. Missing/unavailable
data remains explicit. An explicit backtick-prefixed debug-console request is an
LLDB command. Native debugger expressions do not add mutation or hot
reload or NEX Studio. Current acceptance status is recorded separately; adapter
tests are not an actual VS Code UI acceptance run.

This extension source has no third-party runtime npm dependencies. Project license
selection and public Marketplace publication remain pending. No publishing or
installation is performed by source generation or packaging.

API references: [debugger extensions](https://code.visualstudio.com/api/extension-guides/debugger-extension),
[workspace trust](https://code.visualstudio.com/api/extension-guides/workspace-trust),
[VSIX packaging](https://code.visualstudio.com/api/working-with-extensions/publishing-extension).
