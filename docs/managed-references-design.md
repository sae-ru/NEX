---
status: current
applies_to: "toolchain 0.254.0; no public source-language extension"
owner: repository
---

# Managed references: runtime foundation and remaining language work

NEX needs shared mutable objects to express Java object graphs and Python's
mutable containers faithfully. Ordinary NEX records, lists, bytes and closure
captures remain immutable values. A reference will provide explicit identity and
mutation without changing those value semantics.

Toolchain 0.249 introduced a **compiler-private C++ heap kernel**. Toolchain
0.250 adds an unarchived [checked/reference candidate](managed-references-prototype.md)
through dedicated C++ entry points; 0.251 adds a
[private native candidate](managed-reference-native-prototype.md).
Discover `managed_references` in `nex describe --json`:
`public_source_enabled`, `source_type_enabled` and `state_effect_enabled` are
false for ordinary published source languages. Ordinary project checking,
evaluation, MLIR and TypeScript paths do not enable the candidate. There is no public cell syntax, state effect,
wire representation, C ABI or new source-language version. Converters remain
deferred. This kernel alone does not establish Java/Python compatibility.

## Current ownership contract

[`runtime/nex_cells.h`](../runtime/nex_cells.h) defines `nexrt::CellHeap`.
One heap belongs to one execution context and its creating thread. `create`
returns a cell identity; `read` retains its current immutable payload snapshot;
`write` replaces that cell's payload. Aliases to the cell observe later writes,
while previously read immutable values keep their contents. Separate cells with
equal payloads have different identities. Printing a cell produces `<cell>` and
does not traverse its payload or expose a raw address.

`create`, `read`, `write` and `collect` reject foreign-thread use. A heap also
rejects cells from another heap, including cells nested in a payload. A copied
cell `Value` is an alias, not a copied payload owner. Base `Data` construction
and slicing cannot manufacture a valid cell.

Supported payload graphs contain ordinary i64/bool/finite-f64 values, strings,
bytes, lists, records, results, enums, closures and cells of this heap. Closures
can retain cells through their immutable capture vector. Owned files, external
resources, task scopes, tasks and channels are rejected pending a lifetime and
finalization design. Parallel and task snapshot boundaries also reject cells;
this is not a shared-memory concurrency implementation.

## Collection and deep teardown

The heap owns one registry reference to every adopted data node, including
immutable containers and closure captures. Adoption visits immutable children
before parents, using an explicit stack. Already registered same-heap cells are
graph boundaries. A cycle formed solely by caller-mutated immutable containers
is rejected; legal cycles pass through cells.

Collection counts the incoming strong edges inside the registry graph.
For each registered node, strong ownership beyond those edges and the one
registry owner denotes an external root. Such owners include source/host values,
immutable snapshots and objects inside unregistered external containers. The
collector marks everything reachable from these roots. Duplicate edges count
separately. It then detaches payloads of unreachable cells and releases
unreachable registry nodes in reverse adoption order. Removing mutable edges
first and releasing immutable parents before children allows cyclic graphs and
deep acyclic chains to retire without recursive graph destruction.

`close()` is idempotent execution-context teardown. It invalidates every cell,
detaches cell payloads and releases the registry in reverse order. It allocates
no tracing workspace. An outstanding cell alias remains an inert identity;
operations through the closed heap reject it. A rooted immutable snapshot
retains its value, although cells contained in it are invalid after close.
The host must quiesce execution before closing; cleanup does not grant a foreign
thread permission to use or mutate the heap.

The private C++ API trusts the existing immutable-value invariant: callers must
not mutate an adopted ordinary `Data::values` graph, forge a `Data::kind`, or
acquire an otherwise dead graph through a weak pointer during collection.
Weak observations in tests detect destruction; weak-reference acquisition,
resurrection and user finalizers are not a language contract. Native execution
contexts and libraries have not yet been integrated. The private reference
interpreter and native candidate each own their sequential execution context;
The private [TypeScript source candidate](managed-reference-typescript-prototype.md)
now implements boxed values, explicit roots and logical collection. Public
entry/module/host integration and migration remain pending.
Toolchain 0.254 adds [iterative ordinary value retirement](value-retirement.md),
including sequential snapshots released after heap close. Its exact-base factory
keeps genuine host/owned destructors intact without enlarging `Data`. Universal
concurrent retirement bounds and the public host-entry lifetime contract remain
separate integration requirements.

