# NEX safety checkpoint

This branch preserves all 480 current source, test, example and documentation files for toolchain 0.45.0 / language 0.15. It is a development backup, not a finished release.

The macOS full regression run passed all 52 groups. The installed macOS SDK passed all 13 phases. Logs and bounded verification reports are retained here. Linux verification is captured exactly as observed; a running phase does not mean failure or completion.

`native-sites-0.46.patch` separately preserves all three files changed in an isolated, unfinished next step. It has not been compiled or tested. To reconstruct that work in a separate checkout at this branch, run:

```sh
git apply checkpoints/20261018-183254/native-sites-0.46.patch
```

`manifest.json` records every base source SHA-256/Git blob, changed-file hashes, and validation scope. Build caches, generated binaries and dependencies are omitted. Earlier checkpoints remain in Git history and backup branches.
