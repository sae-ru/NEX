# Versions, compatibility and explicit migration

The ordinary CLI supports projects declaring source language 0.28, 0.29 or
0.30. New projects created with `nex init` declare 0.30. Without a declared
language the compiler uses its 0.28 fallback. Discover the installed toolchain's
choices with `nex describe --field project_languages --json` and retrieve this
guide with `nex guide --kind compatibility --json`. The current graph schema is
4. See [the language specification](language.md) for the canonical formats.

## Physical projects and libraries

```json
{
  "schema": "nex.project/1",
  "language": "0.30",
  "entry": "main.nex",
  "libraries": { "numbers": "./vendor/numbers" }
}
```

An explicit project `language` selects one of the compiler's supported ordinary
project versions. Unsupported versions return `E_LANGUAGE_VERSION` before
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
language selects the compiler fallback. New projects should always declare
schema and language. Extra editor metadata
is permitted. An entry is required when a command does not receive a source
file. Normal source-root/import containment and dependency locks still apply.

## Archived source and the physical projection

`graph`, `history`, `changes`, archived context, explicit `--revision` execution,
restore, snapshot and recovery read retained data. Each command applies its own
revision, schema and language checks. To execute a 0.28 or 0.29 revision, select
its matching project language. To use that project as 0.30, explicitly migrate
the archived source. Migration appends the checked target revision and preserves
the original revisions, local IDs, namespace and physical files. Export the
result to materialize the 0.30 source, manifest and dependency lock.

Use a matching SDK to establish the source graph if it has never been checked.
From the existing project, review the migration before applying it.

```sh
nex snapshot --directory ../before-migration --json
nex migrate --language-version 0.30 --kind plan --json
nex migrate --language-version 0.30 --expected-revision OLD_HEAD --json
nex export --revision HEAD --directory ../project030 --json
cd ../project030
nex check --json
nex test --json
```

