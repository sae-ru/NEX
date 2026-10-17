# Model-independent NEX language pack

`llm/language-pack.json` is its machine-readable index. `llm/patch.schema.json` provides a JSON Schema for generated replacement patches; the compiler performs the required semantic validation after JSON parsing.

[The Russian walkthrough](WORKFLOW.md) shows what to send a chat-only or tool-capable model and exercises a complete function repair, revision-checked patch, differential tests and source export. [The task template](TASK_TEMPLATE.md) specifies behavior and acceptance criteria as text; automatic task-contract enforcement remains pending.

The pack has four coordinated layers:

1. **Normative language:** `docs/language.md` and `docs/grammar.ebnf` specify syntax and semantics.
2. **Prompt:** `llm/SYSTEM_PROMPT.md` is a compact instruction for any model that can read text or invoke tools.
3. **Discovery:** `nex describe --json` exposes the implemented version, capabilities, builtin signatures, and unsupported features.
4. **Feedback protocol:** `context`, `apply`, `check`, `test`, and `build` let a model edit functions across modules atomically and obtain deterministic feedback. Context identifies each symbol's logical module, file and imports; revisions archive complete source bundles.

An installed compiler exposes the documents through `nex guide --kind prompt|language|grammar|protocol|web|server|api|debug|build --json`. Each response contains a version, content hash and text, so the model can obtain the matching pack without knowing repository paths.

`AGENTS.md` provides repository entry instructions to coding agents. A chat-only model can receive the prompt, specification, function context, and task as ordinary messages; its returned patch can be applied by a human or external runner. Tool-capable models can invoke the same CLI directly. No provider SDK, hosted model, special tokens, or training run is required.

The compiler validates model output using exactly the same parser and type/effect checker as human-written source. A model does not get an alternate, less strict language.

Browser authoring uses ordinary NEX functions and `std/web.nex`, with a checked state/update/view contract described in `docs/web.md`. Models use the same patch workflow and select `--target web` for differential tests and browser builds. The adapter and package lock are part of the compiler resources, avoiding provider-specific UI generation APIs.

Source changes and graph changes are separate workflows. Follow the materialization rules in `docs/protocol.md`. Use `describe` to detect version differences instead of guessing that another installation implements the roadmap.

Language 0.5 retains graph/context protocol 2 and qualified symbol identities such as `example::model::create`. A replacement's source still starts with its local declaration, such as `pub fn create` or `endpoint create_row(...) = create;`. Keep the returned visibility and import aliases. The compiler checks the complete candidate, including callers in other modules. `nex export --directory PATH` creates a portable editable project with vendored dependency sources; it requires a new or empty directory. Older stored language revisions require explicit migration.

Recoverable result<T>, typed JSON and server capabilities are described by the matching language/server guides. Native HTTP builds and principal-partitioned SQLite storage are available. The optional pure commands entry with std/net.nex now connects browser events to bounded same-origin HTTP requests; typed response envelopes feed the ordinary update function. examples/fullstack shares checked models with the native server and exercises durable authenticated CRUD. Language 0.5 endpoint declarations now generate the native dispatcher, extracted model SDK, pure typed command/response helpers and OpenAPI. Models use the matching api guide and nex api to inspect/generate these contracts; general source async/await remains unsupported.

The pack is useful for interoperability; it does not by itself prove that every LLM writes correct NEX or that the language saves tokens. Evaluation will record model/version, task, full context and tool output, success rate, repair attempts, and total token usage. A cross-provider coding evaluation remains to be run.

The native debugging guide is available as `nex guide --kind debug --json`. The toolchain advertises its actual debug capabilities separately from language features. Session descriptors connect any compatible DAP client to an installed `lldb-dap`; the read-only `nex-values` command gives models bounded, revision-attributed frame previews. This does not measure cross-model debugging quality or implement a model-specific debugger.

For native incremental compilation, retrieve `nex guide --kind build --json`. Build responses keep per-invocation compiled/reused module counts and a report path; the report contains source/ABI/type fingerprints and dependency indexes. Use normal bounded `context --symbol` queries to investigate a specific function rather than copying a whole build graph into model context. Cached objects never replace source checking or observable test validation.

`nex guide --kind profile --json` supplies the tenth installed guide. `nex profile FILE --scenario TEXT --json` returns bounded graph-attributed function measurements and the saved full timeline report. Use its exact revision and inspect measurement/drop limits before optimizing.

The eleventh guide is `nex guide --kind verify --json`. `llm/verification.schema.json` defines snapshot-bound scalar proof contracts; use the contract/verify commands in the pack manifest. Proof metadata does not change language 0.5 execution or replace tests/task acceptance.
