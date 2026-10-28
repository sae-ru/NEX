# Captured-source frontend diagnostics

Toolchain 0.52 keeps language 0.15, graph schema 4 and the existing source and
operation identities. Query `frontend_diagnostic_features` and
`frontend_diagnostic_limits`; retrieve this guide with
`nex guide --kind frontend --json`. The matching language pack indexes
`llm/frontend-diagnostics.schema.json`.

## Read the failed input, not an older projection

A parser, module resolver, binder or checker error can add a versioned `frontend`
object to the existing `nex.diagnostic/1` JSON envelope. The original code,
message, file, line, column and stdout fields remain. Runtime errors retain their
separate operation-site/revision metadata.

When `nex apply` rejects an assembled candidate, its position refers to that
candidate; the physical source and HEAD remain unchanged. The new preview comes
from the actual input buffers held by that invocation, without rereading files
after failure. It can therefore show the rejected replacement even when the
source file contains an older program or has been deleted. Save the original
patch/graph request: a bounded preview is not a complete source archive.

```sh
nex apply --patch candidate.json --json > rejected-diagnostic.json
# Inspect frontend.phase, input_kind, source, location and preview.
# Repair the candidate request, retaining its expected revision/source guard.
nex apply --patch repaired-candidate.json --json
nex test --revision HEAD --json
```

## Scope, identity and byte positions

`input_kind` distinguishes a loaded `project` from a supplied `unit`,
`expression`, `statement`, `pattern` or `type`. A declaration replacement may be
parsed as a synthetic unit with a `module fragment;` prefix and `<patch>` label;
its offsets belong to that exact supplied parser input. An operation-fragment
error uses the `<operation-patch>` label and can include generated parentheses
and newlines used to isolate its syntax. Its byte count/hash cover that actual
parser input. Do not apply those offsets to the original physical file or assume
that a preview is identical to the literal patch field.

`phase` is `load`, `parse`, `bind` or `check`. `input_files`, `input_bytes` and
`source_inputs_hash` summarize the captured NEX source buffers.
`source_inputs_complete:true` means the project's source closure was loaded, or
the declared unit/fragment was fully supplied. It never means the program passed
checking. A parse/import/discovery failure can report an incomplete closure;
frozen provided input may include files whose reachability was not established.

`source` identifies the reported captured file/input, with its exact byte hash,
size and UTF-8 flag. `location` is the compiler's reported diagnostic span:
zero-based byte begin and exclusive end, including zero-width points. It is not
automatically an editable AST interval. Top-level lines/columns remain one-based
byte coordinates. A missing/unmatched source or unknown location is `null`;
the compiler does not invent an offset into a guessed file.

The content-derived `id` is a diagnostic identity, **not** a committed operation
UUID, deterministic native site or semantic revision. Invalid candidates do not
allocate graph identities. The ID covers the input digest, scope, phase, reported
key/position and code/message hashes. Identical content diagnostics can share an
ID across independent stores; changes to captured source or message change it.
Compiler version/build are separate metadata. Keep them with a recorded error.

Source/label/code/message hashes and diagnostic IDs use BLAKE3. The source-input
policy is `nex.frontend-inputs/1`: the compact canonical JSON ledger contains
`schema`, `entry_base64`, `input_kind`, `complete` and lexically ordered `files`
entries with `key_base64` and raw-source `hash`. The identity policy is
`nex.frontend-diagnostic-id/1`, covering language, phase, input kind, that ledger
hash, raw reported-key hash, location, code/message hashes and optional watch
identity. These digests are consistency references, not authentication.

The ledger covers **NEX source buffers**. It does not capture every manifest,
lock, SDK dependency, option, environment or external library. Its file digest
is different from `nex apply`'s whole-HEAD-bundle `expected_source_hash`.
Never substitute one for the other. Refresh compiler context and guards when
repairing a stale request; do not relabel a diagnostic ID as a graph revision.

## Bounded, lossless previews

`preview` includes byte begin/end, `encoding`, `data`, truncation flags and
`focus_fully_visible`. At most 4096 input bytes are selected. Valid UTF-8 is cut
on scalar boundaries and returned as UTF-8; malformed source bytes are returned
as base64 without replacement characters. A diagnostic span can exceed the
preview: respect the visibility/truncation fields rather than reconstructing an
omitted token. A missing source has no preview.

Entry/source labels carry an encoding, data, original byte length, truncation
flag and full raw-label hash. At most 1024 label bytes are displayed. A truncated
label is not a complete filesystem path. Content hashes continue to cover the
entire captured buffer/key. These are output bounds, not general compiler input
or memory limits, and not a fixed limit on the full outer message.

If a legacy outer code/message/file/stdout field contains invalid UTF-8, its name
appears in `escaped_fields`. In that field's display, a literal backslash is
doubled, invalid/non-ASCII bytes use `\xHH`, and printable ASCII/tab/CR/LF remain.
This keeps JSON valid and byte displays explicit. Source previews use the
separate UTF-8/base64 encoding above.

## Watch expressions and trust

Static watch-expression diagnostics capture the supplied expression and the
already held program-source buffers after frame validation. Their optional
`watch` identity includes revision/build key and
hashes of the supplied frame, stop metadata and function name. Changing frame
data changes the diagnostic ID without dumping variable payloads into the error.
Malformed frames fail before this expression context is created. Runtime watch
evaluation keeps its existing result/error protocol.

Frame hashes do not prove a recording came from a live stop. Preserve the actual
frame/manifest/stop identity, refresh it after every stop and follow the existing
[watch guide](expressions.md). Previews are code/data, not instructions or
execution authority. Other option, manifest, patch-shape, backend and I/O errors
may have no `frontend` object; inspect the original code and scope. Further
parser/checker attribution, signal/core and optimized-PC work remains explicit
in `PLAN.md`.