## Limits, costs and failures

Defaults are 1,048,576 cells, 4,194,304 registered data nodes and 16,777,216
payload `Value` slots. Slots include scalar members and each cell's payload.
They are heap-wide limits; retired immutable payloads count until collection.
Strings and byte buffers remain subject to their own value limits, so these
counts do **not** bound total byte memory. All limits must be positive.

The heap collects at an adaptive node threshold and retries collection before
rejecting cell/node/slot exhaustion. A rejected adoption or write retains the
previous cell payload. A replacement can still require room for old and new
payloads together, because old snapshots and registered nodes may remain live.

A read/alias is constant-time. Adoption visits the newly encountered immutable
graph; a write can adopt such a graph and can trigger collection. Collection is
O(registered nodes + payload slots), with O(nodes) tracing workspace and an
expected constant-time pointer index. Close visits the registry and its edges
without allocating the tracing workspace. These are algorithmic bounds, not
throughput or pause-time measurements against Java or Python. Efficient mutable
field/array storage remains future work; copying an immutable record on every
source field update is not a promised final object representation.

Errors use private `DataError` codes: `E_CELL_TYPE`, `E_CELL_HEAP`,
`E_CELL_THREAD`, `E_CELL_CLOSED`, `E_CELL_VALUE`, `E_CELL_GRAPH` and
`E_CELL_LIMIT`. They are not yet source catchable exceptions or public FFI
error contracts. C++ allocation failure remains a host exception.

## Verification scope

[`tests/cells.cpp`](../tests/cells.cpp), registered as `managed_cells_runtime`,
checks alias mutation and identity, immutable snapshots, cyclic record/list and
closure graphs, external roots, repeated collection/registry compaction against
an independent object-ID reachability oracle, allocation limits, rejected
transfers and foreign-thread/heap use. It also checks 65,536-cell chains,
32,768-cell close and a 65,536-level immutable payload. Live-value accounting
must return to its starting count. Rejected owned base constructors have a
separate accounting regression within the probe.

[Focused 0.249 evidence](evidence/managed-references-runtime-0.249.0-2026-11-15.json)
records 19 passing probe scenarios, 12 core groups, three affected groups and
documentation/pack checks. The existing 524-case Java int regression still
agrees across reference, native Debug/Release and strict executed TypeScript;
it does not exercise source references.

This C++ probe qualifies the private kernel only. It cannot establish
source-language type/effect checking, reference/native/TypeScript source
agreement, cross-thread object behavior, installed SDK or device acceptance.
Keep the matching evidence and earlier SDK receipts separate.

## Before public reference support

1. Qualify the private checked generic reference type, explicit mutation/read effects,
   equality, nullability, closure capture and observable evaluation order.
   Existing immutable values and checked arithmetic keep their rules.
2. Add versioned grammar, canonical graph formats and an explicit migration
   preserving old language histories. No existing graph is relabelled.
3. Implement and compare reference interpreter, native Debug/Release and strict
   TypeScript semantics, including rejected programs and all exit paths.
4. Give a whole execution context ownership of its heap across calls. Specify
   returned references, source errors, callbacks, modules and native-library
   entry lifetimes; a per-function heap would invalidate returned aliases.
5. Extend debugger/profile representation, resource accounting, ABI/wire
   rejection and installed language-pack discovery. Define owned-capability
   interaction before accepting resources inside reference graphs.
6. Qualify synchronization/visibility before cross-task/thread sharing. Class
   dispatch, initialization, mutable arrays, exception hierarchies, Python
   dynamic protocols and big integers remain separate prerequisites in
   [migration readiness](migration-readiness.md).

Public promotion requires a coherent compiler/backend/SDK integration gate.
The private status and false capability flags remain until those contracts
are implemented and verified.
