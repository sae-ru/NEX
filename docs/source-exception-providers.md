# Language025 source-error providers

The025 integration candidate uses public task descriptor ABI6
(`0x4e45585400000006`) across checked static archives and fixed shared images.
The layout remains88 bytes with the ABI word at offset40. ABI3/4/5 and the
private2501/2502 experiments keep their separate formats and meanings.
Discover `source_exceptions.source_providers` and the task-provider descriptors.
This development integration is not a complete SDK or platform acceptance claim.

Source code, exact function/type/effect contracts and one compiler/runtime cohort
remain required. `nex.build.json` selects ordinary source/static/dynamic edges;
`nex project --kind plan|build|run|profile|debug` uses the checked architecture.
The application owns one runtime, executor and limits. A fixed shared library
does not start another scheduler or reset the caller's budget/deadline.

Every function called within an025 task graph has a continuation, including pure
helpers and functions declaring only `throw`. Therefore an imported concrete
helper requires a selected public export even when it has no task effect. The
actual task bit is not fabricated for pure declarations. A pure library connected
to a task application also emits ABI6 descriptors. Source-only/synchronous
projects retain their ordinary native calling convention and explicit error path.

An escaping source error requires `throw` at its checked call site, or a lexical
handler. A handler in the caller can catch a source error from another static or
shared image. Rethrow retains its original payload/site. Spawned-child failures
cross the joined scope through the same source-error channel. Native traps,
cancellation, deadlines and Result propagation remain separate.

Owned values, including genuine File owners, retain their existing physical
grants and cleanup rules across these boundaries. A source exception releases
the abandoned frame and its file aliases. Effect declarations and image flags
are requirements, not grants. File access still needs explicit runtime authority.
External resources, imported function values/callback interfaces, binary-only
providers and arbitrary runtime load/unload remain unfinished interfaces.

For an ABI6 task-provider cohort, retained logical frames also cover a pure
component's concrete helpers. Their step symbols stay compiler-private; public
accessors and checked catalogs identify their physical owners. A component with
no declared task effect can therefore still have retained debug code.

Profile acceptance tasks retain the checked source union for plan12, including
source-absent replay. The application collector binds provider records11/12 to
the matching025 descriptor family and preserves their original image/hash pins.
Retained older records keep their own language/ABI checks. These are ordinary
CLI integrations; complete installed SDK/platform acceptance remains separate.

## Versioned records

| Contract | Ordinary025 format |
| --- | --- |
| Static/shared source provider | `nex.native-task-provider/11` |
| Profile provider | `nex.native-task-provider/12` |
| Logical-debug provider | `nex.native-task-provider/13` |
| Static project plan | `nex.project-static-task-linkage/4` |
| Fixed shared project plan | `nex.project-task-linkage/11` |
| Profile project plan | `nex.project-task-linkage/12` |
| Debug project plan | `nex.project-task-linkage/13` |
| Deferred application selection | `nex.native-task-application/4` |
| Imported continuation | `task-code/6` |

The provider requirement mask is7967: the existing source file bits plus4096
for a declaration with `throw`. Pure exports can have requirement0. The retained
31/799/3871 masks do not gain this bit. Header flags, component owners, load
closures, concrete source contracts and actual descriptor ABIs are checked
together. Relabelling an old record does not upgrade it.

The normative schemas are `llm/native-source-error-task-provider.schema.json`
and `llm/project-source-error-task-linkage.schema.json`. Ordinary acceptance tasks
capture the new records with their sources. Source-absent replay revalidates
ownership/contracts before rebuilding. Project actions do not open a graph store;
an acceptance-task run deliberately records its task history in SQLite.

Profile catalogs keep source components and physical image owners distinct.
Pure helpers are real logical frames, with original source sites and public025
expression context. Their debugger validates ABI6 and each image identity.
Complete debugger controls, full regression/sanitizers, installed SDK acceptance,
broader platforms and the rest of PLAN remain required before release acceptance.
