# Logical resource regions and dependent FFI resources

Toolchain0.131 development C table appends `resource_create_with_parents` after the old
resource prefix. Negotiate `NEX_FFI_V1_RESOURCE_PARENTS_SIZE` before using it.
`NEX_FFI_V1_RESOURCE_SIZE` retains its previous byte offset; old transport,
typed and resource producers keep their original prefixes and ABI major1.

Parent refs must be genuine resource tokens of the same active call/thread and
declared signature. The child type must remain result-reachable, with factory
and destructor owned by the current pinned image. Passing a parent never grants
permission to reinterpret another image's payload. Up to16 supplied parents
are admitted before factory entry; the transitive graph is deduplicated and
bounded to4096 objects including the child and depth256. Invalid/closed parents,
incompatible logical regions and quota exhaustion refuse construction before
entering the factory. Count/graph quota failures return `NEX_FFI_LIMIT`.

Admitted children retain physical parent payloads, code pins and capacity until
their own destruction finishes, including after a parent alias is closed.
Fresh parent borrowing then fails. Original grant revocation still prevents
new child access; an already admitted operation must physically settle.
Source task capture/result/channel/closure transfers promote the full hidden
dependency closure atomically to the genuine target ancestor. Returning a buffer
alone therefore retains its required session without exposing that session in
the NEX value graph. Factory failure/exception and checked exits destroy children
before releasing parent storage. This adds no direct NEX resource constructor,
syntax change or language migration; a pinned server/ffi extern produces the
dependent owner in both native execution and the independent AST interpreter.
Browser/wire resource transport stays rejected. Actual GPU/NPU bindings remain
pending: these tests use real C/C++ payloads, not device allocations.

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
spawning, optionally capturing a genuine Request-family parent authority.
`resourceAuthority` returns a separate task root on workers, an owned inner
scope while inside it, and the group's root on its coordinator. Existing host
tasks without enablement keep their previous behavior. Each task root is a child
of its admitted member scope or group root; an explicit ancestor-scope spawn
does not inherit its caller job's shorter lifetime. Each opened logical scope
owns a child of the current resource context. Leaving scopes and publishing
native futures wait for complete physical resource retirement after frames,
managed values and external operations drain. Empty task roots retire directly;
only unsettled owners enter the admitted intrusive cleanup list.
The scheduler requests cleanup outside its mutex and continues running
other tasks while an owning executor performs physical cleanup. Group finish
retires remaining group-owned resources and waits their physical settlement
before final worker shutdown. Explicitly returned request owners and borrowed
caller resources survive group finish. Request resource closure follows linked
groups' physical fences; it does not replace execution-control cancellation.
Cancellation/deadline errors do not waive cleanup waits.

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
sets `TaskReferenceExternalHost::resourceRegions` and an optional genuine
`resourceRequestParent` before evaluation begins.
The coordinator passes the current genuine Reference-family authority to
`prepareInRegion` and, after physical operation retirement, `admitInRegion`.
Their default implementations preserve the existing unit-only host hooks.
The opt-in is captured once; changing the host flag during execution grants no
new authority. Hosts without it allocate no resource graph. These callbacks are
coordinator-only, non-reentrant trusted APIs; no authority reaches a source Value,
raw mailbox result or IO-worker ticket.

Each AST job owns a task region under its member scope or group root. Its
`with_tasks` regions inherit that current job context. Hosts receive the job
root when the current source scope is its member scope; an owned inner scope
supplies its own descendant authority. Explicit ancestor-scope spawns inherit
the selected member scope, preserving their lifetime beyond the caller job.
Task completion and `taskRetired` wait for frames, operations, owned scopes and
complete physical task resource settlement. `taskRetired` observes publication;
unexpected observer failures drain resources without publishing unfinished jobs.
Idle/control waits include pending task resource fences. Explicit request returns
and borrowed caller resources survive evaluator/group destruction.
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


## Private host dependency graph

The private C++ constructors in `nex_external_resource.h` accept an optional
trailing span of parent resources. `makeInRegion` places it after `localFactory`.
This is not a source-language constructor or a C-table operation. It does not
provide GPU/NPU sessions or buffers by itself.

Admission captures genuine physical parent leases before invoking a child
factory. Parent logical close denies fresh parent access while already admitted
children keep the payload, code pin and original capacity ticket alive. Child
native destruction and its code pin finish before those parent leases are
released. Closed child aliases retain only ancestry/grant metadata, not parent
payloads. Original grant revocation still denies fresh child borrows and is
rechecked before publication; dependency leases do not mint host permission.

Logical parent owners and their transitive dependencies participate in the same
atomic ancestor transfer as the child. All destination slots are checked before
any owner moves. Creation rejects mixed scoped/unscoped ancestry, ended grants,
more than16 supplied parents, dependency depth above256, or more than4096 unique
objects including the new child. Physical grant domains and logical scope depth
keep their existing independent limits. A failed factory/promotion does not
publish a partial dependency graph.

`dependencyCount` and `dependencyDepth` are host diagnostics. Numeric identities
never construct authority. Stable C construction, ordinary-source parent
factories, actual device objects, and complete compiler/SDK/platform acceptance
remain pending.
