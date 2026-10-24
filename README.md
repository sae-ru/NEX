# Development0.127: independent reference resource regions

The serial AST scheduler now has an explicit trusted-host resource-region opt-in.
Its separate Reference-family authority follows actual scopes, checks promotion,
and waits for physical cleanup on ordinary completion, cancellation, timeout and
exceptional unwinding. Other ready AST jobs continue while an executor finalizer
is pending. Query `resource_regions`; read [the host contract](docs/resource-regions.md).
Source task input/result/channel/capture transport and the FFI/device bridge remain
pending. Language0.21 and the approved primary0.81 are unchanged. Matching current
full regression, installed SDK and platform delivery are still required.

# Development0.126: private native logical resource regions

The trusted native TaskGroup adapter can enable explicit logical resource regions.
It preserves256 scope depth with bounded physical joins, checked ancestry and
explicit ancestor promotion. Scope exit parks until its complete physical cleanup
fence; destructors run outside scheduler locks and on a supplied executor when
required. Root group retirement owns the remaining promoted resources.
Query `resource_regions`; read [the exact host scope](docs/resource-regions.md).
Source task/FFI/value transport and request-parent
transfer and actual devices remain pending. Language0.21 and primary081 stay intact.

# Development0.125: executor-owned external cleanup

The private trusted host executor constructs and destroys selected external
resources on one owning thread. Cleanup slots are reserved before factories;
logical close/cancel retains physical leases and object/byte quota until the
actual destructor and code-pin release finish. Operation completion follows
physical settlement and destruction of its retained host operation.
Query `resource_executor`; read [its precise scope](docs/resource-executor.md).
Source-task ownership, C executor binding and actual GPU/NPU objects are still
pending. Language0.21, public guards and historical canonical identities are
unchanged. This separate development tree does not promote primary0.81.

# Development0.124: resource debugger arguments and current example pins

DAP launch uses its args array exactly once; raw LLDB CLI receives one run-args
command. Both ordinary and project debug commands follow the same rule. A real
resource debugger gate checks quoted operator paths, archived source, alias IDs,
pure watch refusal, stale references and graceful cleanup. Source language stays
021, with no canonical or graph migration change from0.123. Current proof/task
and type-patch snapshots are regenerated while retaining reviewed clauses,
checks, outputs and budgets. Full matching delivery acceptance remains required.

# Development0.123 / language0.21: opaque source resources

The current candidate enables server resource declarations, genuine typed extern
owners, server/ffi alias close/status and explicit history-preserving migration.
Graph type identities remain stable; editor/LSP projections distinguish resource
declarations and exact name tokens. See [source resources](docs/source-resources.md).
Matching full compiler/SDK/platform acceptance is still in progress. Source task
completion, owned GPU/NPU resources and actual resource debugging remain pending.
The approved primary0.81 checkout is separate and is not promoted by this work.

# Historical private137 source integration

Explicit internal0.21 source staging adds server resource declarations, generic
resource identities, typed extern owners and server/ffi close/status operations.
The reference and MLIR backends execute these through actual pinned C11/C++20
modules. Constructors, wire/browser/task/channel/parallel authority transport
are rejected. Public CLI/default language remains0.20; migration, public
resource publication and actual device/task integration remain pending.
Read [the private boundary](docs/external-resources-design.md).

The first scoped probe passed28 source cases/51 commands, two real native
applications and C++ factory throw cleanup. All12 genuine020 revisions recheck
to their original hashes. The maintained gate additionally checks native
throw/checked-trap exits with live owners. Matching current regression, installed
SDK, actual resource debugging and migration gates remain separate required work.

# Private136: typed external-resource C and loader integration

This cohort adds an append-only C resource suffix, result-reachable constructors,
actual pinned module callback/borrow ownership, physical capacity retention and
lexical/request revocation. Its normal seven-group private host/compatibility gate
passed, including21 new C boundary cases and the preceding21 owned-value cases.
Sanitizer, compiler/runtime integration and platform gates for this exact cohort
remain pending. Source resource declarations, task/FFI tickets and actual owned
GPU/NPU resources are still unavailable. Read
[the exact contract](docs/external-resources-design.md).

