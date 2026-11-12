# Qualified SDK: 0.162.0 / language 0.28 / task ABI 7

For the current source-to-archive development command, see
[one-command SDK build](sdk-build.md). Its pipeline qualification is separate
from the historical immutable SDK record below.

The [Mac ARM64 SDK record](releases/0.162.0.json) pins the immutable archive:
300 source CTest groups; 41 maintained phases and 90 additional cases on each
moved/restored installation; actual Python3.10/3.14; 4000 C++ host calls and
cleanup checks. It also records browsers, CLI composition, physical OpenCL,
Q1–Q5, packaged-Clang sanitizer controls, numerical measurements and all85 schemas.
Source/dependency/opposite-SDK reads were denied; SDK prefixes stayed read-only.

The archive remains its tested4fb860e resource snapshot. Current repository
documentation and later Windows/source-test corrections have separate identities;
the archive is not silently repacked. This commit publishes source and receipts;
the previously published binary release remains0.159. Use the current
[English](getting-started.en.md) or [Russian](getting-started.ru.md) source-build guide.
Complete matching Windows/Linux SDK delivery remains separate. Earlier workflow
versions below preserve their original scope; query the actual compiler before use.

Linux SDK assembly preserves selected SQLite/OpenSSL static archives byte for
byte, validates them with the selected native archiver, and captures their full
license provenance. Regular archives contain their object members; thin archives
that refer to external objects are rejected. ELF shared libraries retain their
dependency closure, SONAME aliases and origin-relative runtime paths. This
[packaging correction](evidence/linux-static-link-libraries-0.162.2-2026-11-09.json)
passed three actual link/move/refusal methods on both Debian ARM64 and Fedora
x86-64; it does not itself qualify a portable Linux SDK.

The [ARM64 SQLite loader fixture](evidence/cix-static-sqlite-ELF-fixture-0.162.2-2026-11-09.json)
retains dynamic-loader coverage when the selected host SQLite is a PIC static
archive: it links the real objects into an owned shared library, executes NEX
storage operations and checks the loaded library path. The original archive,
Unicode values, cache reuse and rejected invalid ELF directory remain checked.

## Native Windows acceptance adapter in development

The installed workflow selects native PE executable/DLL names, uses physical
SQLite-handle cleanup, and observes DLL load/unload mappings through Windows
debug events. Windows bundles include their selected native symbol tools and an
OpenSSL CLI with its measured PE dependency closure. These changes retain all
41 mandatory phases and preserve the Unix paths.

This adapter is under test. Development 0.162 includes operator-pinned Windows
TCP, DNS and HTTP client provider candidates with selected execution evidence.
Their complete matching SDK qualification remains in progress. Successful
compiler selection, bundle assembly or individual phases do not establish complete
Windows SDK delivery. The current compiler selection has a separate
[Windows smoke receipt](evidence/windows-current-compiler-2026-11-02.json).

DAP timeout diagnostics identify the expected event or response, adapter PID,
exit state and `dap-stderr.log`. Secondary shutdown failures are recorded in that
log while the original request failure is preserved. Request deadlines and
successful-shutdown checks remain active.

Direct C11/C++20 acceptance fixtures use the relocated SDK's selected target
and sysroot for both the selected C++ driver and its sibling `clang` C driver.
This includes the source-resource producers; system headers must come from the
selected SDK rather than the original compiler installation.
The standalone source-resource debugger and dependent-resource checks use the
same selected driver and sysroot; their child processes do not rely on an
ambient C/C++ compiler on `PATH`.

Retained provider acceptance compares absolute paths using the host's path rules
and the actual filesystem identity. This accepts mixed Windows separators without
accepting another file or an outside hard link. Portable relative inventory names,
ordered completion inputs, compiler-issued BLAKE3 pins, independent SHA256/byte
checks and source-deleted replay remain checked. Executable records use `app.exe`
on Windows. The earlier failed complete workflow is preserved; this correction
requires a newly assembled SDK and fresh complete acceptance.

