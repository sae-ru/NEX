# Checked project architecture and builds

Toolchain0.116 adds candidate [concrete static task providers](task-providers.md)
under existing checked static edges. Source and concrete resource-free export
contracts remain required; archives contain real provider definitions and
descriptor accessors. The root alone owns runtime/limits/file authority. This
does not enable dynamic task providers, callable/authority transport or task
profiling/logical debugging across provider graphs. Query `task_providers` for
the actual compiler's enablement and pending acceptance scopes.

## Project actions

Toolchain0.78 adds [acceptance tasks and captured replay](project-tasks.md).
`project --kind build-test --symbol TEST` compiles one native owned test under
the declared binary architecture without executing it. Its result exposes the
actual scope, canonical test hash, final artifact and dependencies so a task
parent can supervise execution directly. `architecture_hash` in a checked plan
is the canonical build-description hash reviewed by project task contracts.

```sh
nex project --kind run --component app --configuration debug --json
nex project --kind test --configuration debug --json
nex project --kind test --component app --symbol app::checks --json
nex project --kind debug --component app --adapter nex-dap --json
nex project --kind profile --component app --configuration measured --profile-output profile.json --json
nex project --kind run --component browser -- --port 5173 --strictPort
```

`measured` must name a configuration with `"profile":"profile"`. Actions preserve
the selected configuration and actual source/static/dynamic edges. Run/debug/profile
require one application; select it explicitly when more than one exists. Native
execution requires the compiler host ABI. Validation of the architecture and
selected entry precedes build tools and execution. No graph Store is opened.

Run streams the selected native application/server, or previews the completed
browser distribution with locked Vite and a loopback default. Arguments after
`--` are application/preview arguments. `--json` captures bounded stdout/stderr
and process status; server/web capture requires an explicit `--timeout 1..3600`.
Timeout returns124, output exhaustion125, and interruption preserves its signal.
Forced termination cannot promise normal language cleanup. The preview is a
development host; its execution does not establish browser UI behavior.

Tests select owned `test fn` definitions once per selected component, including
dependency components. `--symbol` selects one unique qualified/local test name.
Every native test is preflighted as a private executable entry under the declared
dependencies, consumes actual archives/images and retains its test build plan.
Client/web tests use the reachable TypeScript projection. Pure tests additionally
compare interpreter observations; pure shared tests also compare TypeScript; effectful tests execute once in their selected
backend, preserving explicit runtime capabilities. A failed assertion remains a
failed test even when both backends reject it. At most256 tests are selected. Each returned row is bounded to32KiB. Larger observations retain a full private result file at `report`; the response includes UTF-8-safe output prefixes and byte counts.
Full UI/API workloads retain separate validation. Project package task checks
and workload profile captures/replay are supported; see project-tasks.md.

Debug selects native executable or server components (server support0.85).
Profile selects native executables; toolchain0.82 also supports
server profile with an explicit bounded [workload](server-workload.md) and a
profile configuration. Debug emits the
same `nex.debug-session/1` descriptor as a source command, nested under
`observation`; use its exact adapter command, launch program, cwd and source map.
`--adapter lldb|dap|nex-dap` chooses the frontend; an interactive LLDB run is
available without `--json`. Shared provider frames use the captured image UUIDs.
Profile requires an instrumented configuration and reports actual final-image
identity and reachable provider functions. `--profile-output` selects its detailed
report, while `--output` saves the complete project action JSON.

Project diagnostics and measured functions use content hashes and source sites;
persistent graph IDs are null with `identity_scope:"captured_project"`.
`llm/project-action.schema.json` describes action/test envelopes, while existing
debug/profile/native-diagnostic reports retain their stated contracts. Explicit
`--foreign HOST.json` grants are checked before execution and around commands;
receipts and environment variables do not grant foreign authority. Browser
preview accepts no foreign catalogue. Project foreign packaging and captured
workload profile tasks are supported. Automatic workload debugger/task replay
and dedicated task editor commands remain pending. See server-debugging.md
for actual worker frames, runtime inputs and preserved request deadlines.

