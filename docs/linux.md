# Linux compiler and development chain

The [physical Astra x86-64 component record](evidence/astra-source-development-2026-11-05.json)
pins development0.162 source `f4db4dd`: all targets built on system glibc2.28 with
the existing private LLVM/MLIR22.1.8 toolchain. Native Debug/Release and reference
passed a typed-error/contract smoke; TypeScript passed one pure source test.
This is a finite source check. A separate
[full source gate](evidence/astra-full-source-development-failed-2026-11-05.json)
on `b7bf5e2` (including implementation26b4251) built the pinned network dependencies
and registered all298 groups, but CTest failed. Diagnostics include private GNU
runtime notice provenance, other test failures and exhausted temporary storage;
the final JUnit file was absent. Temporary artifacts were archived and the own
test directories removed after verification. Full regression and complete
current SDK delivery remain pending.

The [separate native-staging fixture repair](evidence/astra-native-staging-development-2026-11-05.json)
passed all five cases on that same Astra compiler/probe. The hand-linked test
runtime now explicitly compiles and links its owned resource executor with
`pthread`, matching the compiler's existing dependency. This exercises real
archive reuse, two shared libraries, Debug/Release, profiling and relocation on
glibc2.28. It does not reclassify the failed full source gate.

For private native dependencies, `nex package --notices OPERATOR_CATALOGUE
--directory OUTPUT` requires their actual provenance and full license texts.
A [scoped Astra package check](evidence/astra-gnu-package-development-2026-11-05.json)
declared the installed conda-forge GNU runtime16.2.0 components, copied their
libraries and notices, and ran a moved release application with its original
entry/graph paths absent and `LD_LIBRARY_PATH` unset. Both GNU libraries resolved
inside the moved package; omission of provenance still failed. Canonical path
validation retains the original assertion that incorrectly compared the textual
`bin/../lib` path. This minimal package result does not replace full SDK acceptance.

The maintained environment uses an independently pinned **LLDB23.1.5 APT
snapshot** for debugging, while **LLVM/MLIR/Clang/LLD remain22.1.8** for NEX
compilation. Only `lldb`, `lldb-dap` and `lldb-server` are added ahead of the
compiler directory in PATH. The exact package versions, repository key and
observed archive hashes are recorded in
[`tools/linux/debugger-packages.json`](../tools/linux/debugger-packages.json).
APT validates downloads against its signed index; other Ubuntu packages still
follow their repositories.

On the Fedora x86-64 stand, the private Conda Clang 22 installation initially
selected its cross sysroot when manually linking fixtures against native host
libraries. Its C++ entrypoint now explicitly uses `--no-default-config`,
`--target=x86_64-unknown-linux-gnu`, `--sysroot=/`, `--gcc-toolchain=/usr` and
`--ld-path=/usr/bin/ld`. The real Clang binary and original symlink are retained;
the wrapper has its own byte identity. With this [private native-driver
configuration](evidence/fedora-native-driver-config-2026-11-06.json), the original
CMake `source_exception_modules` group passed without rewriting its registry
or increasing its timeout. This preserves the private fixture cohort and leaves
full Fedora/current SDK acceptance open.

Live verification also builds the optional
[`Debugger.Dockerfile`](../tools/linux/Debugger.Dockerfile) overlay. Its local
[indexed paging patch](../tools/linux/lldb23-indexed-pages.json) makes LLDB DAP
fetch the requested indexed range directly. The unpatched23 adapter first
materializes every child; the Linux0.160 installed live test timed out fetching
two elements from a32768-element list. Its bytes root contains4194304 elements.
The existing page sizes and timeouts are retained. The overlay deploys a matching
LLDB library, Python bindings, CLI, DAP and server built from the pinned source;
replacing DAP alone against the APT library failed the unchanged pre-launch
breakpoint check. The compiler remains22.1.8. The preserved original test binary
passed with the complete debugger build. This dependency repair still needs
complete current source/live/SDK qualification.

