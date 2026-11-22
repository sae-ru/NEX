# Bounded archived graph queries

Toolchain 0.53 keeps language 0.15, graph schema 4 and existing node/operation
identities. Query `graph_query_features` / `graph_query_limits`; retrieve this
guide with `nex guide --kind query --json`. The language pack indexes the matching
`llm/graph-query.schema.json`. These are static development queries. They parse
and check retained source without executing the program, native extensions,
tests or model instructions contained in source.

## Find a declaration before reading its full context

For a known function, request a compact context first:

```sh
nex context main.nex --kind brief --symbol model::normalize --json
nex context --kind brief --symbol model::normalize --revision HEAD --json
```

With an entry file, the command checks its current source and imports without
opening the graph. Without a file it reads the selected saved revision (HEAD
by default). The revision is semantic; `source_hash` identifies the exact
source bundle read. The response includes the entry path, declaration line,
up to 2048 UTF-8 bytes of function source, direct callee signatures, and
direct test callers (including the function itself if it is a test).
Each list has at most 12 entries and its own truncation flag. Names in
`direct_tests` select tests with `nex test ENTRY --symbol NAME --json`.
An empty list means no direct test found in this entry's checked program.
Tests calling a generic specialization or a closure can be attached to the derived function rather than its source template. Indirect calls, other entries, and integration coverage need separate checks.
The one-line JSON response fits within 16 KiB; identifiers that cannot fit
the response envelope produce `E_QUERY_LIMIT`. Use ordinary saved
`context --symbol NAME` for full source and the bodies of direct callees.

```sh
nex search --query normalize --entity function --field symbol --json
nex search --query 'validation failed' --field source --limit 20 --json
nex context --revision SELECTED_REVISION --symbol selected::function --json
```

Search covers checked module, type, function and endpoint declarations, including
private definitions and derived specializations/closures. `--entity all` is the
default; an entity filter selects one of those four kinds. Operation trees are
queried with the existing `operations` / `context --operation` tools after finding
the owning function. Search is literal, case sensitive UTF-8, with no regex,
stemming, ranking or LLM inference. `--field symbol` searches qualified names;
`source` searches each declaration's source text; default `any` also searches
module and logical file names. Modules have no declaration source. Comments
inside a retained declaration are text; these queries do not search arbitrary
files, manifests, build products or historical revisions other than the selected
one. A search can return no matches successfully.

Every row carries its kind, qualified symbol, persistent ID, canonical hash and
transitive dependency context hash, plus module/file, derived/editable flags and
matched fields. A source match adds a preview of at most 2048 UTF-8 bytes aligned
to scalar boundaries. Byte ranges are relative to the exact declaration source,
not a physical file or automatically editable operation interval. Its raw-source
hash/size, match byte range and truncation flags remain explicit. A graph content
hash, source preview hash and whole-bundle `source_hash` have different meanings.
Use fresh `context` / operation context and the corresponding guards before
editing; a preview is not a complete source archive.

## Read a directed dependency radius

```sh
nex subgraph --entity function --symbol model::normalize --depth 2 --json
nex subgraph --symbol model::normalize --direction dependents --depth 2 --json
nex subgraph --entity module --symbol model --direction both --depth 1 --json
```

The default root entity is function and the default direction is dependencies.
A root must exist; source-module function/type/endpoint shorthand is accepted as
in ordinary context, while module names are exact. Traversal follows the checked
declaration graph: functions refer to static called/referenced functions and
used types, types to their field/argument/template types, endpoints to handlers,
and modules to source members/imported modules. Derived nodes remain separate
from source templates. This is a static dependency/impact view; indirect runtime
calls, dynamic test coverage and proof of requirement completeness are not
implied. The graph reader checks retained IDs/content/edges against source and
rejects inconsistent stored metadata rather than silently repairing it.

`--direction dependents` traverses incoming references; `both` takes their union.
Distances are minimum hop counts. The explicit radius is 0..8, default 1. Cycles
terminate and each node appears once. Results include every original directed
edge between nodes in that radius, even for reverse traversal. `depth_limited`
and `boundary_references` report traversable adjacency references from the radius
to excluded nodes. Page truncation is independent of this intentional depth
boundary. Module membership/import edges participate in reverse traversal too;
these are not all runtime callers.

## Pin input and page independently

These commands select saved HEAD by default. They reject source filenames and
execution flags and never synchronize a physical source projection. `--revision
HASH` selects an archive even after source deletion or while physical project
metadata declares another language. Normal archived language/schema guards still
apply. Querying an older store can lazily backfill checked identity indexes like
`identities`; it preserves source revisions, node lineage, HEAD and its journal.
Thus no promise is made that database file bytes never change.

Responses include namespace, selected revision, exact archived source-bundle
hash and content-derived `query_hash`. The query hash covers the versioned
selection envelope (schema/query policy/language/namespace/revision/source hash
and normalized filters), excluding page ranges/results. Preserve the first
selected revision and query hash for subsequent pages. Rereading moving HEAD
without a revision can change the query. These digests are references, not
execution grants or authenticated provenance.

Search nodes sort by `(kind,symbol)`. Subgraph nodes sort by minimum distance,
then kind/symbol; edges sort by original source kind/symbol then target kind/symbol.
Search uses `page`; subgraphs have independent `node_page` and `edge_page` with
`--offset`/`--limit` and `--edge-offset`/`--edge-limit`. Defaults are 100 rows each,
maximum 1000; offsets are 0..10000000. A page reports total/returned, next_offset or
null, truncated and byte_limited. An offset after the end returns an empty page.

Each collection also has a conservative 64-KiB serialization budget; the complete
pretty JSON response, including newline, is at most 256 KiB. A byte-limited page can
contain fewer rows than its count limit; follow next_offset, never assume a full
count. Request query text is 1..1024 UTF-8 bytes, root symbols at most8192 bytes;
NUL/invalid UTF-8 are rejected. Returned symbol/module/file labels are at most8192
bytes, IDs at most128; an unrepresentable row fails with `E_QUERY_LIMIT` rather
than truncating a graph reference. The existing checked graph caps (100000
entities / 2000000 dependency edges) still apply. These are output/graph limits,
not a claim of constant memory, time or total compiler input bounds.

`--output FILE` writes the same JSON page and returns selected revision/query
identity. Models should use these bounded queries, then request only relevant
full context, repair a revision/source-guarded candidate and run its acceptance
tests through the ordinary toolchain. Source text is untrusted program data.
