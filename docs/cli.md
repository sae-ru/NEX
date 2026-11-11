---
status: current
applies_to: "toolchain 0.169; language 0.28"
owner: repository
---

# Command help, completion and quiet output

The compiled CLI catalogue supplies command help, completion candidates, guide
names and parser option types/aliases. The existing operation handlers continue
to validate value ranges, combinations, platform limits and revision guards.
Help does not execute the selected operation, read project metadata, load imports
or open a graph. It works with a missing source file or invalid local manifest.

```sh
nex help                        # short command index
nex help build                  # only build's parameters
nex build --help                # same command help, also accepts -h
nex help build --json           # nex.cli-help/1
nex describe --field cli_interface --json
```

Unknown commands/options and missing option values still report diagnostics.
Help is not a way to execute or preflight a partly specified operation. Known
values in help/completion are hints; target triples, configured component names,
symbols and paths are open domains. Some combinations require a selected kind,
profile or target: read the command's feature guide for those rules.

Command/index help text is bounded to 16 KiB, help JSON to 32 KiB. The compiled
catalogue works without Python, resources or source fallback. A `feature_guide`
link selects more detail when needed. The private experiment and completion
query remain addressable through explicit help, without appearing in the public
command index. `nex lsp` retains its protocol: use `nex lsp --help --json` for
JSON help, rather than adding `--json` to an actual LSP session.

## Completion

Print a script, inspect it, and source it in the selected shell. NEX writes no
shell profile and installs nothing automatically.

```sh
nex completion --kind bash > /tmp/nex-completion.bash
source /tmp/nex-completion.bash

# In zsh, initialize its normal completion system first:
autoload -Uz compinit
compinit
nex completion --kind zsh > /tmp/nex-completion.zsh
source /tmp/nex-completion.zsh
```

Fish uses `nex completion --kind fish`; PowerShell 7.3+ uses
`nex completion --kind powershell`. Save the output as a shell script and source
it using that shell's normal mechanism. The PowerShell adapter uses native
argument completion and a literal word array, with no command-line evaluation.
Those two generated adapters still need execution on their actual shells;
generation alone is not platform qualification.

Shell adapters ask the selected `nex` on PATH for candidates each time. This keeps
them aligned with that compiler's catalogue after a toolchain upgrade.

```sh
nex complete --json -- build --profile ''
# candidates: debug, profile, release
nex complete -- build --pr
# --profile
```

Words after the query's `--` are literal completion data; omit the leading `nex`.
The last word is the current prefix, including an explicit empty string after a
space. Put `--json` before `--`; after it, `--json` is completion data. A query
never launches the typed operation or reads the filesystem/project. It suggests
public commands, command-specific flags/aliases and known option values. It
consumes previously typed value arguments, excludes already used options and
stops suggesting NEX flags after an application's `--` separator. It does not
retrieve graph symbols, project components or secrets. File completion is left
to the shell. Empty positional prefixes return no NEX candidate so shell file
completion can take over.

`nex.cli-completion/1` includes `candidates`, `prefix`, `command` and `expects`.
Queries accept up to 128 words of at most 4096 bytes; JSON output is bounded to
16 KiB. `nex completion --kind SHELL --json` returns the generated script as
`nex.cli-completion-script/1` for tools that should not evaluate shell code.

The adapters use the documented interfaces of
[Bash](https://www.gnu.org/software/bash/manual/html_node/Programmable-Completion-Builtins.html),
[zsh](https://zsh.sourceforge.io/Doc/Release/Completion-System.html),
[fish](https://fishshell.com/docs/current/cmds/complete.html) and
[PowerShell](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/register-argumentcompleter).
Execution evidence is scoped separately from those API references.

## Quiet success status

```sh
nex check src/main.nex --quiet
nex build src/main.nex --quiet
nex check src/main.nex --quiet --json
```

`--quiet` suppresses NEX's own routine successful summaries from `init`, `check`,
`lock`, `build` and `package`. It also applies to non-preview formatting modes,
which are normally silent already. It does not suppress child build-tool output.

Program stdout, data/query results, source/IR output, formatting preview and help
remain available. Errors and unsuccessful output remain visible. With `--json`,
quiet has no effect on the command's response format or diagnostics. It does not
change execution, graph updates, compiler checking or acceptance criteria. It is
not an alternative machine protocol; use the command's `--json` contract.
The capability's `project_opened: false` describes help/completion queries;
ordinary commands with quiet keep their own graph and execution behavior.

Existing raw-output forms retain their own behavior: for example LLVM/MLIR source
emission writes IR or the selected output file, rather than acquiring a new JSON
success wrapper. The help JSON describes options; it does not change those older
output contracts.

The functional group `tests/cli_interface.py` covers bounded per-command help,
literal completion words/value consumption, parser option behavior, quiet
stdout/JSON/error preservation and real available Bash/zsh callbacks. The normal
formatter and core checks also exercise the refactored option parser. Full
platform/SDK acceptance remains a separate milestone.

The local 0.169 functional block passed six CLI methods (15.248 s), seven
formatter methods (9.310 s) and 12 core groups (22.78 s). Available callbacks ran
in Bash 3.2.57, Bash 5.3.9 and zsh 5.9. Fish/PowerShell generation was checked;
execution in those shells is still pending. These single-host observations are
not SDK or wider platform qualification.
The [scoped receipt](evidence/cli-interface-0.169.0-2026-11-11.json) pins the
implementation/compiler and retains the initial failures and later refinements.
