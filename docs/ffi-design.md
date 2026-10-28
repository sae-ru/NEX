# Pinned executable members in toolchain0.132

A bundle may declare an optional `executables` array of unique paths already
listed and hashed in `files`. The loader hashes every member before loading
code, then seals listed executable files0500, all other files0400 and directories0500.
Original source permission bits grant no execution authority. Unlisted files
remain nonexecutable. Unknown, duplicate, malformed and unpinned executable paths
are rejected before initialization. Old manifests retain their original modes.
Query `foreign_boundary.module_loading.executable_members` before preparing
such bundles. The manifest bytes and explicit export grants remain pinned;
this does not sandbox trusted native code or initialize hardware during inspection.

# Foreign calls and versioned C transport

Development 0.41 / language 0.15 adds experimental source declarations, checked
bindings and interpreter/native invocation. Earlier versions 0.37–0.40 introduce
the C transport, checked signatures, native module loader and invocation contexts
described below without changing their language 0.14. C module ABI 1 retains its
original table prefix. Toolchain 0.42 adds reviewed task catalogue capture and current-trust replay.
Toolchain 0.43 adds matching-host native dependency-closure packaging with checked
source-pin projections; see [packaging](packaging.md). Generic external resources, callbacks into NEX and source
async remain pending. This is not a published stable FFI. `STATUS.md` records
the exact validation scope.

## Source declarations (language 0.15)

```nex
pub server extern fn transform(data:bytes) -> bytes !{ffi} =
  foreign("images", "transform", "0000000000000000000000000000000000000000000000000000000000000000");
```

Replace the zero pin with the SHA-256 of the exact bundle `manifest.json` bytes.
Library/export names are ASCII identifiers of at most 128 bytes. External
declarations must be concrete, server-only, non-test functions and declare `ffi`.
Their types derive the value contract returned by `nex ffi --symbol NAME --json`.
Nominal generic model types are supported; external function templates are not.
`extern` and `foreign` are contextual, so ordinary identifiers keep their meaning.
`ffi` denotes opaque trusted native effects, which can include arbitrary OS work.

Supply the independent operator catalogue with `--foreign HOST.json` to
`nex eval`, `run`, `test`, `debug` or `profile`. A standalone generated executable
accepts `--nex-foreign HOST.json`; a generated HTTP server accepts `--foreign`.
Compilation and signature discovery load no native module. Source metadata
identifies intended code and grants no authority. There is no environment grant.
The host catalogue must permit the library, export and exact bundle pin. The
loader also checks the compiler-derived signature before module initialization.
Arguments evaluate once in source order; short-circuiting, checked return types
and immutable/resource ownership semantics apply in interpreter and native code.

Only reachable native declarations add the loader/Crypto runtime. HTTP calls use
an authenticated request's scope; operator/module files must stay outside the
static asset root. Server declarations and binding metadata are excluded from
emitted clients. `nex package --foreign HOST.json` requires explicit grants and
produces a derived, checked source-pin projection for relocated bytes while
preserving original graph history. Toolchain 0.42 task execution requires a
reviewed per-check `foreign_hash` and a separate current `--foreign HOST.json`.
`nex foreign HOST.json` verifies inventory bytes without initializing modules;
capture/replay rules and bounds are documented in [the task guide](tasks.md).

`examples/ffi/source.nex.in` is a template materialized with a real manifest pin
by the installed SDK acceptance workflow. It calls the independent C module and
compares native and interpreter results with the reference NEX model. The
workflow includes source-deleted replay and standalone execution. Explicit
`nex migrate` preserves language-0.14 snapshots and identities; function/12 and
program/13 include the checked binding in current semantic hashes. Rebuild and
review current acceptance pins; keep the old SDK for historical frames/receipts.

## Boundary and ownership

`runtime/nex_ffi.h` is a C11 header. Its versioned function table uses fixed-width
integer scalars, binary64, C function pointers and caller-owned buffers. No STL,
shared-pointer, LLVM, object layout, exception or allocator crosses it. Hosts
negotiate a major ABI and minimum table size with `nex_ffi_get_api`. Future table
extensions must preserve the existing prefix; incompatible changes need a new
major ABI. Compatibility still requires matching platform ABI/architecture.

