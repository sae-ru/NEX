# Current source language0.24 (development0.134.0)

Ordinary source/project commands select024. Server task/fs whole-file and opened
File operations are enabled; genuine File owners can cross checked structured
task and source-provider boundaries while retaining their original grants.
Static/fixed-shared providers use ABI5 records8/9/10, static plan3 and shared/
profile/debug plans8/9/10. Completion envelope schemas retain their existing
independent numbering. C FFI/wire/browser and unstructured parallel boundaries
cannot transport File authority. A diagnostic identity is never an IO grant.

Read [the current source-stream contract](task-file-streams.md) and query actual
compiler descriptors for exact formats. Retained023 parser rules and ABI3/4
records/masks31/799 remain explicit historical contracts. Migrate an archived
project and export separately; changing its manifest alone is insufficient.
Full/SAN/installed SDK/platform delivery have separate acceptance evidence.
Versioned notes below preserve their earlier scopes rather than the new default.

# Fixed shared native task providers

Working124 / toolchain0.117 / language0.20 enables candidate concrete task calls
across shared libraries loaded by the OS at process startup. The11-case actual
source suite and separate controlled private image fence pass. Full144 regression,
matching installedSDK29 and platform acceptance remain pending. Check the actual compiler:

```sh
nex describe --field task_shared_providers --json
nex guide --kind task-shared-providers --json
nex project --kind plan --component app --json
```

This is a build contract. Source syntax, effects, realms, canonical source,
revisions, explicit history-preserving migration and task execution ABI3 remain
unchanged. [Static providers](task-providers.md) keep their separate provider1,
plan1 and completion4 contracts. This guide describes the new `shared-fixed`
cohort and provider2 metadata. Passing a focused case does not establish complete
current regression, matching installedSDK29 or platform acceptance.

## Declared source and load closure

The selected executable declares a task entry. Project components retain
checked source and direct dependencies, for example:

```json
{
  "schema": "nex.project-build/1",
  "default_configuration": "debug",
  "configurations": {
    "debug": {"profile": "debug", "task_limits": {"steps": 1000000, "timeout_ms": 5000, "workers": 2}}
  },
  "components": {
    "leaf": {"kind": "shared_library", "root": "leaf", "entry": "leaf/value.nex", "entry_function": "answer"},
    "mid": {"kind": "shared_library", "root": "mid", "entry": "mid/value.nex", "entry_function": "answer", "dependencies": {"leaf": "dynamic"}},
    "app": {"kind": "executable", "root": "app", "entry": "app/main.nex", "dependencies": {"mid": "dynamic"}}
  }
}
```

`mid/value.nex` imports the checked leaf source, and app imports checked mid
source. A concrete task call across an edge requires a selected public provider
entry or export and its exact signature/contract/accessor. An internally
reachable public helper does not become an external task export until explicitly
selected. Pure helpers and immutable resource-free aggregates/results are
supported. Existing checked task/io direct calls can print; callback effect
rules are unchanged. Static dependencies can form a frontier inside a shared
image or the final executable. Source dependencies retain their ordinary meaning.

Each final application gets its own ownership ledger. An application may load
one shared leaf through two dependencies; the loader maps that leaf once. A
static component embedded in both that application and one of its loaded
libraries would create two definitions and is rejected before tools. Two
independent applications may each embed the same static component because they
have separate process load closures. Select a task application component when a
project also contains independent ordinary applications; a pure executable entry
consuming this task cohort remains unsupported.

## One root and one common runtime

Provider images contain emitted code, constants and checked descriptor
accessors. They do not start an application, executor, request control or file
grant. The final executable embeds its own PIC code and static frontier, then
starts one root application request and task executor. There is no separate
application-code shared library. All provider images import one common runtime
image, with source/runtime identities pinned by the build.

Root configured limits and lowered `--nex-task-steps`,
`--nex-task-timeout-ms`, `--nex-task-workers` controls apply through provider
steps and pure helpers. Provider code cannot renew the deadline or establish an
independent budget. Resource failure/cancellation suppresses source admission,
drains lexical scopes and physical operations, and preserves the first selected
fatal error. The normal source task kernel still owns this protocol.

Server task/fs whole-file reads use the root's explicit revocable FileReadGrant.
No grant, File or scope/channel/task authority crosses a source function boundary
between providers. Exporting an unused read function can require file-read code
in the common runtime, while the selected root still has no read requirement or
grant. Component read flags, the common code-support union and the selected
root's `task_application.task_file_reads` are separate facts. Ordinary missing
capability and file/UTF-8 errors retain typed results at the attempted read;
revocation, cancellation and resource failures terminate and drain.

## Checked records and retained outputs

`task_linkage` in a read-only project plan uses
`nex.project-task-linkage/2`: component-local definitions, concrete imports,
exports, mode and dependency-first `load_closure`. Each image records definitions
with their original source component plus static/dynamic frontiers. A static PIC
stage has no final load closure. Planning does not claim actual binary inspection
or execution.

The strict `nex.native-task-provider/2` sidecar has18 fields. It preserves the
full descriptor ABI value `0x4e45585400000003`, size88 and ABI offset40. It
distinguishes `pic-stage`, `shared-image`, and `application`; a PIC stage has
null final owner/image identity. Final records pin the actual image key,
BLAKE3/SHA256, UUID/build ID and common-runtime key/hash. Each definition retains
its source owner, and each export retains the requirements of that owner.
An image-wide read flag must not replace a component's requirement bits.
The checked schemas are
[provider2](../llm/native-shared-task-provider.schema.json) and
[plan2](../llm/project-task-linkage.schema.json).

Completed images use `nex.native-completion/5` and
`nex.native-image-inputs/2`. Ordered inputs bind the library ABI, own provider
record, image inputs, PIC objects, static archive/provider pairs, owned image
closure, each owned provider sidecar and symbols. Paths and counts are bounded;
missing, changed, reordered or escaping inputs invalidate reuse. Static123's
completion4 remains unchanged.

Reviewed task capture pins checked source topology before tools. Actual build
outputs retain `nex.retained-native-task-build/2` maps with original and retained
paths, BLAKE3 hashes and byte counts. Build/compilation/debug/provider metadata
stays byte-identical; recording original provenance does not rewrite hashed
records to relocated names. Source-deleted replay rechecks the captured
architecture and rebuilds with the matching compiler.

Packaging uses the task-specific application-request2 contract. It verifies the
fixed loaded closure and copies raw provider/build/completion provenance.
`application.json` separately relates original image identities to packaged image
paths/output SHA256. Execution of a copied application plus its `images/` closure
does not require checked source, graph or compiler resources. Captured raw
sidecars describe original build identity, rather than claiming the relocated
bytes have an unchanged hash.

## Explicit boundaries

Only macOS/Linux64 debug/release standalone applications and reviewed project
build/run/test/build-test/package workflows are in this slice. Callable values,
including pure factories and nested callable carriers, and File/task/scope/channel
authority are forbidden in public/imported cohort signatures. Imported function
values and binary-only checking remain unsupported. Existing ordinary synchronous
File/callback libraries use their unchanged mode.

Task profiling, logical task debugging across these images, HTTP task handlers,
foreign providers, Windows/other targets, runtime loading/unloading and plugin
lifetime remain pending. OS startup loading is not a general dynamic module API.
Data-only completion parsing does not enable logical task core inspection.
Regular-file source tests establish actual grant/read/result propagation; a
separate controlled private shared-image fence tests physical settlement and
descriptor lifetime. A timer or process termination is not evidence of physical
IO drain.
