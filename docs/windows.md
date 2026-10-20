# Windows GNU/UCRT core target

Toolchain0.64 adds explicit cross-builds for `x86_64-w64-windows-gnu` and
`aarch64-w64-windows-gnu`. Debug/release executables are PE/COFF `app.exe`;
`--library --entry NAME` produces a GNU `libnex.a` archive. This adds no source
syntax or language0.16 migration. This is an initial core target, with Windows
OS execution and a Windows-hosted compiler still pending validation.

Supply an installed LLVM-MinGW UCRT toolchain and its matching target sysroot.
The maintained build uses LLVM22.1. Do not point these paths at host SDK tools
or libraries. All paths can be relative to the toolchain configuration file:

```json
{
  "schema": "nex.toolchain/1",
  "target": "x86_64-w64-windows-gnu",
  "compiler": "/tools/llvm-mingw/bin/x86_64-w64-mingw32-clang++",
  "linker": "/tools/llvm-mingw/bin/ld.lld",
  "archiver": "/tools/llvm-mingw/bin/llvm-ar",
  "sysroot": "/tools/llvm-mingw/x86_64-w64-mingw32",
  "windows": {
    "runtime": "ucrt-static",
    "notices": "windows-runtime-notices.txt"
  }
}
```

The notices file must contain the applicable LLVM/libc++/libc++abi/libunwind,
compiler runtime and MinGW runtime terms from the selected installation, including
required component attributions. NEX copies the supplied text, bounded to1MiB,
into the build notices and captured runtime projection. It does not determine
whether an operator's notices are complete. The GNU driver links C++ support
statically; UCRT and Windows system DLLs remain platform dependencies. The
output is not a freestanding executable or a signed installer.

```sh
nex toolchain windows-toolchain.json --json
nex build examples/windows/main.nex --toolchain windows-toolchain.json --profile release --json
nex build examples/windows/main.nex --toolchain windows-toolchain.json --library --entry answer --json
```

For ARM64 use its `aarch64` driver, target and sysroot together. NEX probes the
driver's actual LLVM triple, data layout and64-bit pointers and checks selected
MinGW/UCRT preprocessor definitions before code generation. It never overrides
an already-emitted host IR target. Build/cache identities include the configured
driver arguments, linker/archiver bytes, target/layout, notices and selected CRT,
libc++/ABI/unwind libraries and MinGW headers. Toolchain snapshots list the exact
captured files. Other SDK headers, compiler support files and environment remain
external inputs; this fingerprint is not a complete hermetic SDK inventory.

The initial target accepts the checked core language, immutable aggregates,
traits/generics, function values, finite numbers, Unicode and binary values,
strict JSON and `print`. Standard-output text contains UTF-8 bytes; the platform
CRT uses Windows line endings. Console rendering depends on the receiving host.
Reachable database, filesystem/resource operations, environment reads, external
modules, HTTP servers and profile builds fail explicitly. Other unused source
declarations do not require a target adapter. These facilities, native GUI/plugin
bindings, MSVC ABI,32-bit/ARM64EC, Windows debugger/profiler, application packaging
and SDK distribution remain pending.

Local `run`, `test`, `debug` and `profile` reject this foreign ABI with
`E_TARGET_RUN`; NEX starts no emulator. Cross-build success establishes code
generation/linkage. PE inspection, Wine compatibility and actual Windows/device
execution are distinct checks. Keep their results separate in evidence.

The optional real-target regression group uses a preinstalled SDK:

```sh
NEX_WINDOWS_TOOLCHAIN_ROOT=/tools/llvm-mingw ctest --test-dir build -R windows_targets --output-on-failure
```

It builds both architectures/profiles, inspects COFF objects and executable
imports, links a C++ host against the archive, verifies cache/source replay and
checks rejection boundaries. Without this environment variable, real cross-build
cases are reported skipped and the unconfigured-target checks still run. No
toolchain is downloaded or target executable launched by that regression group.
