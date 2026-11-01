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

Current source: **toolchain 0.156.0 / language 0.27**.
Generic runtime contracts are under development and require matching acceptance.
The previous0.155 source passed [287 Mac CTest groups](docs/evidence/runtime-value-contracts-0.155.0.json)
and two40-phase SDK workflows on Python3.14. Its corrected Python3.10+ packaging
is undergoing separate qualification. Earlier Windows receipts retain their own
source scope; they do not accept the current compiler.
The accepted 0.152.1 macOS ARM64 source build passed all 285 CTest groups. The development SDK
passed 40 maintained phases in each moved/restored installation. An additional 126 production UI/Worker
tests passed across Chromium, Firefox and WebKit. This is a development preview.
Read the [logical debugger evidence](docs/evidence/lldb-resume-0.152.1.json) and
[runtime contract guide](docs/runtime-contracts.md) for their exact scopes.
The selected compiler's `nex describe` is the capability authority. Accepted SDKs,
source commits and hardware scopes are recorded in the [delivery record](docs/releases/0.152.1.json).

Apple M5 Max OpenCL U8 Add/Affine has a [scoped physical-device receipt](docs/evidence/macos-opencl-0.151.1.json).
Linux CIX/RK accelerator tests retain their [0.151.0 scope](docs/evidence/accelerators-0.151.0.json).
The [local Windows compiler](docs/windows-host.md) builds and runs x64 `.exe`
applications directly on Windows, including CPU/tasks/files and SQLite.
The earlier [target-only receipt](docs/windows-native-acceptance.md) preserves
its separate WSL producer, Windows execution and CUDA driver prerequisite results.
The [SDL Tic-Tac-Toe example](examples/tic-tac-toe/README.md) has shared NEX/SDL
sources and native build scripts for Windows, macOS and Linux. Its Windows
GPU and relocated standalone package checks passed on its pinned earlier source.
The [Retina readback correction](docs/evidence/sdl-metal-retina-0.155.0.json) passed
scoped macOS ARM64 Metal and relocated-package checks. Current Windows rechecking
and Linux graphical execution remain pending.
The native Windows compiler passed all 274 CTest groups.
NEX CUDA U8 Add/Affine passed 35 physical-device cases on RTX 3090;
[the current Windows record](docs/evidence/windows-native-2026-11-01.json)
keeps that scope separate from full regression and SDK acceptance.
Full Windows-hosted SDK acceptance, Metal compute, Apple NPU, general GPU compilation,
complete mobile/UI delivery and other [PLAN](PLAN.md) work remain open.

## Build and use

Start with the [current installation guide](docs/getting-started.en.md). A source
build requires C++20, CMake 3.25+, LLVM/MLIR 22.1.x, SQLite, OpenSSL 3, Z3 and
Python 3.10+. Web/TypeScript workflows additionally use Node.js 22.18+ and npm with
the repository's lock file.

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
ctest --test-dir build --output-on-failure
cmake --install build --prefix /absolute/path/to/nex-sdk
```

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
