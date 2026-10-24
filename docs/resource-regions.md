# Private logical resource regions

Toolchain0.126 connects trusted host resource regions to the native TaskGroup
scheduler. Query `nex describe --field resource_regions --json`. This changes no
source syntax, language0.21 identity, canonical format or migration. Source task
input/result/channel/capture transport still rejects external resource authority.
Toolchain0.127 also connects the independent AST reference scheduler. The source
task/FFI completion adapter remains pending; no actual GPU/NPU resource is exposed
by this host layer.

Logical ancestry and physical authority are separate. A region graph has up to
1025 nodes including its root,256 nested scopes and4096 retained owner slots.
The256 bound preserves the actual native task scope depth; the static lifetime
analysis's32-level join bound is a different limit. A deep logical scope does
not add physical grant domains. The existing eight-domain physical join bound
and independent object/declared-byte quotas continue to apply.

Native and reference families and independent graphs have distinct identities.
An owning region admits its own borrowers and descendants, with no sibling or
reverse-ancestry borrowing. A number, display name or JSON cannot reconstruct
authority. Host `promoteRegion(actor,target)` explicitly moves a genuine owner
to an active ancestor before closure; all aliases retain its physical identity.
It refuses sibling, foreign-group/family and ended-region transfers. This is a
trusted boundary operation, not a new source intrinsic or general lifetime
inference. Transfer across a whole task group to its request parent is pending.

`ExternalResource::makeInRegion` takes an explicit coordinator-captured
ResourceAccess, the genuine logical authority, class registration, joined byte
budgets, code pin and optional owning-thread executor. It never discovers a
per-resume worker RequestScope through TLS. A logical owner slot and a creation
fence exist before entering the actual resource factory. Null/failing factories,
revocation and rejected publication release the reservation only after the actual
unpublished payload cleanup. Even if all logical wrappers disappear while cleanup
is queued, its retained physical fence prevents early slot reuse or completion.

For ordinary resources `borrow` keeps its existing behavior. Region-owned values
require `borrowInRegion` with genuine authority. Borrows recheck logical activity
and ancestry in addition to the physical owner. An already admitted raw host
pointer can be retained only through its physical borrow lease and the trusted
operation's settlement contract. Logical revocation stops new access; it does
not invalidate already retained physical storage or recycle quota early.

`beginClose` marks a region and its descendants inactive without invoking a
foreign destructor. Its returned retirement request calls `requestClose` outside
scheduler and graph locks. `ready` becomes true after complete payload destruction,
actual code-pin release, the executor cleanup-slot reservation, all joined byte/object quota release and any in-flight
creation guard. Scheduling cleanup, entering a destructor, losing a wrapper or
receiving a cancellation request is not physical settlement.

A trusted coordinator calls `TaskGroup::enableResourceRegions` once before
spawning. `resourceAuthority` then returns the actual current logical scope's
authority, or the group's root on its coordinator/root task. Existing host tasks
without enablement keep their previous behavior. Each opened logical scope owns
a child region. Leaving it parks the source coroutine until all resource fences
settle. The scheduler requests cleanup outside its mutex and continues running
other tasks while an owning executor performs physical cleanup. Group finish
retires root/promoted resources and waits their physical settlement before final
worker shutdown. Cancellation/deadline errors do not waive that cleanup wait.

The maintained18-case gate checks complete ancestry/depth, alias promotion,
foreign family/group refusal, logical admission before factories, invisible
publication failures, quota/fence order and64 real native task resumes. It also
uses a group with only one source worker: a separate task continues running while
the device executor's destructor is blocked, then allows cleanup to finish. Root
retirement and256 actual native nested scopes are separate executable cases.
Existing executor, owned values, files and old C-prefix gates run alongside it.
The installed SDK compiles and runs the same18 cases from installed sources.

The independent serial AST coordinator has its own scopes, jobs and FIFO queues;
it does not dispatch native TaskGroup, TaskIR or compiled frames. A trusted host
sets `TaskReferenceExternalHost::resourceRegions` before evaluation begins.
The coordinator passes the current genuine Reference-family authority to
`prepareInRegion` and, after physical operation retirement, `admitInRegion`.
Their default implementations preserve the existing unit-only host hooks.
The opt-in is captured once; changing the host flag during execution grants no
new authority. Hosts without it allocate no resource graph. These callbacks are
coordinator-only, non-reentrant trusted APIs; no authority reaches a source Value,
raw mailbox result or IO-worker ticket.

Each AST `with_tasks` owns a child logical region. Scope completion and its
`scopeRetired` notification wait for the whole physical resource fence, including
executor finalizers. Other ready AST jobs continue while that cleanup is pending.
Idle waiting polls resource fences at bounded intervals and still observes root
control. Cancellation and deadlines cancel source work but keep waiting for IO
operations and resource destruction. Root and promoted owners are retired before
evaluation returns; unexpected observer/host unwinding also drains operations,
releases retained frames and waits for root cleanup. Request-parent transfer is
still pending. A host must settle its retained physical borrows independently;
waiting for `scopeRetired` before releasing such a borrow would create a cycle.

The separate `reference_resource_regions` gate exercises actual checked AST
programs, ancestry and sibling refusal,64 resumptions, explicit promotion,
independent source-job progress during executor cleanup, cancellation, timeout,
preparation/observer failures and combined IO/resource cleanup. Ordinary reference
task, mailbox and source-value rejection gates remain required.

```sh
cmake -S experiments/resource-regions -B build-resource-regions
cmake --build build-resource-regions -j 4
ctest --test-dir build-resource-regions --output-on-failure
```

Toolchain0.128 adds separate native [Value retirement](task-value-retirement.md):
queued roots and buffer storage leave outside the scheduler mutex, and task/scope
publication waits for their retirement. Source transport still needs checked
transfer to the request parent, captured FFI grants, typed physical completion
admission and the actual source/backend lifetime checks. Keep current source
snapshot guards until that bridge and explicit migration are complete.
Actual devices additionally require their owning executor and
vendor-specific fence/IPC settlement. Process reap is not a generic GPU DMA fence.
