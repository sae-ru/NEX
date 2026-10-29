Language026 finally is a separate synchronous native/reference/TypeScript
development feature. This scalar Wasm adapter rejects it with E_WASM_TYPE;
source-error transport/finalization here remains pending.

# Experimental scalar WebAssembly modules

Toolchain 0.60 introduces an isolated compute-module backend under validation.
The source language stays at 0.16. This is a bounded scalar adapter; the platform,
browser, installed SDK and full regression results must be checked in STATUS.md.

```sh
nex build examples/wasm/main.nex --target wasm --entry compute --profile release -o /new/module --json
```

The command checks the archived semantic graph, emits MLIR, lowers it for a real
`wasm32-unknown-unknown` layout, compiles with LLVM 22.1 Clang, and links with
LLVM 22.1 `wasm-ld`. Configure `NEX_WASM_LD` in CMake when building NEX if the
linker is outside LLVM's tool directory. An explicit `NEX_WASM_LD` environment
override selects a trusted development tool. A bundled SDK records its relative
linker path. No linker is downloaded during an application build.

Functions reachable from the selected entry must be pure shared/client NEX
definitions with only `i64`, `bool` and `unit` values. Concrete ordinary generic
specializations work within those limits. Server functions, effects, FFI, heap
values, callable environments and `f64` are rejected when reachable. Unreachable
server bodies and literals are excluded from the emitted module, wrapper, maps
and IR. Native target checking keeps its separate 64-bit ABI policy.

The initial limits are 128 reachable functions, 8192 total operations, 512
operations per function, 32 parameters per function, call depth 64, a polling
budget of 1..10000000, and fixed 16 MiB linear memory with an 8 MiB stack-first
layout. Polling occurs at function entries and loop iterations. The default
budget is 1000000. These are resource bounds, not wall-clock deadlines or a
claim that all valid NEX programs fit this adapter.

The output directory contains `module.wasm`, `module.mjs`, `module.json` and
`THIRD_PARTY_NOTICES.txt`. Intermediate MLIR/LLVM and captured build inputs stay
in the reported build cache. Cache identity includes the checked source bundle,
entry, compiler/resource/linker identities, target ABI and profile. Missing or
modified completed artifacts cause a rebuild. `debug` and `release` are accepted;
native profiling is a separate workflow.

```js
import { createNexWasm } from './module.mjs';
const response = await fetch('./module.wasm');
const compute = await createNexWasm(await response.arrayBuffer());
const answer = compute.call([6n, 7n]);
```

Use BigInt for every `i64` argument and result, and actual booleans for `bool`.
`unit` returns `undefined`. `call` takes an array matching the checked signature;
an optional second argument sets `{budget: 10000}`. The wrapper validates types,
integer ranges, the module SHA-256 and the exact import/export allowlist. It
needs Web Crypto in a secure browser context (including localhost), or current
Node.js. The module has no host imports, filesystem/network grants or LLM
dependency. The wrapper exposes no mutable instance or linear memory.

Checked failures use `NexWasmError.code`, including `E_OVERFLOW`, `E_DIV_ZERO`
and `E_ASSERT`, with a bounded source operation/site and line when available.
Resource stops use `E_WASM_BUDGET` or `E_WASM_DEPTH`. Unexpected engine traps
report `E_WASM_TRAP` without invented attribution. Every trapped instance is
discarded before another call, because a trap may leave its linear stack pointer
changed. Input errors use `E_WASM_INPUT` before entering Wasm. Calls on an
instance are synchronous and cannot overlap.

The existing React/Vite application backend still emits TypeScript. This first
compute adapter does not automatically replace browser functions, implement WASI,
Emscripten, general Wasm applications, threads, SIMD or GPU execution. Browser
interaction checks, source-free SDK delivery and like-for-like JS/Wasm benchmarks
are required separately; no acceleration claim follows from successful linking.
