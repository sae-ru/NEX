# NEX expressions in stopped frames — toolchain 0.13

NEX expressions use the language 0.5 parser, module resolver, type/effect/realm
checker and reference interpreter. They execute in a separate compiler process
using exact captured values. They do not call functions, resume threads, write
memory or retain handles in the application being debugged. A source function
can be called in the interpreter only when the checked expression is pure and
respects the stopped function's realm and import visibility.

## LLDB

```sh
nex debug examples/debugging/main.nex
```

At the inner breakpoint (line 12):

```text
nex-eval total
nex-eval model::increment(total) + items[1]
nex-eval person.name
nex-eval len(label)
nex-eval label[3]
nex-eval push(items, 99)
nex-eval unwrap(reply)
nex-frame person
```

The first two results are 42 and 84. `total` resolves to the innermost active
binding. At the outer breakpoint it is 40. A helper's parameters and locals
use that helper's module/import scope. Initializers cannot see a later binding.

`nex-eval` returns `nex.expression/1`: type, exact typed wire `value`, display,
read binding names, language/revision/build/function/stop identity and limits.
Integers in wire values are canonical decimal strings; booleans remain booleans.
Display is bounded to about 4096 bytes and reports `display_truncated`; the wire
value is complete or the operation fails. Display text is not an input value.

`nex-frame EXPRESSION` captures the variables referenced by the expression and
returns `nex.debug-frame/1`. Other visible names retain type metadata and an
explicit unavailable reason. This can be saved for offline inspection. It is
different from `nex-values`, which remains a bounded human-readable preview.

Supported expressions include checked arithmetic, short-circuit conditions,
Unicode scalar indexing/slicing, fields, immutable list/record/result operations,
constructors, strict typed JSON builtins and pure user-function calls. Assignments
and statement blocks are not expressions. `print`, environment/storage access
and effectful calls are rejected before evaluation, including inside an otherwise
effectful stopped function. `assert` can fail in the helper without terminating
the application. Newly computed aggregates belong only to the helper.

The command loader accepts an explicit trusted compiler path:

```text
nex-load-debug /path/to/debug.json --compiler /trusted/path/to/nex
```

`nex debug` supplies this automatically. Loading a manifest alone still enables
previews, but does not authorize an executable named inside that manifest.

## DAP and editor watches

```sh
nex debug examples/debugging/main.nex --kind nex-dap --json
```

The descriptor's `adapter_command` is a stdio DAP adapter command; `launch` is its
launch request. Configure a DAP client that supports an external adapter command
with these fields. A launch `type` of `nex` requires that client-side adapter
registration; copying it into an editor without registering the command is not
an installed NEX editor extension. NEX Studio/editor packaging remains pending.

The bridge delegates launch, breakpoints, native scopes, stepping and lifecycle
to the configured `lldb-dap`. It routes watch/hover/ordinary REPL evaluations
through the NEX evaluator. Request a current stack trace before evaluating an
explicit `frameId`. The bridge selects that frame for capture and restores the
previous debugger selection. Source text is base64-encoded inside a single
internal command; newlines cannot become extra LLDB commands.

Computed results retain their NEX type and have read-only expandable fields,
results and list pages. Numeric children display as NEX integers. Backend scope
references and computed references are remapped into separate identities; old
references fail after continue/step/new stops. Variables requests return at most
1000 children per page. `body.nex` on successful evaluate responses contains the
full structured NEX result and exact stop metadata for model tools. DAP
setVariable/setExpression requests are unsupported by this bridge.

