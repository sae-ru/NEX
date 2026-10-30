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

For typed error forwarding, query `nex describe --field result_propagation --json`
and `nex guide --kind result --json`. Respect the reported language and pending
integration gates. For source exceptions, query `source_exceptions` and read the exception guide.
Use only the selected SDK's advertised syntax, payload and effects; checked traps
remain separate from catchable source errors. For a conditional catch, query `source_exceptions.handler_filters`. Language0.27
supports typed payloads, ordered handlers, filters and finally, including task
suspension in reference/native/TypeScript. Checked traps, cancellation and limits
remain separate outcomes; fatal traps and cancellation do not run user finalizers.
Keep installed-SDK and actual platform acceptance separate from source support.

For ordered CPU batches, query source_concurrency and retrieve the concurrency
guide. Require the actual source operation and matching language; native worker
execution and serial reference/TypeScript evaluation have distinct guarantees.
