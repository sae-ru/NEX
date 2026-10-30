# Explicit typed-error graph migration development

Toolchain0.148 keeps ordinary CLI projects on language0.26. The checked C++ API
can archive0.27 source and migrate an existing graph explicitly. The explicit C++ native builder now develops027 source/static/shared/mixed
provider delivery under [matching ABI7 contracts](typed-error-providers.md).
Public CLI selection, UI/Worker, graph-snapshot and SDK delivery remain separate gates. This API is available to compiler/tooling development; it adds
no ordinary CLI flag or implicit source-language upgrade.

Language027 revisions use `nex.program/15`; retained026 uses its original
`nex.program/14`. Function/statement canonical extensions and concrete error
keys round-trip through a checked source bundle. A revision language cannot be
changed by relabelling stored metadata. `loadVersionedBundle` rechecks0.27 only
when explicitly selected. Ordinary loading retains its026 default.

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
directory. Such a project still requires a future matching027 CLI delivery;
the current ordinary compiler rejects its manifest instead of retagging it.

`tests/typed_error_migration.py` starts from the immutable genuine026 fixture
created by toolchain0.139 and a modular026 fixture produced by the verified146
compiler. It checks all16 tables, both retained revisions,
namespace/IDs, reviewed typed source, invalid/corrupt/retagged candidates,
concurrent publication, idempotence and export roundtrip. It emits and executes
the committed/reloaded graph with AST, TaskIR, native O0/O2 at1/4 workers and
Node. The historical fixture's `target_migration_implemented: false` records
its original production time; the new test and current descriptor record147.
