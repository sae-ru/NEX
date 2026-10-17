# Linux compiler and development chain — toolchain 0.23

The Linux environment builds NEX itself and native NEX programs with C++20,
LLVM/MLIR/LLD 22.1.8, SQLite, OpenSSL 3, Z3 5.3.1 and Node.js 22.22.3.
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

For actual LLDB/DAP checks on a Linux CPU with native ptrace support:

```sh
python3 tools/linux/check.py --arch arm64 --live --skip-image-build
```

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
