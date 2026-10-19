# Unicode scalar windows in stopped strings

Toolchain 0.54 keeps language 0.15, runtime-view/expression protocol3, graph
schema4 and source canonical forms. Query `string_debug_features`,
`string_debug_limits` and `string_debug_capture_kind`; retrieve this guide with
`nex guide --kind string-debug --json`. The language pack indexes
`llm/text-range.schema.json` and the extended `llm/debug-frame-v2.schema.json`.
Current validation scope is recorded in `STATUS.md`.

## Inspect large text without a shortened whole value

```text
nex-eval len(text)
nex-eval text[len(text)-1]
nex-eval slice(text,len(text)-4,4)
nex-frame slice(text,len(text)-4,4)
```

These operations can use demand-driven references for stopped strings, including
strings in records/results and callable captures. A string shape is exactly
`{"length":"2097152"}`. The length counts Unicode scalars, as ordinary NEX
strings do. It is not a UTF-8 byte length, grapheme count or escaped display size.
Existing complete string values, whole-value frames and ordinary source/runtime
behavior retain their meaning. No source-language feature or native ABI changes.

A `text_range` request/capture keeps the normal binding and checked aggregate
path and adds canonical nonnegative decimal i64 `start` and `count` strings.
The selector starts/counts Unicode scalars within that exact stopped string:

```json
{
  "binding": "text",
  "path": [],
  "kind": "text_range",
  "start": "2097148",
  "count": "4",
  "value": "A🌍\u0000λ"
}
```

A compiler request instead includes `type: "str"` and its checked `wire_schema`.
The provider supplies exact UTF-8 text or an explicit `unavailable` reason. A
range is at most4096 scalars /16384 UTF-8 bytes. Start+count must fit i64. The
compiler checks metadata, paths, exact scalar count and the captured string
shape; negative/out-of-bounds source operations retain `E_BOUNDS`. Empty slices
still check bounds but require no payload. Short-circuiting and pure helpers
preserve lazy references and do not introduce sibling/whole-value reads.

A retained window supplies contained selections and overlapping captured windows
can supply a wider selection. No missing portion becomes empty text. Source
read paths identify actual captured windows used by the evaluator. Conflicting
observed overlaps are rejected, including different views of the same callable
capture identity and selected ranges versus a complete captured string. Root
binding/path observations also stay consistent. This does not authenticate a
frame or prove that unrelated unused fields match a live process.

## Read-only native streaming

The LLDB provider reads actual std::string size/data fields through the existing
checked libc++/libstdc++ layouts, preserving NUL and validating strict UTF-8. It
never calls an inferior function, uses a displayed summary as a value, resumes
threads or writes target memory. The NEX DAP bridge uses the same provider.

To establish scalar length, it streams at most65536 bytes per read with an
incremental UTF-8 decoder and stores byte/scalar checkpoints. It retains neither
a complete large decoded string nor one offset per character. Selected windows
start near the appropriate checkpoint and are decoded again. A per-expression,
per-stop cache shares scans across demanded reads. It does not survive a new
capture/expression or process stop. Physical memory reads have a separate32MiB
cumulative budget, including any rereads, in addition to the existing1MiB
captured text/frame budget. The ten-second expression deadline is checked between
streaming reads; it is cooperative, not an OS-level interruption guarantee.

Malformed/truncated UTF-8, unreadable bytes, unsupported layouts, exhausted
budgets and changing stop identities produce explicit unavailability/failure.
A string near the physical scan limit may leave insufficient budget to reread a
selected window. Other debugger limits (128 exchanges, 256 captures, path/depth,
value/step/output limits) continue to apply. Observed selected string scalars
are additionally limited to100000 across binding/callable alias observations.
A full string still needs a complete bounded capture for equality, formatting,
JSON/codecs and other whole-value operations; windows do not fabricate that root.

## Save and replay exact partial input

Save `nex-frame` output and inspect it with its matching compiler/manifest:

```sh
nex inspect text-frame.json --manifest /path/to/debug.json \
  --expression 'text[len(text)-1]' --json
```

A snapshot containing the scalar shape and the last four characters can answer
that last-character expression after the process and physical source files are
gone. A selection outside captured windows asks for another range in demand mode,
or reports `E_DEBUG_UNAVAILABLE` offline. Existing full/shape/value captures stay
accepted; new text selectors are additive to the matching build's frame2
contract. Old frames and debug manifests still require their matching compiler,
frozen formatter/runtime views and source identity. The source language is not
silently relabeled and historical native layouts are not reinterpreted.

Frame/stop IDs and alias identities are supplied data, not authenticated live
provenance. Live commands verify the stop around reads and evaluation. Native
memory capture is not a general atomic snapshot against arbitrary external
writers. Direct paging of an uncaptured large root in DAP, editor installation,
further platform/layout checks and broader optimized-PC/core work remain in the
full development plan.
