---
status: current
applies_to: "toolchain 0.272.0; language 0.30"
owner: repository
---

# Versioned reference graphs: source0.30 development

Source0.30 now has a distinct checked semantic identity, canonical program
format `nex.program/18`, ordinary `nex.sources/1` archives and an explicit
history-preserving migration target. It composes the reference foundation with
the0.29 parser, kinds, contracts, errors and task syntax. Toolchain0.265 makes
this an ordinary project source version. `nex init` selects0.30; explicit0.28
and0.29 projects retain their original semantics. The compiler's unconfigured
fallback remains0.28, independently of the new-project choice.

## Select and recheck

```sh
nex init example
cd example
nex check
nex eval
nex run --profile release
nex test
nex test --target web
```

`nex.json` records `"language":"0.30"`. Graph context, edits, archives,
formatting, dependency locks, component builds and API projections select the
project or retained program's actual source version. For a checked cell example,
see [examples/references](../examples/references/README.md).

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
schemas. `public_revision:true` means a valid archival semantic identity;
`ordinary_CLI:true` records ordinary project selection.
The normal test-entry runner accepts this value contract and retains its
rejection of the older private diagnostic envelope.

Reachable source/effects/types determine whether an execution needs a reference
heap. A030 application without references keeps the existing029 ordinary
TypeScript/task generator and reference/native task execution. Merely loading
the030 version does not create a new heap for each continuation atom or select
the boxed representation for reference-free task programs.

Source0.30 task callbacks can declare state when the caller declares it.
Ordinary `eval`, native debug/release applications and HTTP handlers, and
TypeScript exports now use [owned reference-task contexts](reference-tasks.md).
Source executes cooperatively on its heap owner thread; physical IO completion
workers do not receive cells. Native reference tasks select public ABI8; retained
reference-free tasks keep ABI7 and private030 descriptors keep their own cohort.
TypeScript async wire-value exports use public map4; synchronous exports keep
map3. Snapshot/history/archive identities are unchanged.

`parallel_map` in a reference graph still receives `E_CELL_CONCURRENCY`.
[Persistent browser UI state](persistent-ui.md) now retains one application
heap across serialized events. Native [task-provider images](reference-task-providers.md)
support checked static, fixed shared and mixed components. Standalone and
source-backed native applications support [logical debugging](reference-provider-debugging.md)
and [profiling](reference-task-profiling.md). Standalone HTTP servers support
[logical debugging](server-debugging.md#owner-thread-http-tasks-in-030) and
workload profiling of owner-thread tasks. Live reference transfer across
parallel workers remains open. Sequential code-only
native libraries retain their enclosing [host/application context](reference-library-abi.md).
Runtime-embedding reference libraries and Wasm references retain explicit
`E_CELL_TARGET` boundaries. Reference-free entry behavior is preserved.
Device emission can select030's inherited supported
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

For an existing project, first inspect the read-only plan:

```sh
nex migrate --language-version 0.30 --kind plan --json
nex migrate --language-version 0.30 --expected-revision OLD_REVISION --json
```

If the plan reports a builtin-name conflict, review its candidate sources and
pass `--candidate candidate.json` when applying. The apply operation checks the
origin revision and graph namespace again. After successful graph migration,
update the project's language metadata to0.30 and materialize the migrated
source with an explicit export to a fresh directory when needed. Changing only
`nex.json` cannot migrate old HEAD; it produces `E_LANGUAGE_VERSION` instead.
The no-flag migration target remains the compiler fallback; specify0.30 explicitly.
Retained SDKs and old graph rows keep their own identities and capabilities.
Genuine older graphs without the identity extension can be inspected read-only;
apply creates that extension through the existing schema upgrade. Pre0.18
compatibility retains its limited `origin_verified:false` result rather than
claiming a modern versioned origin recheck; the target is still fully checked.

Task acceptance documents retain their independent0.28 protocol version.
New captures index each source program's version in
`inputs/program-languages.json`; replay rechecks that version even after live
source removal. Reference-free task programs inherit029 execution. Capturing a
sequential cell program does not enable cell transfer into concurrent tasks.

## Remaining integration

[Focused0.262 evidence](evidence/references030-0.262.0-2026-11-16.json) records
the versioned/backend matrix, inherited task/device emission, real retained-SDK
history migration and a relocated normal installation. The matching source
files, compiler identities, initial fixture failures and qualification bounds
are retained; this is not a full SDK/platform release receipt.

Ordinary030 CLI authoring, static components, task capture/replay and API source
projection have focused development acceptance. Live read-only cell inspection
has [native debugger coverage](reference-task-debugging.md). Full source and
portable SDK qualification are needed for each supported release platform.
The persistent browser adapter owns its longer-lived context. Per-call exports
keep separate heaps. Nullable
object layouts, class/interface dispatch, mutable arrays, memory visibility,
Java numerics/exception hierarchies and Python dynamic protocols/big integers
remain in [migration readiness](migration-readiness.md). Converters remain
deferred.
