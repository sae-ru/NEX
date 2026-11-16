---
status: current
applies_to: "toolchain 0.258.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Private native reference execution

`emitManagedReferencesPrototypeMLIR` extends the
[private checked reference candidate](managed-references-prototype.md) with
MLIR/LLVM generation through its dedicated C++ entry. Ordinary source versions,
CLI builds, stored graph formats and migration remain separate. The dedicated
[TypeScript candidate](managed-reference-typescript-prototype.md) is implemented;
Wasm/device reference lowering and native reference module/host ABIs remain
pending. This candidate does not qualify a public SDK.

Toolchain0.257's [private source modules](managed-reference-modules.md) use this
same emitter/context across imported source units in one generated application
image. Separate component/DLL reference ownership remains pending.

The checked unit uses the existing native emitter and its verifier. `cell<T>`
uses an owned heap handle. Scalar helpers preserve the i64/bool/f64 value tag;
aggregate/closure helpers retain the immutable payload. Calls evaluate once in
source order, and reads/writes preserve alias identity and snapshot values.
Typed source handlers identify the complete `cell<T>` type and retain its
original cell object. Source functions may return cells and closures to callers
inside the application.

The native application entry takes no arguments and returns unit or an i64
process status, following the existing native entry convention. It does not
export a cell to a C host. The private reference C++ evaluator's wider unit/wire
JSON result convention remains a separate interface.

## One owned execution context

The base runtime has one opaque reference attachment on its application owner.
It is created synchronously by the private helpers, using the emitted cell/node/
slot limits. Function ownership scopes borrow the same context; a function return
cannot close its caller's heap. `cell_collect()` traces current owned values.

Normal finish releases the attachment before checking live-value accounting.
Application unwinding first retires source function/handle owners, then closes
the heap, including fatal traps and uncaught source errors. A private uncaught
source packet drops its payload while the context is still alive and retains
its copied diagnostic fields. Ordinary applications without a reference context
keep their source-packet behavior.

An attachment cannot be reconfigured after creation. Reuse checks the exact
factory/destructor pair, creation cannot reenter, and closed contexts cannot
revive during teardown. Failed creation can retry before the context ends.
A separate [private request entry/context](managed-reference-requests.md) in
toolchain0.258 shares the checked source closure without an application wrapper;
its matching C++ host owns request limits, source-error slots and teardown.
Heap/thread checks and task/parallel rejection remain in force. Public module/DLL context
ownership, host-returned references, synchronization, debugger/profile views and
the shared mutable memory model still need their own integration.
The 0.255 [atomic value owner](value-owners.md) covers deep snapshot retirement,
including concurrent immutable owners, without enabling cross-thread cells.

The base runtime stores a payload pointer and a no-throw destructor, so its
ordinary native runtime has no link dependency on the private cell implementation.
The compiler fixture links the exact cell implementation and exports its private
helpers to generated images. A different runtime cohort cannot be substituted.

## Development checks

`tests/managed_reference_native.py` reuses the source cases and expected outputs
from the core reference probe. The private C++ fixture checks source, retains
MLIR before lowering, then compiles generated LLVM to a native image for each
Debug/Release setting. The matching host runs that image and checks final live
values after success, typed errors and traps. It covers aliased state, closures,
snapshots, cycles, scalar tags/bytes and heap exhaustion.

The same emitted LLVM also links to independently compiled base runtime/cell
objects, separately at O0/O2, and runs as an executable without the compiler
host. Archive installation and SDK relocation remain additional gates.
Preserve failed IR/logs and record matching source/compiler/
runtime identities; a passing emitter or fixture is not public acceptance.

[Focused 0.251 evidence](evidence/managed-reference-native-0.251.0-2026-11-16.json)
records 26 O0/O2 comparisons, each through both the matching host image and an
independent executable. All 26 executables depend on the recorded Mac's
`libc++`/`libSystem`, with no LLVM/MLIR runtime dependency. Source errors retain
code/message/line; fatal codes/reported lines match the reference. Live-value
accounting returns to baseline on normal, source-error and trap exits.
Fourteen core groups and eight affected groups passed, followed by the final
native/context recheck. These scopes do not qualify Linux/Windows execution,
public project/module builds or the complete installed SDK.
