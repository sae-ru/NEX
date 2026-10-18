# NEX

**NEX — Neural Execution Language** («язык нейронного исполнения»).

**Главная идея:** минимальное количество токенов для передачи максимального количества точного смысла при максимальной производительности и безопасности исполняемой системы.

People and LLMs work with a checked semantic graph. The model helps create and change programs; compiled applications run without an LLM.

NEX is a language and development toolchain built around a checked semantic graph. The current implementation is an early C++20 compiler, not the full system in `PLAN.md`.

The working tree is toolchain **0.47.0 / language 0.15**, adding checked native
integer fast paths. Signed overflow checks and guarded division/remainder stay
in SSA; failure branches retain native operation diagnostics. Source syntax,
evaluation order, C value ABI 1 and canonical identities are unchanged. All 55 groups and both installed SDK workflows pass on macOS/Linux ARM64;
[the evidence](docs/evidence/native-arithmetic-0.47.0.json) records exact scope.
Broader validation remains pending in `STATUS.md`.

The preceding verified **0.46.0 / language 0.15** snapshot adds bounded native
runtime trap reports, checked graph mapping and archived log diagnosis. All 54
groups pass on macOS/Linux ARM64, alongside both thirteen-phase installed SDK
workflows and Linux live debugger checks. [The evidence](docs/evidence/native-diagnostics-0.46.0.json)
records exact scope; the [guide](docs/native-diagnostics.md) defines trust and limits.

The preceding verified **0.45.0 / language 0.15** snapshot adds atomic source
type replacements together with affected functions/endpoints. All 52 groups pass
on macOS/Linux ARM64, with both installed SDK workflows and Linux live checks.
[The evidence](docs/evidence/type-patches-0.45.0.json) records exact scope.

The preceding verified **0.44.0 / language 0.15** snapshot adds persistent
module/type nodes, bounded declaration context and atomic, snapshot-scoped
identity reconciliation between stores. Its current validation is recorded in
`STATUS.md`; [the graph guide](docs/graph.md) describes the protocol.

The corrected snapshot passes all 51 regression groups on macOS/Linux ARM64,
both thirteen-phase installed SDK workflows and the Linux live debugger matrix.
The [graph evidence](docs/evidence/graph-identities-0.44.0.json) records the exact
scope, the nested-match traversal correction and pending broader validation.

The preceding verified snapshot is toolchain **0.43.0 / language 0.15**. It adds
matching-host native application packaging with explicit foreign-library grants,
recursive dependency/notices collection and checked, history-preserving pin
projections. The corrected implementation passes all 50 macOS/Linux ARM64 suites,
both thirteen-phase installed SDK workflows and Linux live debugger checks.
Catalogue input bounds, offline schema references and native image identity are
covered by the checks. Broader platform/release/distribution work remains pending;
see `STATUS.md` for exact evidence and remaining work.

Implemented code includes a parser, type/effect/realm checker, modules with private/public definitions, Unicode strings, immutable lists, structures and algebraic enums with nested patterns, guards and exhaustive statement/value matches, parametric generic types/functions, typed callbacks and immutable snapshot closures, a reference interpreter, SQLite/BLAKE3 revision store, transactional patches across modules, model-independent JSON tools, an MLIR → LLVM → native pipeline, and a TypeScript → React/Vite browser pipeline. Verification status and remaining scope are recorded in `STATUS.md`.

Toolchain 0.24 / language 0.11 introduced finite binary64 arithmetic. Source programs, generic numeric functions, native/TypeScript/interpreter execution, typed JSON/API models and float watches passed the macOS ARM64 and Linux ARM64/x86-64 development matrix. Installed SDK acceptance includes numeric browser state and source-deleted replay; Linux x86-64 execution is emulated. Broader platforms remain pending; macOS/Linux development SDK bundles are verified in 0.30. The [numeric design and acceptance plan](docs/floats-design.md) records the scope and limits.

Toolchain 0.30 / language 0.12 adds server-only text-file operations with a
separate `fs` effect, explicit directory access and read-only defaults. Native
HTTP scopes deny implicit environment grants. The [file guide](docs/files.md)
describes syntax and limits; full validation of this new language version is
tracked in `STATUS.md`.

Development 0.33 / language 0.13 connects immutable `bytes` to the checker,
interpreter, native/TypeScript backends, typed JSON/API and bounded debugger
values, with server-only binary files. Current compiler and installed-SDK checks
passed on macOS ARM64 and Linux ARM64/emulated x86-64. The maintained SDK
distribution workflow verifies moved/restored archives; current artifact status
is in `STATUS.md`. The [binary guide](docs/bytes.md) gives exact
interfaces; the [design history](docs/bytes-design.md) preserves prototype scope.

Development 0.35 keeps language 0.13 unchanged and extends the internal resource
runtime with managed file values, native streaming calls, request revocation and
JSON exclusion. [The ownership design](docs/resources-design.md) defines cleanup,
physical leases/quotas and cancellation. Source handles, FFI and async remain
pending; current checks are tracked in `STATUS.md`.

Development 0.36 / language 0.14 adds the opaque server-only `file` type and ten
streaming operations, with `fs`, owner aliases, native/reference agreement and
explicit history-preserving migration from 0.13. Files cannot cross JSON/API or
browser boundaries. [The resource guide](docs/resources.md) documents source
syntax and debugger identities. Validation is tracked in `STATUS.md`.

