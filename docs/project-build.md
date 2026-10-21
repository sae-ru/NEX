# Checked project architecture and builds

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
commands. Omitting the component selects all components. A selected component
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
workspace or export a checked core capsule. Project commands do not yet produce
a combined project debug/test/task session automatically.

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
requirements. Automatic shared-image packaging, core inspection/capsules for shared images,
Windows DLLs and combined project run/test/debug/task commands remain pending.
Do not pass a project app through an ordinary source command expecting the
declared binary architecture to survive that independent compilation.

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
