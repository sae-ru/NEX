# Explicit027 native source-error providers

Toolchain0.148 develops native delivery under explicit C++ source selection.
The ordinary CLI/default source language remains0.26 and `typed_payloads` stays
false. A0.27 project is checked with `ProjectBuildOptions::sourceLanguage` set
to `TypedErrors027`; this is not a manifest switch or implicit CLI upgrade.
Retrieve only this contract with `nex describe --field source_exceptions.typed_payload_development.source027_native_delivery --json`
and `nex guide --kind typed-error-provider --json`.

The graph migration and archival rules remain in [typed-error-migration.md](typed-error-migration.md).

The ordinary native builder emits a distinct public-ready task cohort7
(`0x4e45585400000007`) and uses the normal process entry. The explicit development
emitter retains2702. ABI3/4/5/6 and private2501/2502/2701/2702 preserve their
identities; mixed source-error cohorts are rejected before a continuation starts.
Descriptor size88 and ABI offset40 are unchanged. The requirement mask7967
still expresses task/server/file/throw requirements, not grants.

| Contract | Explicit027 format |
| --- | --- |
| Source provider | `nex.native-task-provider/14` |
| Profile provider | `nex.native-task-provider/15` |
| Logical-debug record format | `nex.native-task-provider/16` |
| Deferred application | `nex.native-task-application/5` |
| Static project plan | `nex.project-static-task-linkage/5` |
| Shared/profile/debug plan | `nex.project-task-linkage/14`, `/15`, `/16` |
| Imported continuation | `task-code/7` |

Source/static/fixed-shared/mixed execution shares one checked compiler/runtime
cohort, scheduler and root limits. Exact function/type/layout contracts and
physical image ownership are checked together. Provider records do not contain
error payload values. Typed values cross calls, suspension, filters, rethrow and
finally with their original type key, value and source position. Existing
resource/realm/lifetime checks remain mandatory; an error grants no authority.
File owners and callable payloads retain their original physical owners.
Provider parameters/returns still reject external/task/channel/scope/callable
authority, and imported function values remain pending interfaces.

Capture/replay preserves the checked0.27 source frontier and validates the new
record family. An old schema, language or ABI cannot be relabelled into that
frontier. Profile collection binds the same source/image ownership and verifies
settled managed-value pools. Uncaught process errors expose the generic
type/message/site, without implicit formatting of the owned payload.

Tests: `typed_task_protocol.cpp` exercises real resumed calls/public process
entry and physical cleanup; `typed_provider_records.cpp` checks strict new and
retained families; `typed_error_projects.py` executes actual source/static/
shared/mixed Debug/Release images, capture/replay and profiling.

Current full compiler regression, installed SDK/platform acceptance, bounded
typed debugger views, public027 CLI selection, graph-snapshot delivery and the
remaining original PLAN are still required. A parsed debug-record format alone
does not establish accepted debugger behavior. The prior0.147 full receipt and
the isolated pre-integration prototypes are separately scoped evidence.
