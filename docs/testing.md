# Development test layers

CTest labels select an explicit development scope. The full unfiltered registry
remains the milestone/release gate. Language/backend changes still need the
affected observable-semantics and rejected-program checks.

## Fast compiler loop

Configure the source build using the [README dependencies](../README.md#build-and-use),
then build only the existing compiler and probes required by the small core set:

```sh
cmake --build build --target nex_core_tests -j 4
ctest --test-dir build -L '^core$' -j 1 --output-on-failure
```

The [development presets](development-build.md) also provide
`cmake --workflow --preset dev-core` for configure/build/core-test orchestration.
The [CI receipt runner](ci.md) also saves and validates the actual registry,
JUnit, exit code and logs for core/full selections.

The selected12 groups cover frontend checking, typed reference evaluation,
checked float/byte runtimes, discovery/language-pack contracts and offline tool
accounting/collection/CTest metadata and compiled diagnostic explanations. They require Python3.10+, the configured
compiler and its selected native dependencies. They require no Node/npm, browser
installation, model inference, SDK packaging or device access. Collector controls
in this layer use a synthetic provider.

## Select a broader scope

```sh
ctest --test-dir build --show-only=json-v1 > /new/registry.json
python3 tools/ctest_tiers.py --registry /new/registry.json --output /new/tiers.json
ctest --test-dir build -L '^browser$' --output-on-failure
ctest --test-dir build -L '^platform$' --output-on-failure
ctest --test-dir build -L '^sdk$' --output-on-failure
ctest --test-dir build -L '^scale$' --output-on-failure
```

| Label | Scope | Additional dependencies |
| --- | --- | --- |
| `core` | Explicit small compiler/tool baseline | Selected build and Python |
| `extended` | Other semantic and integration groups | Per-group contracts |
| `browser` | TypeScript/WebAssembly/browser integration and related source/descriptor checks | Execution groups use Node22.18+, TypeScript and locked web packages; production-browser checks also need their browser runtime |
| `platform` | Native runtime, loaders, files, network, debugger and OS/architecture integration | Selected native compiler/linker/SDK and the group's platform tools |
| `sdk` | Installed delivery, packages, archives, provider preparation and notices | Selected package/dependency cohort and required notices |
| `scale` | Stress/workload coverage or groups with a declared timeout of at least900 seconds | Per-group CPU/memory/time budgets |

Each group has exactly one base label (`core` or `extended`). Area labels overlap;
they are not a partition or a completion claim. Some browser-labelled groups only
inspect adapter/source contracts. CMake keeps existing platform conditions: a
catalogue entry for a Windows/Linux group does not enable it on another host.
CTest may add fixture setup/cleanup groups outside an area selection. The tier
inventory reports that closure using the existing [JUnit/fixture verifier](ctest-results.md).
Core rejects any added fixture group.

The earlier11-group core command passed in **12.36 seconds** on the development
Mac (one sequential CTest observation, toolchain0.165.0/language0.28). Its
selected PATH/NEX_NODE/NEX_TSC guard observed no Node/npm/npx/tsc requests, and
the complete318-group registry retained every earlier command and non-label
property. See the [scoped evidence](evidence/test-tiers-0.165.0-2026-11-11.json). This is a host observation, not a universal timing guarantee.
Other whole-layer wall times remain
unmeasured on the current source until the agreed full milestone. Inventory
reports declared timeout sums separately; those are upper budgets, not runtime
measurements. Historical timings retain their own source/hardware scope.

The later CI block added the extended `ci_ctest_receipts` group:319 groups were
registered on this Mac, with all318 earlier commands/properties preserved. Its
three methods execute small real CTest projects, including failure and skip
controls. The new receipt path also ran all11 real core groups in13.61s;
[local CI evidence](evidence/ci-workflows-0.165.0-2026-11-11.json) retains that
separate observation. It does not claim a GitHub or Linux container execution.

Toolchain0.166 added `diagnostic_catalogue` to core and the separate
`llm_quick_reference` integration group:322 groups were registered at that block.
One sequential12-group core workflow passed in20.78s, including receipt validation.
After correcting a JSON context-advice flag, the two affected new groups passed
again. The quick example compares reference/native Debug/Release, executes
TypeScript and passes the locked7.0.2 strict compiler. These are focused source
observations, not complete SDK or platform qualification.

Toolchain0.167 adds the `standard_library` group (323 registered on this Mac,
328 explicit catalogue entries including conditional groups). Its focused source
checks cover text/list/math semantics and the matching SDK consumption helper;
the latter does not qualify a whole SDK. Core remains12 groups, with one0.167
workflow observation of20.58s. The library guide reports copy complexity separately
from runtime benchmarks.

Toolchain 0.168 adds the extended/browser/platform `source_formatting` group:
324 groups registered on this Mac and 329 explicit catalogue entries including
conditional groups. Its seven methods passed in 15.104 s, including unchanged
graph rows/revision and reference/native Debug/Release/strict executed TypeScript.
The same source's 12 core groups passed in 29.03 s. These are single local
observations; no full layer, SDK or additional platform was qualified.
The [scoped receipt](evidence/source-formatting-0.168.0-2026-11-11.json)
pins the implementation, binary, original failure and later successful reports.

Toolchain 0.169 adds the extended/platform `cli_interface` group: 325 groups on
this Mac and 330 explicit catalogue entries including conditional groups. Its
six methods passed in 15.248 s, the affected formatter's seven methods in 9.310 s
and the unchanged 12-group core in 22.78 s. Bash 3.2.57/5.3.9 and zsh 5.9
callbacks executed; generated fish/PowerShell adapters have no execution claim.
The original failed attempt and later metadata refinements remain separate.
See the [CLI receipt](evidence/cli-interface-0.169.0-2026-11-11.json) for exact
source/binary identities, shell observations and limits.

Toolchain 0.170 adds `list_construction` (326 registered Mac groups, 331 explicit
catalogue entries). Eight constructor methods passed in 58.020 s, two additional
Result/task-budget methods in 45.076 s, six affected standard-library methods in
44.066 s and 12 core groups in 22.84 s. Reference/native Debug/Release and strict
executed TypeScript cover values/effects/suspension. Native profile reports show
balanced managed allocation/free counts after checked and task-budget exits.
The lexical-shadow regression has a retained failing witness and a passing fix.
Earlier test-driver/fixture errors remain separate; no whole platform/SDK claim
follows from this focused source block.

Toolchain 0.171 adds `text_construction` (327 registered Mac groups). Seven
constructor methods passed in 66.22 s on the final binary; the affected list and
standard-library groups passed in 110.93 s and 46.31 s, and the unchanged
12-group core in 22.81 s. Reference/native Debug/Release and strict executed
TypeScript cover count/map/filter/state forms, empty and 20,000-piece inputs,
generic references, effect order, typed source errors and finally, task
suspension, lexical-shadow hygiene and partial native cleanup. The compiled
language pack checked 3596 JSON values across 64 shared fields, and the new forms
are rejected by retired source languages. This is one focused source block, not a
full regression, installed-SDK or platform qualification.

Toolchain 0.172 adds `bytes_construction` (328 registered Mac groups). Seven
byte-constructor methods passed in 61.78 s; the affected text-constructor, list
and standard-library groups passed in 61.98 s, 112.95 s and 48.36 s, and the
unchanged 12-group core in 23.32 s. Reference/native
Debug/Release and strict executed TypeScript cover all four forms, empty and
20,000-octet inputs, generic references, effect order, typed errors and finally,
task suspension, lexical-shadow hygiene, `E_RANGE` for invalid octets and partial
native cleanup. The compiled language pack checked 3633 JSON values across 65

Toolchain 0.173 adds `docs_index` (329 registered Mac groups). The generated
index covers 174 documents and checks 1209 local links with zero missing targets;
eight current contracts and one deferred document are version-checked against
the compiler, and `STATUS.current.md` is regenerated/checked by the same test.

Toolchain 0.174 adds `backend_agreement` and `agreement_generator` (331 groups).
The 12-case corpus (8 valid, 2 rejected, 2 trap) passed in 55.00 s across the
reference interpreter, native Debug/Release and executed/strict TypeScript. The
generator reproduced three byte-identical corpora for one seed, rejected a
different seed's corpus identity and ran its generated programs in 15.55 s.
`docs_index` passed in 0.09 s and the unchanged 12-group core in 22.63 s. This is
a bounded semantic smoke matrix, not proof of language equivalence or full

Toolchain 0.175 adds `bench_command` (332 registered Mac groups). The command
builds one native executable, checks deterministic stdout and reports
min/median/mean/max process wall time, exit codes, stdout hash, build key, source
revision and host/CPU identity; an earlier `nex.bench/1` report supplies
`delta_seconds` and `ratio`. The command test passed in 3.86 s and the unchanged
12-group core in 23.60 s. Only runtime measurement is implemented; cold/warm/edit
build timing, cross-host normalization and statistical significance remain

Toolchain 0.176 adds `fix_command` (333 registered Mac groups). `E_NAME` and
`E_FIELD` diagnostics carry a unique checked `nex.fix/1` interval when a close
visible identifier exists; preview, apply, unavailable-fix and rollback paths
passed in 0.54 s, and the unchanged 12-group core in 23.94 s. Applying a fix
rechecks the whole file and restores the original bytes on rejection. Other
diagnostic families, multi-fix batches and editor protocols remain pending.

Toolchain 0.177 moves test targets and CTest registrations into
`cmake/Tests.cmake` and makes the top-level `VERSION` file the single toolchain
version source. `CMakeLists.txt` is 160 lines, `cmake/Tests.cmake` is 1639; the
registry remains 333 groups. A full all-target build succeeded, the focused
version/docs/agreement/bench/fix/sdk tests passed in 5.51 s and the unchanged
12-group core in 23.26 s. Test semantics, language 0.28 and canonical identities
are unchanged; further build-logic module splitting remains possible but is not

A local 0.177 macOS ARM64 Release smoke installed the current `bin/nex` and
`share/nex`, initialized/checked/tested/evaluated/ran a fresh application,
moved the SDK, created an 11 MB archive and restored it to a third path. The
installed runtime path followed each move and all app commands stayed green.
This is an install/move/archive/restore smoke, not the maintained `sdk_build.py`
sequence, full CTest, source-free/denied-read acceptance, live debugging or a
portable platform matrix.

Windows x86-64 also built the exact 0.178 source with LLVM/MLIR 22.1.8 and ran
the fresh app plus the map/set example natively (`containers-example-ok`,
`std::map::map_test`/`std::set::set_test` native). The Windows sysroot's
`include` junction was replaced by a copied directory before the toolchain was
accepted. Full Windows CTest, web, CUDA/NPU lowering and SDK qualification were
not run.

Toolchain 0.178 adds checked source `std/map.nex` and `std/set.nex`: immutable,
insertion-ordered, list-backed `Map<K,V>`/`Set<T>` with O(n) lookup/update.
`containers` passed its checker, reference/native and TypeScript paths in 7.43 s
on macOS; the pinned `standard_library` workflow passed in 44.90 s and the
unchanged 12-group core in 21.76 s. Descriptor hashes pin both sources. Hash/balanced-tree containers and
effect-polymorphic named signatures remain pending.

Toolchain 0.179 accepts LLVM/MLIR 22.1.x and 23.1.x plus OpenSSL 3 and 4. On
Fedora 45 x86-64 the exact `9bfba2a` source built with LLVM/MLIR 23.1.4 and
OpenSSL 4.0.3 without source patches: core 12/12 in 11.56 s, fresh app
check/test/native run and map/set containers all passed. macOS LLVM 22.1.8 /
OpenSSL 3.6.3 remains green. Full Linux CTest/SDK and GPU/NPU/web matrices
remain pending.

Toolchain 0.180 adds inferred effect parameters on named generic functions:
`fn f<T,U>(..., cb: fn(T)->U !{?E}) -> U !{?E}` infers `?E` from each callable
argument, unions repeated uses and requires the caller to declare the result.
`std/list.map/filter/fold` now accept `io` callbacks while pure callbacks keep
the empty set. The focused checker/reference/native/TypeScript test passed in
8.72 s. Function values, explicit effect witnesses and higher-rank effects
remain pending.

Toolchain 0.181 extends `?E` inference to function values when an expected
function type supplies the effect context; a bare effect-polymorphic reference
without that context is rejected. The focused checker/reference/native/
TypeScript test now covers both direct calls and `seq::map` function values and
passed in 9.08 s. Explicit effect witnesses, higher-rank effects and a
language-version migration remain pending.

Toolchain 0.182 accepts explicit effect witnesses after type arguments
(`seq::map<i64,i64>!{io}(...)`, including contextual function values). A witness
requires exactly one effect parameter and must match every callable argument;
mismatches are `E_EFFECT`. The focused checker/reference/native/TypeScript test
passed in 8.77 s. Higher-rank effects and a language-version migration remain
pending.

Toolchain 0.183 extends `?E` inference to the remaining `std/list` callback
helpers (`generate`, `any`, `all`, `find_index`, `sort_by`) and substitutes
effect parameters in cloned lambda bodies during generic instantiation, so
effectful merge/sort helpers type-check with concrete effects. The focused
checker/reference/native/TypeScript test passed in 10.34 s. Higher-rank effects
remain pending.

Toolchain 0.184 collects effect parameters from function types as well as the
outer effects set, so named generic functions can return `fn(T)->U !{?E}` and
instantiate it with the inferred set. Pure and `io` factory instances receive
distinct names; the focused checker/reference/native/TypeScript test passed in
11.09 s. Higher-rank effects and a language-version migration remain pending.

Toolchain 0.185 adds `nex emit --kind opencl` for the checked scalar subset
(i64/bool/unit, shared pure functions, checked arithmetic, assert/if/while).
Rows/columns kernels are source-only (`driver_initialized`/`device_executed`
false); the focused test compiles emitted OpenCL C with Clang's OpenCL frontend
and rejects f64 in 0.24 s (the standalone Clang syntax run took 1.39 s). Device dispatch and Mali/NPU hardware acceptance
remain pending.

The 0.185 OpenCL scalar kernel was also executed on CIX P1's physical
**Mali-G720-Immortalis r0p0** GPU under OpenCL 3.0 through an external host
harness: `(20,2)->42/error 0` and `(INT64_MAX,1)->0/error 1`, with
`CL_DEVICE_TYPE_GPU` selected and no CPU fallback. Source-only dispatch and full
SDK acceptance remain pending.

The 0.185 OpenCL scalar kernel also ran on RK3588's physical
**Mali-G610 r0p0** GPU under OpenCL 3.0: `(20,2)->42/error 0` and
`(INT64_MAX,1)->0/error 1`, with `CL_DEVICE_TYPE_GPU` and no CPU fallback.

Toolchain 0.186 replaces the scalar Wasm arithmetic stubs with real checked i64
add/sub/mul/neg/div/mod (including INT64_MIN/-1 overflow and division by zero)
in `runtime/wasm_runtime.c`. With LLVM 22.1 `wasm-ld`, the `wasm` and
`typed_scalar_wasm` suites now execute instead of skipping: `wasm` passed in
20.67 s and `typed_scalar_wasm` in 1.96 s, including overflow/assert/div-zero
agreement. Full Wasm/SDK/platform acceptance remains pending.

Toolchain 0.187 adds finite `f64` to the scalar Wasm ABI. The wrapper accepts
only finite JS numbers, checks non-finite results with `E_FLOAT`, and supports
f64 arguments/results. `wasm` passed in 17.87 s, `wasm_f64` in 0.84 s and
`typed_scalar_wasm` in 1.99 s under LLVM 22.1 `wasm-ld` plus Node. Full
Wasm/SDK/platform acceptance remains pending.

Toolchain 0.188 completes OpenCL scalar `f64`: `cl_khr_fp64` source, checked
non-finite status 7, finite input validation and f64 rows ABI. The kernel ran on
NVIDIA RTX 3090 OpenCL 3.0 (`42.0`, error 0; infinity input error 7); Mali
remains i64/bool because it has no fp64. The OpenCL focused suite passed in
0.24 s. Full device/SDK acceptance remains pending.

Toolchain 0.190 extends type-parameter defaults to generic functions. Calls may
omit trailing type arguments, inference fills defaults when a parameter is
otherwise unbound, and function values use defaults without an explicit
context. Non-trailing/unit defaults remain rejected. The focused
resolution/reference/native/TypeScript test passed in 5.35 s.

Toolchain 0.191 extends `nex fmt` to directory trees. It recursively checks or
writes `.nex` files, skips `.nex`/`.git`/`build`/`node_modules`/`dist`, symlinks
and non-NEX files, reports `nex.format-directory/1`, and rejects directory
preview or simultaneous check/write. The focused directory test passed in 0.24 s.
Width wrapping and editor requests remain pending.

Toolchain 0.192 adds LSP `textDocument/formatting` as a full-document edit
through `nex fmt`; the server advertises `documentFormattingProvider`, never
writes the source file and returns an empty edit list for formatted text.
`language_server` passed in 18.98 s.

Toolchain 0.193 adds LSP `textDocument/prepareRename` and
`textDocument/rename`; declaration and references produce a WorkspaceEdit,
invalid identifiers are rejected, and the physical file is untouched.
`language_server` passed in 19.05 s.

Toolchain 0.194 adds LSP declaration completion filtered by the identifier
prefix at the cursor; `language_server` passed in 19.38 s with completion items
for helper/main/Point.

Toolchain 0.195 extends LSP completion to local/parameter/field values with
name deduplication; `language_server` passed in 19.25 s.

Toolchain 0.196 adds `nex fmt --width N` for conservative wrapping of long
unquoted lines at commas; quoted/comment lines are unchanged and invalid widths
are rejected. `fmt_width` passed in 0.24 s.

Toolchain 0.197 filters LSP local/parameter completion to the enclosing
function and declarations before the cursor; `language_server` passed in
20.14 s.

Toolchain 0.198 adds struct-field completion after `.` using the checked
receiver type; `language_server` passed in 20.30 s.

Toolchain 0.199 adds `Enum::` case completion with LSP kind 20;
`language_server` passed in 20.36 s.

Toolchain 0.200 adds import-alias `h::` completion from checked imported
files; `language_server` passed in 20.38 s.

Toolchain 0.201 filters import-alias completion to public declarations and
supports direct module-name qualifiers; `language_server` passed in 20.54 s.

Toolchain 0.202 makes LSP value completion lexical-block aware: declarations
inside `if`/`while`/nested braces are hidden outside their block.
`language_server` passed in 19.99 s.

Toolchain 0.203 adds LSP signature help for checked function calls;
`language_server` passed in 20.40 s.

Toolchain 0.204 adds LSP workspace symbol search; `language_server` passed in
20.23 s.

Toolchain 0.205 adds LSP document highlights; `language_server` passed in
20.07 s.

Toolchain 0.206 adds LSP completion fallback for unparsed source;
`language_server` passed in 20.40 s.

## Maintain the catalogue

[cmake/test-tiers.json](../cmake/test-tiers.json) explicitly classifies all known
groups, including conditional platform groups. New groups must be added there;
configuration fails when a registered test lacks an entry. Keep core small and
review commands/helpers before adding a dependency to it. The
[`test_tiers` control](../tests/test_tiers.py) checks actual `ctest -L` selection,
metadata, fixture closure and rejection of an unclassified new group.

```sh
python3 tools/ctest_tiers.py --check-policy
```

Labels change selection metadata. Existing commands, timeouts, skip rules,
resource locks and fixture relationships retain their contracts. At the final
milestone, run the complete suite with the required web/tool dependencies and
verify its actual JUnit against the complete registry.
