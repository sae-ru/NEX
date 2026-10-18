# Versions, compatibility and explicit migration

Toolchain 0.51 keeps source language 0.15, graph schema 4 and current canonical
forms. Discover `project_features` and retrieve this guide with
`nex guide --kind compatibility --json`. The language pack indexes
`llm/project.schema.json` for authoring current project manifests.

## Physical projects and libraries

```json
{
  "schema": "nex.project/1",
  "language": "0.15",
  "entry": "main.nex",
  "libraries": { "numbers": "./vendor/numbers" }
}
```

An explicit project `language` must match the installed compiler's source
language. Older, future and unknown versions return `E_LANGUAGE_VERSION` before
physical source is parsed. Ordinary file commands validate root metadata before
opening or upgrading the graph database, so a rejected old root project remains
available to its matching SDK. Task initialization also checks source before
opening its store; task checks preflight root metadata when they select physical
program inputs. Explicit archived task candidates and frozen replay remain
independent of physical project metadata.

Configured libraries are directories of source. If a reachable configured
library has its own `nex.json`, its declared language/schema is checked before
reading its module source. An unused configured directory is not loaded. The
entry project's library mapping remains the authority for package resolution;
nested library mappings do not replace it. There is no implicit mixed-language
compilation. Migrate/export an old library separately and point the reviewed
root mapping at its current source. The matching SDK supplies ordinary standard
library sources. Archived bundles already include their required library source.

An explicit `schema` must be `nex.project/1`. Invalid schema/metadata types,
empty version/entry strings and NUL return `E_MANIFEST`. A declared language is
limited to 32 UTF-8 bytes. `libraries` maps identifier names to nonempty paths.
The compiler still accepts legacy omitted schema/language fields; omitted
language means the current compiler's language, not automatic detection of an
older language. New projects should always declare both. Extra editor metadata
is permitted. An entry is required when a command does not receive a source
file. Normal source-root/import containment and dependency locks still apply.

## Archived source and the physical projection

`graph`, `history`, `changes`, archived context, explicit `--revision` execution,
restore, snapshot and recovery select stored data rather than rechecking a stale
physical declaration. Their own revision/schema checks remain active. An older
archive still cannot execute as a current-language program without explicit
migration. `migrate` rechecks the archived source with the current checker and
retains original revisions/IDs; it does not overwrite physical files or rewrite
the old `nex.json`. Export a separate current-language project afterward.

Use the matching old SDK to establish an actual old source graph when needed:

```sh
/path/to/old-sdk/bin/nex check --json
/path/to/old-sdk/bin/nex graph --json > archived-graph.json
/path/to/current-sdk/bin/nex snapshot --directory ../before-migration --json
/path/to/current-sdk/bin/nex migrate --json
/path/to/current-sdk/bin/nex test --revision HEAD --json
/path/to/current-sdk/bin/nex export --revision HEAD --directory ../current-source --json
```

If the old project has no retained database at the destination, use
`nex migrate archived-graph.json`. Keep the original SDK and a complete graph
snapshot separately before migration. A schema-4 database is not readable by
older schema-3 compilers. `snapshot` preserves the original supported schema
without upgrading it; see [its scope and limits](snapshots.md).

Migration is an explicit recheck under current semantics, not proof of semantic
equivalence for every historical program. Review diagnostics and acceptance
criteria. Old reserved names may require repairs to an exported candidate.
Keep original archives and regenerate reviewed task/proof pins for the accepted
new revision; do not weaken requirements to make a migration pass.

## Separate compatibility boundaries

| Artifact | Current policy |
| --- | --- |
| Source language | Explicit declared version; current 0.15. Old archived source requires matching SDK or explicit recheck/migration. |
| Project manifest | `nex.project/1`; legacy omitted metadata accepted; unknown declared schema rejected. |
| Local graph database | Current schema 4; supported schema 1–3 upgrades retain rows/IDs and an explicit journal base. Old tools must use their original compatible database. |
| Graph/source export | Versioned JSON with source language and exact bundle. Import derives destination-local IDs; complete graph recovery preserves lineage. |
| Tasks, proof contracts, debug frames | Preserve recorded schema/language/revision/source/build identities. Retain matching tools; no blanket promise of cross-SDK replay. |
| Native host/runtime | Use the matching SDK and checked ABI/signature/pin contracts. Current experimental C ABI has a retained ABI-1 prefix; this does not certify all cross-version binaries. |
| Native builds and SDK distribution | Compiler/dependency/target identities and measured execution scope remain explicit. Cross-build success is not platform execution evidence. |

Toolchain version numbers do not replace these independent format identities.
Never infer compatibility from a shared major/minor number alone. JSON Schema
checks document shape; the installed compiler enforces version, graph and
semantic rules. Broader stable-ABI, platform/device and reproducible-distribution
validation remains pending as recorded in `STATUS.md` and `PLAN.md`.
