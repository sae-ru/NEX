# Native Bookworm debugger

The [Bookworm source cohort](../tools/linux/debugger-bookworm-source.json) pins
LLDB23.1.6, its complete source archive, both local patches and signature-verified
LLVM23 development packages. NEX compilation continues to use LLVM/MLIR22.1.8.
The Ubuntu [Docker recipe](../tools/linux/Debugger.Dockerfile) retains its own
23.1.5 source/package pins.

On actual Debian12 ARM64, the complete native build, nine register profiles with
105 checks, the original live indexed-page test and all fifteen task-debugger
methods passed. The page test also passed on the original stock-failure binary
without changing its bytes or nanosecond modification time. The
[receipt](evidence/cix-native-lldb-23.1.6-2026-11-09.json) preserves the initial
stock timeout and dependency setup failures. Complete NEX source and portable
SDK qualification remain separate gates.

Use fresh source/build/install directories and matching LLVM23 development
inputs. The package pin lists thirteen LLVM packages and nine Debian development
packages. Include ICU headers: Bookworm's libxml2 development headers include
`unicode/ucnv.h`. Python3.11 development headers/shared library, Ninja, CMake and
the host GNU C++12 headers/runtime are also required. The native control used
CMake3.29.3 and Clang23.1.6. Packages can be extracted with `dpkg-deb -x` into a
private prefix. Private development-library aliases must resolve to the selected
versioned runtime libraries; record their actual hashes. The tested build did
not install packages or add aliases under `/usr`.

Verify the source archive and both pre/post-patch file hashes against the JSON
pin. Apply the two existing patches with `patch --fuzz=0 -p1`. Their source files
are byte-identical across the pinned23.1.5 and23.1.6 revisions, so the patches need
no adaptation. Keep `Process.cpp` as supplied by the pinned upstream revision.

Set `NEX_REPO`, `LLDB_SOURCE`, `LLDB_BUILD`, `LLDB_PREFIX`, `LLVM23_PREFIX` and
`NEX_DEBUGGER_DEPS` to absolute paths. The dependency prefix below contains the
extracted Debian headers, libraries and SWIG resources; LLVM23 has its own prefix.
Keep dependency environment settings scoped to debugger commands:

