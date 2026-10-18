# Versioned foreign-call transport

Development 0.37 adds an experimental C value boundary. Language 0.14 and its
canonical formats do not change. Source external declarations, library loading,
signature checking, packaging, generic external resources, callbacks into NEX
and source async remain pending. This transport is a foundation for those
features; it is not a published stable FFI or an implemented source feature.

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
Builders create scalar/string/bytes/list/result values. Nominal constructors and
NEX callback invocation require the later checked signature/adapter layer.

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

## Source integration gates

Before exposing foreign calls to NEX programs, implement all of the following:

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
