# Operation graph, source edits and attribution

The checked AST supplies parameter, block, statement and expression nodes, structural child edges, lexical binding references and call references. This analysis does not add source syntax or execute model output.

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

Import rechecks source bundles and derives local identities; exported foreign IDs are not trusted or adopted. Preserve `.nex/graph.db` to retain local identity lineage across machines. Git source backups and source export retain reconstructible semantics and sites but do not promise preservation of local-store UUIDs. Explicit snapshot-scoped cross-store reconciliation is described in [graph.md](graph.md); toolchain 0.48 supports the revision/source-checked operation replacements described below.

## Diagnostics and compiled code

Checked interpreter failures from `eval --json` include `operation_site`, persistent `operation_id`, `revision` and `source_hash`. TypeScript trap sites add the same deterministic key as the fourth item of `NexError.site`; the first three items remain file, line and byte column. The TypeScript map includes statement sites and complete operation-site tables only for emitted reachable client/shared functions. Unreachable/server code stays excluded. The runtime's values, ordering, checked arithmetic and cleanup semantics do not change.

Native MLIR attaches `nex.site.KEY` NameLocs around existing scoped source locations. One source node may lower to several instructions. LLVM's debug translation retains source locations and does not promise preservation of NameLoc names in DWARF. The debug manifest pins complete site tables for compiled functions. See the official [MLIR location format](https://mlir.llvm.org/docs/Dialects/Builtin/#nameloc) and [LLVM debug translation](https://mlir.llvm.org/doxygen/DebugTranslation_8cpp_source.html).

At a stopped LLDB frame:

```text
nex-operation
```

This returns `nex.debug-operation/1` with revision/source/build/stop identity and source-column candidates, or source-line candidates when column data is unavailable. It never resumes the process or calls inferior functions. Multiple co-located nodes remain explicit candidates; a line table is not proof of a unique executing source operation. At most 1000 candidates are returned and truncation is explicit. In the NEX DAP REPL, prefix the command with a backtick to delegate it to LLDB. Resolve a returned site with `nex context --site KEY --revision HASH` in the matching store.

Semantic revisions ignore formatting. Locations are byte-based source points, not replacement ranges. Compare `source_hash` before relating coordinates: stored revisions retain their first exact source bundle, while a live build can use differently formatted but semantically identical text. Native build keys/manifests pin the exact source separately. Parser/type failures do not yet have a checked operation identity, and watch-only synthetic expressions have no persistent source identity. Toolchain 0.46 adds [native runtime trap reports and checked graph mappings](native-diagnostics.md), preserving the legacy human-readable line. Precise optimized-PC attribution, operation profiling, core analysis and browser source-map debugging remain pending.

Native debug manifests retain the existing 8 MiB loader limit; larger closures still need selective metadata packaging.

A function analysis is limited to 100,000 nodes and 512 structural separators in a path. These are compiler resource limits. Identity reuse is not a correctness proof; validate all behavioral changes with the compiler and native/interpreter/TypeScript tests.

Language 0.6 uses function/4 and program/5 hashes and adds statement.match, pattern.case, pattern.binding and pattern.discard nodes. Arm paths use resolved case names; matching anchors by case name rather than numeric discriminator so reordering enum declarations cannot silently retarget an existing case identity. Case definitions retain their current discriminator. Pattern uses link to their arm-local binding; discards introduce no binding. Source sites change with the checked function hash.


## Replace a source operation (toolchain 0.48)

Discover `patch_entities`, `operation_source_kinds`, `patch_limits` and
`parser_limits`. `nex context --operation ID --revision HASH --json` adds
`source_range` to the selected node: either null, or `{kind, byte_begin,
byte_end, editable}`. The half-open interval covers complete syntax in the
archived unit named by `location.file`, measured in UTF-8 bytes. Diagnostic
`location` remains its original source point. Query pages contain ranges;
context also contains `source_preview`, full `source_bytes` and explicit
`source_truncated`. The preview ends at a scalar boundary and is at most 4096
bytes; request owner source when it is incomplete. Older reports omit these
additive fields.

```json
{
  "expected_revision": "REVISION_FROM_CONTEXT",
  "expected_source_hash": "SOURCE_HASH_FROM_THE_SAME_CONTEXT",
  "replacements": [
    { "operation_id": "LOCAL_OPERATION_ID", "source": "value + 2" }
  ]
}
```

The operation ID has 32 lowercase hexadecimal characters, and both hashes have
64. Optional replacement `kind` is `operation`; do not supply a name, site or
coordinates. The selected archived source hash is mandatory because semantic
revisions ignore formatting. `E_SOURCE_CONFLICT` rejects a different exact
bundle; `E_CONFLICT` rejects a changed HEAD. Always fetch and reconcile fresh
context instead of rewriting either guard blindly.

One expression, statement or pattern is parsed with complete input consumption.
Expressions are parenthesized to preserve precedence, and newlines isolate line
comments from neighboring source. Declaration replacements also isolate their
trailing comment. Parameters, captures and synthetic block/arm wrappers do not have replaceable
ranges. Simple enum case nodes directly carry their constructor-pattern interval;
nested/guarded cases expose separate editable pattern children. Concrete generic instances and lifted closure
bodies report `editable:false`; replace source-template operations or the owner
lambda expression. A pattern binding and all affected guard/value references
must change together. Coverage, types, effects and realms are checked again.

Operations and existing declarations can change across modules in one patch.
Overlapping intervals, including an operation inside a replaced declaration,
are rejected before any candidate edits are applied. A whole-candidate check
precedes the final expected-HEAD transaction. Failure preserves every graph
row; success retains historical sources and local identity lineage. Accepted
syntax is not proof of the requested behavior: run reference/native/TypeScript
checks with `--revision HEAD`. Source files change only through explicit export.
See [the executable walkthrough](../examples/operation-patches/README.md).

Patch input must be a regular non-symlink UTF-8 file of at most 4 MiB, JSON
container depth 64 and at most 1000 replacements. Individual operation fragments
have a 100,000-token budget. Statement/expression recursion and each postfix or
binary chain, and the resulting expression tree, have a 256-level/operation parser limit. Limit failures produce
bounded diagnostics; no fragment runs during parsing or checking. Canonical
formats, language 0.15, database schema 3 and identity policy 1 are unchanged.
