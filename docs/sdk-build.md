# One command for a committed SDK build

[`tools/sdk_build.py`](../tools/sdk_build.py) joins the maintained source and
distribution workflows. It fixes one Git commit, exports tracked source into a
new owned directory, builds/tests/installs it, then delegates relocation,
source-free acceptance, normalized archive creation and restored acceptance to
the existing platform helper. It never overwrites an SDK or previous attempt.

For SDK 1.0.0, select the host before starting the build. The Linux
instructions below cover x86-64 and ARM64. macOS uses a native ARM64 build.
On Windows x64, apply the two files supplied with the release before running
the native build and distribution commands. Each host has its own compiler,
archive checksum and acceptance results. The release record identifies the
source and packaging inputs used for each archive. [SDK 1.0.0 qualification](https://github.com/sae-ru/NEX/releases/download/v1.0.0/qualification.json)

## Earlier build results

The [published0.280.1 macOS delivery](evidence/sdk-current-0.280.1-2026-11-17.json)
uses a fresh committed source export and all-target Release build. Its attached
orchestrator runs source and distribution gates concurrently after installation,
in separate directories. Both moved/restored SDKs passed43 phases with live
debugging and browser builds. Source coverage explicitly combines387 full-run
groups and the corrected16-case snapshot group on the same compiler/resources;
the original documentation-assertion failure is retained. This is not a passing
unmodified `sdk_build.py` invocation. The archive and14 public assets were
verified after anonymous download; Linux/Windows delivery keeps its own scope.

The earlier [0.246.1 macOS execution](evidence/sdk-current-0.246.1-2026-11-15.json)
completed this command from committed source `3b008a4e`: 2655 tracked source
files, a fresh all-target Release build, all 351 configured source test groups,
installation and 41 phases each after relocation and archive restoration.
The [published archive](releases/0.246.1.json) retains its exact identity.

Earlier [control evidence](evidence/sdk-build-driver-0.165.0-2026-11-11.json)
retains snapshot/configuration/failure methods, platform plans and read-denial
controls. In 0.165, the build driver recorded results for one host. The
release qualification assembles results from all supported hosts and devices.

## Language 0.30 installed checks

The current SDK runs 43 installed phases. The final two exercise language
0.30 reference programs and the multi-module Workboard application.
[Reference workflow](sdk-reference030.md) · [Workboard workflow](sdk-workboard.md)

Version 0.279 ran 42 phases. Its relocated installation exercised live DAP,
three provider modes, persistent native hosts and the browser build.
[Installed workflow results](evidence/sdk-reference030-preparation-0.279.0-2026-11-17.json)

Of 386 groups in the first 0.279 source run, 381 passed and five failed.
The 0.280 registry contained 388 groups. The release qualification gives the
source group count and installed results for each 1.0.0 host.
[0.279 source test results](evidence/full-source-0.279.0-first-attempt-2026-11-17.json)

## Linux

Install Git, Python3.10+ and Docker. Commit source changes first. On a Unix host
with a working Linux Docker daemon:

```sh
python3 -B tools/sdk_build.py plan --config tools/sdk-build/linux-amd64.json \
  --output build/sdk-amd64-attempt-1
python3 -B tools/sdk_build.py run --config tools/sdk-build/linux-amd64.json \
  --output build/sdk-amd64-attempt-1
```

`plan` is read-only and does not contact Docker or a registry. It checks the
checkout, committed metadata, configuration and CLI availability. `run` is the
single full build command. For ARM64 select
[`linux-arm64.json`](../tools/sdk-build/linux-arm64.json). Native Docker execution
and emulated execution are different scopes; the environment report records it.
The [pinned environment](../tools/linux/Dockerfile) prepares LLVM/MLIR22.1.8,
Z3/Node and the locked npm cache. Image preparation uses network access. Source
tests, installed checks and moved/restored checks run in offline containers.

For a manual full GitHub Actions run, enable `retain_sdk_input` to keep the
ordinary installation that passed source-free acceptance. Download the
`linux-amd64-installed-…` artifact within seven days. Its `handoff.json` gives
the checkout, toolchain image ID, archive SHA256, installed compiler SHA256
and hashes of the three CI reports. Verify the archive checksum, extract it
and use the enclosed `sdk/` as the input to the portable packager. Packaging
still has to resolve dependencies and qualify the moved and restored copies.

The complete Linux source/installed helper is followed by the existing
[`tools/linux/bundle.py`](../tools/linux/bundle.py), which retains the exact
source-free/archive acceptance workflow. The original inspected compiler image
ID is passed to the packager. A fresh local Docker tag binds that ID for
Dockerfile `FROM`; derived images execute by inspected ID. The temporary base
tag is recorded; no original image is deleted. This does not add image layers.
`skip_image_build: true` plus optional `image` selects an already prepared source
toolchain. Packaging/runtime image preparation still occurs when necessary.
The release record identifies which steps ran on a hosted runner and which
ran in the packaging environment. Use its archive SHA-256 when comparing
those results with a local build.

## macOS

Copy [the native example](../tools/sdk-build/macos.example.json) to a local
configuration. Replace every placeholder with actual selected dependencies,
complete notice catalogue, populated locked npm cache and external Node/npm
paths. Install the [source prerequisites](../README.md#build-and-use). The
current helper builds Release in its new output directory; it uses no existing
compiler/build cache and does not replace an active development compiler.

```sh
python3 -B tools/sdk_build.py plan --config /absolute/my-sdk.json \
  --output /absolute/new-sdk-attempt
python3 -B tools/sdk_build.py run --config /absolute/my-sdk.json \
  --output /absolute/new-sdk-attempt
```

The sequence is configure, all-target build, locked offline web preparation,
full unfiltered CTest with checked JUnit/fixture closure, CMake install, then the
[maintained macOS distributor](sdk.md#maintained-macos-distribution-workflow).
It performs both moved/restored complete installed workflows. `live: true`
requires real working LLDB/DAP; omitting it does not qualify live debugging.
The distributor reads the assembled file inventory and automatically includes
copied host files from custom prefixes, such as a standalone `wasm-ld` or a
separately installed Z3 library, in both relocation checks.
Python/Node/npm must remain outside denied source/build/dependency roots. The
source and build copies receive explicit readable control files; the existing
kernel read/write denial checks remain active. Host Apple SDK/system tools are
declared prerequisites. The 0.246.1 macOS run completed this full sequence;
its source, configuration, notices, source-test and distribution hashes are
preserved in the linked receipts. `live` was false for that archive.

## Windows x86-64

### Building the Windows SDK from the 0.281.0 or 1.0.0 release tag

Start in a clean checkout of the release tag. Download `qualification.json`,
`nex-windows-sdk-distribution.py`, `nex-windows-native-task-sessions.py` and
`nex-windows-sdk-task-streams.py` from the same release into
`downloads/windows-release/`. The packaging script selects Node for npm,
the session test links against the packaged UCRT, and the stream test uses
portable source paths in its report. [Beta assets](https://github.com/sae-ru/NEX/releases/tag/v0.281.0) · [1.0 assets](https://github.com/sae-ru/NEX/releases/tag/v1.0.0)

Run the commands from the checkout root before building and installing with
CMake. They check each download against the release record, then copy the
three files to their recorded checkout paths.

```powershell
$ErrorActionPreference = 'Stop'
$assets = Get-Item -LiteralPath '.\downloads\windows-release'
$release = Get-Content -Raw -LiteralPath (Join-Path $assets.FullName 'qualification.json') | ConvertFrom-Json
if ((git rev-parse HEAD) -ne $release.qualification_main_commit) { throw 'Release tag and checkout differ' }
$inputs = @($release.windows_packaging_tool, $release.windows_host_session_fixture, $release.windows_stream_report_writer)
foreach ($item in $inputs) {
    $path = Join-Path $assets.FullName $item.file
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash -ne $item.sha256) { throw "SHA256 mismatch for $path" }
}
foreach ($item in $inputs) {
    Copy-Item -LiteralPath (Join-Path $assets.FullName $item.file) -Destination $item.checkout_path
}
```

### Building and packaging the installation

Build and install the selected commit with the native Windows compiler and its
pinned UCRT dependencies. From that checkout, run the native Windows
[distribution driver](../tools/windows/sdk_distribution.py) with the ordinary
CMake installation and the catalogue of packages supplying its actual files.
The OpenSSL prefix must include the CLI, libraries, provider modules and
configuration used with that installation. Select the Wasm linker from the
all-target Clang dependency set. During assembly the unbundled host compiler
loads its LLVM, SQLite and solver DLLs from the directory beside that linker.
If the host DLLs live elsewhere, pass `--host-runtime-bin DIRECTORY`. Moved
and restored acceptance use the assembled SDK and a Windows system PATH
augmented with a private directory containing the selected standalone
`node.exe`. This lets npm's TypeScript and Vite scripts find that executable
by name while keeping compiler and OpenSSL installations off the consumer PATH.

On Windows x86-64 the 0.281.0 beta input from `d492bf7f` reproduced a
`0xC0000135` loader exit during assembly. With the host DLL path supplied,
the same input produced a movable bundle. Its compiler passed `doctor` on
the system PATH and printed `42` in the interpreter and native Release build.
The [assembly receipt](evidence/windows-sdk-assembly-2026-11-23.json) pins the
executable and both packaging scripts. Full distribution acceptance also
exercises the archived and restored SDK.

Windows native HTTP and FFI builds capture the selected `openssl/` header
tree with the runtime inputs. The target compiler supplies its own platform C
headers even when the OpenSSL prefix also contains producer-system headers.

```powershell
python -B tools/windows/sdk_distribution.py `
  --sdk C:\path\installed --output C:\path\new-distribution `
  --notices C:\path\sdk-notices.json --openssl-prefix C:\path\clang64 `
  --wasm-linker C:\path\clang64\bin\wasm-ld.exe `
  --node C:\path\node.exe --npm C:\path\npm.cmd --npm-cache C:\path\npm-cache `
  --live --lldb C:\path\lldb.exe --lldb-dap C:\path\lldb-dap.exe
```

The driver assembles and inventories the native SDK, then runs the maintained
browser and installed workflows at the relocated and archive-restored paths.
Acceptance resolves native tools, Wasm tools, headers and libraries inside the
candidate. Python, Node/npm and the selected LLDB tools are external
prerequisites. Use `--forbid-source` to require absent source paths on the
qualification host. The default network profile requires IPv6. On a Windows
host that intentionally denies it, select `--network-profile windows-ipv6-denied`
so the receipt records that exact scope. The driver creates a report and an
archive checksum after the two installed checks pass.

## Local 0.177 macOS smoke

A local Release install/move/archive/restore smoke was run on macOS ARM64: the
installed `bin/nex` and `share/nex` initialized, checked, tested, evaluated and
natively ran a fresh app; the SDK was moved and restored from an 11 MB archive
with the runtime path following each location. The
[scoped evidence](evidence/sdk-local-smoke-0.177.0-2026-11-11.json) records the
Release binary/compiler identity and limits. It is not the full `sdk_build.py`
sequence, full CTest, source-free/denied-read acceptance, live debugging or a
portable platform matrix.

## Inputs, outputs and limits

`source` defaults to the checkout containing the command; `--source` can select
another clean NEX checkout. Staged/unstaged tracked changes are rejected.
Untracked files, ignored graphs/builds and Git credentials are not exported.
The driver selects a resolved commit rather than a branch that can move during
the build. Regular tracked files are required; symlinks/submodules need a
separately designed source export path. `expected_commit` can additionally pin
a reviewed config to one exact source SHA. Keep reviewed configs, source,
manifests and locks in Git; keep machine paths/local catalogues out when needed.
Git replacement refs and [implicit missing-object fetches](https://git-scm.com/docs/git)
are disabled during inspection/export. A partial clone must already contain
the selected objects.

The output retains the source tar, full snapshot file/hash/mode inventory,
selected config digest, command arrays, actual exit codes, exact binary
stdout/stderr and child report/archive hashes. A failed phase stops later work
and keeps earlier logs. An existing output is rejected; a retry is a distinct
attempt. There is no automatic resume, deletion, push or publication.
macOS notice parsing reuses the assembler's provenance loader. Complete local
UTF-8 license texts are required before the build; catalogue/license digests
are rechecked before a successful result is recorded.

Linux dependencies use the pinned container recipe; macOS uses explicit local
installations and their notices. This is not a claim of byte-identical compiler
builds across hosts or of a hermetic macOS dependency installation. Final
archive inventories and actual moved/restored observations retain their scope.
`sdk_build.py` orchestrates macOS and Linux from committed source. On Windows,
the native source build and the distribution driver are separate commands.
