# Language023 writer library

From this directory, with a matching development compiler on PATH:

```sh
mkdir -p /private/tmp/nex-output
nex check
NEX_FILES_ROOT=/private/tmp/nex-output NEX_FILES_WRITE=1 nex project --kind run --component app
```

The library is a real code-only static archive. The application owns one runtime
and explicit root grant. For fixed shared linking set leaf kind to
`shared_library` and its dependency edge to `dynamic`. Packaging uses
`nex project --kind package --component app --directory NEW_DIRECTORY`.
Keep NEX sources, manifests and dependency locks in Git. Runtime output and
operator grants are separate from source and do not belong in the language graph.
