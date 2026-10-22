# NEX

**NEX — Neural Execution Language** («язык нейронного исполнения»).

**Главная идея:** минимальное количество токенов для передачи максимального
количества точного смысла при максимальной производительности и безопасности
исполняемой системы.

This isolated development source is **toolchain 0.109.0 / language 0.19**.
Working116 adds a private explicit root FileReadGrant to the experimental
[external-completion kernels](docs/task-external.md). Per-path preparation
retains the original lexical/request grant across task resumes and never
uses worker TLS or environment discovery. The bounded retained path uses
exact owned bytes. Public source asynchronous IO remains unsupported; this
foundation adds no source syntax, semantic rule or canonical migration.

Standalone grant checks pass45 scheduler cases and42 non-task compatibility
cases, with independent code review. Current116 common regression, sanitizers,
installed SDK and platform acceptance remain pending. Exact115 passed122 groups,
strict sanitizers, three scoped browser kernels and21 Linux ARM64 groups; its
installed SDK is still being checked. These are separate receipts and do not
establish an accepted116 release. The preceding113 installedSDK24/438 also has
its own passing receipt.

Checked source tasks retain native compiled continuations, an independent
reference scheduler and generated TypeScript.
`task_scope`, `task<T>`, `channel<T>` and the `task` effect share one contract.
Known capability escapes are diagnosed before execution; uncertain flows retain
mandatory runtime owner checks. A [rendezvous example](examples/structured-tasks.nex)
can be checked and tested in native and web targets. See [the language](docs/language.md),
[lifetimes](docs/task-lifetimes.md) and [explicit migration](docs/task-migration.md).

Native task applications use bounded joined workers; source-only component
projects are supported. Reference and TypeScript scheduling are cooperative.
Their private external-completion experiments do not enable source filesystem,
network or UI task adapters. Task callbacks accept pure/task effects. Task debugger
and profile attribution, binary-provider task lifetimes, the NEX UI task adapter,
full current installed SDK/platform validation and complete static region
inference remain pending. Linux116, Windows116 and complete116 delivery have no
acceptance claim here. The approved primary checkout remains 0.81 / 0.16.

**Начать работу:** [Quickstart на русском](docs/quickstart.md) — установка,
первый проект, запуск и веб-сборка, что хранить в Git и как работать через LLM.
[Критерии качества](docs/quality.md) задают требования к крупным системам,
производительности и совокупной стоимости LLM. Паритет с C++/Python и экономия
токенов пока не доказаны. [Конвертер проектов C++/Python](docs/project-porting-design.md)
описан как будущий инструмент; команды конвертации ещё нет.

NEX is a language and development toolchain built around a checked semantic
graph. People and different LLMs use the same versioned specification, prompt
and compiler tools. Compiled applications run independently of an LLM.
Use the [model-independent bootstrap](llm/BOOTSTRAP.md), the
[language pack](llm/README.md), actual capability discovery and bounded context.

Language 0.19 retains ordered CPU mapping, introduced in 0.18, through
`parallel_map(items, callback, workers)`. Native macOS/Linux uses bounded joined
threads, pure available-realm callbacks and checked resource-free captures.
Reference and current public TypeScript execute this operation serially. The
dedicated browser-worker adapter is separate; integrating source tasks with
that adapter remains pending. See [the contract](docs/concurrency-design.md) and
[example](examples/parallel.nex). Explicit migration preserves genuine 0.17
history; a declaration named `parallel_map` requires a reviewed repair.

The language includes checked numbers, Unicode strings, immutable data,
matching, generics, traits, constructor parameters, function values and snapshot
closures. Types, effects and realms are checked. Language 0.17 adds typed postfix
[result propagation `?`](docs/error-propagation.md) in the checker, interpreter,
native and TypeScript backends, with explicit history-preserving migration.
Native output uses MLIR/LLVM; browser applications use TypeScript/React/Vite.

The development chain includes the SQLite/BLAKE3 graph, transactional patches,
locks, snapshots, task contracts, scalar Z3 checks, LLDB/DAP and CPU profiling.
[Project builds](docs/project-build.md) describe components, direct dependencies,
exports and configurations in `nex.build.json`. Source, static and dynamic edges
have distinct checked behavior. macOS/Linux shared libraries use one application
runtime; a static dependency consumes a separately built archive and does not
request a fully static executable. Captured project run/test/debug/profile,
[acceptance tasks](docs/project-tasks.md), [server workloads](docs/task-workloads.md)
and source-deleted replay preserve the declared architecture.

