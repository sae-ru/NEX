# Private module and HTTP process profiles

Toolchain0.135.27 adds explicit profiling to the private source-backed module
workflow. Public language remains0.24, private execution ABI2502 and public
ABI3/4/5 keep their meanings. Read [module HTTP](source-exception-module-http.md),
[physical images](source-exception-frontiers.md) and
[consumer instances](source-exception-instances.md) first.

Architecture/5 retains the six component fields and host selection from/4,
and requires `"instrumentation":"profile"`. Every selected code component is
instrumented; old/1-/4 architectures retain their original unprofiled meanings.
An instrumented source record is `nex.private-task-module/5`, with a checked
`nex.private-task-module-profile/1` extension. This is an explicitly prepared
compiler-private workflow, not public `nex profile` support or025 publication.

```json
{
  "schema": "nex.private-task-architecture/5",
  "mode": "mixed-fixed",
  "application": "app",
  "host": "application",
  "instrumentation": "profile",
  "components": {
    "math-lib": {"entry": "math::value", "units": ["math.nex"],
      "exports": [], "dependencies": [], "linkage": "shared", "instantiations": []},
    "app": {"entry": "app::main", "units": ["main.nex"],
      "exports": [], "dependencies": ["math-lib"], "linkage": "application", "instantiations": []}
  }
}
```

The modules/5 plan includes `nex.private-task-profile-catalog/1`. Each component
emits its own immutable32-byte registry ABI1 and accessor. Original component
labels, including hyphens/digits, map to stable bounded internal registry keys;
the catalog retains that mapping. Site rows bind function canonical/source
hashes, source-unit identity/hash, file/line, original source component, emitting
machine component and physical image. Consumer-owned template instances retain
their original template source and actual consumer method targets.

The host prepares the entire checked registry batch before source work or HTTP
workers start. It resolves tables in the already loaded physical image closure;
metadata preparation does not add source dependencies or create a task executor.
Descriptors keep their original local site addresses. One common runtime and
collector map those ranges to dense run-local site indexes. Limits are128
registries,16384 sites and16MiB of runtime site text, checked by both the planner
and existing runtime registration. Changed records are rederived from current
checked source; JSON shape does not verify an arbitrary binary.

With `NEX_PROFILE_OUTPUT` set, the real collector writes raw
`nex.profile-runtime/3`. Its build identity is explicitly
`nex.private-module-profile-build/1`, `archived:false`, with no graph revision.
The immutable private catalog supplies source/machine/image attribution, including
selected unused exports with zero calls. The public saved-profile reader does
not accept this private build identity. Without an output request, instrumentation
stays dormant; source behavior and execution limits remain in force.

A logical invocation counts once across suspension, function/image crossings and
worker changes. Source-failed invocations/tasks settle as Aborted, including a
source error whose code resembles a runtime cancellation. Runtime control keeps
its separate channel. The report includes thread CPU, active elapsed, logical
lifetime, scheduler states and shallow managed allocations. Check all completeness
and drop fields before interpreting measurements. Collector backing capacities
and shallow managed pools are not total process RAM; event/timeline limits are
not execution budgets. Owned cleanup and source-error locations must survive
profiling and measurement drops.
Deferred result/payload retirement is executor work, not another source resume.
A future may retain a value after its source task completes. Such detached cleanup
can add executor CPU/elapsed after the logical terminal event; nested cleanup is
already included in the active executor. It does not extend source lifetime or
reactivate a completed invocation. Overlapping executor retirement spans are not
additive wall-clock process duration.

For an HTTP root, the prepared host uses the same registry batch and one
process-wide bounded collector across requests. It records the configured and
effective common **per-request** limits before starting workers. Concurrent
requests have distinct root tasks; futures retain their spawn relationships.
Caught errors can return normal responses, uncaught source errors keep500 and
original source diagnostics, and runtime timeout/budget/disconnect retain their
control outcomes. The host joins request workers before final report publication.
Raw task IDs do not yet correlate to HTTP request IDs/routes; per-request
selection and streaming/rotation for long-running services remain pending.

The conformance drivers execute actual static/shared/mixed O0/O2 images, verify
physical code/descriptor owners and exact runtime catalogs, and compare source
outcomes with AST/TaskIR. They cover caught/uncaught source errors, owned file/FFI
cleanup, consumer-origin generic errors, unused exports, runtime budgets and
actual concurrent HTTP/HTTPS requests, including cancellation and relocation.
The output schemas, catalogs, actual image hashes and raw logs are retained.

Public build/project/profile CLI, captured/replayed/packaged private025 profiles,
request-ID attribution, module logical debugging, complete installed SDK/platform
delivery and explicit history-preserving025 migration remain pending. The
original language/toolchain/Studio/converter/accelerator/performance goals remain
open. Sanitizers have been reauthorized by the user; audit/fuzz campaigns remain
deferred. Current matching sanitizer/platform evidence is a separate gate.
