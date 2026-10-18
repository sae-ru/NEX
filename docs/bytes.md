# Immutable binary data — language 0.13

Query `nex describe --json` and its `binary_features` / `binary_limits` before
generating source. Platform and SDK acceptance status is recorded in `STATUS.md`.

```nex
module binary_example;
fn main() -> unit !{io} {
  let data:bytes = unwrap(bytes([0,255,128,65]));
  let changed:bytes = set(data,1,7);
  assert(data[1]==255 && changed[1]==7);
  assert(len(slice(data,1,2))==2);
  assert(unwrap(decode_base64(encode_base64(data)))==data);
  assert(unwrap(decode_json<bytes>(encode_json(data)))==data);
  print(unwrap(decode_utf8(utf8_bytes("Я🧠\u0000text"))));
}
```

`bytes(list<i64>) -> result<bytes>` copies checked octets in 0..255, returning
`E_RANGE` otherwise. Empty construction uses `bytes([])`. Text stays a distinct
Unicode scalar string: use `utf8_bytes(str)` and `decode_utf8(bytes)`. Decoding
returns `E_UTF8` for malformed sequences, preserves BOM/NUL and never normalizes.
There are no implicit conversions, byte literals, pointers or mutable views.

Indexing returns i64; `len` / `slice` count octets. Bad indices/slices trap
`E_BOUNDS`. `push` / `set` return new values and trap `E_RANGE` for bad octets;
`set` checks its index before the replacement range. `+` concatenates. Copies,
aliases, slices and immutable closure captures retain their owners; updates do
not mutate them. Bytes have structural equality and generic `add` / `wire`
bounds, without ordering or numeric bounds.

`encode_base64(bytes)` returns a string. `decode_base64(str)` returns
`result<bytes>`, with `E_BASE64` for noncanonical input. Padding is required;
whitespace, the URL-safe alphabet and nonzero unused bits are rejected. Formatting
bytes produces quoted base64; explicitly encoding produces the unquoted string.

Typed JSON/API bytes are canonical base64 strings. Malformed wire data returns
`E_JSON`. The 1 MiB JSON limit includes encoding, quotes and wrappers; a standalone
byte value fits at most 786429 raw octets. Nominal descriptor objects remain
distinct from the `"bytes"` primitive, preserving historical wire schemas.
Codecs work in native and TypeScript/browser programs without OpenSSL or Node
dependencies. Host imports/exports copy mutable arrays.

Server-only `file_read_bytes(str) -> result<bytes>` and
`file_write_bytes(str,bytes) -> result<bool>` require `fs`. Their capability,
1 MiB file limit, atomic replacement and HTTP isolation are the same as text
files; see [files.md](files.md). Arbitrary file octets are never treated as text
until an explicit strict decode. Source resources/FFI/async remain pending.

Stopped values have bounded previews and paged octet children. Pure watches can
request `len(data)`, `data[index]` or a small slice without fetching siblings.
Partial slices select at most 255 octets and share a 256-capture frame budget;
bounded whole values support larger slices. Full formatting/equality/codecs
require complete captures. Missing/inconsistent values remain explicit failures.
The scalar prover reports unsupported for binary operations.

Language 0.12 stores need explicit `nex migrate`; conflicting definitions named
`bytes`, codec intrinsics or binary file intrinsics must be repaired in an
exported candidate. Nominal/generic parameter `bytes` conflicts are rejected too.
Rejected migration preserves HEAD/history. Keep original SQL and matching SDK
0.30/0.32 for old frames/receipts. Regenerate acceptance snapshot metadata while
preserving test source and formal properties. See [the specification](language.md).
