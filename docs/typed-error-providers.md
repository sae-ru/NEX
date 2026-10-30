# Native source-error providers (language0.27)

Toolchain0.151 develops checked native delivery through the ordinary027 CLI.
The ordinary CLI/default source language is0.27 with typed_payloads enabled.
Explicit migration preserves older graphs; a manifest edit alone cannot upgrade
them. C++ callers may still select retained languages explicitly.

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

Explicit C++027 debug builds additionally capture the matching formatter and
checked source bundles. Synchronous DWARF and task LLDB/NEX-DAP views expose typed
catch values and legacy bindings in ordered handler chains. Guard caller frames
and catches after yield preserve their checked scope and source/image ownership.
Bounded list/string reads retain ordinary wire representations, including Unicode
and NUL. Original source files may be absent during inspection. File watches
expose only diagnostic identities; IO/effectful watches and stale views reject.
`tests/typed_error_debugging.py` exercises actual source/static/shared/mixed LLDB
and NEX-DAP, a large generic list, legacy catch, file owner and synchronous DWARF.
Source-language diagnostics and their IDs use the captured program language;
the ordinary diagnostic API retains its existing default identity.

Current full compiler regression, installed SDK/platform acceptance and the
remaining original PLAN are still required. Parsed debug records alone do not establish debugger acceptance. The
`logical_debugging_development` descriptor records this checked development scope;
`logical_debugging_accepted` remains false until the wider delivery gates pass.
The prior receipts retain their own compiler/source/version scopes.