Trusted C++ hosts call `nexrt::invokeForeign`. The foreign callback receives the
table, a call token, argument tokens and an output-token slot. Call/reference
tokens are nonzero, never reused within this runtime image, and are not pointers
or OS handles. Each reference belongs to one call and its creating thread.
Expired, cross-call and wrong-thread use fails. These checks do not turn native
code into a sandbox: C must supply valid buffers/function pointers and must not
longjmp, destroy host objects illicitly or retain borrowed argument-array/table
lifetime assumptions across unloaded runtime images. C++ callbacks must not
throw across the C boundary; the host wrapper still catches accidental throws.

Arguments are retained before the first host poll. C receives no borrowed NEX
storage. String/byte imports copy C buffers; exports copy into C-owned buffers.
Embedded NUL is data, strings are strict UTF-8, f64 is finite with positive zero,
and booleans accept only 0/1. Offsets/sizes are unsigned byte counts at this C
boundary, including UTF-8 copying. They do not change source scalar indexing.
Copy calls may return a short prefix at the end; offset past the end is an
error. No implicit terminator is copied. Outputs remain untouched on errors.

Aggregate inspection is read-only. Lists, records, enums and results expose
children; record labels, qualified enum tags and error codes expose copied UTF-8
labels. String/byte payloads expose bounded byte copies. Closures remain opaque;
file identity is diagnostic and grants no IO. References can forward any valid
input value, including owned resources, without reconstructing its representation.
Builders create scalar/string/bytes/list/result values. Typed calls additionally
construct records/enums from checked type tokens. NEX callback invocation still
requires the later source adapter layer.

`retain` creates another call-local owner; `release` consumes only its token.
All other tokens expire when the call exits, including failed calls and traps.
The returned managed value retains its complete subtype and resource authority
domain; it does not outlive request revocation merely because C forwarded it.
No FFI API constructs a file, reveals an FD, mutates an aggregate or gives a
diagnostic watch identity IO authority. Domain/file cleanup uses the existing
ownership runtime. Destruction and host polls run outside the registry lock.

## Limits, errors and cancellation

Default limits are 4096 live references, 1 MiB cumulative copied bytes and 65536
API operations per call. Hosts may choose 1..65536 references, 1..64 MiB copied
bytes and 1..1048576 operations. There are at most 4096 incoming arguments.
Reference IDs remain unique even after release. Builders charge copied payloads
and list slots; copying out charges transferred bytes. Failed imports may still
consume budget. Existing input storage is retained, not charged again; limits
bound new transport work rather than the full pre-existing object graph.
New aggregate/result wrappers have a conservative nesting bound of 128; copying
an existing input does not traverse or revalidate its entire pre-existing graph.

API calls return numeric status codes and never propagate C++ exceptions. Value
errors (type/range/UTF-8/bounds/reference/quota) are separate from recoverable
application errors built as a failure result. A nonzero callback status or an
invalid/missing output becomes `E_FFI`; accidental callback exceptions become
`E_FFI_EXCEPTION`. A host poll failure is sticky: later API calls return
`NEX_FFI_HOST_TRAP`, and invocation rethrows the original exception with its
diagnostic code/line even if C ignores that status. Entry and exit polls run as
well. Recursive polling of the same call returns `NEX_FFI_REENTRANT`.

Native work must poll cooperatively; arbitrary blocking C cannot be forcibly
interrupted by this transport. Pure value operations consume the operation
budget; `poll` invokes the supplied host callback. Source adapters must bind it
to the native request/interpreter budget and cancellation mechanism.

## Checked host signatures (0.38)

Export a concrete named function's value contract without executing it:

```sh
nex ffi examples/ffi/main.nex --symbol ffi_example::contract --json > signature.json
```

`nex.foreign-signature/1` uses a flat table of types and numeric table indices,
including recursive nominal layouts, specialized/phantom identities, opaque
function keys and file types. These indices are metadata, not C tokens. Generic
templates, tests and hidden closure entries are rejected; select a concrete
named specialization. Both compiler export and the host constructor use the
same schema validator. The language-pack JSON schema describes the format;
runtime checks also enforce identities, reachability and recursive graph rules.

Trusted hosts construct an immutable `ForeignSignature` and use
`invokeForeignTyped`. Inputs are retained and checked before entering C. The
result is checked after the exit poll. Wrong scalar kinds, heterogeneous lists,
nominal identities, field names/order/counts, enum tags or result payloads fail
with `E_FFI_TYPE`. Malformed metadata fails with `E_FFI_SIGNATURE`. This layer
expects genuine runtime values; it does not validate arbitrary raw C++ memory.