LLDB22.1.8 repeated process-event handling when an additional listener consumed
events. Three strict Linux debugger groups exposed missed stops or an all-stop
refusal. Four preserved binaries passed the original scenarios with the fixed
LLDB23 build and the same NEX reader/runtime. This is focused replay evidence;
current full Linux and installed SDK qualification remain separate gates.
Manifest and relocation JSON are explicitly decoded as UTF-8, including under
a C locale. The image also selects a UTF-8 locale for its test tools.

The [debugger follow-up record](evidence/linux-debugger-0.160.0.json) records
three passing modular/public debugger groups and a passing separate watch run
(24 LLDB comparisons, two DAP comparisons). The first four-group run also had
one `lost connection` exit in the watch group. The exact binary then passed
three diagnostic replays, and the complete watch group passed unchanged.
The original intermittent failure remains recorded. Subsequent ARM64 core analysis found a `lldb-server` SIGSEGV when `ConfigureVectorLengthZA` indexed an empty optional SME register collection. The [pinned inventory patch](../tools/linux/lldb23-za-registers.json) leaves unadvertised registers untouched. A deterministic test fails with the original dependency and passes nine register configurations after the repair. Replay and complete current Linux/SDK qualification retain separate evidence; the earlier successful replays alone did not establish a fix.
These checks use the retained Linux0.159 compiler with the updated reader and
tests. They do not qualify a current0.160 Linux compiler or SDK.

Clang sanitizer builds require the matching `libclang-rt-22-dev` package, pinned
to the same LLVM22.1.8 APT version as the compiler. The maintained development
Dockerfile includes it. For an existing verified image, build the separate
`tools/linux/Sanitizers.Dockerfile` with `TOOLCHAIN_IMAGE` set to its verified
local tag, and record both immutable image IDs and the installed package version.
The TCP experiment uses actual loopback IPv4/IPv6 with external network disabled;
its normal, ASAN/UBSAN and TSAN scopes are separate from compiler/SDK acceptance.

The live shared-image/core-capsule test places its temporary project under
`/build/live-image-tmp`. On a host bind mount this exercises a filesystem distinct
from container `/tmp`, with literal percent signs and Unicode in the fixture
path. Toolchain0.134.5 keeps capsule publication staging beside its destination;
the test also verifies that a repeated export preserves the existing capsule.

Native application packaging uses `readelf`, `ldd` and patchelf 0.18.0; the
development recipe now installs the pinned patchelf package. Older retained
images need that packaging dependency before running the new `packaging` suite.
`tools/linux/check.py --image IMAGE --skip-image-build` can select an existing
prepared image, retaining its actual immutable image ID and architecture in
the report. The dedicated `nex-sdk-packager:arm64`/`:amd64` images supplement
the previously verified compiler images with patchelf without replacing them.
See [application packages](packaging.md) for the smaller runtime requirements.

The Linux environment builds NEX itself and native NEX programs with C++20,
LLVM/MLIR/LLD 22.1.8, SQLite, OpenSSL 3, Z3 5.3.1 and Node.js 22.22.3.
The debugger has its own LLDB23 package pin and does not select a new compiler.
`tools/linux/Dockerfile` pins the Ubuntu 24.04 base image digest, LLVM package
version, repository signing-key fingerprint, and Node/Z3 archive SHA-256 hashes.
Other Ubuntu packages still follow its package repositories; this is not a
fully immutable package mirror.

## Run the checks

From a source checkout with Python 3 and a working Docker engine:

```sh
python3 tools/linux/check.py --arch arm64
python3 tools/linux/check.py --arch amd64
```

The image build downloads dependencies and preloads the existing npm lock into a
cache using `npm ci --ignore-scripts`. Source code is mounted read-only. The
compiler build, CTest suites and installed SDK workflow run with `--network none`;
local loopback HTTP/TLS tests remain available. Native Linux tests cannot be
replaced by interpreter-only checks. The report lists any platform-specific
skips separately; macOS cross-SDK tests are unavailable in this Linux image.

Keep temporary test projects on the container's native Linux filesystem, normally
`/tmp`. A macOS host-shared `TMPDIR` can reject raw non-UTF-8 filenames before
NEX runs and can change SQLite locking or directory-iteration behavior. The
verifier now checks a raw filename round trip before configuring or building,
retains the selected directory in `verification.json`, and fails with a concrete
scratch-directory diagnostic. This preflight checks filename support; the full
history, packaging and compiler tests still establish their own behavior.

