# Native Debian ARM64 compiler dependencies

The [Bookworm compiler pin](../tools/linux/compiler-bookworm-arm64.json) records
fifteen signature-verified native LLVM/MLIR/Clang/LLD22.1.8 packages. Extract
their exact archives into a private prefix with `dpkg-deb -x`. Check each
archive's size and SHA256 against the pin. The recorded InRelease signature
uses the same LLVM repository key as the maintained Linux image. No package
installation or system compiler change is required.

On physical Debian12 ARM64, these inputs compiled all730 current NEX targets
and launched the resulting compiler with the system glibc2.36 interpreter.
The [development receipt](evidence/cix-native-compiler-22.1.8-2026-11-09.json)
pins the actual source and compiler. The older dependency cohort required
glibc2.38 symbols and a private loader; its successful execution did not establish
a native Bookworm SDK baseline.

## Keep the two solver dependencies explicit

Bookworm LLVM22 uses the system `libz3.so.4` from Z3 4.8.12. That library can
satisfy LLVM's dependency while NEX selects its own solver. The first native NEX
build used the matching4.8.12 headers/library and passed ten of eleven original
bounded-verification methods. One checked-arithmetic obligation returned
`unknown`/`canceled` with the original2000ms/1000000-resource limits. Its failed
fixture, queries, compiler identity and raw logs are retained in the receipt.

The [Z3 source pin](../tools/linux/z3-bookworm-source.json) selects the same5.3.1
release as the maintained Linux image, built from unmodified upstream sources
on Bookworm. Its [native build and matching NEX proof receipt](evidence/cix-native-Z3-5.3.1-2026-11-09.json)
records all892 build steps,3095 independently rehashed source files,23 installed
files and four rehashed signed libc++ packages. The native library requires at
most GLIBC2.34 symbols on this glibc2.36 host. The resulting NEX passed all eleven
original bounded-verification methods with their original limits; complete303
and portable SDK qualification remain in progress.

The linker reported both `libz3.so.4` from native LLVM and NEX's `libz3.so.5.3`.
The receipt retains that warning and the actual loader selections. The eleven
proof methods establish their stated scope; complete cohort qualification is
still required.

The upstream source uses `<format>`, which is absent from Bookworm GCC12's C++
library. The original GNU build failed at that include. Select native Clang22
and the four matching signed libc++22 runtime/development packages listed in the
solver pin. Extract them into a separate `LIBCXX_PREFIX`; preserve the system
GNU C++ SDK used to build NEX itself. A real `<format>` program compiled and
executed42 with this private selection before the successful solver build.
The original GNU and package-layout setup failures are retained.

Set `Z3_SOURCE`, `Z3_BUILD` and `Z3_PREFIX` to new absolute private paths. Download
the exact source URL from the pin and verify its SHA256 before extraction.
The upstream CMake build requires CMake3.26+; the native stand uses3.29.3.
`LLVM22_PREFIX` names the extracted native compiler's `usr/lib/llvm-22` directory.

```sh
(
LIBCXX_INCLUDE="$LIBCXX_PREFIX/usr/lib/llvm-22/include/c++/v1"
LIBCXX_LIB="$LIBCXX_PREFIX/usr/lib/aarch64-linux-gnu"
export PATH="$LLVM22_PREFIX/bin:/usr/local/bin:/usr/bin:/bin"
export LD_LIBRARY_PATH="$LIBCXX_LIB:$LLVM22_PREFIX/lib"
cmake -S "$Z3_SOURCE" -B "$Z3_BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER="$LLVM22_PREFIX/bin/clang++" \
  -DCMAKE_CXX_FLAGS="-stdlib=libc++ -nostdinc++ -isystem \"$LIBCXX_INCLUDE\"" \
  -DCMAKE_EXE_LINKER_FLAGS="-L\"$LIBCXX_LIB\" -Wl,-rpath,\"$LIBCXX_LIB\"" \
  -DCMAKE_SHARED_LINKER_FLAGS="-L\"$LIBCXX_LIB\" -Wl,-rpath,\"$LIBCXX_LIB\"" \
  -DCMAKE_INSTALL_PREFIX="$Z3_PREFIX" -DCMAKE_INSTALL_LIBDIR=lib \
  -DBUILD_SHARED_LIBS=ON -DZ3_BUILD_EXECUTABLE=ON \
  -DZ3_BUILD_TEST_EXECUTABLES=OFF -DZ3_BUILD_PYTHON_BINDINGS=OFF \
  -DZ3_ENABLE_EXAMPLE_TARGETS=OFF -DZ3_BUILD_DOCUMENTATION=OFF
cmake --build "$Z3_BUILD" -j 4
cmake --install "$Z3_BUILD"
env LD_LIBRARY_PATH="$Z3_PREFIX/lib:$LIBCXX_LIB:$LLVM22_PREFIX/lib" \
  "$Z3_PREFIX/bin/z3" --version
readelf -d "$Z3_PREFIX/lib/libz3.so"
ldd "$Z3_PREFIX/lib/libz3.so"
)
```

