# Atomic type and caller replacement

Requires a language0.20 compiler advertising `type` in `patch_entities`.
From this directory:

```sh
nex describe --json
nex check --json
nex context --entity type --symbol type_patch::model::Parcel --json
nex apply --patch patch.json --json
nex test --revision HEAD --json
nex test --revision HEAD --target web --json
nex run --revision HEAD --json
nex export --revision HEAD --directory /tmp/nex-type-patch-export
```

Before the patch the program prints `42`. Afterwards it prints `43` and
`готово` on separate lines. The patch extends the generic source type with a
label and repairs its factory, application entry and test in one transaction.
The source-template and `Parcel<i64>` IDs persist; an archived revision retains
the original layout/output. Editing only the type fails because the original
constructor has too few fields.

The patch changes archived HEAD and leaves these source files unchanged. Use
`--revision HEAD` until exporting. A subsequent bare `check` checks the old
physical files and selects their revision again. The example's expected digest
is pinned to the checked language0.20 baseline; changed source requires a fresh
reviewed patch and expected HEAD.
