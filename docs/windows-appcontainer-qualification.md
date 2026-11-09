# Windows AppContainer SDK qualification

`tools/windows/appcontainer.py` is a host qualification tool for controlled SDK
tests. It creates a fresh ephemeral Windows AppContainer profile, copies an SDK
into it, and runs controlled programs through the native Job Object observer.
It does not add a NEX language feature or automatically sandbox NEX applications.

## Debugger pipe prerequisite in development

A controlled native PE ran to normal exit inside the same AppContainer through
both ordinary `CreateProcessW` and `DEBUG_ONLY_THIS_PROCESS`. The retained LLDB
CLI/DAP prerequisite still failed before an argument stop. The DAP log records
`SetUpPipeRedirection` access denial. A direct native control rejected the global
pipe namespace with Win32 error5 and created/opened a `LOCAL` pipe successfully.
These observations do not accept debugger operation or a complete isolated SDK.

`tools/windows/build_debugger.py --appcontainer-pipes` selects the separately
pinned `lldb23-appcontainer-pipes.json` patch. It selects per-package `LOCAL`
paths when the debugger process token is an AppContainer and keeps ordinary
host pipe paths. It applies the decision to both creation and opening, reports
token-query failures, and retains default object ACLs and existing ownership
checks. Use new source, build and output directories. The selected patch hash
is included in the debugger revision and build receipt. Source preparation was
byte-verified. The [actual patched source compiled to a Windows x86-64 object](evidence/windows-lldb-appcontainer-pipe-object-0.162.2-2026-11-09.json)
using the prior Ninja compilation database, with the same compiler, headers and
flags and new source/object/dependency outputs. The compiler exited normally
without diagnostics; the old source and object remained unchanged. This verifies
one translation unit. The new private linked build and native CLI/DAP regression
remain pending. The queued replay uses the unchanged original PE, requiring an
argument stop at41, actual inferior output42 and normal exit on the host and
inside AppContainer, together with outside read and copied-code write denials.
The existing qualified debugger remains unchanged.

## Current coherent SDK follow-up

The [0.162.2 coherent-SDK receipt](evidence/windows-current-AppContainer-TCP-0.162.2-2026-11-08.json)
records ten actual AppContainer cases on the freshly assembled SDK from source
`05f01d69da0fe1f782d1f4558ba350738eef5d94`, archive
`1bda62f5148fe87a2d5303dd9e66eaca162db6994b920214439a53bc926a8f0f`.
Native checking, reference execution, debug compilation/execution and tests ran
with actual copied Python3.14.3. TCP binary exchange passed in reference, Debug
and Release, with every socket ledger balanced. Source, dependency and opposite
profile reads were denied; the selected SDK was read-only and its work area
writable. This SDK used no resource overlays.

The independent receipt rechecks all source files, the original SDK inventory
and archive. All owned children retired, and private code/profile parent
directories were absent after cleanup. This closes the recorded private-provider
staging regression for that exact archive. Complete moved/restored SDK acceptance
and a general application sandbox remain separate work.

## Broker prerequisites and earlier qualification

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
Those Python-only receipts do not verify NEX execution or complete SDK
filesystem isolation; the coherent native follow-up above has its own scope.

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

## Private code and writable data

`Profile.code_root(parent)` creates a new private staging directory with the same
AppContainer SID. Copy an immutable SDK there; keep project data and native Temp
inside the AppContainer profile. The existing parent's ACL is never changed.
Select an existing parent your account can create directories in and the
AppContainer can traverse and enumerate. The qualified example used `C:/`.

```python
from pathlib import Path
from appcontainer import Profile

with Profile() as profile:
    with profile.code_root(Path("C:/")) as code:
        copied = code.copy_tree(selected_sdk)
        environment = profile.native_environment({
            **base_environment,
            "NEX_RESOURCE_DIR": str(copied / "share/nex"),
        })
        result = profile.run(
            [str(copied / "bin/nex.exe"), "doctor", "--json"],
            new_evidence_directory, environment, observer=observer, timeout=60,
        )
        assert result["active_job_processes"] == 0
        assert result["parent_exit_code"] == 0
        code.verify_copies()
```

