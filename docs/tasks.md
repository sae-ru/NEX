# Tasks and acceptance evidence

A `nex.task/1` file records the requested goal, named programs, requirements,
qualified graph bindings and explicit acceptance checks. It is independent of
LLM vendor. Current source language is 0.9; this is a development-tool protocol.
The compiler checks the declared criteria. Natural-language completeness and
the quality of those criteria still require review.

```sh
nex task main.nex --kind init -o task.json
nex task task.json --kind check --json
nex task task.json --kind run --task-hash HASH_FROM_CHECK --json
nex task task.json --kind history --json
nex task /absolute/run/receipt.json --kind replay --json
```

`init` scaffolds checks from existing tests and an available application/library
entry. Replace its placeholder goal and requirements. It does not invent or
prove the acceptance criteria for a new product. `llm/task.schema.json` defines
the format; `examples/tasks` is an executable example.

`check` checks the document, sources, reviewed test hashes, formal property
hashes and graph links. It does not execute programs, install npm packages or
build outputs. It archives checked source candidates without changing graph
HEAD. Unsupported targets are reported as unsupported and return failure.

`run` freezes inputs before execution. A receipt records each check and linked
requirement, candidate revisions, exact source hashes, task identity, logs,
artifacts, compiler build and host. The CLI returns `nex.task-session/1`; the full saved receipt is `nex.task-receipt/1`. CLI results omit large artifact/binding indexes and per-test details. Every required check must pass; failure,
unsupported scope, timeout, output limit, interruption, skipped work and an
unproven solver result cannot satisfy a requirement. Independent checks continue
after ordinary failures. Interruptions skip remaining work. Receipts are
checkpointed before and after checks and indexed in SQLite. History contains at
most 50 runs; a recorded running state alone does not show that a process is
still alive.

## Intent and candidates

All document fields participate in `task_hash`. Use `--task-hash HASH` to reject
an unintended change to the task. This is an optimistic guard, not a signature
or an approval mechanism. Keep the reviewed task in version control.

Programs have unique IDs and project-relative entry files. Several entry
programs can share identical module sources; conflicting versions of the same
logical module are rejected. Each requirement names qualified functions,
structures or endpoints and its check IDs/targets. The checker requires the
bindings to be statically reached by a linked check and every required target to
have a linked check. This is static linkage, **not measured test coverage**, a
proof that assertions are sufficient, or proof of the natural-language goal.

Normally commands read live source candidates. `--revision HASH` selects an
archived candidate for a single-program task. `--candidates FILE` accepts a JSON
object mapping program IDs to archived revisions for multiple programs. Omitted
IDs use live source. The entry must match the task's entry. Neither mode changes
the task definition or project HEAD. `baseline_revision` is descriptive metadata;
it does not automatically select or compare candidates.

Test checks pin each selected test's canonical `content_hash`; changing an
assertion requires explicit review and a changed task. The bodies of called
implementation functions remain editable. Helpers/fixtures outside the pinned
test bodies are not separately pinned in this version: review those changes too.

A verify check pins the approved functions, return bindings, preconditions and
postconditions using `intent_hash`:

```sh
nex contract main.nex --symbol increment -o proof.json
# Review and edit requires/ensures and any loop proof strategy.
nex contract --kind intent --contracts proof.json --json
```

The task derives a separate snapshot-bound contract for the candidate. Only its
revision/source/function hashes are rebased. Preconditions and postconditions
must retain the approved intent hash. Loop coordinates, invariants and rankings
are proof strategy: they can change without changing the property hash, but the
verifier still checks their validity and every generated obligation. A changed
interface also needs review; this hash does not itself encode a function type.
The original sidecar remains unchanged. Only a proven result passes. These
contracts do not inject runtime pre/postconditions or remove runtime guards.

## Check kinds