Toolchain0.71 adds `nex project`. This is external build metadata, separate from
the existing source/language/library manifest `nex.json` (`nex.project/1`). It
does not change language0.16, source canonical identities or existing commands.
Keep the source manifest beside `nex.build.json`; existing projects opt in by
adding the latter file. No implicit project-schema or graph migration occurs.

```sh
nex project --kind plan --json
nex project --kind build --configuration release --json
nex project --kind build --component app --configuration release --json
nex project /path/to/project/nex.build.json --kind plan --json
```

`--component` and `--configuration` belong to `project`, not ordinary file
commands. For plan/build/package/test, omitting the component selects all components. Run/debug/profile infer exactly one application or require `--component`. A selected component
includes its declared transitive dependency closure. The default kind is `plan`.
The optional positional argument is a directory or build-description file;
without it NEX uses `nex.build.json` in the enclosing source project.

## Build description

```json
{
  "schema": "nex.project-build/1",
  "default_configuration": "debug",
  "configurations": {
    "debug": {"profile": "debug", "target": "native"},
    "release": {"profile": "release", "target": "native"}
  },
  "components": {
    "core": {"kind": "source", "root": "core", "entry": "core/value.nex"},
    "app": {
      "kind": "executable", "root": "app", "entry": "app/main.nex",
      "dependencies": {"core": "source"}
    }
  }
}
```

The authoring schema is `llm/project-build.schema.json`. Names are ASCII
identifiers of at most64 bytes. Unknown fields, unsupported artifact/linkage
requests and malformed JSON are rejected rather than ignored. Limits are256KiB
per description,128 components,32 configurations,64MiB across selected loaded
source closures and8MiB for a plan before its hash is added. Filesystem and
source checks supplement JSON Schema; schema validation alone cannot prove them.

Roots, entries and toolchain-description paths are normalized relative paths
inside the physical project. Roots must be existing, disjoint directories,
including after symlink resolution. Each entry is a `.nex` file inside its root.
Every loaded project source must have one component owner. Ordinary external
configured packages and the installed standard library keep their existing
library boundaries. A package alias pointing into a component still belongs to
that component and cannot bypass architecture checks.

For each loaded import crossing component roots, the importing component must
declare that **direct** dependency. A transitive dependency does not authorize a
direct import. Source dependencies may target `source`, `static_library` or `shared_library` components;
applications/servers/web components cannot serve as libraries. Dependency cycles,
unknown names and overlapping roots are rejected even outside the selected
closure. Only selected source closures are parsed/checked; an unrelated
unselected source file is not an implicit build input. Existing `pub`, type,
effect, realm, import-containment and dependency-lock checks still apply.

## Artifact kinds and dependency linkage

| Kind | Result | Entry contract |
| --- | --- | --- |
| `source` | Checked reusable source; no separate artifact | Source module |
| `executable` | Native executable | `entry_function`, default `main` |
| `static_library` | Native GNU archive, `libnex.a` | Required `entry_function`; current trusted runtime ABI |
| `shared_library` | macOS dylib or Linux shared object (candidate0.74) | Required `entry_function`; same private runtime ABI |
| `server` | Native HTTP server | `entry_function`, default `handle`; existing HTTP contract |
| `web` | TypeScript/React/Vite application and static assets | Existing initial/update/view/title contract |

A `"source"` edge compiles the reachable checked dependency source into its
consumer. A `"static"` edge requires a `static_library` provider and a native
consumer (executable, server or another static library). It consumes the actual
archive and excludes matching definitions from consumer compilation. Source/web
components cannot consume native binaries. Dependencies are built before consumers;
the linker receives archives in caller-before-provider order.

```json
"math": {
  "kind": "static_library", "root": "math", "entry": "math/value.nex",
  "entry_function": "calculate", "exports": ["make", "roundtrip"]
},
"app": {
  "kind": "executable", "root": "app", "entry": "app/main.nex",
  "dependencies": {"math": "static"}
}
```

