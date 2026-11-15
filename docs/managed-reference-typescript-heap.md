---
status: current
applies_to: "toolchain 0.253.0; no public source-language extension"
owner: repository
---

# Private TypeScript managed heap

[`web/nex-managed-heap.ts`](../web/nex-managed-heap.ts) adds a private graph
kernel matching the C++ [managed heap](managed-references-design.md). The 0.253
[private source candidate](managed-reference-typescript-prototype.md) uses it
with a boxed-value facade and explicit source roots. No ordinary generated
client imports this file. The private source candidate advertises
`typescript: true`; public reference flags remain false. This is not a public
JavaScript SDK or a Java/Python compatibility layer.

## Representation and ownership

`HeapValue` admits checked i64 (`bigint`), bool, finite f64, an immutable
`HeapNode`, or a `Cell`. Node kinds cover string, bytes, list, record, success,
failure, enum and closure. Each node has one frozen vector corresponding to
C++ `Data::values`; scalar members count as slots too. A cell has one mutable
payload slot, an identity and exactly one owning heap.

Even strings have explicit node identity. Reusing one source string allocation
in two cell payloads must count one string node; allocating two equal strings
must count two. JavaScript primitive string equality cannot recover that
distinction. This kernel therefore does not accept raw JS strings or ordinary
host objects as payloads. The checked value facade attaches text/byte content,
nominal fields, result layout and callable/capture metadata through weak maps.
For example, the C++ failure node contains one message-string child; its error
code is metadata, not another payload slot. The facade preserves that layout.
`HeapNode.publish` consumes a compiler-owned builder vector and freezes it in
place; ordinary construction keeps its defensive vector copy.

Creation adopts previously unregistered immutable nodes in child-first order.
Read returns the current payload alias. Write adopts the next immutable graph
and replaces the cell's slot. Existing immutable snapshots keep their contents.
Same-heap aliases compare by object identity. Foreign-heap cells are rejected,
including those nested in a new immutable payload. Ordinary immutable graphs
without cells can be shared by independent heaps; another registry owner counts
as an external root until that registry releases the node.

## Explicit roots

JavaScript's host collector cannot implement NEX's deterministic cell/node/slot
limits: its timing and weak observations are unspecified. The private kernel
uses explicit roots and its own registry instead.

`heap.frame()` creates a root frame with four operations:

- `track(() => binding)` observes the binding's current value at collection;
  returning `undefined` removes that binding's former root.
- `trackValues(() => buffer)` roots elements in an unpublished mutable builder
  or another compiler-owned vector without inventing a source list node.
- `keep(value)` retains an evaluated operand/return value until
  `clearTemporaries()` or frame close, and returns the same value.
- `close()` releases that frame's callbacks and temporaries. It is idempotent.

The private emitter brackets lexical/function frames with cleanup, registers
parameters/locals/pattern/catch bindings, and retains every evaluated heap operand
until its consumer owns it. In `f(make_cell(), collect_then_value())`, the first
argument remains a root while the second evaluates. Returns and pending source
error payloads have explicit transfer roots across frame cleanup. Closure
captures are actual graph edges. The [source execution guide](managed-reference-typescript-prototype.md)
describes their implementation and remaining public integration.

Root callbacks are compiler-owned observations, not source callbacks. Mutating,
collecting or closing the heap during root traversal is rejected. A failed root
traversal leaves the registry unchanged. Creation internally roots its initial
payload across capacity/threshold collection; write internally roots both its
receiver and next value. Other host references are not implicit roots in this
private graph API. A caller must register a value before expecting later
collections to retain it.

Collection traces live frames, operands, other registry owners and everything
reachable from them, including unregistered immutable outside containers. It
invalidates unreachable cells and releases unreachable registry entries. No
weak reference, finalization callback or explicit host-GC request decides this
logical reachability. Physical JS allocation and reclamation still belong to
the host; a zero registry count does not measure total JS memory or an RSS limit.

## Limits and teardown

Defaults and admission/automatic-collection rules match the C++ kernel:
1,048,576 cells, 4,194,304 registered nodes and 16,777,216 payload slots. Limits
must be positive safe JS integers. Retired immutable payloads count until
collection; a rejected write keeps its previous payload. Equal strings do not
collapse allocations. These are graph counts, not byte-memory bounds.

Adoption, marking, sweeping and close use iterative traversal. Close invalidates
all cells, clears the registry and retires root frames without invoking their
callbacks. Immutable outside snapshots remain immutable; cells inside them are
inert. The kernel is sequential and local to one JS realm. It supplies no worker
transfer, shared-memory model, owned-capability finalization or host ABI.
Every heap owner must call `close()` on all exits. Merely losing the host's heap
variable does not retire the explicit registry-ownership counts.

Collection cost includes the reachable unregistered root graph as well as the
registered graph; unlike C++, JS has no reference counts from which to infer
outside owners. No pause-time, throughput or Java/Python speedup is claimed.

## Verification and next integration

[`tests/managed_heap_typescript.py`](../tests/managed_heap_typescript.py) strictly
type-checks the runtime and driver, executes real TypeScript in Node, and compares
each trace step with the independently executed C++ kernel in
[`tests/managed_heap_trace.cpp`](../tests/managed_heap_trace.cpp). Hand-written
observations cover identity/snapshots, cells and slot limits, two distinct versus
one shared string allocation, failed-write preservation, external containers,
closure cycles, 96 cyclic objects with four retained roots, deep collection and
close. Eleven separate TS root checks cover temporaries, binding updates, builder
contents, return transfer, foreign heaps, retired frames and rejected values.
The C++ probe also requires native live-object accounting to return to baseline;
TS requires empty logical registries, without claiming host-GC byte measurements.

The [0.252 focused receipt](evidence/managed-heap-typescript-0.252.0-2026-11-16.json)
records the original ten-root-check kernel scope. The
[0.253 source receipt](evidence/managed-reference-typescript-0.253.0-2026-11-16.json)
adds in-place owned-vector publication and source execution. The
[corrected 0.251 core run](evidence/core-ci-0.251.0-corrected-2026-11-16.json)
passed macOS/Linux after the separate dependency-download correction; it did
not execute this new TypeScript kernel.

The private boxed facade, source lowering/root placement and source-error
payload handling are implemented and compared with reference/native O0/O2.
Public source
migration, module/host ownership, debugger/ABI/SDK and platform qualification
remain separate gates. Do not promote the private language identity yet.
