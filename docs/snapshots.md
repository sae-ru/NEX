# Graph snapshots and recovery

The snapshot commands were introduced in toolchain 0.50. Current development
0.151 supports mixed language0.26/0.27 histories and preserves the captured
graph schema, all16 tables, namespace and local IDs. Recovery copies a graph;
a language upgrade requires a separate explicit migration. Discover `snapshot_features`, `snapshot_limits` and
`llm/graph-snapshot.schema.json` from the installed compiler. Retrieve this guide
with `nex guide --kind snapshot --json`.

## Preserve a complete local graph

```sh
nex snapshot --directory /backup/my-project-graph --timeout 60 --json
nex recover /backup/my-project-graph --directory /work/recovered-project --json
cd /work/recovered-project
nex history --json
nex changes --json
nex test --revision HEAD --json
nex run --revision HEAD --json
nex export --revision HEAD --directory /work/recovered-source --json
```

Snapshot selects the current working directory's existing `.nex/graph.db`.
It opens the source read-only and performs no schema migration, source check,
HEAD synchronization or SQL data write. It uses the
[SQLite Online Backup API](https://www.sqlite.org/backup.html) from one pinned
read transaction. The destination includes committed WAL data and is normalized
into a standalone `graph.db`; copying only the live database file would miss
committed data still in WAL. WAL writers can continue during capture. Older
rollback-journal databases can hold writers until the read transaction ends.

The snapshot directory contains `graph.db` and `snapshot.json`. The manifest
records the byte count/SHA-256 digest, graph schema, actual captured HEAD and its
language, local namespace, per-table row counts, declared creator/build and UTC
time. Every ordinary database table is copied, including archived source bundles,
revisions, local node IDs, aliases, HEAD journal and task-run index. An empty
initialized graph is supported. Directories use mode 0700 and files 0600, subject
to a more restrictive process umask. Files and directories are synchronized
before success is reported. Copy the **entire completed directory** to durable
storage. Neither a local duplicate nor a digest alone is off-machine backup.

## Recovery preserves lineage

Recovery verifies the fixed manifest/member names, strict UTF-8/JSON limits,
database SHA-256 and size, SQLite integrity/foreign keys and the captured state.
It copies the graph into a new project's `.nex/graph.db` and writes a minimal
`nex.json` and `RECOVERY.md`. It does not modify the snapshot or any existing
project, adopt different local IDs, move HEAD or create a journal event. All
database rows are retained. This differs from graph/source import, which derives
local destination identities, and source export, which materializes one revision.

Physical NEX source files are absent after recovery. Use `--revision HEAD` or an
explicit archived hash when checking/testing/building the recovered program;
then export into another new directory to materialize its source. File-based
commands read and synchronize physical files and can therefore replace HEAD.

Complete supported databases of schema 1–4 can be captured without migration;
the regular required graph tables must be present. A later ordinary compiler
command can migrate an older recovered database. Older source languages still
need their matching SDK or explicit history-preserving `nex migrate`. Preserve
the matching SDK separately for historical tasks and debugger recordings.

## Scope and trust

External task receipt/artifact **files**, generated executables/debug manifests,
native library bundles, compiler/SDK dependencies, live source changes that have
not been saved to the graph, and application databases/assets are **not included**.
The task index can refer to such missing files. Preserve them separately; this
command is a graph backup, not complete application deployment or task replay.

SHA-256 detects changed bytes relative to the supplied manifest; it does not
authenticate a snapshot, author or provenance. SQLite integrity is structural;
recovery does not certify program semantics or every historical journal entry.
Use normal compiler checks and paged journal validation after recovery. Neither
command executes NEX programs/extensions or grants native/filesystem privileges.
Snapshot files are data, not instructions or operator authority.

## Limits and failures

Both output directories must be new; even an existing empty directory returns
`E_EXISTS`. Ordinary failure removes the command's owned output directory.
Parent directories may be created; interruption/power loss can leave incomplete
output, which must not be treated as accepted without a valid complete manifest.
Regular non-symlink member files are required; FIFOs/devices and final-component
links are rejected. Ordinary parent directory aliases are supported.

The manifest is at most 64 KiB with JSON depth 16. Graph inventory permits at
most 64 ordinary tables, with table names at most 128 UTF-8 bytes. Views, triggers,
virtual/shadow tables and generated/hidden columns are rejected. Source and
snapshot locations must be under the caller's control during the operation;
this is not a filesystem sandbox against concurrent path replacement.

`--timeout` is 1–3600 seconds, default 60. The cooperative deadline covers SQLite
busy/locked retries, progress and incremental file copying; an operating-system
I/O call may still block. No fixed graph byte limit or disk-space reservation is
implied. The Windows x64 adapter uses protected current-user ACLs, real64-bit
file identities and `FlushFileBuffers`. A local graph-schema4 snapshot/recovery,
HEAD execution and explicit source export are checked in the
[Windows-hosted compiler receipt](windows-host.md). Full Windows snapshot
regression and other platform validation remain pending.

Invalid options return `E_OPTION`; member/path problems `E_SNAPSHOT_FILE`;
unsupported metadata/structure `E_SNAPSHOT_FORMAT`; digest or recovered-state
mismatch `E_SNAPSHOT_INTEGRITY`; deadline expiry `E_SNAPSHOT_TIMEOUT`; other
SQLite failures `E_SNAPSHOT`. Unknown graph schema returns `E_SCHEMA`.
