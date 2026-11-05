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

The [scoped calibration receipt](evidence/windows-appcontainer-development-2026-11-05.json)
records real ordinary Python 3.10.11 and 3.14.3 brokers with a distinct copied
Python 3.14.3 peer runtime, six AppContainer cases per broker, six deleted
profiles and unchanged source-canary contents/ACLs. This is a Python-runtime
qualification pilot; no NEX compiler or HTTP request ran inside those profiles.

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
    env = {**os.environ, "TEMP": str(profile.work), "TMP": str(profile.work)}
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
[profile creation](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-createappcontainerprofile),
[process attributes](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute),
[profile deletion](https://learn.microsoft.com/en-us/windows/win32/api/userenv/nf-userenv-deleteappcontainerprofile).
