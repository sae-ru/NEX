# Native compilation and toolchains — toolchain 0.28

Current source language is 0.16. The native compiler produces a separate object
for each reachable concrete function, including lifted closures and generic
specializations. It can
reuse those objects across semantic revisions, entry points and source-based or
archived builds. The entire loaded program still passes the normal checker
before cached code can be selected.

Toolchain 0.26 validates native entry signatures, realms, test markers and
generic concreteness independently of IR emission. Warm cache hits therefore
do not regenerate the complete MLIR program just to check the entry. Missing
objects still pass normal MLIR/LLVM verification. One operation tree per
reachable concrete function supplies both debugger sites and the immutable
site index shared by aggregate/unit emitters; snapshots preserve the checked
AST identities. This is build-work reuse, not incremental frontend checking.

```sh
nex build src/main.nex --json
```

Native build responses include `compiled_functions`, `reused_functions`,
`compiled_modules`, `reused_modules` and `compilation`.
The last field names a `nex.compilation/1` report. A warm whole-program cache hit
reports zero compiled functions and all selected functions reused. Module counts
group these objects: a module is compiled when at least one selected function
was compiled, and reused when all its selected functions were reused. A partially
rebuilt module therefore contributes only to `compiled_modules`. The saved report
describes the last materialization of that artifact; use the command response
for this invocation's counters.

The report's `granularity` is `function`. Each `units` entry has a qualified
function `identity`, its source `unit`/`module`, and a singleton `functions`
list. Consumers must inspect `granularity` and use `identity` as the object
identity; a source `unit` may contain many objects. Older module reports retain
their original `granularity: module`. Lifted closure and specialized generic
names remain derived metadata.

## Native targets and SDKs

Toolchain 0.27 also selects compiler, archive/debug tools and host dependencies
from a relative installed-SDK descriptor when present. Explicit toolchain
manifests can override `archiver` and `debug_packager`; their bytes participate
in native cache keys and read-only toolchain fingerprints. A broken bundle
descriptor fails with E_SDK rather than selecting build-machine defaults.
`doctor` reports the effective paths, including `NEX_CLANG` overrides.
See [SDK bundling and acceptance](sdk.md) for layout, provenance and prerequisites.

`--target native` selects the host ABI. `--target TRIPLE` selects a concrete
64-bit native ABI. On a macOS host, macOS arm64 and x86_64 builds are configured:

```sh
nex build src/main.nex --target x86_64-apple-macosx13.0 --profile release --json
```

The driver is probed with the same target/SDK arguments used for every NEX IR
object, C++ runtime object, bridge and final link. The probed LLVM data layout,
architecture, OS/environment and explicit `macosx` deployment version must match.
Darwin kernel triples are normalized by Clang and do not specify a macOS release.
Unsupported OS/architecture combinations fail with E_TARGET. This configures
macOS cross-compilation. Toolchain 0.61 additionally builds debug/release iOS
static archives with an explicit matching Xcode sysroot; read [the iOS guide](ios.md).
Toolchain0.64 additionally supports explicit GNU/UCRT Windows core artifacts;
read [the Windows guide](windows.md). Linux/Android cross-targets and iOS
application delivery remain pending.

`--toolchain FILE` supplies a `nex.toolchain/1` JSON configuration; its schema is
`llm/toolchain.schema.json`. It also works with `--target server` to select HTTP
output and its native ABI independently:

```json
{
  "schema": "nex.toolchain/1",
  "target": "x86_64-apple-macosx13.0",
  "compiler": "/path/to/llvm/bin/clang++",
  "sysroot": "/path/to/MacOSX.sdk",
  "sqlite": {"include": "dependencies/include", "library": "dependencies/lib/libsqlite3.dylib"},
  "openssl": {"include": "dependencies/include", "ssl": "dependencies/lib/libssl.dylib", "crypto": "dependencies/lib/libcrypto.dylib"}
}
```

An optional `linker` selects a native linker executable. Linux defaults to the matching LLVM `ld.lld`; the final symlink name is preserved for driver dispatch. Selected linker bytes participate in fingerprints (`nex.toolchain-snapshot/2`) and build/cache identity. The Linux guide covers the verified ELF DWARF path.

Normalized manifests preserve the final executable name for compiler, linker,
archiver and debug packager aliases, and canonicalize their parent directories.
Saving an inspected manifest and inspecting it again keeps the same fingerprint.
Keep a selected shared library and its transitive dependency closure together
when its RUNPATH uses `$ORIGIN`.

