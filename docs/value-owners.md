---
status: current
applies_to: "toolchain 0.255.0; language 0.28 and 0.29; private reference candidate"
owner: repository
---

# Atomic runtime value ownership

Toolchain 0.255 replaces the runtime's `std::shared_ptr<Data>` with
`ValueOwner<Data>` and its internal weak observer, `WeakValueOwner<Data>`.
This removes the 0.254 check-then-release race from graph retirement. Public
source syntax, immutable snapshots, cell thread affinity and graph formats do
not change. Mutable reference transfer, monitors, atomics and a Java/Python
memory model remain separate language work.

## Last-owner transition and stack bound

[`runtime/nex_value_owner.h`](../runtime/nex_value_owner.h) owns the complete
typed allocation. A strong reference is two pointer words. The control stores
an atomic strong state, an atomic weak count and a typed disposal action.
Ordinary and owned runtime factories coallocate the control and complete
object; custom raw adoption remains available at trusted C++ call sites.

Live strong states encode `(count * 2) + 1`. Every edge release performs one
atomic decrement; exactly the thread observing the transition from 3 to 1
queues destruction. There is no preliminary `use_count()` decision. A queued
control uses the same state word for an aligned next pointer, and an actively
destroying control uses it for its retirement-context pointer. These states
are even. Weak acquisition accepts only live odd states of at least 3 and
uses a compare/exchange increment, so it cannot acquire queued, destroying or
destroyed data. The implicit weak reference pins storage through completion of
the genuine destructor; remaining weak observers may then retain storage but
cannot revive the object.

Root release owns a small stack context and drains its queue synchronously.
The genuine complete-type destructor runs first. The base `Data` destructor
transfers its dying payload edges to that same explicit context. An edge's last
release only queues another control; it never recursively invokes the child's
destructor. The drain loop performs the next destruction after the current one
returns. Thus runtime `Value` graph edges do not add call depth, regardless of
which worker wins each atomic last release. Work is O(nodes destroyed + edges
released), with no separately allocated cleanup workspace.

Forward edge admission and a LIFO queue retire newly dead child subgraphs in
reverse payload order. Strong counts can reach zero before their actual queued
destructor runs. Source weak references/finalizers are not introduced by this
implementation. Cycles still require the private cell heap's tracing collector.

## Reentry, modules and resources

The queue is explicitly passed through each control and `Data` allocation;
there is no TLS recursion flag or module-local pending queue. A typed disposal
action in a separately loaded image uses its caller's context. This also avoids
depending on linker coalescing of inline/TLS symbols.

A host destructor can release an independent root or call a task API that
retires roots. Such releases own separate contexts and finish before those
calls return. The outer queue remains valid. This preserves task/scope
publication fences and physical resource cleanup, rather than deferring the
last root's work until a later event loop turn. Host-derived destructors see
their own payloads intact; base cleanup occurs afterward.

The stack bound covers runtime payload edges. Arbitrary recursive C++ member
destructors and host callbacks are not converted into NEX graph edges. A custom
raw-adoption deleter must end the complete object's lifetime; a borrowed object
with a no-op deleter is unsupported. Code images must outlive their allocation
actions, including surviving weak controls. This private C++ lifetime contract
is not a public host-returned-reference or unloadable-module ABI.

## Layout and runtime cohort

On the recorded 64-bit macOS build, `ValueOwner<Data>` remains 16 bytes and
`Value` remains 32 bytes. `Data` gains one control pointer, increasing from
104 to 112 bytes; the control is 24 bytes. These are C++ sizes, not allocator
bucket sizes or a total-memory bound. Known owned wrappers now coallocate,
including task/reference/external wrappers that previously used separate
object/control allocations. Performance must be measured with matching source
programs; no universal speedup is claimed.

`ValueOwner` cannot be binary-interchanged with `std::shared_ptr`. All C++
runtime images must be rebuilt as one matching cohort. Native runtime/core/
shared ABI fingerprints now include the owner header, preventing reuse of
older cached runtime objects. Public C handles remain opaque; source/task tags
retain their versions. The debugger reads the new pointer member through the
actual DWARF layout and keeps its old shared-pointer fallbacks for old images.

## Acceptance

`value_owner_runtime` is a no-Node core group. It covers strong/weak conversion
with a nonzero base adjustment, self assignment/move, constructor failure,
weak storage pinning and observation of a queued object, synchronous nested root retirement,
weak-lock races, a 65,536-node alias ladder released on two 256 KiB workers,
and deep graph retirement across a genuinely hidden-symbol module boundary.
Both host and module live-value counts must return to their baselines.

The [focused receipt](evidence/value-owners-0.255.0-2026-11-16.json) records
16 core groups, 23 affected groups, six passing integration groups plus two
LLDB/DAP groups that passed outside the initial restricted launch context.
The original launch failures remain recorded. The shared source corpus agrees
in 72 native O0/O2 comparisons and 38 strict executed TypeScript cases.

The bounded-stack value suite also passes with C++ allocation forbidden on the
retiring thread. A normal local CMake installation was moved to a Unicode path;
its installed headers/tests rebuilt both owner probes, and the standard library
passed reference plus native Debug/Release consumption with unchanged locks.
This local relocation depends on the host toolchain/libraries. Full source/
platform/portable-SDK qualification remains an integration gate.

Two source programs constructing and retiring 65,536-level graphs were measured
as whole O2 processes on this Mac, with two warmups and ten interleaved samples
per binary. The source bytes match across both toolchains:

| Program | 0.254 median | 0.255 median |
|---|---|---|
| Normal return | 14.459 ms | 13.764 ms |
| Typed source unwind | 14.775 ms | 14.228 ms |

These short measurements qualify only the recorded programs, binaries and host.
The receipt retains every sample and the object-size increase.
