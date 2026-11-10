# Checked scalar GPU source emission

Development toolchain0.165 adds a compiler backend for ordinary checked
language0.28 functions. It emits Metal Shading Language directly from the
compiler's typed AST. It uses no second NEX parser and initializes no driver.
Native, reference and TypeScript source semantics and graph identities are
unchanged; no language migration is required.

```sh
nex describe --field gpu_codegen --json
nex emit --kind metal --entry transform --input-layout columns -o kernel.metal --json
```

Select a shared pure concrete function, including a concrete generic instance
reached by an ordinary root. Only its reachable functions are emitted.
Unsupported reachable types or instructions fail with a source diagnostic;
unreachable server/foreign code is excluded. Failed emission preserves an
existing output file. Text output goes to stdout when `-o` is absent; `--json`
returns the [versioned emission record](../llm/metal-emission.schema.json), with
inline source or its output path, actual shader hash, revision, compiler and
descriptor identities, parameter/result types and reachable function hashes.
Generated function line ranges map to their original declarations. This is
function attribution; GPU stepping and operation profiling remain pending.

The current subset supports checked i64, bool and unit, locals and assignment,
arithmetic/comparisons, lazy boolean operators, branches, loops, ordinary helper
calls and lowered source/loop contracts. Arguments and operands execute once in
source order. Signed arithmetic uses unsigned bits and explicit overflow guards;
division truncates toward zero and `MIN % -1` is zero. Fatal arithmetic/assertion
outcomes retain a separate lane status and publish no partial result.

The root has0..8 i64/bool parameters. At most128 reachable functions and128 call
levels are supported, with emitted UTF-8 source bounded to16MiB. Recursion,
effects, non-shared realms, heap values, f64, closures, indirect calls, match and
source-error/finally control are rejected. Diagnostics use `E_GPU_TYPE`,
`E_GPU_REALM`, `E_GPU_RECURSION`, `E_GPU_LIMIT` and `E_GPU_UNSUPPORTED`.

## Kernel host contract

The entry is `nex_generated_map`. A trusted host supplies physical Metal buffers
and validates their exact lengths and explicit device authority before dispatch.
Source emission grants neither host access nor a fallback to CPU.

Each input is a signed64 word; bool must be exactly0 or1. `rows` uses one row-major
input at buffer0, output at1, uint32 lane statuses at2 and constant uint2
`{lanes,steps}` at3. `columns` uses one input buffer per parameter at0..7, output
at8, statuses at9 and the same parameters at10. A zero-argument columns root
needs no dummy input buffer. Output is one signed64 word per lane: bool0/1,
unit0 and zero for a failed lane.

The host must enforce1..32768 lanes,1..65536 steps per lane and
`lanes * steps <= 16777216`. The step counter bounds generated expressions and
statements across helper calls. It is separate from CPU/reference task budgets.
Lane status0 means success;1 overflow,2 division by zero,3 assertion,4 GPU step
limit,5 internal failure and6 invalid canonical input. A source diagnostic is
not a runtime lane status.

The public emitter's [scoped acceptance](evidence/macos-public-Metal-emission-0.165.0-2026-11-10.json)
passed20 reference/native Debug/Release/TypeScript/Metal cases with1799 oracle
lanes per layout. Rows and columns executed physically on Apple M5 Max, with48
dispatches including eight boundary dispatches; nine invalid host inputs were
rejected. The independent record also covers all native targets, six CLI tests
and actual JSON contract validation. This establishes the named scalar scope.

## Execute through owned NEX resources

The [owned-provider preparer](../experiments/owned-metal-codegen/README.md)
calls the selected compiler's public emitter with `columns` layout. The SDK
installs it with its worker sources and verification tools. Discover its paths
and exact scope with `nex describe --field gpu_codegen.owned_provider --json`.
It keeps
the exact emission record, source maps, canonical function hashes and shader
SHA256, then obtains nine actual FFI signatures and builds a pinned worker/module
bundle. Select a0.165 or later SDK and a source project containing the scalar root:

```sh
python3 -B "$NEX_SDK/share/nex/tools/owned-metal-codegen/prepare.py" --sdk "$NEX_SDK" \
  --source-project /absolute/path/to/project --symbol transform \
  --output /absolute/new/gpu-project --cxx "$(xcrun --find clang++)"
```

