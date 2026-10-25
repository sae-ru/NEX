# Private language0.23 source write integration

The ordinary compiler/project default remains language0.22. Its stored histories,
parsers, task/provider ABI3 and mask31 retain their existing meaning. Language023
is an explicit internal parse/bundle/test entry point; there is no public023
project selection or implicit migration. Public publication requires the genuine
022 history-preserving migration, provider contracts and complete installed
SDK/platform/tool acceptance below. Query `task_file_writes_prototype`.

The prototype supports existing server `file_write_text(str,str)` and
`file_write_bytes(str,bytes)` calls in functions declaring both task and fs.
Their result remains `result<bool>`. An fs-only function remains synchronous
outside tasks. A task call cannot silently turn an fs-only helper into a
continuation. Streams, network/DB and task HTTP handlers remain pending.

The frontend checks argument/result/effect/realm contracts. TaskIR lowers a
write to a typed suspension after evaluating both arguments once left to right.
Native continuations use request ordinals13/14 following retained Foreign12.
Their88-byte descriptor uses explicit execution ABI4 and write/code-image bits;
ABI3 cannot acquire write bits. Legacy provider records remain ABI3/mask31 and
cannot be relabelled as write providers. Private023 static/shared output now uses separate ABI4 records5/6/7 and
explicit write-image metadata. Read task-write-providers.md; public CLI selection,
capture/replay/package and matching SDK/platform delivery remain separate.

The root native coordinator captures a revocable write grant only when its image
contains a write request, before child task resumes. Frames/helpers/closures
retain the context. The independent AST scheduler separately prepares and
admits typed requests through its mailbox, with no native frame/TaskIR pointer.
An explicitly supplied read grant does not authorize discovery of a write grant
from the environment. Without explicit host grants, evaluation captures its
authorized lexical/environment capability under the root request as before.

Both adapters use [the physical write foundation](task-file-writes-host.md):
exact immutable input snapshot, bounded IO workers/tickets/payload, revocation,
private temporary, fsync/rename, physical retirement and coordinator-only result
admission. Ordinary capability/path/file/size errors are typed results. Fatal
control/resource failures abort/drain and preserve first-fatal policy. Task
cancellation does not prove that physical IO stopped. Publication can race the
last pre-rename checkpoint: a complete committed file may remain when result
delivery is suppressed. No rollback or directory crash durability is promised.

Original1MiB file/4096-byte path limits apply. Bytes preserve all octets;
text validates strict Unicode scalars and preserves NUL/BOM. Input snapshots do
not retain hidden large backing slices on IO workers. Source-frame memory is
separate from declared transport payload credits.

Native and independent reference tests cover text/bytes, empty/max/oversized
inputs, snapshots, helper/generic/callable/capture, task/channel/scope transfer,
read-after-write, order, lazy branches, function-local result propagation,
ordinary errors, absent/read-only authority and checked imported modules.
TypeScript rejects reachable server code and omits unreachable server write
functions. Wasm gains no filesystem access. These source tests do not replace
the physical pre/post-commit cancel/revoke/drain host scenarios.

Before public023: complete explicit022 migration using real retained SDK
histories/all16 tables/schema/IDs, new static/shared provider contract and
capture/replay/package, public CLI/context/editor/debug/profile/spec/prompt/pack,
full regression, fresh relevant sanitizers, source-absent SDK/quickstart and
current native platform checks. Preserve old022 interpretation and reject
corrupt origins/targets/conflicts before partial history writes.
All original NPU/UI/mobile/Studio/converter/quality requirements remain open.
