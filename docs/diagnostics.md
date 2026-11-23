# Bounded diagnostic explanations

Toolchain0.166 adds a compiled read-only catalogue:

```sh
nex explain E_PARSE
nex explain E_EFFECT --json
nex explain --kind index --json
```

`explain` works without a project, source files, installed resource tree or
Python. It opens no graph and executes no source or shell command. It accepts
one builtin code, or the explicit index mode, and rejects unrelated flags.
Codes have the form `E_[A-Z0-9_]+`, at most128 ASCII bytes. An unknown code fails
with `E_OPTION`; the catalogue does not invent an explanation for a provider's
arbitrary user-defined code.

The initial reviewed catalogue has103 entries across syntax/types/generics,
effects/realms, runtime/control, resource limits, debug, API, FFI and GPU paths.
It is not a complete diagnostic registry. Query the selected compiler's index
for exact coverage rather than inferring that an unlisted code cannot occur.

Each result gives the code's meaning, a concrete next action and a relevant
guide command. JSON also binds language/toolchain/compiler_build,
descriptor_hash and catalogue_hash. The latter is a BLAKE3/256 hash of ordered
reviewed text/example data. Index/detail output is capped at8192 UTF-8 bytes;
the compiled capability `diagnostic_catalogue` advertises those bounds.

Nine illustrative invalid/corrected program pairs cover common checker errors.
For example, `E_PARSE` shows `n=n+2` with a mutable local in place of unsupported
`+=`. `E_EFFECT` distinguishes ordinary IO declarations from task source-error
delivery requiring `throw` or a lexical try. Examples are not fix-its for the
caller's source. `context_specific` is false: the command gives general advice
for a code. It does not read a project or establish which edit
would preserve its behavior; `automatic_fix` and `applies_to_user_source` are false.
Inspect the original message/span and validate the reviewed edit normally.

The output schemas are
[`nex.diagnostic-explanation/1`](../llm/diagnostic-explanation.schema.json) and
[`nex.diagnostic-catalogue-index/1`](../llm/diagnostic-catalogue-index.schema.json).
Runtime traps, source exceptions and result values retain their existing
semantics. In particular, adding an explanation does not make overflow,
unwrap/assert failures, cancellation or deadlines catchable by source handlers.

## Compact language entry

```sh
nex describe --field llm_entry --json
nex guide --kind quick --json
```

The [quick reference](../llm/QUICK_REFERENCE.md) stays within6144 UTF-8 bytes.
It explains actual declaration/assignment syntax, immutable collection updates,
Unicode scalar slices, generics/imports, results, typed errors, effects and task
boundaries. Its selected resource must be bounded regular UTF-8 text; an absent,
oversized or malformed override fails. It does not change language0.28 or
provide an implicit graph migration.

The [multi-module example](../examples/llm-quick/nex.json) combines those source
rules. Its tests compare reference, native Debug/Release and strict checked /
executed TypeScript, including a joined yielding child. The catalogue's example
pairs have independent actual checker acceptance/rejection controls.

Matching0.166 SDK acceptance also executes the quick guide and copied multi-module
project in its new-project phase, compares reference/native Debug/Release, and
executes TypeScript when browser acceptance is requested. Its resource hashes and
compiler identities are checked by the final receipt validator. Focused source
controls exercise that same sub-workflow; they do not qualify a complete SDK.

These tools improve access to information. They do not prove lower token cost
or greater model success. The [original local Qwen result](llm-cost-qwen38-27b-2026-11-11.en.md)
remains negative and unchanged. New model observations need their own versioned
protocol; no earlier failed candidate is repaired or relabelled by this command.

[Recorded0.166 scope and checks](evidence/bounded-language-entry-0.166.0-2026-11-11.json) bind compiler/source identities and retain the initial failures.

## Repair an assertion from a test run

When the reference execution in `nex test --json` reports `E_ASSERT`,
`test_failure.symbol` names the selected test, including when a helper inside
that test failed. The outer file, line and column identify the failing assertion.
Run the arguments in `test_failure.rerun_argv` from the same project directory,
using the same SDK. The array preserves the entry, target and supported test
options, selects that test, and resolves an explicit archived HEAD to its revision.
It is omitted if any argument cannot be represented in UTF-8.

For model-assisted repair, run `nex test ENTRY --repair-context --json`.
On an assertion failure, `repair_context` includes a source excerpt for
the first public function in the failing test's bounded list of direct
callees. If the list has no public function, the excerpt shows the test.
It includes up to 2,048 UTF-8 bytes of source, 12 callee signatures and
three argument arrays for inspecting callees. For an archived run, execute
those arrays from the selected project root. They pin the tested revision.
The whole excerpt must fit in 16 KiB. It can include string literals and
comments from the selected function. A passing test keeps its usual output.
Use `nex help test --json` to check whether an installed SDK has this option.

For an archive that supports function briefs and lacks the flag, use the
standalone SDK driver. From the project root, run
`python3 repair_context.py --nex /path/to/nex entry.nex`. The driver checks
the entry once, pins its revision and runs the test and context queries on
that revision. On Windows, use `py -3` and the path to `nex.exe`.
[Standalone SDK driver](../tools/llm/repair_context.py)

On three NEX 0.30 defects, Codex accepted six repairs in each condition.
Total input plus output fell from 396,127 to 344,777 tokens (13.0%),
including tokens read from the cache. Mean time to acceptance was 24.12 s
with the ordinary diagnostic and 24.16 s with the excerpt.
[Trial counts, cache reads and original time criterion](evidence/test-repair-context-cost-2026-11-23.json)

When a source predicate range survives interpretation, `condition` gives its
byte interval in the reported file and a preview of at most 256 UTF-8 bytes.
String literal contents and line comments are hidden. A direct comparison of
two i64 or bool values also reports its operator and the left/right operands
already evaluated at the failure. Integers use decimal strings so a JavaScript
reader retains all 64 bits. Booleans use JSON booleans. Compound conditions,
other value types and task boundaries that preserve only the trap may omit
details. The program's existing stdout remains available separately.
