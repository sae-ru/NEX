# NEX bootstrap

Use the installed compiler as the capability authority. PLAN and proposed
designs are not implemented features. Preserve the project's language version.

1. Run `nex describe --kind index --json` once. On an older SDK that rejects it,
   use `nex describe --json`. Request only relevant `nex describe --field PATH`
   sections; keep compiler_build/descriptor_hash consistent across lookups.
   The legacy `features` array is partial; use the indexed capability sections,
   not absence from that summary, to decide support.
2. Follow `llm/SYSTEM_PROMPT.md` and the normative language/grammar. If `llm_entry`
   is advertised, retrieve `nex guide --kind quick --json` once for actual source
   syntax. Retrieve feature guides for concrete uncertainties. Never invent syntax,
   effects or support. For a covered rejection, use `nex explain CODE --json`
   when `diagnostic_catalogue` is advertised; preserve the original message/span.
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

If `cli_interface` is advertised, request `nex help COMMAND --json` for that
command's actual flags/aliases/value rules. Help opens no project and executes
no operation; its feature guide retains combination/platform restrictions.

Before writing basic text/list/math helpers, query `standard_library` when
advertised and read its `stdlib` guide. Import only needed modules; `list` is a
reserved word, so use `seq`/`lists` as the alias for `std/list.nex`. Keep existing
dependency pins until an explicit reviewed `nex lock` update.

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

For source contracts, query `source_contracts` before using028 clauses. Retrieve
`source-contract` and `source-contract-migration` guides. Runtime assertions do
not imply a proof or zero overhead. Preserve original history and physical source
until an explicit guarded migration/export is reviewed and checked.
