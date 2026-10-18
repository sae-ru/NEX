# Immutable binary buffers — next language milestone

This is an implementation plan, not current syntax. Toolchain 0.30 / language
0.12 exposes UTF-8 text files; `bytes` and binary file operations are not yet
available. Query the actual compiler before generating source.

The next runtime step is a distinct immutable `bytes` value, so arbitrary file
data never masquerades as valid UTF-8. Native storage should be contiguous octets
behind the existing owned handle; copying a NEX value shares immutable storage.
Updates allocate a new value. No descriptor, mutable pointer or host lifetime
becomes a source value. A host adapter must copy imported mutable data or retain
an explicitly immutable owner; borrowed views cannot outlive that owner. General
source FFI/resources/async remain separate required work.

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
repaired candidate. Keep SDK 0.30 for original frames and receipts.

Acceptance must include arbitrary octets and malformed UTF-8, alias immutability,
left-to-right/short-circuit behavior, strict codec rejection, generic/callback/API
roundtrips, bounded debugger demand, native cleanup on every exit, archived-source
migration, installed and restored SDKs, and deployment without the SDK. Check
native Debug/Release, interpreter and TypeScript agreement; preserve the full
macOS/Linux matrix and explicit unsupported-platform status.
