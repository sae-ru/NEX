---
status: historical
applies_to: mixed earlier milestones
owner: repository
original_path: docs/architecture.md
original_sha256: 1780f159eea59be98dd10179d6dde251ef517c68aca777850cdddefa089563ca
---

This is the exact previous document body, preserved during the current architecture audit.
Its old version and pending-work claims are historical data.

# Architecture decisions for the implemented core

## Compiler and toolchain

The core is C++20 and uses the installed LLVM/MLIR 22.1.x libraries directly. The verified installation is LLVM/MLIR 22.1.8 with Apple Clang 21 compiling NEX itself, CMake 3.31.12 using Unix Makefiles, SQLite 3.53.1 and Python 3.9.6 for tests. Ninja is not currently installed and is not required by the build. The generated programs use LLVM Clang++ 22.1.8 and the platform SDK/linker.

The compiler has separate frontend/checker, module loader, interpreter, backend, project store and command-line modules. The parser creates typed ASTs, including nominal structures and generic list types. The loader resolves file-local aliases, enforces public/private boundaries, and binds definitions to logical module-qualified identities before type/effect/realm checking. Canonical function ASTs form the content-addressed nodes; function-call relations form graph edges. The native planner indexes direct/reverse function and layout-provider dependencies and groups the selected closure into source-module compilation units. Fine-grained persistent operation IDs remain a future extension.

The backend emits verified `func`, `arith`, `cf` and LLVM-dialect operations, including direct scalar/pointer stack slots and standard debug attributes, lowers through MLIR conversion passes, and translates to LLVM IR. Each native source unit is lowered/compiled separately; a verified LLVM link provides aggregate inspection IR. Clang's driver handles object generation and platform linking. Explicit `nex.toolchain/1` configurations select the native triple, SDK and dependency installations. The same driver arguments are probed and applied to generated/runtime objects and linking; the resulting ABI/layout and SDK/dependency identity isolate caches. macOS cross-build artifacts are verified on ARM64, while foreign execution and other OS/mobile targets remain pending. Task checks can pin external toolchain fingerprints and capture normalized configurations; replay compares them to a current explicitly supplied trusted catalog before executing a compiler. SDK/support-tool/environment contents outside the recorded fingerprint scope are not frozen. There is no C/C++ source translation fallback and no interpreter embedded in native output.

The TypeScript backend consumes the same checked graph and emits only the reachable client/shared function closure. It preserves i64 with checked BigInt arithmetic, Unicode scalar string operations, nominal aggregate equality and frozen immutable data. Unique generated local names preserve NEX's initializer-before-binding scope rule, avoiding JavaScript temporal-dead-zone differences. Native and TypeScript backends are independently compared with the reference interpreter.

Arithmetic uses a small C ABI runtime with explicit overflow/division/assertion checks. This preserves semantics across debug and optimized builds. The memory model has immutable UTF-8 strings, homogeneous lists, nominal structures and result<T>. Runtime objects share immutable child data through reference counting; generated code owns handles, borrows parameters, retains escaping results and releases temporaries/locals on assignment, scope exit and every return path. Source code exposes no pointers or mutable reference cycles. Opaque handles use pointer-typed local slots on the currently supported 64-bit host target. Native entry wrappers check that all managed objects were released on normal completion. The server additionally contains traps in tracked request scopes. General source FFI/resource types, mutable objects and source-level async still need additional rules.

## Identity, history and edits

SQLite stores semantic revisions, canonical function nodes, stable local IDs and call edges. BLAKE3 comes from LLVM's bundled implementation. Canonical JSON is serialized deterministically. A program revision incorporates all of its canonical function definitions in name order, including their bodies and signatures; recursion does not require recursively hashing call edges in this initial whole-program scheme.

Function content hashes are not used as sufficient keys for independently compiled objects. Database schema 2 records the language version per revision; schema migration preserves old sources, and language migration explicitly reparses them. Structure layouts, public visibility and resolved module dependencies participate in program identity. Source paths and local import alias names do not. Function context includes the transitive structure definitions needed by its source and direct callees, its file's imports and the native symbol.

