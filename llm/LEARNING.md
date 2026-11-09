# NEX for language models

[English overview](../docs/overview.en.md) · [Русское описание](../docs/overview.ru.md)

This repository supplies a model-independent language contract: readable source,
a normative specification/grammar, compiler discovery, examples and behavior
checks. A model can use these files immediately through retrieval. Future model
training and inclusion in a provider's dataset are decisions outside this
repository; publication does not guarantee that a model already knows NEX.

## A small working context

1. Read applicable `AGENTS.md`, [BOOTSTRAP](BOOTSTRAP.md) and [SYSTEM_PROMPT](SYSTEM_PROMPT.md).
2. Query `nex describe --kind index --json`. Keep toolchain/language,
   compiler_build and descriptor_hash consistent across feature queries.
3. Retrieve only relevant `--field PATH` sections and `nex guide --kind KIND`.
   Source-error providers are nested at `source_exceptions.source_providers`.
4. Read the affected project's manifest, tests and bounded
   `nex context --symbol NAME --json`. Preserve its existing language version.
5. Make the requested change with exact source/revision guards. Run `nex check`,
   relevant tests and the reviewed acceptance task. Preserve failed diagnostics.
6. Record observed results and remaining work. A successful emit or cross-build
   does not establish native execution, browser execution or device placement.

[The specification](../docs/language.md) and [grammar](../docs/grammar.ebnf)
resolve syntax/semantic questions. [The workflow](WORKFLOW.md) explains guarded
graph changes, export and recovery. `PLAN.md` contains intentions and historical
notes; it is not a substitute for compiler discovery.

## Examples with explicit labels

[corpus.json](corpus.json) identifies positive projects, expected stdout and
intentionally rejected source with expected diagnostic codes. Start with:

- [Values and a test](../examples/learn/hello/main.nex).
- [Typed source error, guard and finally](../examples/learn/typed-errors/main.nex).
- [Ordered CPU mapping](../examples/learn/cpu-map/main.nex).

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

## Using the material in a dataset

Keep code, natural-language task, expected behavior, language version and
validation metadata together. Retain rejected examples with their rejection
labels. Preserve source/commit identity and MIT notices; third-party files
retain their own terms. Do not label proposals as implemented APIs or remove
failed outcomes when measuring model performance.

Measure total accepted-task cost, including retrieved context, tool responses,
generation and retries. [Quality criteria](../docs/quality.md) describe the planned
cross-model comparison; compact syntax alone does not prove lower token cost.