This candidate carries forward HTTP-server project/source debugging and the
editor 0.7 launch contract. It fixes a confirmed Python 3.9 DAP shutdown abort by
waking and joining input readers before interpreter shutdown; SDK acceptance now
rejects abnormal adapter exits. The preserved primary 0.81 still has that defect.
Version 0.90 also fixes duplicate traversal of statement-match arms and isolates
fresh test fixtures from local example caches. Focused checks are separate from
complete acceptance.

Platform coverage is bounded. Linux/macOS execution, Windows cross-build/Wine,
iOS archives and mobile WebView generation have separate receipts and remaining
delivery work. Cross-builds are not evidence of actual device execution.
[CIX P1](docs/cix-p1.md) fixed trusted FFI experiments do not provide general
GPU/NPU language APIs. Asynchronous IO, task delivery, general accelerators, source
try/catch/throw, broader native targets and cross-model cost measurements remain
pending in [PLAN.md](PLAN.md). This checkpoint does not complete the objective.

## Build

TypeScript task tests also require Node22.18+ and the pinned TypeScript
compiler. Set `NEX_TSC=/path/to/node_modules/typescript/bin/tsc`, or set
`NEX_NPM_CACHE` to a populated cache for the exact `web/package-lock.json`.
The test installs missing tools offline with lifecycle scripts disabled in its
owned temporary output; it never creates a cache inside the checked source.

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

Linux application-package integration tests also require `patchelf` and the
usual `readelf`/`ldd` tools. The maintained development image installs these.

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

Generated native output runs without the compiler, LLVM or a model. Pure programs do not link SQLite; storage programs link SQLite, and HTTP/TLS programs additionally link OpenSSL. The development compiler links against LLVM/MLIR, SQLite and Z3. Generated programs do not depend on Z3. `cmake --install build --prefix /chosen/sdk` installs the compiler and language/runtime resources. The compiler first looks for resources in its installed `share/nex`, then in the source checkout. `NEX_RESOURCE_DIR` explicitly overrides the resource location; `NEX_CLANG` overrides the native compiler driver. Toolchain 0.27 adds relative host-SDK selection and a verified macOS ARM64 development bundle. Toolchain 0.29 verifies ELF bundling, installed-package notices, moved/archive SDKs and application packages on the stated macOS/Linux matrix. Other platform/OS coverage and redistributable delivery remain pending. See [SDK bundling](docs/sdk.md).

Verify a complete installed development workflow with `python3 /chosen/sdk/share/nex/tools/sdk_acceptance.py /chosen/sdk --output /new/evidence --browser --live`. It exercises a failed reviewed task, graph repair/import, native/reference/TypeScript agreement (including finite numbers), profile attribution/cleanup, real archived DAP watches, source-deleted replay/export, explicit text-file capabilities and independent file applications, scalar proof and locked Vite builds for callable and numeric browser state. See [the SDK handoff guide](docs/sdk.md) for dependencies, retained evidence and optional checks. Linux verification also runs this workflow in a separate container with no source checkout mounted.

## Application packages

The maintained [SDK distribution workflow](docs/sdk.md) packages development
tools, validates normalized archives and repeats acceptance after restoration.
macOS checks source/dependency read denial and SDK write denial with kernel
controls; Linux checks run in source-free runtime containers.

`nex package FILE --directory NEW_DIRECTORY --json` builds a release application
and copies only its required non-platform libraries and notices. Native servers
use `--target server`. The directory can run without NEX SDK; platform runtime
compatibility and actual deployment execution must be verified separately.
See [application packaging](docs/packaging.md) for provenance, SDK inventory
reuse, Linux tools and runtime configuration. Current compiler, SDK and deployment evidence have separate scopes recorded in STATUS.md.

## Native target selection

```sh
./build/nex build examples/generics/main.nex --target x86_64-apple-macosx13.0 --profile release --json
./build/nex build examples/server/main.nex --target server --toolchain /path/to/toolchain.json --json
```

On macOS, native builds can select arm64 or x86_64. `--toolchain FILE` records the target, compiler, optional linker/SDK and target SQLite/OpenSSL paths. Build metadata and caches distinguish architectures. Local run/test/debug/profile commands require the compiler host architecture; NEX does not launch an emulator itself. macOS Intel artifacts have been cross-built on ARM64; macOS Intel execution/debugging remains unverified. The Linux workflow runs matching ARM64/x86-64 compiler containers. See [the native build guide](docs/incremental.md) and [toolchain schema](llm/toolchain.schema.json).

## Experimental Wasm compute modules

