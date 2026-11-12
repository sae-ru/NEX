# Persistent graph identities

Toolchain 0.44 introduced independent module/type nodes and checked references
between stores while retaining its then-current language 0.15/database schema 3.
Current language 0.16 additionally indexes source traits and named implementations;
the current main database schema is4. These versioned extensions preserve local
identity history; source-language migration remains explicit. Query `nex describe
--json` for the installed compiler's policy and limits; `nex guide --kind graph
--json` returns this guide. `llm/graph-identity.schema.json` describes the JSON
responses with local schema references only. Toolchain 0.45 adds atomic source
type replacements through the existing patch protocol.

## Identity and content

Each store allocates a 32-hex namespace. Module names, qualified type names,
trait/implementation names, function names and endpoint names have persistent local IDs. Generic type
instances also have IDs; their source templates remain separate nodes. Function
and operation IDs retain their existing history. Deleting and reintroducing a
logical declaration in the same store reuses its declaration ID. Renaming a
module or type creates a new identity. Copying a whole database also copies its
namespace and identity lineage.

`hash` describes a canonical definition, independently of its ID, source path,
comments and formatting. A module's definition lists its imported logical
modules and sorted source members with their hashes. Derived specializations
and closures are excluded from that module definition, so another application's
instantiations do not change the shared source module's identity content.

`context_hash` includes the node's transitive checked dependencies. Recursive
components are hashed together in a deterministic order. Function references,
parameter/result/body types, generic templates and type arguments participate.
An endpoint depends on its handler. Operations include their owning function's
context, path, kind and content. Incoming callers do not participate. Therefore
changing an application caller preserves the shared library context; changing a
callee or referenced type invalidates it even if the selected function's own
canonical text stays identical. This is a graph reference policy, not a native
object-cache key or a proof of general semantic equivalence.

## Bounded queries

```sh
nex declarations --entity type --symbol common::Box --json
nex context --entity type --symbol common::Box --json
nex context --entity module --symbol common --json
nex identities --entity module --symbol common --limit 100 -o common-page.json
```

Without a source filename these commands read saved HEAD, including after live
sources disappear. `--revision HASH` selects a retained revision. An explicit
filename on `declarations` or identity export checks/saves that source first,
like `check`. Reconcile and resolve accept saved revisions only.

`declarations` returns `nex.declarations/1`; typed context returns
`nex.declaration-context/1`. Module/type context clips source at 4096 UTF-8 bytes,
omits canonical definitions larger than 8192 bytes and caps outgoing reference
previews at 100. Counts and omission/truncation flags remain explicit. Module
source is empty: its definition represents membership/imports. Source type nodes
are `editable` from toolchain 0.45; language 0.16 also supports guarded source
trait and named-implementation patches. Use `context --entity trait|impl` for
their checked declarations. Modules, contract method nodes and derived
specializations remain read-only. Replace source declarations and their affected
functions/endpoints together with `nex apply --patch FILE`. Adding top-level definitions
or changing imports still requires export/edit/check.

`identities` exports `nex.identities/1`. Supported entities are `all`, `module`,
`type`, `trait`, `impl`, `function`, `endpoint` and `operation`. A selected module exports itself,
its source functions/types/traits/implementations/endpoints and their source operations; caller-specific
derived nodes are excluded. An unscoped export includes derived nodes too.
A function selection contains its declaration; use `all --symbol FUNCTION` to
include operations, or `operation --symbol FUNCTION` for operations alone.
`--offset`/`--limit` page deterministically in kind/symbol order, followed by
functions in symbol order and operations in structural tree order. The default
limit is 100; the maximum is 1000. Page a single retained revision consistently.

`graph` keeps schema `nex.graph/2` and adds `identity_namespace`, complete
`declaration_graph`, and module `id`/`hash`/`context_hash`. Its existing function,
endpoint, structure and operation projections retain their meanings. Complete
graph export is intentionally unpaged and does not apply context preview caps.

## Explicit identity-preserving rename

After editing source names, bind the new logical names to the existing local IDs
before checking the renamed source:

```sh
nex check --json
nex identities --kind rename --symbol app::old --to app::new \
  --expected-revision OLD_HEAD_HASH --json
nex check --json
```

The command moves `node_ids` rows for functions and `declaration_ids` rows for
nominal declarations without changing their IDs, so the next checked revision
reuses the old identity. Fully qualified symbols are required when a name is not
unique; moving between modules is rejected, as are existing targets, absent
sources and a stale `--expected-revision`. The transaction does not move HEAD or
rewrite source; operator edits and a following check remain explicit.

## Transfer and resolution

Import or independently check source in the destination first. Graph import
rechecks source and allocates destination IDs; it does not adopt IDs, namespaces
or mapping claims from an exported graph. Then explicitly reconcile an identity
page against that checked destination:

```sh
# In the source project:
nex identities --entity module --symbol common --limit 100 -o /tmp/common.json