`entry_function` and optional `exports` select the union of concrete reachable
function closures. Extra roots must be public concrete functions owned by the
library component. Private helpers stay private to the source checker. Importing
an ordinary public function outside that compiled closure rejects with
`E_PROJECT_EXPORT`; add a concrete export instead of silently compiling its body
in the consumer. Export roots do not bypass types, effects, realms or locks.

A provider consumed through a static edge emits a **code-only archive**. It
contains NEX function objects, with unresolved runtime/dependency calls. The
final executable supplies one runtime for the whole linked closure. Heap values,
closures, files and cleanup keep their existing ownership rules; there is no
second resource registry or cross-runtime handle conversion. Such an archive
is not independently linkable by a bare C++ host without its matching runtime
and transitive archives. An unconsumed legacy archive retains its runtime-bearing
host-library behavior. `code_only_library` in the plan distinguishes them.

Sources remain required for checking; this is not a binary-only package manager.
The exact compiler build, native compiler/toolchain/target/profile and runtime
core form a private ABI hash. Checked concrete function bodies, interfaces,
referenced type layouts and callable bridges must agree with the consumer's
context. A module name resolving to different physical sources in a linked
closure rejects with `E_PROJECT_ABI`. Native archives are trusted executable
inputs, not a sandboxed format or stable cross-version C ABI.

A new generic specialization absent from the provider is instantiated in the
consumer, including its missing helper closure. The plan explicitly reports
`consumer_instantiations`. This does not authorize a direct ordinary call to an
unexported binary function. Existing provider specializations still require
matching checked contracts; source-level safety checks remain identical.

Build results retain `library-abi.json` beside each artifact and actual
`static_libraries` (path, byte hash, ABI, contracts) in `compilation.json`.
Archives are captured, hash-checked and copied into the consumer's private
build directory. Their bytes and contracts enter its build/cache identity;
changed/corrupt cached outputs are rebuilt. This validates NEX link inputs,
not all operating-system dynamic dependencies.

The final executable's frozen source map covers archive code as well as its
locally compiled functions, including nested imports through package aliases.
Use the complete projection path from its `debug.json` when placing a library
source breakpoint. A matching captured LLDB formatter can inspect the same
locals and pure watches after original source deletion; keep the retained build
workspace or export a checked core capsule. Candidate0.77 project actions use these actual artifacts for native run/test/debug/profile. Project task/replay integration preserves these binary edges; see project-tasks.md.

Retained builds declare `nex.native-completion/2` and an ordered bounded
`completion_inputs` list: the ABI record, then captured dependency archives.
Build completion and core inspection bind these bytes. Core capsules retain
and validate the same additional files when moving a build. This is a native
artifact format extension, not a source-language migration. Historical
completion records without these fields keep their six-file binding contract.

## Shared native images (candidate0.74)

A `"dynamic"` edge requires a `shared_library` provider and a native consumer.
The selected shared-image domain is built as PIC under one target, profile and
private compiler/runtime ABI. Native compiler, archiver, linker, debug packager
and selected dependency bytes participate in its toolchain fingerprint. Inputs
are checked again before/after tools; a changed fingerprint rejects the build.
macOS and Linux are supported targets for this build path; Windows DLL output
and iOS shared images remain pending.

```json
"core": {
  "kind": "shared_library", "root": "core", "entry": "core/value.nex",
  "entry_function": "calculate"
},
"app": {
  "kind": "executable", "root": "app", "entry": "app/main.nex",
  "dependencies": {"core": "dynamic"}
}
```

The compiler stages actual NEX function archives, then links each shared image
and the application without recompiling provider source. A static dependency
frontier is absorbed into its owning image; a dynamic edge links a separate
image. Generic specializations absent from a provider remain explicit consumer
instantiations. One common runtime supplies managed values, file resources,
profiling and cleanup across the whole shared-image domain. Standalone programs
outside that domain retain their ordinary runtime link.