Provider symbol checks use the selected `llvm-nm` and the actual PE import
directory from `llvm-readobj`. A Windows import jump thunk is not a runtime
implementation; actual local kernel/main/continuation definitions remain
forbidden. Windows leading underscores are preserved; Mach-O removes its single
ABI prefix. Captured command artifacts use native absolute paths, while retained
inventory members keep their portable relative-path checks. PE closure DLLs are
adjacent to the executable; Unix owned images use `images/`, as recorded by the
compiler's completion metadata. These development helper corrections still need
their matching newly assembled SDK acceptance.
Copied PE closures use the declared image list and verify native file identity
and SHA256 before copying. The native regression executes a moved two-DLL call
after deleting the original DLLs/import libraries and rejects a changed hash
before writing any copied image. Unix retains its `images/` tree layout.
The [scoped helper receipt](evidence/windows-macos-SDK-provider-helpers-0.162.2-2026-11-09.json)
records all four provider actions on Windows and macOS, actual PE controls and
the95-method SDK suite on both hosts. It pins each host's exact helper snapshot
and original SDK archive; complete matching SDK delivery remains separate.

The [coherent Windows HTTP receipt](evidence/windows-coherent-http-0.162.2-2026-11-08.json)
records 29 source cases in reference/Debug/Release, 18 delivery rejections,
three complete 15-case stream groups and source-deleted HTTP/HTTPS2 packages.
It rehashes the original compiler, full source snapshot and selected dependency
libraries. The receipt excludes positive IPv6 and complete portable SDK acceptance.

### Explicit profile for a Windows host that intentionally denies IPv6

The default `--network-profile full` retains all 41 current SDK phases and
requires successful IPv6 TCP execution in the reference interpreter and native
Debug/Release programs. A networking policy that blocks IPv6 must not be changed
or treated as a successful IPv6 execution to obtain a green receipt.

On native x86-64 Windows with toolchain 0.162+, an operator can explicitly select:

```powershell
python C:\NEX\share\nex\tools\sdk_acceptance.py C:\NEX --output C:\NEX-check --browser --live --network-profile windows-ipv6-denied
```

This profile keeps all 41 phases and the TCP delivery checks. It executes every
other TCP source case in all three modes: 33 comparisons, plus three explicit
IPv6-denial comparisons. Before each denial comparison, a real native Python
socket must receive Windows error 10013 against the same listening `::1` peer;
NEX must return `E_NETWORK`, accept no peer connection and retire its resources.
A successful connection, refusal, timeout or another error fails this profile.
No policy detection automatically selects the profile, and the tooling changes
no network settings.

Reports carry `network_profile` and `network_scope`, with
`positive_TCP_IPv6_accepted: false` for the denial profile. The normal
`validate_completed_report(report)` rejects such a receipt. A distribution
validator must deliberately pass
`expected_network_profile='windows-ipv6-denied'` to validate that scope; relabelling
or stripping the profile cannot replace the missing positive IPv6 evidence.
Older full receipts keep their original contract.

The profile is a development adapter, not a completed Windows SDK qualification.
Installed workflow success still requires separate matching build, archive,
relocation and filesystem-isolation evidence. Full positive IPv6 acceptance
remains pending on a Windows host where IPv6 is permitted.

# Development0.136.0 / language0.25 SDK candidate

Current development0.151 selects language0.27. Its installed acceptance adds a
mandatory `typed-source-errors` phase: ordinary typed CLI/native/TypeScript and
scalar Wasm execution, rejected programs, genuine026 migration, all16-table
history preservation, source-absent snapshot recovery and explicit export.
There are40 required phases for this version. Earlier SDKs keep their original
phase and ABI families. These are acceptance requirements; the current installed
SDK and full platform workflow have not yet passed them.

The current workflow requires **39 phases**, including `source-exceptions`.
It checks source-error delivery from joined children, uncaught errors, preserved
rethrow locations, checked-trap separation, effect rejection and native profile
cleanup alongside the existing native/browser/graph/provider workflows.
ABI6 provider records use schemas11/12/13. New acceptance projects use the actual
compiler language; historical stores retain their original rows and manifests.
A migration that needs task delivery effects uses an explicit checked candidate.

Run the complete installed workflow in a fresh output directory:

```sh
python3 /chosen/sdk/share/nex/tools/sdk_acceptance.py /chosen/sdk --output /new/evidence --browser --live
```

This is a development candidate. Independent phase checks do not establish full
SDK, relocation, archive or platform acceptance. The older sections below retain
their stated version scopes. Query `nex describe --kind index --json` and
`nex doctor --json` for the compiler actually installed.