In a REPL, an explicitly backtick-prefixed request remains a native LLDB command,
for example `` `nex-values ``. This is an explicit debugger-command interface,
not a NEX expression. Ordinary direct `--kind dap` descriptors remain compatible
with an external `lldb-dap`; their added `nex_adapter` field supplies the NEX
bridge command/launch configuration. The direct backend's expression language is
its own debugger language, so use the NEX bridge for NEX watch semantics.

The backend is found through `NEX_LLDB_DAP`, PATH or Xcode's `xcrun --find lldb-dap`
on macOS. `NEX_PYTHON` optionally selects the Python interpreter for the bridge.
The frozen bridge and formatter are part of build keys/cache integrity. These
are development dependencies; generated applications do not need them.

## Offline and model tools

```sh
nex inspect frame.json --manifest /path/to/build/debug.json \
  --expression 'model::increment(total) + items[1]' --kind plan --json
nex inspect frame.json --manifest /path/to/build/debug.json \
  --expression 'model::increment(total) + items[1]' --json
```

Without a frame filename, `inspect` reads bounded JSON from stdin. The plan
checks types/effects/visibility and returns only the referenced variables and
matching wire schemas; it does not evaluate user code. The LLDB command first
uses this plan, reads those values, then evaluates the expression. Values are
decoded lazily in the helper: an unavailable binding on a nonexecuted
short-circuit branch is not required.

The manifest pins the compiler build, semantic revision and exact complete
source bundle. Inspection checks these before loading archived sources; original
source/library files can have changed or been deleted. It does not open or move
project graph HEAD. The frame's declared name/types and build identity must
match the selected function. `llm/debug-frame.schema.json` describes the format;
the compiler also performs semantic validation.

A saved frame is supplied data. Its IDs/hashes do not authenticate that a value
came from a live process. Live commands obtain fresh values and verify that the
stop did not change while capturing/evaluating; offline inspection reports the
supplied stop identity. A frame from an old compiler build needs its matching
compiler; source language 0.5 and graph identity do not change in this milestone.

## Exact capture and limits

Scalar reads check LLDB errors. Heap reads validate runtime tags, nominal record
names, field order and result shape against the checked wire schema. Standard
strings are read with their actual length through DWARF fields and process
memory, including embedded NUL and long UTF-8 content. Truncated escaped
summaries are never parsed as values. The implementation uses the
[LLDB frame API](https://lldb.llvm.org/python_api/lldb.SBFrame.html) and
[read-only value access](https://lldb.llvm.org/python_api/lldb.SBValue.html).

Capture is bounded to 256 visible entries, 10,000 recursive visits, 10,000 items
per collection, value depth 60 (reserving space for the frame envelope) and 1 MiB of text/frame JSON. The shared strict JSON validator rejects duplicate/escaped-equivalent keys, malformed UTF-8 and packets deeper than 64 before conversion; one leading UTF-8 BOM is accepted. An incomplete binding is
unavailable, never a shortened list or fabricated zero. Only referenced roots
are read, but reading one currently captures that whole root. A field/length of
a very large root can therefore be unavailable; demand-driven partial object
reads remain pending. Unknown C++ layouts and optimized-out locations also
produce explicit failure/unavailability. libc++ on the exercised macOS ARM64
host is verified; other host/layout combinations need their own live checks.

Expression source is at most 8192 UTF-8 bytes, 1024 lexer tokens (including the end marker) and AST depth 128.
The default interpreter budget is 100,000 steps; offline `--steps` accepts up to
1,000,000. Additional cumulative budgets are 100,000 value visits, depth 64 and
8 MiB of text, protecting pure calls that build growing structures. Wire
results retain the normal 1 MiB codec limit. The LLDB helper gives each compiler
invocation five seconds; it never runs a slow expression in the inferior.
The DAP bridge bounds packets to 8 MiB, outstanding requests to 256 and live
references to 100,000 per stop. These are operational limits, not successful
partial evaluations or proofs about arbitrary source execution.

Operation IDs, source-level crash/core analysis, demand-driven large-value reads,
browser NEX source-map watches, additional platforms and an installed editor
extension remain open development work.

```sh
python3 tests/expressions.py build/nex
python3 tests/dap_transport.py build/nex
python3 tests/expressions.py build/nex --live LiveExpressions
```