The preserved134/0.122 compiler separately passed fresh full154, installedSDK33
(595 commands/280 resources), and18 actual Chromium/Firefox/WebKit task cases.
That accepted local SDK has its own exact compiler SHA and does not validate new
private136 code. Primary0.81 and original graph history remain unchanged.

# Private135: owned external value foundation

A separate host prototype now adds typed external resource owners, physical byte
budgets, managed values and C opaque forwarding. Public source resource types,
typed construction, device executors and task/ffi integration remain pending.
Read [the implementation contract and required integration](docs/external-resources-design.md).
This changes no source language or migration and does not enable owned handles
in std/model. The frozen134 candidate and its historical full154/SDK33 gates remain
separate and unchanged. The private host foundation passed21 cases, existing
file/C compatibility and3 suites each under ASAN/UBSAN and TSAN. Normal evidence
is composite3 after correcting a missing request scope in the new task test;
the original failure remains retained. See [scope](docs/evidence/owned-external-host-foundation.json).
The reference guard has syntax validation; public source behavior and matching
compiler/platform delivery still require their own implementation and gates.

# Development0.122: installed named model contract

This candidate integrates `std/model.nex`, exact discovery/guide/prompt metadata,
installed ONNX provider preparation and matching library/SDK checks. Language0.20
and primary0.81 are unchanged. Build, four focused groups (including9 model
cases/29 compiler commands) and the exact installed model phase passed. That
phase used12 commands with the original compiler source path hidden, standard
model/compute files absent for replay, and standalone resources unavailable.
See [the scope](docs/evidence/model-sdk-0.122-development.json). Full matching154
regression, installedSDK33 and platform delivery remain pending. The verified0.121 core and compatible0.120
experimental provider receipts below retain their original scope.

# Verified local0.121 and experimental models

The unchanged0.121 compiler passed an audited153-group composite (148 original
plus4 TypeScript repeats and the complete8-case Wasm group), installedSDK32/584
commands with its original source path absent, and a separate18-case run in
Chromium/Firefox/WebKit. See [the exact local scope](docs/evidence/compute-0.121-local.json).
Primary0.81 and graph history are preserved. Full current Linux121/portable
bundle and remaining PLAN work are separate.

The experimental [named model API](experiments/models/README.md) accepts pinned
external ONNX artifacts through an isolated CPU/Zhouyi child provider. Its source
contract passed native/reference/TypeScript checks. On CIX, two small F32 models
passed actual NPU execution; a two-input MatMul graph correctly refused NPU
placement and passed explicit CPU fallback. Current receipts contain14 NPU calls,
28 selected CPU calls,14 separate CPU precision references and17 process cases.
A separate Vendor-precision check passed3 CPU/3 NPU calls without a CPU oracle.
See [exact scope and pins](docs/evidence/named-models-0.121-development.json).
These are compatible0.120/language0.20 provider tests, outside installed0.121;
they add no compiler builtin, owned model handle or general task/FFI bridge.

# Development: portable common OpenCL preparation

Prepare a complete checked common-GPU project with `--backend gpu --api compute`.
Select an installed OpenCL loader explicitly with `--opencl-library`; preparation
embeds its absolute path in the pinned child and records runtime provenance.
Matching common-GPU runs passed on CIX and RK3588; each checked49 actualGPU calls and20 worker cases with compatible compiler0.120. Read [the usage and exact scope](experiments/rk3588/README.md).
The only stdlibrary delta is a Context comment correction; executable functions,
compiler and runtime are unchanged from the0.121 core candidate.

# Development: full-U8 OpenCL provider