Toolchain0.135.1 adds a mandatory38th installed acceptance phase,
`structured-task-tcp`. It runs the installed pinned-provider source and delivery
helpers:36 actual AST/debug/release socket cases,22 target-policy rejections,
18 authority/pin/integrity rejections, client pruning and moved source-deleted
package execution. Reports and actual helper/compiler hashes must match. This
phase does not replace the earlier37 gates. Toolchain0.134.4..0.135.0 receipts
retain their37-phase contract. See [the TCP guide](tcp-provider.md). Complete
matching current SDK and distribution acceptance remains pending.

# Development0.133.3: SDK migration acceptance correction

The SDK019-history gate now keeps current language separate from each migrated
revision hash. Language/revision/namespace/16-table assertions remain strict.
This is a Python acceptance correction; compiler/runtime/TypeScript/grammar and
language-pack bytes match frozen169. Public023 and private024 scopes are unchanged.
Actual CLI gate and complete installed SDK acceptance are separate requirements.

# Installed SDK acceptance and handoff

The current0.122 candidate workflow has33 phases, adding `model-contract` after
the0.121 compute phase. It checks the installed public model import, finite F32
bytes, native/reference/TypeScript observations, managed cleanup, installed
provider preparation files, archived replay with physical standard library files
absent, and standalone execution with compiler resources unavailable. This is
library delivery; native model inference keeps its separate provider/device gates.
The exact0.121 local checkpoint passed32 phases/584 commands. Matching0.122 full
regression, installed SDK and platform receipts remain pending.

The preserved0.119 workflow has31 phases, including `task-provider-debugging`.
The preceding0.118/125b installed checkpoint passed30 phases/557 commands;
that receipt does not certify the current compiler. The new phase verifies
static/shared debug artifacts, immutable completion7, source-deleted capture,
package and replay. With `--live`, actual LLDB-backed NEX-DAP sessions inspect
provider locals/pure watches, next/in/out, stale references and graceful exit.
Full delivery requires a completed report for the exact compiler and resources.
The separate opt-in [Q1–Q5 quality pack](../experiments/quality/README.md) does
not add phases to this SDK workflow.

For first installation, application creation, Git versioning and Hermes/Codex
setup, use the Russian [quickstart](quickstart.md). This page describes SDK
validation and packaging in more detail.

Install the compiler and its matching resources after building NEX:

```sh
cmake --install build --prefix /absolute/nex-sdk
python3 /absolute/nex-sdk/share/nex/tools/sdk_acceptance.py /absolute/nex-sdk \
  --output /absolute/new-evidence --browser --live
```

For private compiler runtime libraries, add `--package-notices FILE` containing
operator `nex.sdk-notices/1` components with their full local license texts.
Acceptance merges these with its application/foreign fixture notices; only
components actually used by each package are copied.
The same explicit catalogue is forwarded to the public file-write delivery
subprocess, which packages static, shared and mixed task-provider applications.
That subprocess records the catalogue path/hash and requires it to remain
unchanged; the SDK report verifies that it received the selected catalogue.
For a standalone invocation, pass `--package-notices FILE` to
`share/nex/tests/task_write_delivery.py` together with its compiler/resources.
The packaging command still rejects an undeclared private runtime dependency.

The output directory must be new or empty. The script never replaces previous
evidence and never imports files from the compiler's source checkout. It sets
`NEX_RESOURCE_DIR` to this SDK, verifies the selected runtime and matching
language-pack version, inventories every indexed text resource, and queries the
installed guides, including the experimental Wasm guide. Python 3.10+, the SDK's development dependencies
(LLVM/MLIR, Clang, platform SDK, SQLite/OpenSSL, Z3 and Node.js) remain required. The maintained HTTPS check also uses the `openssl` CLI. On Linux, its application-packaging phase additionally requires `patchelf`, `readelf` and `ldd`; these are development/packaging tools rather than generated-application dependencies.
The text-file phase checks explicit capability/read-only denial, native/reference
Unicode/NUL agreement, source-deleted replay and a packaged file application
executed with compiler resources unavailable. File access requires no SQLite or
JSON runtime. Its report distinguishes assembly from actual execution.
This is an installed-development-chain check, not a portable SDK bundle.

Both SDK assembly and acceptance reject older Python versions before inspecting
the selected SDK or creating output. The compiler and generated native programs
do not require Python for ordinary execution.

