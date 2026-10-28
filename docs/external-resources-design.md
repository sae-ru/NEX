# Source publication update

Development0.123/language021 enables the opaque source contract described in
[source resources](source-resources.md). The private135/136/137 stages below
record the host design and its historical gates. Public support must be queried
on the actual compiler; source task/device completion remains pending.

# Owned external resources: implementation and source integration

This is an active design and private host implementation. Language0.20 cannot
declare or construct these values. `std/model.nex` still has an ordinary callable
Context, not an owned session/device handle. Query the actual compiler; this
document adds no supported source syntax or implicit host grant.

## Host foundation

`nex_external_resource.h/.cpp` provides a typed host registration, owned payload,
borrow lease and joined byte accounting. `ExternalResourceType<T>` identifies
one actual registration; matching display names/digest strings cannot fabricate
it. Names are bounded qualified ASCII identifiers and semantic hashes are
64 lowercase hexadecimal digits. This validates metadata syntax, not a digest's
truth or an operator's authority. Source declaration hashes and loader-owned
registrations must be connected in the subsequent integration.

An external owner uses the existing ResourceDomain/ResourceAccess mechanism.
Construction reserves an object slot, reserves declared capacity in1..8 joined
host budgets, then invokes the factory outside locks. Aliased budgets charge
once. All limits use checked unsigned arithmetic. Factory failure, null return
or revocation before publication releases the unpublished object and both quotas.
Native RequestScope binding joins the grant and request domains. Request exit
and cancellation revoke created owners, including escaped managed values.

Aliases share identity and logical close. A borrow retains physical storage;
new access after close/revocation fails. Closing does not return object slots or
capacity while an admitted borrow still exists. A raw host borrow is bounded by
its lease; it is not a source pointer or continuing authority for new operations.
Host callbacks and destructors run outside registry/domain/budget locks.

`ExternalData` is a separate managed subtype. Base Data construction/copy cannot
slice it. Nested results, records, lists and genuine closure captures retain it;
equality compares identity and formatting emits only `<resource>`. Application
JSON, parallel values and native/reference task snapshots reject external
authority, including hidden captures. The original C value table prefix and
major ABI remain unchanged. Kind15 is opaque to ordinary value inspection;
separately compiled0.37-prefix producers can forward a genuine owner.
Private136 adds the host-only typed constructor/borrow extension below.
Source signature export/construction remains unavailable for this kind.

The host must supply an explicit code owner. Physical payload destruction calls
the object's destructor before releasing that owner; capacity and object slots
return afterward. Payloads, control blocks, managed wrappers and their destruction
are allocated/implemented in the host runtime. Allocating the final control block
inside a provider could unload the very code executing its deletion, so the
public value constructor is a host function. The real test module verifies
object destructor, dlclose callback and quota order.
The code owner must retain physical code, not a lexical grant's revocation
responsibility. Payloads must not form strong cycles through managed values or
authority owners. The C constructor selects the loader's actual physical module
lease instead of accepting a producer-supplied code-owner object.

Capacity budgets account for declared external capacity retained by the resource;
they are not a claim about complete vendor allocation, process RAM or GPU memory.
Managed wrapper hooks separately account for their actual subtype size. Current
host payload destructors must be nonthrowing, safe on the last-release thread and
finish cleanup before returning. Thread-affine device cleanup, driver fences and
asynchronous settlement require the next ownership/executor integration before
actual device buffers/sessions are exposed.

## Private136 typed C and loader extension

The original resource suffix is negotiated with `NEX_FFI_V1_RESOURCE_SIZE`.
Dependent factories additionally negotiate `NEX_FFI_V1_RESOURCE_PARENTS_SIZE`
and call `resource_create_with_parents`; see [resource dependencies](resource-regions.md).
Both prefixes preserve ABI major1 and their original byte offsets.
`NEX_FFI_V1_TYPED_SIZE` preserves the exact preceding typed table boundary;
the0.37 transport prefix and major1 remain usable. This is a trusted host
prototype, not public source resource syntax or a stable ABI claim.

