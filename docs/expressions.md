# NEX expressions in stopped frames — toolchain 0.14

NEX expressions use the language 0.13 parser, module resolver, type/effect/realm
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
read binding names and structured read paths, language/revision/build/function/stop identity and limits.
Integers in wire values are canonical decimal strings; booleans remain booleans.
Display is bounded to about 4096 bytes and reports `display_truncated`; the wire
value is complete or the operation fails. Display text is not an input value.

`nex-frame EXPRESSION` captures the data demanded while interpreting the expression and
returns `nex.debug-frame/2`. Other visible names retain type metadata and an
explicit unavailable reason. Partial bindings have exact shape/value entries in
the frame's `captures` array. This can be saved for offline inspection. It is
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
checks types/effects/visibility and returns referenced variables and matching
wire schemas; it does not evaluate user code. The LLDB command then invokes
the checked interpreter in demand mode. A missing read returns
`nex.expression-demand/1` with a request containing `binding`, `path`, `kind`,
canonical `type` and `wire_schema`. The provider captures that read, checks the
stop identity and replays the pure expression. Success is `nex.expression/1`.
The source and stop stay fixed across this exchange.

`nex inspect ... --kind demand --json` exposes the same exchange to model tools.
With ordinary value mode, a missing capture is `E_DEBUG_UNAVAILABLE`; it never
silently becomes an empty collection. The original `nex.debug-frame/1` full-value
format is still accepted. Version 2 requires an additional `captures` array;
source language and runtime ABI are unchanged.

The manifest pins the compiler build, semantic revision and exact complete
source bundle. Inspection checks these before loading archived sources; original
source/library files can have changed or been deleted. It does not open or move
project graph HEAD. The frame's declared name/types and build identity must
match the selected function. `llm/debug-frame.schema.json` and
`llm/debug-frame-v2.schema.json` describe the two formats; the compiler also
validates path types, uniqueness, full-binding/capture conflicts and read values.

A saved frame is supplied data. Its IDs/hashes do not authenticate that a value
came from a live process. Live commands obtain fresh values and verify that the
stop did not change while capturing/evaluating; offline inspection reports the
supplied stop identity. A frame from an old compiler build needs its matching
compiler; source language 0.5 and graph identity do not change in this milestone.

## Large aggregate reads

```sh
nex debug examples/debugging/large.nex
```

Stop at the line marked `break: large`, then try:

```text
nex-eval len(samples)
nex-eval report.id
nex-eval last(report.samples)
nex-eval len(unwrap(reply).samples)
nex-eval error_code(failure)
nex-frame last(report.samples)
```

The list contains 32,768 strings and the failure message is 2 MiB. These
expressions read only needed headers and payloads. The last-element helper uses
the checked length and dynamic index; it does not need a special static pattern
in the expression planner. Aliases, pure helper parameters/returns, constructors,
branches, loops and short-circuiting preserve references until data is needed.

Capture paths are arrays: record field names, nonnegative list indices, and
result selectors `ok`, `code` or `message`. A shape read returns exactly one of
`{"length":"32768"}`, `{"record":"debugging::large::Report"}` or `{"ok":true}`.
Lengths are canonical nonnegative decimal i64 strings. Shape checks validate
native kind, nominal name, field order and result layout without reading
sibling payloads. A value read returns the complete typed wire value at its
checked path, or an explicit unavailable reason. No captured value is a shortened
substitute for a whole root. Complete captures, when present, can satisfy later
selection inside that value.

A saved partial frame can evaluate another expression only if its needed reads
were captured. For example, the last-element snapshot retains the list length
and selected string but has no first element. Offline inspection reports the
missing path; it cannot fetch more data after the process has exited. Offline
shapes and payloads remain supplied data, not authenticated evidence.

Whole-value operations such as list concatenation, push/set, JSON encoding and
aggregate equality currently require complete bounded operands. Toolchain0.54 adds
[scalar shapes and bounded string windows](string-debug.md) for length/index/slice;
other whole-string operations still need a complete bounded operand. Direct
expansion of a large uncaptured root through DAP is pending; use a selected
expression to compute a bounded value, then expand its children.

## Exact capture and limits