Ordinary host/macOS configurations require only `schema` and `target`. Windows
core additionally requires explicit compiler/linker/archiver/sysroot and its
`windows` runtime/notices object. Omit unused dependencies. Each supplied
dependency object must include all its fields. Files are limited to 64 KiB;
unknown keys and nonexistent paths are rejected. Relative paths resolve against
the configuration directory. A supplied compiler path precedes `NEX_CLANG`;
otherwise the existing compiler selection applies. Without `sysroot`, Clang uses
its configured SDK/environment. A simultaneous triple in `--target` must match
the normalized manifest triple.

For another architecture, SQLite and OpenSSL must come from this explicit
configuration when required. E_TARGET_LIBRARY prevents host dependency fallback.
The macOS SDK SQLite headers and `.tbd` stub can be selected for storage builds;
OpenSSL needs a separately supplied target installation. The linker checks linked
dependency compatibility. Packaging dependent dylibs, checking their deployment
requirements, signing and application distribution remain separate work.

Build JSON and `build.json` report `target`, `compiler_target` and
`host_compatible`. The last means the selected architecture/OS ABI matches this
host; it does not certify deployment on every OS release. Native and runtime
caches include effective toolchain arguments, target, data layout, explicit SDK
settings identity and dependency inputs. `debug.json` records the target too.
Cache hits retain the same target metadata.

`build` and `emit --kind llvm` can produce foreign artifacts, including archives
and instrumented profile builds. `run`, `test`, `debug` and `profile` execute
locally and reject foreign architectures with E_TARGET_RUN. No emulator is
configured. An interpreter result cannot certify foreign native execution;
run the output/tests on a matching machine. Task contracts can pin toolchain
fingerprints and capture/replay foreign build checks through a current trusted
catalog. Foreign execution checks remain unsupported; see the task guide.

`nex toolchain FILE --json` reports a normalized configuration and a read-only
fingerprint for task acceptance. It hashes the driver and configured dependency
inputs/SDK settings without invoking the compiler. See `nex guide --kind task`
for the exact fingerprint scope and current-catalog requirement on replay.

macOS x86_64 artifacts, LLVM/object/archive/dSYM architecture, cache isolation and
archived builds are checked on the ARM64 development host. Intel execution and
live Intel LLDB/DAP are unverified here because Rosetta is unavailable.

## Invalidation

The cache granularity is one concrete function. Its checked definition, exact
source declaration and emitted line/column positions participate in its key.
Changing a function's body does not invalidate unrelated functions in the same
file. A preceding edit that changes only absolute byte offsets can preserve
reuse; moving a function to another line/column invalidates it. Captured binding
coordinates also participate. Comments inside a declaration are source inputs;
comments elsewhere matter when they move emitted coordinates. The complete
program is still parsed, specialized and checked before selecting objects.

For calls within or across modules, the consumer records the callee's qualified name,
parameter/result types, declared effects, realm, visibility and test status.
The callee's implementation body is not a consumer input. A body-only edit
recompiles the defining function while a contract edit invalidates consumers whose
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
fingerprints, a stable virtual DWARF path and any C application wrapper. Compiler
build/identity, LLVM, selected target, the probed native driver triple/data layout,
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

- `source-cache/` holds complete content-addressed immutable source projections
  shared by builds. `source-anchors/` names stable virtual DWARF paths; it is not
  a mutable source copy. Each debug manifest maps those paths to that build's
  exact complete files. `nex-load-debug` sets LLDB's source-map property through
  its API, and DAP launch configurations provide the same `sourceMap` pairs.
  Standalone debugger integrations must apply these mappings. Both old and new
  sessions retain their own complete sources after working files change/disappear.
- `native-cache/INPUT_KEY.json` is an atomically published object-cache index.
- `native-objects/CONTENT_KEY/` holds validated function MLIR, LLVM IR and object
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
Native archive and HTTP server output use the same NEX function pipeline.
Profile reports map recorded virtual paths back to the selected frozen sources;
their function content/node attribution still must match the selected graph.

Object/IR/index corruption forces the affected function to rebuild. A damaged local
copy or aggregate can be restored from valid shared objects without recompiling
them. Whole-build cache checks cover executable, aggregate IR, compilation/build
metadata, source bundle, selected unit copies, captured NEX sources and debugger
artifacts, including packaged macOS DWARF. Failed unit compilation retains its
intermediate directory in the diagnostic.

Debugging uses the normal `nex debug` session. Its manifest maps original files
to their frozen projections. Keep the build workspace's `source-cache/` along
with the selected artifact and runtime source projections when preserving an
old debugging session, and apply that session's `source_map`. An archived revision can reconstruct missing sources
from its stored source bundle; original live files are not rewritten.

## Validation and current limits

