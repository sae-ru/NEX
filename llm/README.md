# Model-independent NEX language pack

NEX uses one versioned specification, grammar and compiler interface for Codex,
Hermes and other LLMs. Start with [BOOTSTRAP.md](BOOTSTRAP.md), then use the
compact [coding contract](SYSTEM_PROMPT.md).
[Learning entry](LEARNING.md) links the public bilingual guides and labelled examples. Detailed guides are retrieved for
the feature being changed. Current development language is0.28; installed
compiler capabilities and matching acceptance evidence govern actual support.

## First use

1. Install a matching SDK and follow the [current installation guide](../docs/getting-started.en.md).
2. Ask `nex describe --kind index --json`, then `nex describe --field PATH --json`
   for the needed features. Keep compiler_build and descriptor_hash consistent.
   Older SDKs can use `nex describe --json`.
3. Retrieve the coding contract with `nex guide --kind prompt --json` and selected
   feature guides. Use indexed examples and JSON schemas. Read the normative
   language/grammar when needed; PLAN is a list of intentions, not capabilities.
4. Get bounded context with `nex context --symbol NAME`, edit with exact guards,
   and run compiler checks, relevant tests and reviewed acceptance tasks.
5. Preserve source, tests, locks, contracts and graph history. Use explicit
   migrations; do not relabel archived source or replace requirements.

`language-pack.json` indexes documents, schemas, examples and capability contracts.
The installed SDK also includes source/runtime resources and acceptance tools.
The labelled `corpus.json` retains its language0.27/toolchain0.152.1 validation
record; it does not qualify a newer compiler. Follow the selected compiler's
capabilities and recheck examples when moving to another version.
No model-specific syntax or separate private grammar is required. A natural
language request still needs observable acceptance criteria; the compiler cannot
prove that a test suite completely captures the user's intent.

## Current boundaries

Language0.28 includes typed source errors, ordered handlers, filters and finally,
including task suspension in reference/native/TypeScript. It also supports pure
[`requires` / `ensures` and loop `invariant` / `decreases`](../docs/source-contracts.md),
with runtime checks active in release builds. Bounded Z3 proof is a separate
request. Existing0.27 graph histories require an
[explicit migration](../docs/source-contract-migration.md).
Native task providers use ABI7; the retained explicit0.27 development emitter
has its separate cohort2702.
Server task/fs/ffi resource transport, physical grants, owner transfer and cleanup
retain their checked rules. General algebraic effects, remaining network/DB task
integration, universal GPU/NPU APIs, native UI/mobile completion and broader
platform delivery remain pending. Query each relevant descriptor and guide.

Source enablement, full compiler tests, installed SDK acceptance and actual
platform/hardware execution have separate evidence. A browser asset build is
not a browser execution test. Historical compiler receipts keep their versions
and do not establish support in a new SDK.

The compact prompt replaces accumulated milestone instructions; prior prompt
versions remain in source history/recovery checkpoints. This reduces required
initial document bytes. It does not establish lower total model-token cost,
higher success rates or parity with C++/Python. Measure complete context, tool
responses, generations, retries, time and correctness on the same defined tasks;
see [quality criteria](../docs/quality.md).
# Validate current language-pack artifacts

The source-checkout developer gate below checks a fresh project's actual
manifest, three analysis projections, operations and task contract against the
current JSON Schemas. It also rejects invalid language-version values. Use the
actual current compiler; initialization selects its declared entry and language.
This gate performs no native build, application execution or model calls.

Use Python with `jsonschema>=4.23`; this is a developer dependency, not an NEX
application or installed compiler dependency. Normal CTest uses standard Python.

```sh
python3 tests/current_schema_contracts.py /absolute/path/to/current-sdk/bin/nex \
  --output /new/current-schema-evidence
```

Language0.28 is admitted by the current authoring/analysis/graph/debug/project,
ABI7 provider, runtime-contract and browser-delivery schemas. The diagnostic
schema describes the uncaught source-error packet explicitly, and migration
candidates admit target0.28. These data contracts do not upgrade old graphs,
change a runtime ABI or update a previously archived SDK. Source implementation,
artifact-schema checks and installed delivery retain separate evidence.

The broader `tests/schema_artifacts.py` gate exercises the current language0.28
compiler and ABI7. It generates real graph, editor, diagnostic, native debug,
verification, Wasm and project artifacts in 14 selected tests. All 85 schema
documents are checked for valid definitions; the selected scenarios must produce
the 23 required artifact families. This does not claim runtime coverage of every
schema document.

```sh
python3 tests/schema_artifacts.py /absolute/path/to/current-sdk/bin/nex \
  --output /new/current-artifact-evidence
```

This gate compiles and executes native programs and uses LLDB. The full mode
also needs a matching LLVM22.1 `wasm-ld`; select it with `NEX_WASM_LD` when it is
not reported by `nex doctor`. Missing tools and skipped tests fail the gate.
`--only-providers` runs the narrower provider scenario: plain, profiled and
debug providers, each with static and shared linkage. Both modes require these
six actual provider variants, two actual project LLDB sessions and rejection of
malformed provider/debug-session records. The optional `--retained-nex` argument
adds a separate historical0.24 replay; ordinary current runs do not use an older
compiler. Retained ABI2–6 schema documents must remain byte-for-byte unchanged
during either run.

The [macOS source artifact record](../docs/evidence/current-artifact-schemas-2026-11-05.json)
pins the tested compiler, driver and schema inputs. Installed SDK and other
platform acceptance need their own runs with matching resources.

The compiler enforces byte budgets, graph identity, provenance and semantic
constraints beyond JSON Schema. A valid JSON document does not authorize an
effect or make a captured frame match a different build.