Scalar reads check LLDB errors. Exact vector reads use checked begin/end pointers and DWARF element sizes instead of interpreting a synthetic provider failure as an empty list. Heap reads validate runtime tags, nominal record
names, field order and result shape against the checked wire schema. Standard
strings are read with their actual length through DWARF fields and process
memory, including embedded NUL and long UTF-8 content. Truncated escaped
summaries are never parsed as values. The implementation uses the
[LLDB frame API](https://lldb.llvm.org/python_api/lldb.SBFrame.html) and
[read-only value access](https://lldb.llvm.org/python_api/lldb.SBValue.html) and
[DWARF type sizes](https://lldb.llvm.org/python_api/lldb.SBType.html).

Capture is bounded to 256 visible entries, 10,000 recursive visits, 10,000 items
per collection, value depth 60 (reserving space for the frame envelope) and 1 MiB of text/frame JSON. The shared strict JSON validator rejects duplicate/escaped-equivalent keys, malformed UTF-8 and packets deeper than 64 before conversion; one leading UTF-8 BOM is accepted. An incomplete binding is
unavailable, never a shortened list or fabricated zero. List/record/result
projections request only needed paths. Each LLDB expression is additionally
bounded to 128 read exchanges and ten seconds overall (five seconds per compiler
invocation). Captured frames accept at most 256 unique reads, paths of at most 56
segments and 10,000 interpreter-only lazy references. Unknown C++ layouts and optimized-out locations also
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

Operation IDs, source-level crash/core analysis, string chunk reads, large-root paging,
browser NEX source-map watches, additional platforms and an installed editor
extension remain open development work.

```sh
python3 tests/expressions.py build/nex
python3 tests/dap_transport.py build/nex
python3 tests/expressions.py build/nex --live LiveExpressions
```

## Language 0.6 enum values

Matching pure helpers accept exact enum values or demand only the selected case shape and fields. A shape is `{"case":"Chosen"}`; a checked payload path component is `Chosen::field`. Ignored or unused pattern bindings do not request payloads. Whole enum captures use the strict case/fields wire wrapper. LLDB validates the stopped ordinal, nominal case name and field layout without inferior calls. DAP computed children expose `<case>` plus selected payload names and preserve paging/stop identity. New manifests use `nex.runtime-view/2` and `nex.debug-expression/2` because the native object layout has an enum ordinal. Old language 0.5 frames require the matching 0.15 SDK and runtime views; migration cannot reinterpret an old stopped process.

Language 0.7 watches can instantiate pure generic helpers that were not emitted into the stopped binary. A generic frame resolves its original type parameter names to the concrete instance arguments. Captured nominal type names include applications such as `model::Box<i64>`. Instances are derived metadata, so creating a watch helper does not change source revision identity. The compiler still validates source/build/stop identity and rejects effectful calls; evaluation never runs code in the inferior. Type-name budgets in the frame schemas are 4096 bytes.

## Callable watches (language 0.10)

Language 0.10 / toolchain 0.23 supports pure calls through captured and
watch-created closures. Source migration is explicit; consult STATUS.md for
the current platform/installed-SDK verification. Retain SDK 0.22 for its
existing frames and receipts.

Types containing callables use `nex.debug-wire/1`, described structurally by
[debug-wire.schema.json](../llm/debug-wire.schema.json). Ordinary wire-only
types retain their existing application wire descriptor. `encode_json`,
`decode_json` and API payloads continue to reject function types recursively.
The debug descriptor has `root`, `records`, `enums` and `targets`. A function
type is `{"function":"fn(bool)->i64"}`. Each target records its exact checked
signature, native symbol, compiled flag and ordered capture types. Entries
marked `compiled:false` may describe computed watch functions; they cannot be
supplied as stopped native values.

A full stopped callable is:

```json
{
  "function": "example::make::$lambda_0",
  "identity": "12345",
  "captures": {"offset": "2"}
}
```

Its partial shape contains exactly `function` and `identity`. Capture paths
then descend through checked capture names, such as `["offset"]` or
`["payload","Pick::number"]`. Closure invocation reads each capture only
when used. Obtaining a whole callable result needs all its bounded captures;
omitted values produce further demands or explicit unavailability. Alias
identity is a nonzero canonical decimal u64 object token; it is scoped to the
recorded stop, not a portable code address. The evaluator rejects inconsistent
targets and observed capture data for the same identity, identity cycles and
targets with different signatures, realms or effects. Data not read by the
expression is not evidence of a complete snapshot.

The LLDB provider validates the actual code pointer against the manifest's
compiled target symbol without calling it. Evaluation executes the checked
source in the helper process. Computed closures receive `computed:N` identities;
these cannot be reintroduced as stopped native inputs. Function equality uses
object identity, including inside aggregates. DAP computed children expose
`<target>` followed by captured values, retaining paging and stop expiry.
Watches inside a concrete generic closure also resolve the enclosing template's
type names. Watch-created closures remain derived and do not write a revision.

Current manifests use `nex.runtime-view/3` and `nex.debug-expression/3`; older
layouts require their original compiler/resources. Capture/text/node/depth
budgets remain bounded; callable alias observation keys and values share an
8 MiB budget. The live fixture includes an unread 32,768-item captured list.
The 128-depth source AST limit includes lambda bodies and their statements.

```sh
python3 tests/function_debug.py build/nex
python3 tests/function_debug.py build/nex --live LiveFunctionDebug
```

Language 0.8 watches enforce builtin generic bounds before pure helper specialization, including helpers absent from the stopped binary. Inside a concrete generic frame, source T resolves to its captured concrete type argument; constraint failures remain E_GENERIC_BOUND. Retain the matching source language/compiler/resources for historical snapshots.

Language 0.9 watches support value matches and pure helpers with nested/guarded patterns. Pattern bindings are local; expression planning reports free frame bindings only. Enum/result/list selectors read required shapes and selected fields, while discarded payloads remain unread.

Language 0.13 binary watches use canonical base64 whole values, length shapes
and selected i64 octets in 0..255. `len(data)` and `data[index]` can read bounded
headers/one octet without siblings. A partial byte slice selects at most 255
octets and shares the frame capture budget; a bounded whole capture supports
larger slices. Full equality/formatting/codecs need complete values. Byte ranges
retain immutable owners, and aliased callable capture observations must agree.
Keep SDK 0.30/0.32 for their original language-0.12 frames; migrate source
explicitly and regenerate a matching debug build.

`tests/bytes_debug.py` checks canonical wire values, bounds, selected-octet
budgets, aliased captures and source-deleted replay. Its optional `--live
LiveBinaryDebug` check uses real LLDB/DAP: a four-MiB buffer remains stopped while
only its length/selected octets are read; whole capture explicitly exceeds its
budget. Byte children are read-only paged NEX integers.