`tests/incremental.py` wraps the actual native compiler to count LLVM compilation
calls and inspect which functions are compiled. It checks body edits, ABI/effect
changes, parameter renames, nested record/JSON layouts, pinned library updates,
archived-source reuse, profiles/compiler/runtime inputs, damaged caches and
concurrent builds with shared units. Same-file tests count actual compiler calls,
cover body/contract/coordinate edits and retained generic/closure objects. With
`--live`, `LiveFunctionCache` tests both actual LLDB and DAP over reused objects
from two revisions after deleting their working source. Native observations are compared with the
interpreter and clean builds; existing TypeScript and runtime suites remain in
the regression set. Reuse counters alone are not treated as proof.

Optimization is currently per function (`-O0` debug, `-O2` release/profile). A cold
build invokes the native driver for each function. Cross-function
LTO/inlining, incremental frontend checking,
remote/distributed caches and deterministic test-result caching remain pending.
Absolute debug source paths make this a local build cache; portable SDK/cache
distribution and additional operating-system verification remain separate work.
These limits do not restrict the broader NEX development objective.

The source remapping uses LLDB's documented
[source-map setting](https://lldb.llvm.org/use/settings.html#target-source-map)
and the DAP launch
[sourceMap property](https://lldb.llvm.org/use/lldbdap.html#common-configurations).
The formatter assigns the setting through
[SBDebugger.SetInternalVariable](https://lldb.llvm.org/python_api/lldb.SBDebugger.html#lldb.SBDebugger.SetInternalVariable),
so mapped filenames remain data rather than debugger commands.

Generic source bodies specialize into the declaring module. A body edit recompiles the provider while unchanged consumed signatures permit caller reuse. Concrete nominal layouts and type arguments, including phantom arguments, participate in transitive type dependencies. Source projections still refresh debugger locations, and source revision identity excludes redundant derived instances.

For macOS storage/server executables, selected SQLite/OpenSSL library directories
are passed as separate runtime-search-path arguments, allowing `@rpath` dylib
install names while preserving literal commas, percent signs and Unicode.
Native archives leave dependency resolution to the final host link.

Toolchain 0.28 also records selected Linux library directories as ELF runtime
search paths. The integration test executes SQLite storage and checks the actual
loader resolution in a comma/Unicode/percent directory. ELF search-list colons
are rejected explicitly. Linux SDK assembly and clean archive acceptance are
described in the SDK and Linux guides.

## Checked integer lowering (0.47)

The native backend emits signed overflow intrinsics for `i64` addition,
subtraction, multiplication and negation. Division checks zero and `MIN / -1`
before executing signed division. Remainder checks zero and selects a defined
divisor for `MIN % -1`, which returns zero. Successful arithmetic stays in SSA;
only the failure edge calls the existing checked runtime helper with its static
operation descriptor. Assertions also branch directly on their already evaluated
boolean, calling the existing failure helper only when false. Arguments still evaluate once, left to right. Floating
arithmetic keeps its existing finite-value and caller-environment handling.

Source syntax, canonical hashes, language 0.15, graph identity policy and C value
ABI 1 are unchanged. Compiler/build identities invalidate old function objects.
The public native diagnostic format remains the 0.46 format; archived reports
still require a matching compiler/build manifest.

```sh
nex test examples/native-arithmetic.nex --json
nex test examples/native-arithmetic.nex --target web --json
nex build examples/native-arithmetic.nex --profile release --json
```

The isolated acceptance cases compare more than a thousand valid boundary and
seeded random operations across native/interpreter/TypeScript execution. Every
integer failure kind checks both error code and operation ID in debug/release;
loops and nested effectful operands check remainder and evaluation order.
Current full platform/SDK scope is recorded in `STATUS.md`.

An initial local ARM64 experiment interleaved eleven warm process runs of the
same 20-million-iteration program and exact 0.45/0.46/0.47 runtime snapshots.
Median times were 91.6/105.9/71.9 ms. A separate 300-expression constant workload
produced 223,808/391,168/259,040-byte executables with equal output. These are
observations on a shared development host during validation, not general
performance guarantees. Compiler/source hashes and raw observations are retained
in the development evidence; broader benchmarks remain pending.

## Application ownership on checked failures

Toolchain0.73 wraps the generated entry with a compiler-private C++ ownership
boundary. A checked failure unwinds host temporaries and releases live managed
values from every NEX caller/callee scope before returning process code70.
Normal returns retain the zero-live-value check and original process status.
Frozen operation diagnostics and final build identity remain attached. This
boundary adds no request scope, request budget, implicit file grant or source
concurrency. Trusted embedding hosts still use explicit RequestScope for calls
that require fault containment and request cancellation. Forced termination
may skip cleanup and profile output. Language0.16 and graph histories need no
migration; native objects use the new matching private runtime/compiler ABI.
Fallible allocation/profiling/request registration completes before a handle is
committed to its owner; a failed constructor cannot leave a dangling owner entry.