Toolchain 0.60.2 supports `build --target wasm --entry NAME` for bounded pure
scalar functions. [The Wasm guide](docs/wasm.md) describes its BigInt ABI, limits
and validation scope. This is separate from the TypeScript application adapter.

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

Explicit endpoint declarations reference checked server handlers. The compiler generates a frozen native dispatcher, a client SDK with extracted models and typed request/response helpers, exact wire schemas and OpenAPI 3.1.1 documentation. Successful response data is validated before reaching browser update events.

```sh
./build/nex api examples/api/service.nex --json
./build/nex api examples/api/service.nex --directory examples/api/generated --json
./build/nex test examples/api/client.nex --target web --json
./build/nex build examples/api/client.nex --target web --profile release --json
```

Generate into a new/empty directory before using this client example. Build the reported `server_entry` with `--target server`; serve the browser `dist` with its `--static` option. [The API guide](docs/api.md) documents contracts, statuses, generation, schema limits and SDK use. Older language revisions require explicit `nex migrate`; their archived sources/history are retained.

## Generic libraries

`struct Box<T>`, `enum Maybe<T>` and `fn identity<T>(value:T) -> T` are checked even when unused. Concrete calls infer type arguments or supply them explicitly. Builtin bounds such as `T: add`, `T: ordered` and `T: integer` state required operations and are checked before specialization, including abstract forwarding. `examples/generics` and `examples/constraints.nex` exercise reusable models/functions and backend agreement. Source-template edits rebuild derived instances. User traits, associated types and fixed constructor parameters are implemented in language 0.16; see [traits](docs/traits.md). General type lambdas and broader higher-kinded inference remain pending.

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

The native backend emits a separate object for each reachable concrete function, closure and generic specialization, avoids redundant entry-only IR generation and shares checked operation-site indexing. Body edits can reuse siblings in the same file; call contracts, source coordinates and transitive record layouts invalidate affected consumers. `nex build FILE --json` reports compiled/reused function and module counts and the `compilation` report path. Stable DWARF paths map to each session's complete frozen sources. The [build guide](docs/incremental.md) covers keys, dependencies, artifact integrity and remaining frontend/LTO/test-cache work. Programs are checked before cached code is selected; exact platform/SDK validation is recorded in STATUS.md.

## Debugging and editor integration

```sh
./build/nex debug examples/debugging/main.nex
./build/nex debug examples/debugging/main.nex --kind nex-dap --json
```

Native debug builds include typed parameter/local records and lexical scopes. LLDB loads matching previews for strings, lists, records and results; `nex-values` returns a bounded read-only JSON frame report. The DAP session descriptor supplies a stdio adapter command and launch configuration for a compatible client using an installed `lldb-dap`. Pure NEX watch expressions use exact captured values and a separate interpreter. Demand-driven reads select list lengths, record fields, result tags and dynamic indices without serializing unrelated payloads; computed aggregates support paged children. Native list/byte roots also support bounded pages through the matching NEX DAP bridge; textual previews retain their separate limits. [The expression guide](docs/expressions.md) covers LLDB commands, offline snapshots, adapter registration and operational limits. [The debugging guide](docs/debugging.md) covers breakpoints, immutable source projections, value limits, validation and remaining expression/platform work.

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

The complete language and development chain remain under development.
macOS ARM64 and Linux ARM64 are the primary exercised root hosts. Earlier0.72
development candidates also ran on a separate Astra Linux1.7.4 x86-64 guest;
those SDK/toolchain checks retain their exact compiler scopes. macOS Intel binaries can be cross-built, but their execution is
unverified. Native Windows-hosted SDKs, mobile device execution and native UI/GPU remain
pending. Experimental scalar Wasm and mobile project generation retain their
specific guide limits.

Source-level async, general external-resource kinds and callbacks, full
pre/post-contract execution, optimized-PC/core attribution, browser profiling,
remote package retrieval and cross-model quality/token benchmarks remain open.
The native debugger's indexed previews are separate from exact captured NEX
values; named roots and native string-root paging retain their stated limits.
See the relevant guides and PLAN.md for precise scope.

Older language archives require explicit history-preserving migration with
`nex migrate`. Keep their matching SDKs for old debug sessions and receipts.
The project is the language and its development tools; application products
will be built afterwards using NEX.


The development toolchain0.106 adds [explicit task execution limits](docs/task-limits.md): native application ceilings, reference/TypeScript host controls, reviewed project configurations and captured acceptance/replay. Source language0.19 and stored identities remain unchanged; current SDK/platform acceptance is reported separately.
