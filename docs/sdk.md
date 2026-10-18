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
eighteen installed guides. Python 3.9+, the SDK's development dependencies
(LLVM/MLIR, Clang, platform SDK, SQLite/OpenSSL, Z3 and Node.js) remain required. The maintained HTTPS check also uses the `openssl` CLI. On Linux, its application-packaging phase additionally requires `patchelf`, `readelf` and `ldd`; these are development/packaging tools rather than generated-application dependencies.
The text-file phase checks explicit capability/read-only denial, native/reference
Unicode/NUL agreement, source-deleted replay and a packaged file application
executed with compiler resources unavailable. File access requires no SQLite or
JSON runtime. Its report distinguishes assembly from actual execution.
This is an installed-development-chain check, not a portable SDK bundle.

The foreign-boundary phase also builds an independent C11 shared module and a
C++20 host against the installed runtime. It pins the exact bundle manifest and
canonical compiler-exported signature, grants only the named export, deletes
the C/C++ sources and compares loaded output with the native/reference/
TypeScript NEX model. The host links the selected OpenSSL Crypto (and `dl` on
Linux); this does not verify a distributable native dependency closure.
The same phase exercises the scoped native handle bridge with explicit
operator/binding JSON, relative bundle paths and a real request scope after
deleting the C++ host source. The same phase materializes
`examples/ffi/source.nex.in` with the actual manifest pin and runs its source
external call in the interpreter, native Debug/Release and native tests with an
explicit operator catalogue. It also checks a portable client test, archived
execution after source deletion and the standalone native binary with compiler
resources unavailable. Toolchain 0.42 additionally runs reviewed native task
checks with a pinned operator catalogue, captures exact module bytes and replays
after deleting NEX sources/task documents while requiring current operator trust.
Its evidence records both task receipts. Packaging of external dependency
closures remains pending.

## Relocatable macOS development bundle (0.27, under validation)

```sh
cmake --install build --prefix /absolute/installed-sdk
python3 tools/sdk_bundle.py --sdk /absolute/installed-sdk \
  --output /absolute/new-nex-bundle --notices /absolute/notices.json
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
mv /absolute/new-nex-bundle '/absolute/moved NEX SDK'
python3 '/absolute/moved NEX SDK/share/nex/tools/sdk_acceptance.py' \
  '/absolute/moved NEX SDK' --output /absolute/new-bundle-evidence --browser --live
```

Select the host Apple SDK with `SDKROOT` as above, or use an explicit native
`--toolchain` configuration with `sysroot`. The bundle does not carry Apple SDK
headers or depend on Homebrew's machine-specific Clang config files.

The packager currently runs on macOS. It copies the installed compiler, matching
resources, Clang/llvm-ar/dsymutil, Clang builtin/runtime resources, libc++ headers,
SQLite/OpenSSL headers/libraries and their transitive non-system Mach-O libraries.
It rewrites copied load commands to bundle-relative `@loader_path` references,
removes build-machine rpaths and refreshes ad hoc code signatures. Source
installations are never rewritten. Apple SDK/command line tools, the system C++
runtime/linker, Python, Node/npm and host LLDB/lldb-dap remain prerequisites.
Developer ID signing/notarization, older macOS versions, Linux/Windows bundles
and mobile SDKs remain pending. The resulting manifest records the maximum
minimum macOS version of its shipped images; the development compiler built
on this host requires macOS 27.0 even when generated applications target 13.0.

`--notices` supplies a `nex.sdk-notices/1` JSON object with `components`, each
containing a unique `name`, `version`, upstream `url`, local `roots` and
`license_files` arrays. Paths are relative to that JSON file or absolute.
Every external file must belong to a declared root; overlapping roots use the
most specific match. Full UTF-8 notice files are retained with their hashes.
For example one entry can describe the LLVM installation prefix and its complete
LLVM and component notice files. Add entries for every actual dependency found
in the closure, including compression libraries. Missing provenance stops the
packaging process. Keep the completed component/notice inventory with the bundle.

`share/nex/sdk-host.json` (`nex.sdk-host/1`,
[`sdk-host.schema.json`](../llm/sdk-host.schema.json)) selects tools and dependency
paths relative to the actual executable's installation prefix. Paths must resolve
inside that prefix. A present but invalid/incomplete descriptor fails with E_SDK;
it does not fall back to paths from the compiler's build machine.
`NEX_RESOURCE_DIR` selects language/runtime text resources separately.
`NEX_CLANG` and explicit `--toolchain` configurations retain their normal override
precedence; `doctor` now reports the effective compiler, archive/debug tools and
dependency paths. An explicit native toolchain can select `archiver` and
`debug_packager`; both are fingerprinted alongside the selected linker.

`share/nex/sdk-bundle.json` inventories packaged bytes, original external hashes,
component notices, prerequisites and minimum OS. `ok: true` there means assembly
and static load-command/signature validation passed. `acceptance_passed: false`
requires the separate maintained acceptance run after moving the directory.
That manifest does not claim testing on another machine or older OS.

