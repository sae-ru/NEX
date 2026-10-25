# Real installed SDK0.133.5 stream migration histories

The five `language-0.23-sdk1335-stream-*.json` files and their matching `.sql`
files were produced by the actual installed macOS ARM64 SDK0.133.5:

```
compiler SHA256: 65e45e386272025627da730c1bb49c3c05a80345a0b9aa19c50b790087808b21
source language: 0.23
```

Histories: generic-modules, aggregate-aliases, callable-unicode,
whole-file-tasks and locked-library. Each contains three genuine revisions
and all16 original graph tables. The fixture records the exact SQL SHA256,
source bundle and expected old result for every revision. SQL language tags
and semantic identities have not been rewritten.

The private migration suite restores each archive and checks every retained
revision independently. See `docs/task-stream-histories.md` for the scope;
ordinary compiler defaults remain023 and these archives do not publish024.
