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
A [recorded 0.162.2 checked-integer benchmark](docs/evidence/macos-e63-sdk-complete-0.162.2-2026-11-09.json)
measured median wall times of 0.296170 s for NEX, 0.290189 s for checked C++ and
7.610111 s for Python on one Mac. These are one-workload observations.
End-to-end token savings across LLMs have not yet been measured.

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

Current source: **toolchain 0.165.0 / language 0.28 / task ABI 7**, in development.
Complete matching portable SDK qualification is still pending. Source support,
physical device checks and portable delivery have separate acceptance records.

| Platform | Recorded evidence | Remaining qualification |
|---|---|---|
| macOS ARM64 | [302 groups for `0abc5d7`, nine current delta groups and a moved/restored `53634a5` SDK candidate](docs/evidence/macos-installed-Metal-full302-SDK-candidate-0.165.0-2026-11-10.json); [ordinary installed Metal tools: 15 pairs, 24 physical kernels](docs/evidence/macos-installed-public-Metal-tools-0.165.0-2026-11-10.json) | Complete workflows and physical Metal acceptance for the new immutable SDK |
| Windows x86-64 / RTX 3090 | [Snapshot `2172b35`: all targets, 11 groups, 35 physical CUDA cases, 36 Compute Sanitizer cases](docs/evidence/windows-latest-build-CUDA-0.165.0-2026-11-10.json) | Complete source regression and portable SDK; positive IPv6 remains unverified under the operator's restriction |
| Fedora x86-64 | [304 source groups and ordinary installed smoke, snapshot `61fbd21`](docs/evidence/fedora-public-Metal-full304-0.165.0-2026-11-10.json) | Later changes and portable SDK |
| CIX ARM64 | [Snapshot `979ef54`: 36 GPU and 26 NPU calls, NPU CPU fallback disabled](docs/evidence/cix-current-source-GPU-NPU-0.165.0-2026-11-10.json) | Full matching source regression, later changes and portable SDK |
| RK3588, other architectures and mobile devices | Earlier records retain their own versions in [STATUS](STATUS.md) | Matching current platform and device acceptance |

The earlier [`61fbd21` macOS SDK baseline](docs/evidence/macos-baseline-SDK-82-184-0.165.0-2026-11-10.json)
passed 82 maintained phases, 184 additional cases and 4000 C++ host calls with
cleanup checks across read-only moved/restored installations. Its post stages
and the later SDK containing the new public Metal tools remain separate gates.

The [scalar Metal backend](docs/gpu-codegen.md) emits reachable shared pure
`i64`/`bool`/`unit` functions from the checked AST. Its explicit owned-task
provider is experimental; the SDK installs its preparation tools and advertises
`gpu_codegen.owned_provider`. GPU stepping/profiling, broader GPU/NPU compilation,
Apple NPU, complete mobile/native UI, NEX Studio, project conversion and measured
cross-model token/cost savings remain [planned work](PLAN.md).

[STATUS.md](STATUS.md) and [versioned evidence](docs/evidence/) retain the
history, exact source/compiler/archive identities, original failures and scope
of each result. An earlier SDK's acceptance does not qualify a new archive.

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
