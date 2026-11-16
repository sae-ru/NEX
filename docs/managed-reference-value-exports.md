---
status: current
applies_to: "toolchain 0.261.0; private 0.30-refs-prototype candidate"
owner: repository
---

# Managed TypeScript host-value entries

`emitManagedReferencesValueTypeScript` prepares the private reference candidate
for browser-host integration. Its generated functions accept and return the
ordinary immutable TypeScript value representation. Source functions can use
cells internally; each invocation owns one sequential heap and closes it before
the host receives its copied result. No live reference leaves that context.

This is a private C++ API, with no public source promotion, graph archival,
history migration, UI adapter, persistent browser state or worker transfer.
Ordinary language0.28/0.29 projects keep their existing semantics and emitters.
The published portable SDK0.246.1 remains unchanged.

## Generate a module

Parse/check a private unit or use its checked module-bundle loader:

```cpp
auto program = parseManagedReferencesPrototype(source, path);
check(program);
auto module = emitManagedReferencesValueTypeScript(
    program, {{"increment", "increment"}, {"snapshot", "snapshot"}});
writeWebModule(module, outputDirectory);
```

For imported units, select the actual checked qualified function names. Export
aliases use the existing TypeScript identifier rules. All source functions must
be checked. Reachable exports must be concrete client/shared functions, with no
implicit captures. Only reachable client/shared code is emitted; unreachable
server functions and their source text remain absent.

For example, this private source function:

```nex
fn increment(value: i64) -> i64 !{state} {
  let stored: cell<i64> = cell_new(value);
  cell_write(stored, cell_read(stored) + 1);
  return cell_read(stored);
}
```

exports an ordinary `increment(value: bigint): bigint`. Calling
`increment(9007199254740993n)` returns `9007199254740994n` with full i64 precision.
The checked fixture also covers records, enums, bytes, lists and Results:
[`value-exports.nex`](../tests/fixtures/managed-references/value-exports.nex).

## Inputs and returned values

| Source type | Host representation |
|---|---|
| `i64` | Checked `bigint`; no string/number coercion |
| `f64` | Finite `number`, with ordinary NEX zero normalization |
| `bool`, `str` | Exact primitive kind and strict Unicode string |
| `bytes` | Existing immutable `nex-runtime.ts` ByteBuffer |
| `list<T>` | Immutable copied array of checked elements |
| Record/enum | Existing nominal TYPE/CASE brands and checked field layout |
| `result<T>` | Existing branded success/failure representation |
| `unit` result | `undefined` |

The generator emits exported host nominal types separately from internal boxed
types. Compiler-produced wire schemas appear in `host_entry_contracts` in the
source map. Hosts may construct correctly branded values with the ordinary
runtime or decode them using that schema. An unbranded object is rejected.
TypeScript signatures catch ordinary static mistakes; executed boundary checks
also reject mismatched arguments supplied by JavaScript or reflection.

Input fields are checked and copied once into an immutable snapshot, then
converted to the private managed representation. Each argument becomes a source
root before the next argument is evaluated. Ordinary host mutation after a call
cannot change its returned snapshot. Result conversion finishes while source
roots and the heap are still valid. The copied host value remains usable after
collection, heap close and subsequent invocations.

Each argument/result retains the ordinary wire bounds: 1MiB encoded bytes, depth64,
10000 elements per collection and100000 visited value nodes. Existing finite
number, checked i64 and strict Unicode errors remain distinct. Structural kind
or nominal-layout mismatches report `E_CELL_HOST`. Heap limits remain independent
and do not measure total physical JavaScript memory.

Cells, callables, task authority and owned resources are rejected in host entry
signatures, including nested types. An internal closure or cell can participate
in computation and typed errors, but cannot be exported as a host value.

## Completion and context ownership

The export returns the actual host value. It does not return the diagnostic
envelope used by `emitManagedReferencesPrototypeTypeScript`; that older API
retains its no-argument entry and heap-statistics contract.

Source `print` calls reach `console.log` synchronously. Output before a trap or
uncaught source error is preserved. Uncaught source errors become independent
`NexError("E_SOURCE_EXCEPTION", ...)` diagnostics inside their context; their
live typed payload is released. Fatal errors keep their original category.
File, line, column and operation-site data are copied when available. Error
objects contain no reference to the source completion or its heap.

A host output observer may invoke another generated export synchronously. That
call gets its own context and restores the enclosing context on return or error.
An exception raised by the host observer propagates after generated ownership
cleanup. The next invocation starts with a fresh context. Host imports/returns
are synchronous; promises and persistent closures are outside this contract.

## Verification and next integration

`managed_reference_value_exports` runs the existing hand-written source corpus
against reference execution and strict, executed TypeScript, using ordinary
value exports twice per case. Additional argument tests compare reference output
for all supported shapes, check 64 repeated invocations, nested host calls,
static type diagnostics, argument rejection and recovery after fatal/source
errors. `managed_reference_module_value_exports` repeats imported module cases
and checks reachable-only output. The old envelope and heap-kernel suites remain
separate regressions.

[Focused0.261 evidence](evidence/managed-reference-value-exports-0.261.0-2026-11-16.json)
records16 core and11 affected groups,54 new reference/TypeScript comparisons,
argument/reentry/error checks and a relocated normal installation. These scopes
do not establish full source/platform or portable SDK qualification.

Public0.30 still requires normal project/version selection, canonical graphs,
history-preserving migration, complete backend/entry integration and qualified
task/component/debugger/SDK boundaries. Persistent UI state needs an explicit
context-lifetime contract; per-call exported values do not establish it.
