# Native debugging — NEX toolchain 0.15

Current source language is 0.15. Debug information describes real native parameters,
stack locations, scalar types and lexical binding scopes. Heap types are named
aliases for their actual runtime handles. They are not fabricated inline C
structures. LLDB reads their contents through the matching captured formatter.
DWARF uses the C language code for debugger interoperability; this does not add
C or C++ expression semantics to NEX.

## Stop and inspect

```sh
nex debug examples/debugging/main.nex
```

This builds the normal debug profile and launches LLDB with the build's frozen
`debugger/lldb_nex.py` and `debug.json`. With the included example:

```text
breakpoint set --file source.nex --line 12
run
frame variable
nex-values
next
thread backtrace
continue
```

Line 12 is inside the inner binding of `total`. Both the outer `40` and inner
`42` remain represented with their own scopes. At line 14 only the outer binding
is in scope; line 16 observes its updated value `43`. The imported increment
function has its own captured `sources/model.nex` and parameter/local records.
Use `nex context --symbol NAME` to obtain a function's exact `native_symbol` for
a name breakpoint. Debugger function display may use that native linkage name.

Source paths point to immutable projections in the shared `source-cache/`,
including archived sources and reused native modules. A source-based debug command checks the current program; use
`nex debug --revision HASH` to debug a stored revision even after original files
were changed or deleted. `debug.json` maps original paths to their projections
and records the semantic revision, build key, function names and native symbols.

If the host prevents launching children under a debugger, ordinary compiled
execution may still work. Report that limitation directly: source/symbol lookup
alone does not prove live debugging. Host debugger permissions and installed
LLDB with Python scripting support are prerequisites. Optimized `profile`/`release` builds can lose values or
reorder source steps; use the default `debug` profile for variable inspection.

## Value previews and model tools

The formatter reads the stopped process through LLDB's SBValue APIs and standard
C++ library layouts/formatters. It never evaluates an expression, invokes an inferior
function, retains an application value or changes a value's ownership. Strings
read a bounded byte prefix using the actual string length and buffer, preserving
embedded zero bytes, literal escapes and Unicode. A truncated UTF-8 prefix ends
before an incomplete scalar and displays an ellipsis. Lists, named records and recoverable results have summaries and
expandable children. Synthetic aggregate children retain their runtime
`nexrt::Value` type; their summaries show the source values. Native scalar
parameters/locals retain the NEX `i64`/`bool` aliases.

Previews bound depth to six, collection children to 32, recursive value visits
to 256 and string reads to 4096 bytes before escaping. Unavailable or incompatible
data produces an explicit unavailable preview. The runtime-view identifier is
versioned; loading an incompatible manifest is rejected. The current exercised
hosts are macOS ARM64 with Apple LLDB/libc++ and Ubuntu 24.04 ARM64 with
LLVM LLDB 22/libstdc++. Linux x86-64 builds/DWARF run under emulation, but
live ptrace/debugger support there remains unverified. Other runtime/debugger
combinations still need platform verification.

`nex-values` prints a `nex.debug-values/1` JSON object for the selected stopped
frame: revision, logical function when mapped, native symbol, projected file,
line and a list of `{name, type, value}` previews. Duplicate names remain separate
entries, preserving shadowed bindings. At most 256 variables are returned and
`truncated` reports a clipped frame. Values are debugger previews, not a lossless
wire serialization and not NEX source expressions. Retrieve fresh values after
each stop; do not reuse a previous frame's locations.

## Editor / Debug Adapter Protocol

For the NEX VS Code extension and original-file breakpoint mapping, see
[editor.md](editor.md). Its package and current compiler acceptance are separate.

```sh
nex debug examples/debugging/main.nex --kind dap --json
```

The `nex.debug-session/1` response contains `adapter: "lldb-dap"`, the matching
manifest and a `launch` object. Put that object in the `configurations` array of
a compatible editor's launch settings. Configure the editor to use an installed
`lldb-dap`; NEX does not download it or start a listening server. The launch
configuration names the frozen executable and installs its matching previews
through `initCommands`.

The adapter supplies normal DAP breakpoints, stack frames, scopes, variables,
children, stepping and resume/exit handling. In an LLDB DAP REPL, the command
`` `nex-values `` explicitly requests the read-only NEX frame report. For pure NEX watches and expandable computed values, use the added `nex_adapter` descriptor or `--kind nex-dap`. The bridge uses exact snapshots and a separate NEX interpreter. See [expressions.md](expressions.md) for setup, supported expressions and limits. The direct backend retains its own expression language.
`nex debug FILE --json` returns the same session descriptor without launching a
debugger. Without `--json` and with the default `--kind lldb`, it starts LLDB;
arguments after `--` go to LLDB.

For source-operation candidates at a stop, use `nex-operation` and resolve its deterministic site through `nex context --site KEY --revision HASH`. Co-located candidates are explicit; see [operations.md](operations.md) for local persistent identities, exact source hashes and optimized-PC limits.

## Integrity and validation

The native build key includes the formatter content. Cache hits verify the
captured formatter/stdio adapter, exact debug manifest, all projected source contents and,
on macOS, the packaged DWARF image as well as the executable and notices.
Corruption causes a rebuild. Installed SDKs include the matching debug guide
and formatter. Keep the build workspace (including `source-cache/`, runtime projections and
`.dSYM`) when debugging; copying
only an executable with `-o` does not export this whole debugging workspace.

```sh
python3 tests/debugging.py build/nex
python3 tests/debugging.py build/nex --live
```

The normal suite checks real DWARF verification, types/scopes, native/interpreter
agreement, optimized execution, cache repairs, session generation and archived
source projections. The opt-in live run additionally launches LLDB and an actual
`lldb-dap`, verifies stops/steps, nested binding values, mutation, imported frames,
value previews/children and clean completion. It requires host debugger launch
permission; the normal suite does not silently claim those live checks.

Function/frontend incremental reuse, string chunk reads and direct expansion of uncaptured large roots, direct browser NEX source
maps, crash/core workflows and other target platforms
remain parts of the open development plan.

Native function/managed shallow allocation profiling and optional Tracy CPU capture are documented in [profiling.md](profiling.md).

Checked native runtime failures can be resolved through `nex run --json` or
`nex diagnose --manifest DEBUG.json --log STDERR.log --revision HASH`. See the
[native diagnostic guide](native-diagnostics.md) for archived sources, local IDs,
operator request logs, bounds and attribution limits.
