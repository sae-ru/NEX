# Windows AppContainer SDK qualification

`tools/windows/appcontainer.py` is a host qualification tool for controlled SDK
tests. It creates a fresh ephemeral Windows AppContainer profile, copies an SDK
into it, and runs controlled programs through the native Job Object observer.
It does not add a NEX language feature or automatically sandbox NEX applications.

Use a non-elevated, unpackaged Python 3.10+ broker on native Windows and a
separately built, calibrated observer. Microsoft Store Python is explicitly
rejected before profile creation: its package identity changes profile layout
and did not support the ordinary-helper launch in the recorded experiment.
This restriction concerns the qualification broker, not NEX source semantics.
Choose an ordinary Python executable explicitly; the tool never silently
substitutes another interpreter.

The [packaged-root follow-up](evidence/windows-packaged-root-refusal-2026-11-08.json)
observed a Store Python root inside the private Job Object while its two-second
native child belonged to no job. Ordinary Python 3.10/3.14 retained both actual
processes. The current native observer queries the held, suspended root with
`GetPackageFullName` and rejects package identities before resume. Unknown query
results also fail admission. Its capability descriptor advertises
`unpackaged_roots_only`; raw receipts record the identity check and refusal.
Select ordinary interpreters throughout an SDK workflow, including `NEX_PYTHON`.
This root admission check does not classify every future process a program could
launch. The full SDK checks remain separate from this controlled-peer result.

The follow-up built all host targets and passed both registered CTest groups,
plus actual ordinary Python 3.10/3.14 suites. Each broker passed one actual Store
root refusal, the original native controls, seven AppContainer cases, three
budget refusals and two legacy-helper controls. All six profiles and their parent
directories were removed; all 836 original compact-runtime files were preserved.

The [scoped calibration receipt](evidence/windows-appcontainer-development-2026-11-05.json)
records real ordinary Python 3.10.11 and 3.14.3 brokers with a distinct copied
Python 3.14.3 peer runtime, six AppContainer cases per broker, six deleted
profiles and unchanged source-canary contents/ACLs. This is a Python-runtime
qualification pilot; no NEX compiler or HTTP request ran inside those profiles.

The [workflow follow-up](evidence/windows-appcontainer-workflow-2026-11-08.json)
records the newer host-tool build, both registered CTest groups, and actual
Python3.10/3.14: seven AppContainer cases, three invalid-budget refusals and two
old-helper compatibility/refusal controls per broker. All six profiles and
their parent directories were removed. Separate generated Python parent/client
pairs completed same-profile IPv4 loopback with empty and explicit network
capabilities; those two profiles were also removed. No loopback exemption or
other network setting changed. This is measured Python behavior on that host;
NEX execution and complete SDK filesystem isolation remain unverified.

## Native NEX runtime follow-up

The [native follow-up](evidence/windows-AppContainer-NEX-native-2026-11-08.json)
records a separate runtime development overlay on the pinned0.162.1 compiler.
Actual debug/release FFI tests passed in fresh AppContainers with both flat and
nested module layouts. Missing grants, a private outside catalogue and the
opposite profile were rejected. Temporary module snapshots were empty after
every case, and all profiles and parents were deleted. The maintained native
image tool passed five cases each under actual ordinary Python3.10/3.14;
the extended calibration passed eight each and preserved all836 peer-runtime files.
These results qualify the recorded overlays and test images. Complete SDK,
compiler-in-container and HTTP-in-container acceptance remain pending.

Windows requires both user and AppContainer principals for access. Private
runtime files therefore retain the effective user SID and, when present, only
that process's current AppContainer SID. Ordinary tokens keep user-only ACLs.
This follows the [Windows dual-principal model](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer).
The stream adapter uses the same principal selection as host snapshots.

