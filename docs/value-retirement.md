---
status: current
applies_to: "toolchain 0.255.0; language 0.28 and 0.29; private reference candidate"
owner: repository
---

# Deep immutable value retirement

Ordinary values and immutable snapshots retained after a cell heap closes use
the [atomic runtime value owner](value-owners.md). It preserves live/shared
snapshots and genuine owned/host destructors. Atomic last-owner admission and
an explicit stack-owned queue remove recursive descent through runtime payload
edges, including concurrent last releases. No cleanup workspace is allocated.
Cycles still require `CellHeap` tracing and mutable cell transfer remains
disabled across task/parallel boundaries.

`value_retirement_runtime` runs separate processes with a 256 KiB worker stack.
Cases cover 65,536-level values, closed-heap snapshots, shared tails, duplicate
edges, wide branches/base copies, a host destructor inspecting its children,
an owned file, exception unwind and concurrent root release. The probe forbids
C++ `operator new` on the retiring thread during cleanup; this is not an
interception claim for every platform allocator. Live values return to their
baseline. `value_owner_runtime` adds the atomic/weak, nested-call and hidden
module cases described in the owner contract.

The [0.254 receipt](evidence/value-retirement-0.254.0-2026-11-16.json) retains
the original 0.253 failures: eight scenarios failed with a 256 KiB worker stack
and all nine passed with 32 MiB. Toolchain 0.254 fixed sequential retirement
using unique-owner descent without enlarging `Data`; its check-then-drop
decision left a concurrent stack-bound gap. Toolchain 0.255 replaces that
mechanism with atomic admission and explicit queues. The earlier receipt
qualifies its original cohort only.

Public reference grammar/migration, entry/module/host ownership and matching
complete source/platform/SDK acceptance remain pending. The published 0.246.1
SDK does not contain these changes.
