# Separate native compilation — toolchain 0.9

Current source language is 0.6. The native compiler now produces an object for each
source module containing functions reachable from the selected entry. It can
reuse those objects across semantic revisions, entry points and source-based or
archived builds. The entire loaded program still passes the normal checker
before cached code can be selected.

```sh
nex build src/main.nex --json
```

Native build responses add `compiled_modules`, `reused_modules` and `compilation`.
The last field names a `nex.compilation/1` report. A warm whole-program cache hit
reports zero compiled modules and all selected units reused. The saved report
describes the last materialization of that artifact; use the command response
for this invocation's counters.

## Invalidation

The cache granularity is one module's reachable function set. A module's own
source contents and checked definitions participate in its input key. Changing
one function therefore recompiles its module. Unrelated modules can be reused;
the current implementation does not cache individual functions independently.
Changing comments or source coordinates also changes the module key so its
DWARF cannot point to a different source version.

For cross-module calls, the consumer records the callee's qualified name,
parameter/result types, declared effects, realm, visibility and test status.
The callee's implementation body is not a consumer input. A body-only edit
recompiles the defining module while a contract edit invalidates consumers whose
emitted assumptions changed. Parameters are positional, so renaming a callee's
parameter does not invalidate unchanged consumers.

Type inputs include the layouts of structures used in signatures, local values,
expressions, generic builtin annotations and external call contracts. This
closure follows fields, lists and results, including recursive record models.
Field names/order and nominal identity matter: reordering same-typed fields can
change native field indexes, constructors and typed JSON descriptors even when
the source consumer text is unchanged. Modules defining only types have dependency
nodes but need no native object.

Input manifests separately record toolchain, semantic, source and runtime ABI
fingerprints, the frozen source path and any C application wrapper. Compiler
build/identity, LLVM, host target, the probed native driver triple/data layout,
profile and relevant SDK environment belong to
the toolchain fingerprint. Matching runtime sources/headers used at the boundary
also participate; optional wire/storage components are included for units using
those capabilities. The whole executable key continues to cover the complete
source bundle, revision, runtime components and linked dependencies.

The selected closure has direct/reverse function and module dependency indexes
in the report. Module dependencies include called function contracts and
referenced layout providers; they are not merely the textual import list.
Effect/type/realm errors are rejected before an old object can hide the change.
Existing `nex.lock.json` enforcement remains in effect; an edited pinned library
must be reviewed and explicitly repinned with `nex lock`.

## Artifacts and consistency

Inside the project's `.nex/build`:

- `source-cache/` holds content-addressed immutable source projections shared
  by builds. Each module's DWARF refers to its exact source contents.
- `native-cache/INPUT_KEY.json` is an atomically published object-cache index.
- `native-objects/CONTENT_KEY/` holds validated module MLIR, LLVM IR and object
  bytes. Readers verify the whole content object before using it. Atomic index
  replacement and content-addressed objects allow independent builds to share
  units without consuming partially published data.
- `BUILD_KEY/units/` retains each selected unit's MLIR/LLVM inputs; named native
  object copies, the executable/archive, `compilation.json`, source bundle,
  metadata, debugger manifest and formatter accompany them.

`program.mlir` is a readable aggregate projection. `program.ll` is a verified
LLVM link of the selected units' IR for inspection/`nex emit --kind llvm`.
Machine code is compiled from separate units, not by compiling that aggregate.
Runtime components retain their own object cache and link only when required.
Native archive and HTTP server output use the same NEX module pipeline.

Object/IR/index corruption forces the affected unit to rebuild. A damaged local
copy or aggregate can be restored from valid shared objects without recompiling
them. Whole-build cache checks cover executable, aggregate IR, compilation/build
metadata, source bundle, selected unit copies, captured NEX sources and debugger
artifacts, including packaged macOS DWARF. Failed unit compilation retains its
intermediate directory in the diagnostic.

Debugging uses the normal `nex debug` session. Its manifest maps original files
to their frozen projections. Keep the build workspace's `source-cache/` along
with the selected artifact and runtime source projections when preserving an
old debugging session. An archived revision can reconstruct missing sources
from its stored source bundle; original live files are not rewritten.

## Validation and current limits

`tests/incremental.py` wraps the actual native compiler to count LLVM compilation
calls and inspect which functions are compiled. It checks body edits, ABI/effect
changes, parameter renames, nested record/JSON layouts, pinned library updates,
archived-source reuse, profiles/compiler/runtime inputs, damaged caches and
concurrent builds with shared units. Native observations are compared with the
interpreter and clean builds; existing TypeScript and runtime suites remain in
the regression set. Reuse counters alone are not treated as proof.

Optimization is currently per unit (`-O0` debug, `-O2` release/profile). Cross-unit
LTO/inlining, function-level object reuse, incremental frontend checking,
remote/distributed caches and deterministic test-result caching remain pending.
Absolute debug source paths make this a local build cache; portable SDK/cache
distribution and additional operating-system verification remain separate work.
These limits do not restrict the broader NEX development objective.
