# Mixed source File and external-resource ownership

Private language0.24 permits a checked immutable NEX aggregate to hold both a
File and a genuine server resource returned by a pinned C11/C++20 producer.
The existing mixed owner transfer checks the complete graph before promotion.
File access retains its captured filesystem grants; a resource in the same
aggregate does not upgrade a readonly file. Logical aliases share closure.

The conformance suite runs12 scenarios with each producer dialect, comparing
real separately compiled native NEX applications with the independent AST:

- Child future and scope return promote both owners to their caller.
- A rendezvous channel transfers both owners between sibling tasks.
- A captured parent aggregate retains both owners across child suspension.
- A returned snapshot closure retains the aggregate past its creating scope.
- Lists/results/enums preserve aliases without duplicate physical destruction.
- Seventy scopes reuse both file and external-resource physical quotas.
- A function-local result error releases both owners before task shutdown.
- Seventy errors inside joined scopes settle both owners before quota reuse.
- A forwarded external-resource alias cannot upgrade file access.
- Checked overflow after writing preserves the completed prefix and retires both.
- Cancelling an acknowledged child with both open owners settles physical cleanup.

An ordinary helper return is not a physical cleanup barrier: the final
wrapper release can queue destruction on the owning executor. Its physical
quota stays charged until that destructor finishes. A joined scope, published
future and task/group shutdown provide the documented settlement barrier.
Repeated one-resource construction therefore uses an explicit joined scope;
local helper error cleanup is checked separately at task shutdown.

Success paths require42, unchanged input bytes, balanced actual producer factory/
destructor events and zero reference external capacity after shutdown. Failure
paths require the same error class and written prefix in both backends. The C
and C++ modules use a one-resource/eight-byte physical quota. Native executables
run while their caller source bundle is hidden. Nine rejected check/reference/
native entries cover an FFI File factory, FFI transport of a File-bearing Pair
and wire serialization of mixed authority. Retained023 rejects the mixed task
program. Browser generation emits only its reachable client function.

This suite does not send File values through C FFI. Source tasks pass the File
only inside NEX; C/C++ callbacks receive the checked opaque Session. Fixed
binary task-provider exports still reject opaque external-resource authority.
It does not establish cancellation during an arbitrarily blocked syscall,
rollback, NPU execution, public024 delivery or current platform acceptance.

Run the registered task_file_stream_mixed CTest or tests/task_stream_mixed.py
with the private source-resource probe. Sanitizer runs select matching LLVM
C/C++ producers and instrument the AST/backend and emitted C++ runtime as well
as these modules; full NEX IR and LeakSanitizer claims remain separate.