# In the destination project, after reading history's current head:
nex identities --kind reconcile --manifest /tmp/common.json \
  --expected-revision DESTINATION_HEAD_HASH --json
nex identities --kind resolve --origin SOURCE_NAMESPACE \
  --from-revision SOURCE_REVISION_HASH --node SOURCE_NODE_ID --json
```

Every node must match by kind, fully qualified symbol, operation path (when
applicable), canonical content and dependency context. Application revisions may
differ when their selected shared module matches. Local IDs are preserved. The
stored mapping relates `(source namespace, source revision, source ID)` to a
node in the selected destination revision; an ID alone is insufficient.
`resolve --revision HASH` selects an archived destination. Mapping a new
destination revision requires reconciliation again. References from the store's
own namespace/revision can resolve directly; a foreign manifest cannot rename a
local identity. Duplicate IDs, conflicting aliases and incomplete/invalid page
metadata are rejected. Namespace/digest shapes are checked; historical IDs are
opaque, nonempty strings of at most 128 UTF-8 bytes.

Reconciliation holds an immediate SQLite transaction, checks
`--expected-revision` against current HEAD and validates the entire supplied
page before committing aliases. Errors roll back the page, including any lazy
backfill. Neither source nor HEAD moves. Multiple pages are separate atomic
transactions. `offset`, `total`, `truncated` and `selection` must describe each
page consistently; they are provenance, not evidence that other pages arrived.
Use smaller pages when names make a packet approach the 4-MiB regular-file
input limit. Symlinks, directories, FIFOs and invalid UTF-8 are rejected, and
reads remain bounded if a file grows. Reconciliation limits symbols and paths
to 8192 UTF-8 bytes.

Successful responses use `nex.identity-reconciliation/1` and
`nex.identity-resolution/1`. `manifest_hash` fingerprints the supplied parsed
page; an existing identical alias retains the first page hash as provenance.
Reconciliation is idempotent for the same checked mapping. Exported source hashes
are validated as digests but do not authenticate a remote store. Aliases grant no
code execution, native-library access or source mutation authority. Runtime
semantics and language revision hashing are unchanged.

## Existing stores

The0.44 extension added declaration versions/IDs, dependency edges, revision
policy markers and identity links, with `identity_schema=1` in metadata, while
its main database remained schema 3. Its lazy indexing of genuine 0.43 archives
retained old revisions, source bytes, function IDs, operation IDs and HEAD.
Current compilers additionally use the schema 4 journal introduced in 0.49;
opening an older supported database preserves its rows and lineage, and does not
silently migrate the archived source language. Keep matching older SDKs for
historical source/artifacts and use explicit migration for current-language
checking. Do not retag genuine fixtures. Readers verify stored
declaration/edge and identity-operation metadata against checked source, and
reject unsupported identity policies.

## Atomic type replacements (toolchain 0.45)

A replacement names an existing source struct or enum, optionally with
`kind: "type"`, and provides exactly that local declaration. The same patch
can repair constructors, signatures, exhaustive matches and endpoint handlers
across modules. Generic instances are regenerated from their source templates;
patching a specialization directly is rejected. A valid struct-to-enum
refactoring can keep the same logical name and persistent type ID.

The compiler rechecks the complete candidate before one guarded transaction
commits. Invalid layouts, visibility, effects, realms, call sites or patterns
leave HEAD and history unchanged. Physical source files remain unchanged.
Build/test with `--revision HEAD`; export to materialize the accepted graph.
Archived revisions keep their original layouts and execution. Optional `kind`
can also be `function` or `endpoint` and must match the selected declaration.
Unknown patch fields are rejected. See `examples/type-patches` and
`llm/patch.schema.json`.


Toolchain 0.48 also permits exact-source-guarded operation replacements alongside
these declarations. Operations carry nonsemantic syntax intervals separately
from diagnostic positions. See [the operation guide](operations.md) for
editable expression/statement/pattern nodes, bounded previews and restrictions.
Overlapping declaration and operation ranges are rejected atomically.


Toolchain 0.49 adds graph schema 4 with a local HEAD-transition journal and
expected-HEAD restoration of retained, rechecked current-language source. The
upgrade retains old rows and starts an empty journal at the actual HEAD; it
does not infer unknown prior provenance. See [the history guide](history.md) for
`nex changes`, `nex restore`, declared labels, bounds and older-SDK compatibility.
The installed SDK backend-agreement scenario restores both source-deleted
operation-edit revisions and verifies their four actual transitions.
