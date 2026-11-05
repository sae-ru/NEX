# Checking CTest results

`tools/ctest_report.py` checks a completed CTest JUnit report against the registry
from the same test configuration and the actual CTest process exit code.
The native Windows cohort runner uses this check for both full and focused runs.

CTest can add preparation and cleanup tests through `FIXTURES_REQUIRED`,
`FIXTURES_SETUP` and `FIXTURES_CLEANUP`. Selecting only
`source_exception_frontiers`, for example, also runs
`source_exception_modules`. Both results must be present and successful.
Ordinary `DEPENDS` controls order and does not expand the selected inventory.

Save the unfiltered registry before running tests:

```sh
ctest --test-dir build --show-only=json-v1 > registry.json
nex_ctest_exit=0
ctest --test-dir build --output-on-failure \
  -R '^source_exception_frontiers$' --output-junit results.xml || nex_ctest_exit=$?
python3 -X utf8 tools/ctest_report.py --registry registry.json --junit results.xml \
  --select source_exception_frontiers --ctest-exit-code "$nex_ctest_exit"
```

For a full run, omit both `-R` and `--select`. Repeat `--select NAME` for several
selected groups. The registry must still contain their fixture declarations.
The result distinguishes selected groups, added fixture groups and every
observed result. It includes SHA256 hashes of the two input reports.

On Windows PowerShell, capture the registry without a text-encoding conversion:

```powershell
python -X utf8 -c "import pathlib,subprocess; pathlib.Path('registry.json').write_bytes(subprocess.check_output(['ctest','--test-dir','build','--show-only=json-v1']))"
ctest --test-dir build --output-on-failure -R '^source_exception_frontiers$' --output-junit results.xml
$nexCtestExit = $LASTEXITCODE
python -X utf8 tools/ctest_report.py --registry registry.json --junit results.xml --select source_exception_frontiers --ctest-exit-code $nexCtestExit
```

The checker exits with:

- `0`: the exact selected and required fixture inventory completed successfully,
  without skipped groups, and CTest exited with zero.
- `1`: the inventory is valid but a group failed, did not execute, was skipped,
  or the CTest process exited unsuccessfully.
- `2`: an input is invalid, missing, duplicated or inconsistent with the registry,
  or the derived output cannot be saved.

`--output FILE` saves the derived JSON. Keep it separate from the original
registry, JUnit and process logs. A successful JUnit document cannot override
a nonzero process exit. A failed fixture cannot be hidden by its selected
test's successful result. Missing, unrelated and duplicate groups are rejected.
The registry limit is 32 MiB and the JUnit limit is 64 MiB.

This validates the CTest group inventory. It does not attest source/compiler
identity or interpret skips inside a child test suite's textual output. The
cohort runner separately pins its compiler, debugger, harness and resources;
platform and installed SDK acceptance retain their own scopes.