| Kind | Target | Acceptance |
| --- | --- | --- |
| `test` | `native`, `web` | Named, hash-pinned tests pass in interpreter and native/TypeScript execution; excluded realms cannot pass. |
| `build` | `native`, configured triple, `server`, `web` | Requested application, native library or web module is generated successfully. Foreign artifacts do not certify execution. |
| `run` | `native` | Native and reference stdout match the exact expected text; exit status and an optional runtime error code agree. |
| `verify` | `source` | All functions in a property-pinned scalar contract are proven. |
| `effects` | `source` | Every function in the selected transitive call closure stays within allowed declared effects and realms. |
| `profile` | `native` | The instrumented scenario succeeds, aggregate records are complete and every explicit budget is satisfied. |
| `api` | `source` | Checked API dispatch/SDK/schema/OpenAPI generation succeeds. |

Check IDs are unique. No arbitrary shell-command step exists. Unknown check
kinds/fields are errors. Unknown or unconfigured targets remain unsupported.
Tasks have 1–8 programs, 1–32 requirements and 1–64 checks; JSON inputs are bounded.

Build `mode` is `application` by default, `library` for a native archive, or
`module` for emitted TypeScript. A web application build performs the normal
locked npm install, TypeScript check and Vite build. Module emission alone is
not a browser application build or an independent TypeScript typecheck.
Native executables/archives and notices, web `dist`, modules and API generated
sources are copied to the run's artifacts. Build metadata can refer to shared
cache paths; copied binaries are not promised to be portable SDK bundles.

## Pinned native toolchains

Toolchain 0.19 adds optional `toolchain` and `toolchain_hash` fields to native
build/test/run/profile checks. Supply both. `toolchain` is an ID (1–64 ASCII
letters/digits/underscores/hyphens); `toolchain_hash` is the reviewed fingerprint:

```sh
nex toolchain /path/to/intel.json --json
```

This read-only command returns `nex.toolchain-report/1`: `hash`, `target`,
`host_compatible`, normalized `manifest` and fingerprint `inputs`. It never runs
the selected driver. Review the configuration and copy its hash into the check:

```json
{
  "id": "intel-library",
  "program": "app",
  "kind": "build",
  "target": "native",
  "mode": "library",
  "entry": "app::compute",
  "toolchain": "intel",
  "toolchain_hash": "REPLACE_WITH_REVIEWED_64_CHARACTER_HASH"
}
```

Link the check to a reviewed requirement as usual. `target` still selects output
kind; the toolchain selects its precise native ABI. A concrete target triple
must match the selected configuration. `server` can select a toolchain too.
Web/source checks cannot select native toolchains. Local test/run/profile checks
use `target: native` and require a host-compatible configuration; a foreign
configuration is reported unsupported and cannot satisfy execution requirements.

Pass a separate trusted catalog on check/run/replay:

```json
{"intel": "/path/to/intel.json"}
```

```sh
nex task task.json --kind check --toolchains trusted.json --json
nex task task.json --kind run --toolchains trusted.json --task-hash HASH --json
nex task /absolute/run/receipt.json --kind replay --toolchains trusted.json --json
```

`llm/toolchains.schema.json` defines this map of 1–16 IDs to configuration paths.
Relative paths resolve against the catalog directory. Only configurations used
by the task are inspected. The catalog is a current, explicitly selected source
of trusted paths; replay does not execute a compiler merely because a receipt
names it. Omitting a required current catalog entry, changing a pinned input or
disagreeing with the captured configuration fails with E_TASK_TOOLCHAIN. A new
trusted configuration file with the same normalized inputs may replace a deleted
original file. Changing the reviewed fingerprint changes task intent.

Runs capture normalized `inputs/toolchains/ID/config.json` and `identity.json`,
indexed alongside the source/runtime inputs. Summaries and receipts report each
selected toolchain's hash/ABI/host compatibility; native check rows report their
resolved target. Replay checks the capture against the current trusted catalog
and the pinned hash before creating a run. Fingerprints are rechecked before and
after child commands: a successful child cannot satisfy a check if either
inspection finds different pinned inputs. Changes restored between reads are
not detected. Independent checks still continue.

