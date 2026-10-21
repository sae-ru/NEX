# Shared native images: implementation work

The integrated0.72 compiler supports source and static archive project edges.
General shared-library project output remains pending. This design preserves
that public capability boundary while the implementation is tested separately.
Language0.16, checker rules and historical graph formats are unchanged.

## Object staging

The private native build API can select `positionIndependent` and `deferredLink`.
Deferred output requires both PIC and the checked project ABI. It preserves the
normal executable, test or HTTP entry contract and emits a deterministic object
archive named `objects.a`. The generated executable `main` wrapper is retained;
the mode does not turn an arbitrary function into an executable entry.

Each archive contains the actual verified per-function LLVM objects. Existing
binary dependency contracts exclude provider definitions from the consumer.
PIC participates in native function-object keys and the private runtime ABI, so
ordinary and PIC objects cannot silently alias in the cache or link together.
Deferring the final link does not alter those function keys: a later ordinary
PIC final link can reuse the same objects without recompiling LLVM IR.

Staging captures exact runtime sources, headers, hashes, component requirements,
selected toolchain, debug sources and dependency archives. It compiles no C++
runtime, HTTP bridge or application/profile identity. Those belong to the final
link owner. A stage receipt binds the object archive and captured inputs; it
does not describe any later manually linked executable or shared library.
Staging is currently restricted to macOS/Linux native targets. There is no
public staging command or `shared_library` project kind in this checkpoint.

`tests/native_staging.cpp` drives the production build API without installing a
new SDK command. Its Python acceptance test uses actual archive objects to link
two native libraries and one runtime, moves the complete runtime folder, and
checks immutable aggregates, snapshot callbacks, file aliases and trap cleanup.
It also checks ordinary/PIC cache separation, actual PIC object reuse, dependency
ABI rejection, corrupted receipt repair, and executable/server/profile staging.
These are implementation tests, not proof of final DLL provenance or packaging.

## Remaining final-link integration

The project planner must add checked `shared_library`/`dynamic` edges and ensure
all participating native objects use the same ABI. One runtime image must cover
the exact union of captured runtime requirements. HTTP hosting/bridges and the
final application/profile identity stay executable-owned. Provider keys depend
on their own source and actual image inputs; unrelated application edits must
not invalidate every provider. All final keys and image hashes use NEX BLAKE3.

Final-image completion records need typed static/dynamic/runtime inputs and
backward validation for historical six-file and archive completion records.
Debuggers must bind provider frames to captured image bytes/UUIDs; core capsules
must capture and relocate verified owned images. Profiling needs an explicit
tested executable identity binding. Packaging must preserve configured library
closure, licenses and relative loader paths without granting a notice bypass
for arbitrary images. Combined project run/test/debug/profile/package/task
flows and actual target execution remain required before full acceptance.