Current 0.36 checks pass all 42 suites on macOS ARM64 Debug/Release and Linux
ARM64, installed macOS/Linux ARM64 SDK workflows, real LLDB/DAP and managed-file
sanitizers. Corrected Linux x86-64 compiler/SDK checks pass under emulation;
other platforms, current SDK archives, general FFI and source async remain
pending. See [the evidence](docs/evidence/source-resources-0.36.0.json).

Development 0.37 keeps language 0.14 unchanged and adds an experimental C value
transport for trusted hosts. Its [contract](docs/ffi-design.md) covers copied
payloads, call-local owners, quotas, thread checks and sticky host traps. The
25 C/C++ cases pass with sanitizers on macOS ARM64 and Linux ARM64/emulated
x86-64. macOS Debug passes 43 suites and the installed SDK passes thirteen
workflow phases, including an independent C/C++ host. Broader current compiler
and SDK/distribution checks remain pending. Source
foreign declarations and library loading are not implemented yet.

Development 0.38 adds checked host signatures exported by `nex ffi FILE --symbol
NAME --json`, typed input/result validation and C constructors for nominal values.
It preserves the original ABI-1 table prefix and language 0.14. The
[typed host example](examples/ffi/main.nex) agrees with an independent C producer.
macOS Debug passes 45 suites and the installed SDK passes thirteen phases; the
48 legacy/typed C cases pass sanitizers on the stated macOS/Linux scope.
See [the evidence](docs/evidence/ffi-types-0.38.0.json) for remaining validation.
Source external calls remain pending.

Development 0.39 adds explicit host grants and content-pinned native module
loading with checked signatures, private verified snapshots and resource-scoped
physical leases. It keeps language 0.14 unchanged. The
[module contract](docs/ffi-design.md) records trust, dependency lookup and pending
source/packaging work. macOS Debug passes 46 suites and the installed SDK passes
thirteen workflow phases; component sanitizers pass on macOS ARM64 and Linux
ARM64/emulated x86-64. See [the evidence](docs/evidence/ffi-modules-0.39.0.json)
and `STATUS.md` for the exact scope and remaining checks.

Development 0.40 adds explicit operator catalogues, lexical invocation contexts
and the shared managed-value adapter required by source FFI. It preserves
language 0.14; source external declarations and backend lowering remain pending.
The [host contract](docs/ffi-design.md) records the implemented adapter. macOS
Debug passes 47 suites and the installed SDK passes thirteen phases; component
sanitizers and source-free Linux bridge hosts pass on the stated scope.
See [the evidence](docs/evidence/ffi-contexts-0.40.0.json) and `STATUS.md`.

Development 0.41 / language 0.15 connects concrete server `extern` declarations
and `ffi` to the checker, interpreter/native backend, CLI, profiler, debugger
and browser reachability rules. Its [evidence](docs/evidence/source-ffi-0.41.0.json)
records full macOS/Linux ARM64 regressions and installed SDK scenarios, including
source-deleted execution. Broader current platforms and stable ABI validation
remain pending.

Development 0.42 keeps language 0.15 and adds `nex foreign HOST.json` read-only
inventory discovery. Native task execution checks pin `foreign_hash`; task
check/run/replay requires current `--foreign HOST.json`, captures exact module
bytes and rejects changed/unauthorized inputs. See [tasks](docs/tasks.md) for
trust, input limits and replay. Matching-host native dependency-closure packaging
is added in 0.43; current validation is recorded in `STATUS.md`.

Development 0.43 retains language 0.15 and C ABI 1. `nex package --foreign`
copies reachable native module closures, preserves complete notices, derives
new checked source pins and retains both graph revisions without editing source
files or moving HEAD. Standalone applications resolve their deployed catalogue
from the actual executable location. See [packaging](docs/packaging.md) for
native loader scope, trust and pending platforms.

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
reuse, Linux tools and runtime configuration. Toolchain 0.29 passed the stated macOS/Linux compiler, SDK and deployment matrix.

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

Toolchain 0.25 introduced a separate native object for each reachable concrete function, closure and generic specialization. Development 0.26 removes redundant entry-only IR generation and shares checked operation-site indexing; its performance/full matrix validation is in progress. Body edits can reuse siblings in the same file; call contracts, source coordinates and transitive record layouts invalidate affected consumers. `nex build FILE --json` reports compiled/reused function and module counts and the `compilation` report path. Stable DWARF paths map to each session's complete frozen sources. The [build guide](docs/incremental.md) covers keys, dependencies, artifact integrity and remaining frontend/LTO/test-cache work. Programs are checked before cached code is selected; the new full platform/SDK matrix remains in progress.

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

The current verified development checkpoint is **0.47.0 / language 0.15**, with 55 regression groups passing on macOS/Linux ARM64, installed SDK workflows and Linux live debugger checks. Broader current Release, sanitizer, x86-64 and SDK distribution checks remain pending; consult `STATUS.md` for exact coverage. Language 0.5/0.6/0.7/0.8/0.9/0.10/0.11 archives require explicit history-preserving migration; old debug sessions and receipts require their matching compiler binary/resources. Code targets are host native, native HTTP/HTTPS and browser TypeScript with explicit request/cancel commands. macOS ARM64 and Linux ARM64/x86-64 execution are exercised; Linux x86-64 uses emulation. macOS Intel execution and Linux x86-64 live debugging remain unverified. OR/rest/range patterns, custom generic traits, general source-level async/resource FFI, richer data/resource proofs, source-level contract enforcement, broader task/agent operations, mobile/native UI/GPU targets, remote package retrieval and broader SDK/platform distribution remain pending. The requested project is the language and complete development chain. Application products will be built afterwards using NEX.
