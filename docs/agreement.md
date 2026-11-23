---
status: current
applies_to: "toolchain 0.281.0; language 0.28, 0.29, 0.30"
owner: repository
---

# Three-backend agreement corpus

`tools/agreement.py` runs one checked corpus against the reference interpreter,
native Debug/Release and TypeScript. It complements, and does not replace, the
individual feature tests, `nex test`, the full CTest suite or installed-SDK
acceptance.

```sh
python3 tools/agreement.py --compiler build/nex --output build/agreement
python3 tools/agreement.py --compiler build/nex --language-version 0.30 --require-complete --output build/agreement-030
python3 tools/agreement.py --compiler build/nex --output build/agreement --case arith
python3 tools/agreement.py --compiler build/nex --output build/agreement --no-typescript
```

The checked-in manifest is [`tests/agreement/cases.json`](../tests/agreement/cases.json)
with schema `nex.agreement/1`. It contains valid programs with exact expected
stdout, rejected programs with an expected check code, and trap programs with an
expected runtime code. Valid cases compare reference/native/TypeScript stdout;
trap cases compare the code from each backend. TypeScript is emitted, executed
with the pinned Node and typechecked with the pinned `NEX_TSC`.

The runner reads program output as UTF-8 in every terminal locale. The Unicode
case checks a supplementary character, embedded NUL, carriage return, CRLF and
a final empty line across the interpreter, both native profiles and Node.
For invalid UTF-8 it records the byte offset, stream checksum and actual process
exit code. A timeout or decoding failure fails the observation even when the
process already printed the expected language error.

By default a portable case uses the manifest's project language (0.28 in the
checked-in corpus). `--language-version 0.30` selects 0.30 for the same portable
cases and runs the additional 0.30 cell-alias case. A case with its own
`language` keeps that declaration, including when testing historical behavior.
The optional `additional_cases` map groups cases by selected project language.

Set `NEX_NODE` to the Node executable and `NEX_TSC` to the pinned TypeScript
compiler for a full run. With `--no-typescript` or a nonempty
`NEX_SKIP_TYPESCRIPT`, the report records a reduced run. Each report includes
`requested_language`, effective `project_languages`, each case's `language`,
compiler SHA256/build identity, manifest SHA256, commands, exits and outputs.
The historical top-level `language` field identifies the compiler fallback.
`coverage` counts passing checker, reference and native profiles as well as
TypeScript executions and successful strict checks. `typescript_executed` is true
when every eligible case ran in Node and at least one was eligible. Check
`complete` for coverage of every case, including native Debug and Release,
reference execution and strict, executed TypeScript. The `backend_agreement_030`
CTest group uses `--require-complete` and fails if any of this coverage is missing.

## Deterministic generator

```sh
python3 tools/agreement_generate.py --seed 7 --count 3 --directory build/agreement-generated
python3 tools/agreement.py --compiler build/nex --root build/agreement-generated \
  --output build/agreement-generated-run --no-typescript
```

The generator writes a `nex.agreement/1` manifest with seed, count, per-program
SHA256 and a copyable reproducer command. The same seed produces byte-identical
programs; a different seed produces a different corpus. Generated programs use
only small total i64 arithmetic, so Python-computed expected stdout is an
independent oracle for those cases. The generator is checked with a real
three-run reproducibility test and an actual agreement execution.

## Scope and limits

The corpus is a bounded semantic smoke matrix, not proof of language
equivalence. It does not cover tasks, effects, realms, files, FFI, JSON edge
cases, performance or every rejected program. Those retain their dedicated
tests. External URLs and network access are not used. Running the same corpus on
another platform or SDK is a separate acceptance claim.

[Recorded 0.174 validation](evidence/agreement-0.174.0-2026-11-11.json) pins the
compiler, corpus, generator, test scope, retained corrections and limits.
