# Persistent graph identities

Toolchain 0.44 retains language 0.15 and database schema 3. It adds independent
module/type nodes and checked references between stores. Query `nex describe
--json` for the installed compiler's policy and limits; `nex guide --kind graph
--json` returns this guide. `llm/graph-identity.schema.json` describes the JSON
responses with local schema references only. Toolchain 0.45 adds atomic source
type replacements through the existing patch protocol.

## Identity and content

Each store allocates a 32-hex namespace. Module names, qualified type names,
function names and endpoint names have persistent local IDs. Generic type
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
source is empty: its definition represents membership/imports. Source type nodes are `editable` in toolchain 0.45; modules and derived
specializations remain read-only. Replace a source type and its affected
functions/endpoints together with `nex apply --patch FILE`. Adding top-level definitions
or changing imports still requires export/edit/check.

`identities` exports `nex.identities/1`. Supported entities are `all`, `module`,
`type`, `function`, `endpoint` and `operation`. A selected module exports itself,
its source functions/types/endpoints and their source operations; caller-specific
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

The extension adds declaration versions/IDs, dependency edges, revision policy
markers and identity links, with `identity_schema=1` in metadata. The main
database remains schema 3. Opening a genuine 0.43 store lazily indexes checked
archived source without changing old revisions, source bytes, function IDs,
operation IDs or HEAD. Older compilers can still read their original tables.
No language migration or fixture retagging is involved. Readers verify stored
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
