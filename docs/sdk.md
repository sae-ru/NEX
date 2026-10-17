# Installed SDK acceptance and handoff

Install the compiler and its matching resources after building NEX:

```sh
cmake --install build --prefix /absolute/nex-sdk
python3 /absolute/nex-sdk/share/nex/tools/sdk_acceptance.py /absolute/nex-sdk \
  --output /absolute/new-evidence --browser --live
```

The output directory must be new or empty. The script never replaces previous
evidence and never imports files from the compiler's source checkout. It sets
`NEX_RESOURCE_DIR` to this SDK, verifies the selected runtime and matching
language-pack version, inventories every indexed text resource, and queries the
sixteen installed guides. Python 3.9+, the SDK's development dependencies
(LLVM/MLIR, Clang, platform SDK, SQLite/OpenSSL, Z3 and Node.js) remain required.
This is an installed-development-chain check, not a portable SDK bundle.

The maintained scenario performs these actual operations:

1. Create, check, test and execute a new project.
2. Author a two-module program using generics, bounds, nested result/enum
   patterns, guards, immutable aggregates and an embedded NUL/Unicode string.
   Keep reviewed acceptance tests and exact native output in a task contract.
3. Run the deliberately wrong implementation and require failed acceptance.
   Query bounded function/operation context, apply a revision-checked repair,
   reject its stale duplicate, and preserve function identities.
4. Export the checked graph, import it into a separate store and execute it.
   Run the original task against the repaired archive with its unchanged task
   hash. Compare reference/native/TypeScript behavior and debug/release output.
   Copy and run a standalone native executable with NEX resources unavailable.
5. Profile a named workload, check function content/node attribution and actual
   balanced managed allocation pools, and reject dropped measurement records.
6. Delete the original source files and task document. Retrieve an archived
   debug session, replay the accepted task, execute the old revision with its
   original wrong behavior, materialize the repaired sources and execute them.
7. Prove the installed scalar verification example with the actual solver.
   This does not prove matching, the compiler or the whole application.
8. Test and generate the installed generic browser example with captured
   callback state, checking that an
   unreachable server sentinel is absent from generated TypeScript.

The source workflow also exercises generic snapshot closures and wire-bounded
roundtrips across reference/native/TypeScript output. Discovery checks the
matching function guide and callback capabilities. These checks are included in
the ordinary source-free scenario rather than requiring the repository.

`--live` additionally launches the actual NEX DAP/LLDB stack against archived
source after its original files were deleted. It verifies a source breakpoint,
evaluates a nested match over a stopped parameter, captures a partial frame,
resumes to clean exit and evaluates that exact snapshot offline. Without
`--live`, the report records `live_debugger: false`; creating a manifest does
not establish debugger execution. The host must permit child debugging.

`--browser` additionally performs the real locked TypeScript/Vite release build
and checks emitted assets/maps for the server sentinel. Without this flag only
TypeScript semantic tests and project generation run; browser production
compilation is recorded as false. Actual browser interaction remains covered by
the separate Playwright suites. In an isolated container, the npm lock's
packages must already be cached; a missing dependency fails the check.

Every command records its arguments, working directory, exit status and separate
stdout/stderr files. `report.json` is checkpointed before/after phases, starts
with `ok: false`, and becomes true only after every requested phase passes.
Failure, interruption or timeout retains the completed evidence and current
phase. The expected failing task has a nonzero exit status, pinned task hash
and failed receipt; it is never counted as accepted behavior. Evidence paths in
a container report use that container's mount layout. Keep its whole output
directory for receipt/debug replay. Hashes describe captured inputs, not signed
attestations or proof that arbitrary external tools are trustworthy.

The script does not modify the SDK or source checkout. Evidence contains its
own fixture sources, SQLite stores, binaries, frozen resources, debug symbols,
task receipts and generated browser projects; allow sufficient disk space.
The retained sources are test fixtures, not credentials. Timeout cleanup asks
the NEX process group to terminate before escalating; this is not an OS sandbox
and does not contain deliberately detached processes.

## Linux without a source mount

`tools/linux/check.py` now runs this workflow in a second container after the
compiler regression and installed server/SDK checks. That container has only
the read-only installed SDK and a fresh writable evidence directory mounted;
`/src` is absent, external networking is disabled, and `--browser` is required.
The image preloads the exact npm lock. `--live` also requests real debugger
execution and the documented ptrace permissions on a supported native CPU.
The top-level verification remains false while this second workflow runs and
cannot pass if it fails or observes another compiler/resource selection.

The outer report links `sdk-acceptance/RUN/workflow/report.json`. It retains a
copy as `source-free-sdk.json` and archives that report/log with the versioned
checkpoint. `--forbid-source /src` in the inner command verifies that known
mount path is absent. The Docker invocation supplies the evidence that the
source checkout was not mounted; a path probe alone cannot prove that arbitrary
other filesystem locations contain no sources.
