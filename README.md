# NEX — Neural Execution Language

[Русский](README.ru.md) · [Language overview](docs/overview.en.md) · [Get started](docs/getting-started.en.md) · [For LLMs](llm/LEARNING.md) · [Codex skill/plugin](https://github.com/sae-ru/NEX/blob/main/plugins/nex/README.md) · [Current status](docs/STATUS.current.md)

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
usage; no NEX token saving is established. A separate [Codex before/after maintenance pilot](docs/codex-maintenance-2026-11-22.ru.md) accepted all three NEX changes in each arm. Reported tokens fell from 529,630 to 353,520. The pilot compares two NEX workflows on the same model. A [second Codex experiment](docs/codex-multimodule-2026-11-22.ru.md) measures context and assertion diagnostics separately on a failing multi-module billing project.

A [cross-language Codex benchmark](docs/codex-billing-languages-2026-11-23.ru.md) measures time and tokens per accepted repair of the same invoice in NEX, C++ and Python, including cached input.

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

**SDK 1.0.0** creates projects in language **0.30**. Download the archive for
macOS ARM64, Windows x64, Linux x86-64 or Linux ARM64. The compiler reports
**toolchain 1.0.0 / language 0.28 / task ABIs 7/8**. Here 0.28 is the fallback
for projects without a language selection. Projects can select 0.28, 0.29 or
0.30 in `nex.json`. Changing the language of a stored graph requires an explicit
migration. [Download the SDK](https://github.com/sae-ru/NEX/releases/tag/v1.0.0) · [Installation guide](docs/getting-started.en.md)

The 1.x compatibility contract covers documented 0.30 source behavior, public
standard-library declarations, specified CLI fields and project history. On each
supported host, SDK 1.0.0 was tested with projects from the published 0.281.0
beta. The comparison records the archive hashes and results for each host.
[Compatibility contract](docs/compatibility.md#compatibility-target-for-10) · [Results by host](https://github.com/sae-ru/NEX/releases/download/v1.0.0/compatibility.json)

Language 0.30 supports typed cells, [structured reference tasks](docs/reference-tasks.md),
[persistent UI](docs/persistent-ui.md), native libraries and
[persistent C++ host sessions](docs/native-task-sessions.md).
[Native debugging](docs/reference-provider-debugging.md) and
[profiling](docs/reference-task-profiling.md) cover source-backed provider images.
Standalone HTTP owner-thread tasks support [LLDB/DAP](docs/server-debugging.md#owner-thread-http-tasks-in-030)
and pinned-workload profiling. The [compatibility guide](docs/compatibility.md)
defines the source and project contracts for SDK 1.x.
[Workboard](examples/workboard/README.md) joins a browser UI, HTTP/tasks, SQLite,
file export/restore and a summary Worker; it is a required SDK consumption phase.
Ordinary libraries include [hash containers](docs/hash-containers.md),
[ordered maps](docs/ordered-containers.md) and [queues/heaps](docs/sequence-containers.md).
[Java int](docs/java-integers.md)/[long](docs/java-long.md) have explicit domains;
the [IEEE kernel](docs/ieee-numeric.md) still has no source types.

Run `nex guide --kind prompt` to read the coding instructions shipped with
SDK 1.0.0 (1,833 UTF-8 bytes). The Qwen study used an earlier version of the
instructions. Its report includes all 60 outcomes and identifies missing usage
data. [Coding instructions](llm/SYSTEM_PROMPT.md) · [Qwen study](docs/llm-cost-qwen38-27b-2026-11-17.en.md)
[Reference-context preparation](docs/llm-entry-v3.md) supplies public
source-task/byte guides and normative reviewer context. A subsequent
[three-slot pilot](docs/evidence/llm-response-envelope-v4-0.280.1-2026-11-17.json)
checked response framing and completed all three attempts.

| Platform | Recorded checks | Scope |
|---|---|---|
| macOS ARM64 | Relocated and archive-restored SDK, Metal kernels | Apple Silicon |
| Windows x64 | Relocated and archive-restored SDK, CUDA kernels | Device and driver requirements apply to CUDA |
| Linux x86-64 | Relocated and archive-restored SDK, native build of an application on Fedora | Native builds require compatible host libraries |
| Linux ARM64 | Relocated and archive-restored SDK, GPU and NPU on CIX P1 and RK3588 | Devices, operations and userspace versions are listed in the [release record](https://github.com/sae-ru/NEX/releases/download/v1.0.0/qualification.json) |
| iOS Simulator | [Debug/Release, launch and actual UI input](docs/evidence/mobile-ios-release-0.244.0-2026-11-13.json) | device signing/store delivery |
| Android emulator | [signed release APK, launch and add interaction](docs/evidence/mobile-android-release-signed-0.244.0-2026-11-13.json) | Play Store delivery |
| macOS desktop app | [standalone embedded app, live input](docs/evidence/desktop-macos-interaction-0.244.0-2026-11-13.json) | Developer ID/notarization |

HTTP task-provider debugging/profiling, parallel reference transfer, general
GPU/NPU compilation, Apple NPU, native desktop UI, Studio, converters and other
[migration prerequisites](docs/migration-readiness.md) remain open. The
[implementation sequence](docs/implementation-1-6.md) and [original PLAN](PLAN.md)
retain these requirements. CUDA/OpenCL emission covers its advertised subsets.

[STATUS.md](STATUS.md), [CI scope](docs/ci.md) and [versioned evidence](docs/evidence/)
retain exact source/compiler/archive identities, original failures and each
result's scope. The macOS ARM64 SDK uses ad-hoc signatures and requires macOS 27, an Apple SDK and Python. Web builds also require Node.js and npm.

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
To reproduce a package build, follow the [SDK build guide](docs/sdk-build.md).
The published release includes the acceptance results for each portable archive.
[SDK 1.0.0 qualification results](https://github.com/sae-ru/NEX/releases/download/v1.0.0/qualification.json)

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
