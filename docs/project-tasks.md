# Acceptance tasks for a declared architecture

Toolchain0.78 extends `nex.task/1` with optional project metadata. Existing tasks
keep their source-command behavior. Language0.16, canonical identities and graph
history are unchanged. Query the actual compiler's `task_features` before using
the extension.

```sh
nex project --kind plan --component app --configuration debug --json
nex task nex.build.json --kind init --component app --configuration debug -o task.json
# Review the goal, requirements, test pins, architecture and configurations.
nex task task.json --kind check --json
nex task task.json --kind run --task-hash HASH_FROM_CHECK --json
nex task /absolute/run/receipt.json --kind replay --json
```

The generator does not infer adequate acceptance criteria. Keep the reviewed
task, sources, `nex.json`, `nex.build.json`, dependency lock and relative toolchain
descriptions in Git. Generated runs, native caches and runtime credentials stay
outside version control. Architecture selection belongs to the task; check/run
do not accept a CLI override for its component or configuration.

Each project-backed program adds a `project` object containing the root manifest
filename, component name and reviewed `architecture_hash` from the project plan.
The manifest must be beside `nex.json`. The ordinary `entry` remains the selected
component's canonical project-relative source entry. Each of its checks names a
`configuration`; profile overrides are rejected. The source/target/artifact kind
must match the selected component. Changes to the architecture require a reviewed
task update; implementation bodies remain editable under the existing test pins.

Build, test, run and profile checks use actual source/static/dynamic dependencies.
Library build checks use `mode:"library"`; their actual static/shared kind comes
from the architecture. Module emission is a separate source task operation.
Verify/effects/API checks retain their source semantics and requirement linkage.
Profile checks need a profile configuration and explicit budgets. A duration
budget still requires the approved hardware identity. Successful compilation
for another ABI establishes a build, not execution on that platform.

Native test compilation uses `nex project --kind build-test --symbol TEST`.
This returns `nex.project-test-build/1` without running tests or opening a graph
Store. The task parent supervises the resulting native process directly. Pure
shared tests additionally compare interpreter and TypeScript execution in the
owning component's context. Effectful tests execute once in their selected
backend. Web/client tests use the reachable TypeScript projection. A failed,
skipped, interrupted or unsupported observation cannot satisfy a requirement.

Run checks preserve exact expected stdout, exit status and optional checked
runtime error. Pure entries also compare the interpreter; effectful project
entries run once natively and record why reference replay was omitted. Native
profiles measure the actual final image and provider functions. Process timeouts,
output limits and SIGINT/SIGTERM are managed by the task parent, including
ordinary forked native descendants. Forced termination cannot promise language
destructors or reversal of application side effects.

## Captured inputs and replay

When `isolated_replay_graph` is available (toolchain0.80), replay owns its graph,
cache and history under `NEW_RUN/state`. It never searches upward for a project
to modify. Saved input receipts can be readonly with an explicit writable output
directory. Temporary preflight IDs are preserved by a checked SQLite snapshot in
the output state; recorded bindings refer to that state, not an enclosing graph.

The run stores a `nex.project-capture/1` record in `inputs/projects/PROGRAM.json`.
It contains selected source closures, project metadata, configuration identities
and their physical alias relationships. External packages used by those closures
are captured. Unrelated files and unselected component bodies are not copied;
empty validation placeholders preserve their declared paths without parsing them.
`llm/project-capture.schema.json` describes the data envelope. Compiler checks add
path containment, canonical alias, source hash, ABI, byte and count validation.

Materialization creates a new private namespace under the run. It preserves the
original relative containment of components, package roots and aliases, while
all source inputs remain inside that owned namespace. Plans are rechecked against
captured semantic revisions, source bundles and toolchain fingerprints before
execution and around commands. Workspace mutation fails the check. Replayed
builds never silently substitute live original source or package files.

`--revision HASH` or the existing `--candidates FILE` can select archived code.
The reviewed architecture metadata remains explicit; captured source overlays do
not rewrite the original working files. Archived dependencies receive a derived
lock for their captured contents. Source language changes still require explicit
migration. Existing task history and optimistic `--task-hash` guards apply.

