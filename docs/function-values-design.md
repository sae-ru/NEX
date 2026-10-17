# Function values and closures — implementation in progress

This document records the next language milestone. It is not an implemented
capability list. The released checkpoint remains 0.22 / language 0.9; query the
compiler descriptor and `STATUS.md` before authoring applications.

## Semantics

- Function types contain value parameter types, result, declared effects and
  execution realm: `fn(i64)->i64`, `fn(str)->unit !{io}` and
  `server fn(str)->result<str> !{db}`. Parentheses around a returned function
  type distinguish its effects from its caller's effects. Canonical type text
  parenthesizes a returned function type to bind its effects unambiguously.
- Named functions are values, with explicit generic specialization or inference
  from an expected function type. Test functions and bare builtin/nominal
  constructors cannot be taken as function values. A lambda uses
  `fn(x:i64)->i64 { return x+1; }` and may explicitly declare a realm/effects.
- Calls accept any function-valued expression: parameters, locals, returned
  functions, fields and list elements. Callable locals take precedence in named
  calls; non-callable locals preserve NEX's existing separate global-call
  namespace. Parenthesized/expression callees must themselves have function type.
  Evaluate the callee first and arguments left to right, once each.
  Check indirect calls against the function type's effects and realm.
- Capture each free lexical value by immutable snapshot when the lambda is
  created. A captured `var` cannot be assigned inside that closure. Its later
  outer assignments do not change the captured snapshot. Inner lambdas can
  capture outer parameters/locals and transitively capture a grandparent's
  value. Initializers cannot capture their own not-yet-defined binding; ordinary
  named recursion remains available. Immutable aggregate sharing and automatic
  ownership make captures a DAG, with no new reference cycles.
- Function values can be returned, reassigned and stored in immutable generic
  aggregates. Equality is value-object identity, consistently across native,
  reference and TypeScript execution, not extensional function equivalence.
  Copies retain identity. Text formatting is opaque and deterministic, without
  exposing a native address. JSON/API boundaries reject function values,
  including nested function fields. Parametric serialization needs an explicit
  recursive `wire` capability so an unconstrained parameter cannot silently
  promise serialization of every new function type.
- Reject client/server privilege changes through callbacks, including function
  references and lambdas. Browser reachability follows the actual reachable
  creation/call graph and must not include unrelated possible callback targets.

## Representation and lowering

Use an owned `Data::Closure` handle containing a native code pointer, logical
target name and ordered immutable captures. Append the new kind/layout metadata
and version the debugger runtime-view contract. Preserve all existing object
cleanup, request unwinding and profiler allocation behavior.

Every native closure entry has signature `(environment, explicit arguments) ->
result`, with the same checked scalar/heap result convention as existing NEX
functions. Named references use a bridge to their ordinary function; lifted
lambdas read their captured fields from the hidden environment. Indirect calls
use LLVM's typed indirect call, retaining the closure and arguments until the
call completes and cleaning owned temporaries afterwards. Imported references
must link the bridge in the defining source module; bridge/signature/capture
layout changes must invalidate their consumers.

The MLIR experiment under `build/closure-abi-probe` passed the exact existing
arith/func/memref/cf/LLVM conversion pipeline with verification enabled. It
captured 41 in an environment, passed 1 through an actual function pointer,
returned 42 in a real native executable and passed LLVM verification. No dispatch
over a guessed whole-program function set is needed.

The reference interpreter uses the same logical target and immutable captured
values, without a native pointer. TypeScript must capture values as IIFE
arguments, rather than accidentally retaining mutable JavaScript variables by
reference. Use function-object identity consistently in all three paths.

Lifted lambda bodies are derived functions with explicit owner/capture metadata.
Their source parent includes the complete checked lambda body in its canonical
expression; exclude generated lambda definitions from top-level revision input,
as with generic instances. Watch-only generated lambdas must not change the
archived program revision. Derive stable lambda names from their lexical owner
and source traversal ordinal, with separate names for watch expressions.

## Required integration and evidence