Shared images have content-keyed basenames and relative loader paths. Each final
artifact captures its complete first-party image closure in `images/`, including
the common runtime and native symbols. Its metadata records hashes, SHA-256 and
UUID/build IDs. `compilation.json` distinguishes actual captured static link
inputs from the earlier staging binary inputs. The final executable, rather
than a staging archive, owns application/profile identity. Unrelated application
body edits do not force unchanged providers or runtime to relink.

These images use `nex.native-completion/3`: typed ABI/link-input/object records,
then ordered static archives, sorted owned images and sorted owned symbol files.
The bounded relative path inventory rejects traversal, arbitrary libraries,
duplicates and reordered records. Earlier completion/2 and legacy six-file
records remain readable. This changes native artifacts, not source syntax or
language history.

Build output is not a deployment package. Keep the full `images/` directory
beside its executable; external system dependencies retain their platform/notice
requirements.
Windows DLLs, project package task checks and dedicated editor commands remain pending.
Do not pass a project app through an ordinary source command expecting the
declared binary architecture to survive that independent compilation.

Toolchain0.75 adds manual LLDB frames and read-only core/capsule workflows for
these images; see [core debugging](core-debugging.md). The final app manifest
covers reachable provider code and binds selected images by bytes and UUID.
Explicit export retains the complete image/symbol inventory for matching-host
reads after original source/image deletion. Candidate0.77 emits project DAP descriptors for native applications; dedicated editor commands and capsules with external non-system dependencies remain pending.

The selected configuration supplies `profile` (`debug`, `profile`, `release`),
native `target` (default `native`) and optional relative `toolchain` description.
Component kind selects web/server output; target selects a native CPU/OS ABI.
An explicit nonhost server ABI needs a matching native toolchain. Browser
artifacts use their browser adapter, not that native CPU ABI. Existing native
target restrictions remain enforced during actual builds. A successful plan
does not prove that a cross compiler can link or execute the output.

## Planning and execution

`nex.project-plan/1` records the build-description and source-project hashes,
configuration, dependency-first component order, exact source hashes/import
owners, semantic revisions, source-bundle hashes and selected native toolchain
fingerprints or web projection hashes. `plan_hash` hashes compact canonical NEX
JSON of the complete plan before that field is inserted. Physical paths and the
compiler identity participate; this is not a path-independent package identity.

Planning opens no graph Store, invokes no external compiler/package tool,
executes no program and creates no build cache. It checks source, entry/web
contracts, coherent captured source text, project metadata and dependency locks.
It does not claim an atomic filesystem snapshot against arbitrary concurrent
changes. `--output FILE` explicitly saves the command result when requested.

Builds consume the captured checked Programs. Native toolchain fingerprints
are checked again before each native build. Native and web backends retain their
normal caching, source captures, notices and verification. The default cache is
`.nex/build`; `--build-directory DIRECTORY` overrides it. The command returns
`nex.project-build-result/1` with the plan and actual artifact paths/metadata.
It does not execute or deploy applications or synchronize graph HEAD. Use the
normal source check/context/graph workflow when a persistent semantic revision
is needed. Earlier completed cache artifacts can remain if a later build tool
fails; a multi-artifact build is not a filesystem transaction.

An executable is not a fully static executable. System/runtime libraries can
remain dynamic. The plan/result explicitly leave binary dependency inspection
unproven. Windows DLL output/consumption, binary-only packages, a stable
cross-version export ABI, full-static policies and resolved operating-system
binary dependency reports remain pending. Unsupported linkage/kinds fail with
`E_PROJECT_CAPABILITY`.

General source concurrency, GPU kernels and NPU model adapters also remain
pending. HTTP workers and client/server/shared realms are not a source task API.
Separate [CIX P1 hardware checks](cix-p1.md) must not be advertised as completed
NEX accelerator integration.

Run the complete checked archive example from `examples/native-libraries`:

