# Start with NEX

Current source uses **toolchain 0.246.1 / language 0.28 / task ABI 7**, in development.
Readable source, runtime contracts and explicit history-preserving migrations
are available through the ordinary CLI.

[Русский](getting-started.ru.md) · [Overview](overview.en.md)

## Install the macOS ARM64 SDK

[SDK 0.246.1](releases/0.246.1.json) requires macOS 27.0+ on ARM64, Apple command-line
tools with a macOS SDK and Python 3.10+. Web builds also require Node.js 22.18+
and npm. This portable development archive includes its selected compiler and
library dependencies. Keep its entire directory together.

Download, verify and extract it:

```sh
curl -fL -o nex-sdk-0.246.1-macos-arm64-development.tar.gz \
  https://github.com/sae-ru/NEX/releases/download/v0.246.1/nex-sdk-0.246.1-macos-arm64-development.tar.gz
echo 'd583cb214f4831207253a14a84927386195cecd652ffd4744a8b3bd4f0aae2aa  nex-sdk-0.246.1-macos-arm64-development.tar.gz' | shasum -a 256 -c -
mkdir -p "$HOME/.local/nex"
tar -xzf nex-sdk-0.246.1-macos-arm64-development.tar.gz -C "$HOME/.local/nex"
export PATH="$HOME/.local/nex/nex-sdk-0.246.1-macos-arm64-development/bin:$PATH"
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
nex doctor --json
nex describe --kind index --json
```

The [release receipts](evidence/sdk-current-0.246.1-2026-11-15.json) identify the
exact source, archive and moved/restored acceptance. Signatures are ad-hoc;
Developer ID signing/notarization and the full live SDK debugger matrix remain
separate work. For Windows/Linux, use the source instructions below and the
matching platform guide.

## Build the current version

Install C++20, CMake 3.25+, LLVM **and MLIR 22.1.x or 23.1.x**, SQLite 3.37+, OpenSSL **3**,
Z3 development files and Python 3.10+. Web/TypeScript needs Node.js 22.18+ and npm.
Native execution needs the target platform's compiler/SDK; live debugging needs
compatible LLDB tools. Keep the repository's `web/package-lock.json`.

On Unix, the complete source suite also requires matching LLVM `ld.lld` and `llvm-ar`
for the [ELF library selection tests](native-runtime-search.md). If ELF LLD has a
separate prefix, add `-DNEX_ELF_TEST_LD=/absolute/path/to/ld.lld` to the CMake
configure command below. This option is independent of `NEX_WASM_LD`.

```sh
git clone --branch main https://github.com/sae-ru/NEX.git
cd NEX
git rev-parse HEAD
cmake -S . -B build -DCMAKE_BUILD_TYPE=Release
cmake --build build -j 4
npm --prefix web ci --cache "$PWD/build/npm-cache" --ignore-scripts --no-audit --no-fund
NEX_TSC="$PWD/web/node_modules/typescript/bin/tsc" \
NEX_NPM_CACHE="$PWD/build/npm-cache" \
ctest --test-dir build --output-on-failure
cmake --install build --prefix /absolute/path/to/nex-sdk
export PATH="/absolute/path/to/nex-sdk/bin:$PATH"
nex doctor --json
nex doctor --toolchain windows-toolchain.json --json
nex describe --kind index --json
```

The full source test suite includes TypeScript checks, even when your own
application has no browser client. `npm ci` installs the exact lock-file versions;
`NEX_TSC` and `NEX_NPM_CACHE` select that compiler and populated cache for tests.
Run the shell commands above from the repository root. For PowerShell, set these
variables before CTest:

```powershell
$env:NEX_TSC = (Resolve-Path web/node_modules/typescript/bin/tsc).Path
$env:NEX_NPM_CACHE = (Resolve-Path build/npm-cache).Path
ctest --test-dir build --output-on-failure
```

Set `LLVM_DIR`, `MLIR_DIR`, `OPENSSL_ROOT_DIR` and `NEX_Z3_ROOT` when CMake cannot
find the selected dependencies. Optional DNS/HTTP groups need the explicit
`NEX_CARES_PREFIX` / `NEX_HTTP_PREFIX`. Source package tests also need the actual
operator-selected `NEX_PACKAGE_NOTICES_FILE` where automatic ownership discovery
is unavailable. Test counts depend on configuration. See [SDK](sdk.md),
[Linux](linux.md) and [Windows](windows-handoff-current.md) for platform recipes.
Use a matching OpenSSL 3 or 4 installation; both ranges are accepted, with OpenSSL 4 qualified on Fedora 45.
SDK delivery is recorded per archive; see the [SDK guide](sdk.md) and
[current platform evidence](../README.md#development-status).

## Older SDK archives

Select a matching prebuilt archive from [GitHub Releases](https://github.com/sae-ru/NEX/releases)
and verify its published SHA256 before extracting it. Each release records its
source revision, supported host and acceptance scope.

The [qualified0.162 macOS ARM64 record](releases/0.162.0.json) identifies the exact
archive `nex-sdk-0.162.0-macos-arm64-development.tar.gz`, minimum macOS27.0:

```text
SHA256 c1393c94709d3e3290d39b1a60da7ad78e28705bfa6cea539e74ff7e40bc6208
```

This is a historical 0.162.0 archive. To use the current implementation, select
a matching published SDK or build the source revision above and verify its
actual `doctor` and `describe` output. Cloning `main` selects the published branch head; its version can differ
from an unpublished development checkout. The [0.159 release](https://github.com/sae-ru/NEX/releases/tag/v0.159.0)
also retains its separate historical scope.

Keep `bin/nex` and `share/nex` together. Select your actual OS/architecture;
macOS ARM64 binaries do not run on Windows. Ordinary CMake installation uses
local dependencies; portable bundles require separate closure/relocation checks.
The0.162 record qualifies actual Python3.10.22/3.14.9, source/dependency denial,
read-only moved/restored SDKs, browser builds and live debugging. Its resource
snapshot is pinned; use this current online guide for publication status.

Confirm toolchain, language, runtime and tool paths with `doctor` and `describe`.
For a GUI coding agent, run those commands in its terminal too.

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

Read [snapshots](snapshots.md), [history](history.md) and the
[current-language migration guide](source-contract-migration.md)
before moving an existing store or upgrading language versions.

## Use an LLM

Give it [BOOTSTRAP](../llm/BOOTSTRAP.md) and the [coding contract](../llm/SYSTEM_PROMPT.md).
Ask it to discover actual capabilities, retrieve bounded symbol context and
validate behavior. [LEARNING](../llm/LEARNING.md) provides the compact entry point.
The compiler and tests decide acceptance; a plausible generated answer does not.
