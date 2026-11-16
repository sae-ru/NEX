---
status: current
applies_to: "toolchain 0.259.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Private references with files and foreign resources

The checked private reference candidate accepts sequential server `fs` and `ffi`
functions alongside `state`, typed throws and ordinary immutable values. This
composes the existing resource APIs with the same application/request reference
heap; it introduces no new file, foreign or task ABI and no public source version.
Ordinary CLI projects still cannot select this private candidate.

## Independent owners in one execution context

A source function may read bytes/text from a file into a cell, use a file or
foreign owner while updating a cell, or throw/catch a typed packet holding both.
Ordinary closures may capture these owners and cells in the same context. Existing
file cursor sharing, explicit close, Result failures, typed-error cleanup and
fatal skip-finally rules remain in force. Cell collection never becomes the
owner or finalizer of a file/external capability.

For example, this is input to the private development parser:

```nex
module counter_file;
server fn main() -> i64 !{fs,state} {
  let input: file = unwrap(file_open_read("input"));
  let count: cell<i64> = cell_new(0);
  cell_write(count, len(unwrap(file_read(input, 4096))));
  assert(file_close(input));
  cell_collect();
  return cell_read(count);
}
```

`cell<file>`, cell payloads containing opaque resources and equivalent concrete
generic substitutions remain rejected. The heap also rejects actual owned
values hidden in a closure's capture vector. A function type alone cannot
describe the ownership of all its captures; this runtime admission check remains
necessary. Closing a source owner does not make its wrapper a legal cell payload.

The existing FFI transfers only its supported typed call values. A `cell<T>` is
not a direct C ABI value. No new persistent C handle, invocation of source
callbacks from C, reference-valued host result, or cross-request transfer is
defined here. Owned values retain their existing call/request/resource domains.

## Host configuration and teardown

The private reference interpreter respects an enclosing explicit `FileScope`
instead of shadowing it with a new environment scope. Without one, its ordinary
standalone file environment remains available. Foreign calls require the existing
explicit `ForeignScope` and pinned host catalogue. Effects declare permission in
the source; the host must still supply actual capabilities.

Provider/contract failures in this private evaluator use the external declaration's
source location, matching the generated native adapter. Retained public evaluator
diagnostic locations are unchanged.

Generated applications retain their normal configuration wrapper. The private
[request entry](managed-reference-requests.md) uses the caller's explicit file
and foreign scopes and its request resource bindings. Repeated successful calls
may share cells within that request. Fatal failures end the request. Source
handles/error packets and their owned values retire before the reference heap;
its close does not extend resource authority or export values into a later
request. A completed write stays completed if a later operation fails.

## Browser and pending work

The private TypeScript emitter still rejects reachable server functions and
resource authority. Unreachable server code is excluded from emitted clients.
Browser cells remain limited to the supported shared/client value domain.
Database execution, task/parallel reference transfer, resource payloads inside
cells, class dispatch, public graph migration and matching full compiler/platform/
portable-SDK qualification remain separate requirements.

## Verification

`tests/managed_reference_resources.py` supplies manual programs with real files
and an independently compiled C resource producer. It compares reference,
native O0/O2 application and request execution, both matching-host images and
independently linked consumers. It observes retained snapshots, error packets,
Result/finally/fatal exits, actual closed files, external destructor counts and
zero live source values after context teardown. No converter is used.

[Focused qualification](evidence/managed-reference-resources-0.259.0-2026-11-16.json)
records the exact source/tools, 15 programs and 60 native comparisons, retained
backend groups, moved installed-resource checks, initial failures and limitations.
