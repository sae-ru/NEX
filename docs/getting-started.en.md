# Start with NEX

The development SDK below uses toolchain 0.159.0 / language 0.28 / task ABI 7.
It includes source-level runtime contracts. Existing older graphs require
explicit history-preserving migration before current-language execution.

[Русский](getting-started.ru.md) · [Overview](overview.en.md)

Toolchain versions and source-language versions are different. This source tree
uses toolchain 0.159.0 / language 0.28. Check [delivery evidence](releases/0.159.0.json)
for the exact accepted SDK, source commit, platform, archive hash and prerequisites.

## Install a matching SDK or build the compiler

For macOS ARM64 on macOS27.0+, download the [0.159.0 development SDK](https://github.com/sae-ru/NEX/releases/tag/v0.159.0).
It requires Apple command line tools/SDK and Python3.10+. Web builds use Node/npm;
live debugging uses host LLDB. Verify the archive before adding it to PATH:

```sh
curl -fL 'https://github.com/sae-ru/NEX/releases/download/v0.159.0/nex-sdk-0.159.0-macos-arm64-development.tar.gz' -o 'nex-sdk-0.159.0-macos-arm64-development.tar.gz'
curl -fL 'https://github.com/sae-ru/NEX/releases/download/v0.159.0/nex-sdk-0.159.0-macos-arm64-development.tar.gz.sha256' -o 'nex-sdk-0.159.0-macos-arm64-development.tar.gz.sha256'
shasum -a 256 -c 'nex-sdk-0.159.0-macos-arm64-development.tar.gz.sha256'
tar -xzf 'nex-sdk-0.159.0-macos-arm64-development.tar.gz'
export PATH="$PWD/nex-sdk-0.159.0-macos-arm64-development/bin:$PATH"
nex doctor --json
nex describe --kind index --json
```

Published SHA256: `fe8dde075971f422b2311c27e131ca00b4c3cac24094cc6bd6857eab8b537374`.

For Windows/Linux or a different target, use the source build below and the
matching platform guide. Exact accepted platforms and source/archive hashes
are recorded in the linked delivery record.

An SDK contains `bin/nex` and `share/nex`; keep both together. Use an artifact
for your actual OS/architecture and verify its published SHA256 before extracting
it. The macOS ARM64 SDK is not a Windows executable. A CMake install is a local
prefix; portable bundles have their own dependency-capture and relocation tests.

For a source build, install C++20, CMake 3.25+, LLVM **and MLIR 22.1.x**, SQLite 3.37+,
OpenSSL 3, Z3 development files and Python 3.10+. Web/TypeScript also needs Node 22.18+
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
[Linux](linux.md) for the maintained recipes. Native Windows x64 hosting has separate [0.152.1 acceptance](windows-handoff-current.md);
this 0.159 source requires fresh Windows acceptance. Use the Windows host
recipe and keep host and target C++ ABI/CRT dependencies separate.

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
