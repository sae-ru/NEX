# NEX

**NEX — Neural Execution Language** («язык нейронного исполнения»).

**Главная идея:** минимальное количество токенов для передачи максимального количества точного смысла при максимальной производительности и безопасности исполняемой системы.

People and LLMs work with a checked semantic graph. The model helps create and change programs; compiled applications run without an LLM.

NEX is a language and development toolchain built around a checked semantic graph. The current implementation is an early C++20 compiler, not the full system in `PLAN.md`.

Implemented code includes a parser, type/effect/realm checker, modules with private/public definitions, Unicode strings, immutable lists, structures and algebraic enums with nested patterns, guards and exhaustive statement/value matches, parametric generic types/functions, typed callbacks and immutable snapshot closures, a reference interpreter, SQLite/BLAKE3 revision store, transactional patches across modules, model-independent JSON tools, an MLIR → LLVM → native pipeline, and a TypeScript → React/Vite browser pipeline. Verification status and remaining scope are recorded in `STATUS.md`.

Toolchain 0.24 / language 0.11 introduced finite binary64 arithmetic. Source programs, generic numeric functions, native/TypeScript/interpreter execution, typed JSON/API models and float watches passed the macOS ARM64 and Linux ARM64/x86-64 development matrix. Installed SDK acceptance includes numeric browser state and source-deleted replay; Linux x86-64 execution is emulated. Broader platforms and portable SDK delivery remain pending. The [numeric design and acceptance plan](docs/floats-design.md) records the scope and limits.

## Build

Dependencies: CMake 3.25+, a C++20 compiler, LLVM/MLIR **22.1.x**, SQLite3, OpenSSL 3 and Z3 development headers/libraries, and Python 3 for integration tests. A native Clang++ driver and platform SDK are needed when building NEX programs. CMake detects the existing Homebrew llvm@22/OpenSSL locations on this machine; elsewhere set `LLVM_DIR`, `MLIR_DIR` and `OPENSSL_ROOT_DIR` explicitly. HTTP tests open local sockets and create a temporary TLS certificate with the `openssl` CLI.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j 4
ctest --test-dir build --output-on-failure
```

For another installation:

```sh
cmake -S . -B build \
  -DLLVM_DIR=/path/to/llvm/lib/cmake/llvm \
  -DMLIR_DIR=/path/to/llvm/lib/cmake/mlir
