---
status: current
applies_to: "toolchain 0.176; language 0.28"
owner: repository
---

# Compiler-checked diagnostic fixes

A diagnostic can carry a machine-readable `nex.fix/1` edit: a byte interval in
the reported source file and its replacement text. Fixes are attached only when
the compiler has a unique, bounded suggestion; they are not guessed by the CLI.
The diagnostic JSON gains a `fixes` array when one is available.

```sh
nex fix src/main.nex --json            # preview, no write
nex fix src/main.nex --apply --json    # apply one unique fix and recheck
```

Currently `E_NAME` (an unknown visible identifier) and `E_FIELD` (an unknown
nominal field) produce a fix when exactly one visible candidate is closest. The
range is the exact source interval; the replacement is an identifier already
known to the checker. Preview never writes. `--apply` writes only when the source
currently has one diagnostic with one fix, then rechecks the entire file. If the
edit still fails, the original bytes are restored and `E_FIX_REJECTED` is
reported. `E_FIX_UNAVAILABLE`, `E_FIX_AMBIGUOUS`, `E_FIX_FILE` and `E_FIX_RANGE`
cover the other refusal paths.

The command edits physical source only and does not accept `--revision`; graph
history is synchronized by the ordinary later `nex check`. It does not apply
batches, effect/type/arity rewrites or editor LSP edits. Those remain pending.
The JSON report records the original diagnostic, fix interval, replacement,
safety label, source hashes and the checked revision after a successful apply.