The ordinary-source compute contract now has an experimental checked OpenCL
provider for Add/Affine0..255, including maximum262144-element tensors, overflow
errors and cancellable device admission. Read [the provider](experiments/rk3588/README.md).
The current Context is a non-wire opaque NEX callable, without a host FFI grant;
its passive/opaque forwarding follows existing language0.20 rules.
Compiler/runtime/library remain identical to the locally verified0.121 core.
The153-group composite and matchingSDK32 passed as recorded above. Device receipts use
the compatible0.120 compiler; full0.121 platform delivery is not claimed.
Primary081 and the full original PLAN remain preserved/open.

# Development0.121: checked compute contract

`std/compute.nex` provides validated immutable tensors, exact integer CPU
operations, typed device/provider contexts and explicit fallback. Read
[the contract](docs/compute.md) and query `nex describe --field compute --json`.
Real common-API adapters have the separately scoped device receipts above.
Language0.20 and primary0.81 remain unchanged. Historical0.120 receipts below
retain their original scopes and do not validate this candidate.

# NEX

Toolchain0.120 development adds task-only `worker_compute` hosting in dedicated
browser Workers, with a separate bounded cooperative scheduler per job. UI
entries remain pure and synchronous; wire values alone cross the worker boundary.
See [the contract](docs/browser-workers.md) and
[the example](examples/task-workers/main.nex). Language0.20 and migration stay
unchanged. The matching frozen implementation passed full152 on Mac, installed
SDK31/575 commands and18 cases in three real browser engines. Physical stand
checks retain their scoped receipts. See [current acceptance](docs/stand-acceptance-0.120.md).

**NEX — Neural Execution Language** («язык нейронного исполнения»).

**Главная идея:** минимальное количество токенов для передачи максимального
количества точного смысла при максимальной производительности и безопасности
исполняемой системы.

This isolated development source is **toolchain0.121.0 / language0.20**.
New [RK3588 opt-in fixtures](experiments/rk3588/README.md) retain separate device
acceptance; their addition changes no compiler/runtime/language semantics.

The previous0.119 checkpoint is retained below as history.
Working126 provides development source-backed logical task debugging across
concrete static and fixed startup-linked shared providers. Actual generated-image
LLDB/NEX-DAP, relocated delivery and bounded physical-drain/sanitizer preflights
pass; full matching regression, installed SDK31 and platform delivery have
separate receipts. Query `task_provider_debugging` and read
[the bounded contract](docs/task-provider-debugging.md).
Execution ABI3, source syntax and history-preserving migration remain unchanged.

Preserved125b / toolchain0.118.0 provides a checked native task-provider profiling
across concrete static archives and fixed startup-linked shared images. Its
matching ten-case source/report suite, separate private physical-drain fence and
exact scoped SDK30 phase body passed. Its retained Mac regression is composite148
(147 original passed groups plus the corrected55-check boundary group); scoped
Linux is composite11 (10 original groups plus that correction). Matching installed
SDK30 passed30 phases/557 commands with269 indexed resources; its original compiled
source path was absent and restored unchanged. See the
[exact125b checkpoint](docs/evidence/toolchain-0.118.0-task-provider-profiling.json).
Original failures remain retained; this is no pristine-full, full-Linux or kernel
source-isolation claim and does not validate126. Query
`nex describe --field task_provider_profiling --json` and read
[provider task profiling](docs/task-provider-profiling.md). Broader platform acceptance
remains separate. Language/canonical
identity, migration and execution ABI3 remain unchanged.

Preserved124d / toolchain0.117.2 passed a pristine full144 regression and matching
installedSDK29/542 commands. Seven scoped LinuxARM64 groups and the separate
private image fence/sanitizers passed. It fixes atomic cache-image publication
and literal parent-path handling; original124b/c failures remain retained. See the
[exact124d development checkpoint](docs/evidence/toolchain-0.117.2-task-shared-providers.json)
and [shared task providers](docs/task-shared-providers.md). These results cover
that snapshot, without a full Linux/installed Linux SDK or kernel source-isolation
claim. They do not validate Working125 provider profiling.