`--check-sdk` checks preparation and source signatures without native compilation
on other hosts. Native preparation requires macOS and its SDK. Execution uses
the generated project's `make_context`, `try_apply`/`apply` and the explicitly
granted `foreign.json`. See the preparer guide for a complete caller. Buffers and
read cursors retain their physical parents; cancellation and failures drain the
admitted GPU command before resource release. `try_apply` returns explicit
Results, while `apply` forwards original fatal codes through the trusted C API.

The same tools remain available under `experiments/owned-metal-codegen` in a
source checkout. Complete matching immutable SDK and platform qualification
remain pending. GPU operation debugging
and profiling, further types/backends and device-loss recovery are also pending.
Emitting a shader alone does not establish device execution or speedup.

## CUDA source emission

The same compiler also accepts `--kind cuda`. Discover its own subset with
`nex describe --field gpu_codegen.cuda --json`; the Metal fields above retain
Metal's narrower contract. The [CUDA result schema](../llm/cuda-emission.schema.json)
uses `nex.cuda-emission/1` and carries the same revision, compiler/descriptor
identities, reachable function hashes and declaration line mappings.

```sh
nex emit examples/gpu-cuda.nex --kind cuda --entry transform \
  --input-layout columns -o kernel.cu --json
```

CUDA accepts shared pure i64/f64/bool/unit functions, concrete scalar generic
instances, branches, loops, checked source/loop contracts and scalar matches
with ordered binding/wildcard guards or i64/bool literal patterns. Fixed records/enums, Results and bounded static device text are described below.
Unbounded containers/dynamic text allocation, source errors, finally, closures, indirect
calls, effects and recursion fail explicitly.
Unreachable unsupported functions are excluded.

Finite f64 uses IEEE754 binary64 bits in the same eight-byte words as i64.
Arithmetic and i64-to-f64 conversion specify round-to-nearest/ties-even; FMA
contraction is absent. Zero normalizes positive, subnormals are retained, and
NaNs/infinities fail with lane status7 (`E_FLOAT`). Binary remainder uses bounded
integer significand reduction. Source evaluation/trap order is preserved.
The optional `floating_point` result object describes reachable f64 use, even
if the root's signature contains only integers. Status8 denotes failure to
establish the host FP environment in developer host controls; device kernels
have no host FP environment.

The kernel is `nex_generated_cuda_map`. Rows accepts one input pointer; columns
accepts one pointer per parameter, followed by output and uint32 status pointers,
uint32 lane count and uint32 step limit. A zero-argument columns root has no input
pointer. Both layouts retain the bounds described above. Bool words are exactly
0/1 and unit results are0; failed outputs are0. Source emission needs no CUDA
headers, NVRTC, driver or NVIDIA device. It produces CUDA C++20 source, not PTX,
a binary or an automatic CPU fallback.

The owned CUDA preparer now uses this public command by default:

```sh
python3 -B "$NEX_SDK/share/nex/tools/owned-cuda-codegen/prepare.py" \
  --compiler "$NEX_SDK/bin/nex" --resources "$NEX_SDK/share/nex" \
  --source-project /absolute/project --symbol transform \
  --source-only --output /absolute/new/prepared-project
```

Native preparation is explicit on Windows/Linux: omit `--source-only`, select
`--nvrtc /absolute/library` (version12+) and an appropriate `--compute` target.
It embeds exact compiled PTX and checks eleven actual FFI signatures. All-f64
roots expose `try_apply_f64`/`apply_f64`; codecs use1024-value bounded calls for
columns of up to32768 values. Ordinary Results remain distinct from forwarded
fatal `E_FLOAT`, which skips source catches/finally after resource settlement.
Only an explicit foreign catalogue grants device access.

The promoted backend shares its implementation with the standalone developer
harness. Earlier scoped records establish [integer CUDA hardware execution](evidence/windows-checked-AST-CUDA-physical-0.165.0-2026-11-10.json),
[f64 host/IR/PTX semantics](evidence/cuda-f64-source-PTX-0.165.0-2026-11-10.json)
and [typed transport host behavior](evidence/owned-cuda-f64-host-0.165.0-2026-11-10.json).
Matching public-CLI, current owned-provider NVIDIA execution, sanitizer and
immutable SDK acceptance remain separate gates. GPU stepping/profiling and
dynamic GPU allocation remain unfinished.

## Fixed CUDA values and Results