The current fingerprint (`nex.toolchain-snapshot/2`, toolchain 0.20) includes compiler/selected-linker executable bytes, configured SQLite
header/library, OpenSSL header tree/libraries, normalized configuration paths and
explicit SDK settings files. Defaults and explicit equivalent paths normalize
identically, preserving the final `clang++` driver name. Inspection is bounded
to 4096 files, 512 MiB per file, 1 GiB total and 4 MiB of metadata. Header directory
cycles are bounded. Paths are part of this identity; it is not a portable package
identity or signed attestation. File hashes/metadata are saved, not full external
toolchain copies.

SDK contents beyond settings, compiler support files, default system linker/libraries
and the environment remain external. This fingerprint detects changes within
its stated scope; it does not promise hermetic or bit-for-bit builds. Intel
artifact acceptance is exercised by cross-building on ARM64. Intel native
execution and live debugging still need a matching machine or configured
emulator. No emulator is configured.

Profile budgets use canonical unsigned decimal strings. Available maxima are
`max_duration_ns`, `max_peak_handles`, `max_peak_objects`, and `max_calls` keyed
by qualified function. A duration threshold requires explicit `hardware.cpu`
and `hardware.target` equal to the measured host. A missing measured call does
not satisfy a call budget. Reports measure instrumented wall time and shallow
managed objects/handles, not total RSS or uninstrumented application latency.
Task profiling disables timeline events; its expected dropped timeline count
is not loss of aggregate function/allocation statistics. Aggregate drops fail.

## Snapshots, replay and process lifetime

Each run has `inputs/task.json`, source bundles per program, derived formal
contracts, and snapshots of the selected compiler's runtime/lib/web/debug
resources. `inputs/manifest.json` indexes their byte hashes and sizes and the
exact compiler binary/build. `receipt.json` pins the manifest. Mutable SQLite
workspaces and a shared build cache are derived outputs. Graph node IDs are local to a store; derived-workspace proof/profile IDs can differ from the project binding IDs. Correlate evidence by qualified symbol, content hash and program revision. Check logs and artifact
indexes preserve evidence, including failure diagnostics.

Replay verifies the manifest, every listed file and the absence of unindexed
inputs. It requires the captured compiler binary/build and compares captured
executable resources against that compiler's current trusted resources. It then
copies captured inputs to a **new** run, rebuilds derived stores and executes
the checks again. It works after the original source/sidecar files are deleted.
It does not trust previous passed flags or take execution paths from a prior
report's absolute artifact fields. The old receipt is retained. Receipts and
hashes are integrity evidence, not signed attestations. Editing both a manifest
and its expected hashes does not create trusted evidence.

Each external check runs in an owned POSIX process group on the configured
macOS/Linux host implementation. Timeout, SIGINT/SIGTERM, output overflow and
normal leader exit stop descendants that remain in that group before reaping
the leader. Compiler subprocesses inherit the group. Output capture is bounded;
external commands within a check share a deadline including compilation, at most 3600 seconds. Input capture and parent-side static analysis/artifact copying are outside that subprocess deadline.
Code deliberately escaping its process group is outside this lifetime mechanism.
Windows supervision is pending and cannot report a successful run by skipping
checks.

The task runner is not an OS sandbox. NEX code, compilers, Node/npm packages,
Clang, SDKs and environment variables can perform their ordinary actions.
External tools, system libraries, network responses and environment are not
fully frozen. Replay rechecks behavior with the recorded NEX inputs; it does
not promise bit-for-bit builds or deterministic performance. Inspect the normal
compiler/runtime and third-party trust boundaries before interpreting evidence.

Source-level task annotations, dynamic coverage, dependent generated-program
steps, task scheduling, automatic requirement discovery, broader agent editing
operations and measured cross-model trials remain pending.

Language 0.7 links a reached generic instance back to its original function/type template, including phantom type arguments, so requirements can bind source declarations while tests exercise concrete instances. This is static lineage, not dynamic coverage of every instantiation. Profile max_calls budgets use exact concrete instance names from the measured report; a source-template name without a measured row remains unobserved and cannot pass.

Policy 2 adds selected linker identity. Toolchain 0.19 SDKs retain policy 1 for their saved receipts; inspect/review replacement fingerprints rather than silently changing task intent. Policy 2 originally retained language 0.7; language 0.8 adds explicit generic bounds and requires a reviewed migration.
