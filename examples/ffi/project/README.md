# Foreign module through an actual NEX shared provider

This candidate0.84 example uses the nominal bytes/Reply contract from the parent
[FFI example](../README.md). Follow its instructions to build/review the module,
its `manifest.json`, operator `host.json` and complete notice provenance first.
Native modules are trusted code. The project package does not initialize them.

Create `core/` and materialize the parent `source.nex.in` as `core/main.nex` in this directory,
replacing `@MANIFEST_SHA256@` with the exact SHA-256 of that module manifest.
Copy `app/main.nex.in` to `app/main.nex` as well.
Commit this NEX source and both project JSON files in your application's Git
repository. Keep private host settings, credentials, database files and `.nex/`
outside versioned source. Preserve reviewed native bundles/notices separately.

```sh
nex project --foreign /operator/host.json --json
nex project --kind package --foreign /operator/host.json \
  --notices /operator/notices.json --directory /new/deployment --json
/new/deployment/apps/app/bin/app
```

The first command checks the project and grants without tools or module
initialization. Packaging derives matching pins in memory, compiles `core` once
as a shared library, and links the actual provider into `app` with one runtime.
Original sources and the graph stay unchanged. The package's own host catalogue
grants only `example/contract` and is resolved relative to its executable.
Inspect `project.json.foreign_projection` for source/derived identities and
`apps/app/application.json` for the exact native deployment inventory.

Assembly and actual destination execution have separate evidence. Matching
macOS/Linux host packaging is implemented; Windows DLL deployment and packaged
debug/core provenance remain pending. Installed SDK acceptance materializes and
executes this nominal contract through direct packaging and captured task replay.