The0.114 candidate adds a twenty-sixth phase, `structured-task-profile`.
It requires the matching native task profiler descriptor, exact source-call
counts across suspension, balanced shallow managed pools and explicit event-only
timeline loss. It also exercises an archived revision after deleting sources,
a copied instrumented executable with compiler resources unavailable, source-only
project limits and reviewed profile capture/replay after deleting the project.
This candidate workflow is under integration; its existence does not establish a
passed SDK gate. Each accepted receipt identifies its actual toolchain and phases.

The 0.60 workflow has twenty-three phases. Its `wasm-compute` phase requires
LLVM 22.1 Clang and `wasm-ld` and current Node.js. It checks exact BigInt results,
checked overflow and operation attribution, input rejection, bounded loops,
post-trap recovery, module integrity, cache repair, server-code exclusion and
archived export after source deletion. The exported modules then execute with
compiler resources unavailable. Independent execution uses a byte-verified
temporary copy when necessary for Node's handling of literal backslashes in
POSIX module paths. The exported evidence remains in the report directory.
The SDK scenario does not run an actual browser for Wasm; use the separate
`tests/wasm_browser.py` three-engine scenario in the source checkout.

When a configured Wasm linker exists, the SDK packager copies it and records an
optional relative `wasm_linker` in `sdk-host.json`. A descriptor without that
field leaves this experimental target unavailable; it never falls back to the
original build-machine linker. Include the linker's upstream notices and all
non-system dependencies in the packaging inventory. `NEX_WASM_LD` explicitly
overrides linker selection in a trusted development environment.

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

If the compiler has no configured Wasm linker, set `NEX_WASM_LD` to an executable
LLVM22.1 `wasm-ld` when assembling the bundle. The packager validates its actual
version and captures its bytes/notices under the relative SDK host descriptor;
an empty, missing or incompatible explicit override fails before copying the
SDK. The maintained macOS distribution helper clears this assembly override
before checking moved/restored copies, which must select the bundled linker.

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
On Linux, explicit invocation through a dynamic loader still discovers the
compiler image's own prefix for resources, `sdk-host.json` and compiler paths
passed to helpers. The loader's prefix does not select a different SDK. This
does not supply missing GNU runtime libraries, target headers/CRT or establish
compatibility with an older distribution; those require separate qualification.
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

The 0.57 workflow has twenty-one phases. Its foreign-boundary phase compiles a
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

Server debug preparation still builds and checks the actual shared provider and
invokes the editor's production preparation code. Starting with 0.162, a host
without `lldb-dap` can complete the non-live workflow only when that editor
reports its exact missing-backend error. The receipt records the real command,
exit status, diagnostic and editor resource hashes, Python presence and backend
absence; `editor_preparation` and all live execution fields remain false.
`--live` requires the backend and successful preparation and cannot accept this
refusal. Build failures and other editor errors still fail either workflow.
Server and ordinary shared-library projects use the same checked preparation
path. Each unavailable-backend refusal has its own actual Node command; a shared
project cannot reuse the server's refusal as evidence. Project receipts retain
the checked native binary dependencies even when editor preparation is unavailable.

Captured fatal diagnostics from direct LLDB, LLDB-DAP or lldb-server commands
fail the installed workflow and private HTTP debugger checks even if the parent
returns zero. Both runners retain the original exit code and captured stderr;
ordinary command errors keep their existing expected-result checks.
The installed DAP client applies the same rule during shutdown, preserving an
earlier request error and logging the fatal shutdown diagnostic alongside it.

The installed native stream-host fixture executes 27 physical scenarios on
macOS/Linux and 26 on Windows. Its POSIX child-only `RLIMIT_FSIZE` partial-write
scenario is excluded from the Windows C++ fixture. The Windows 0.162 receipt
therefore records `actual_partial_write: false`, `portable_corpus_complete:
false` and that exact pending case. Every other scenario remains required.
This scoped Windows receipt cannot satisfy a macOS/Linux or historical full
27-case gate, and does not establish physical partial-write handling on Windows.

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
directories as runtime search paths for `@rpath` install names. The same selection applies to source foreign calls. Independent C++ FFI hosts
need both the full `native_openssl_crypto` path reported by `nex doctor --json`
and its parent as separate compiler operands: `-Xlinker -rpath -Xlinker PATH`.
This preserves literal commas, quotes, backslashes and UTF-8. Moving an SDK
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
resolution must stay within the bundle. GNU glibc/loader and GCC development
headers/CRT stay part of the external platform SDK. libstdc++/libgcc resolved
from OS library directories remain external; private compiler copies are
captured with their component notices. This is a
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
server. It runs all eighteen maintained phases, including the three locked browser
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

