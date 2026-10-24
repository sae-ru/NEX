# Private022 task/FFI data calls

This is an explicit C++-API source experiment. Public CLI language021, its
archives and callback rejection rules stay separate. `task_foreign_prototype`
reports `source_support:false` and `public_enabled:false`. No public022 release
or installed SDK/platform acceptance is established by these tests.

The frontend accepts server task/ffi callbacks when the server caller declares
their complete effect set. Optional fs retains the020 whole-file read contract.
Callable type equality remains exact. Ordinary source ffi helpers must declare
task and ffi when called by a task; external leaves keep their ordinary ffi-only
C signature. Only direct checked extern calls use the bridge. Taking an ffi-only
function value does not introduce a resumable callable ABI.

The MLIR continuation parks a concrete Foreign request. The independent checked
AST traversal emits its own request without executing TaskIR or NativeTaskGroup.
Each uses the existing separate bounded joined IO pool. A scope with one CPU
worker can make progress while two foreign calls run. Arbitrary uncooperative C
cannot be interrupted: cancellation/deadline waits for the physical call to end.

Capture the explicit ForeignScope and physical request on the authorized caller
before workers start. This snapshot retains no lexical revocation responsibility
and never renews access. Later binds use its original access, never a per-resume
worker's temporary RequestScope or ForeignScope. The bounded binding cache is
synchronized; callbacks, module loading and finalizers run outside its lock.
Ending the original lexical/request/catalogue authority denies later calls and
admission of already completed bytes. Active calls retain their physical image
lease until C and checked result processing finish.

The request validates the actual source argument graph against the exact pinned
ForeignSignature before native loading. TaskCodec rejects function, file and
external resource types. It copies checked scalars, finite f64, strict Unicode,
bytes and immutable list/result/nominal/enum data through strict schema-bound
snapshots. Nominal reconstruction uses checked names, fields and variants.
The worker reconstructs its own Values and creates fresh call-local C tokens on
that thread. Those values and tokens are gone before completion publication.
Only copied octets and bounded diagnostics enter TaskExternalResult.

The codec bounds one input envelope and one result to1 MiB each; its two schema
descriptors together use at most1 MiB. Exact foreign signature metadata has the
existing1 MiB bound. Each admitted call reserves4 MiB of transport capacity in
the existing8 MiB pool. JSON retains64-depth/10000-item/100000-node checks;
the argument envelope consumes one structural level. These bounds describe
transport, rather than all decoded/native/vendor memory. Unit has no result
token or copied payload. Result decoding and authority checks run again before
resuming source code. Checked traps, cancellation and canonical host resource
exhaustion drain physical operations before scope/application completion.

Source resources, nested/phantom resource types and resource captures remain
rejected at task value boundaries. External ownership needs a separate typed
owned-result channel authenticated to logical owners, expected class/hash/realm,
the physical grant and actual operation fence. Do not insert external owners,
borrowed payloads, source frames or task/channel capabilities into this copied
byte transport. VM cleanup does not prove driver/DMA settlement.

The genuine021 fixtures were produced by accepted SDK128 compiler
40fcbef8657a74f1f51339ed45876808f2d657ed93da8e22a7838c9234b70975.
Five histories contain15 real revisions and16 tables each; that SDK executed
their native/reference and TypeScript tests. Separate current probes authenticate
all original021 hashes, preserve resource nominal identities and derive distinct
private022 revisions. They do not perform or certify public history migration.
The original SQL and sources remain unchanged; do not relabel them as022.

`tests/task_foreign_source.py` compiles real C11/C++20 modules and actual NEX
applications, compares native/independent AST behavior and checks wrong-thread
C token refusal. It exercises nested tasks, one-CPU/two-IO overlap, immutable
aggregate/channel transfer, unit, evaluation/short-circuit behavior, errors,
cancellation, deadline settlement/unload and browser reachability exclusion.
The context probe checks worker request turnover and late lexical/request/module
revocation. `tests/task_foreign_origins.py` checks the authentic retained origins.
Sanitizer, full regression, owned-resource transport, public migration and SDK/
platform evidence retain their separate required gates.

Module authorizations use their own captured module domain and module_limit.
The separate resource_limit applies to external value objects. A data-only call
does not consume an external object slot; aliases of one image still consume
separate logical module authorization slots. Both domains retain the original
lexical/request revocation and physical lease behavior. The actual C11/C++20
native/AST tests grant two library names with resource_limit1/module_limit2,
and separately verify rejection under module_limit1.

Private standalone Foreign request flags do not extend ABI3 provider/capture
records. Those records retain their task/fs-only31 mask and reject private
flags33/65/129/97/225. Exporting an ffi-effect task provider is explicitly
unsupported; source FFI authorization is not a binary-provider grant.
