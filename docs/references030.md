---
status: current
applies_to: "toolchain 0.262.0; source0.30 development APIs"
owner: repository
---

# Versioned reference graphs: source0.30 development

Source0.30 now has a distinct checked semantic identity, canonical program
format `nex.program/18`, ordinary `nex.sources/1` archives and an explicit
history-preserving migration target. It composes the reference foundation with
the0.29 parser, kinds, contracts, errors and task syntax. This is an explicit C++
development API stage. The ordinary compiler default stays0.28, new projects
select0.29 and ordinary CLI/project selection of0.30 remains pending.

## Select and recheck

```cpp
auto program = loadVersionedBundle(bundle, root, "0.30");
auto savedRevision = revision(program);
auto restored = loadVersionedBundle(sourceBundle(program), root, "0.30");
assert(revision(restored) == savedRevision);
```

`parseVersioned(source,path,SourceLanguage::References030)` provides the matching
raw per-unit parser. The module loader supplies import resolution, visibility,
declaration-local generic binding and complete checked graphs. Use the loader
for archived application/module programs. The unarchived
`0.30-refs-prototype` remains a separate identity and keeps its dedicated API
and archival rejection; it is never relabelled into an ordinary archive.

The [grammar additions](references030.ebnf) enable `cell<T>`, its unary type
constructor, `state` and `cell_new/read/write/collect`. The existing
[reference semantics](managed-references-prototype.md), immutable snapshots,
[owned payload rules](managed-reference-owned-payloads.md) and checked arithmetic
remain in effect. Reading/mutating/collecting requires a declared `state` effect.
Cells retain identity; structural payload equality does not identify two cells.

Only0.30 reserves these new names. A retained0.29 `struct cell<T>` or
`fn cell_new(...)` retains its original parser, meaning and revision. A conflicting
new030 program receives a diagnostic; migration never silently changes an old
declaration into a builtin.

## Normal backend entry points

Version-selected030 programs use the normal `evaluate`, `emitMLIR`, `build` and
`emitTypeScriptDelivery` APIs. Native applications include/pin the cell kernel
and host bridge as actual build/runtime inputs when reachable code needs them.
The reference interpreter and generated native application keep one heap across
the whole sequential entry, including imported calls and source-error handlers.
Uncaught reference-bearing source errors are flattened inside that lifetime;
their live payload cannot escape after context close.

TypeScript entries needing a reference heap use the [ordinary host-value boundary](managed-reference-value-exports.md):
checked immutable arguments/results, one context per call, independent errors
and synchronous print observations. Their `nex.typescript-map/3` map carries the
actual030 semantic revision, source-bundle hash, operation sites and host entry
schemas. `public_revision:true` means a valid archival semantic identity; the
separate `ordinary_CLI:false` flag retains this stage's selection boundary.
The normal test-entry runner accepts this value contract and retains its
rejection of the older private diagnostic envelope.

Reachable source/effects/types determine whether an execution needs a reference
heap. A030 application without references keeps the existing029 ordinary
TypeScript/task generator and reference/native task execution. Merely loading
the030 version does not create a new heap for each continuation atom or select
the boxed representation for reference-free task programs.

Execution closures combining references with task/parallel execution currently
receive `E_CELL_CONCURRENCY`. No cross-thread transfer or shared mutable memory
model is inferred. Native library/HTTP entries needing a reference heap and Wasm
references remain explicit `E_CELL_TARGET` boundaries; reference-free entry
behavior is retained. Device emission can select030's inherited supported
scalar operations; that version check is not physical device qualification.

## Guarded migration

`preflightGraphMigration(directory,origin,expectedHead,References030,candidate)`
opens the existing graph read-only and rechecks the retained origin using its
own source version. `applyGraphMigration` rechecks the plan and transactionally
publishes a new030 revision. Old rows, local identities, source snapshots and
the graph namespace remain present. No schema reset or physical source rewrite
is part of this operation.

For new builtin-name conflicts, supply a reviewed `nex.migration-candidate/1`
with the original revision, language/source hash, target0.30 and corrected source
bundle. Renaming the conflicting old declaration is explicit. A rejected
candidate/preflight preserves the store. Ordinary synchronization cannot perform
the version transition. A new `nex.json` value alone cannot migrate its HEAD.

Use fresh isolated stores for this API stage. The ordinary CLI is not yet a
030 project driver; its version selectors and defaults remain unchanged.
Retained SDKs and graph histories are independent of this new development stage.

## Remaining integration

[Focused0.262 evidence](evidence/references030-0.262.0-2026-11-16.json) records
the versioned/backend matrix, inherited task/device emission, real retained-SDK
history migration and a relocated normal installation. The matching source
files, compiler identities, initial fixture failures and qualification bounds
are retained; this is not a full SDK/platform release receipt.

030 CLI/project publication still requires complete entry/component/HTTP/task,
debugger/profile and SDK/platform qualification. Persistent UI state needs a
longer-lived owned context; per-call exports do not implement it. Nullable
object layouts, class/interface dispatch, mutable arrays, memory visibility,
Java numerics/exception hierarchies and Python dynamic protocols/big integers
remain in [migration readiness](migration-readiness.md). Converters remain
deferred.
