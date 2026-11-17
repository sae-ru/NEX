# NEX — Neural Execution Language

[Русский](README.ru.md) · [Language overview](docs/overview.en.md) · [Get started](docs/getting-started.en.md) · [For LLMs](llm/LEARNING.md) · [Codex skill/plugin](plugins/nex/README.md) · [Current status](docs/STATUS.current.md)

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

Current source: **toolchain 0.280.1 / language 0.28 / task ABIs 7/8**, in development.
The [control correction](docs/evidence/native-owner-control-0.280.1-2026-11-17.json)
preserves timeout/cancellation outcomes in borrowed native task scopes.
The [0.280.1 full source baseline](docs/evidence/sdk-source-and-relocation-first-0.280.1-2026-11-17.json)
passes388 groups. Its first portable SDK attempt passed41 relocated phases
before a test linker argument split a comma-containing archive path. Delivery
fixes pass19 core/affected groups; current archive qualification remains pending.
The compiler fallback remains0.28. `nex.json` selects0.28,0.29 or0.30 per project;
new `nex init` projects select0.30. Language0.29 adds partial type lambdas and
higher-order kinds;0.30 adds typed cells and the `state` effect. Retained projects
preserve their selected version and require explicit migration to change it.

[Owner-thread storage](docs/task-storage.md) lets030 server tasks use blocking
SQLite operations in their existing invocation/HTTP transaction. Native task
graphs with storage select ABI8 even without cells. The
[Workboard application](examples/workboard/README.md) combines persistent UI,
HTTP tasks, SQLite, file export/restore and a dedicated summary Worker.
[Focused acceptance](docs/evidence/workboard-task-storage-0.280.0-2026-11-17.json)
and complete SDK/platform delivery remain separate scopes.

Libraries provide [hash containers](docs/hash-containers.md),
[ordered maps](docs/ordered-containers.md) and [queues/heaps](docs/sequence-containers.md).
[Java int](docs/java-integers.md)/[long](docs/java-long.md) are explicit domains;
the [IEEE kernel](docs/ieee-numeric.md) still has no source types.
[Source030](docs/references030.md) supports references through native libraries,
HTTP, structured tasks, persistent UI and [native host sessions](docs/native-task-sessions.md).
Native [debugging](docs/reference-provider-debugging.md) and
[profiling](docs/reference-task-profiling.md) cover source-backed provider images.
HTTP debugging/profiling, parallel reference transfer and other
[migration prerequisites](docs/migration-readiness.md) remain open.
The [implementation sequence](docs/implementation-1-6.md) tracks remaining work.

The immutable [macOS ARM64 SDK0.246.1](docs/releases/0.246.1.json) passed
351 source groups and41 phases each after relocation/archive restoration,
with locked browser builds and full network checks, at its recorded source.
[Download](https://github.com/sae-ru/NEX/releases/tag/v0.246.1) and
[install](docs/getting-started.en.md#install-the-macos-arm64-sdk).
Current source/SDK qualification remains separate. See [CI scope](docs/ci.md).

Browser applications support workers, custom CSS/assets/HTML/React components
and generated file hashes. iOS/Android projects share that checked web output;
macOS embeds it through `nex://app/`. Recorded builds and UI interactions are
listed below, with delivery gaps kept separate.

| Platform | Recorded evidence | Remaining qualification |
|---|---|---|
| macOS ARM64 | [0.280.1 source388/388 and delivery correction](docs/evidence/sdk-source-and-relocation-first-0.280.1-2026-11-17.json); [immutable SDK0.246.1](docs/releases/0.246.1.json); [physical Metal M5 Max](docs/evidence/owned-metal-0.243.0-2026-11-13.json) | corrected current SDK archive, extended interactive web/mobile matrices, signing |
| Astra Linux 1.7 x86-64 | [0.280.1 build, core17/17, native app](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended/browser/SDK groups |
| Fedora 45 x86-64 | [0.280.1 Clang23 build, core17/17, native app](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended/browser/SDK groups |
| Windows 11 x86-64 | [0.280.1 core17 unique groups, native app, CUDA35/35](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended/browser/SDK groups; intentional IPv6 restrictions retain a separate scope |
| iOS Simulator | [Debug/Release, install/launch, actual UI, test-driver input](docs/evidence/mobile-ios-release-0.244.0-2026-11-13.json) | device signing/store delivery |
| Android emulator | [signed release APK, launch, add interaction](docs/evidence/mobile-android-release-signed-0.244.0-2026-11-13.json) | Play Store delivery |
| macOS desktop app | [standalone embedded app, live input](docs/evidence/desktop-macos-interaction-0.244.0-2026-11-13.json) | Developer ID, notarization |
| CIX ARM64 | [0.280.1 core17/17 +12 Mali GPU/8 Zhouyi NPU](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended source regression and portable SDK installation |
| RK3588 ARM64 | [0.280.1 Ubuntu24 ARM64-container core17/17 +49 GPU/30 NPU](docs/evidence/stands-current-0.280.1-2026-11-17.json) | native Jammy qualification and portable SDK |

CUDA/OpenCL emission remains bounded. General GPU/NPU compilation, Apple NPU,
native desktop UI, Studio, conversion, signed installers and cross-model token
savings remain [planned work](PLAN.md). Older device receipts do not qualify
the current compiler/archive.

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

For a short development loop after configuring, use the [17-group core layer](docs/testing.md):

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
macOS/Linux workflows; [0.246.1 completed the full macOS sequence](docs/evidence/sdk-current-0.246.1-2026-11-15.json).
Portable Linux/Windows SDK qualification remains separate.

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
