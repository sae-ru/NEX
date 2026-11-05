# Windows diagnostic process ownership

The native observer runs a controlled program inside a fresh unnamed Windows
Job Object. It requires Windows 10 / Server 2016 or later. The recorded native
calibration uses Windows 11; it does not certify every supported OS version.

The root is created suspended with `PROC_THREAD_ATTRIBUTE_JOB_LIST`, checked
with `IsProcessInJob`, and resumed only after membership is confirmed. Only the
three capture handles are inherited. Timeouts terminate the private job;
`KILL_ON_JOB_CLOSE` supplies cleanup if the observer exits. The helper never
walks parent PIDs or terminates a process discovered from a PID notification.
Job notifications can be lost or refer to recycled PIDs, so accounting and
verified held handles determine the recorded lifetime. A receipt does not
claim that every short-lived child exit code was captured. See the Microsoft
[creation attribute](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/nf-processthreadsapi-updateprocthreadattribute)
and [job notification](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_associate_completion_port)
contracts.

Build and calibrate with a complete native LLVM-MinGW toolchain:

```powershell
cmake -S tools/windows -B build/job-observer -G Ninja `
  -DNEX_WINDOWS_JOB_OBSERVER_ONLY=ON `
  -DCMAKE_C_COMPILER=C:/llvm-mingw/bin/clang.exe `
  -DCMAKE_CXX_COMPILER=C:/llvm-mingw/bin/clang++.exe
cmake --build build/job-observer -j 4
ctest --test-dir build/job-observer --output-on-failure
```

The calibration uses generated peers and a separate outside-job canary. It
checks normal parent/child completion, preservation of a nonzero root exit,
timeout after a zero root exit with a still-running child, rejected assignment
before program execution, and observer termination after its peers start. The
outside canary must survive and then stop cooperatively. It never uses personal
applications as canaries. The same calibration checks the maintained Python
wrapper's zero, nonzero and timeout results. Successful temporary test evidence is removed;
`job_observer_test.py --observer ABSOLUTE_EXE --output NEW_DIRECTORY` retains it.

App execution aliases and packaged executables can reject creation with job
assignment. The installed Microsoft Store Python 3.10 on the recorded Windows
host returned access denied before its root could resume. This remains a failed
launch, with no uncontained fallback. Use an ordinary executable for peers;
`--peer-python ABSOLUTE_PYTHON` records a distinct peer interpreter while testing
the wrapper under the actual controller interpreter.

Use the calibrated helper from Python or the standalone wrapper:

```powershell
python tools/windows/job_observer.py `
  --observer build/job-observer/nex_windows_job_observer.exe `
  --output build/owned-debug-run --timeout 180 -- C:/debugger/bin/lldb.exe --version
```

The program path must be absolute and the output directory new. Raw program
streams, helper streams and kernel receipt remain available. Exit codes stay
unchanged; timeout returns 124 and observer failure is an error. Callers still
validate application behavior and fatal debugger stderr. Kernel job membership
is a process-ownership boundary, not a filesystem or network sandbox.

For controlled filesystem isolation, the helper also accepts explicit
`--directory`, `--appcontainer-sid` and repeated `--capability` options before
`--`. The AppContainer and private job are applied atomically at process
creation. The suspended root's real token, exact package SID and declared
capabilities are verified before resume. A failed creation or token check is
an error; there is no ordinary-process fallback. Use the
[owned-profile qualification broker](windows-appcontainer-qualification.md)
to create, copy and remove the temporary profile after the entire job retires.
`--describe` reports the required helper capabilities.

The earlier external Toolhelp lineage observer was quarantined after a false
ownership classification affected an unrelated application. Its ownership and
cleanup conclusions are invalid; original diagnostic reports remain preserved.

The [scoped calibration record](evidence/windows-job-observer-2026-11-05.json)
pins the helper source, native CTest, both Python controllers and four cached
HTTP/task sessions. Full source-deleted debugger and SDK acceptance remain open.
That earlier receipt pins the helper before AppContainer support; the newer
AppContainer calibration has a separate source and binary identity.
