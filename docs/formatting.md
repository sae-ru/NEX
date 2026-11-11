---
status: current
applies_to: "toolchain 0.168; language 0.28"
owner: repository
---

# Formatting NEX source

`nex fmt` formats one explicitly selected UTF-8 source file or a directory tree. It uses the actual
current-language parser and preserves ordered line comments and the spelling of
every literal. `--width N` (20..1000) conservatively wraps formatter output
lines longer than N at commas, but never rewrites lines containing comments,
string/character literals or an empty split. It is not a general reflow and
leaves overlong quoted lines intact. It does not load imports, type-check, execute code or open a graph
Store. A missing imported file or an unresolved name does not prevent formatting.
Run ordinary `nex check` and the affected tests to validate program behavior.

```sh
nex fmt src/main.nex                 # preview source on stdout
nex fmt src/main.nex --check         # no writes; exit 1 if formatting differs
nex fmt src/main.nex --write         # replace this source file
nex fmt src/main.nex --check --json  # machine-readable nex.format/1 result

nex fmt src --check --json           # recursive directory check; nex.format-directory/1
nex fmt src --write --json           # format every .nex file under src

nex fmt src/main.nex --width 80      # conservative wrap of long unquoted lines
nex guide --kind format --json
```

Preview always exits 0 for valid input, including when the source would change.
Check exits 0 when already formatted and 1 when a change is needed. Invalid input
or options exit 1 with the usual diagnostic; JSON diagnostics have a `code`, while
a formatting difference is a `nex.format/1` result with `ok: false`. Check and
write cannot be combined. A no-op write preserves the file's modification time.
Plain write is silent; plain check reports a difference on stderr. JSON preview
includes the formatted `source`; check/write omit that potentially large field.
Results include original/formatted BLAKE3 hashes and compiler version/build.

## Fixed style `nex/1`

Indentation is two spaces per block or multiline argument/list/type group. Blocks
and semicolon-terminated statements receive structural newlines. Expression
match arms receive newlines after commas at their brace level. Type arguments,
member access, indexing and unary operators are compact; binary operators are
spaced. Effect braces stay inline unless a comment requires a line break.

The parser distinguishes type angles from comparisons. Its accepted compact
`list<i64>=value` declaration becomes `list<i64> = value`; an actual `>=`
comparison retains that operator. There is no separate formatting grammar.

Intentional multiline argument/list/type layouts and at most one separating
blank line at statement/comment boundaries are retained. Output uses LF and one
final newline. Comment text, including Unicode and trailing spaces, is retained;
CR in a CRLF comment terminator becomes LF. String/number spelling and escape
sequences are copied exactly. Comments containing `//`, quotes or delimiter text
are never interpreted as program tokens. String text containing `//` remains a
string. A leading UTF-8 BOM is rejected by the current source grammar.

The formatter reparses its result and compares every normalized token spelling,
parser role and ordered comment against the original. Only the parser's existing
type-closing `>=` split is normalized. It also verifies that formatting its result
again produces identical bytes. An invariant failure reports `E_INTERNAL` and
does not write the source.

## Source files and graph history

Formatting does not synchronize a project, change a manifest/lock, migrate a
language or edit stored graph rows/revisions/local IDs. The normal subsequent
check can archive the new physical source with the same semantic revision.
Existing debug/source captures retain their original byte coordinates; create a
new capture after changing physical source layout.

Write uses a sibling temporary file, preserves ordinary file permission bits,
rechecks the original bytes and renames the complete result over the source.
It rejects a symlink rather than replacing its target. An observed concurrent
edit reports `E_CONFLICT`. This is not an editor locking protocol: avoid concurrent
writes to the same file. Native filesystem replacement behavior still applies.

Input and formatted output are limited to 4 MiB; the existing lexer/parser limits remain in force.
This command selects current language 0.28 syntax, independently of manifests;
it does not reinterpret or upgrade an older project. Directory recursion,
configurable style, width-based wrapping, editor format requests and C++
formatting are not provided by this command. Those are separate tooling work.

Functional coverage is in `tests/source_formatting.py`, including exact layout,
comments/literal bytes, nested generics and comparisons, current source examples,
rejected input without writes, retained graph rows, semantic revision, reference
execution, native Debug/Release and strict executed TypeScript. A test definition
alone is not a current platform or SDK acceptance receipt.

The [recorded 0.168 source observation](evidence/source-formatting-0.168.0-2026-11-11.json)
passed all seven methods (15.104 s), 12 core groups (29.03 s) and the shared
language-pack comparison. It preserves the initial test-protocol error separately.
These local observations do not qualify a complete SDK or another platform.
