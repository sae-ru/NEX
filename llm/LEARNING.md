# NEX for language models

[English overview](../docs/overview.en.md) · [Русское описание](../docs/overview.ru.md)

This repository supplies a model-independent language contract: readable source,
a normative specification/grammar, compiler discovery, examples and behavior
checks. A model can use these files immediately through retrieval. Future model
training and inclusion in a provider's dataset are decisions outside this
repository; publication does not guarantee that a model already knows NEX.

## A small working context

1. Read the project's instructions and the SDK's [coding contract](SYSTEM_PROMPT.md).
2. Inspect the manifest, affected source and relevant tests. For a larger change, inspect the checked source directly with
   `nex context ENTRY --kind brief --symbol QUALIFIED_NAME --json`.
3. Resolve concrete uncertainties with `nex describe --field PATH --json` or a feature
   guide. Use `nex describe --kind index --json` to find unknown field names.
4. Use the [detailed rules](DETAILED_CODING_RULES.md) for feature-specific contracts.
   Pin the compiler build, descriptor and project language when caching answers.
5. Make the requested change with exact source/revision guards. Run `nex check`,
   relevant tests and the reviewed acceptance task. Preserve failed diagnostics.
6. Record observed results and remaining work. A successful emit or cross-build
   does not establish native execution, browser execution or device placement.

[The specification](../docs/language.md) and [grammar](../docs/grammar.ebnf)
resolve syntax/semantic questions. [The workflow](WORKFLOW.md) explains guarded
graph changes, export and recovery. `PLAN.md` contains intentions and historical
notes; it is not a substitute for compiler discovery.

Current development advertises project languages0.28/0.29/0.30; `nex init`
selects0.30 and the unconfigured compiler fallback remains0.28. Read the
[reference guide](../docs/references030.md) and [cell example](../examples/references/README.md)
for explicit mutation/identity. Retained SDKs and existing project histories
keep their original versions; migration is explicit.

## Examples with explicit labels

[corpus.json](corpus.json) identifies positive projects, expected stdout and
intentionally rejected source with expected diagnostic codes. Start with:

- [Values and a test](../examples/learn/hello/main.nex).
- [Typed source error, guard and finally](../examples/learn/typed-errors/main.nex).
- [Ordered CPU mapping](../examples/learn/cpu-map/main.nex).
- [Runtime source contracts and loop checks](../examples/learn/contracts/main.nex).
- [Generics, enums, Results and f64](../examples/learn/values/main.nex).
- [Unicode and immutable bytes](../examples/learn/text-bytes/main.nex).
- [Traits and associated types](../examples/learn/traits/main.nex).
- [Structured tasks](../examples/learn/tasks/main.nex).
- [Modules and checked imports](../examples/learn/modules/main.nex).

The current0.28 labels are generated from [corpus-spec.json](corpus-spec.json)
by the [actual-compiler workflow](../docs/learning-corpus.md). Nine positive
projects have reference/native Release/TypeScript main/test observations; six
counterexamples have exact rejected diagnostics. The old0.27 record and inputs
are preserved separately. Absence from this finite corpus does not disable an
advertised compiler feature. The old `features` summary is also explicitly
partial: query the indexed sections and respect their scope/pending fields.


Language 0.28 also supports pure `requires` / `ensures` and loop
`invariant` / `decreases` clauses. Discover `source_contracts` and read the
[contract guide](../docs/source-contracts.md). Checks are runtime assertions in
release too; bounded Z3 proof is a separate explicit operation. Keep inline
contracts and detached guarded projections consistent with original declarations.

Rejected examples under `llm/rejected/` are counterexamples, not valid templates.
Larger examples and conformance tests retain their own version/prototype scopes.
Never retag an old graph or copy a private ABI into a public program.

## Rules that matter

For a matching native C++ host, discover `native_entry_abi` and retrieve the
library build's [physical entry description](../docs/native-entry-abi.md).
Hidden error outputs, runtime scopes and task-executor arguments are part of the
calling contract. Do not infer a prototype from `native_symbol` alone.

Preserve checked arithmetic, left-to-right evaluation, short-circuiting,
strict UTF-8/Unicode scalars, immutable aggregate semantics, effect declarations,
realms and owned cleanup. `result<T>` errors, typed source errors, checked traps,
cancellation and limits have distinct meanings. Fatal outcomes do not become
catchable because their code strings happen to match.

Only reachable client/shared code belongs in a browser result. Effects and
payload metadata do not grant filesystem, foreign-module or device authority.
Use actual grants and exact provider ABIs. GPU/NPU support must name the device,
operation, backend and fallback policy that were physically verified.

For scalar GPU source generation, query `gpu_codegen` and read
`nex guide --kind gpu --json` from the selected compiler. Development0.165
offers `nex emit --kind metal` directly from checked source. Its versioned
record includes reachable identities and function line mappings; emission
alone neither executes a GPU nor establishes installed SDK support. Keep
unsupported types, effects, realms and control flow explicit.
When the selected descriptor includes `gpu_codegen.owned_provider`, query that
field for the installed preparation and verification paths. They connect public
emission to a pinned owned NEX task provider; source-only preparation uses
`--check-sdk` without a GPU or Apple's SDK. Keep its actual emission record,
compiler/descriptor hashes and foreign grant together. Complete immutable SDK
and hardware acceptance remain separate requirements.

Persistent native hosts use the compiler-private
[task session API](../docs/native-task-sessions.md), discovered through
`managed_references.source030_development.native_host_sessions`. Keep one matching
runtime, explicit file grants and checked code images alive across related calls;
per-call limits reset without discarding healthy source state.

## Using the material in a dataset

Keep code, natural-language task, expected behavior, language version and
validation metadata together. Retain rejected examples with their rejection
labels. Preserve source/commit identity and MIT notices; third-party files
retain their own terms. Do not label proposals as implemented APIs or remove
failed outcomes when measuring model performance.

Measure total accepted-task cost, including retrieved context, tool responses,
generation and retries. [Quality criteria](../docs/quality.md) describe the planned
cross-model comparison; compact syntax alone does not prove lower token cost.
The user-selected [local Qwen3.8 27B study](../docs/llm-cost-qwen38-27b-2026-11-11.en.md)
completed60 trials and found lower NEX acceptance with higher total token use.
Keep that negative result separate from the labelled learning corpus; do not
present compiler-checked examples as evidence of model task-success or savings.

The [version2 entry and study](../docs/llm-entry-v2.md) preserves that historical
result. Its explicit030 host controls and synthetic accounting checks have
passed; no new observed model result or token saving is claimed.
