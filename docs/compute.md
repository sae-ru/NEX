# Checked compute contract1

Toolchain0.121 adds `import "std/compute.nex" as compute`. The library uses
existing language0.20 types, effects, checked integers, immutable bytes and
source functions. It introduces no syntax, builtin, reserved name, canonical
format, execution ABI or language migration. Its imported source participates
in normal revision identity, dependency locks, archived replay and export.

## Data and exact arithmetic

`Tensor(dtype, shape, data)` is row-major immutable data. Supported dtypes are
`U8`, signed `I8` (two's-complement octets), and signed `I32` (little-endian).
`tensor`/`validate_tensor` check rank1..4, positive dimensions, at most262144
elements and1048576 bytes. Product bounds are tested before multiplication;
shape, dtype and exact byte count must agree. A raw structure constructor is
not validation. `from_i8`, `from_i32` and `to_i32` perform checked conversions;
there is no reinterpretation as NEX i64/f64 or implicit precision loss.

`Request(1,id,operation,inputs,Selection(kind,id),fallback)` has two inputs and
a nonempty correlation ID of at most128 Unicode scalars. An empty device ID
requests automatic selection of a device of the explicit kind. Operations:

- `Add()` takes same-shape U8 inputs and produces U8.
- `Affine(scale)` computes exactly `scale*a+b`, with scale0..255 and same-shape
  U8 inputs/output. Output overflow returns `E_COMPUTE_OVERFLOW`.
- `Matmul()` takes compatible rank2 I8 matrices and produces exact I32 output.
  The checked NEX CPU backend permits up to1048576 multiply-accumulates; it
  accumulates in i64 and returns an error if the final result cannot fit I32.

The CPU work ceiling is separate from interpreter/task host budgets. Large
reference oracles may need an explicit bounded `eval --steps`; no library call
renews a caller's budget. The native CPU implementation is compiled NEX source,
without a BLAS, vectorization or GPU speed claim. Float tensors, broadcasting,
other operations and optimized kernels remain planned extensions.

## CPU and explicit placement

```nex
import "std/compute.nex" as compute;

// Within a function:
let a:compute::Tensor=unwrap(compute::from_i8([1,2],[2,-3]));
let b:compute::Tensor=unwrap(compute::from_i8([2,1],[4,5]));
let job:compute::Request=compute::request("product",compute::Operation::Matmul(),
  [a,b],compute::Selection(compute::Kind::CPU(),""),compute::Fallback::Deny());
let response:compute::Response=unwrap(compute::execute_cpu(job));
assert(compute::to_i32(response.output)==ok([-7]));
```

`execute_cpu` requires explicit CPU selection; it cannot silently fulfill a GPU
or NPU request. The actual builtin device is `cpu`, provider `nex.compute.cpu`,
contract version1. Response carries version, request ID, output, device metadata
and separate fallback flag/reason. Its provider/version/provenance data describes
the implementation; it is not a hardware attestation or device kernel timer.
See [the complete runnable example](../examples/compute/main.nex).

## External provider contexts

`Context` contains at most16 external devices and an exact callable:

```nex
server fn(Request,Device)->result<Response> !{ffi}
```

Create it with the server `context(devices,callback)` factory. It validates
bounded nonempty identity/provider/version/provenance, unique device IDs and
nonduplicate typed capabilities. CPU identity is reserved for the library.
`Context` contains an ordinary opaque NEX callable and cannot satisfy `wire`,
JSON or browser messages. It is not an owned device/resource handle and contains
no host FFI grant. Existing language0.20 rules permit a genuine callable to be
forwarded opaquely through the trusted typed C value FFI; the native module cannot
invoke it or construct new callable authority. A resource-free Context may also
be passively captured by a pure CPU mapping callback. Calling its server/ffi
callback still requires server realm and ffi effects; hidden file/task captures
retain their existing ownership and parallel-capture guards. Request/Response/Tensor/Device are data
and may use the existing strict wire encoding. Metadata alone grants no native
execution: any actual FFI provider still needs explicit pinned bundle/catalogue
permission from the host.

`server execute(ctx,request) !{ffi}` validates the request and context before
selecting or invoking anything. Automatic selection chooses the first capable
matching device; an explicit device ID never switches to another accelerator.
The callback receives the selected device. Its response must preserve version,
correlation and exact device metadata, have the required output dtype/shape,
and claim no private fallback. Mismatches return `E_COMPUTE_RESPONSE`.
These checks validate structure/placement reports; numerical correctness and
actual device execution remain obligations of the trusted provider and its
independent device tests.

Fallback defaults must be explicit: `Deny()` returns unavailable/unsupported
errors. `CPU()` allows the library to use CPU only for `E_COMPUTE_UNAVAILABLE`
or `E_COMPUTE_UNSUPPORTED`, including absent device/capability. It reports the
actual CPU device, `fallback_used=true` and reason. Invalid requests, malformed
provider responses, range/overflow/precision errors, ordinary provider failures,
traps, host cancellation and exhausted budgets are never disguised as fallback.
The callback itself must not substitute a different device. A declared capability
may have additional provider constraints; return `E_COMPUTE_UNSUPPORTED` for them.

## Scope and next integration

The common typed contract and checked CPU backend are implemented here. The
previous [RK3588 fixtures](../experiments/rk3588/README.md) and CIX OpenCL/Zhouyi
fixtures have independent actual numerical/device receipts. Their adaptation
into this common Context has a separate RK3588 source-library receipt. The
experimental OpenCL provider now accepts U8 Add and Affine0..255 through its
pinned worker, including checked overflow and maximum262144-element images.
The same common-GPU project generator has now passed scoped CIX OpenCL execution
with its installed Mali-G720 runtime. Use `prepare.py --backend gpu --api compute`
and an explicit `--opencl-library`; see the provider guide for pinned bundles,
vendored source, provenance and remaining device-selection limits.
Provider discovery, broader kernels/models and current full SDK/platform
acceptance remain separate work. The [scoped common-API receipts](evidence/compute-opencl-0.121-development.json)
verify actual GPU/NPU dispatch on RK3588 with the compatible0.120 compiler;
they do not establish full compiler0.121 platform delivery.

All vendor runtimes must retain the pinned child boundary and bounded binary
frames; arbitrary vendor stdout cannot enter machine JSON. Owned device buffers,
zero-copy/async dispatch, persistent worker pools, general kernels/models and
source-task/FFI integration remain pending. A source Context is an immutable
callable value, not a new external-resource lifetime system.