```sh
lldb_env() {
  env LD_LIBRARY_PATH="$LLDB_PREFIX/lib:$LLVM23_PREFIX/lib:$NEX_DEBUGGER_DEPS/usr/lib/aarch64-linux-gnu" \
      SWIG_LIB="$NEX_DEBUGGER_DEPS/usr/share/swig4.0" \
      PKG_CONFIG_SYSROOT_DIR="$NEX_DEBUGGER_DEPS" \
      PKG_CONFIG_LIBDIR="$NEX_DEBUGGER_DEPS/usr/lib/aarch64-linux-gnu/pkgconfig:$NEX_DEBUGGER_DEPS/usr/share/pkgconfig" \
      PATH="$LLVM23_PREFIX/bin:$NEX_DEBUGGER_DEPS/usr/bin:/usr/local/bin:/usr/bin:/bin" "$@"
}
lldb_env cmake -S "$LLDB_SOURCE/lldb" -B "$LLDB_BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_C_COMPILER="$LLVM23_PREFIX/bin/clang" \
  -DCMAKE_CXX_COMPILER="$LLVM23_PREFIX/bin/clang++" \
  -DCMAKE_C_FLAGS="-I$NEX_DEBUGGER_DEPS/usr/include" \
  -DCMAKE_CXX_FLAGS="-I$NEX_DEBUGGER_DEPS/usr/include" \
  -DLLVM_DIR="$LLVM23_PREFIX/lib/cmake/llvm" \
  -DClang_DIR="$LLVM23_PREFIX/lib/cmake/clang" \
  -DCMAKE_PREFIX_PATH="$NEX_DEBUGGER_DEPS/usr;$LLVM23_PREFIX" \
  -DCMAKE_LIBRARY_PATH="$NEX_DEBUGGER_DEPS/usr/lib/aarch64-linux-gnu" \
  -DCMAKE_INCLUDE_PATH="$NEX_DEBUGGER_DEPS/usr/include" \
  -DCMAKE_PROJECT_lldb_INCLUDE="$NEX_REPO/tools/linux/private-debugger-dependencies.cmake" \
  -DNEX_LLDB_Z3_LIBRARY="$NEX_DEBUGGER_DEPS/usr/lib/aarch64-linux-gnu/libz3.so" \
  -DCURL_INCLUDE_DIR="$NEX_DEBUGGER_DEPS/usr/include/aarch64-linux-gnu" \
  -DCURL_LIBRARY_RELEASE="$NEX_DEBUGGER_DEPS/usr/lib/aarch64-linux-gnu/libcurl.so" \
  -DLIBXML2_INCLUDE_DIR="$NEX_DEBUGGER_DEPS/usr/include/libxml2" \
  -DLIBXML2_LIBRARY="$NEX_DEBUGGER_DEPS/usr/lib/aarch64-linux-gnu/libxml2.so" \
  -DSWIG_EXECUTABLE="$NEX_DEBUGGER_DEPS/usr/bin/swig4.0" \
  -DLLVM_LINK_LLVM_DYLIB=ON -DLLDB_INCLUDE_TESTS=OFF \
  -DLLDB_ENABLE_LIBCXX_TESTS=OFF -DLLVM_INCLUDE_TESTS=OFF \
  -DLLDB_ENABLE_PYTHON=ON -DLLDB_ENABLE_LUA=OFF -DLLDB_ENABLE_CURSES=OFF \
  -DLLDB_ENABLE_LIBEDIT=ON -DLLDB_ENABLE_LIBXML2=ON \
  -DLLDB_ENABLE_LZMA=OFF -DLLDB_BUILD_INTEL_PT=OFF \
  -DPython3_EXECUTABLE=/usr/bin/python3 \
  -DLLDB_PYTHON_RELATIVE_PATH=lib/python3.11/site-packages \
  -DCMAKE_INSTALL_LIBDIR=lib -DCMAKE_INSTALL_PREFIX="$LLDB_PREFIX"
lldb_env cmake --build "$LLDB_BUILD" \
  --target lldb lldb-dap lldb-server lldb-argdumper -j 4
lldb_env python3 "$NEX_REPO/tools/linux/check_lldb_registers.py" \
  --build "$LLDB_BUILD" --source "$LLDB_SOURCE" \
  --llvm-prefix "$LLVM23_PREFIX" --compiler "$LLVM23_PREFIX/bin/clang++" \
  --test-source "$NEX_REPO/tools/linux/lldb23-za-registers-test.cpp" \
  --output /absolute/new/register-controls
lldb_env cmake --build "$LLDB_BUILD" --target install-liblldb install-lldb \
  install-lldb-dap install-lldb-server install-lldb-argdumper -j 4
mkdir -p "$LLDB_PREFIX/lib/clang"
cp -a "$LLVM23_PREFIX/lib/clang/." "$LLDB_PREFIX/lib/clang/"
```

The register checker requires exactly nine profiles and105 checks. Verify
`lldb --version`, `lldb-dap --version` and the embedded Python module's actual
`lldb.__file__` under the new prefix before NEX tests. Deploy the complete matching
CLI/DAP/server/liblldb/Python/Clang cohort. The earlier DAP-only replacement failed
the original pre-launch breakpoint check.

For NEX checks, select `NEX_LLDB` and `NEX_LLDB_DAP` explicitly and keep LLVM22
symbol/compiler tools ahead of LLVM23 in the child PATH. Run the unchanged
`tests/native_pages.py /absolute/current/nex --live` and the complete
`task_debugging_native` CTest group with their original sizes and timeouts. Preserve
all raw logs and exact compiler/resource hashes. These checks exercise the source
configuration; moved/restored SDK isolation and hardware acceptance still need
their own exact-archive results.
