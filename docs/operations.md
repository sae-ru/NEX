# Operation graph and source attribution — toolchain 0.15

Language 0.5, `nex.function/3`, `nex.program/4` and semantic revision hashes stay unchanged. The checked AST now also supplies parameter, block, statement and expression nodes, structural child edges, lexical binding references and call references. This analysis does not add source syntax or execute model output.

## Query the selected revision

```sh
nex check examples/operations/main.nex --json
nex operations --symbol operations::adjust --limit 100 --json
nex operations --symbol operations::adjust --offset 100 --limit 100 --json
nex context --operation ID --json
nex context --site SITE_KEY --revision REVISION --json
```

Queries default to saved HEAD. An explicit revision selects its archived sources without moving HEAD. Use the project's directory or `nex.json` when selecting a store. `nex.graph/2` exports an additive `operation_graph` object; existing function and endpoint fields remain compatible. Both response formats are described by `llm/operations.schema.json`.

Expressions and parameter/binding types are resolved. Statement slots without a declared binding type use the checked AST marker `unknown`; operands and the owner signature supply value types.

An operation has a local-store `id`, deterministic `site`, owner function/ID, structural `path`/`parent`/`role`/`ordinal`, readable `kind`, Merkle content `hash`, local typed `definition`, source `location`, children and references. A name expression points to its actual parameter/declaration, including outer bindings during a shadowing initializer. Assignments reference their mutable declaration. Calls reference the qualified callee's function ID. Children also carry parent IDs, so the full exported node set recovers structural edges even when an individual child preview is clipped.

Pages contain 100 nodes by default and accept 1..1000 via `--limit`. `total`, `offset` and `truncated` describe the page. Each node previews at most 100 children, with its exact `child_count` and `children_truncated`. Context for one ID/site also contains its ancestor chain. Definitions exceeding 8192 encoded bytes are explicitly omitted in paged queries (`definition: null`, `definition_omitted`, `definition_bytes`); their hash remains available. The complete graph/source export retains that content. The node count is bounded; this is not a fixed token budget for arbitrary names or types.

## Identity and matching

IDs are 128-bit random values owned by the local SQLite store and separated from content hashes. A deterministic 256-bit site key hashes the function's checked content and structural path. The same function in independent stores has matching sites but different local IDs. Changes to canonical function content change its site keys; surviving logical IDs can remain unchanged. Revision/source/build identity separately distinguishes dependency, layout and formatting changes.

The versioned `nex.operation-identity/1` policy is conservative:

- Parameters match unique names; body/else/expression/argument roles match their structural position and kind under a surviving parent.
- An unchanged block preserves statement positions, including repeated identical statements.
- In a changed block, unique complete statement hashes match first, allowing insertion/reordering. Remaining unique kind/name anchors match edited declarations/assignments and unique control/return/call roles.
- Ambiguous duplicates receive fresh IDs. A move to another parent/scope or a changed node kind is a new identity. This policy tracks logical editing roles, not semantic equivalence or user intent.
- An already recorded revision never rematches. Exact function content seen in another recorded revision reuses that function's mapping. Otherwise the selected HEAD's mapping is preferred, then the latest recorded mapping for that function. Old mappings remain queryable, and returning to an old revision recovers its exact IDs.

Records, hashes and IDs commit in the same transaction as checked source/functions/edges. Stale patches and rejected candidates cannot allocate committed operation identities. SQLite schema 2 upgrades transactionally to 3, preserving revisions, sources, language versions and function IDs. Current-language archived sources are backfilled lazily; old language snapshots still require explicit language migration. Once present, operation queries read the index without changing HEAD. Stored hashes/sites are checked against reconstructed source metadata. Changing the content/identity algorithms requires an explicit index/history migration.

Import rechecks source bundles and derives local identities; exported foreign IDs are not trusted or adopted. Preserve `.nex/graph.db` to retain local identity lineage across machines. Git source backups and source export retain reconstructible semantics and sites but do not promise preservation of local-store UUIDs. Cross-store identity reconciliation and operation-level patch commands remain open. Existing revision-checked function patches are still the edit interface.

## Diagnostics and compiled code

Checked interpreter failures from `eval --json` include `operation_site`, persistent `operation_id`, `revision` and `source_hash`. TypeScript trap sites add the same deterministic key as the fourth item of `NexError.site`; the first three items remain file, line and byte column. The TypeScript map includes statement sites and complete operation-site tables only for emitted reachable client/shared functions. Unreachable/server code stays excluded. The runtime's values, ordering, checked arithmetic and cleanup semantics do not change.

Native MLIR attaches `nex.site.KEY` NameLocs around existing scoped source locations. One source node may lower to several instructions. LLVM's debug translation retains source locations and does not promise preservation of NameLoc names in DWARF. The debug manifest pins complete site tables for compiled functions. See the official [MLIR location format](https://mlir.llvm.org/docs/Dialects/Builtin/#nameloc) and [LLVM debug translation](https://mlir.llvm.org/doxygen/DebugTranslation_8cpp_source.html).

At a stopped LLDB frame:

```text
nex-operation
```

This returns `nex.debug-operation/1` with revision/source/build/stop identity and source-column candidates, or source-line candidates when column data is unavailable. It never resumes the process or calls inferior functions. Multiple co-located nodes remain explicit candidates; a line table is not proof of a unique executing source operation. At most 1000 candidates are returned and truncation is explicit. In the NEX DAP REPL, prefix the command with a backtick to delegate it to LLDB. Resolve a returned site with `nex context --site KEY --revision HASH` in the matching store.

Semantic revisions ignore formatting. Locations are byte-based source points, not replacement ranges. Compare `source_hash` before relating coordinates: stored revisions retain their first exact source bundle, while a live build can use differently formatted but semantically identical text. Native build keys/manifests pin the exact source separately. Parser/type failures do not yet have a checked operation identity, native textual runtime traps retain their existing format, and watch-only synthetic expressions have no persistent source identity. Precise optimized-PC attribution, native trap IDs, operation profiling, core analysis and browser source-map debugging remain pending.

Native debug manifests retain the existing 8 MiB loader limit; larger closures still need selective metadata packaging.

A function analysis is limited to 100,000 nodes and 512 structural separators in a path. These are compiler resource limits. Identity reuse is not a correctness proof; validate all behavioral changes with the compiler and native/interpreter/TypeScript tests.