A signature node is `{"kind":"resource","name":"module::Session","identity":"…"}`
with a bounded qualified ASCII name and64 lowercase hexadecimal identity.
The nominal name is unique across resource/record/enum nodes. Validation checks
genuine owned values and exact nominal metadata; strings or records cannot create
authority. Registration keys additionally belong to the actual loaded Image.
Another image with identical metadata can forward the opaque owner but cannot
borrow its private native payload. Per-image registrations are bounded to4096.

`resource_create(call,type,bytes,factory,destroy,user,out)` requires a type reachable
from the checked result, not merely an input type. Both code callbacks must reside
in the current pinned bundle snapshot. The loader supplies its physical module
lease, host value domain, byte budget and current request authority. A scoped
source invocation joins its ForeignScope value domain as well. Joining retained
access objects creates no temporary revoker and adds no ambient grant.

Object slots and declared capacity are reserved before entering the factory.
Writing a nonnull pointer transfers it to host cleanup immediately, including if
the factory later returns failure, polls into cancellation or throws. A successful
null pointer is rejected. The nonthrowing destructor must settle synchronously
on whichever thread releases the final lease; no thread-affine device claim is made.

`resource_borrow(call,ref,type,out)` returns the native pointer only to the current
typed producer invocation/thread and retains a physical lease through call end.
Closing or releasing the C value token does not destroy an admitted borrow.
The pointer cannot be retained for a later call, job or asynchronous callback.
`resource_close`, `resource_is_open` and `resource_identity` operate on genuine
aliases with metadata declared in the signature; identity is diagnostic only.
Closed borrowing returns appended status `NEX_FFI_RESOURCE_CLOSED`. Failed APIs
leave output slots untouched, and host polling traps remain sticky.

Operator JSON accepts optional `resource_limit`1..4096 (default64) and
`resource_bytes`1..1073741824 (default67108864), separately from module quota.
Capture/package normalization retains these values. The shared physical image
also applies its own1GiB declared-capacity budget. These limits do not report
actual total driver or GPU allocations. Revocation does not recycle reserved
capacity until destructor and code-pin release finish.

The dedicated gate builds actual C11 modules with independent signature pins and
exercises host C++20 calls, lexical/request exit, ignored poll traps, concurrent
close/calls, foreign-image rejection, token/thread lifetime and real dlclose order:

```sh
cmake -S experiments/typed-resources -B build-typed-resources
cmake --build build-typed-resources -j 4
ctest --test-dir build-typed-resources --output-on-failure
```

It also runs existing nominal C, pinned loader, ForeignScope, owned-value,
file-value and separately compiled0.37 transport gates. Public source types,
reference execution of resource operations, TypeScript rejection, source migration,
task completion tickets and actual device resources remain separate required work.

Build the private host/compatibility gates separately from the public compiler:

```sh
cmake -S experiments/external-resources -B build-owned
cmake --build build-owned -j 4
ctest --test-dir build-owned --output-on-failure
```

These gates include real managed values, C forwarding, native task rejection,
request revocation, physical quota retention, concurrent close and a loaded
provider's actual destruction/unload. Existing file-value and0.37 C transport
tests run alongside them. They do not prove public resource types or device use.

## Private137 source integration

An explicit internal0.21 versioned-bundle recheck accepts
`pub server resource Session;` and generic opaque declarations such as
`server resource Buffer<T>;`. The public/default CLI remains0.20 and rejects
the new declaration syntax. Migration and source publication remain pending.

Opaque declarations use a separate `nex.resource/1` canonical node while ordinary
records retain their exact old canonical format and meaning. Generic instances
retain their declaration flag and arguments. Compiler-exported C resource class
names use a complete digest in bounded qualified ASCII; semantic identity includes
the genuine declaration, owning module and specialization. Long/generic source
names are not truncated or merged into one host registration.

