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

Source development 0.160 adds [native library entry ABI discovery](docs/native-entry-abi.md)
for matching C++ hosts; the published SDK and accepted delivery below remain 0.159.
That exact SDK also has scoped [native iOS Simulator execution](docs/evidence/0.159.0-ios-native/README.md):
1400 calls and cleanup checks across Debug/Release. Complete mobile delivery remains open.

Current development SDK: **toolchain 0.159.0 / language 0.28 / task ABI 7**.
The ordinary CLI accepts [source contracts](docs/source-contracts.md): pure
`requires` / `ensures` clauses and loop `invariant` / `decreases` checks, including
generic functions. Checks remain active in release builds. Existing 0.27 graph
histories need an [explicit migration](docs/source-contract-migration.md).

The [macOS ARM64 delivery record](docs/releases/0.159.0.json) pins the exact
accepted source, compiler and immutable archive. It records **296 CTest groups**,
**41 maintained SDK phases plus 57 additional cases per installation**, using
actual Python 3.10.22 and 3.14.9 on moved and archive-restored installations.
Original source/dependency roots and the opposite SDK were denied; both SDK
prefixes remained read-only. Internal platform-only skips retain their own scope.

The same archive passed [150 production-browser checks](docs/evidence/sdk-browsers-0.159.0.json)
in Chromium, Firefox and WebKit, and [18 CLI composition scenarios](docs/evidence/sdk-composition-0.159.0.json)
with 28 native debug/release executions and two explicit bounded scalar/loop proofs.
On Apple M5 Max, [OpenCL U8 Add/Affine](docs/evidence/macos-opencl-0.159.0.json)
passed 21 native/reference scenarios and six native source profiles, with 47
physical kernel events. These include source and detached contracts, generic
roots, pending cancellation/deadline and balanced visible managed pools.

This is a development preview for macOS ARM64, minimum macOS 27.0.
[Install it](docs/getting-started.en.md). Windows and Linux have source-build
recipes and earlier platform receipts; this release needs fresh acceptance there.
The Windows 0.152.1 receipt records 274 CTest groups, 35 RTX 3090 CUDA cases and
its own SDK checks. Linux CIX/RK accelerator evidence retains its
[0.151.0 scope](docs/evidence/accelerators-0.151.0.json).

The [SDL Tic-Tac-Toe example](examples/tic-tac-toe/README.md) shares NEX rules and
SDL integration across native build scripts. Its earlier Windows GPU/package
and [Mac Metal/Retina](docs/evidence/sdl-metal-retina-0.155.0.json) checks retain
their source identities. Current Windows/Linux execution, general GPU code
generation, Metal compute, Apple NPU, complete mobile/UI delivery, NEX Studio,
project conversion and other [PLAN](PLAN.md) work remain open.

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
