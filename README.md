# NEX — Neural Execution Language

[Русский](README.ru.md) · [Language overview](docs/overview.en.md) · [Get started](docs/getting-started.en.md) · [For LLMs](llm/LEARNING.md) · [Current status](docs/STATUS.current.md)

**Precise programs, bounded context, native execution.**

NEX is a programming language and development toolchain for humans and language
models. Its central idea is to communicate the greatest amount of exact meaning
with the fewest necessary tokens, while pursuing high execution performance and
safe runtime behavior. These are engineering goals with explicit acceptance
criteria.

You write readable `.nex` source. The compiler checks types, effects and execution
boundaries, keeps a versioned semantic graph, and generates native code through
MLIR/LLVM or TypeScript for the browser. The compiled application runs independently
of an LLM.

```nex
module hello;
fn answer(x: i64) -> i64 { return x * 2; }
fn main() -> unit !{io} { print(answer(21)); }
test fn answer_is_42() -> unit { assert(answer(21) == 42); }
```

## Where the acceleration comes from

- **Less repeated context.** Ask the compiler for one capability or a bounded
  symbol context instead of loading the whole project into a model prompt.
- **Earlier feedback.** Checked types, effects, realms and rejected programs
  expose mistakes before execution. Tests compare observable backend behavior.
- **Less repeated compilation.** Content identities and cached native functions
  let unchanged code and runtime objects be reused.
- **Compiled execution.** Native applications execute machine code. Explicit CPU
  mapping and device providers cover their advertised, measured scopes.

