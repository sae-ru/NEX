# Change history and archived restoration

Toolchain 0.49 retains language 0.15 and canonical/identity policies while
upgrading the local graph database from schema 3 to 4. Discover
`history_features`, `history_limits` and `llm/history.schema.json` from the actual
installed compiler. This guide is available through `nex guide --kind history`.

## Revisions and transitions

`nex history --json` retains its existing revision inventory. A revision can be
saved for a task or package without ever becoming HEAD; its creation timestamp
is not a complete editing history. The separate change journal records actual
committed HEAD transitions, including a return to an older retained revision.

```sh
nex check --note "Initial implementation" --actor "local operator" --json
nex changes --offset 0 --limit 100 --json
nex changes --offset 100 --limit 100 -o changes-page.json --json
```

Each `nex.change/1` record includes its local namespace/sequence, previous change
hash, previous/selected semantic revision, exact selected archived source hash,
compiler version/build, action/command, UTC creation time and optional actor/note.
`request_hash` identifies the canonical JSON payload when available for
apply/import/migrate/restore; it is empty for source synchronization. Hashes use
the compiler's BLAKE3 digest. A record hash covers its canonical stored JSON
without the returned `hash` field. Source hashes identify archived bundles;
semantically equivalent formatting retains the first exact saved bundle.

Actor and note are declared labels, not authenticated author identities. A
source-based command that synchronizes a different checked revision records
`synchronize`; ordinary archived queries do not move HEAD. A no-op, failed patch
or non-HEAD candidate does not invent a transition or retain an unused note.
Both the graph changes and their journal record commit in the same transaction.

Pages run in one SQLite read snapshot and return newest transitions first with
total/offset/limit/truncation fields. Record hashes and adjacent journal links
are checked for the selected page and current tip. This local integrity check
does not authenticate a recording or certify every unrequested historical page.
Keep the namespace with records when comparing stores. Source/graph imports
derive local identities and do not import a foreign journal as trusted history.

## Restore a retained revision

First read the desired retained target and current HEAD. Use their actual
64-character hashes:

```sh
nex history --json
nex restore --revision TARGET_HASH --expected-revision CURRENT_HEAD_HASH \
  --note "Return to the last accepted implementation" --json
nex test --revision HEAD --json
nex run --revision HEAD --json
```

Restore rechecks the target's archived current-language source and semantic
identity before an expected-HEAD transaction. It does not compile or execute the
program, load native foreign modules or grant effects. A stale guard returns
`E_CONFLICT`; a missing target returns `E_REVISION`; an older language returns
`E_LANGUAGE_VERSION` and still needs explicit `nex migrate`. Use `EMPTY` as the
expected value only when the store has no HEAD but contains the desired retained
candidate. A no-op reports `changed:false` without creating a change record.

The original and newer revisions, local node IDs, sources and artifacts remain
retained. Restoration is another forward journal entry, not deletion of history.
Physical source files remain unchanged. File-based commands can synchronize
their source projection back into HEAD; use `--revision HEAD` to validate the
restored graph, then `nex export --directory NEW_DIRECTORY` to materialize it.

## Upgrade and limits

The schema-4 upgrade is automatic and transactional. It preserves existing
revision/source/identity/task data and captures the actual HEAD as
`base_revision`. It creates an empty journal rather than fabricating authors or
transition order for older data. Older compilers do not understand schema 4;
retain their matching original database/compiler/resources for old SDK receipts.
Exported source preserves program semantics; copy the complete database to
preserve its local journal and UUID lineage.

Page limits are 1–1000 records, default 100, and offsets are 0–10,000,000. Notes
are at most 1024 UTF-8 bytes and actor labels at most 128, without NUL. A stored
record is bounded to 16 KiB. Invalid labels return `E_CHANGE`, invalid page or
restore options `E_OPTION`, and malformed records/links `E_CHANGE_INTEGRITY`.
Changes and restore select the current project store; they accept no source
file, execution arguments or target/profile selection.
