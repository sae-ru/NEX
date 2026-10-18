# Immutable binary buffers — next language milestone

This is an implementation plan, not current syntax. Toolchain 0.30 / language
0.12 exposes UTF-8 text files; `bytes` and binary file operations are not yet
available. Query the actual compiler before generating source.

Toolchain 0.31 now contains internal C++/TypeScript `ByteBuffer` primitives with
copied host boundaries, immutable slices/updates and a strict codec. Eight native
cases and three cross-runtime/oracle checks passed on macOS ARM64, Linux ARM64
and emulated Linux x86-64. Sanitizer and strict TypeScript checks also passed;
all 33 macOS Debug compiler suites passed. The emitted ES2020 module also passed
68 assertions in each installed Chromium, Firefox and WebKit engine. The opt-in
`tests/bytes_browser.py PROJECT --output NEW_DIRECTORY --browsers-path PATH`
uses existing locked TypeScript/Playwright dependencies and retains its evidence.
This preserved 0.31 checkpoint preceded managed-value integration. The source
language remains 0.12.

## Managed runtime values (development 0.32)

The C++ value runtime now has a distinct immutable binary `Data::Bytes` kind.
`ByteData` stores its `ByteBuffer` separately, leaving the field locations and
size of ordinary `Data` objects unchanged. Its shared-pointer control block keeps
the derived destructor; direct construction or copying as base `Data` fails with
`E_RUNTIME` instead of losing the binary payload. Shallow allocation profiling
accounts for `sizeof(ByteData)`, without claiming vector capacity or total heap
coverage. Copying a value shares immutable storage; a sliced value retains its
owner after the original handle is released. No pointer or descriptor becomes a
source value.

C++ and TypeScript value helpers implement construction from checked i64 lists,
length, octet indexing, retained slicing, immutable updates/concatenation,
structural equality, formatting, explicit UTF-8 and canonical base64 conversion.
Construction returns `E_RANGE` for an octet outside 0..255; indexing and updates
trap with `E_BOUNDS` for bad indices, checking the index before the replacement's
range. Pure helper failures preserve the native source line or TypeScript site.
UTF-8 decoding returns `E_UTF8`, preserves a leading BOM, NUL and normalization,
and rejects overlong sequences, surrogates, truncation and values above U+10FFFF.
Explicit base64 decoding returns `E_BASE64`. Formatting a byte value uses its
quoted base64 representation; explicit encoding produces the unquoted string.

The typed JSON runtimes recognize primitive `"bytes"` as a canonical padded
base64 JSON string; malformed encodings produce `E_JSON`. Nominal schemas have
always used objects such as `{"record":"bytes"}`, so historical record names
retain their meaning. This is an extension of the runtime's wire descriptors;
the source compiler does not yet emit a bytes descriptor or API model. JSON's
1 MiB limit includes quotes and padding: at most 786429 raw octets fit as a
standalone byte value. Larger values fail before allocating the encoded string.
The existing depth/node limits also apply inside containers.

The POSIX `TextFiles` host capability keeps its compatibility name and now has
`readBytes` / `writeBytes` and matching native host entry points. Binary and text
operations share bounded raw I/O, pinned roots, path validation, symlink and
nonregular-file denial, private atomic replacement and cancellation cleanup.
The binary reader transfers its freshly allocated vector into immutable storage;
mutable host imports and exports still copy. File data is limited to 1 MiB.
Text reads alone validate UTF-8. HTTP request scopes still deny implicit
environment grants; an explicit trusted `FileScope` can grant either operation.
No general source FFI/resources/async or binary source intrinsic is exposed yet.

Generated TypeScript projects copy `nex-bytes.ts` with `nex-runtime.ts`; browser
cache identities include both files. These helpers introduce no dependency or
Node-only API. Source authoring and debugger/API integration below remain open;
validation of the new internal value boundary is recorded separately from the
preserved 0.31 primitive evidence.

## Remaining source-language integration

Proposed operations are checked byte construction from `list<i64>`, explicit
UTF-8 encode/decode, indexing/length/slicing, immutable concatenation and updates,
and server-only `file_read_bytes` / `file_write_bytes` under the existing `fs`
capability. Byte values are 0..255; indices and sizes retain checked i64 rules.
Exact signatures and recoverable versus trapping range errors must be fixed in
the normative specification before source exposure. Text operations must retain
Unicode scalar indexing and strict UTF-8 without normalization.

Typed JSON/API needs an unambiguous bytes mapping before claiming full
integration. The proposed representation is a canonical padded base64 JSON
string, using the ordinary alphabet and rejecting whitespace, invalid padding,
nonzero unused bits and non-alphabet characters. This follows the choices
allowed by [RFC 4648 sections 3–4](https://www.rfc-editor.org/rfc/rfc4648.html#section-3).
Existing encoded-text/depth/node limits still apply; a file that fits the file
limit need not fit its larger encoded JSON form. Pure base64 support must not
introduce OpenSSL or Node-only dependencies into ordinary programs.

The TypeScript runtime needs private octet storage and copies at mutable host
boundaries, rather than exposing a writable typed array as a NEX value. Structural
equality, generic `wire`/`add` domains, API schemas, source reachability, callbacks,
native ownership/profile counts, stopped-frame wire values and paged debugger
reads must describe the same type. Scalar proofs must reject unsupported binary
operations explicitly. File adapters must keep bounded reads/writes, pinned
roots, atomic publication, symlink rejection, cancellation cleanup and the
existing denial of inherited HTTP capabilities.

Before changing the language version, genuine SDK 0.30 / language 0.12 stores
were retained in `tests/fixtures/language-0.12*`. They include generic wire code,
server `fs` functions and function references. The conflict fixture contains
currently valid user definitions named `bytes`, `file_read_bytes` and
`file_write_bytes`. Migration must retain old SQL/source/history and logical IDs,
reject conflicting names without moving HEAD, and accept only an explicitly
repaired candidate. The additional genuine `language-0.12-byte-names` fixture
retains a user nominal type named `bytes`, all four proposed codec-like function
names, a wire generic and a captured callback. Native/interpreter/TypeScript
checks passed under SDK 0.30 before capturing its original SQL. Migration must
also reject a conflicting nominal declaration after the function names have
been repaired, rather than silently interpreting its constructor as a primitive.
Keep SDK 0.30 for original frames and receipts.

Acceptance must include arbitrary octets and malformed UTF-8, alias immutability,
left-to-right/short-circuit behavior, strict codec rejection, generic/callback/API
roundtrips, bounded debugger demand, native cleanup on every exit, archived-source
migration, installed and restored SDKs, and deployment without the SDK. Check
native Debug/Release, interpreter and TypeScript agreement; preserve the full
macOS/Linux matrix and explicit unsupported-platform status.