```sh
nex project --kind plan --json
nex project --kind build --configuration release --json
```

Execute the app artifact reported by the build. It prints `22` and `NEX 🧠`;
the consumer compilation lists its archive instead of recompiling math functions.

## Project packages (candidate0.76)

```sh
nex project --kind package --configuration release --directory /new/deployment --json
nex project --kind package --component app --configuration debug --directory /new/app --json
```

The command builds the same checked architecture/configuration and consumes its
actual artifacts. Native executable/server components become `apps/NAME/bin/app`
with application manifests, required shared images/dependencies and complete
notices. Web components become `web/NAME/` with Vite dist, maps and runtime notices.
Libraries enter their consumers; they are not standalone deployment entries. A
selection containing only libraries is rejected before invoking build tools.
The configuration keeps its declared debug/release/profile policy.

The output must be absent and its parent must exist. A private sibling stage
collects all selected outputs, then publishes without replacing an existing
destination. Failures retain the partial stage and tool inputs for inspection.
`project.json` follows `nex.project-package/1`, recording plan/configuration,
relative component entries and a SHA-256/file-mode inventory. Limits are16384
files,512MiB per regular file and4GiB total. Internal regular-file SONAME aliases
are recorded; escaping or directory symlinks reject. Assembly executes no app,
creates no graph Store and does not deploy to a host.

The native collector checks compiler-owned images against their captured hashes,
UUIDs and completion/3 inventory. Only those exact files receive generated-code
provenance and matching runtime notices. Other native dependencies retain the
SDK inventory or explicit `--notices FILE` / Linux `--dpkg-notices` requirements.
The application author's source licensing remains their choice. Copies receive
relative loader paths; original artifacts stay unchanged. Run relocated output
on its intended host before treating execution as verified.

Credentials, keys, databases and operator runtime settings are supplied after
packaging. Serve a web directory from its matching configured server/static
host; browser route fallback and API configuration retain their existing rules.
Debug/core provenance for rewritten packaged images, Windows installers and
dedicated task/editor debugging remain pending. Project package task/replay is
described in project-tasks.md; it preserves actual binary edges.

## Foreign project packages (candidate0.84)

```sh
nex project --kind plan --foreign /operator/host.json --json
nex project --kind package --foreign /operator/host.json \
  --notices notices.json --directory /new/deployment --json
```

The original locked project, every selected source closure, direct dependency
edge, concrete export, private binary contract and toolchain fingerprint are
checked before preparation. The readonly plan checks source signatures and
current operator grants; it invokes no native tool and initializes no module.
Packaging currently requires a matching macOS/Linux host target for foreign
module dependency discovery. The normal native provenance/notice rules apply.

The compiler prepares the union of actually reachable app/server exports once.
Only exact external manifest literal tokens are projected in memory across all
selected components sharing those physical declarations. It reloads/checks the
projection and revalidates the declared binary contracts, then consumes the
actual archives and shared images. Original sources, lock and Store stay
unchanged. Input aliases, source/metadata bytes, catalogue and compiler helpers
are checked around preparation, compilation and final publication.

Each application receives a separate `foreign/host.json` containing only that
application's reachable libraries/exports and the original operator module
quota. Shared providers use the same projected pins. Apps without reachable
externals receive no catalogue, including HTTP companions linked to a common
foreign-enabled runtime. The runtime resolves the default relative to the
actual executable, including a shared runtime loaded from `lib/`.

`project.json.foreign_projection` records `nex.project-foreign-projection/1`,
the original plan/catalogue and source/derived identities for every selected
component. Per-app `application.json.foreign_projection` has `scope: project`
and a narrowed preparation/catalogue. A source closure can include changes
needed by another selected application; these do not grant authority to call
those exports. The manifest inventories bind the actual relocated native bytes.
No module constructor, application, database or runtime credential is executed
or created during packaging. Verify relocated output on its destination host.
Candidate focused checks and full platform/installed SDK acceptance have
separate evidence; do not infer a completed release from this design contract.