The subshell scopes the dependency environment. The multiarch
`libc++.so` is a linker script that also selects libc++abi; the LLVM library
directory contains additional aliases of the same runtime. The package inventory
therefore legitimately has two `libc++.so` paths.

Upstream CMake assigns the5.3 library the SONAME `libz3.so.5.3`. Retain that
versioned library and its aliases; LLVM's separate `libz3.so.4` remains selected
by its own SONAME. Keep unversioned development aliases outside the child runtime
library path. The [native debugger guide](linux-native-debugger.md) describes the
same boundary for the independently selected LLDB23 cohort.

## Configure the NEX source gate

Use the actual compiler pin's LLVM prefix for `LLVM_DIR`, `MLIR_DIR`, Clang,
LLVM AR and both LLD tools. Select the new Z3 headers and library together.
The Debian development prefix supplies the matching libcurl development files
needed by LLVM's exported CMake targets. The existing private CMake hook resolves
those targets to the versioned system Z3 without adding a global library alias.

In addition to the usual SQLite/OpenSSL3, Python and Node settings, pass:

```sh
cmake -S "$NEX_SOURCE" -B "$NEX_BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/g++ \
  -DLLVM_DIR="$LLVM22_PREFIX/lib/cmake/llvm" \
  -DMLIR_DIR="$LLVM22_PREFIX/lib/cmake/mlir" \
  -DNEX_Z3_INCLUDE="$Z3_PREFIX/include" \
  -DNEX_Z3_LIBRARY="$Z3_PREFIX/lib/libz3.so" \
  -DNEX_Z3_EXECUTABLE="$Z3_PREFIX/bin/z3" \
  -DNEX_ELF_TEST_LD="$LLVM22_PREFIX/bin/ld.lld" \
  -DNEX_WASM_LD="$LLVM22_PREFIX/bin/wasm-ld" \
  -DCMAKE_PROJECT_NEX_INCLUDE="$NEX_SOURCE/tools/linux/private-debugger-dependencies.cmake" \
  -DNEX_LLDB_Z3_LIBRARY=/usr/lib/aarch64-linux-gnu/libz3.so.4 \
  -DCURL_INCLUDE_DIR="$DEBIAN_DEPS/usr/include/aarch64-linux-gnu" \
  -DCURL_LIBRARY_RELEASE="$DEBIAN_DEPS/usr/lib/aarch64-linux-gnu/libcurl.so" \
  -DCMAKE_PREFIX_PATH="$DEBIAN_DEPS/usr" \
  -DCMAKE_LIBRARY_PATH="$DEBIAN_DEPS/usr/lib/aarch64-linux-gnu" \
  -DNEX_CARES_PREFIX="$CARES_PREFIX" -DNEX_HTTP_PREFIX="$HTTP_PREFIX" \
  -DNEX_PACKAGE_NOTICES_FILE="$PACKAGE_NOTICES"
```

`PACKAGE_NOTICES` is the real operator catalogue for private runtime libraries.
The original native attempt omitted this CMake argument even though its parent
configuration supplied it. Before the long run, inspect the registered commands
for public file-write, DNS, TCP, HTTP and HTTP-stream delivery: all five must
receive the selected `--package-notices` path. Preserve the earlier registry;
adding the argument does not turn that earlier attempt into a passed run.

Build with `cmake --build "$NEX_BUILD" -j 4`. Verify the actual `ldd` output and
ELF interpreter, then run all eleven unchanged `tests/verification.py` methods
and the complete registered CTest suite. Retain its registry/JUnit and original
individual timeouts. Use the new matching debugger, compiler and Node selection
in a scoped child environment. On the ARM stand, the full FFI group previously
used1640 of its1800 seconds; the complete regression uses one CTest worker to
avoid competing cold compilations.

Ordinary installation, relocated SDK assembly, archive restoration, source and
dependency isolation, live debugging, browser and physical-device acceptance
remain additional gates. The system glibc/GCC development SDK, Python, Node/npm
and independently qualified host debugger remain documented prerequisites.
