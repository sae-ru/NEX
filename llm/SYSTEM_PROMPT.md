# NEX coding contract

Write checked NEX programs using the selected compiler's public capabilities.
Plans, private kernels and old receipts do not establish source support.
Toolchain, project language, runtime ABI and platform acceptance are distinct.

1. Inspect the project, its tests and acceptance requirements. Preserve the
   language selected by `nex.json`. Create projects with `nex init PATH`.
2. Query `nex describe --kind index --json` once; request relevant fields with
   `nex describe --field PATH --json`. Keep compiler/descriptor identities
   consistent. If scoped discovery is unavailable, use `nex describe --json`.
3. Read `nex guide --kind quick --json` once when `llm_entry` is advertised.
   Fetch feature guides for concrete uncertainties. Use `nex help COMMAND --json`
   for flags and `nex explain CODE --json` for covered diagnostics. Do not invent
   source constructs, options or support; the old `features` list is partial.
4. Get bounded context with `nex context --symbol NAME`, then its needed types,
   imports and callers. Query `standard_library` before writing replacement
   helpers. Use actual callable signatures, generic bounds, effects and realms.
5. Make coherent source edits. Keep every acceptance rule, interface and budget.
   Graph patches need exact source/revision guards. Edit source templates, not
   generated specializations; preserve diagnostics and failed attempts.
6. Run compiler checks and affected tests. Check changed observable behavior
   through reference/native and applicable TypeScript execution, including
   rejected programs. Generation alone does not prove execution or delivery.

Arithmetic is checked; preserve left-to-right evaluation and short-circuiting.
Strings use strict UTF-8 and Unicode scalar indexing; bytes preserve octets.
Aggregates and ordinary captures are immutable snapshots. Genuine cells and
resources retain identity only within their advertised ownership boundaries.
Results are ordinary values; `?` propagates from the current function and
`unwrap` may trap. Source errors, fatal traps and cancellation are distinct.
User `finally` does not run for fatal traps/cancellation; runtime cleanup must
still retire owned values on every exit. Read the selected exception guide.

Effects declare required operations; they grant no OS or provider authority.
Keep client/server/shared realms and original resource grants. Browser output
contains only reachable client/shared code. Opaque authority cannot enter wire
data. Declare the caller/callback's complete effects. Use the relevant guide
before composing tasks, cells, IO, native images, devices or persistent UI.
Do not infer shared-memory parallel cells, worker reference transport or Java/
Python compatibility from a reference/task capability.

Read the relevant sections of `llm/DETAILED_CODING_RULES.md` for these contracts:
errors/contracts; graph/history; project/linking; web/server; task/resource/IO;
compute/devices; debugging/profiling. Discover each feature first and follow its
indexed guide, limits, ownership, ABI and pending integrations. Private source
experiments never enable ordinary syntax. Keep native code images and physical
work alive through value/resource retirement; cancellation is not completion.

Ordinary checks must not change a graph's selected language. Migrate explicitly
with a reviewed, revision-guarded plan; preserve namespace, IDs and old rows.
Changing a manifest version is not migration. Old captures require their matching
compiler/resources. Static linkage does not imply a fully static executable.

Commit source, tests, manifests, locks, contracts and required assets; retain
graph exports/snapshots when history matters. Keep credentials, keys, caches and
generated SDKs out of Git. Update dependency pins explicitly. Report actual
checks, source/build identities and remaining gaps. Measure complete accepted
work, including context, tools and retries: smaller text alone proves no token
or quality gain. Discover unsupported targets and keep them visibly pending.
