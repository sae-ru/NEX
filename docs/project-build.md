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
direct import. Dependencies may target `source` or `static_library` components;
applications/servers/web components cannot serve as libraries. Dependency cycles,
unknown names and overlapping roots are rejected even outside the selected
closure. Only selected source closures are parsed/checked; an unrelated
unselected source file is not an implicit build input. Existing `pub`, type,
effect, realm, import-containment and dependency-lock checks still apply.

## Artifact kinds and source linkage

| Kind | Result | Entry contract |
| --- | --- | --- |
| `source` | Checked reusable source; no separate artifact | Source module |
| `executable` | Native executable | `entry_function`, default `main` |
| `static_library` | Native GNU archive, `libnex.a` | Required `entry_function`; current trusted runtime ABI |
| `server` | Native HTTP server | `entry_function`, default `handle`; existing HTTP contract |
| `web` | TypeScript/React/Vite application and static assets | Existing initial/update/view/title contract |

The only implemented dependency linkage is explicit `"source"`: each consumer
compiles its reachable checked dependency source. If that dependency also has a
`static_library` output, the consumer does **not** consume that archive. The
archive is a separate output for a matching trusted native host. It is not a
stable cross-version C ABI. Do not label these source edges as archive linkage.

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
unproven. General NEX DLL/so/dylib output, actual archive/shared dependency
consumption, stable export/ownership ABI, full-static policies and resolved
binary dependency reports remain pending. Unsupported linkage/kinds fail with
`E_PROJECT_CAPABILITY`.

General source concurrency, GPU kernels and NPU model adapters also remain
pending. HTTP workers and client/server/shared realms are not a source task API.
Separate [CIX P1 hardware checks](cix-p1.md) must not be advertised as completed
NEX accelerator integration.
