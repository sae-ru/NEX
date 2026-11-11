# One command for a committed SDK build

[`tools/sdk_build.py`](../tools/sdk_build.py) joins the maintained source and
distribution workflows. It fixes one Git commit, exports tracked source into a
new owned directory, builds/tests/installs it, then delegates relocation,
source-free acceptance, normalized archive creation and restored acceptance to
the existing platform helper. It never overwrites an SDK or previous attempt.

This is a source development tool. Current local qualification covers its
snapshot/configuration/failure controls, not a complete new SDK execution.
The [scoped evidence](evidence/sdk-build-driver-0.165.0-2026-11-11.json) records
five control methods, actual macOS/Linux plans and an exact2302-file source
export. It also records the three actual kernel read-denial controls.
The final matching platform/device/SDK milestone remains pending. The command
does not publish a release or call an LLM; `release_qualification` stays false
because one host archive does not qualify every requested platform/device.

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

The complete Linux source/installed helper is followed by the existing
[`tools/linux/bundle.py`](../tools/linux/bundle.py), which retains the exact
source-free/archive acceptance workflow. The original inspected compiler image
ID is passed to the packager. A fresh local Docker tag binds that ID for
Dockerfile `FROM`; derived images execute by inspected ID. The temporary base
tag is recorded; no original image is deleted. This does not add image layers.
`skip_image_build: true` plus optional `image` selects an already prepared source
toolchain. Packaging/runtime image preparation still occurs when necessary.
Whole Docker/hosted execution of this new joining command remains unqualified.

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
Python/Node/npm must remain outside denied source/build/dependency roots. The
source and build copies receive explicit readable control files; the existing
kernel read/write denial checks remain active. Host Apple SDK/system tools are
declared prerequisites. Complete source-test and newly assembled archive
execution through this joining command remain pending.

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
Windows-native source/portable distribution orchestration remains pending;
Windows is explicitly rejected by this configuration schema rather than counted
as a successful Linux or macOS delivery.
