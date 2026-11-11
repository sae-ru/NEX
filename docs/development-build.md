# Repeatable development configuration

The shared [CMake presets](../CMakePresets.json) select Debug/Release profiles,
separate build directories and the small [core test layer](testing.md). Install
the source build dependencies from [README](../README.md#build-and-use), then:

```sh
cmake --workflow --preset dev-core
```

The file uses the [CMake3.25 preset/workflow format](https://cmake.org/cmake/help/v3.25/manual/cmake-presets.7.html).

This configures `build/presets/dev-debug`, builds the existing compiler/core
probes with four jobs and runs the eleven core groups sequentially. It performs
no npm installation or model invocation. Configure, build and test can also be
selected independently:

```sh
cmake --preset dev-debug
cmake --build --preset core
ctest --preset core
cmake --build --preset dev
```

The presets use the host's selected generator and compiler. Set `CC`, `CXX` and
`CMAKE_GENERATOR` before the first configure when a particular toolchain is
needed. Windows source builds use the documented CLANG64 environment and Ninja;
current Windows/portable SDK acceptance remains its own gate. Discover actual
LLVM/MLIR22.1, SQLite, OpenSSL3 and Z3 installations rather than substituting a
different compiler stack. Explicit local selectors are kept in the build cache:

```sh
cmake --preset dev-debug \
  -DLLVM_DIR=/absolute/llvm22/lib/cmake/llvm \
  -DMLIR_DIR=/absolute/llvm22/lib/cmake/mlir \
  -DNEX_Z3_ROOT=/absolute/z3
```

Subsequent `dev-core` workflows retain those selectors. Use `CMakeUserPresets.json`
for additional personal configurations; that file stays out of Git. Shared
presets, source, manifests, lock files and reviewed test policy belong in Git.

## Full and release workflows

```sh
cmake --preset dev-release
cmake --build --preset release
```

For the full milestone, prepare the repository's locked web dependencies and
selected platform/provider tools as in README, then use `ctest --preset full`
or `ctest --preset release-full`. Full presets have no label filter and do not
silently hydrate npm dependencies. `core` is a small development baseline;
affected feature/backend checks and final full acceptance retain their scope.

## Existing Linux environment

The repository already has a [Linux toolchain container](../tools/linux/Dockerfile)
with LLVM/MLIR22.1.8 package versions, a pinned Ubuntu base and pinned Z3/Node
archives. Reuse this environment for Linux work. The existing
[`tools/linux/check.py`](../tools/linux/check.py) orchestrates the complete
source/full-test/installed-SDK/source-free SDK workflow, with immutable image ID
recording and offline verification after image preparation. Its `--skip-image-build`
option uses an already prepared image.

Presets do not pin every host package or establish a reproducible portable SDK.
Complete dependency inventories, immutable archive preparation and current
platform/source-free acceptance remain separate delivery work. Whole-profile
builds and timing for every platform remain qualification gates.

The [current qualification](evidence/development-presets-0.165.0-2026-11-11.json) covers actual CMake preset parsing, a fresh selected-
dependency Debug configure and exact11-group core preset selection on macOS.
The fresh profile has not been fully rebuilt or executed: the independent
Qwen comparison keeps its original compiler immutable while it runs. The
previous core-target build and11-group execution retain their own
[evidence](evidence/test-tiers-0.165.0-2026-11-11.json).
