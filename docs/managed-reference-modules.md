---
status: current
applies_to: "toolchain 0.259.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Private reference source modules

`loadManagedReferencesPrototypeBundle` resolves and checks a transient group of
source files with the existing module loader. It extends the
[checked reference candidate](managed-references-prototype.md), keeping one
execution heap across calls and returns between those source units.
This is an internal C++ development API. No ordinary CLI version, stored graph,
dependency lock, public source archive or SDK language is promoted.

## Input and selection

The dedicated input schema is `nex.private-reference-sources/1`:

```json
{
  "schema": "nex.private-reference-sources/1",
  "entry": "main.nex",
  "files": {
    "main.nex": "module app; import \"./value.nex\" as value; fn main()->unit!{state,io}{let target:cell<i64>=value::make();value::change(target);print(cell_read(target));}",
    "value.nex": "module value; pub fn make()->cell<i64>!{state}{return cell_new(1);} pub fn change(target:cell<i64>)->unit!{state}{cell_write(target,42);}"
  }
}
```

Pass the parsed JSON value and a root for source locations to the C++ API in
`include/nex/managed_references.h`. The returned `Program` is already checked:

```cpp
auto program = loadManagedReferencesPrototypeBundle(input, sourceRoot);
auto result = evaluateManagedReferencesPrototype(program, "main");
auto mlir = emitManagedReferencesPrototypeMLIR(program, "main", false);
auto client = emitManagedReferencesPrototypeTypeScript(program, "main");
```

The example prints `42`. The root supplies locations; input source text comes
only from `files`. Imports cannot silently fall back to physical source files,
installed packages or a different language. All supplied units must be reachable
through the import graph. Relative, `std/` and package source keys
follow the loader's existing path rules; dependency files must be present in the
input. No physical `nex.json` or graph is read or written by this frozen loader.

Ordinary `loadBundle`/`loadVersionedBundle` do not accept this private schema or
language. `loadVersionedProgram` also rejects the private enum selection.
`revision`, `sourceBundle` and `dependencyLock` still reject every private
program, even one without cells. The single-unit private parser continues to
reject imports; imported source must use the explicit bundle API.

## Binding and execution

Each unit retains its own module identity and selected private language. Existing
import aliases, visibility, duplicate-module/import-cycle checks and public
signature rules apply. Functions, nominal types, trait bounds, associated types
and method references resolve through the shared symbol tables.

The private route binds partial nominal constructors such as
`left::Pair<cell<i64>,_>` to the selected module before specialization. Two
modules can each declare `Pair` without merging those types. Parameter-dependent
type defaults are bound in their declaration's scope. These corrections apply
to the private language only; retained 0.28/0.29 canonical identities and loading
behavior are unchanged.

A cell passed to an imported function is the same cell, not a copied payload or
a new module-owned heap. Returned cells, closures, generic aggregates, caught
errors and immutable snapshots retain their existing ownership rules. Collection
sees roots from all active source frames. Context close still follows source
owner cleanup on normal return, fatal traps and uncaught source errors.

The native candidate compiles all reachable source units into **one application
image**. The test fixture can load that image into a matching runtime, and also
links/runs the same generated LLVM independently at O0/O2. This does not define
separately compiled DLL/component reference passing or host-returned cell
lifetimes; those ABI/context contracts remain pending.

## TypeScript output and source attribution

Only reachable client/shared functions and required types enter generated code.
An imported but unreachable server function is omitted. No source text is copied
into the private map. For multi-unit input, `reachable_source_units` maps each
emitted function/type's source unit to a text hash. Changing an imported body
changes its hash even when the entry source stays identical. These hashes are
ephemeral source attribution, not public revisions or archival identities.

The private evaluation envelope copies the failure's source `file` and `line`.
It keeps typed data inside the execution context. Native tests compare failure
line and owning function/source hashes with the reference engine, including a
fatal trap and an uncaught typed source error in imported code.
The input/output browser adapters, UI state lifetime and public wire rules are
unchanged. npm dependencies, lock and notices are unchanged.

## Current boundaries and checks

Tasks, parallel execution, owned file/external cell payloads, database effects and
endpoints remain outside this candidate. Cells cannot leave the unit/wire host
entry. There is no cross-thread memory model, public migration, module/DLL host
ABI, source debugger/profile integration or matching portable SDK release.

Toolchain0.258's [private native request entry](managed-reference-requests.md)
can run this same checked module closure in a matching C++ `RequestScope`, with
one heap across its calls. It does not turn the source modules into independent
DLL providers or publish a new source/HTTP ABI.

Toolchain0.259 permits sequential server fs/ffi functions in the private checker;
the [resource coexistence guide](managed-reference-resources.md) records their
owned-value/context contract and its focused single-unit qualification. Complete
imported-resource, component and platform qualification remains separate.

`tests/managed_reference_modules.cpp` checks cross-unit state and module/archival
rejections. The fast existing reference probe also consumes a two-unit bundle.
`tests/managed_reference_module_cases.py` supplies the same manual programs to
reference, native O0/O2 and strict executed TypeScript. Cases cover aliasing,
snapshots, partial constructors with equal local names, trait methods/projections,
source errors/finally, cycles/returned closures, defaults/contracts, reachable
client output and imported-source attribution. Exact results are recorded in
versioned evidence after acceptance; these checks do not establish arbitrary
Java/Python project compatibility or full platform/SDK qualification.

[Focused0.257 evidence](evidence/managed-reference-modules-0.257.0-2026-11-16.json)
records16 passing core and13 affected groups. Ten module programs agree in
reference,20 native O0/O2 comparisons (40 actual machine executions including
independent executables) and10 strict executed TypeScript cases. The44 retained
single-unit TypeScript cases pass. Module frontend gates accept1/reject21 and
finish with no runtime values left live. Full platform/SDK gates remain separate.