The executable cache includes NEX's compiler-source fingerprint, native compiler identity/actual ABI, target, profile, complete source bundle, runtime and relevant SDK environment. Independently reusable module objects key their own checked definitions/source and consumed contracts/layouts instead of unrelated callee bodies. Shared object indexes publish atomically; content objects and build-local projections are validated before reuse. See docs/incremental.md for the report and source cache.

Source-based commands synchronize a checked program into HEAD. Graph-based patches use an expected semantic revision and a SQLite transaction, and can replace functions across files together. Their source projection is materialized only by explicit export. This avoids pretending that a database transaction and a filesystem edit are a single atomic operation. Semantically equivalent source projections share a revision; the first projection is retained for graph recovery.

## Source bundles and libraries

Language 0.5 retains the complete `nex.sources/1` bundles introduced in 0.3. The live loader reads paths from the project root, configured local library roots, or the installed standard library. The frozen loader reads only archived text and rejects unreachable files, missing imports, duplicate module identities, escaping paths and import cycles. Building an archived revision never consults current dependency files or locks. Package roots are access boundaries, including after filesystem symlink resolution for relative/configured-library imports.

`nex.lock.json` pins the raw content of loaded standard/library sources; it deliberately does not pin application sources. Existing loaded pins are enforced, while unused entries may serve another entry point. `nex lock` explicitly refreshes loaded entries. Portable directory export materializes all source text, vendors dependency sources, generates a local-library manifest and records the pins. No remote registry or package solver is involved. Installed standard libraries are ordinary NEX source using the same language checks.

## Browser applications

The initial browser adapter uses ordinary `std/web.nex` structures and pure initial/update/view/title functions; it introduces no alternate language grammar. React renders semantic elements from those view values, with controlled inputs and explicit action/path events. The adapter permits defined HTML tags/attributes/events and escapes text. A fixed npm lock supplies React, TypeScript, Vite and Playwright. `nex web` only generates; `nex build --target web` installs, typechecks and builds actual static assets, with full asset-tree cache integrity checks. Server bodies and unused literals are absent from emitted client source and source maps.

The optional pure `commands(before, after, event)` entry returns ordinary `std/net.nex` descriptors. A serial browser event queue computes state/commands once per event; rendering does not replay effects. The host validates complete batches before executing bounded same-origin requests/cancellation and returns strict response envelopes as ordinary events. Models decode application bodies with the same generated type schemas as the server. Request IDs let pure transitions reject stale responses across cancellation/sign-out; runtime bearer credentials stay out of generated resources. The full-stack example shares public models with the native server and persists data by authenticated principal. Explicit endpoint contracts now generate server dispatch, typed client helpers and OpenAPI; application-specific assets/components remain required work. NEX source version is 0.7 and toolchain version is 0.17.0. See `docs/web.md` for contracts, scope and commands.

## Recoverable data and server host

`result<T>` is an immutable managed value with success payload or code/message error. Typed JSON is driven by checked type schemas, uses decimal strings for i64, validates nominal record fields and rejects duplicate keys/invalid Unicode/limit violations. The native/interpreter parser uses vendored nlohmann/json 3.12.0; TypeScript performs its own strict parsing/type reconstruction and is differentially checked. General JSON numbers are never silently rounded into NEX integers.

The native HTTP host uses cpp-httplib 0.61.0, OpenSSL 3 and a bounded worker/queue model. A checked Request-to-Response server function runs in a request scope, with cooperative function/loop polls, deadlines/disconnect/shutdown checks and a registry that releases generated handles on unwinding. Runtime counters are atomic. Generated native functions carry unwind tables; runtime traps throw only inside this trusted boundary and retain the existing process-exit behavior for ordinary standalone programs.

SQLite connections/transactions are RAII-owned and never become NEX pointers. The host authenticates bearer hashes, injects a principal partition, and commits successful requests only after a final scope check. Error/trap/cancel paths roll back, and failed mutations make a transaction noncommittable. Shared CLI/interpreter storage helpers use separate per-operation transactions when no host capability is active. Binary collation/schema checks prevent a mismatched table from silently changing principal identity rules. This is a bounded synchronous request model, not general source concurrency or a native-code memory sandbox.