An explicit configuration toolchain requires a reviewed `toolchain` ID/hash and
a current `--toolchains CATALOG.json`, including during replay. Normalized driver
paths and identities must agree with that current operator catalogue. A capture
cannot grant permission to execute an old driver. Default native toolchains are
also fingerprinted and rechecked. Foreign execution requires the existing
reviewed `foreign_hash` and current `--foreign HOST.json`; receipts and environment
variables do not grant FFI authority. Changes restored between checks are outside
these discrete observations.

Inputs retain the existing task bound of128MiB and8192 indexed files. A project
capture is bounded to64MiB,8192 files/aliases,32 configurations and128 components.
Source candidates retain their ordinary16MiB bundle limit. Native build artifacts
retain first-party images beside their executable; web artifacts retain `dist`.
Build copies are distinct from deployment packages and relocated debugger
sessions. [Server workload profile tasks](task-workloads.md) require the separately
advertised0.83 capability; dedicated task/editor debugging remains pending.

## Package acceptance

When the compiler advertises `project_task_packages` (toolchain0.79), a check can
package a project-backed executable, server or browser component:

```json
{"id":"delivery","program":"app","kind":"package","target":"native",
 "configuration":"release","timeout_seconds":300}
```

Link it to a reviewed requirement and its component entry functions as usual.
Use `target:"server"` for a server or `target:"web"` for a browser component.
The declared configuration supplies profile and toolchain; check-level entry,
profile, mode and shell steps are not accepted.
Native packaging requires a matching host. Libraries and source-only components
are not standalone application packages. Source tasks keep their existing kinds.

The check calls the compiler's package action in its captured architecture. Its
receipt records a relative `package` directory, component entries, command report
and indexed artifact files. The package includes deployment libraries and notices
under the existing project-packaging rules. Packaging never runs the application;
it cannot satisfy a runtime expectation without a separate execution observation.
The example task in `examples/project-tasks` requests both kinds of evidence.

Package helpers are copied from the compiler's current trusted resources and
verified during replay. The compiler's current SDK inventory and host packaging
tools supply provenance; a receipt cannot select replacement executable helpers.
Python helpers do not write bytecode into immutable captured inputs. Relative
file aliases are indexed only if they resolve inside the same saved package;
all ordinary input inventories still reject symlinks. Artifacts retain the task
limit of8192 files and256MiB per check, narrower than standalone package limits.

Source-deleted replay rebuilds and packages captured code under the required
current toolchain. It is not a promise of byte-for-byte package identity, platform
signing, target execution or complete external notice coverage. Native dependency
licensing failures remain failed checks. Source foreign-call package projection
remains pending.

### Reviewed notice inputs

For external dependencies not covered by the current SDK inventory, place their
complete license texts inside the project and create a `nex.sdk-notices/1`
catalogue using the ordinary packaging format. Task notice components accept
`name`, `version`, `url`, `roots` and `license_files`. Root paths identify the
actual native dependencies; license paths resolve relative to the catalogue and
must remain inside the project after symlink resolution.

```sh
nex task licenses/notices.json --kind notices --json
```

This readonly query returns `inputs_hash`, component names and license counts;
it invokes no compiler/packager tools and opens no graph Store. Add
`"notices":"licenses/notices.json"` and `"notices_hash":"RETURNED_INPUTS_HASH"`
to the package check. The hash covers normalized dependency roots, component
metadata and complete license text. Re-review changes explicitly. A changed
license fails check/run before packaging. A data catalogue grants no permission
to execute a driver or native module.

The run captures `snapshot.json`, normalized `notices.json` and license text in
`inputs/package-notices/CHECK/`, all under the ordinary input hash index. Replay
uses those checked files after original catalogues/licenses have been deleted.
The package helper receives this explicit captured catalogue; inputs are checked
before and after its command. Bounds are128 components,128 roots/64 licenses per
component,256 distinct license files,1MiB per text and8MiB total license text;
the formatted catalogue is limited to1MiB and snapshot to16MiB. This mechanism
records the supplied provenance; operators remain responsible for its accuracy.
