---
status: current
applies_to: "toolchain 0.260.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Private TypeScript reference execution

`emitManagedReferencesPrototypeTypeScript` emits the checked
[private reference candidate](managed-references-prototype.md) through a dedicated
C++ API. It supports sequential source calls, `cell<T>`/`state`, immutable
snapshots, closures and typed source errors. It keeps one heap across all calls
within an entry execution and closes that heap on every exit.

Ordinary CLI/project versions and the public TypeScript emitter still reject
this private identity. There is no public language promotion, graph archival,
module/host reference ABI, browser-UI state contract or matching SDK release.
The private candidate advertises `typescript: true`; the ordinary published
`typescript_source_enabled` reference flag remains false.

## Selection and output

Use the source checkout's `include/nex/managed_references.h` and `nex/web.h`:

```cpp
auto program = parseManagedReferencesPrototype(source, path);
check(program);
auto module = emitManagedReferencesPrototypeTypeScript(program, "main", limits);
writeWebModule(module, outputDirectory);
```

The API requires the private identity and a fully checked program. The entry
takes no arguments and returns unit or an immutable wire-capable type. A cell,
closure or owned authority cannot escape to the host. Realm checks apply to the
reachable entry closure; unreachable server code is omitted. The private parser
still excludes single-unit imports, endpoints and task/parallel execution.
Toolchain0.259 accepts sequential server fs/ffi code for its reference/native
hosts; the browser emitter rejects reachable server/resource functions and
excludes unreachable ones.
Limits must be positive safe JS integers.

The [private module loader](managed-reference-modules.md) in toolchain0.257 also
supplies checked multi-unit input. Only reachable client/shared code is emitted;
the single-unit parser keeps its import rejection. Multi-unit maps add hashes
for reachable source units, and the private failure envelope copies file/line.

The generated module imports a separate boxed runtime and exports `main()`.
That function returns a private evaluation envelope: `kind`, `output`, an exact
`value_json` string on return, or diagnostic code/message/source line on failure.
It also reports heap counts before final collection, after collection and after
close. `value_json` follows the interpreter's JSON representation, including
full decimal i64 text; it is not a new version of NEX's public wire protocol.
Consuming the text must preserve integer width. No live managed value leaves
the execution context. The ordinary `entry` test adapter rejects this envelope.

The source map is `nex.private-typescript-managed-map/1`, with ephemeral source
locations and a text hash. It has no public revision or source-bundle identity.
`writeWebModule` supplies exactly these runtime sources:

- `nex-runtime.ts` and `nex-bytes.ts` for existing checked arithmetic, Unicode,
  byte and bounded JSON primitives;
- `nex-managed-heap.ts` for explicit graph identity/admission/collection;
- `nex-managed-context.ts` for source roots and completion ownership;
- `nex-managed-runtime.ts` for checked boxed values and source operations.

All five files participate in `webRuntimeInputs`. No npm dependency changes are
needed. The existing ordinary browser output keeps its original representation
and runtime imports.

## Values and roots

The [heap kernel](managed-reference-typescript-heap.md) distinguishes every
immutable data allocation, including equal strings. Weak metadata maps attach
text/bytes, nominal layouts and callable implementations to frozen heap nodes;
actual value slots remain explicit graph edges. Captured cells are closure-node
children, so keeping a closure also keeps its captures alive.

Operations preserve the reference/native allocation model where graph limits
make it observable: `str(strValue)` allocates a string node, byte updates wrap a
new byte node even when storage can be shared, and failure creation owns a fresh
message child. `error_code` and `error_message` create fresh strings. Reading a
cell retains its original immutable payload; writing replaces that cell's slot.

Lexical scopes root current parameter/local/pattern/catch bindings. Expression
scopes retain earlier operands while later operands execute, then release
consumed intermediates before the next expression. For example, with a one-cell
budget, `cell_read(cell_new(1)) + cell_read(cell_new(2))` can retire the first
temporary cell after its scalar value is read.

Unpublished builders root their current element vector across callbacks.
Publishing a list freezes and adopts the compiler-owned vector in place.
Construction remains linear and does not copy the completed vector. Published
list/record/enum values remain immutable.

## Returns, handlers and finalizers

Source returns and local `?` propagation use an owned return completion.
Source raises use an owned typed/legacy completion. A transport root retains
their payload while lexical/function frames unwind. A handler acquires its own
root before releasing the transport root; rejected filters, rethrow and nested
handlers preserve the same payload identity.

The pending completion stays rooted while a user finalizer runs. A replacement
return/error retires the previous completion before an enclosing finalizer or
handler runs. A handled packet retires at the end of its handler, including in
repeated loops. Keeping every handled payload until function exit would exceed
small cell budgets and is not the implemented ownership rule.

Fatal traps bypass source catches and user finalizers. Generated root cleanup
still runs. Uncaught source errors become `E_SOURCE_EXCEPTION` diagnostics
inside the owned context, before cells are invalidated; their payloads are not
exported. Normal returns and all checked error paths leave empty logical
registries. Physical JS memory reclamation still belongs to its host collector.

## Acceptance and remaining work

The shared hand-written corpus in `tests/managed_reference_cases.py` feeds
reference, native O0/O2 and strict executed TypeScript acceptance. It includes
alias/snapshot behavior, evaluation order, closure/operand roots, precise
temporary retirement, returns/replacement returns, handler filters/rethrow,
replacement source errors, fatal finalizer exits, builders and typed payload
shapes. Separate host-result cases preserve wide integers and immutable values.
Successful reference/TS executions also compare cell/node/slot/collection counts.
Every checked TS exit requires an empty registry after close; the reference
probe additionally requires its native live-object count to return to baseline.

[Focused evidence](evidence/managed-reference-typescript-0.253.0-2026-11-16.json)
records the actual tools, hashes, outputs, rejected API calls and affected
regressions. The preceding
[0.252 hosted core](evidence/core-ci-0.252.0-2026-11-16.json) qualified its own
source commit and heap-kernel stage, not this later emitter.

The next public integration must preserve old graph histories and define
reference entry/module/host lifetimes, nullability, debugger/profile data,
owned-capability interaction, synchronization and SDK/platform acceptance.
Browser UI state/effect contracts and worker transfer are separate integrations.
Class dispatch, mutable field/array layouts, Java numeric domains and Python
dynamic protocols/big integers remain in [migration readiness](migration-readiness.md).