The repository includes [measurements and limitations](docs/overview.en.md#measurements).
A [recorded 0.162.2 checked-integer benchmark](docs/evidence/macos-e63-sdk-complete-0.162.2-2026-11-09.json)
measured median wall times of 0.296170 s for NEX, 0.290189 s for checked C++ and
7.610111 s for Python on one Mac. These are one-workload observations.
The [first local Qwen3.8 27B task comparison](docs/llm-cost-qwen38-27b-2026-11-11.en.md)
found no NEX token saving. Other models/workloads remain unmeasured.

## What you can build

The implemented core includes modules, generics and traits, immutable aggregates,
linear list/text/byte construction, Unicode strings and bytes, checked arithmetic,
typed source errors and `finally`, structured tasks, graph history, project
components, native libraries, HTTP/API and browser adapters, debugging,
profiling and bounded scalar verification.

A project can share portable logic between a native server and a TypeScript /
React / Vite client. Device execution uses explicit trusted providers. Read the
[overview](docs/overview.en.md) for the distinction between source features and
platform acceptance.

## Development status

Current source: **toolchain 0.243.0 / language 0.28 / task ABI 7**, in development.
Language 0.29 is an explicit opt-in for partial type lambdas and higher-order kinds;
0.28 remains the default and rejects those constructs. The compiler default is not
a project default: `nex.json` selects 0.28 or 0.29 explicitly per project.

The 0.243 full macOS regression passed **351/351 groups**. The immutable
[macOS SDK 0.243.0](docs/releases/0.243.0.json) was accepted end-to-end: 4015
inventory files, 41 phases, real locked browser builds and the full network
profile. The relocatable archive is `nex-sdk-0.243-macos-arm64.tar.gz`
(SHA-256 `72d093d5...e37417`). The owned Metal provider also ran on an Apple
**M5 Max** with 15 hardware scenarios, 12 reply faults, log isolation and 27+1
source checks; see the [Metal receipt](docs/evidence/owned-metal-0.243.0-2026-11-13.json).

Browser applications support workers, `web/app.css`, `web/public/` assets,
`web/index.html`, application-provided `web/components.tsx` and generated file
hashes. iOS and Android projects are generated from the same checked web output:
iOS built in Xcode for the iOS 27.1 simulator, and Android built `app-debug.apk`
with JDK21/API36; both were installed/launched with actual UI, and Android input
added and completed a task. See the [iOS receipt](docs/evidence/mobile-ios-0.243.0-2026-11-13.json)
and [Android receipt](docs/evidence/mobile-android-interaction-0.243.0-2026-11-13.json).

| Platform | Recorded evidence | Remaining qualification |
|---|---|---|
| macOS ARM64 | [351/351 full CTest](docs/evidence/full-ctest-0.243.0-2026-11-13.json); [immutable SDK 0.243](docs/releases/0.243.0.json); [physical Metal M5 Max](docs/evidence/owned-metal-0.243.0-2026-11-13.json) | extended interactive web/mobile matrices, signing |
| Astra Linux 1.7 x86-64 | [0.242 build, core 12/12, native smoke](docs/evidence/platform-cross-compiler-0.242.0-2026-11-13.json) | extended/browser/SDK groups |
| Fedora 45 x86-64 | [0.242 Clang 23 build, core 12/12, native smoke](docs/evidence/platform-cross-compiler-0.242.0-2026-11-13.json) | extended/browser/SDK groups |
| Windows 11 x86-64 | [0.242 LLVM-MinGW build, core 12/12, native smoke](docs/evidence/platform-cross-compiler-0.242.0-2026-11-13.json) | extended/browser/SDK groups |
| iOS Simulator | [generation, Xcode build, install/launch, actual UI](docs/evidence/mobile-ios-0.243.0-2026-11-13.json) | scripted input, device signing/store delivery |
| Android emulator | [APK build, launch, add/complete interaction](docs/evidence/mobile-android-interaction-0.243.0-2026-11-13.json) | device matrix, signing/store delivery |
| CIX ARM64 | [Snapshot `979ef54`: 36 GPU and 26 NPU calls, CPU fallback disabled](docs/evidence/cix-current-source-GPU-NPU-0.165.0-2026-11-10.json) | matching current source regression and portable SDK |
| RK3588 ARM64 | [Snapshot `2172b35`: 63 GPU and 30 NPU calls](docs/evidence/rk3588-current-GPU-NPU-0.165.0-2026-11-10.json) | matching current source regression and portable SDK |

CUDA and OpenCL source emitters remain bounded checked-AST paths; CUDA device
execution and provider phases retain their own earlier receipts. General GPU/NPU
compilation, Apple NPU, complete native-desktop UI, NEX Studio, project conversion,
signed/public upload, device signing and measured cross-model token savings remain
[planned work](PLAN.md). Retained CIX/RK NPU results are real hardware receipts but
do not qualify the current compiler/archive.

[STATUS.md](STATUS.md) and [versioned evidence](docs/evidence/) retain the
history, exact source/compiler/archive identities, original failures and scope
of each result. An earlier SDK's acceptance does not qualify a new archive.

## Build and use

Start with the [current installation guide](docs/getting-started.en.md). A source
build requires C++20, CMake 3.25+, LLVM/MLIR 22.1.x or 23.1.x, SQLite, OpenSSL 3 or 4, Z3 and
Python 3.10+. The full CTest suite includes Web/TypeScript workflows and also
requires Node.js 22.18+, npm and the repository's locked web dependencies.
On Unix, the ELF fixture tests also require matching LLVM `ld.lld` and `llvm-ar`;
use `-DNEX_ELF_TEST_LD=/absolute/path/to/ld.lld` when LLD has a separate prefix.

For a short development loop after configuring, use the [11-group core layer](docs/testing.md):

```sh
cmake --build build --target nex_core_tests -j 4
ctest --test-dir build -L '^core$' --output-on-failure
```

It needs the selected compiler build and Python, with no Node/npm preparation.
The [tier inventory](cmake/test-tiers.json) also labels browser, platform, SDK and
scale groups.

Shared [development presets](docs/development-build.md) also provide
`cmake --workflow --preset dev-core` with separate Debug/Release build directories.
See [CI receipts and workflow scope](docs/ci.md) for the automated checks.
The [source-to-archive SDK driver](docs/sdk-build.md) joins the maintained
macOS/Linux workflows; complete execution of the new driver remains pending.

Use the complete workflow below at the agreed milestone:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
npm --prefix web ci --cache "$PWD/build/npm-cache" --ignore-scripts --no-audit --no-fund
NEX_TSC="$PWD/web/node_modules/typescript/bin/tsc" \
NEX_NPM_CACHE="$PWD/build/npm-cache" \
ctest --test-dir build --output-on-failure
cmake --install build --prefix /absolute/path/to/nex-sdk
```

For saved CTest results, use the [registry/JUnit checker](docs/ctest-results.md).
It includes required fixture groups and rejects incomplete or skipped runs.

Keep `bin/nex` and `share/nex` together. Ordinary CMake installation uses the
build machine's dependencies; [portable SDK packaging](docs/sdk.md) is a separate
verified workflow.

```sh
nex doctor --json
nex describe --kind index --json
nex init /path/to/my-app
```

## Documentation

[Documentation index](docs/INDEX.md) · [Specification](docs/language.md) · [Grammar](docs/grammar.ebnf) ·
[Architecture](docs/architecture.md) · [Web](docs/web.md) ·
[Project builds](docs/project-build.md) · [Errors](docs/exceptions.md) ·
[Debugging](docs/debugging.md) · [Profiling](docs/profiling.md) ·
[Quality criteria](docs/quality.md) · [Windows handoff](docs/windows-handoff-current.md)

For agents, start with [llms.txt](llms.txt), [AGENTS.md](AGENTS.md),
[BOOTSTRAP](llm/BOOTSTRAP.md) and the [coding contract](llm/SYSTEM_PROMPT.md).
The roadmap and historical development notes describe work beyond implemented
support; always verify the actual compiler and matching evidence.

## License

NEX-authored code and documentation use the [MIT license](LICENSE). Bundled
components retain their own [licenses and notices](THIRD_PARTY.md).
