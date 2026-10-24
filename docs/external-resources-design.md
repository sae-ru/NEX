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
authority, including hidden captures. The original C value table layout and
major ABI remain unchanged. Its new kind15 is opaque; both current C callbacks
and separately compiled0.37-prefix producers can forward a genuine owner.
No C table entry currently creates a resource or exports its payload pointer.
Typed source signature export/construction remains unavailable for this kind.

The host must supply an explicit code owner. Physical payload destruction calls
the object's destructor before releasing that owner; capacity and object slots
return afterward. Payloads, control blocks, managed wrappers and their destruction
are allocated/implemented in the host runtime. Allocating the final control block
inside a provider could unload the very code executing its deletion, so the
public value constructor is a host function. The real test module verifies
object destructor, dlclose callback and quota order.
The code owner must retain physical code, not a lexical grant's revocation
responsibility. Payloads must not form strong cycles through managed values or
authority owners. The subsequent C constructor will select the loader's actual
module lease instead of accepting a producer-supplied code-owner object.

Capacity budgets account for declared external capacity retained by the resource;
they are not a claim about complete vendor allocation, process RAM or GPU memory.
Managed wrapper hooks separately account for their actual subtype size. Current
host payload destructors must be nonthrowing, safe on the last-release thread and
finish cleanup before returning. Thread-affine device cleanup, driver fences and
asynchronous settlement require the next ownership/executor integration before
actual device buffers/sessions are exposed.

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

## Required source and FFI integration

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
4. Extend the typed C boundary with host-issued resource type/borrow tokens and
   a checked constructor. The current loader invocation, never a producer-supplied
   pointer, must supply the actual module lease and authority. Snapshot payload
   ownership before polls, retain destructors' code, and preserve sticky traps.
   Existing reference tokens remain call-local and thread-bound.
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
