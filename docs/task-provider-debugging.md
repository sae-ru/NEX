# Source-backed native task-provider debugging

Working126/toolchain0.119.0/language0.20 enables this development slice after
actual generated-image debugger and physical-drain/sanitizer preflights. Complete
delivery acceptance remains specific to the matching compiler/resources/platform. Query `nex describe --field task_provider_debugging
--json` and `nex guide --kind task-provider-debug --json` for the actual compiler.
The presence of metadata or this guide is not a live-debugger acceptance result.
The [prototype preflight receipt](evidence/toolchain-0.119.0-task-provider-debug-preflight.json)
pins the tested compiler/source and explicitly excludes final delivery acceptance.

The implemented scope is native macOS/Linux64 source-backed concrete static archives
and fixed startup-linked shared images through `project --kind debug` with
`--adapter lldb` or `--adapter nex-dap`. The selected executable entry declares task.
Ordinary `profile:debug` build/run keeps its existing uninstrumented contract;
logical instrumentation is an explicit debug action. HTTP/foreign tasks, raw DAP,
binary-only providers, arbitrary load/unload and combined debug/profile remain
unsupported. Existing static1/shared2/profile3/source-only debug2 formats retain
their original meaning. Execution ABI3 is still88 bytes, including its existing
profile-site pointer; source syntax, checked effects, canonical graphs and
history-preserving020 migration do not change.

The artifact selector is `project --kind plan|build|package --task-debug` for a
native task application in a debug-profile configuration. Ordinary build/package
without that flag retains the uninstrumented contract. The flag is rejected for
run/test/build-test/profile and non-native/pure/HTTP/foreign roots. Actual scope
validation precedes native tools and cache creation.

## Logical tasks and source values

The debugger observes retained TaskIR activations across checked provider calls,
yields and waits. A task keeps its logical identity while its physical worker may
change. `nex-tasks`, `nex-task-select`, `nex-task-stack`, `nex-task-values`,
`nex-task-next`, `nex-task-in` and `nex-task-out` retain the source-only command
meanings. NEX-DAP exposes the same logical selection, bounded locals and pure
watch evaluation. Continue/step resumes all physical workers so dependencies
can progress. Deadlines continue advancing while the process is stopped.

Only initialized bindings visible at the exact source point are available.
Authority-bearing File/scope/task/channel/effectful-callable values are opaque;
other resource-free locals can still be inspected. Captures are borrowed through
checked DWARF layouts with strict read/size/depth limits. No inferior functions,
callbacks, permission/grant inspection, Value retention or source evaluation in
the inferior is used. Pure watch evaluation runs in the trusted external compiler
against the actual checked component archive. A provider-only concrete generic
uses its component identity rather than a fabricated root graph node.

Synchronous ordinary pure helpers retain ordinary DWARF behavior. They do not
acquire invented logical task frames. A pure-only provider may therefore have
zero retained logical code rows while remaining in the physical/source inventory.
Queued tasks without a first activation have no fabricated target/source frame.
Torn, mutating, retired, stale or exhausted publications are unavailable.

## Separate metadata and image identities

The new debug branch uses provider4, debug catalog1/source-union1, completion7,
linkage4/retained4/request4 and debug3/view2/frame4/expression2 tooling formats.
Runtime catalogABI2 has a200-byte header,32-byte component registry,24-byte
registry refs and16-byte original-code refs. It retains the existing96-byte code,
72-byte point,40-byte binding,128-byte task,80-byte frame and64-byte stop layouts.
There are at most128 registries including root, with global bounds16384 codes,
262144 points,65536 bindings and1048576 visibility entries. Per-component source
bundles are bounded separately from the8MiB host manifest.

Original registry/code/point/binding/string/descriptor tables remain in their
checked EXE/DSO owners. One common runtime owns catalog/marker/publication state.
The reader validates pointer widths/counts/ranges before reading, then checks
actual loaded module paths, SHA256, UUID/build-ID and module-qualified step symbols.
Registry refs and dense code IDs must match the exact checked running closure.
Same-name symbols, a complete-looking substituted unused table or another root's
DSO do not establish ownership. Semantic catalog/source-union hashes differ from
raw serialized file pins and final image hashes; no own-image hash cycle is used.

## Captured and relocated delivery

A `task_debug:true` on an existing native application build check prepares
a noninteractive debug descriptor; it does not launch an inferior or add an
interactive acceptance-check kind. Capture rechecks the source linkage before
tools. Actual provider/catalog/source-union/component bundles, executable/DSOs,
exact symbols, debugger scripts and complete7 bytes are retained after build.

Replay prepares a fresh descriptor for that action's CWD/build key. A separately
relocated launch manifest derives from byte-verified original metadata and
original-to-output mappings; original hashed metadata and source anchors are
never rewritten. An application copy may run independently, while watches/debug
still require the matching trusted compiler and installed LLDB. End-user packages
are not automatically self-debugging, and logical task core capsules remain pending.

## Acceptance boundaries

Actual static and mixed shared images must show provider locals/watch42, next/in/out
through call/yield/return, correct dependency progress, source-deleted delivery,
strict stale/image/source/metadata rejection and preserved cleanup/error semantics.
The permanent suite and a matching installed-SDK phase must retain exact commands,
compiler/resource/image identities and raw LLDB/NEX-DAP exchanges. Runtime private
physical-drain/sanitizer probes have a separate scope and do not substitute for
these live generated-image checks. Full regression, installed SDK31 and platform gates require their own matching
receipts. The seven-case native suite also checks explicit plan/build/package
for a source-only root while inherent source-only debug keeps catalogABI1.
Darwin completion7 pins the root dSYM metadata/DWARF and completion marker;
a package keeps a byte-identical dSYM beside its relocated executable.
Loaded image and symbol paths in the fresh manifest are rederived from raw
metadata and separate relocation mappings; altered owned paths/pins are rejected.
