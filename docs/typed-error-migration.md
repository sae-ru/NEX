# Explicit typed-error graph migration development

Toolchain0.151 develops ordinary language0.27 CLI execution and explicit migration
of archived026 graphs. Native source/static/shared/mixed delivery uses the
[ABI7 contracts](typed-error-providers.md); [web delivery](typed-web-delivery.md)
uses checked maps. Matching full/SDK/platform acceptance remains pending.

Before migration, preserve the original graph with `nex snapshot`. Review
`nex migrate --kind plan --revision HEAD --expected-revision OLD --json`;
then apply the same expected revision, optionally with a reviewed `--candidate`.
Migration publishes a new checked graph revision and retains old rows/IDs.
Physical source, manifest and lock materialization is a separate export into a
new directory: `nex export --revision HEAD --directory NEW --json`.
Do not replace a version field or overwrite unsaved physical edits.

This CLI path needs an archived origin or exported graph. A source-only old Git
checkout needs its matching SDK to check/export or an origin graph snapshot;
source-only migration bootstrap is still pending. No origin is fabricated.

Language027 revisions use `nex.program/15`; retained026 uses its original
`nex.program/14`. Function/statement canonical extensions and concrete error
keys round-trip through a checked source bundle. A revision language cannot be
changed by relabelling stored metadata. `loadVersionedBundle` rechecks0.27 only
when selected. Ordinary current loading selects027; retained026 rechecks stay separate.

`preflightGraphMigration` in `include/nex/migration.h` takes an existing store
directory (normally `PROJECT/.nex`), an origin revision or `HEAD`, a nonempty
expected HEAD and an explicit target language. It opens the graph read-only,
recomputes the origin revision under its retained parser, then checks and
round-trips the complete target bundle. It cannot create or upgrade a graph.
Its plan binds the canonical store path, graph namespace, origin revision/source
hash, expected HEAD, target revision/source hash and checked source snapshot.

An optional reviewed `nex.migration-candidate/1` has exactly six fields:
`schema`, `origin_revision`, `origin_language`, `origin_source_hash`,
`target_language`, and `sources`. The guards must match the retained origin;
the target is fully rechecked. A malformed or invalid candidate fails before
opening writable state. Omitting a candidate rechecks the unchanged old source
under027; legacy throw/catch/finally remains executable.

`applyGraphMigration` revalidates the plan and origin before opening writable
state. `Store::save` repeats both expected-HEAD and namespace checks inside its
transaction. A competing writer, replaced namespace, corrupt origin or modified
plan cannot publish the planned transition. An unguarded ordinary save cannot
change a026 HEAD into027, or implicitly downgrade027. An explicit migration
appends the new revision while preserving old revisions, schema and local IDs.

Migration does not rewrite physical source files, `nex.json`, or dependency
locks. The result has `materialized: false`. An explicit, separate
`exportProject(..., "0.27")` can materialize the checked source in a new/empty
directory. The ordinary027 CLI checks and runs that exported source, while
retained026 physical projects still require their explicit migration.

`tests/typed_error_migration.py` starts from the immutable genuine026 fixture
created by toolchain0.139 and a modular026 fixture produced by the verified146
compiler. It checks all16 tables, both retained revisions,
namespace/IDs, reviewed typed source, invalid/corrupt/retagged candidates,
concurrent publication, idempotence and export roundtrip. It emits and executes
the committed/reloaded graph with AST, TaskIR, native O0/O2 at1/4 workers and
Node. The historical fixture's `target_migration_implemented: false` records
its original production time; the new test and current descriptor record147.
