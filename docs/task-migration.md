# Language0.20 and retained019 migration

Current public source is020. Keep the matching019 SDK and a complete graph
snapshot. Explicit migration rechecks018/019 source with its original parser,
checker and canonical language, then checks a separate reviewed020 target
before opening a mutable destination. Known corrupt identities/unknown languages
fail closed. The new program has a distinct020 revision; original rows/IDs/schema,
namespace and history remain. A HEAD conflict rolls back and an unchanged recheck
is idempotent.019 needs no reserved-name renaming; helper effect edits are
explicit reviewed source changes. Physical manifests/source are never rewritten.
See [the020 read contract](task-file-reads.md).

The CLI reports origin_language and origin_verified. Retained018/019/020 origins
are canonical-verified. Known earlier versions without retained parsers remain
explicit unverified-origin rechecks; do not describe them as certified old hashes.
Export old revisions with their matching SDK or explicit export support; normal
current execution never silently reinterprets old source. Source capture is not
an external filesystem snapshot or a replay permission.

The historical019 procedure below applies to its matching SDK or an explicitly
selected019 versioned API. Current CLI migration targets020. The genuine018
reserved-name repairs remain necessary when that older source conflicts.

# Explicit task-language migration

Language0.19 gives checked structured-task programs their own source identity.
A0.18 archive is rechecked explicitly; changing a manifest or a stored language
field does not migrate it. Keep the matching0.18 SDK, original source and a
complete database snapshot. Migration retains old revisions, local declaration
and operation IDs, and the existing graph schema. It adds a new revision and a
HEAD transition with the actual target language.

Discover the installed contract with `nex describe --json`. The descriptor's
language, structured-task source support, lifetime analysis and pending work
have separate meanings. A migration test does not establish platform, SDK,
debugger, profile, asynchronous IO or delivery acceptance. The bounded lifetime
analysis retains mandatory runtime authority checks; see
[task lifetimes](task-lifetimes.md) and [the task runtime contract](tasks-runtime-design.md).

## Names that need a reviewed repair

The0.19 frontend reserves the types `task<T>`, `channel<T>` and `task_scope`,
including their names in nominal declarations and generic parameters. It also
reserves these intrinsic declaration names:

| Structured-task operation | Intrinsics |
| --- | --- |
| Scope and current authority | `with_tasks`, `current_task_scope` |
| Future creation, observation and cancellation | `task_spawn`, `task_wait`, `task_cancel` |
| Channel creation, send, receive and close | `channel_new`, `task_send`, `task_recv`, `task_close` |
| Cooperative scheduling | `task_yield` |

Ordinary functions named `async`, `await`, `spawn`, `send`, `recv`, `cancel`,
`close` and `yield` remain ordinary functions. These spellings are not a reason
to rename a historical program. The source API uses the intrinsic names above
and the declared `task` effect; it does not introduce `async`/`await` keywords.

A historical declaration that conflicts with a reserved name must be repaired
in a separate candidate bundle. Review the declaration and its actual uses,
rename identifier tokens consistently, and preserve literals, comments,
substrings and unrelated lexical bindings. Recheck all candidate modules and
run the original acceptance criteria. A spelling repair alone is not a proof
of equivalence under the new checker or runtime.

## Preserve the archive, then recheck

Before upgrading, use the matching old SDK to save the old graph JSON and retain
an independent complete snapshot. Read [compatibility](compatibility.md) and
[snapshots](snapshots.md) for the database boundaries. For an archive with no
reserved-name conflict, the current compiler can recheck its selected revision:

```sh
/path/to/current-sdk/bin/nex snapshot --directory ../before019 --json
/path/to/current-sdk/bin/nex migrate --revision OLD_REVISION --json
/path/to/current-sdk/bin/nex test --revision HEAD --json
/path/to/current-sdk/bin/nex export --revision HEAD --directory ../source019 --json
```

The old physical `nex.json` and source stay unchanged. Explicit `--revision`
selects the saved new program even while physical metadata still declares0.18.
The separate exported project declares0.19 and can be checked normally. Do not
replace the original files merely to make an old physical check succeed.

If a name conflicts, retain the original old graph JSON unchanged. Make a
separate reviewed graph candidate, repair its root `source` and the affected
`bundle.files` entries consistently, and retain the actual origin revision and
language as origin metadata. The migration command derives a new checked graph
from those candidate sources:

```sh
/path/to/current-sdk/bin/nex migrate ../reviewed-candidate.graph.json --json
/path/to/current-sdk/bin/nex test --revision HEAD --json
/path/to/current-sdk/bin/nex export --revision HEAD --directory ../reviewed019 --json
```

The candidate is a new input, not a claim that its repaired text has the old
semantic hash. Migration records the candidate source/request identity and
returns a different0.19 revision. It does not trust copied declaration hashes
or transplant another store's IDs. Existing destination IDs and historical rows
remain in that store. Preserve the reviewed rename record alongside the old
archive and new acceptance evidence.

Source checking, type/effect checking and known lifetime-escape diagnostics
precede opening the migration destination. A failed source recheck cannot
initialize or upgrade it. Saving a valid candidate checks the expected HEAD
inside its transaction; a conflict leaves existing rows and HEAD intact.
Repeatedly saving the same checked revision at the same HEAD adds no transition.
A stored revision whose language disagrees with its checked semantic identity
is corrupt and returns `E_REVISION`; it must not be silently relabeled.

## Regression evidence

`tests/task_migration.py` is a standalone driver for the structured migration
probe and actual compiler. CMake registers it as `task_migration_native`:

```sh
python3 tests/task_migration.py /path/to/nex_task_migration_probe /path/to/nex
```

To retain a new evidence directory, including every structured request, raw
stdout/stderr, process result, candidate and concise report:

```sh
NEX_TASK_MIGRATION_OUTPUT=/new/evidence/task-migration \
  python3 tests/task_migration.py /path/to/nex_task_migration_probe /path/to/nex
```

The output path must not exist. Without that variable the driver uses a temporary
directory and removes it afterward. Assertions and process timeouts stay active;
a nonzero compiler result is accepted only in an explicitly rejected scenario.
The report records the installed language from `describe`, rather than pinning
a public toolchain release or private execution-guard flags.

The fixture `language-0.18-task-names.{json,sql}` was captured by the genuine
installed0.97 SDK. It has two actual0.18 revisions with results42 and43,16tables,
real declaration/operation IDs and original change records. Tests verify its
SQL/source SHA-256 metadata and both canonical revision hashes with an explicit
0.18 parser/checker. They never change these fixture files or manufacture old
history by relabeling new source.

The driver checks every table and row, SQLite DDL and schema versions. Rejected
reserved declarations preserve the entire database; a successful reviewed
migration retains every historical row except the expected HEAD replacement.
The same repaired source has distinct0.18 and0.19 semantic revisions. Graph,
operation, declaration, identity, lock and new journal envelopes carry0.19;
original journal entries and revisions keep0.18. Archived reads, explicit replay,
export and repeated rechecks use the stored selected source. HEAD conflicts,
a corrupted revision language, invalid/unknown language, invalid source and
known generic/aggregate/capture lifetime escapes are checked separately.

Real0.19 source cases additionally archive, roundtrip, export and execute scopes,
futures, rendezvous channels, generic values, immutable captures, cancellation
and ancestor borrowing through the independent reference scheduler. Public CLI
checks cover archived graph/evaluation, exported checks/tests, task evaluation
and a reviewed migration into a second complete genuine0.18 SQL store. These
are scoped regression observations; broader integration gates retain their own
reports and pending status.
