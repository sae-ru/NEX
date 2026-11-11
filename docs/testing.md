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
pending.

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