Native builds emit the selected closure and capture exact runtime inputs. Required runtime components have content-verified object reuse; SQL/OpenSSL dependencies are included in relevant keys. Host-native archive output enables a version-matched trusted C++ boundary. Separate native NEX module compilation is implemented; a stable cross-version source FFI, finer-grained frontend/function reuse and cross-unit LTO remain pending.

## Observability

Each build preserves its actual source bundle alongside MLIR, LLVM IR and object files. Debug metadata points to immutable entry and imported source projections. Native symbols encode qualified module/name components without collisions; graph/context results expose the exact symbol. On macOS, `dsymutil` packages debug information explicitly. Typed DWARF parameters/locals and lexical binding scopes travel through standard MLIR debug attributes. Direct LLVM stack slots keep their address records usable in native DWARF; borrowed debug parameter copies never participate in owned cleanup. The captured LLDB formatter reads stopped values without evaluating expressions, and lldb-dap uses the generated session configuration. The cache validates debug manifests, source projections, formatter content and macOS DWARF alongside the executable. Full NEX expression evaluation, per-operation graph IDs and other debugger hosts remain pending; see docs/debugging.md.

The `profile` mode retains optimization, symbols and frame pointers and instruments reachable NEX function entries/normal exits. The runtime closes active frames on traps and request-boundary exceptions, records bounded wall-time/allocation observations and optionally emits Tracy 0.14.1 CPU zones and named shallow memory pools. CLI reports join function name/content with the selected graph to attribute node IDs and revision without embedding project-local identity in shared object caches. Debug/release builds omit the profiler. See docs/profiling.md for capture, timing/size definitions and remaining GPU/browser/system coverage.

Browser builds retain Vite maps to generated TypeScript and a function/statement mapping back to original NEX coordinates. Runtime arithmetic/assertion/bounds errors carry NEX source sites. Direct debugger-consumable NEX source-map chains and browser measurements attributed to graph nodes remain pending.

## Model independence

LLM-facing interfaces are versioned text and JSON. `describe` exposes capabilities, `guide` exposes the matching language pack, `context` exposes bounded function context, and `apply` checks and commits proposed changes. The parser and checker treat model output like any other source. There is no model provider dependency in the compiler or generated program.

The installed SDK includes its runtime, specification, grammar, prompt and protocol documentation. It still depends on a compatible native development toolchain. Packaging that toolchain for other machines and verifying other operating systems are separate unfinished deliverables.

## Endpoint graph and generated projects

`endpoint` declarations are separate checked graph nodes with stable IDs/handler edges and canonical contracts. They participate in nex.program/4 identity, source bundles, context and optimistic replacement transactions. The runtime/interpreter/backends continue to execute checked functions; endpoint declarations are transport metadata, not implicit calls or effects.

`nex api` projects both sides from the frozen checked graph. Generated server routers call implementations with injected context, strict body decoding, tagged results and explicit HTTP statuses. The client SDK reconstructs only required public model declarations under their original nominal identities, plus pure helpers containing compiler-generated wire descriptors. The typed browser command unwraps its control envelope locally, sends only the input body and validates successful payloads before event delivery. Both candidate projects are reloaded/checked before an atomic output-directory rename. Stored language 0.4 revisions migrate explicitly; their bundles/history remain intact. See docs/api.md for the exact supported contract and limits.

## Scalar verification

The compiler links Z3 as a development dependency; native/browser output does not. Separate snapshot-bound contracts select pure scalar roots, pre/postconditions and loop invariants/rankings. The verifier uses the NEX expression parser, checked i64 VC rules, path-sensitive symbolic states, acyclic full-body call expansion and inductive loop havoc/preservation. It reports input versus inductive-state counterexamples separately, checks precondition feasibility and saves exact source/contract/SMT artifacts. Unknown/timeouts/unsupported constructs stay unproved. No proof result is trusted by code generation to remove guards; richer data/effect proofs and source-level contract/runtime-enforcement syntax remain open. See docs/verification.md.
