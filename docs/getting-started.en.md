# Start with NEX 0.152.1

[Русский](getting-started.ru.md) · [Overview](overview.en.md)

Toolchain versions and source-language versions are different. This source tree
uses toolchain 0.152.1 / language 0.27. Check [delivery evidence](releases/0.152.0.json)
for the exact accepted SDK, source commit, platform, archive hash and prerequisites.

## Install a matching SDK or build the compiler

For this snapshot, use the source build below. A public binary download has not
yet been published; the delivery record identifies the verified macOS archive.

An SDK contains `bin/nex` and `share/nex`; keep both together. Use an artifact
for your actual OS/architecture and verify its published SHA256 before extracting
it. The macOS ARM64 SDK is not a Windows executable. A CMake install is a local
prefix; portable bundles have their own dependency-capture and relocation tests.

For a source build, install C++20, CMake 3.25+, LLVM **and MLIR 22.1.x**, SQLite 3.37+,
OpenSSL 3, Z3 development files and Python 3.9+. Web/TypeScript also needs Node 22.18+
and npm. Use the locked `web/package-lock.json` dependencies. Native code needs
the target platform's compiler/SDK; LLDB workflows need compatible debugger tools.

```sh
git clone --branch main https://github.com/sae-ru/NEX.git
cd NEX
git rev-parse HEAD
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
ctest --test-dir build --output-on-failure
cmake --install build --prefix /absolute/path/to/nex-sdk
```

Set `LLVM_DIR`, `MLIR_DIR`, `OPENSSL_ROOT_DIR` and `NEX_Z3_ROOT` to your selected
installations when CMake cannot discover them. See [SDK delivery](sdk.md) and
[Linux](linux.md) for the maintained recipes. Native Windows hosting is an open
port/validation task; follow the [Windows handoff](windows-handoff.md).

Add the chosen SDK's `bin` directory to PATH, then verify selection:

```sh
nex doctor --json
nex describe --kind index --json
```

Confirm toolchain, language, runtime and tool paths. For a GUI coding agent,
run these commands in that agent's terminal too.

## Create an application

```sh
nex init /path/to/my-app
cd /path/to/my-app
nex check --json
nex run --json
nex test --json
nex build --profile release --json
```

Edit `.nex` source and repeat check/test. Native output can run without NEX or an
LLM when its actual runtime/system dependencies are available. The build JSON
names the artifact. Examples in [examples/learn](../examples/learn) demonstrate
values, typed errors and CPU mapping.

`nex.json` selects source language, entry and libraries. `nex.build.json` adds
component architecture; `nex lock` pins dependencies. Older graph histories need
an explicit migration. Editing a version number is not a migration.

## Keep a project in Git

Track source, manifests, lock files, tests, reviewed task/contracts, required
assets and intentional build configuration. Exclude credentials, local grants,
keys, caches, binaries and `node_modules`.

Source Git history does not by itself retain the semantic store's complete
revision/ID history. Preserve graph history with the maintained snapshot/export
workflow, separately from generated caches:

```sh
nex snapshot --directory ../my-app-snapshot --json
```

When redistributing NEX runtime code, retain its [MIT notice](../LICENSE) and
applicable third-party notices. Your application source can have its own license.

Read [snapshots](snapshots.md), [history](history.md) and [migration](typed-error-migration.md)
before moving an existing store or upgrading language versions.

## Use an LLM

Give it [BOOTSTRAP](../llm/BOOTSTRAP.md) and the [coding contract](../llm/SYSTEM_PROMPT.md).
Ask it to discover actual capabilities, retrieve bounded symbol context and
validate behavior. [LEARNING](../llm/LEARNING.md) provides the compact entry point.
The compiler and tests decide acceptance; a plausible generated answer does not.