The original 0.37 table prefix and ABI major 1 remain unchanged. New table slots
come after `NEX_FFI_V1_TRANSPORT_SIZE`. New clients must negotiate their required
table size; separately compiled old C producers keep using their original
prefix. Type queries/constructors on an untyped call return `NEX_FFI_TYPE`.

Private host development appends a second suffix for genuine owned external
resources. It uses `NEX_FFI_V1_TYPED_SIZE` for the preceding table and
`NEX_FFI_V1_RESOURCE_SIZE` for the resource suffix. Result-reachable type tokens,
actual module code pins, origin-checked call-local borrows and explicit operator
value quotas are described in [the resource contract](external-resources-design.md).
This adds no source resource declaration, source task/FFI bridge or device handle.

`argument_type` and `result_type` return call-local `nex_ffi_type` tokens.
`type_child`/`type_child_count` inspect list/result element types or ordered
record/enum payload fields; records use variant zero, enums use their ordinal.
`type_variant_count` applies to enums. `type_kind` uses the value kind constants,
plus type-only `NEX_FFI_UNIT` and `NEX_FFI_RESULT`. `make_nominal` obtains labels,
identity and discriminant from the selected type, then checks every supplied
field. It cannot create a function or resource. Metadata copies via
`signature_size`/`copy_signature` consume the normal byte budget and expose no
borrowed pointer. At most 4096 type tokens exist separately from value owners.

Only original compatible callable values discovered through the input graph
may cross back as functions. A library cannot relabel their realm/effect/type
key. Captures stay opaque and retain their original ownership. Genuine closed
file owners may still be forwarded, while diagnostic identities are rejected;
forwarding does not restore revoked IO rights. Unit exists only as a result:
the C callback leaves `*out` zero and returns success. There is no unit value
token to insert in a list or record.

Metadata is limited to 1 MiB, 4096 types, 65536 fields overall, 1024 fields per
payload and 4096 enum cases. Value checks allow depth 128 and 100000 visited
nodes, poll the host periodically, reject cycles and memoize aliases. Limits
report `E_FFI_LIMIT`. Existing source programs can contain larger layouts; a
contract export that exceeds this transport's limits fails explicitly.

`examples/ffi/producer.c` and `host.cpp` demonstrate the actual interface. The
host consumes the exported JSON and constructs a typed generic record/enum/result
through C. It is compiled from the SDK runtime as a C++20 host plus C11 producer.
It does not turn the ordinary NEX model function into a source external call.

## Authorized native modules (development 0.39)

`nex_ffi_module.h` declares a separate ABI-1 module descriptor. A C11 shared
library exports `nex_ffi_module_entry(host_value_abi, host_value_table_size)`.
The getter returns a versioned table with export count, stride and entries.
Each entry contains its bounded ASCII name, canonical signature SHA-256,
callback and opaque module-owned user pointer. Reserved fields must be zero.
The getter must belong to the entry image; callback code must belong to an
inventoried image in the same bundle. These origin checks do not make native
pointers or native code safe. The module and its dependencies are trusted.

`ForeignLibraries` accepts an explicit map of logical library names to
`ForeignLibraryGrant {directory, manifestSha256, exports}`. There is no ambient
environment grant. `bind(library, export, signature, expectedManifestSha256)`
requires both pins to agree and the requested export to be permitted. The
catalogue may grant only a subset of the module's exports. Each catalogue has
a physical authorization quota, default 64 and maximum 4096. Revocation and
destruction invalidate bound functions; `isOpen()` reports logical authority.

The bundle's `manifest.json` follows `nex.foreign-bundle/1` and
[`foreign-bundle.schema.json`](../llm/foreign-bundle.schema.json). It contains
the exact host platform, entry path, file path/SHA-256 inventory, export
name/signature-SHA-256 map and at least one inventoried notice. The manifest
pin hashes its exact UTF-8 bytes. Signature pins hash the validated contract's
compact JSON with recursively sorted object keys, unescaped UTF-8 and original
array order (`foreignSignatureDigest`); table indices and ordered fields remain
significant. JSON whitespace and object key order do not alter a signature pin.
The Python equivalent is `json.dumps(contract, sort_keys=True,
separators=(',', ':'), ensure_ascii=False).encode('utf-8')` followed by SHA-256.

