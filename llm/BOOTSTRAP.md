# NEX bootstrap

Use the installed compiler as the capability authority. PLAN and proposed
designs are not implemented features. Preserve the project's language version.

1. Run `nex describe --kind index --json` once. On an older SDK that rejects it,
   use `nex describe --json`. Request only relevant `nex describe --field PATH`
   sections; keep compiler_build/descriptor_hash consistent across lookups.
2. Follow `llm/SYSTEM_PROMPT.md` and the normative language/grammar. Retrieve
   guides for the selected features. Never invent syntax, effects or support.
3. State behavior, constraints and acceptance criteria. Get bounded graph
   context with `nex context --symbol NAME`; fetch dependencies when needed.
4. Make small changes with exact source/revision guards. Preserve checked
   arithmetic, Unicode, effects, realms, immutable values and owned cleanup.
5. Run compiler checks, relevant tests and the reviewed task. Inspect diagnostics;
   keep rejected attempts and acceptance requirements intact. Validate observable
   behavior, not just successful generation. Export/source-control the result.

Retrieve extra context only for a concrete uncertainty. Count the entire accepted
task's context, tools, generation and retries when comparing token cost. A short
prompt or a smaller JSON response alone proves no overall LLM improvement.
