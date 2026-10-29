# Model-independent NEX language pack

NEX uses one versioned specification, grammar and compiler interface for Codex,
Hermes and other LLMs. Start with [BOOTSTRAP.md](BOOTSTRAP.md), then use the
compact [coding contract](SYSTEM_PROMPT.md). Detailed guides are retrieved for
the feature being changed. Current development language is0.24; installed
compiler capabilities and matching acceptance evidence govern actual support.

## First use

1. Install a matching SDK and follow the [quickstart](../docs/quickstart.md).
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
No model-specific syntax or separate private grammar is required. A natural
language request still needs observable acceptance criteria; the compiler cannot
prove that a test suite completely captures the user's intent.

## Current boundaries

Language0.24 enables checked server task/fs whole-file and stream IO, including
ABI5 static/fixed-shared task providers and genuine File owner transport. Source task/ffi resource transport, physical
grants, owner transfer and cleanup retain their checked rules. General exceptions,
network/DB tasks, owned NPU/models, native UI/mobile completion and broader
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
# Validate actual language-pack artifacts

The source-checkout developer gate below checks compiler responses, accepted
debug frames, actual LLDB captures, project captures/packages, Wasm metadata and
all six025 provider variants against their JSON Schemas. `--retained-nex` also
builds/runs an024 application and rejects retagging its ABI5 provider as025.
Use Python with `jsonschema>=4.23`; this is a developer dependency, not an NEX
application or installed compiler dependency. Normal CTest uses standard Python.

```sh
python3 tests/schema_artifacts.py /absolute/path/to/nex \
  --output /new/schema-evidence \
  --retained-nex /absolute/path/to/024-sdk/bin/nex
```

The compiler still enforces byte budgets, graph identity, provenance and semantic
constraints beyond JSON Schema. A valid JSON document does not authorize an
effect or make a captured frame match a different build.

