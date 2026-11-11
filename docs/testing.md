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

The selected11 groups cover frontend checking, typed reference evaluation,
checked float/byte runtimes, discovery/language-pack contracts and offline tool
accounting/collection/CTest metadata. They require Python3.10+, the configured
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

The current11-group core command passed in **12.36 seconds** on the development
Mac (one sequential CTest observation, toolchain0.165.0/language0.28). Its
selected PATH/NEX_NODE/NEX_TSC guard observed no Node/npm/npx/tsc requests, and
the complete318-group registry retained every earlier command and non-label
property. See the [scoped evidence](evidence/test-tiers-0.165.0-2026-11-11.json). This is a host observation, not a universal timing guarantee.
Other whole-layer wall times remain
unmeasured on the current source until the agreed full milestone. Inventory
reports declared timeout sums separately; those are upper budgets, not runtime
measurements. Historical timings retain their own source/hardware scope.

The later CI block adds the extended `ci_ctest_receipts` group:319 groups are now
registered on this Mac, with all318 earlier commands/properties preserved. Its
three methods execute small real CTest projects, including failure and skip
controls. The new receipt path also ran all11 real core groups in13.61s;
[local CI evidence](evidence/ci-workflows-0.165.0-2026-11-11.json) retains that
separate observation. It does not claim a GitHub or Linux container execution.

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
