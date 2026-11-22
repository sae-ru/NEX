# NEX bootstrap

Use the installed compiler as the capability authority. PLAN and proposed
designs are not implemented features. Preserve the project's language version.
Current development's `project_languages` lists0.28/0.29/0.30; new projects
select0.30, separately from the unconfigured compiler fallback0.28. Discover
`managed_references` and read its `references` guide before using cells/state.

1. Start with the project manifest, affected source and its tests. Follow
   `llm/SYSTEM_PROMPT.md`. An ordinary edit can use the project's existing patterns.
2. Resolve a specific uncertainty with `nex describe --field PATH --json`,
   `nex guide --kind quick` or a feature guide. Use `nex describe --kind index --json`
   to discover unknown fields. Reuse results only for the same compiler build,
   descriptor and project language.
3. For a larger change, use `nex context ENTRY --kind brief --symbol QUALIFIED_NAME --json`
   on the current source. On older SDKs run `nex check ENTRY` first, then use
   `nex context --symbol QUALIFIED_NAME --json`. For invalid source use the file and diagnostic.
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