Emission uses `nex.cuda-emission/2` when a reachable declaration/expression needs
fixed records, enums, Results or bounded device text.
Legacy scalar emission remains `/1` with its original kernel wire layout. No
source-language/graph migration or C/task ABI change is required. Both records
are described by the indexed CUDA schema. Query the actual compiler first.

The `/2` record adds `value_abi` (`nex.cuda-values/1`): root parameter/result word
widths, recursive field offsets, nominal names, enum tags and the exact text pool.
Each word is8 little-endian bytes. Fields appear in declaration order; nested
values are flattened. A record has the sum of its fields' widths, with one zero
word for an empty record. An enum has a tag followed by enough words for its
largest variant. All inactive/padding words are zero. Concrete generic instances
retain their concrete nominal type names. Maximum nesting is32, aggregate types128
and width64 words. Lists use the separately versioned bounded layout below. Authority-bearing types and unbounded allocation are rejected.

A Result uses tag1 for `ok`, with its payload at word1. Tag0 is an ordinary error:
words1/2 reference its code/message in the emitted text pool. Its total width is
`1 + max(payload_words, 2)`. Ordinary language restrictions on payload types
continue to apply: unit is a function result, not an aggregate payload. `ok`, `err`, `is_ok`, `error_code`, `error_message`,
`unwrap`, nested constructor patterns/guards and `?` are supported. `?` returns
an error Result with the caller's payload type; it never turns that error into
a fatal lane status. `unwrap(err)` produces fatal `E_RESULT` with the exact
`code + ": " + message`. Fatal status bits31 and0..19 encode the two text IDs:
`0x80000000 | (code_id << 10) | message_id`; bits20..30 must be zero. The explicit
provider validates both IDs and settles work before publishing the diagnostic.

Device text is an immutable reference into reachable UTF-8 literals, including
Result diagnostics. ID0 is empty text. There are at most1024 entries/64KiB total,
1023 UTF-8 bytes per entry, without NUL. Equality, literal patterns and Unicode
scalar `len` are supported. These restrictions bound transport and preserve the
existing fatal-packet limit; they do not alter ordinary NEX strings. Dynamic
concatenation/allocation is unsupported on this backend.

`as_i64(f64)` truncates toward zero and returns `result<i64>`. Values outside
`[-2^63, 2^63)` return `E_RANGE`; malformed nonfinite input still fails with
`E_FLOAT` before source execution. The conversion uses exact binary significand
bits and avoids an out-of-range C++ cast or a host-rounding dependency.

Rows places complete arguments consecutively for each lane. Columns contains
`parameter_words[i]` words per lane in input column i. Output has `result_words`
per lane. The kernel validates active fields in argument/declaration order,
normalizes f64 zero, rejects invalid bool/tag/text IDs and rejects nonzero padding.
Every failed output word is zero. Pattern bindings, assignment and returned
values are private copies; field access cannot mutate an earlier value.

Owned preparation embeds these widths and the exact pool. Its public byte-column
interface slices large columns into batches before uploading. Every C FFI upload
and output stays at most256KiB; source results are concatenated after physical
settlement and resource closure. Up to32768 logical lanes remain possible without
raising per-call budgets. Root all-f64 convenience functions keep their existing
contract; fixed aggregates use the described canonical byte layout.

See [the fixed-value example](../examples/gpu-values.nex). Current NVIDIA,
Compute Sanitizer and immutable SDK acceptance for this ABI remain pending until
the agreed milestone. Host source/control checks are not hardware execution.

Internal device helper parameters use read-only borrowing for aggregates and
return independent values. This compiler-private calling convention preserves
source value semantics and avoids a retained LLVM22.1.8 aggregate-parameter
machine-verifier failure. The public kernel wire layout is the `value_abi` record.

### Bounded immutable CUDA lists

Reachable `list<T>` values select emission `nex.cuda-emission/3` with
`nex.cuda-values/2`. Existing scalar `/1` and fixed-value `/2` layouts keep their
versions. Source list syntax and CPU semantics remain language0.28.

```sh
nex emit examples/gpu-lists.nex --kind cuda --entry transform \
  --list-capacity 32 --input-layout columns -o lists.cu --json
```

The CUDA-only `--list-capacity N` chooses1..1024 slots per list, default32.
Owned CUDA preparation accepts the same option. The limit is part of the exact
emission and wire metadata; hosts must read it rather than assume a capacity.
Lists containing other lists, records, enums or Results are supported when their
acyclic layout fits. A type containing lists has at most4096 eight-byte words;
a type without lists retains its64-word bound. Depth32 and128 aggregate types
remain enforced. Increasing capacity can exceed these layout limits.

