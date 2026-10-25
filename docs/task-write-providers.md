# Language023 static/shared whole-file write providers

Ordinary023 CLI projects build separate task writers through static archives or
fixed startup-linked shared images. Retained022 source and ABI3/mask31 records
keep their old meaning. Use explicit migration for old graph HEADs. Complete
compiler/SDK/platform acceptance remains distinct from enabled implementation.

## Versioned code and image requirements

Language023 descriptors use execution ABI4 with the same88-byte layout and
40-byte ABI offset. Plain, profiled and logical-debug provider records use
`nex.native-task-provider/5`, `/6` and `/7`. Their strict parser and
`llm/native-write-task-provider.schema.json` preserve the old1/2/3/4 contracts.
Old records cannot acquire writes by relabelling a language, widening a mask or
adding new fields. ABI/cohort, actual source contracts and physically owned
exports must match before native artifacts are published.

The new provider mask is799: retained task/server/fs/read/image-read bits plus
write256 and image-write512. Standalone source FFI bits32/64/128 remain forbidden
in binary provider exports. A task/fs declaration grants permission to request
checked reads/writes; it never supplies an operating-system capability.

`task_file_writes` describes an actual reachable write suspension in the checked
image closure, independently of the retained broad read-support flag. Build
keys, runtime requirements and application identity record the write flag and
execution ABI. Unreachable writes and read-only task images keep the flag false.
Shared records retain explicit per-component read/write flags and physical
ownership. New root application stages use `nex.native-task-application/2` with
explicit execution ABI and write requirement; retained four-field stages cannot
acquire writes. The write adapter header participates in the checked cohort.

## Authority and physical completion

There is one final runtime, root request and coordinator-captured write grant.
Code-only provider archives supply descriptors and machine definitions, not
independent executors or operator grants. Fixed shared images use the same root
host context; dependency source remains available to the checker while actual
calls consume the separately built machine implementation.

No File, callable, task/scope/channel or opaque resource authority is added to
the binary export signature. Text/bytes/results use the checked immutable value
ABI. Preparation snapshots exact input bytes; IO cleanup settles before typed
publication. Cancellation may suppress a result after a complete rename, with
no rollback or directory crash-durability promise. Read-only or missing root
authority returns the ordinary checked capability result.

## Verification and remaining delivery

`task_write_provider` executes static/shared native and independent reference
programs in debug/release/profile and logical-debug metadata configurations,
including text/NUL/Unicode, binary data, read-only and unreachable-write images,
and denied write authority. Boundary checks reject old/new ABI relabelling,
foreign bits, malformed flags and mismatched component/root requirements.
Logical-debug metadata construction/execution is separate from an actual DAP
session; profile output is separate from a complete CLI profiler workflow.

`public_task_write_delivery` additionally checks ordinary023 CLI selection,
versioned project plans and three static/shared/mixed projects, including
source-deleted packages and reviewed capture replay. Three genuine022 SDK131
revisions migrate without losing original rows/schema/IDs. Broader genuine
migration histories, matching full tests, fresh relevant sanitizers, installed
SDK and current Linux/stand acceptance remain required. This provider step does
not finish streams/network/DB,
owned NPU/models, native UI/mobile/platform delivery, Studio or quality measures.