The selected SDK still needs its documented PATH and debugger prerequisites.
A code root is a copy/cleanup object; execute through the owning `Profile`.
The parent profile tracks these roots and closes them on retirement, including
when a caller exits before closing a nested code context. Each owned tree has an
explicit `max_cleanup_entries` bound (default200000, permitted1..1000000).
Exceeding it retains the tree and reports the failure. A broker can explicitly
raise that bound and retry after inspection.

This layout addresses two measured Windows behaviors. An ordinary process could
not load the matching native Clang DLL cohort from the Low-integrity profile
copy; changing only that copy's label to Medium restored ordinary execution.
Inside the AppContainer, Clang still failed in LLVM initialization because
`GetLongPathNameW` could not enumerate private parent directories. A native probe
returned Win32 error5 for the original profile path and success through a new
private path. The final physical code root also survives NEX's canonical tool
path resolution, with no compiler override or changed SDK bytes.

Microsoft documents the [parent-directory permissions required by GetLongPathNameW](https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-getlongpathnamew).
The selected LLVM22.1.8 [argument initialization](https://github.com/llvm/llvm-project/blob/ca7933e47d3a3451d81e72ac174dcb5aa28b59d1/llvm/lib/Support/Windows/Process.inc#L182)
uses that function before the driver handles ordinary options. The code root
inherits its selected parent's integrity label; its protected ACL grants only
SYSTEM, Administrators and the broker full access, plus the owning AppContainer
read/execute. The qualified C:/ parent provided Medium integrity. Data/Temp keep
their separate profile permissions. Original SDKs, sources, existing parent ACLs,
network policy and process mitigations stay unchanged.

Cleanup requires physical job retirement and the creating broker thread. It
checks volume/file identities, opens objects without following reparse points,
revokes the AppContainer grant, and prepares only broker-owned ordinary nodes.
Reparse entries and shared hardlink names are removed without changing their
target's ACL or attributes. Held cleanup handles are closed before deleting the
owned tree. Unexpected root identities retain the tree for inspection.

The current Windows0.162.1 compiler passed actual `check`, reference execution,
native debug build, executable execution and native tests from an unchanged SDK
copy using this API. Read controls denied the original project, original SDK and
opposite profile, while code stayed read-only and own work stayed writable.
Four standalone host CTest groups passed on actual Python3.10/3.14, including
abrupt native exit, readonly/link cleanup, root replacement and bounded retries.
These are offline core/host-tool scopes; complete SDK workflow, debugger,
networking and device acceptance remain separate. The [private-code core receipt](evidence/windows-owned-code-root-0.162.1-2026-11-08.json)
pins the host sources and exact SDK. The same compiler's [physical CUDA receipt](evidence/windows-CUDA-0.162.1-2026-11-08.json)
records its separate device and Compute Sanitizer checks.

## Provider staging and private tool files

The [0.162.2 provider-principal record](evidence/windows-provider-principals-0.162.2-2026-11-08.json)
qualifies two candidate Python helpers against the unchanged native compiler.
Python 3.14's Windows `mkdir0700` descriptor omitted the current AppContainer
principal, so the linker could not create `provider.dll` in that private directory.
The helper now creates the directory atomically with a protected DACL for the
effective user and, when present, that token's current AppContainer SID. Private
tool files use the same principal selection. Ordinary tokens retain user-only
access; no inherited broad grant is added.

Actual ordinary Python 3.10/3.14 and an AppContainer Python 3.14 peer created and
read the private files, rejected existing destinations and retained non-inheriting
file descriptors. Captured directory/file DACLs contained exactly one ordinary
principal or the user/container pair. Actual TCP binary exchange then passed in
reference, Debug and Release, with no live sockets remaining. Source, dependency
and opposite-profile denial controls remained enforced; code copies stayed
read-only. All new code roots, profiles, parents and temporary SDK copies were
removed.

This was an explicitly modified experimental SDK copy. Its final inventory check
correctly rejected the old bundle manifest's hashes for the two changed helpers;
the overall pilot remains failed. The scoped OS/TCP results do not accept a new
coherent SDK. A fresh same-source installation, bundle and complete workflow
qualification are still required.

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
