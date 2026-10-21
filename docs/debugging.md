# Native debugging — NEX language 0.17

Current source language is0.17. Debug information describes real native parameters,
stack locations, scalar types and lexical binding scopes. Heap types are named
aliases for their actual runtime handles. They are not fabricated inline C
structures. LLDB reads their contents through the matching captured formatter.
DWARF uses the C language code for debugger interoperability; this does not add
C or C++ expression semantics to NEX.

Toolchain0.89 fixes adapter shutdown on macOS/Linux. Its client/backend input
readers use interruptible descriptor reads and a wake pipe, then join before
stdio destruction. Backend EOF, client EOF, malformed packets and SIGINT/SIGTERM
also interrupt a partial header/body. This avoids a Python3.9 fatal buffered-stdin
lock during interpreter finalization when a client leaves stdin open. SDK
acceptance now checks the adapter's actual exit status so an aborted adapter
cannot pass merely because earlier breakpoint/watch requests succeeded.
This changes no source syntax, effects, ownership semantics or language version.
The matching installed SDK/editor/live debugger gates remain required.

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
function has its own immutable projection and parameter/local records; find its
path through the `sources` entries in `debug.json`.
Use `nex context --symbol NAME` to obtain a function's exact `native_symbol` for
a name breakpoint. Debugger function display may use that native linkage name.

Source paths point to immutable projections in the shared `source-cache/`,
including archived sources and reused native modules. A source-based debug command checks the current program; use
`nex debug --revision HASH` to debug a stored revision even after original files
were changed or deleted. `debug.json` maps original paths to their projections
and records the semantic revision, build key, function names and native symbols.

Within a project build cache, a virtual DWARF source origin identifies its
logical module, independently of entry/import roles or package aliases. A
static provider and its consumer therefore map the same origin to the same
captured module text. Projections use a content-derived directory and the
filename `source.nex`; select the full projection path for an unambiguous file
breakpoint. Unrelated edits can still reuse function objects when their emitted
source coordinates have not changed. Core capsules retain canonical source
storage and preserve historical imported DWARF basenames when preparing a
verified temporary workspace.

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

Toolchain0.57 adds native indexed pages to the matching NEX stdio bridge
(`--kind nex-dap`). Native `list<T>` and `bytes` roots advertise their actual
indexed child counts, up to2147483647. Text previews remain bounded to32
elements. A DAP `variables` request can start at a later index without reading
the preceding elements. Both `start` and `count` must be nonnegative signed32
integers; omitted/zero `count` means at most1000 children. Larger requested
counts also return at most1000. Native replies add `body.nex.native_page` with
`start`, `requested_count`, `returned_count` and `limit:1000`, described by
`llm/dap-native-page.schema.json`. The matching bridge rejects oversized backend
pages. A named-only request on a NEX indexed root returns no children.

Use standard stack/scopes requests, then the root's `variablesReference` and
`indexedVariables` to request pages. References expire on execution or a new
stop, and replies from an earlier stop are rejected. These are read-only native
previews from this runtime's DWARF layout, not complete wire values, retained
frame captures or interpreter inputs. Plain `--kind dap` uses LLDB directly and
does not apply the bridge's1000-child request bound. Named aggregate previews,
very large indexed counts beyond the DAP bound and direct string expansion
retain their separate limits. String scalar windows use the existing checked
expression/capture protocol.

`examples/debugging/pages.nex` creates a32768-element list and4MiB byte value.
Run `python3 tests/native_pages.py build/nex --live` for actual late-index,
default/oversized-page, filter, unchanged-stop and stale-reference checks.
The default suite skips actual process launches unless `--live` is supplied.

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

Darwin LLDB cannot track loaded images when an executable's physical path
contains a literal backslash. For those project/build paths, `nex debug` uses
an owned mode-0700 native build cache in a temporary location without backslashes.
The project build directory retains its cache pointer; repeat descriptors reuse
the same owned cache. LLDB, raw DAP and the NEX DAP bridge all receive the actual
executable/manifest paths from that cache. Source identity, frozen source maps,
build checks and application working directory retain their normal contracts.
Keep the reported cache while debugging. If the system removes temporary files,
request a fresh descriptor to rebuild it. Ordinary run/build outputs remain in
their selected build directory.

For source-operation candidates at a stop, use `nex-operation` and resolve its deterministic site through `nex context --site KEY --revision HASH`. Co-located candidates are explicit; see [operations.md](operations.md) for local persistent identities, exact source hashes and optimized-PC limits.

## Integrity and validation

NEX frame reports, operation candidates and exact watches require the selected
frame to belong to the same loaded executable module as the manifest context.
A matching function name or pathname is insufficient: LLDB can load a core's
actual executable alongside another selected image. A different loaded module
is rejected before variables are captured or graph identities are assigned.
This guard does not authenticate process data or add a portable core archive
format. Core use through raw LLDB options still requires matching artifacts and
its own platform validation.

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

InstalledSDK0.89 acceptance also exercises the result-propagation sample through
native/reference/TypeScript, checks profile ownership/completed calls, then
replays archived source and runs a standalone binary without compiler resources.
These are required evidence, not a new workflow phase or relaxed criterion.

## CPU worker thread discovery

Some LLDB DAP backends return a one-shot launch-time thread list after a worker
has stopped. If a successful list omits the actual stopped thread, the NEX
adapter requests one fresh list before replying to the editor. A second omission
or a changed stop fails inspection. It never invents threads or resumes the
process. CPU callback breakpoints and pure watches use the same archived source
projections and matching compiler as ordinary frames.