The deny-read roots must cover the **input SDK** and every copied host-component
source. An empty list is rejected before relocation.
```

The helper assembles copies, moves the SDK to a temporary comma/Unicode/percent
path, then runs every phase in the matching SDK contract. `sandbox-exec` denies reads from
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
thirteen-phase workflow and remains in the current eighteen-phase workflow; consult current evidence for the compiler/source hashes
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

The toolchain 0.51 fifteen-phase workflow added `project-version-boundaries`. It checks
that an older root declaration is rejected before creating a graph, a reachable
old configured library is rejected, current library source is accepted, archived
native/reference execution ignores stale physical metadata without moving HEAD,
and current source export checks to the same semantic revision. The matching
compatibility guide/project schema are included in discovery's resource inventory.

## Captured frontend error acceptance (toolchain 0.52)

The toolchain 0.52 sixteen-phase workflow added `frontend-diagnostics`. A rejected
assembled candidate must expose its own source preview/hash, repeatable error
identity and unchanged physical source/history. Invalid UTF-8 input is returned
losslessly as base64, a static expression error carries supplied frame/build
identity, and a corrected candidate executes from its retained archive. These
are compiler-input references, not authenticated authors or committed operation
UUIDs. Discovery includes the matching frontend guide/schema.

## Archived graph-query acceptance (toolchain 0.53)

The toolchain 0.53 seventeen-phase workflow added `graph-queries`. It discovers a
checked function, traverses dependencies and incoming references, pages a pinned
selection without duplicate/missing IDs, and requests full context. The same
queries work after source deletion and with stale physical language metadata,
without moving HEAD/history. A discovered ID/name and exact whole-bundle guard
then feed an atomic repair, verified by archived native/reference execution.
This connects discovery to the existing development chain; a static subgraph
does not prove dynamic test coverage or complete requirement satisfaction.

## Stopped-string acceptance (toolchain 0.54)

The current eighteen-phase workflow adds `string-ranges`. A supplied partial
frame demonstrates scalar length, exact bounded windows, contained-window reuse
and explicit missing-range demands. With --live, an actual4MiB native UTF-8
string is streamed without inferior calls, a bounded window is recorded at an
unchanged stop/handle, and its last character is replayed after source deletion.
Supplied data and live recordings stay distinct in the report; these checks
preserve graph history and do not claim direct DAP root paging or all layouts.

## Editor sources and acceptance in0.56

The installed development SDK contains share/nex/editor/vscode, its separate
pinned npm development lock, focused Node contract cases and the editor guide.
The twentieth installed acceptance phase runs those cases without installing
npm packages. With --live it also uses the installed compiler to prepare a
frozen native debug session and verify byte-checked original-file mapping.
This is not a VS Code extension-host run. Actual installed VSIX/IDE acceptance
is recorded separately. See editor.md for explicit packaging and installation;
NEX never publishes or installs the extension automatically.

## Matching workflow contract (toolchain 0.56.1)

`tools/sdk_acceptance.py` exports the ordered twenty-phase contract and a
terminal-report validator. macOS and Linux portable bundle checks import that
matching installed helper, including editor tools, graph recovery/version/error
checks, graph queries, string ranges and source traits. The workflow checks its
action registration before running. A historical twelve-phase report cannot
satisfy current acceptance. Missing/duplicate/reordered/incomplete phases or
failed commands fail the contract. Expected rejected programs and native traps
can have nonzero exit codes; their explicit expected outcomes must pass.

Source language 0.16 and runtime/canonical formats are unchanged. This repair
has focused archive/contract checks; actual current relocated/restored SDK
acceptance is recorded separately in STATUS.md. Retain matching historical SDK
scripts with their old archives instead of applying a new contract retroactively.

## Native indexed page acceptance (0.57)

The native-indexed-pages phase requires the compiled capability descriptor and
the installed list/byte example. With --live it launches the matching NEX DAP
bridge, opens the last two children of a32768-item list and4MiB byte root, checks
indexed/named filters, and bounds both omitted and oversized requests to1000
children. Exact pure watches before and after paging must retain the same stop.
The application resumes with exit0 and old handles must be rejected. Without
--live the report explicitly leaves live_dap_pages false; it does not claim a
native process interaction. The matching distribution validators require all21
phases in order, including this one.
Development0.98.1 fixes acceptance of explicitly reviewed private runtime notices.
The acceptance runner uses matching `--package-notices` entries before automatic
Debian ownership lookup, retains all supplied entries in captured package tasks,
and supplies them to project packaging. Identical relocated license texts can
deduplicate; conflicting versions, roots or license bytes for one component name
fail explicitly. This changes the validation workflow, not source language,
compiler/runtime ABI or migration. Original0.94 Astra failures remain retained.


Development0.100 also copies every reviewed license into the owned project
before computing task notice pins. External library roots keep their reviewed
identity; complete license bytes are captured within project bounds. This fixes
a real last-phase installed102 acceptance failure with --package-notices.
A separate reviewed corrected driver passes24phases/427commands on the exact
installed102 compiler; the original102 driver remains unchanged. Matching
installed acceptance of this source must still be run.


Toolchain0.117 adds the29th installed workflow phase, `shared-task-providers`.
It discovers the distinct shared-fixed descriptor, builds real checked provider
images, verifies defined accessors/component ownership and executes the loader
with exactly one common runtime. It separates unused read-code support from the
root grant, captures ordered completion5 raw pins and original bytes, verifies
package provenance against relocated image SHA256, deletes source/cache and
executes both copied and packaged closures with loader tracing before replay.
The phase body alone is a scoped proof; full matching installedSDK29 acceptance
and supported platform gates are separately recorded. Static123's phase and
provider1/completion4 contract remain required and unchanged.
# Public task HTTP/TLS delivery (SDK0.134.4)

The matching SDK workflow requires37 ordered phases, including
`structured-task-http`. It executes the installed, indexed
`tests/task_http_server.py` helper with the actual installed compiler. The
helper builds debug/release task servers and retains148 checks,50 HTTP request
outcomes,14 clean server exits, verified HTTPS certificates and exact
E_CANCELLED diagnostics after real disconnects with an opened File. Compiler,
helper, image and metadata hashes bind this evidence to the SDK. Native/AST
Unicode and NUL behavior, authenticated principals, file grants, path limits,
compiled ceilings, runtime control and source-absent app execution are checked.

`validate_completed_report` keeps the older34/35/36-phase contracts for their
original toolchains;0.134.0..0.134.3 still require36. A0.134.4 receipt cannot
omit the37th phase, its declared phase list, indexed helper or actual request/
cleanup evidence. Passing the isolated HTTP receipt check does not bypass any
other SDK requirement. Archive/moved SDK, supported platform and whole-project
acceptance remain separate. App-source absence is distinct from compiler-source
fallback absence: promotion tests temporarily hide the exact compiled source
prefix and pass it to `--forbid-source` throughout the installed workflow.

The source/runtime implementation is unchanged from the188 HTTP cohort. This
delivery update installs/indexes its extended helper and strengthens SDK receipt
validation. It adds no source syntax, language migration, dependency or notice.

The maintained macOS and Linux distribution wrappers give each moved/restored full SDK
workflow a bounded18000-second budget. Its summary counts the phases in the
actually validated receipt, including37 for0.134.4, rather than the historical
34-phase base tuple. Individual SDK operations retain their own shorter limits;
this wrapper does not relax any receipt or isolation check.

The positive FFI capture/replay source fixtures allow300 seconds for a cold
build,180 for the profiling check and900 for their parent watchdog on all hosts.
The [ARM64 measurement](evidence/cix-FFI-cold-compilation-0.162.2-2026-11-09.json)
records90.5 seconds for release compilation and101.2 for the profile command,
with3.06ms of measured program execution. The original60-second failures remain
recorded. This changes fixture budgets, not compiler defaults; the intentional
five-second native timeout/interruption cases and their cleanup assertions are
unchanged. Acceptance of the entire updated FFI group is recorded separately.
The [complete ARM64 FFI group](evidence/cix-FFI-full12-0.162.2-2026-11-09.json)
passed all12 methods without skips in1640 seconds under the original1800-second
CTest limit, including source-deleted replay, exact8192-file capture, tampering,
timeout/interruption and native descendant cleanup. This remains a scoped source
result rather than complete Linux SDK acceptance.

The Linux verifier keeps its600-second limit for individual inspection tools.
The complete maintained workflow uses the18000-second aggregate limit, including
all41 phases in0.162; native task deadlines and DAP response limits are unchanged.

Failed source-test fixtures retain their owned temporary parent, including moved
replay inputs and sibling packages, when a test removes its nested project root.
The Windows oversized-core fixture sets a sparse logical EOF directly; it does
not extend the file through the CRT's zero-writing truncate path. The concurrent
storage host reports worker exception codes and still exits unsuccessfully;
its transaction counts and the runtime's1000-ms busy timeout remain unchanged.
Source HTTP/debugger commands capture pipe bytes before decoding UTF-8 text.
Timeouts save partial stdout/stderr before reraising the original process error;
interrupted UTF-8 tails remain diagnostic text, and normal text/newline behavior
is unchanged.


### Read-only standard-library replay acceptance

The model-contract gate never renames files in the installed SDK. It copies its
text resources into the writable evidence project and removes model.nex and
compute.nex only from that private projection. NEX_RESOURCE_DIR explicitly selects
that projection; doctor must identify its runtime, and fresh imports of each
missing standard library must fail with E_RESOURCE. The original project source
and native build cache are removed, then the archived revision must rebuild
without a cache hit and agree in reference and native execution. A copied
standalone binary also runs with resources unavailable. The receipt records the
projection, both negative controls, selected runtime and unchanged installed
library hashes. Existing full phase, resource inventory and kernel write-denial
checks remain mandatory. This gate establishes library replay, not native model
inference or general GPU/NPU execution.

### C/C++ producer paths in relocated SDKs

On Windows the native driver and sysroot occupy separate SDK paths. Ordinary
NEX builds select both through the SDK descriptor. Direct C/C++ host builds use
`doctor.native_compiler` with `--target=<doctor.host>` and
`--sysroot=<doctor.native_sysroot>`, together with the selected link dependencies.
The acceptance helper supplies these defaults for its selected native driver.
A regression compiles a private header available only inside the moved sysroot,
links C11 and C++20 code, deletes their sources and runs the resulting program.

Deployed-program checks retain the required Windows OS environment, including
`SystemRoot`, existing `TEMP`/`TMP` and a System32-only `PATH`. SDK and developer
search paths remain absent. This also gives the foreign loader its normal
writable OS temporary directory after the original project has been removed.

The installed source-resource and debugger gates encode marker paths as UTF-8
bytes in fixed-width C octal escapes. JSON string encoding is not a C literal
encoder: non-BMP characters become surrogate pairs which Clang rejects, and
control characters can also produce invalid universal characters. The native
regression compiles and runs both C11 and C++20 probes and checks the exact
filesystem path containing emoji, quotes, a backslash, newline, tab and a digit
after non-ASCII bytes. Paths are separate argv values, never shell fragments.
SDK read/write isolation and all existing resource lifetime checks remain in
force; this fixes producer preparation rather than changing NEX semantics.
# Public025 integration gates

The025 candidate adds an installed source-error check:

```sh
python3 /sdk/share/nex/tools/sdk_source_exceptions.py /sdk --output /new/exception-evidence
```

It executes caught child errors, native debug/release, TypeScript, original
rethrow payload/site, uncatchable runtime traps, missing-effect rejection and
managed cleanup after caught/uncaught native profiles. Success covers this gate;
the report explicitly keeps full_SDK_accepted=false. The complete025 acceptance
workflow additionally requires its versioned provider, file/network, debugger,
browser and platform gates. Retained024 provider families keep ABI5 and their
original record schemas;025 uses ABI6 and record families11/12/13.



### Static vendor provenance in Windows applications

Windows native builds record SHA-256 and byte counts for the selected SQLite
and OpenSSL static archives in the completed build metadata. Application
packaging verifies those same inputs before collecting their explicit component
licenses, even though a PE import table cannot name statically linked code.
`application.json` records the archive names, hashes, sizes and license component
without retaining local source paths. Relocated SDK archives also remain subject
to the SDK inventory hash check. A changed archive or missing component license
rejects packaging.

### Native Windows CUDA helpers

CMake installs the CUDA provider sources and `prepare.py`, `verify.py`,
`memcheck.py` in `share/nex/tools/owned-cuda`, next to the shared owned-opencl
corpus. Installed preparation discovers `bin/nex.exe` from that SDK, without
a source-tree fallback. The moved Windows SDK was checked with System32-only
PATH, explicit Python, native EXE/static/Wasm/packages, all four game batch
launchers, all 35 physical CUDA cases and memcheck with local Named Pipes.
See the [scoped receipt](evidence/windows-sdk-2026-11-01.json). These checks do
not substitute for the complete maintained 40-phase distribution workflow.
