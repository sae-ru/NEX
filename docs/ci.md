# Development CI

The [core workflow](../.github/workflows/core.yml) builds the compiler/core
probes and runs the explicit core tier on macOS15 and Ubuntu24.04. It is
triggered by pull requests, pushes to `main`/`codex/**`, or a manual request.
Each job configures its own fresh build. No language model is invoked.

The separate [full Linux workflow](../.github/workflows/full.yml) is manual or
nightly at03:23 UTC on the default branch. It uses the existing Linux source,
installed smoke and source-free installed workflow. It runs all configured
CTest groups without a label filter. It does not run after every patch.

The [0.246.1 core run](https://github.com/sae-ru/NEX/actions/runs/43717414285) passed on macOS and Linux
for `48464ca7d9a218524485c9745b9629458c30e2bf`. The SDK's exact source `3b008a4e` also passed core CI and
**344/344 configured Linux source groups**; its raw CTest receipt is retained.
The [later integrated run](https://github.com/sae-ru/NEX/actions/runs/43693616418) completed its entire compiler,
source, install/smoke and source-free SDK **test step successfully** at `576ee8ad`.
Its overall workflow failed afterward, during artifact upload. The uploader
recursively encountered an intentionally unreadable test project. The x86-64
SDK JSON receipt could not be uploaded; the successful test-step API conclusion
and console result are preserved. This is not recorded as a green full workflow.

The workflow now exports selected receipts and captured command stdout/stderr
to a new readable directory before uploading. It does not traverse test projects
or change their permissions. [Export CI](https://github.com/sae-ru/NEX/actions/runs/43717414295) passed three
regressions and a real ordinary-user upload of root-owned evidence containing an
unreadable probe. A separate export also preserved all 1708 selected files from
the actual completed ARM64 installed SDK run. See the
[retention receipt](evidence/ci-artifact-retention-0.246.1-2026-11-15.json) and
[combined SDK evidence](evidence/sdk-current-0.246.1-2026-11-15.json).

The compiler tests were not repeated for that CI-only report-copying change.
The later [nightly at `e95b792f`](https://github.com/sae-ru/NEX/actions/runs/43859732440)
retained its artifact successfully. All **363/363 Linux source groups** passed.
Its source-free installed workflow passed20 phases, then failed while compiling
the shipped scoped C++ host in `foreign-boundary`: the example still constructed
`std::shared_ptr<Data>` after the runtime switched to `ValueOwner<Data>`.
Toolchain0.266 source now uses `Data::make`. The actual fixed installed example
and C11 module agree with reference/native Debug/Release NEX output; the example
also compiles in the core build. This [focused repair](evidence/sdk-scoped-example-0.266.0-2026-11-16.json)
does not rerun or qualify the complete source-free Linux/portable SDK workflow.
Linux installed acceptance does not qualify a portable Linux archive. Windows CI, hosted macOS full
CI and new physical GPU/NPU acceptance remain separate work. A green core job
is development feedback; the matching [SDK release record](sdk.md) records
source regression and portable archive acceptance separately. The Qwen experiment
keeps its frozen compiler and inputs.

The [recorded0.265 development run](evidence/core-ci-0.265.0-2026-11-16.json)
passed Linux. GitHub cancelled macOS after15 minutes without acquiring a hosted
ARM runner and reported capacity/internal-service errors. Its workflow conclusion
is failure; the macOS source tests did not start. Local macOS source acceptance
has its separate receipts. Changing source tests cannot remedy runner acquisition;
later development runs retain their own observed conclusions.
The subsequent [0.266 development run](evidence/core-ci-0.266.0-2026-11-16.json)
passed both Linux and macOS at `6a90e9cd`. That result precedes the scoped-example
repair; its own commit receives a separate core run.
That [scoped-example run](evidence/core-ci-scoped-example-0.266.0-2026-11-16.json)
was cancelled in both hosted jobs during build/helper execution. The macOS
CTest step was skipped; the cancelled Linux helper has no complete accepted
CTest result here. The API responses do not establish the cancellation cause.
Local repair evidence remains separate; this run is not recorded as green and
was not automatically rerun.
The subsequent [0.267 run](evidence/core-ci-0.267.0-2026-11-16.json) passed
Linux and macOS at `906b3943`, with the16-group core. Toolchain0.268 adds the
private reference-task source/control/resource probe as the17th core group;
its hosted result belongs to its own later commit.

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

The [0.251 native-candidate core run](https://github.com/sae-ru/NEX/actions/runs/43766696580)
passed on macOS. Linux failed while downloading the LLVM repository key:
`curl: (7) Failed to connect to apt.llvm.org port 443`. Docker image preparation
stopped before any NEX configure/build/test command. The original downloaded
artifact and its digest are recorded in the
[failure receipt](evidence/core-ci-0.251.0-network-failure-2026-11-16.json).
Dependency downloads now use bounded curl retries, and APT uses three retries
with 30-second connection timeouts. Package versions, archive digests and the
LLVM key fingerprint stay pinned. An exhausted download still fails the job;
the helper prints the last 16 KiB of its complete saved build log to the console.
Two offline subprocess checks verify successful logging and failure-code/log
preservation. The [corrected run](evidence/core-ci-0.251.0-corrected-2026-11-16.json)
passed macOS/Linux at `279c15db`, including the unchanged 14-group core scope.
The [0.253 run](evidence/core-ci-0.253.0-2026-11-16.json) subsequently passed
both hosted jobs at `52a2f169`, retaining that 14-group scope. Toolchain 0.254
adds the deep-value retirement probe to core. Its
[matching run](evidence/core-ci-0.254.0-2026-11-16.json) passed both hosted jobs
at `1632eb1f` with 15 groups. Toolchain 0.255 adds atomic/weak ownership and the
hidden-module fixture as the 16th core group; matching CI is a separate run.

The [first 0.255 run](evidence/ci-debugger-cache-0.255.0-2026-11-16.json)
passed macOS. Linux stopped before NEX configuration because the locked LLDB
23.1.6 package revision disappeared from the rolling APT index and pool. The
replacement remains 23.1.6, at upstream `551bf48cf74f`; `Process.cpp` has the
same hash as the previously recorded event-guard source. The lock records exact
amd64/arm64 filenames, sizes, digests and index snapshots.

Core/full CI now share a lock-derived cache of the five public LLDB packages.
`tools/linux/check.py` prepares it before image construction. Every restored or
downloaded file is checked against the lock, then checked again inside Docker
before APT receives only the five explicit filenames. A read-only build mount
keeps package archives out of image layers. This avoids requiring a still-live
APT index entry for every later build of the same snapshot. Cache misses still
need upstream bytes; cache retention is not an immutable public mirror.

An observed0.259 hosted image build stopped before NEX configuration when APT
could not resolve `apt.llvm.org`. Image preparation now retries DNS failures at
most three times, with5/10-second delays and separate complete attempt logs.
Unknown preparation failures still stop immediately; compiler/tests are never
retried by this helper. Package versions, digests and offline test execution
remain unchanged. Offline subprocess checks cover recovery and exhausted retries.

Five offline preparation cases pass. The actual amd64 packages installed in a
disposable, network-disabled Linux container and LLDB reported 23.1.6. Docker's
build check passed without warnings. Those checks qualify preparation; they do
not repeat or replace NEX runtime or full debugger/SDK acceptance. The original
failed run and all results remain in the linked receipt.

For a direct image build, first prepare the same input cache:

```sh
python3 -B tools/linux/debugger_packages.py --arch amd64 --cache build/linux-debugger-packages
docker build --platform linux/amd64 -f tools/linux/Dockerfile -t nex-linux-toolchain:amd64 .
```

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
The next [attempt](evidence/linux-ci-output-ownership-0.246.1-2026-11-15.json)
passed all 344 source groups and installed smoke, then stopped before the
source-free workflow: the host could not update the root-owned Docker receipt.
The hosted full job now runs its host orchestrator with `sudo`, matching the
ownership of its disposable Docker output. The subsequent test step passed;
its artifact retention failure and targeted export correction are described
above. Original failures and local controls are preserved.
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
