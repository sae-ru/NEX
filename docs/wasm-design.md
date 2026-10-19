# Scalar WebAssembly design history

This records the proposal that preceded the isolated 0.60 implementation.
The current command and supported bounds are documented in [wasm.md](wasm.md).
Seven draft backend tests and the example in Chromium, Firefox and WebKit pass;
complete matching regression and installed/portable SDK acceptance are pending.
The following feasibility notes describe the earlier probe environment and do
not establish the state of an installed SDK.

Originally prepared while exact0.58.2 root acceptance and0.59 core-capsule work ran.
No language-version change is proposed. This file does not accept a release,
close PLAN.md, or claim a production Wasm target.

## Evidence and prerequisites

- LLVM22.1.8 in the existing Linux ARM64 image contains mlir-opt,
  mlir-translate, llc, clang and wasm-ld. Host macOS currently has the matching
  compiler/MLIR tools but no installed wasm-ld; host delivery remains open.
- `wasm-scalar-060-feasibility/verification.json`: checked NEX0.58.2 scalar MLIR
  lowered to wasm32 and executed in Node with no Wasm imports. Three accepted
  i64 cases preserve exact values, including a value above2^53; three overflow
  cases trap through the deliberately minimal experiment runtime.
- `wasm-scalar-060-product-feasibility/verification-failed.json`: general checked
  multiplication fails at link because LLVM lowers part of its overflow check
  through `__multi3`. This failure is retained.
- `wasm-scalar-060-product-compiler-rt-feasibility/reference-agreement.json`:
  unchanged compiler-rt `multi3.c` and headers resolve the dependency;84 valid
  products agree with the reference interpreter and TypeScript, and84 overflow
  inputs are rejected by Wasm and the reference interpreter. This is an
  experiment with one function, not a complete runtime/backend test.
- Compiler-rt is pinned to llvmorg-22.1.8, commit
  ca7933e47d3a3451d81e72ac174dcb5aa28b59d1. Six file contents were compared by tag
  and commit. Original license and source headers are retained under the probe's
  compiler-rt directory. Product reuse must add file hashes, notices, SDK
  installation, capability resources and THIRD_PARTY.md entries.

## First product contract to implement

1. Add an explicit `nex build FILE --target wasm --entry FUNCTION` path which
   uses the checked graph and existing MLIR emitter, with a real wasm32 target
   and data layout. Preserve normal native target rejection and its64-bit ABI.
   Do not relabel host LLVM IR or reuse a host object as Wasm.
2. Start with concrete pure shared/client functions whose reachable functions,
   parameters, results and locals use i64/bool/unit only. Reject server code,
   effects, foreign declarations, heap values, callable environments and any
   unsupported intrinsic with useful source diagnostics. Unreachable server
   functions and their literals must not enter emitted MLIR/LLVM/Wasm/maps.
   Finite f64 is a subsequent explicit extension requiring its full semantics.
3. Supply a small freestanding trusted runtime for checked failure edges,
   assertions and bounded polling. Runtime diagnostic state must be reset for
   every exported call, retain the first code/line/site, and expose checked
   information after a trap. Budget exhaustion must terminate recursive calls
   and loops; recursion/native Wasm traps must be reported without inventing
   source attribution. Keep modules independent of an LLM and the NEX compiler.
4. Use pinned compiler-rt for legalizer helpers. Build with no unresolved symbols
   and no imports; enumerate the actual imports/exports in acceptance. Never
   replace checked arithmetic with wrapping operations or an unchecked JS shim.
5. Emit an ES-module host wrapper with explicit export allowlists. i64 crosses
   the JavaScript boundary as BigInt, with exact range/type checks before calling
   Wasm: raw WebAssembly i64 coercion wraps out-of-range BigInts. bool uses an
   exact boolean contract rather than general truthiness; unit maps to undefined.
   The wrapper translates checked runtime failures to stable diagnostics and
   reports unexpected Wasm traps separately. A trap can leave the compiler's
   linear-memory stack pointer unrestored; discard that instance before the
   next call instead of assuming the next reset function can execute safely.
   A stack-first layout and fixed bounded memory need actual recursion/large
   local-frame rejection tests. Concurrent/reentrant use needs an explicit
   per-instance rule. No arbitrary loader imports or ambient authority.
6. Version/cache the build by checked revision, compiler/resource/tool identities,
   entry, profile, target ABI and emitted artifact contents. Retained revision
   builds and source-deleted exports must work; changed artifacts must invalidate
   cache hits. Record function/source/operation identities in mapping metadata.
7. Install all resources in the SDK, describe the actual scalar limits in
   `nex describe`, grammar/spec notes and the model-independent language pack.
   The existing React/TypeScript app remains usable. No automatic acceleration,
   Emscripten completeness, WASI, threads, SIMD, general memory ownership or full
   application support is inferred from the first compute-module adapter.

## Required acceptance

- Native/reference/TypeScript/Wasm equality for boundaries, seeded inputs,
  checked add/sub/mul/div/mod/negation, MIN%-1==0, short-circuiting, left-to-right
  calls, loops and ordinary pure generic specializations.
- Correct rejection for overflow, zero division, bad input types/ranges,
  unsupported reachable types/effects/realms/FFI, malformed modules and exhausted
  budgets. Preserve code/site and absence of undesired operand execution.
- Node plus actual Chromium/Firefox/WebKit execute a self-contained scalar module
  without the compiler or a model. A tiny browser example must load the Wasm
  artifact and handle one accepted and one rejected computation accessibly.
- Source/secret exclusion, complete artifact inventories, cold/warm/modified
  cache behavior, saved-revision builds, installed/source-free/moved/restored SDK.
- Appropriate full regression after implementation. Measure JS/Wasm on the same
  workload including load/call overhead before making performance claims.