Results are written under `build/linux-ARCH/`: image/configure/build/ctest logs,
`verification.json`, `environment.json`, installed `sdk`, and `sdk-smoke.json`.
The environment report identifies the Docker server architecture and whether
the selected image runs through emulation. AMD64 execution under Docker's
emulation is distinct from validation on physical x86-64 hardware. Kernel,
runtime and dependency versions are retained with the evidence.

After those checks, a second container mounts only the installed SDK read-only
and a fresh evidence directory. It runs the maintained [SDK acceptance workflow](sdk.md)
with `/src` absent, external networking disabled and the real Vite build enabled.
The top-level report remains false while this phase runs. Its task failure/repair,
graph import, profile, archive/replay/export and optional live-debugger evidence
is retained under `sdk-acceptance/RUN/workflow/`, with `source-free-sdk.json`
and `source-free-sdk.log` copies in the rolling and versioned reports. Build-tree
and installed compiler hashes are recorded separately: CMake may change ELF
RPATHs during installation. The isolated run must match the installed hash.

Use `--output PATH` for a different writable build directory, `--jobs N` for
1–8 build/test workers, and `--skip-image-build` only when the matching local
image already exists. The default of two workers accommodates an 8 GiB Docker
VM. `--source PATH` selects a source checkout when invoking the script from an
installed resource pack. Build files and caches remain separate from the
read-only source. No image is published by these commands.

The 0.60.1 correction encodes bind-mount fields as Docker CSV for source,
build, installed-SDK and evidence paths. Quoting an entire shell argument does
not escape Docker's comma/quote parser. The same helper is used by the bundle
workflow and preserves read-only source/SDK mounts and writable evidence.
Current actual-path regression and full source/SDK checks are recorded separately
in STATUS.md; this correction introduces no source-language change.

The source checkout also contains an explicit real-container regression:

```sh
python3 tests/linux_mounts.py --image nex-sdk-packager:arm64 --output /new/mount-evidence
```

It pins the selected local image ID, exercises quote/comma/Unicode and newline
paths, compares exact binary payloads, requires kernel readonly rejection and
writable evidence, native scratch filename support, explicit rejection of a
read-only scratch directory, and the absent outbound route. The prior raw mount
strings must still fail. This focused regression does not replace compiler,
live-debugger or complete installed-SDK acceptance.



For actual LLDB/DAP checks on a Linux CPU with native ptrace support:

```sh
python3 tools/linux/check.py --arch arm64 --live
```

The first run builds both the base toolchain and the paged-debugger overlay.
To reuse an already built overlay, select its exact tag explicitly:

```sh
python3 tools/linux/check.py --arch arm64 --live --skip-image-build \
  --image nex-linux-toolchain:arm64-paged-debugger
```

The report records the actual immutable image ID. `--skip-image-build` uses
the selected image as supplied; it does not add the paging patch to an old image.

This grants `SYS_PTRACE` and disables the container's syscall filter for that
test run, retaining its isolated PID namespace, read-only sources and disabled
external network. These permissions support debugging the test children.
The live run includes the debugging, expression, generic, constraint and matching suites, exercising
both ordinary previews and exact/partial NEX watch captures through LLDB/DAP.
Foreign CPU emulation can lack native ptrace support; source/DWARF checks alone
do not establish live debugger support. See the debug/expression guides for
frame/watch limits and permission failures.

## Compiler, linking and artifacts

The underlying configure/build commands are ordinary CMake:

```sh
cmake -S /src -B /build -DCMAKE_BUILD_TYPE=Debug \
  -DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++ \
  -DLLVM_DIR=/usr/lib/llvm-22/lib/cmake/llvm \
  -DMLIR_DIR=/usr/lib/llvm-22/lib/cmake/mlir -DNEX_Z3_ROOT=/opt/z3
cmake --build /build -j 2
ctest --test-dir /build --output-on-failure
cmake --install /build --prefix /build/sdk
```