Preserved123 adds concrete static task providers with checked source and real
code-only archives. Its17-case scoped suite and production SDK phase body passed.
Its original full141 found one stale capability assertion; a test-only repair
passed the entire21-case integration group with the same frozen compiler, and
an explicit140+1 composite is retained. Matching installedSDK28 passed28 phases/523 commands with262 indexed resources;
four scoped Linux groups passed17 actual cases. See the [exact123b acceptance
summary](docs/evidence/toolchain-0.116.0-task-providers.json) and
[static task providers](docs/task-providers.md). These results do not validate
Working124 shared integration. Source syntax/language history and task execution
ABI3 remain unchanged.

Preserved122 enables narrow native020 logical task debugging with a separate
catalog ABI. Its recorded regression is composite139:138 original passed groups
plus the corrected9-case server workload group using the same compiler. The
original numeric-metric/text-marker false-positive failure remains retained;
there is no claim of a pristine full139 rerun. Matching installedSDK27/504
commands and three scoped Linux groups passed. See the [exact122 acceptance
summary](docs/evidence/toolchain-0.115.0-task-debug.json) for hashes and limits.
These results do not validate later provider integration.

Frozen121 passed full134 and scoped Linux profiling gates; its matching
installedSDK26/498 commands passed with its original compiled source path absent
and restored unchanged.

Frozen121 integrates native source task profiling across compiler, scheduler,
retained source frames and checked CLI/project/replay reports. Its accepted
development checkpoint retains exact full134/SDK26 and scoped sanitizer/Linux
receipts. Language020 and history-preserving migration remain unchanged;
execution ABI3 and its site metadata were checked together. Frozen120's collector passed its scoped common,
strict sanitizer and Linux module gates, full129 regression and its matching
installed SDK25/486 commands.
Frozen119b full128 and its matching installed SDK25/486 commands passed.
The implementation connects the two existing whole-file read operations to structured
suspension in explicit server `!{task,fs}` functions. Native macOS/Linux
applications/source-only projects and the independent reference scheduler use
a root-captured revocable grant, bounded raw host operations and scheduler-only
result admission. See [task file reads](docs/task-file-reads.md) and the
[example](examples/task-file-reads.nex). Current0.120 acceptance is recorded above.

Migration explicitly rechecks genuine019 source and a separate020 target before
mutable destination access; existing history/IDs/schema remain intact. A task
calling an fs-only helper is rejected until its declaration is reviewed. Scope
and spawn callbacks additionally accept exactly server task/fs with matching
caller effects. There are no new source keywords or implicit callable upcasts.

The frozen115 separately passed122 regression groups and matching installed
SDK24/438 commands, strict sanitizers, three production private-kernel browser
engines and21 Linux ARM64 groups. Frozen116 passed the shared build,20 focused groups, strict sanitizers,
full122 and matching installedSDK24/438. These receipts
apply to their exact source snapshots. Primary081 remains preserved.

Checked source tasks retain native compiled continuations and independent
AST/TypeScript schedulers, conservative lifetime diagnostics and mandatory
runtime guards. TypeScript/browser filesystem, task writes/streams/db/ffi/network,
HTTP task handlers, non-native task debugging/profiling, runtime provider loading/unloading,
combined task debug/profile, NEX UI task adapters,
other task platforms and complete static region inference remain pending.

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

Language 0.20 retains ordered CPU mapping, introduced in 0.18, through
`parallel_map(items, callback, workers)`. Native macOS/Linux uses bounded joined
threads, pure available-realm callbacks and checked resource-free captures.
Reference and current public TypeScript execute this operation serially. The
dedicated browser-worker adapter is separate; task-only worker_compute is
now hosted in its own bounded scheduler, with pure synchronous main-thread UI. See [the contract](docs/concurrency-design.md) and
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
GPU/NPU language APIs. Broader asynchronous IO, task delivery, general accelerators, source
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
