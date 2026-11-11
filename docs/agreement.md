---
status: current
applies_to: "toolchain 0.174; language 0.28"
owner: repository
---

# Three-backend agreement corpus

`tools/agreement.py` runs one checked corpus against the reference interpreter,
native Debug/Release and TypeScript. It complements, and does not replace, the
individual feature tests, `nex test`, the full CTest suite or installed-SDK
acceptance.

```sh
python3 tools/agreement.py --compiler build/nex --output build/agreement
python3 tools/agreement.py --compiler build/nex --output build/agreement --case arith
python3 tools/agreement.py --compiler build/nex --output build/agreement --no-typescript
```

The checked-in manifest is [`tests/agreement/cases.json`](../tests/agreement/cases.json)
with schema `nex.agreement/1`. It contains valid programs with exact expected
stdout, rejected programs with an expected check code, and trap programs with an
expected runtime code. Valid cases compare reference/native/TypeScript stdout;
trap cases compare the code from each backend. TypeScript is emitted, executed
with the pinned Node and typechecked with the pinned `NEX_TSC`.

`NEX_TSC` is required unless `--no-typescript` is used; a reduced run is recorded
as `typescript_executed: false` and is not full agreement. Every run writes
`report.json` with the compiler SHA256/build identity, manifest SHA256, per-case
commands, exit codes, stdout/stderr and failures. Failures are retained; the
runner exits nonzero.

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
