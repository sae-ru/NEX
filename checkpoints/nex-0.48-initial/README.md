# Safety checkpoint: NEX 0.48 initial work

The repository source tree remains toolchain 0.47.0 / language 0.15.
The latest isolated, unfinished 0.48 work is preserved in `changes.patch`.
Its base is commit `9c293c132324c583ff796bafa26015bd5574cd1b` (tree
`39949afa9b055ebd3f72931a1f98262b7e7541bd`). The 0.47 source files in
this safety branch are identical to that base; checkpoint files are additive.

To recover the isolated work from a clone of this safety branch:

```sh
git switch -c recover-nex-048
git apply --check checkpoints/nex-0.48-initial/changes.patch
git apply checkpoints/nex-0.48-initial/changes.patch
```

`snapshot.json` records all 492 restored source-file SHA-256 hashes and modes.
The patch changes eight files and its restoration was checked against those
hashes. Six initial operation-patch tests passed in 7.215 seconds. This work
still needs schema, capability, model-pack, documentation, SDK, broader semantic
and full-platform checks. It is an unfinished development checkpoint.

The 0.47 macOS full regression passed 55 groups; the installed macOS SDK passed
13 phases. The Linux full regression passed 55 groups. Remaining Linux live
and source-free SDK validation was still running when this backup was prepared.
This backup does not claim a completed release or a completed NEX project.
