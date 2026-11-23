---
name: nex-programming
description: Write, debug, test and refactor applications in NEX (Neural Execution Language), including .nex sources and nex.json projects. Use compiler-provided language guides and bounded symbol context. Compiler/toolchain implementation work follows that repository's contributor instructions.
license: MIT
---

# NEX programming

Develop checked NEX applications using the selected SDK as the authority for
syntax, capabilities and command arguments. Follow the user's requirements and
project instructions. The skill version is independent of the language version.

## Discover the selected compiler

Use the project's chosen NEX executable consistently. If it is missing, read
[SDK setup](references/sdk-setup.md); the skill contains no compiler.

1. Read the installed coding contract once with `nex guide --kind prompt`, or
   use its matching local copy. Follow the project's existing source and tests.
2. Query `nex describe --field PATH --json` when the task needs an unfamiliar
   capability. To find field names, use `nex describe --kind index --json`.
   Reuse results for the same compiler build, descriptor and project language.
3. Consult `nex guide --kind quick` or a feature guide for a concrete syntax or
   semantics question. If a guide is missing, record the error and use the
   matching installed documentation or release language pack.

When `cli_interface` is advertised, get `nex help COMMAND --json` for unfamiliar
flags. Keep `--json` before an application's `--` argument separator.

## Implement the requested behavior

Inspect the project manifest, relevant sources and acceptance tests. Preserve
its selected language and dependency pins. Use `nex init PATH` for a new project;
do not hardcode the newest language version into an existing one.

For a larger change, request `nex context ENTRY --kind brief --symbol NAME --json`.
On older SDKs run `nex check ENTRY`, then `nex context --symbol NAME --json`. Expand
to related types, imports or callers when there is a concrete uncertainty.
Bounded context complements the physical source and tests. Graph-local IDs,
content hashes and revisions have different meanings; use the advertised
revision/source guards when applying graph operations.

Query `standard_library` before recreating collection, text or numerical
helpers. Prefer advertised bulk list/text/byte constructors for growing outputs.
For feature-specific routing, read only the relevant row of
[workflows](references/workflows.md).

Keep checked arithmetic, left-to-right evaluation, lazy boolean branches,
strict UTF-8/Unicode-scalar strings and declared effects. Ordinary aggregates
are immutable snapshots. Use reference identity/mutation only when the selected
language and `managed_references` advertise it. Distinguish `result<T>` values,
catchable source errors and fatal traps. Query source-error/finalizer rules
before relying on cleanup behavior. Preserve owned-resource cleanup and
client/server boundaries.

Do not relabel a manifest to migrate graph history. Discover and use the
explicit guarded migration workflow when a language upgrade is requested.
Edit authored source/templates rather than generated output.

For a small new example, [hello.nex](assets/hello.nex) provides checked integer
arithmetic, Unicode output and a source test. Copy it only when it fits the task,
into a project initialized by the user's compiler, and validate it there.

## Check the completed change

After a coherent edit, run `nex check --json`, the affected `nex test` cases and
the task's acceptance scenario. Use the compiler's actual help to select tests.
For changed execution semantics, compare the relevant native/reference and,
when targeted, TypeScript behavior. Successful code generation alone does not
establish successful execution or packaging. Reserve full SDK/device suites for
milestones or changes that require them.

For a failing source test, check `nex help test` once per compiler. If it lists
`--repair-context`, run `nex test ENTRY --repair-context --json` from the project
root, using the entry from `nex.json`. If the SDK ships the separate
[`nex-repair-context.py` helper](https://github.com/sae-ru/NEX/releases/download/v1.0.0/nex-repair-context.py),
run it there with `python3` (Windows: `py -3`) when the flag is absent.
Read the failed comparison and function excerpt, then request an entry from
`repair_context.inspect` only if a callee matters. After the edit, run
`nex test --symbol NAME --json` against the physical source.

If the failure has no repair context, use its code, span and a brief for the
failing symbol. Query `nex explain CODE --json` for an unfamiliar diagnostic.
Preserve the test's expected behavior.

Report the actual change, commands/results, selected SDK/language and material
limits. Make performance or token-cost claims only from measurements of the
complete task, including tool output and retries.
