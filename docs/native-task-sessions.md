---
status: current
applies_to: "language 0.30; toolchain 0.276.0"
owner: repository
---

# Persistent native task sessions

`nexrt::NativeTaskSession` in `runtime/nex_task_session.h` is a compiler-private,
matching-runtime C++ host API for ordinary checked030 ABI8 provider exports.
It retains one application heap across related calls while creating a fresh
step budget, deadline and cancellation callback for each call. Time spent idle
in the host does not consume a later invocation's deadline.

This is a host/runtime contract, not a new source type or syntax, stable C ABI,
generated native UI controller or permission to move cells between threads.
Source versions, canonical graph identities and retained ABIs do not change.
The [provider contract](reference-task-providers.md) supplies the checked code
images; [the example](../examples/native-host-session/README.md) describes their
normal project build.

## Ownership and invocation

Construct the session and invoke its capture-free `TaskCodeDescriptor` exports
on one owner thread. All contributing code-only images resolve runtime calls to
that same host. Compare the emitted provider record, library ABI and exact
compiler/runtime cohort. Do not infer a descriptor or calling signature from a
source name. Keep every code image loaded until sessions, returned values,
callables and typed-error packets that depend on it have retired.

`invoke` accepts matching-runtime `Value` arguments and returns a `Value`.
The physical arguments and descriptor are validated before source admission.
Each call joins its structured tasks before returning; tasks, channels and scopes
cannot survive as host capabilities. Related cells, immutable views and source
error payloads keep their identity and roots between calls. Different sessions
have separate heaps; a cell from another session is rejected with `E_CELL_HEAP`.

```cpp
nexrt::NativeTaskSession session;
auto state = session.invoke(makeDescriptor, {nexrt::Value(40)});
session.invoke(addDescriptor, {state, nexrt::Value(2)});
auto answer = session.invoke(getDescriptor, {state});
session.finish();
```

Descriptors in this sketch are actual ABI8 getters from a checked provider,
not arbitrary host callbacks. The integration fixture demonstrates discovery
from `task-provider.json` and linking several code-only images to one host.

`NativeTaskSessionOptions` bounds heap cells/nodes/edges, logical resource
owners, tasks and external operations. `NativeTaskInvocationOptions` sets that
call's step/time/worker limits and cancellation observer. Source continuations
always execute on the owner thread; bounded IO workers exchange raw completions.
`statistics()` reports the retained heap and admitted/source-error/fatal counts.
`collect()` collects unreachable cycles between calls. Host-retained `Value`
snapshots are roots; release them before expecting their cells to be reclaimed.

## Errors, cancellation and retirement

A `NativeSourceException` is an ordinary typed source outcome. Its returned
payload remains live and the same session can handle another call. Invalid
descriptor/physical argument/foreign-cell preflight also preserves the healthy
session. Source traps, budget exhaustion, timeout, cancellation, allocation
failure and unexpected host failure close it. A later retry requires a new
session. Compiled failures preserve their owned source attribution.

`cancel()` is the only mutating cross-thread operation. It cancels a currently
active invocation and returns false while idle; it does not poison a future
call. Cancellation is cooperative and observed at execution polls. `closed()` is also safe to query from another thread. The session object
itself must remain alive while another thread accesses it. Calls, collection,
statistics, close, finish and destruction are owner-thread operations and cannot
nest/reenter. A wrong-thread destructor terminates, following the existing
trusted C++ heap lifetime contract.

`close()` revokes source access immediately. During an active invocation,
physical heap/resource destruction waits for that invocation's cleanup. The
invocation pins its state, so an owner callback may destroy the session wrapper
without freeing frames that are still unwinding. `finish()` closes and waits
for this session's resource retirement. Call it outside active source work and
release outside physical resource borrows first. Destruction closes without
waiting; externally supplied cleanup executors remain the host's responsibility.
Retained immutable fields survive close; contained cells are inert.

## Explicit file authority

Supply a `shared_ptr<const TaskFrameHostContext>` with captured file grants and
its cleanup executor for file-using exports. The original grant/FileScope must
outlive the session. No ambient grant is captured automatically. A descriptor
requiring files without an explicit host fails before admission (`E_TASK_HOST`).

Returned results and typed-error payloads promote their genuine file owners
from the invocation root region into the session region before task retirement.
A file cursor therefore survives related calls. Merely storing a new file in
an existing cell and returning unit does not transfer its resource authority.
Access through that expired owner remains `E_RESOURCE_SCOPE`; cell retention
does not renew it. Foreign-provider authorization and stable foreign cell
transport remain separate work.

## Qualification scope

The [0.276 receipt](evidence/native-task-sessions-0.276.0-2026-11-17.json)
records32 distinct passing core/affected groups, the14-case host kernel and13
compiled cases in each Debug/Release profile. Both profiles also pass with the
moved ordinary installation and a host rebuilt from its installed runtime.
An88-case existing resource regression preserves ordinary application/request
behavior. The original host-boundary/callback/deadline failures are retained.

The kernel runs inside the existing `reference_tasks_development` core group.
`native_task_sessions` builds ordinary030 projects and actual code-only images
in Debug/Release, then exercises persistent cross-image state, retained views,
typed errors, cycle collection, controls, file return/error promotion and
expired-owner rejection. Receipts record the platform and exact source/compiler
identities. Focused execution and ordinary installation do not qualify a new
portable SDK, Windows/Linux execution, native UI lifecycle, parallel cell
transfer or reference-aware debugging/profiling.

По-русски: сессия хранит объекты приложения между вызовами, а лимиты времени и
шагов задаются заново для каждого вызова. Типовая ошибка сохраняет сессию;
аварийный выход закрывает её. Файловые права передаются явно, и сохранение файла
в объекте само по себе не продлевает право доступа.
