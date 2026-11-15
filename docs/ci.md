# Development CI

The [core workflow](../.github/workflows/core.yml) builds the compiler/core
probes and runs the explicit core tier on macOS15 and Ubuntu24.04. It is
triggered by pull requests, pushes to `main`/`codex/**`, or a manual request.
Each job configures its own fresh build. No language model is invoked.

The separate [full Linux workflow](../.github/workflows/full.yml) is manual or
nightly at03:23 UTC on the default branch. It uses the existing Linux source,
installed smoke and source-free installed workflow. It runs all configured
CTest groups without a label filter. It does not run after every patch.

The [November 14 core run](https://github.com/sae-ru/NEX/actions/runs/43625795419)
passed on both hosted platforms for source `c949180175a428bfeb8373ce9f2bffaf787ee311`.
This qualifies the core workflow for that source. Windows CI, hosted macOS full
CI and new physical GPU/NPU acceptance remain separate work. A green core job
is development feedback; the matching [SDK release record](sdk.md) records
source regression and portable archive acceptance separately. The Qwen experiment
keeps its frozen compiler and inputs.

## Dependencies and provenance

Linux reuses [the toolchain Dockerfile](../tools/linux/Dockerfile) with its pinned
base, LLVM/MLIR22.1.8 and Z3/Node archives. Image preparation has network access;
test containers use `--network none`, a read-only source mount and separate
writable build output. Both source and source-free SDK containers execute the
inspected immutable image ID. The tag and ID remain in `environment.json`.
`--tier core` builds `nex_core_tests` and skips web hydration/install/SDK phases.
The base image still contains Node and its prepared npm cache. The full mode
keeps locked offline web dependency preparation and installed workflow stages.
`--live` requires full mode and is not enabled on hosted runners.

macOS selects native Homebrew `llvm@22`, `lld@22`, OpenSSL3, SQLite, Z3,
Python3.14, Ninja and CMake. The package inventory and configure/build logs
are retained. Homebrew dependencies are rolling installations, not a pinned
portable SDK; a changed/unavailable dependency is a visible job failure.
No npm preparation is performed by the macOS core job.

The November 14 hosted run failed before tests: macOS used Apple's older C++
library without `std::stop_token`, and Linux could no longer download the pinned
LLDB23.1.5 packages. The macOS job now explicitly selects the LLVM22 compiler,
headers and libc++ runtime. The Linux debugger pin and package inventory now
select the available23.1.6 snapshot for both architectures. Local C++20
compile/run and package-index checks cover these corrections; the linked hosted
run passed with the updated workflows.
The subsequent macOS attempt exposed an additional include-order failure:
system SQLite injected the Apple SDK's entire `usr/include` ahead of Clang's
builtin headers. The job now explicitly selects Homebrew SQLite headers/library
without adding that SDK directory. A local negative/positive compile control
reproduces the SDK-include failure and passes with the selected include layout.

The first complete Linux run at `c9491801` built every target, then passed
331 of 344 configured groups. Thirteen failed: Git was absent from the image,
the OpenCL loader was absent, and real logical LLDB/DAP tests lacked the
container debugger syscall configuration. The toolchain image now includes
Git and the OpenCL loader. Full source and source-free SDK containers use
`SYS_PTRACE` and the existing debugger seccomp setting because their maintained
phases exercise debugger helpers even when the additional `--live` matrix is
not selected. The core tier keeps its ordinary container configuration.
A [local control](evidence/linux-ci-container-fixes-0.246.1-2026-11-15.json)
reproduces `configurationDone: process already running` and
passes with the debugger configuration using the same NEX and LLDB binaries.
Complete hosted qualification of the replacement remains pending.
The full job uses four parallel jobs on the public Ubuntu runner, matching its
[four CPU cores and 16 GB RAM](https://docs.github.com/en/actions/reference/runners/github-hosted-runners#standard-github-hosted-runners-for-public-repositories).

The two external actions are fixed to full commit SHAs from the official
[checkout release](https://github.com/actions/checkout/releases/tag/v7.0.1)
and [artifact release](https://github.com/actions/upload-artifact/releases/tag/v7.0.2).
Workflows grant `contents: read`, do not retain checkout credentials and upload
only selected build/configuration reports, with14-day retention. They do not
publish packages, push commits or use repository secrets.

## Receipt rules

[`tools/ci/ctest.py`](../tools/ci/ctest.py) operates on an already configured and
built directory. It records the real unfiltered CTest registry, validates its
labels against [the explicit policy](../cmake/test-tiers.json), selects core or
full, runs CTest once and retains its actual process exit code. The existing
fixture-closure/JUnit validator checks exact group names, completeness, unique
cases, failed/not-run groups and group-level skips. Missing or malformed XML
fails the command. An existing output directory is rejected to prevent reuse
of an old result. Individual test programs can still report their own
platform-specific skipped cases; their logs remain evidence and do not qualify
those unexecuted capabilities. The receipt always says
`release_qualification: false`.

Examples after configuring/building:

```sh
python3 -B tools/ci/ctest.py --build build/presets/dev-debug \
  --tier core --output build/my-core-evidence
python3 -B tools/linux/check.py --arch amd64 --tier core \
  --output build/my-linux-core
python3 -B tools/linux/check.py --arch amd64 --tier full \
  --output build/my-linux-full
```

Use fresh output/build directories for independent attempts. The Linux helper
also accepts `--skip-image-build --image EXISTING_TAG` for a previously prepared
environment. The first dependency image/build on a hosted runner can dominate
latency; no cached-build speedup is claimed. A shared immutable image/cache can
be qualified separately after initial hosted runs.

CTest JSON, JUnit, validated receipt, stdout/stderr and `LastTest.log` remain
available for failures. Workflow artifact steps use `always()`; failure before
test execution cannot become a test pass just because no report was uploaded.
GitHub's [workflow syntax](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
defines trigger, permissions, timeout, shell and concurrency behavior.

The [local qualification](evidence/ci-workflows-0.165.0-2026-11-11.json) covers
one all-target incremental build, all11 actual core groups through the new
receipt runner, the new CTest receipt controls and successful actionlint1.7.12
validation. No compiler binary or language/ABI changed.