There is no source constructor or constructor pattern. Granted typed extern
factories create genuine owners. `resource_close(owner)->bool !{ffi}` and
`resource_is_open(owner)->bool !{ffi}` require server realm and an opaque resource
type. Aliases, aggregate/result forwarding, identity equality and diagnostic
formatting preserve the host ownership behavior. Reference execution and MLIR
native output use the same checked value C ABI with independent source execution.

Nested and phantom resource types/captures are server-only and cannot satisfy
wire or cross JSON, task, channel, parallel or browser boundaries. Known hidden
resource captures are rejected before parallel/task entry; runtime guards remain.
Unreachable resource/server code is absent from emitted client code. Native
runtime selection also includes resource operations in code without local externs.

Native formatter code can preview only opaque identity. Reconstructing an external
owner from a watch capture is explicitly unavailable; no diagnostic ID becomes
authority. Actual resource LLDB/capsule acceptance remains pending.

The maintained private probe/conformance test exercises declaration/type checks,
generic separation, source refusals, pinned C11/C++20 producers, actual
reference/native execution, client reachability, C++ throw-after-pointer-transfer
cleanup and checked native failure with a live owner. The optional genuine020
fixture gate rechecks all12 original revisions without changing their hashes.
These checks establish a private integration result, not public021 migration.
New builtin-name conflicts require a reviewed repair when publication is enabled.

## Required remaining source and FFI integration

1. Add an opaque nominal resource declaration, for example the proposed
   `pub server resource Session;`. `resource` is contextual at declaration
   position; existing ordinary identifiers keep their meaning. No default/null
   source value, public constructor, raw pointer or authoritative integer token
   may create it. Exact syntax is pending frontend implementation and review.
2. Bind resource declaration identities into semantic hashes, graph/context/type
   patches, module imports and compiler-exported FFI schemas. Treat source types
   separately from host registrations and physical resource instance IDs.
3. Add generic close/status operations with explicit server/ffi effects and
   identity-only diagnostic previews. Enforce resource ownership through nested
   generics/phantoms, closures, result propagation and every native exit. Keep
   wire/API/storage/scalar-proof/browser exclusion across the full type graph.
4. Connect the private136 typed C/loader extension above to compiler-exported
   source signatures and genuine source owners. Preserve its actual code pin,
   result-reachable construction, nominal/origin checks and scoped revocation.
   Existing reference/type tokens remain call-local and thread-bound.
5. Implement owned device execution/cleanup admission. An explicit executor must
   keep physical leases, module code and byte/object quota until its actual
   driver fence/worker settles. Logical cancellation cannot recycle device memory.
   Queued cancellation starts no operation. A thread-affine object's idle close
   must schedule cleanup on its owning executor, including domain/request revoke.
6. Connect model loading/inference and compute buffers to these genuine owners.
   Then add task/ffi host operations using separately owned completion tickets,
   copied immutable arguments and retained resource/module leases. Do not extend
   ordinary C token lifetimes or store NEX callables in arbitrary native jobs.
   Validate output and request control after physical settlement before publication.
7. Introduce an explicit history-preserving language migration when source
   resource semantics are enabled. Create genuine0.20 fixtures with the existing
   SDK, including ordinary `resource` names/records, and preserve every old row,
   ID and schema. Never reinterpret old records as resource declarations.
8. Keep frontend, independent reference execution, MLIR, TypeScript rejection,
   specification/grammar, actual discovery, prompt and pack consistent. Verify
   successful and rejected programs, C/C++ producers, failed/trapped/canceled exits,
   source-free installed SDK delivery, real provider placement, sanitizers and the
   stated platform matrix. A private host gate cannot certify these source gates.

The full original PLAN remains active. This foundation is a dependency of the
requested general resource/device/task system, not its completion criterion.