Linux native application links default to the matching LLVM `ld.lld`. A
`nex.toolchain/1` configuration can select an explicit `linker` path, preserving
the final driver name (`ld.lld` selects ELF dispatch). Linker identity enters
build/cache keys and the selected binary enters toolchain fingerprints. Build
metadata reports the linker. Static archives still use `llvm-ar`.

This choice addresses an observed ELF DWARF failure: identical generated/runtime
objects linked with Ubuntu's GNU ld failed LLVM 22's string-offset verification,
while the LLD output passed. NEX retains verified MLIR/LLVM IR and uses the
existing strict DWARF tests. Artifact copies stream bytes and preserve file
permissions rather than relying on filesystem-specific fast-copy syscalls,
which failed on Docker/macOS shared folders. LLVM ELF/archive output is staged
separately so literal percent signs in project paths are not treated as
temporary-name placeholders. Historical 0.5/0.6 migration tests restore stores
captured from the actual older SDKs when their native macOS binaries cannot
execute on Linux; the same history/ID assertions still run.

Fingerprint policy `nex.toolchain-snapshot/2` adds selected linker bytes. Review
new toolchain hashes when moving from 0.19's policy; saved receipts retain their
matching SDK and original inputs. The linker-policy change in 0.20 retained source language 0.7. Toolchain 0.21 adds language 0.8 constraints and requires explicit source migration.
Default macOS system-linker contents remain external unless explicitly selected.

## Installed SDK and scope

The installed workflow checks the matching language pack, native/TypeScript/
interpreter agreement, strict generic data, ELF DWARF, standalone execution,
profiles, pinned task acceptance and archived replay after source deletion.
It also exercises authenticated per-principal SQLite storage and server restart
persistence. Pure native output does not require NEX/LLVM/Z3 at runtime; servers
need the selected SQLite/OpenSSL runtime libraries. The development compiler
still needs its matching LLVM/MLIR/Z3 installation.

The image is a development environment, not a portable SDK tarball or a signed
application distribution. Linux desktop UI/GPU, broader distributions/kernel
matrices, Windows, mobile packages and complete external SDK capture remain
separate work. Check `STATUS.md` and actual saved reports for verified results.

Upstream inputs: [LLVM packages](https://apt.llvm.org/),
[Node 22.22.3](https://nodejs.org/en/download/archive/v22.22.3),
[Z3 5.3.1](https://github.com/Z3Prover/z3/releases/tag/z3-5.3.1).

## Relocatable SDK bundle

Toolchain 0.28 adds ELF SDK assembly through `python3 tools/linux/bundle.py
--sdk PREFIX --arch arm64 --output NEW_DIRECTORY` (or `--arch amd64`). The separate
packaging image adds patchelf; clean runtime and archive verification run without
LLVM/MLIR/Z3/Clang packages, source mounts or external network. The system GCC C/C++
SDK and GNU runtime remain prerequisites. [The SDK guide](sdk.md) defines the
copied closure, notice inventory, relocation/archive gates and scope limits.

### POSIX file runtime standard headers

The file runtime explicitly includes <optional> for its pending creation
settlement guard. Linux libstdc++ must compile this code without depending on
Apple libc++ transitive standard-library includes. This is a source portability
correction, with unchanged file ownership, cancellation and physical-settlement
semantics. The original frozen191 Linux compiler diagnostics are retained in
the local linux191-arm64-v1/build.log; matching current Linux verification is a
separate requirement from prior macOS or historical Linux receipts.

### Current SDK smoke language and recovery output

The smoke helper requires actual describe, doctor and installed language-pack
versions to agree, supporting the reviewed023 and024 cohorts. Every new test
project uses that discovered language rather than a stale023 literal. Its302
unique indexed files (303 manifest references) still match the supplied source.
Use `--source MATCHING_CHECKOUT --output-root NEW_EVIDENCE` to retain an earlier
failed run while exercising an installed compiler. Defaults `/src` and `/build`
preserve the container workflow. This helper correction does not change the
compiler, existing graphs, runtime semantics or the separate source-free SDK gate.
