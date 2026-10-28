# Public025 provider integration candidate

Ordinary025 providers use ABI6 and records11/12/13; project plans use static4
or shared/profile/debug11/12/13. Pure helpers have real continuations and logical
frames. Source errors and File cleanup cross checked static/shared/mixed images.
Read [the025 provider contract](source-exception-providers.md) and query the actual
compiler. Complete regression, SDK/platform acceptance and unfinished interfaces
remain open. Notes below retain their stated historical scope.

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

# Concrete static task providers

Toolchain0.116/language0.20 enables this candidate native macOS/Linux64 slice.
Query `nex describe --field task_providers --json` for actual enablement.
The preserved123b checkpoint has explicit composite141 regression, matching
installedSDK28/523 commands and four scoped Linux groups/17 cases; see
[exact evidence](evidence/toolchain-0.116.0-task-providers.json). Current124
shared integration and its full/SDK29/platform gates are separate.

Use an existing `nex.build.json` static dependency with available checked source.
The provider is a real code-only archive. Its selected concrete public task
functions are called through immutable descriptor accessors; their bodies are
absent from the consumer's machine definitions. The application owns one runtime,
root request, executor, task limits and file grant. A provider does not start a
second executor or renew a budget/deadline. Execution ABI3 remains the same
88-byte descriptor, with its ABI word at offset40. This is compiler-private
transport under one exact toolchain/runtime cohort, not a stable plugin ABI.

An executable entry in the selected task ABI cohort must itself declare task.
Pure helpers and pure providers are supported, but a pure application root
consuming a task cohort is rejected before tools. Select the task application
component explicitly when the project also contains independent ordinary
applications; this slice does not accept every mixed-root selection. Ordinary
source-only/synchronous archive projects keep their existing mode and File/
callback interfaces.

```json
{
  "schema": "nex.project-build/1",
  "default_configuration": "debug",
  "configurations": {
    "debug": {"profile": "debug", "task_limits": {"steps": 1000000, "timeout_ms": 5000, "workers": 2}}
  },
  "components": {
    "core": {"kind": "static_library", "root": "core", "entry": "core/value.nex", "entry_function": "answer"},
    "app": {"kind": "executable", "root": "app", "entry": "app/main.nex", "dependencies": {"core": "static"}}
  }
}
```

```nex
// core/value.nex
module core;
pub fn answer(value:i64)->i64 !{task}{task_yield();return value+1;}
```

```nex
// app/main.nex
module app;
import "../core/value.nex" as core;
fn main()->unit !{task,io}{print(core::answer(41));}
```

Use `nex project --kind plan --component app --json`, then
`--kind build|run|test|build-test|package`. Debug/release compilation modes are
accepted; a debug compilation mode does not enable logical task inspection.
Keep `nex.json` at language0.20. This build arrangement adds no source syntax,
canonical field or language migration; genuine archived018/019 retain their
own rules and the existing explicit migration policy.

`entry_function` and optional `exports` choose exact concrete roots. A task
export accepts and returns only immutable resource-free values: checked scalars,
strings/bytes, lists, records, enums and results. Nested File, task/scope/channel
authority, every callable type and nonempty exported capture environments are
rejected. Existing direct source-checked `io,task` functions may print. Existing
server functions declaring task and fs may read whole files. Neither effect
creates a new grant. Source callback rules remain unchanged: io/db/ffi callbacks
are not newly accepted by `with_tasks` or `task_spawn`.

Direct calls to pure helpers across the same archive cohort use their existing
synchronous interface, with the same recursive resource-free signature
restriction in this task cohort: pure factories cannot return a callable or
hide one in a record/list/result, and pure callbacks cannot cross as arguments.
Imported provider functions cannot be taken as function
values, passed as task callbacks or hidden in aggregates/captures. A local lambda
may call the imported function directly. Missing concrete task specializations
reject; the compiler must not silently emit a missing provider body in the
consumer. Existing synchronous archive File/callback behavior and explicitly
reported pure generic consumer instantiations retain their old path.

Every selected machine definition has one physical component owner. A static
provider chain can call another checked provider. Two independent archives
source-importing the same standard/configured helper would both define its
machine body; this slice rejects that duplicate ownership before native tools.
Move a common helper behind one explicit provider edge. Direct source imports
still require the declared direct architecture edge. Private/missing/duplicate
exports and incompatible source contracts fail before artifact publication.

Provider-only `file_read_text`/`file_read_bytes` use the root-captured
`FileReadGrant` and the existing bounded raw adapter. No provider grant, worker
TLS lookup or authority value crosses the archive boundary. The selected
entry's checked transitive reachability determines root read requirements; an
uncalled read export does not expand them. Missing authority remains a typed
CAPABILITY result at the attempted read. Ordinary file errors, strict UTF-8,
left-to-right arguments, `?`, fatal priority and physical cancellation drain keep
their existing [file-read contract](task-file-reads.md). Static mappings remain
loaded until process exit; this is no unload or hot-reload mechanism.

The read-only plan's `task_linkage` object distinguishes local `definitions`,
checked `imports` (`task-code/3` or `sync/1`) and public task `exports`.
`nex.project-static-task-linkage/1` is captured and compared to fresh checked
source during replay. The completed `task-provider.json` uses
`nex.native-task-provider/1`: exact compiler/language/cohort, component,
descriptor layout, local definitions, checked export signatures/accessors and
requirement bits. Requirements describe code; they never grant file authority.
The schemas are `llm/project-static-task-linkage.schema.json` and
`llm/native-task-provider.schema.json`. JSON shape alone is not source, binary
or authority validation.

Completion4 pins the original archive and sidecar inputs and preserves their
content hashes. Reviewed project task receipts retain the completed native
build under `retained_build` with a bounded original-to-retained file map;
hashed build/debug/completion metadata is not rewritten. Replay requires the
matching captured compiler/resources and checked source, rederives ownership
and rebuilds; a previous receipt or a sidecar alone is not permission to execute
an arbitrary binary-only provider. Packaging retains the completed standalone
application and its normal provenance/notices.

This static cohort does not enable shared task providers; the separate fixed
shared-image mode is described below. Binary-only checking, arbitrary external
providers, imported callable transport, exported authority, task profiling or
logical debugging across providers, task HTTP/foreign hosting, unload, other
native targets and broader asynchronous IO remain unsupported. Runtime kernel
drain tests and actual regular-file provider reads have different evidence
scopes; a process timeout is not a proof of physical IO retirement.

## Separate fixed shared-image mode

Toolchain0.117 integrates a distinct `shared-fixed` cohort described in
[task-shared-providers.md](task-shared-providers.md). Query
`task_shared_providers` for its actual enablement. This static descriptor keeps
`dynamic_linkage:false`: provider1/plan1/completion4 are not reinterpreted as
provider2/plan2/completion5. Existing synchronous File/callback archives remain
in their original mode.