Each list occupies `1 + capacity * element_words` words: word0 is its length,
followed by fixed-width element slots. Metadata gives `element_type`,
`element_words`, `capacity`, `length_offset` and `elements_offset`. Length must
be0..capacity. Every inactive word is zero, including inactive nested payloads.
Active elements are validated recursively, including bool/text IDs and finite
f64; negative f64 zero is normalized. Malformed length/padding is `E_GPU_INPUT`.

Supported operations are list literals, indexing, `len`, `push`, `set`, `+`,
structural equality and exact nested list patterns with guards. They preserve
immutable values and left-to-right evaluation. All call arguments evaluate
before the operation checks bounds/capacity: for example, division by zero in
`set(xs, -1, 1 / 0)` wins over the invalid index. Indexing and `set` trap with
status9 / `E_BOUNDS`, message `index is outside collection bounds`. `push` and
concatenation beyond the declared capacity trap with status10 / `E_LIMIT`,
message `device list exceeds declared capacity`. Oversized literals/patterns
are rejected during emission. This device resource bound does not constrain CPU
lists or introduce a source-level fixed-size list type.

The owned adapter accepts these statuses only for list ABI2. It splits logical
columns into physical batches using their declared word widths; every input and
output FFI transfer stays within256KiB. No device heap allocation, raw pointers
or additional authority is introduced. Device execution and matching SDK
qualification remain pending until the final platform gate.

### Packed immutable CUDA bytes

Reachable `bytes`, including nested record/enum/Result/list payloads, select
`nex.cuda-emission/4` and `nex.cuda-values/3`. The earlier scalar, fixed-value and
list-only versions keep their wire contracts. No source syntax/version or core
bytes behavior changes.

```sh
nex emit examples/gpu-bytes.nex --kind cuda --entry transform \
  --byte-capacity 256 --input-layout columns -o bytes.cu --json
```

The CUDA-only `--byte-capacity N` selects1..32760 octets, default256. The owned
preparer forwards it. A byte value occupies `1 + ceil(capacity / 8)` words:
word0 is its octet count; following words pack octets least-significant first.
The metadata describes `capacity`, `octets_per_word`, `octet_order`,
`length_offset` and `elements_offset`. Length must be0..capacity; every inactive
octet and word is zero. Invalid padding/length fails before source execution
with E_GPU_INPUT. Every type containing bytes/lists must fit4096 words; types
without either retain64 words. A maximum-size bytes root fits; a Result wrapper
at that same capacity needs one more word and is rejected. Choose capacity to
fit the whole reachable value layout.

Supported operations are `bytes(list<i64>)`, `len`, indexing, `slice`, `push`,
`set`, concatenation and structural equality. They copy values and preserve
snapshots. All operands evaluate once, left to right, before operation checks.
`set` checks index before octet range; `push` checks octet range before the
additional device-capacity bound. The constructor validates octets and returns
recoverable `E_RANGE` before applying that bound; it never silently truncates.
Nested Results, patterns, `?` and exact `unwrap` diagnostics remain available.

| Status | Diagnostic | Message |
|---|---|---|
| 11 | E_BOUNDS | `byte index is outside buffer bounds` |
| 12 | E_BOUNDS | `slice is outside byte buffer bounds` |
| 13 | E_RANGE | `byte value must be between 0 and 255` |
| 14 | E_LIMIT | `device bytes exceed declared capacity` |

The first three retain ordinary NEX diagnostics. The fourth is the explicit
backend resource limit. They are accepted only for byte ABI3; list statuses9/10
are accepted when lists are also reachable. Wide columns keep the same256KiB
FFI transfer bound through physical batching.

`utf8_bytes` and `decode_base64` accept the existing bounded static text IDs.
Encoding preserves their exact UTF-8 octets; base64 decoding preserves canonical
padding/alphabet/unused-bit validation and recoverable E_BASE64. The emitter
precomputes each text-pool entry; runtime selection still follows the source
value. A valid decoded buffer exceeding capacity traps E_LIMIT. Ordinary text
pool limits, including its NUL restriction, remain unchanged; byte buffers
support all octets, including zero. Dynamic text creation, `decode_utf8` and
`encode_base64` remain explicitly unsupported. Full GPU code generation, actual
NVIDIA execution, sanitizer and matching immutable SDK acceptance remain open.