Before any native initializer can run, the loader validates the manifest,
requested signature and platform; reserves physical quota; opens only regular
files through directory descriptors without following member/parent symlinks;
copies and hashes every inventoried file into a private temporary directory;
and seals that snapshot read-only. It then loads the absolute entry path with
`RTLD_NOW | RTLD_LOCAL` and checks the module descriptor against the manifest.
The manifest is limited to 1 MiB, inventory to 128 files, each file to 64 MiB,
total copied bytes to 256 MiB, exports to 1024 and host grants to 128. Paths use
at most 4096 UTF-8 bytes and 128 components. Each component is at most 255 bytes;
absolute paths, empty/dot/dot-dot components, NUL, backslash, colon and file/parent
prefix conflicts are rejected. The manifest itself cannot be an inventoried file.

Concurrent binds share a content-addressed image cache. Once verified and
loaded, an image may be reused under the same pin after its original bundle
changes; its private bytes remain the executed bytes. The cache is weak and
cannot keep an otherwise unowned library loaded. Module authorization is
separate for each catalogue/request. Binds made inside a native request join
its resource scope. Hosts that reuse a catalogue must bind inside each request
and pass the request poll callback. Source adapters will enforce this rule.
An active invocation retains a physical image lease through argument/result
validation and all polls. Revocation prevents further operations while native
code stays loaded until the invocation unwinds. Finalizers run before snapshot
removal and physical quota release. No native initializer, callback or finalizer
runs under loader/cache/resource locks. Same-thread recursive loading fails
with `E_FFI_REENTRANT`; other threads wait with cooperative host polling.

Errors distinguish `E_FFI_GRANT`, `E_FFI_HASH`, `E_FFI_MANIFEST`,
`E_FFI_PLATFORM`, `E_FFI_IO`, `E_FFI_LOAD`, `E_FFI_ABI` and
`E_FFI_SIGNATURE`; resource and sticky host cancellation errors retain their
original codes. The host never exposes platform loader error text or addresses.
Metadata pointers must be valid for the module's lifetime. Modules must obey
the C ABI, use thread-safe callbacks, allow cleanup on the last-release thread
and stop all escaped workers before unloading. Native blocking work must poll;
there is no forced interruption or native-code sandbox. Exceptions/longjmp
across C frames are prohibited. C++ exceptions accidentally thrown by the getter
are translated to `E_FFI_EXCEPTION` as a diagnostic safeguard.

