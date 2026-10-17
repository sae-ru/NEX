# NEX

**NEX — Neural Execution Language** («язык нейронного исполнения»).

**Главная идея:** минимальное количество токенов для передачи максимального количества точного смысла при максимальной производительности и безопасности исполняемой системы.

People and LLMs work with a checked semantic graph. The model helps create and change programs; compiled applications run without an LLM.

NEX is a language and development toolchain built around a checked semantic graph. The current implementation is an early C++20 compiler, not the full system in `PLAN.md`.

Implemented code includes a parser, type/effect/realm checker, modules with private/public definitions, Unicode strings, immutable lists and structures, a reference interpreter, SQLite/BLAKE3 revision store, transactional patches across modules, model-independent JSON tools, an MLIR → LLVM → native pipeline, and a TypeScript → React/Vite browser pipeline. Verification status and remaining scope are recorded in `STATUS.md`.

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

## Incremental native builds

Native builds compile reachable functions into separate source-module objects. Body edits reuse unaffected modules; call contracts and transitive record layouts invalidate affected consumers. `nex build FILE --json` reports `compiled_modules`, `reused_modules` and the `compilation` report path. The [build guide](docs/incremental.md) covers keys, dependency indexes, validated shared objects, source projections and remaining frontend/LTO/test-cache work. Programs are checked before cached code is selected.

## Debugging and editor integration

```sh
./build/nex debug examples/debugging/main.nex
./build/nex debug examples/debugging/main.nex --kind dap --json
```

Native debug builds include typed parameter/local records and lexical scopes. LLDB loads matching previews for strings, lists, records and results; `nex-values` returns a bounded read-only JSON frame report. The DAP session descriptor supplies an editor launch configuration for an installed `lldb-dap`. [The debugging guide](docs/debugging.md) covers breakpoints, immutable source projections, value limits, validation and remaining expression/platform work.

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

The compiler/toolchain is **0.12.0**, source language **0.5**. Code targets are host native, native HTTP/HTTPS and browser TypeScript with explicit request/cancel commands. General source-level async/resource FFI, richer data/resource proofs, source-level contract enforcement, broader task/agent operations, mobile/native UI/GPU targets, remote package retrieval and portable SDK distribution remain pending. The requested project is the language and complete development chain. Application products will be built afterwards using NEX.