```

## Linux development environment

```sh
python3 tools/linux/check.py --arch arm64
python3 tools/linux/check.py --arch amd64
```

The pinned Ubuntu/LLVM image builds the compiler, runs the full regression suite and verifies an installed SDK with external network disabled. Linux ARM64 execution and LLDB/DAP are exercised; Linux x86-64 execution is exercised through Docker emulation. Linux application linking uses LLVM LLD with verified ELF debug information. Reports retain execution architecture and platform-specific skips. See [the Linux guide](docs/linux.md), also available as `nex guide --kind linux`.

## Use

```sh
./build/nex describe --json
./build/nex doctor
./build/nex check examples/arithmetic.nex
./build/nex eval examples/arithmetic.nex --json
./build/nex test examples/arithmetic.nex
./build/nex test examples/data.nex --profile release
./build/nex test examples/modules/main.nex --profile release
./build/nex build examples/arithmetic.nex --profile release -o /tmp/nex-arithmetic
/tmp/nex-arithmetic
```

Create a standalone project with `nex init PATH`, then run `nex check`, `nex test`, and `nex run` from that directory. Add the built compiler's directory to PATH for the short `nex` command.

Imports use `import "./model.nex" as model;` and exported definitions use `pub fn` or `pub struct`. Call an exported function with `model::create(...)`. Standard libraries currently include `std/math.nex` and `std/text.nex`; other local library roots are registered in `nex.json` under `libraries`. `nex lock` pins dependency source content. `nex export --directory NEW_DIRECTORY` materializes the current revision with all sources and vendored libraries. Stored-revision builds remain usable even when the original files or library directories change.

Generated native output runs without the compiler, LLVM or a model. Pure programs do not link SQLite; storage programs link SQLite, and HTTP/TLS programs additionally link OpenSSL. The development compiler links against LLVM/MLIR, SQLite and Z3. Generated programs do not depend on Z3. `cmake --install build --prefix /chosen/sdk` installs the compiler and language/runtime resources. The compiler first looks for resources in its installed `share/nex`, then in the source checkout. `NEX_RESOURCE_DIR` explicitly overrides the resource location; `NEX_CLANG` overrides the native compiler driver. Redistributable toolchain bundles for other machines are pending.

Verify a complete installed development workflow with `python3 /chosen/sdk/share/nex/tools/sdk_acceptance.py /chosen/sdk --output /new/evidence --browser --live`. It exercises a failed reviewed task, graph repair/import, native/reference/TypeScript agreement (including finite numbers), profile attribution/cleanup, real archived DAP watches, source-deleted replay/export, scalar proof and locked Vite builds for callable and numeric browser state. See [the SDK handoff guide](docs/sdk.md) for dependencies, retained evidence and optional checks. Linux verification also runs this workflow in a separate container with no source checkout mounted.

## Native target selection

```sh
./build/nex build examples/generics/main.nex --target x86_64-apple-macosx13.0 --profile release --json
./build/nex build examples/server/main.nex --target server --toolchain /path/to/toolchain.json --json
```

On macOS, native builds can select arm64 or x86_64. `--toolchain FILE` records the target, compiler, optional linker/SDK and target SQLite/OpenSSL paths. Build metadata and caches distinguish architectures. Local run/test/debug/profile commands require the compiler host architecture; NEX does not launch an emulator itself. macOS Intel artifacts have been cross-built on ARM64; macOS Intel execution/debugging remains unverified. The Linux workflow runs matching ARM64/x86-64 compiler containers. See [the native build guide](docs/incremental.md) and [toolchain schema](llm/toolchain.schema.json).

## Web applications

With Node.js 22.18+ and npm installed:

```sh
./build/nex test examples/web/main.nex --target web
./build/nex build examples/web/main.nex --target web --profile release --json
```

The build installs locked packages, checks generated TypeScript and builds browser assets. Its result reports the generated project `directory` and static `dist`; run `npm --prefix DIRECTORY run preview` to view it locally. `nex web FILE --directory NEW_DIRECTORY` generates an editable React/Vite project without installing/building it. [The web guide](docs/web.md) describes state/update/view, optional request commands, routing and browser tests. `examples/web` has local memory state; `examples/fullstack/client.nex` connects asynchronously to its native `server.nex` API using shared models, runtime bearer credentials and durable user-partitioned data.

## Native HTTP/API and data

```sh
./build/nex test examples/results.nex --target web
./build/nex token --user alice --auth /private/tmp/nex-auth.json --json
./build/nex build examples/server/main.nex --target server --profile release --json
```

Run the reported executable with `--auth FILE --database FILE` and optional `--cert FILE --key FILE` or `--static DIST`. The [server guide](docs/server.md) covers request contracts, bearer credentials, SQLite transactions, cancellation and the current limits. The task API persists data and isolates authenticated principals. `result<T>` and strict typed JSON work across the interpreter/native/TypeScript paths. `--library --entry NAME` builds a host-native archive for the matching trusted C++ runtime ABI.

## Typed API generation

Language 0.5 adds explicit endpoints referencing checked server handlers. The compiler generates a frozen native dispatcher, a client SDK with extracted models and typed request/response helpers, exact wire schemas and OpenAPI 3.1.1 documentation. Successful response data is validated before reaching browser update events.

```sh
./build/nex api examples/api/service.nex --json
./build/nex api examples/api/service.nex --directory examples/api/generated --json
./build/nex test examples/api/client.nex --target web --json
./build/nex build examples/api/client.nex --target web --profile release --json
```

Generate into a new/empty directory before using this client example. Build the reported `server_entry` with `--target server`; serve the browser `dist` with its `--static` option. [The API guide](docs/api.md) documents contracts, statuses, generation, schema limits and SDK use. Older language revisions require explicit `nex migrate`; their archived sources/history are retained.

## Generic libraries

`struct Box<T>`, `enum Maybe<T>` and `fn identity<T>(value:T) -> T` are checked even when unused. Concrete calls infer type arguments or supply them explicitly. Builtin bounds such as `T: add`, `T: ordered` and `T: integer` state required operations and are checked before specialization, including abstract forwarding. `examples/generics` and `examples/constraints.nex` exercise reusable models/functions and backend agreement. Source-template edits rebuild derived instances; custom traits and higher-kinded types remain pending.

## Function values

`fn(i64)->i64` values support named/generic references, returned lambdas, immutable
snapshot captures and checked higher-order calls in native and TypeScript output.
Use `<T:wire>` for generic serialization; actual callables are excluded from
application JSON/API payloads. [The function guide](docs/functions.md) describes
identity, effects/realms, ownership, debugging and explicit 0.9 migration.

```sh
./build/nex guide --kind function --json
./build/nex test examples/functions/main.nex
./build/nex test examples/functions/main.nex --target web
```

## Operation graph

```sh
./build/nex check examples/operations/main.nex --json
./build/nex operations --symbol operations::adjust --json
./build/nex context --operation ID --json
```

Parameters, blocks, statements and expressions have local persistent identities separate from content hashes. Paged queries expose typed definitions, lexical references, parents and operands. Deterministic sites connect interpreter/TypeScript errors, MLIR source locations and stopped-frame LLDB candidates to those identities. [The operation guide](docs/operations.md) defines matching, source hashes, storage migration and attribution limits.

## Incremental native builds

The development 0.25 compiler gives each reachable concrete function, closure and generic specialization a separate native object. Body edits can reuse siblings in the same file; call contracts, source coordinates and transitive record layouts invalidate affected consumers. `nex build FILE --json` reports compiled/reused function and module counts and the `compilation` report path. Stable DWARF paths map to each session's complete frozen sources. The [build guide](docs/incremental.md) covers keys, dependencies, artifact integrity and remaining frontend/LTO/test-cache work. Programs are checked before cached code is selected; the new full platform/SDK matrix remains in progress.

## Debugging and editor integration

```sh
./build/nex debug examples/debugging/main.nex
./build/nex debug examples/debugging/main.nex --kind nex-dap --json
```

Native debug builds include typed parameter/local records and lexical scopes. LLDB loads matching previews for strings, lists, records and results; `nex-values` returns a bounded read-only JSON frame report. The DAP session descriptor supplies a stdio adapter command and launch configuration for a compatible client using an installed `lldb-dap`. Pure NEX watch expressions use exact captured values and a separate interpreter. Demand-driven reads select list lengths, record fields, result tags and dynamic indices without serializing unrelated payloads; computed aggregates support paged children. [The expression guide](docs/expressions.md) covers LLDB commands, offline snapshots, adapter registration and operational limits. [The debugging guide](docs/debugging.md) covers breakpoints, immutable source projections, value limits, validation and remaining expression/platform work.

## Profiling

```sh
./build/nex profile examples/profiling/main.nex --scenario "sum and labels" --json
```

Native profile builds instrument reachable function calls and managed object/handle allocations. The saved report includes measured wall/self times, call counts, bounded trace events, shallow memory sizes, revision/build identity, graph node IDs and workload/host metadata. The CLI returns at most 100 functions. The bundled Tracy 0.14.1 client can send CPU zones and named memory pools to a matching upstream collector when explicitly enabled. [The profiling guide](docs/profiling.md) covers capture commands, request failure cleanup, measurement limits and remaining GPU/browser work.

## Scalar contracts and Z3

```sh
./build/nex verify examples/verification/main.nex --contracts examples/verification/contracts.json --json
./build/nex contract examples/verification/main.nex --symbol increment -o /tmp/increment.json
```

Snapshot-bound JSON contracts state preconditions, postconditions and loop invariants/rankings for pure scalar functions. The verifier checks arithmetic/assertions and supported termination rules, preserves replayable SMT queries and distinguishes proof, counterexample, inconsistency, unknown, timeout and unsupported scope. It retains runtime checks and does not prove compiler/runtime correctness. [The verification guide](docs/verification.md) defines the supported subset and trust boundaries. Z3 5.3.1 was verified on this host; configure another development prefix with `-DNEX_Z3_ROOT=/path/to/z3`.

## Task contracts

```sh
./build/nex task examples/tasks/task.json --kind check --json
./build/nex task examples/tasks/task.json --kind run --json
./build/nex task /absolute/run/receipt.json --kind replay --json
```

Native task checks can pin an inspected toolchain hash and select it through `--toolchains CATALOG.json`. The runner records its normalized configuration and external-input fingerprints, checks for changes around execution and requires the current trusted catalog on replay. Foreign build checks can produce Intel artifacts; foreign execution checks remain unsupported. `nex toolchain FILE --json` inspects a configuration without executing its compiler.

A reviewed task links requirements, qualified definitions, target platforms and explicit checks. The runner freezes source candidates and executable resources, runs pinned tests, observations, scalar proofs, effect limits, builds or measured profile budgets, and saves checkpointed receipts and artifacts. Replay verifies captured inputs and reruns checks in a new run. Static graph linkage does not prove natural-language completeness. [The task guide](docs/tasks.md) covers multi-program candidates, intent guards, process cleanup and external-tool/replay limits.

## Language and LLM interoperability

- [Language specification](docs/language.md) and [EBNF grammar](docs/grammar.ebnf).
- [Model-independent language pack](llm/README.md) and [coding prompt](llm/SYSTEM_PROMPT.md).
- [JSON/graph protocol and CLI](docs/protocol.md).
- [Browser backend and application contract](docs/web.md).
- [Native server and resource capabilities](docs/server.md).
- [Development plan](PLAN.md) and [implementation status](STATUS.md).

The language pack can be given to different LLMs as ordinary text. Agents can discover supported features, request function context, submit a revision-checked patch, and run deterministic validation through the same CLI. Model output has no special privileges in the compiler.

For a concrete handoff to another model, use [the walkthrough](llm/WORKFLOW.md) and [task template](llm/TASK_TEMPLATE.md). They cover chat-only use as well as terminal agents, including the difference between graph revisions and working source files. Cross-model coding quality and token savings remain to be measured.

## Current boundaries

The development compiler/toolchain is **0.25.0**, source language **0.11**, with function-level object reuse under validation. The preserved 0.24 numeric development milestone passed the matrix recorded above. The last accepted checkpoint is **0.23.0 / language 0.10**, verified on macOS ARM64 and Linux ARM64/x86-64; Linux x86-64 uses emulation. Consult `STATUS.md` for exact coverage and remaining work. Language 0.5/0.6/0.7/0.8/0.9/0.10 archives require explicit history-preserving migration; old debug sessions and receipts require their matching compiler binary/resources. Code targets are host native, native HTTP/HTTPS and browser TypeScript with explicit request/cancel commands. macOS ARM64 and Linux ARM64/x86-64 execution are exercised; Linux x86-64 uses emulation. macOS Intel execution and Linux x86-64 live debugging remain unverified. OR/rest/range patterns, custom generic traits, general source-level async/resource FFI, richer data/resource proofs, source-level contract enforcement, broader task/agent operations, mobile/native UI/GPU targets, remote package retrieval and portable SDK distribution remain pending. The requested project is the language and complete development chain. Application products will be built afterwards using NEX.
