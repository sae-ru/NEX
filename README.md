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
The [latest local Qwen3.8 27B task comparison](docs/llm-cost-qwen38-27b-2026-11-17.en.md)
accepted6/20 NEX,18/20 C++ and20/20 Python attempts. Two NEX calls have unknown
usage; no NEX token saving is established. Other models/workloads remain unmeasured.

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
The compiler fallback remains0.28. Projects explicitly select0.28,0.29 or0.30;
new `nex init` projects select0.30. Existing graphs need an explicit migration.

The [macOS ARM64 SDK0.280.1](docs/releases/0.280.1.json) is published from
`bfb34928`, qualified at main `b02514eb`. [Source coverage](docs/evidence/sdk-current-0.280.1-2026-11-17.json)
combines387 groups from the full run with all16 tests in the corrected snapshot
group, on the same compiler/resources. Its only correction follows the compact
prompt to the detailed rules; the original failed receipt is attached.
This covers388 groups and is explicitly not one passing full invocation.
Moved and archive-restored installations each passed **43 phases**, including
locked production browser builds, full networking and live LLDB/DAP debugging.
[Download](https://github.com/sae-ru/NEX/releases/tag/v0.280.1) ·
[Install](docs/getting-started.en.md#install-the-macos-arm64-sdk).
[Core CI](docs/evidence/core-ci-0.280.1-2026-11-17.json) passed17 groups each on
macOS/Linux at the qualification main. The [full Linux attempt](docs/evidence/linux-full-profile-timeout-0.280.1-2026-11-17.json)
passed380/381 groups; profiling hit its aggregate timeout, before installed
checks. [SDK0.246.1](docs/releases/0.246.1.json) retains its original bytes.

Source030 supports typed cells, [structured reference tasks](docs/reference-tasks.md),
[persistent UI](docs/persistent-ui.md), native libraries and
[persistent C++ host sessions](docs/native-task-sessions.md).
[Native debugging](docs/reference-provider-debugging.md) and
[profiling](docs/reference-task-profiling.md) cover source-backed provider images.
[Workboard](examples/workboard/README.md) joins a browser UI, HTTP/tasks, SQLite,
file export/restore and a summary Worker; it is a required SDK consumption phase.
Ordinary libraries include [hash containers](docs/hash-containers.md),
[ordered maps](docs/ordered-containers.md) and [queues/heaps](docs/sequence-containers.md).
[Java int](docs/java-integers.md)/[long](docs/java-long.md) have explicit domains;
the [IEEE kernel](docs/ieee-numeric.md) still has no source types.

The [bounded LLM entry](docs/llm-entry-v2.md) has a4058-byte common contract and
preserves the full detailed rules. Its [observed Qwen study](docs/llm-cost-qwen38-27b-2026-11-17.en.md)
retains all60 outcomes, unknown usage and explicit execution amendments.
The next [reference-context preparation](docs/llm-entry-v3.md) supplies public
source-task/byte guides and normative reviewer context; no new model result is claimed.

| Platform | Recorded evidence | Remaining qualification |
|---|---|---|
| macOS ARM64 | [SDK0.280.1,43 phases per installation](docs/releases/0.280.1.json); [same-compiler Metal15 pairs/32 kernels](docs/evidence/sdk-current-0.280.1-2026-11-17.json) | signing/notarization, extended interactive web/mobile matrices |
| Astra Linux1.7 x86-64 | [0.280.1 build, core17/17, native app](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended/browser groups, portable SDK |
| Fedora45 x86-64 | [0.280.1 Clang23 build, core17/17, native app](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended/browser groups, portable SDK |
| Windows11 x86-64 | [0.280.1 core17 unique groups, native app, CUDA35/35](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended/browser groups, portable SDK; IPv6 intentionally restricted |
| CIX ARM64 | [0.280.1 core17/17,12 Mali GPU/8 Zhouyi NPU](docs/evidence/stands-current-0.280.1-2026-11-17.json) | extended regression, portable SDK |
| RK3588 ARM64 | [0.280.1 Ubuntu24 ARM64-container core17/17,49 GPU/30 NPU](docs/evidence/stands-current-0.280.1-2026-11-17.json) | native Jammy qualification, portable SDK |
| iOS Simulator | [Debug/Release, launch and actual UI input](docs/evidence/mobile-ios-release-0.244.0-2026-11-13.json) | device signing/store delivery |
| Android emulator | [signed release APK, launch and add interaction](docs/evidence/mobile-android-release-signed-0.244.0-2026-11-13.json) | Play Store delivery |
| macOS desktop app | [standalone embedded app, live input](docs/evidence/desktop-macos-interaction-0.244.0-2026-11-13.json) | Developer ID/notarization |

HTTP reference-task debugging/profiling, parallel reference transfer, general
GPU/NPU compilation, Apple NPU, native desktop UI, Studio, converters and other
[migration prerequisites](docs/migration-readiness.md) remain open. The
[implementation sequence](docs/implementation-1-6.md) and [original PLAN](PLAN.md)
retain these requirements. CUDA/OpenCL emission covers its advertised subsets.

[STATUS.md](STATUS.md), [CI scope](docs/ci.md) and [versioned evidence](docs/evidence/)
retain exact source/compiler/archive identities, original failures and each
result's scope. The SDK uses ad-hoc signatures and requires macOS27 ARM64,
Apple SDK, Python and Node/npm for web builds.

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
