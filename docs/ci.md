# Development CI

The [core workflow](../.github/workflows/core.yml) builds the compiler/core
probes and runs the explicit core tier on macOS15 and Ubuntu24.04. It is
triggered by pull requests, pushes to `main`/`codex/**`, or a manual request.
Each job configures its own fresh build. No language model is invoked.

The separate [full Linux workflow](../.github/workflows/full.yml) is manual or
nightly at03:23 UTC on the default branch. It uses the existing Linux source,
installed smoke and source-free installed workflow. It runs all configured
CTest groups without a label filter. It does not run after every patch.

These definitions are not observations of successful GitHub runs. They remain
local until pushed; the current Qwen experiment uses its frozen compiler and
inputs throughout. Hosted-runner qualification, Windows CI, macOS full CI,
physical GPU/NPU acceptance and final immutable portable SDK delivery remain
pending. A green core job is development feedback, not release acceptance.

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