Keep the checker, interpreter, native and TypeScript emitters, generic cloning,
module/name binding, operation/binding graph, visibility, API projection,
incremental cache interfaces, profiling and debugger capture/validation in sync.
Keep explicit unsupported proof statuses for new non-scalar operations. Extend
the matching coverage checker conservatively for an opaque callable domain.

Pure watch-created closures should use lazy captured values. Stopped callable
values must be decoded through their checked logical target/signature and exact
capture metadata, not by executing a pointer in the inferior. Missing/invalid
captures remain explicit errors. Never trust a snapshot to downgrade an
effectful or server-only target to a pure/shared function type.

Before release: differential tests for named/higher-order/generic/returned and
nested closures; immutable snapshot/shadowing behavior; identity and formatting;
argument order, short circuit and checked traps; rejected signatures, effects,
realms, JSON and private types; native cleanup for returns/loops/failing guards
and request traps; archived patches/imports/exports; persistent operation edges;
actual LLDB/DAP captures/offline replay and profile attribution; browser
reachability/interaction; installed/source-free SDK acceptance on each exercised
architecture. Keep unsupported OS/device targets visibly pending.

The old 0.22 SDKs are preserved for macOS and both Linux architectures. The
genuine language-0.9 SQL/JSON fixture was produced by that compiler before any
function-value implementation edits. The source-language change needs explicit
history-preserving migration and unchanged reviewed task/proof intent. The
discovery descriptor's stale unsupported entries for already implemented match
and generic-constraint capabilities also need removal.

## Current prototype evidence and next integration

The ten maintained tests in `tests/function_values.py` passed in the
reference interpreter, debug/release native output and TypeScript, including
cross-module bridge invalidation and hidden-name collision checks. All 23 CTest
suites passed (211 cases in 237.09 seconds) in
`build/function-values-prototype-ctest-verified.log`. The prototype
under `build/function-values-prototype` also prints the expected eight 42 values,
identity booleans, opaque function text and captured Unicode string, with clean
native exit. A real TypeScript/Vite application storing a closure in its State
built and passed the existing interaction scenario in Chromium, Firefox and
WebKit; its unreachable server sentinel is absent from assets/maps. This does
not complete the milestone. Current source/toolchain/canonical version labels
have deliberately not been published as a new release yet.

The first full regression found the existing contextual `match` case where a
non-callable local and a global function share a name. Named calls must retain
the old function namespace in that case; only a callable local should redirect
the call. That fix and removal of unnecessary native bridges passed the full
suite. Required bridge names now enter their defining module's cache contract,
so introducing a reference in another module cannot reuse an object lacking its
bridge. Derived closure names contain a source-forbidden `$` component and use
hashed native symbols, avoiding collisions with functions and nested modules.
The original collision failure and repaired output remain under
`build/function-collision-evidence`. Keep a running
test process's binary/resources unchanged while observing its terminal result.

Debugger integration requires a separate debug-value codec/schema; application
JSON must continue rejecting callables. A callable partial shape can name its
checked target and carry an identity token. Target signatures, realm/effects and
capture layouts must be validated against archived checked source. Capture paths
then descend by the selected target's capture names/types. Read captures lazily,
so invoking a closure that uses one field does not fetch an unrelated large
payload. Alias identity must survive snapshot decoding; conflicting target/data
for one identity must be rejected. `WatchValues::concrete` must not accidentally
clone closure identity, and a watch invocation must resolve a callable proxy
before choosing its logical target. A captured pointer must never be executed
inside the debuggee.

Remaining integration includes updating native runtime-view metadata/formatter,
frame validation/planning, DAP children and JSON schemas, context/derived edits,
all function-type traversal sites, documentation of the implemented `wire`
implications (integer/ordered imply wire), remaining core/type
limits, proof unsupported statuses and API projections. Finish source language
0.10/toolchain 0.23 and canonical function/program versioning with a genuine
0.9 migration test, then synchronize the specification, grammar, descriptor,
prompt/pack, task/proof examples and installed/source-free SDK workflows. Retain
the original full-platform scope and explicitly pending capabilities.
