# NEX — Neural Execution Language

[Русский](README.ru.md) · [Language overview](docs/overview.en.md) · [Get started](docs/getting-started.en.md) · [For LLMs](llm/LEARNING.md)

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
One historical checked-integer benchmark was close to its checked C++ baseline;
it does not establish universal C++ parity. End-to-end token savings across LLMs
have not yet been measured.

## What you can build

The implemented core includes modules, generics and traits, immutable aggregates,
Unicode strings and bytes, checked arithmetic, typed source errors and `finally`,
structured tasks, graph history, project components, native libraries, HTTP/API
and browser adapters, debugging, profiling and bounded scalar verification.

A project can share portable logic between a native server and a TypeScript /
React / Vite client. Device execution uses explicit trusted providers. Read the
[overview](docs/overview.en.md) for the distinction between source features and
platform acceptance.

## Development status

Current source: **toolchain 0.162.1 / language 0.28 / task ABI 7**, in development.
The [ELF runtime search correction](docs/native-runtime-search.md) passed a
301-group macOS source run and Linux native/package checks. Linux covers all
303 groups across a retained failed run and its verified notice-argument recovery.
The [development record](docs/evidence/native-runtime-search-0.162.1-2026-11-08.json)
also records the fresh Windows build and 12 moved/restored C11/C++20 history
pairs. Complete matching SDK delivery remains pending.
The qualified 0.162.0 SDK below retains its exact source and archive identity.
The [macOS ARM64 SDK record](docs/releases/0.162.0.json) pins the exact immutable
archive and its qualified resource snapshot. The matching source passed all
300 CTest groups. Moved and archive-restored SDKs each passed 41 maintained
phases and 90 additional cases using actual Python 3.10/3.14, denied source and
dependency reads, read-only SDKs, and 4000 total C++ host calls with cleanup checks.

That archive also passed 150 production-browser checks, 18 CLI composition
scenarios, 21 native/reference OpenCL scenarios with 47 physical kernel events,
and all Q1–Q5 workflows. A 100-module/10,000-declaration project made 9900, 0 and
1 actual LLVM calls for its cold, unchanged and single-function-edited builds.
All 85 shipped format schemas were checked against actual artifacts and rejected
mutations. The record describes sanitizer scope and the limits of its numerical
measurement; it does not establish universal binary safety or measured LLM savings.
The [current primary-source follow-up](docs/evidence/macos-current-primary-source-2026-11-06.json)
records all 300 groups across the original invocation and verified recovery;
its original failed run remains recorded.

Windows has a [fresh complete source build and ordinary-install smoke check](docs/evidence/windows-source-0.162.0-2026-11-06.json).
The [current Windows native/CUDA record](docs/evidence/windows-current-CUDA-2026-11-06.json)
covers 13 selected groups, 35 actual GPU cases and 36 Compute Sanitizer cases
on that fresh compiler. Complete portable SDK delivery remains separate.
The [native-file fixture correction](docs/evidence/windows-native-file-fixture-2026-11-06.json)
preserves actual AF_UNIX rejection tests on long Unicode paths. A separate exact
union of pinned current-engine invocations covers 298 of 302 groups; four positive
IPv6 groups remain unverified under the operator's intentional IPv6 restriction.
This union does not accept a complete latest Windows SDK.

The [Linux ARM64 source receipt](docs/evidence/linux-current-source-2026-11-05.json)
passed all 300 groups. Current scoped [CIX](docs/evidence/cix-current028-device-development-2026-11-05.json)
and [RK3588](docs/evidence/rk-current028-device-development-2026-11-05.json) receipts
record physical GPU/NPU calls without CPU fallback. Each keeps its source and
archive identity. The [Fedora45 full attempt](docs/evidence/fedora-current-full-2026-11-06.json)
passed 289/300 groups and remains failed. Separate [follow-up checks](docs/evidence/fedora-current-followups-2026-11-06.json)
passed its three environment/timeout groups and three debugger groups, plus six
ELF identity controls. A [coherent OpenSSL 3 follow-up](docs/evidence/fedora-current-OpenSSL3-2026-11-06.json)
built all current targets; DNS/TCP delivery completed before a disk interruption,
and all three HTTP groups then passed with that same compiler and dependency
cohort. CMake requires OpenSSL 3.x and refused system 4.0.3. A complete current
Fedora regression and portable SDK delivery remain pending.

The qualified 0.162 archive is recorded here; this source commit does not upload
a new binary release. The published [0.159 archive](docs/releases/0.159.0.json)
retains its own evidence. Use the [current source-build guide](docs/getting-started.en.md).

This is a development preview for macOS ARM64, minimum macOS 27.0. Matching
Windows/Linux SDK delivery, general GPU/NPU code generation, Metal compute,
Apple NPU, complete mobile/native UI, NEX Studio, project conversion and real
cross-model token/cost measurement remain [planned work](PLAN.md).

## Build and use

Start with the [current installation guide](docs/getting-started.en.md). A source
build requires C++20, CMake 3.25+, LLVM/MLIR 22.1.x, SQLite, OpenSSL 3, Z3 and
Python 3.10+. The full CTest suite includes Web/TypeScript workflows and also
requires Node.js 22.18+, npm and the repository's locked web dependencies.
On Unix, the ELF fixture tests also require LLVM22.1 `ld.lld` and `llvm-ar`;
use `-DNEX_ELF_TEST_LD=/absolute/path/to/ld.lld` when LLD has a separate prefix.

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

[Specification](docs/language.md) · [Grammar](docs/grammar.ebnf) ·
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