Dynamic loader dependency lookup and symbol interposition still follow OS
rules. `RTLD_LOCAL` does not create an isolated dependency namespace, and this
inventory does not prove that every transitive loaded dependency is pinned.
Copied dependent libraries must use appropriate loader-relative paths. The
host must provide a trusted process environment. Toolchain 0.43 packages native
loader dependency closures on matching hosts; arbitrary dynamic loads and native
OS actions are outside automatic discovery. Broader dependency auditing,
platform signing and Windows/mobile support remain pending. The present target list states
implemented host branches; executed validation belongs in `STATUS.md`.
The host temporary directory must allow executable mappings: a `noexec` mount
rejects the sealed image with `E_FFI_LOAD`, even when all content checks pass.
Initializer timing and lookup behavior follow the
[Linux loader contract](https://man7.org/linux/man-pages/man3/dlopen.3.html) and
[Apple dynamic library guidance](https://developer.apple.com/library/archive/documentation/DeveloperTools/Conceptual/DynamicLibraries/100-Articles/DynamicLibraryUsageGuidelines.html).

`examples/ffi/module.c` wraps the same independent typed C producer used by the
static host example. Compile it with `NEX_EXAMPLE_SIGNATURE_SHA256`, package its
image and `NOTICE` in the inventory, and use `module_host.cpp` with the explicit
bundle pin and exported signature. The installed SDK acceptance workflow builds
and loads this actual C shared module after deleting its C/C++ sources and with
NEX resources unavailable; it compares the nested result against the NEX model.

## Scoped invocation adapter (development 0.40)

`loadForeignLibraries(path)` reads an explicit `nex.foreign-host/1` operator
catalogue, described by [`foreign-host.schema.json`](../llm/foreign-host.schema.json):

```json
{
  "schema": "nex.foreign-host/1",
  "module_limit": 64,
  "libraries": {
    "example": {
      "directory": "bundle",
      "manifest_sha256": "<exact 64 lowercase hexadecimal digits>",
      "exports": ["contract"]
    }
  }
}
```

The placeholder above must be replaced by the actual manifest SHA-256. The
configuration is at most 1 MiB and must be a regular file; its final component
cannot be a symlink. Parent components resolve before opening it. Relative grant
directories resolve against that actual configuration parent, retaining normal
filesystem symlink/`..` behavior. Reading the catalogue validates its structure
and creates a capability object, without loading modules or executing native
initializers. There is no `NEX_FOREIGN_CONFIG` or other environment fallback.
A binding supplied by a program never supplies operator authority.

Trusted C++ hosts enter `ForeignScope(shared_ptr<ForeignLibraries>, limits)`
and call `invokeScopedForeign(bindingJSON, arguments, poll)`. Binding JSON follows
[`foreign-binding.schema.json`](../llm/foreign-binding.schema.json): schema
`nex.foreign-binding/1`, logical `library`, logical `export`, exact
`manifest_sha256` and a full compiler-exported `signature` object. Both the host
catalogue and binding must independently agree with the pinned bundle.

Contexts are lexical and local to a thread. A nested empty catalogue denies
access instead of falling back to its parent. Destroying a context ends its
authority immediately, including through callbacks or out-of-order destruction;
ended/expired entries are pruned. Host code may share a catalogue across threads,
but each thread enters its own context. An external shared catalogue remains
owned by its host; ending one borrowed context does not revoke other host uses.
Calls retain their metadata, values, callback and context state before any host
poll. Scope checks surround every poll. A library is rebound inside each native
request before polling, including after a metadata cache hit; cached metadata
cannot turn ended request authority into process authority. Caching never stores
a request-independent callable to bypass those checks.

Default bounds are 4096 cached bindings and 64 MiB of cumulative cached binding
UTF-8, with at most 1 MiB per binding, 4096 arguments and 64 nested scopes. Hosts
can lower those cache limits and choose supported `ForeignCallLimits`. The byte
counter bounds retained input metadata; parsed layouts and bookkeeping consume
additional memory within their separate structural limits. Exhaustion reports
`E_FFI_LIMIT` and already cached bindings remain usable. Invalid binding metadata
reports `E_FFI_BINDING`; invalid operator configuration reports `E_FFI_GRANT`.
`E_FFI_SCOPE` distinguishes a context ended during a call. File IO failures use
`E_FFI_IO`, while loader, type and sticky host errors keep their existing codes.

`foreign_runtime.cpp` provides the internal same-version native ABI
`nex_foreign_invoke(bindingBytes, size, argumentListHandle, sourceLine)`. This is
an adapter for generated code, not an extension of the stable-prefix C value
table. It receives genuine managed runtime handles, calls the common scoped
adapter, and returns an internal owned one-slot result box. A generated caller
extracts its statically checked scalar/heap result and releases the box; unit
has no observable source value. Native host errors preserve their source line;
real request cancellation remains sticky even when C ignores a failed poll.
The adapter registers terminal context/catalogue cleanup for standalone
`nex_runtime_finish` or fatal runtime exit. Embedded hosts use `RequestScope`
so failures unwind as `Trap`; they must not finalize a runtime while unrelated
work still uses its catalogues.

`examples/ffi/scoped_host.cpp` exercises this actual native handle bridge using
the existing typed module, a real request and explicit host/binding JSON. The SDK
workflow deletes its C++ source, removes NEX resources from the selected
environment and compares its output with the NEX model. That adapter example
exercises the internal bridge directly; the separate 0.41 source template
exercises `extern`, the `ffi` effect, interpreter and MLIR lowering.

## Stable FFI acceptance gates

Before claiming a stable FFI, complete and verify all of the following on the
stated target matrix. Experimental 0.41 implements the source path; pending
packaging and broader validation remain visible in `STATUS.md`:

- Checked declarations and versioned signatures with explicit realm/effects,
  library/symbol identities and content-pinned dependency/configuration inputs.
- Matching interpreter/native invocation and typed return validation. Reject
  wrong aggregate shapes, nominal identities, captures and resource kinds.
- Explicit host/library authorization, deterministic loader errors, ownership
  transfer/borrowing rules and platform-specific packaging/notices.
- Browser reachability exclusion or a separately checked web adapter; native
  library names or privileged code must not leak into emitted clients.
- Explicit history-preserving migration for any new source names/syntax, genuine
  old snapshots, graph/cache invalidation and a model-independent language pack.
- C and C++ producers, nested/reentrant calls, host traps, stale/cross-call/thread
  tokens, retained resources, bad values, quotas and sanitizer/platform checks.

Only after those gates and the stated target matrix pass can a stable source
FFI be claimed. Runtime verification status belongs in `STATUS.md`.