The plan reports the expected HEAD, the origin's checked identity and any target
diagnostic. For a reserved-name conflict, edit the sources in the returned
candidate and apply with `--candidate FILE`. A graph export can also be supplied
as `nex migrate archived-graph.json --language-version 0.30`. For target 0.30,
an export of a retained revision must agree with its stored source snapshot.
Older migration targets retain their repaired-graph input. The compiler
verifies the old revision against its retained snapshot before checking the
supplied repair under the selected target. See
[0.30 migration](references030.md#guarded-migration) and
[snapshot and recovery](snapshots.md).

Migration is an explicit recheck under current semantics, not proof of semantic
equivalence for every historical program. Review diagnostics and acceptance
criteria. Old reserved names may require repairs to an exported candidate.
Keep original archives and regenerate reviewed task/proof pins for the accepted
new revision; do not weaken requirements to make a migration pass.

## Separate compatibility boundaries

| Artifact | Current policy |
| --- | --- |
| Source language | Ordinary project versions 0.28, 0.29 and 0.30. Use explicit versioned migration for updates. |
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

## Compatibility target for 1.0

The beta qualifies the documented 0.30 source behavior and supported SDK
platforms. The 1.x compatibility promise starts with the 1.0 release. A program
using documented 0.30 syntax and stable standard-library APIs should continue
to check and retain its specified behavior on later 1.x toolchains. It can be
rebuilt with the SDK for its target. The promise covers explicit 0.30 project
selection, graph export and snapshot recovery, with retained revision IDs and
source versions. A later language mode that changes meaning must be opt-in and
offer an explicit, guarded migration.

The 1.0 release notes identify the stable APIs, CLI and JSON schemas covered by
that promise. The proposed [CLI contract](cli-consumer-contract.md) specifies
the fields read by a tool that creates, checks, tests and runs a native project.
The [standard-library contract](stdlib-source-compatibility.md) identifies
the public signatures and constructor fields used by existing source programs.
Native components, task/debugger records and external providers
keep their own versioned compatibility contracts. Use their matching SDK and
runtime when the release notes require them. GPU and NPU support is listed by
qualified provider and device.

Before promoting the beta, run the 0.30 agreement and migration corpus on the
proposed 1.0 SDKs. Check and execute the published beta examples with the new
compiler. Recover beta snapshots and rerun their selected revisions. Record
which preserved source, archive, CLI and platform contracts passed. Include any
intended compatibility exception in the release notes before making the promise.

### Checking a proposed host SDK against a published beta

Use the release record and the original archive for the host. For the
single-platform 0.280.1 release, use the checked-in
delivery record shown below. For a multi-platform release, download
`qualification.json` and the host archive from the same GitHub release and
pass that JSON file to `--release-record`. The runner selects the target by
archive length and SHA256, so a renamed local download also works. The target
must cite the release's source commit. The restored SDK must match the target's
compiler host, compiler checksum and file count. The report records the target
and source commit. Use the record from GitHub Releases when qualifying a public
baseline. For release qualification, pass the candidate archive and its own
record as well. The runner verifies both archives, restores their inventories
in separate directories, checks that the host ABIs match and uses the two
restored compilers, examples and migration tools. The resulting report records
both archive checksums, both release-record checksums and both compiler identities.

The archive comparison runs the 0.30 agreement corpus with the restored
candidate compiler. Set `NEX_TSC` to the pinned TypeScript compiler and
`NEX_NODE` to Node. It uses the corpora shipped by the two SDKs and runs
identical manifests and source files once. Once a baseline ships a corpus,
the candidate must also include one. When both SDKs predate the packaged
corpus the runner uses the compatibility tool's own corpus. The report
identifies which SDKs shipped a corpus, the inputs executed and the coverage
of each run.

The runner checks the archive SHA256,
restores its complete inventory, then verifies that both compilers select
their own installed runtime. It exercises the public CLI and standard-library
contracts against both installations, runs the published examples from fresh copies,
recovers two historical revisions and checks both the published and current
migration suites. Use a fresh output directory. Successful runs discard the
copied projects' native build cache. Failed runs keep it for diagnosis.
On macOS the runner uses the selected Apple SDK. Set `SDKROOT` to override
the SDK reported by `xcrun --sdk macosx --show-sdk-path`.

```sh
python3 -B tools/sdk_compatibility.py \
  --release-record docs/releases/0.280.1.json --baseline-archive "$beta_archive" \
  --candidate-release-record "$candidate_record" --candidate-archive "$candidate_archive" \
  --output build/beta-compatibility
```

During development, pass an installed prefix using `--candidate-sdk` in place
of the two candidate archive options. Use that prefix to exercise the current
backend agreement corpus separately.

```sh
python3 -B tools/agreement.py --compiler "$candidate_prefix/bin/nex" \
  --language-version 0.30 --require-complete --output build/candidate-agreement
```

For the agreement run set `NEX_TSC` to the pinned TypeScript compiler and
`NEX_NODE` to Node. The [recorded macOS ARM64 comparison](evidence/beta-source-compatibility-efef1032-2026-11-23.json)
uses the published 0.280.1 archive and an ordinary 0.281.0 Release installation
from `efef1032`. It covers ten explicit 0.30 projects, archived identities,
0.28/0.29 migration and all thirteen checker cases. Eleven executable cases
passed reference, native Debug and Release, strict TypeScript and Node execution.
Each platform and subsequent release candidate needs its own identified SDKs.

The [comparison for candidate `7f1b75ea`](evidence/beta-contracts-7f1b75ea-2026-11-23.json)
also checked the six-command consumer workflow and every catalogued source
declaration in 0.280.1. It preserved 207 functions and 35 structures across
20 modules. All ten published projects and both retained revisions ran on
macOS ARM64. Eleven executable agreement cases passed in the interpreter,
native Debug and Release and executed strict TypeScript.

On macOS ARM64, a local rehearsal used a two-platform index assembled from
development archives. All six compatibility checks passed with the selected
macOS archive, including its eleven 0.30 projects. A separate check executed
all twelve 0.30 example projects from `584715e4` with two compiler builds. The
new map example printed `east` then `west` after removing and reinserting a key.
The future 1.0 release gate still requires the publicly distributed beta and
the actual candidate for each supported host.
[Compiler identities and rehearsal results](evidence/multi-platform-baseline-rehearsal-2026-11-23.json)

The published 0.280.1 macOS ARM64 archive and the earlier 0.281.0 development
archive from `d492bf7f` passed all seven checks with both SDKs restored from
their recorded bytes. Each of the ten published 0.30 example projects passed,
and the candidate recovered two earlier snapshot revisions. Both archives
predate the packaged agreement corpus. The maintained corpus ran 13 checker
cases and 11 executable cases on the candidate and separately on the
`584715e4` macOS source build.
[Host, archive and backend measurements](evidence/host-archive-pair-and-030-agreement-2026-11-23.json)

## Historical source migrations

Language0.17 result propagation is additive syntax with an appended AST kind15;
existing function/structure/enum/program formats retain old kind numbering.
Program identities include the new language. Preserve a complete snapshot and
SDK0.81 for0.16 artifacts; explicitly migrate the archived bundle, verify all old
rows/IDs remain, then export a new0.17 project. Never edit the original version
field as a substitute. See [result propagation](error-propagation.md).

Language0.18 adds the reserved parallel_map intrinsic. Keep the0.17 SDK and a
complete store snapshot. Explicit migration rechecks archived source and retains
old rows/IDs/schema; conflicting old declaration names require an explicit
reviewed exported-source repair. The genuine017 fixture has two actual revisions,
including a reserved-name conflict; no stored version/source is relabeled.

## Language0.19 task migration

Language0.19 reserves ten task intrinsics and `task`, `channel`, `task_scope`
type names. Retained018 bundles use the original parser and canonical hashes;
public019 recheck creates a new revision while preserving old rows/IDs. Conflicting
declarations need an explicit reviewed source repair. The physical manifest is
not automatically rewritten. See [the migration procedure](task-migration.md).

## Language0.20 task file reads

The two read builtins suspend only in actual server task/fs functions.019 is
rechecked under its original rules before a separate020 migration target.
Callable realm/effects remain exact; fs-only helpers require reviewed task/fs
declarations before task use. All historical rows/IDs/schema remain unchanged;
program/14 includes actual language and therefore gives distinct revisions.
Migration preflight precedes mutable destination access. See [migration](task-migration.md)
and [the exact source/target boundary](task-file-reads.md).
