---
status: development
applies_to: "toolchain 0.275.0; language 0.30; task ABI8"
owner: repository
---

# Reference tasks across native libraries

Ordinary030 projects can retain cell identity across checked code-only static
archives and fixed shared images in Debug/Release. The application owns one
runtime, request, heap and cooperative source executor. Related provider calls,
suspended frames, futures, channels and typed source errors share that heap.
Independent applications retain independent contexts. These contracts prepare
large applications; full SDK/platform qualification remains separate.

Use ordinary `nex.build.json` components and direct source/static/dynamic edges.
See [the example](../examples/reference-task-providers/README.md). Source remains
available for checking: a sidecar or arbitrary binary is insufficient. Existing
ownership rules still require each machine definition to have one physical owner
per application load closure. A fixed shared image and its captures remain loaded
until all source work and application ownership retire. Runtime unloading and
cross-version library mixing are unsupported.

When reachable030 source uses references, the planner propagates owner-thread
ABI8 across the connected binary cohort, including pure providers and consumers
sharing those providers. Reference-free unconnected cohorts retain ABI7. A pure
provider in an ABI8 cohort also emits ABI8 continuations; it cannot switch the
caller back to a worker executor. Source operations run on one owner thread;
configured worker limits still govern applicable physical IO work. Runtime limits
and cancellation remain application-owned and cannot be renewed by a provider.

Public source language/grammar, graph formats and C ABI1 do not change. ABI7 and
the private reference-task descriptor keep their identities. The descriptor stays
88 bytes, with its ABI word at offset40.

| Record | Reference cohort |
|---|---|
| Provider sidecar | `nex.native-task-provider/17` |
| Static plan | `nex.project-static-task-linkage/6` |
| Fixed shared/mixed plan | `nex.project-task-linkage/17` |
| Imported continuation | `task-code/8` |
| Deferred application | `nex.native-task-application/6` |

The provider requirement mask16159 adds the explicit `state` bit8192 to the
retained file/typed-error requirements. These bits describe checked code; they
grant no file or foreign authority. Values crossing a provider boundary may
contain typed cells and existing File owners. They retain ordinary task-region
admission and transfer rules. Cells do not renew an ended File owner's authority.
Task/scope/channel capabilities, exported callable types and external resource
authority remain excluded from provider signatures. Imported provider function
values remain unsupported; a local checked callback may call a concrete export.

Source errors preserve their concrete payload and cell identity between related
images. Fatal traps, cancellation and deadlines skip user finalizers while owned
frame/value/resource cleanup runs. The application closes its heap after joined
source work, before the enclosing request finishes physical cleanup.

Discover `managed_references.source030_development.native_providers`. Its
schemas are [provider17](../llm/native-reference-task-provider.schema.json) and
[linkage](../llm/project-reference-task-linkage.schema.json). Capture/replay uses
the explicit new formats; relabeling an old record does not upgrade its ABI.

Native provider logical debugging/profiling, HTTP project providers, shared-memory
parallel cells, arbitrary load/unload, public foreign cell interfaces and matching
portable SDK/platform delivery remain open. Standalone/HTTP reference-task and
TypeScript entries retain their separate contracts.

## Focused qualification

The [0.275 receipt](evidence/reference-task-providers-0.275.0-2026-11-17.json)
records six static/shared/mixed Debug/Release combinations. Ordinary evaluation
and native execution agree on aliases, child waits, typed packets, retained cell
state and cycles. Step-budget/deadline exits occur with live state inside
provider continuations and retain mapped source diagnostics. The mapper checks
the selected language, including030, rather than the default028.

The36-command source workflow also checks warm reuse, ordinary project tests,
capture/replay after deleting the original source tree, and explicit rejection
of unsupported profile/debug/callable interfaces. Two separate retained ABI7
source-chain methods pass. A moved normal CMake installation runs static Debug
and shared Release from its actual installed example; this retains host
dependencies and does not qualify a portable release.

There are27 passing core/affected CTest groups. One initial HTTP diagnostic group
could not bind in the sandbox; its failed result is retained alongside that
group's successful loopback-enabled rerun. The registered new-provider CTest
group remains separate from its direct harness execution. Whole source,
matching platform and complete SDK/archive acceptance remain required.