The layout follows [Apple's guidance for nonstandard code bundles](https://developer.apple.com/documentation/xcode/embedding-nonstandard-code-structures-in-a-bundle)
and uses the [LLVM toolchain components](https://clang.llvm.org/docs/Toolchain.html).

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
   Require finite f64 generic/aggregate/callback agreement in both native
   profiles and TypeScript, archived replay after source deletion, and a
   separate numeric executable without runtime resources.
   Build a separate three-function project, require a warm cache, edit one
   function without moving siblings, and require one compiled/two reused
   function objects with correct changed output. Delete its source and execute
   both archived revisions again.
5. Profile a named workload, check function content/node attribution and actual
   balanced managed allocation pools, and reject dropped measurement records.
6. Delete the original source files and task document. Retrieve an archived
   debug session, replay the accepted task, execute the old revision with its
   original wrong behavior, materialize the repaired sources and execute them.
7. Prove the installed scalar verification example with the actual solver.
   This does not prove matching, the compiler or the whole application.
8. Build a native HTTP/HTTPS service, reject unauthenticated requests and check
   per-principal Unicode storage and persistence after a server restart.
9. Test and generate both the installed generic browser example with captured
   callback state and the finite-number application. Its immutable f64 state,
   generic arithmetic, callback and strict JSON edits pass native/TypeScript
   transition tests. Check that unreachable server sentinels are absent from
   generated TypeScript.

The current workflow has fifteen phases. Its foreign-boundary phase compiles a
C11 producer and C++20 host using only the installed runtime, verifies copied
UTF-8/binary values, deletes their source files and runs the independent host
with NEX resources unavailable. This tests the experimental host transport. The
same phase additionally runs the 0.15 source external declaration described
above. It exports a checked NEX function's
value schema and uses a C producer to construct its generic record/enum/result.
Its C host agrees with the reference/native/TypeScript model and runs after
source deletion with only the retained type metadata. Its binary-value phase additionally
compares source bytes, codecs, generic wire models and captured callbacks across
reference/native Debug/Release/TypeScript. It replays an archived binary program
after deleting source, runs an independent executable with resources unavailable,
and packages a binary-file application that preserves NUL and invalid UTF-8
octets. `--live` also checks typed byte watches and paged children after source
deletion. The browser phase includes immutable binary state and strict codec
edits from `examples/bytes-web.nex`.

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

`--browser` additionally performs all three real locked TypeScript/Vite release builds
and checks emitted assets/maps for their server sentinels. Without this flag only
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

The current maintained workflow additionally builds a native HTTP/HTTPS service
with the selected SQLite/OpenSSL dependencies, rejects unauthenticated requests,
checks per-principal Unicode data and restarts against the same database. On
macOS, generated storage/server executables record the selected dependency
directories as runtime search paths for `@rpath` install names. Moving an SDK
after building an application requires rebuilding that application; distributing
application runtime libraries remains separate platform packaging work.

## Linux bundle assembly and clean validation (0.28, under validation)

From a matching installed Linux SDK built with the pinned Ubuntu 24.04/LLVM 22
recipe:

```sh
python3 tools/linux/bundle.py --sdk /absolute/linux-sdk --arch arm64 \
  --output /absolute/new-linux-bundle-evidence
# Use --arch amd64 for x86-64; execution is emulated on an ARM64 Docker host.
```

The helper builds separate packaging and runtime images. It does not change
`nex-linux-toolchain`. The packaging image adds pinned patchelf 0.18.0; the
runtime image has the system GCC C/C++ SDK, Python, OpenSSL CLI and external
Node/npm prerequisites, with no installed LLVM, MLIR, Z3 or Clang. Both acceptance
containers disable external network and have no source or original SDK mount.
The helper freezes the input SDK and assembler before packaging.

The bundle includes Clang/llvm-ar/LLD and Clang resources, SQLite/OpenSSL headers
(including the architecture-specific OpenSSL configuration) and all non-platform
ELF dependencies. Copied images get `$ORIGIN` RUNPATH entries; SONAME aliases are
retained and absolute DT_NEEDED entries are normalized. Each direct library
resolution must stay within the bundle. GNU glibc/loader, libstdc++/libgcc and the
GCC development headers/CRT stay part of the external platform SDK. This is a
supported-platform development bundle, not a libc-independent Linux executable.
The manifest records the build distribution, observed GLIBC/GLIBCXX requirements,
platform prerequisites and the actual patchelf version. Broader Linux distributions,
older glibc baselines and physical x86-64 execution need separate validation.

Explicit notice roots still describe unmanaged official Z3 files. `--dpkg-notices`
adds component ownership, exact package/source versions, installed copyright texts
and referenced common license texts for Debian/Ubuntu-managed files. Missing
ownership or copyright files stop assembly. Patchelf is a packaging dependency;
it is absent from the resulting SDK's runtime requirements.

After moving the bundle to a comma/Unicode/percent path, the runtime probe checks
all inventoried bytes, confirms host LLVM/MLIR/Z3/Clang and source paths are absent,
and audits actual `ldd` resolutions for compiler/tools and the generated HTTPS
server. It runs all fifteen maintained phases, including the three locked browser
builds and the text/binary-file application workflows.
The helper then creates a normalized `.tar.gz` and hash, extracts it into another
source-free container and repeats the workflow with the restored compiler.
`verification.json` retains commands, image IDs, logs and both acceptance reports.
Live LLDB is a separate verified host prerequisite; these minimal containers report
`live_debugger: false` rather than claiming debugger execution.

Native Linux executable builds now record configured SQLite/OpenSSL directories
as ELF runtime search paths, preserving literal commas, Unicode and percent signs.
A colon in such a directory is rejected because it separates ELF search entries.

Linux packaging also performs a real malformed-ELF metadata check before normal
assembly. An absolute SONAME must be rejected without creating a link outside
the output SDK; component names `.` and `..` are rejected. The validator builds
an owned metadata-only ELF fixture and does not count it as compiler evidence.

## Maintained macOS distribution workflow

With an unbundled installed SDK, the provenance/notice configuration described
above, and a populated cache for the pinned web lock:

```sh
python3 tools/macos/bundle.py --sdk /absolute/installed-sdk \
  --notices /absolute/notices.json --output /absolute/new-distribution \
  --npm-cache /absolute/npm-cache --deny-read /absolute/source-checkout \
  --deny-read /opt/homebrew --deny-read /opt/local --live
```

The helper assembles copies, moves the SDK to a temporary comma/Unicode/percent
path, then runs all fifteen acceptance phases. `sandbox-exec` denies reads from
the explicitly supplied source/dependency roots and denies writes to the SDK.
Each denied root needs a readable input/notice file for an actual negative
control; a separate control verifies SDK write denial. Node/npm/Python must be
outside the denied roots; explicit `--node`, `--npm` and `--python` paths are
available. Apple SDK/linker and host LLDB remain declared prerequisites.

The exact inventoried files and relative links are archived with normalized
owners/timestamps, then restored into another directory and checked with the
same kernel policy and complete workflow. Archive checksum, every file hash,
executable mode and link target are checked. Unexpected files, duplicate keys,
escaping paths, links through non-directories and privileged archive entries
are rejected. Regular unmanifested Python cache files are excluded. Both macOS
and Linux distribution helpers use `tools/sdk_archive.py` for this boundary.

Output includes `.tar.gz`, SHA-256 sidecar and a `nex.sdk-distribution/2` report
([schema](../llm/sdk-distribution.schema.json)). Historical distribution/1 reports
remain unchanged. Failed attempts retain their output and working directory;
new attempts require a new output directory. The helper keeps npm offline;
it does not claim blocking all external network traffic on macOS. Temporary
working evidence stays available at the path recorded in the report.


Toolchain 0.48 extends the backend-agreement phase with the indexed
`examples/operation-patches` project. It queries an exact editable operation,
deletes the materialized source, applies a source/revision-guarded replacement,
checks the retained local ID with a new site, runs native/reference/TypeScript
validation and rejects the stale patch. Both the original 41 and revised 42
outputs must remain runnable from archived sources. This was part of the original
thirteen-phase workflow and remains in the current fifteen-phase workflow; consult current evidence for the compiler/source hashes
and the platform scope actually tested.


Toolchain 0.49 adds graph schema 4 with a local HEAD-transition journal and
expected-HEAD restoration of retained, rechecked current-language source. The
upgrade retains old rows and starts an empty journal at the actual HEAD; it
does not infer unknown prior provenance. See [the history guide](history.md) for
`nex changes`, `nex restore`, declared labels, bounds and older-SDK compatibility.
The installed SDK backend-agreement scenario restores both source-deleted
operation-edit revisions and verifies their four actual transitions.

## Graph recovery acceptance (toolchain 0.50)

The toolchain0.50 installed SDK acceptance workflow introduced fourteen phases. Its new
`graph-snapshot-recovery` phase deletes the original project, moves a complete
graph snapshot and recovers into a new project. It checks every database row,
local node IDs/namespace, the HEAD journal, both retained revisions and
native/reference/TypeScript execution without physical source files. Existing
output is rejected without changing the recovered database. The language pack
indexes the snapshot guide and manifest/result schema. This phase preserves
graph state; external receipt/artifact files, application data and SDK/native
dependencies remain separate. An SDK report is evidence only when this phase
and the other requested phases actually pass.

## Declared project version acceptance (toolchain 0.51)

The current fifteen-phase workflow adds `project-version-boundaries`. It checks
that an older root declaration is rejected before creating a graph, a reachable
old configured library is rejected, current library source is accepted, archived
native/reference execution ignores stale physical metadata without moving HEAD,
and current source export checks to the same semantic revision. The matching
compatibility guide/project schema are included in discovery's resource inventory.
