# Owning-thread resource executor

Toolchain0.125 provides a private trusted C++ host executor. It is the physical
lifetime layer needed before exposing owned model sessions, GPU/NPU buffers and
source task/FFI completions. Query `nex describe --field resource_executor --json`.
This adds no source syntax, source task authority, C executor token, language
version, canonical identity or migration. Current source task/JSON/browser guards
continue to reject resource authority. No actual GPU/NPU handle is provided here.

`ResourceExecutor` owns one OS thread. `ResourceDomain::makeOnExecutor` and
`ExternalResource::makeOnExecutor` reserve a cleanup slot before a factory runs,
then construct and destroy the complete payload on that thread. Native host
code supplies the explicit executor and code pin. Defaults are64 live resources,
64 admitted operations and8 MiB of declared operation capacity. Supported maxima
are4096 resources,64 operations and8 MiB. This accounts for declared retained
capacity, not all process, vendor or GPU memory. Resource-domain object quota and
the joined external byte budgets remain independently enforced.

Logical close, alias close and domain/request revoke mark an owner unavailable
immediately. They do not reclaim its physical payload while a borrow exists.
The final release queues the complete physical payload into its pre-reserved
slot without allocation or fresh admission. Destruction on the owning thread
finishes before the actual module pin and the byte/object quotas are released.
Full operation queues and closed admission cannot reject this finalizer.
Factory failure, null output and publication failure also retire unpublished
objects on the owning thread. No destructor runs under executor/domain locks.

Trusted fixed adapters derive from `ResourceExecutionOperation` and submit an
owned operation object. They retain immutable host inputs, the real borrowed
physical owners and actual module pins. Source Values, raw Handles, C invocation/
type/reference tokens and source callbacks must never cross this boundary.
An accepted operation and its retained state are destroyed on the executor.
A rejected operation remains the submitting host's responsibility and is
destroyed on the submitting thread; it has acquired no executor authority.

`run(control)` must return or throw only after the actual device fence, child
process/IPC operation or equivalent physical work has settled. A driver adapter
must catch a cancellation checkpoint if it still owes physical settlement;
the generic executor cannot infer completion from opaque vendor pointers.
The executor publishes completion only after `run` and destruction of the
operation's owned state. It then releases the declared operation reservation.
Adapters must recheck the actual resource/request/type/placement before admitting
a result into source execution. This host layer does not perform that future
source completion admission.

`ticket.cancel()` prevents queued work from starting. For running work it marks
the control, while the operation retains its real leases until physical
settlement. Waiting observes cancellation after settlement, never an early
success. A later cancellation cannot rewrite an already published result.
Calling `close()` refuses new admission but retains all pre-reserved cleanup.
`drain()` waits for current queued/running work; it does not close idle owners.
`finish()` closes admission, waits for all reserved resources and operations,
then joins the worker. Release idle owners and borrows before calling it.
Waiting/draining/finishing from the same executor is rejected to avoid deadlock;
ordinary nested host `invoke` runs inline while admission remains open.

The destructor closes admission. Already retained cleanup tickets keep the
physical worker alive until all owners retire. A host lifecycle must call
`finish()` before declaring full shutdown; dropping the facade is not a claim
that live resources have already settled. Payloads and module pins must not
create cycles through the executor or resource owners.

The maintained gate verifies actual thread identity, queued/running cancellation,
physical fence barriers, close/revoke/publication failure, cleanup capacity,
concurrent aliases, byte/object retention and a real C module's destructor and
`dlclose` callback. The actual device adapter and logical source-task ownership
remain subsequent required integration, with their own platform acceptance.
The installed SDK's source-resources phase separately compiles and runs all21
cases using the installed runtime, probe and actual module sources. Its receipt
does not enable source task/FFI/device transport. Full SDK/platform acceptance is
reported for the exact compiler after it completes.

```sh
cmake -S experiments/resource-executor -B build-resource-executor
cmake --build build-resource-executor -j 4
ctest --test-dir build-resource-executor --output-on-failure
```
