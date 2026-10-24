# Private144: request-parent resource ownership foundation

This host-only draft adds `ResourceRegionFamily::Request` and
`ResourceRegion::inRequest`. It is not an accepted SDK/toolchain release.
The main compiler still identifies its preceding0.128/language0.21 cohort.
The native adapter draft includes per-job roots and explicit request-parent
capture. Its tests and matching compiler delivery remain separate required
gates. Independent reference per-job/request-parent integration is pending.

A request authority is a genuine common ancestor of separately identified
Native and Reference graphs. Both can borrow a resource owned by their request
ancestor. Group-local resources cannot cross siblings or return to a caller
implicitly. An admitted borrower must explicitly promote the existing owner to
an active ancestor. Cross-graph promotion reserves the destination owner slot
before updating the shared owner, preserving aliases, physical identity,
settlement fence and code pin. Capacity refusal leaves the origin intact.

Request closure revokes its own descendants and attached groups. Revocation is
logical; readiness still waits for complete physical destruction, outstanding
borrows, byte/object quota and executor cleanup-slot release. Destructors run
outside the ancestry mutex. Native/reference groups share their request's
ancestry mutex so promotion and closure cannot race through separate locks.

Logical request authority does not supply a physical grant, cancel pure source
execution or replace `RequestScope`/TaskGroup execution draining. The source
resource task input/result/channel/capture guards and the typed task FFI bridge
remain unchanged and disabled. Actual GPU/NPU resource ownership is pending.

Scope and task ancestry have independent256-level limits. Each group retains
at most1025 scope nodes,65536 task nodes and4096 owners. A request retains at
most1024 unsettled or active group links; settled closed graphs can release
their link despite retained closed aliases. Empty task-region retirement skips
the owner table. Logical depth does not consume the physical eight-domain join.

The standalone `experiments/resource-regions` CMake project includes the new
request primitive gate and the existing native region/executor/owned-resource
gates, plus the native per-job/request-parent gate. These do not establish
independent AST per-job integration, installed SDK delivery or platforms.