Snapshot directories remain read-only during module execution. Cleanup retains
handles before sealing, restores the saved ACLs with
[SetSecurityInfo](https://learn.microsoft.com/en-us/windows/win32/api/aclapi/nf-aclapi-setsecurityinfo),
then closes child handles before recursive deletion. This preserves cleanup
authority without requiring a new writable open of a sealed path.

Use `profile.native_environment(base_environment)` for native children. It
selects the newly created profile's Temp directory and the actual LocalAppData
base. Replacing LOCALAPPDATA with the work directory caused Windows native temp
lookup to append a second Packages/profile/AC/Temp path in the measured failure.
No original folder ACL or global environment setting is changed.

The maintained tool accepts self-contained native FFI test images that exercise
the supplied catalogue and exit zero on success. It copies only pinned manifest
members, verifies hashes and rejects reparse points; it does not copy unlisted
provider files. From the source tree, run tools/windows/nex_appcontainer_test.py
with --observer ABSOLUTE_HELPER --debug DEBUG_EXE --release RELEASE_EXE
--foreign HOST_JSON --output NEW_DIRECTORY. An optional --outside-catalogue
PRIVATE_HOST_JSON requires actual OS read denial for that selected file without
changing its ACL. Opposite-profile and missing-grant controls always run.

## Build and calibrate

From a source checkout, select a complete native LLVM-MinGW toolchain and a
compact ordinary Python runtime to copy for the controlled peers:

```powershell
C:/Python314/python.exe --version
cmake -S tools/windows -B build/appcontainer-observer -G Ninja `
  -DNEX_WINDOWS_JOB_OBSERVER_ONLY=ON `
  -DCMAKE_C_COMPILER=C:/llvm-mingw/bin/clang.exe `
  -DCMAKE_CXX_COMPILER=C:/llvm-mingw/bin/clang++.exe `
  -DPython3_EXECUTABLE=C:/Python314/python.exe `
  -DNEX_WINDOWS_APPCONTAINER_PYTHON_ROOT=F:/test-runtimes/python314
cmake --build build/appcontainer-observer -j 4
ctest --test-dir build/appcontainer-observer --output-on-failure
```

The optional runtime flag registers `windows_appcontainer_ownership` alongside
`windows_job_object_ownership`. The AppContainer peer runtime must contain
`python.exe` and its required standard library, at most 1000 files / 64 MiB.
The broker interpreter and copied peer runtime are distinct recorded inputs.
Successful temporary evidence is removed; retain raw reports in a new directory
with `appcontainer_test.py --observer ABSOLUTE_EXE --runtime ABSOLUTE_RUNTIME
--output NEW_DIRECTORY`. An optional `--source-canary ABSOLUTE_FILE` checks read
denial without changing that file or its ACL.
To include an actual Store-root refusal, set
`-DNEX_WINDOWS_PACKAGED_PYTHON=ABSOLUTE_STORE_PYTHON` or pass
`job_observer_test.py --packaged-python ABSOLUTE_STORE_PYTHON`. The generated
marker must remain absent and the suspended root must retire before the test
accepts the refusal. No Store or machine configuration is changed.

`Profile.run` defaults to180 seconds and accepts an explicit outer workflow
budget up to10800 seconds. A budget above one hour requires the selected native
observer to advertise that ceiling before any program or observation output is
created. The maintained calibration uses a short-lived healthy peer at the
three-hour ceiling, rejects invalid budgets, and optionally checks a calibrated
one-hour helper with `--legacy-observer ABSOLUTE_EXE`. Individual commands and
tests inside a workflow retain their own deadlines. The
[host-tool calibration](evidence/windows-appcontainer-workflow-2026-11-08.json)
uses short-lived peers; it does not claim three hours of endurance or complete
SDK acceptance. Immutable SDK resource snapshots keep their original identity.
For the registered CTest case, select the optional old helper with
`-DNEX_WINDOWS_APPCONTAINER_LEGACY_OBSERVER=ABSOLUTE_EXE`.

The calibration checks actual AppContainer child and grandchild tokens, read
denial for the outside file and opposite profile, read-only copied runtime
access, writable work space, nonzero exit preservation, and a zero root exit
with a live child that must be retired by the private job timeout. An explicit
capability case verifies the suspended token; it makes no network request.
The ordinary job calibration separately checks observer termination cleanup.
Existing-profile reuse and ACL changes outside the fresh profile are rejected.

## Use the broker from a controlled acceptance driver

```python
from pathlib import Path
import os, sys

sys.path.insert(0, str(Path("F:/NEX/tools/windows")))
from appcontainer import Profile

with Profile() as profile:
    sdk = profile.copy_tree("F:/test-inputs/nex-sdk")
    env = profile.native_environment(os.environ)
    result = profile.run(
        [str(sdk / "bin/nex.exe"), "doctor", "--json"],
        "F:/test-evidence/new-doctor-run", env,
        observer="F:/test-tools/nex_windows_job_observer.exe", timeout=60,
    )
    assert result["parent_exit_code"] == 0 and not result["timed_out"]
    profile.verify_copies()
```

The selected SDK still needs all of its real execution dependencies. This
example is an API usage pattern; it is not an accepted installed SDK result.
Keep receipt directories beneath a trusted broker-owned parent outside every
test profile. Select environment, toolchain and resource roots explicitly in a
real acceptance driver. Receipts must survive profile deletion.

## Ownership and cleanup

The broker accepts only newly created profiles. File copies use new file bytes,
not hard links or copied source ACLs. Reparse points and symlinks are rejected;
file/byte/space limits and hashes are checked. Empty directories are preserved.
Only the new profile and its descendants receive test ACLs: SDK files get
read/execute, work gets modify. A separate profile has its own distinct SID;
put an opposite SDK there when testing its denial.

The observer applies `PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES` and
`PROC_THREAD_ATTRIBUTE_JOB_LIST` before execution, inherits only capture handles,
and verifies the held root token before resume. Job accounting must reach zero
and captured members must retire before deletion. Unknown retirement retains
the profile and raises an error. Timeout terminates only that private job;
there is no PID-tree cleanup. No claim is made that notifications capture every
short-lived child exit code.

Original source/system ACLs, existing profiles, accounts, firewall, loopback
exemptions, VPN and IPv6 configuration are not changed. Network capabilities are
empty by default. A caller may explicitly request capability SIDs, but token
presence does not prove network access or connectivity. HTTP/loopback execution
and full moved/restored SDK isolation remain separate acceptance gates.

Profile deletion is performed by the live broker after job retirement. Abrupt
broker or machine failure can leave its fresh profile for explicit recovery;
the tool does not search for or delete unrelated profiles. This controlled
qualification harness is not a general service for running hostile programs.

Windows contracts: [AppContainer implementation](https://learn.microsoft.com/en-us/windows/win32/secauthz/implementing-an-appcontainer),
[process package identity](https://learn.microsoft.com/en-us/windows/win32/api/appmodel/nf-appmodel-getpackagefullname),
[profile creation](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile),
[process attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute),
[profile deletion](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile).
