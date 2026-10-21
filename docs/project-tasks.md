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
These copies are build evidence, not dependency-bundled deployment packages or
relocated debugger sessions. Project package checks, server workloads and
dedicated task/editor debugging remain pending.
