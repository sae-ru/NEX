# Genuine language0.22 histories

These six generated test projects contain three revisions each. The actual
installed SDK0.132.6 compiler SHA256 is
`a75421b899a7e47d617a8ef6257123f75db4ee4f9869fe2aa11c3be6b87bb1a8`.
It checked every revision and executed native/reference and TypeScript tests.
The fixtures are newly compiled022 graphs, not relabelled021 SQL. The first
five use the earlier reviewed resource/nominal/callable/import/task examples;
the sixth uses installed std model/compute/device imports with CPU computation.
Opaque resource declarations are checked; these cases do not execute opaque
resource factories or GPU/NPU operations.

Each JSON contains exact archived bundles, original revision hashes, execution
observations, table counts and a raw SQL SHA256. Every SQL export contains the
complete16-table logical database, including namespace/local IDs. A SQL restore
can allocate different physical btree pages; migrations must preserve the
restored schema and every original row/ID.

The model/compute/device SQL is7,001,523 bytes because it contains specialized
graph records. Its `.sql.xz.b85` file stores the exact SQL with lossless XZ and
ASCII base85; the conformance test bounds decompression to8MiB and checks the
pinned raw digest before opening SQLite. Other fixtures are plain SQL.

The public CLI test migrates all18 revisions, rejects implicit HEAD upgrades,
preserves physical manifests and old rows/schema/IDs, verifies native/reference
outputs and retained web tests, then verifies idempotence. Keep old SDKs and
captured runs; these fixtures do not make old receipts current-language runs.
