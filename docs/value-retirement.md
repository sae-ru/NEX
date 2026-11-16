---
status: current
applies_to: "toolchain 0.254.0; language 0.28 and 0.29; private reference candidate"
owner: repository
---

# Deep immutable value retirement

Toolchain 0.254 removes recursive descent through uniquely owned ordinary
runtime values during sequential retirement. This covers ordinary source values
as well as immutable snapshots retained after a private `CellHeap` has closed.
It changes no source syntax, public language version, graph identity or ABI tag.
The corresponding compiler/runtime cohort must still be rebuilt together.

## Ownership and implementation

Source/runtime factories use `Data::make(kind)` and `Data::make(existing)` for
exact base `Data` allocations. The allocation family occupies the existing
private owner-family field; it adds neither a field nor a vtable. Public C++
base construction/copy remains available for trusted host subclasses and does
not mark a subclass as an exact base allocation. Owned byte/file/external/task/
cell types retain their genuine destructor and ownership-family checks.

`Data` retirement uses a depth-first loop. When a payload edge is the only
strong owner of an exact ordinary child, the loop drains that child's values
before releasing its final owner. The unused scalar of each dying object edge
temporarily stores the suspended parent link using `memcpy`. No live shared
node is modified. Completed children have an empty payload vector when their
actual shared-pointer destructor runs, so that descent has constant call depth.
No allocator, recursive traversal stack or auxiliary vector is needed.

A shared child loses only the retiring edge. A retained snapshot keeps its
contents and its normal identity. When its last sequential owner later retires,
the same loop handles its graph. Duplicate edges and branching graphs use the
same ownership rule. Cycles still require `CellHeap` collection; this loop does
not replace its tracing collector or accept caller-forged immutable cycles.

Host/owned subtypes are released through their real shared-pointer control
block. Their derived destructor and members run before the base `Data`
destructor drains their own child vector. No source finalizer or resurrection
contract is introduced. Trusted hosts must use `Data::make` for ordinary source
graphs; arbitrarily deep chains of custom host subtype finalizers are outside
this guarantee. Concurrent weak-pointer acquisition of an otherwise dead graph
remains outside the private heap contract.

## Concurrency limitation

Immutable source values can have owners on several workers. Real concurrent
release is covered by a regression scenario, and shared nodes are never drained
while another strong owner remains at the descent decision. This is **not** a
constant-stack proof for every concurrent last-release schedule: another owner
can disappear between a nonunique `use_count()` observation and the edge drop,
causing an ordinary nested destructor. A universal concurrent retirement bound
requires further lifetime integration before shared mutable references can be
promoted. The private reference candidate remains sequential and rejects task/
parallel cell transfer. Passing this regression does not close that requirement.

## Regression and evidence

`value_retirement_runtime` is in the no-Node core build/test layer. Its driver
runs each scenario in a separate process, with a 256 KiB worker stack and core
dump generation disabled on POSIX. Cases cover a 65,536-level ordinary graph,
a snapshot released after heap close, retained shared tails, duplicate edges,
wide branches and base copies, a real host destructor inspecting its children,
an owned file, exception unwind and simultaneous immutable-root release.
The deep scenarios span list/record/enum/result/closure allocations.

The probe forbids C++ `operator new` allocations on the retiring thread during
the measured cleanup interval and checks a zero live-value delta. This does
not claim interception of every platform allocator. The previous 0.253 runtime
failed eight sequential scenarios with a bounded-stack signal; the separate
concurrent scenario passed. With a 32 MiB worker stack the old runtime passed
all nine, confirming the depth-dependent failure. The
[focused receipt](evidence/value-retirement-0.254.0-2026-11-16.json) retains the
baseline controls and post-change outcomes.

Full source/platform/SDK qualification remains a later integration gate; the
published 0.246.1 SDK does not contain this change.
