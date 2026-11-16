---
status: current
applies_to: "toolchain 0.260.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Owned resources in private reference graphs

The private candidate permits genuine files and opaque external owners in cells,
records, lists, Results, enums and closure captures. A server object can therefore
retain a file or native session in its changing state. Existing resource realm,
effect, identity and close rules still apply. Task capabilities, public source
selection, graph archival/migration and cross-request reference transfer remain
unavailable. No C/task ABI or public0.28/0.29 semantics change.

## Values, snapshots and authority

`cell_read` returns the current value with the same resource identity. It does
not clone a descriptor or cursor. Replacing a cell's payload preserves a retained
old snapshot and its original resource aliases. The aggregate's fields are
immutable; IO/close through an alias still changes that resource's state.

For the private C++ development parser:

```nex
module owned_file;
server fn main() -> i64 !{fs,state} {
  let source: cell<file> = cell_new(unwrap(file_open_read("input")));
  let old: file = cell_read(source);
  cell_write(source, unwrap(file_open_read("input")));
  assert(len(unwrap(file_read(old, 2))) == 2);
  assert(len(unwrap(file_read(cell_read(source), 1))) == 1);
  assert(file_close(old));
  assert(file_close(cell_read(source)));
  return 42;
}
```

A closed genuine owner remains a value with its existing identity. Debug-only or
empty fabricated file wrappers are rejected. Retention never renews an ended
file/foreign/request domain, makes a closed handle open, or grants another realm
or thread permission. Existing explicit `file_close`/`resource_close` affect all
aliases to that resource. JSON, ordinary host returns and browser emission still
reject owned/reference authority.

## Collection and teardown

The heap registers resource wrappers as leaf data nodes. Its ordinary external
root/edge accounting traces visible cells, aggregates and closure captures,
including cycles that retain files/native owners. Reclaiming a graph releases
these wrappers; the last actual resource owner triggers its existing physical
cleanup and settlement/executor policy. Independent resource aliases, borrowed
leases or retained snapshots may keep physical state alive longer.

Heap close invalidates cells and detaches their payloads, then releases registry
owners. It does not independently close a rooted immutable snapshot's resource;
the resource's own authority and aliases govern it. Source contexts still unwind
their source roots/error packets and close their resource domains. Normal, typed
source-error, Result and fatal exits retain their existing cleanup rules.

Resource quotas remain separate from heap node/edge limits. Garbage collection
does not promise prompt file closing or preemptible finalization; explicit close
remains the way to release a resource at a specified point. GC/adoption and
native destructors have no hard pause bound or separate source work meter.

## Native cleanup callbacks

Each heap operation pins its internal state and prevents operation/statistics
reentry from resource destruction (`E_CELL_REENTRY`). A callback may close or
destroy its heap owner. Close marks it unavailable immediately and defers registry
teardown until the active operation unwinds. An allocation interrupted by this
close cannot publish a new cell (`E_CELL_CLOSED`). Registry teardown retains the
genuine file/external destructors and allocates no tracing workspace.

Trusted C++ hosts must quiesce and close the context on its owner thread and must
not mutate adopted data or resurrect dead values during collection. Opaque native
object memory is not traced: source values retained inside it count as external
roots. Cycles hidden through arbitrary native object/callback state therefore
need explicit host ownership/close contracts; they are not source-visible GC
cycles. No user-defined source finalizer or C-to-source callback ABI is introduced.

## Verification and remaining scope

The C++ kernel fixture exercises real descriptors, snapshots, visible resource
cycles, revoked/closed owners, failed adoption, destructor reentry and a heap
destroyed from inside collection. Source fixtures compare reference and native
O0/O2 application/request execution using an independent C resource producer,
including caught/uncaught typed owned-cell errors and fatal cleanup. The private
TypeScript emitter rejects resource-bearing cells while preserving supported
client/shared reference semantics.

These are private development contracts. Public grammar/history migration,
complete imported-resource/component/task integration, class dispatch, source
debug/profile views and matching complete platform/portable SDK delivery remain
requirements of the original project plan.

[Focused0.260 qualification](evidence/managed-reference-owned-payloads-0.260.0-2026-11-16.json)
records the 30 kernel scenarios, 22 source programs/88 native comparisons,
retained source backends and moved installed-resource checks, with exact bounds.
