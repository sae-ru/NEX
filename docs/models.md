# Named model contract

Toolchain0.122 provides `std/model.nex`, an ordinary language0.20 library for
validated named tensor/model requests, explicit precision and provider dispatch.
Query `nex describe --field model --json` before use. It changes no language
syntax, canonical format, effect/realm semantics or migration requirement.

```nex
module model_input;
import "std/model.nex" as m;

fn main()->unit !{io} {
  let input:m::Tensor=unwrap(m::from_exact_i32("X",[3,2],[-2,-1,0,1,2,3]));
  assert(unwrap(m::to_exact_i32(input))==[-2,-1,0,1,2,3]);
  print(encode_base64(input.data));
}
```

`Port(name,dtype,shape)` defines an ordered input/output. `Tensor` adds immutable
row-major `bytes`. Dtypes are F32, U8, I8 and I32; numeric words use little-endian
encoding. F32 bytes must encode finite IEEE754 binary32 values, including
subnormals and signed zero. NaN/infinity are rejected. This does not narrow NEX
f64 or specify a vendor kernel's internal arithmetic. The exact-integer helpers
accept only integers in[-16777216,16777216]; use explicit raw bytes for other
finite binary32 values. `is_sha256` validates lowercase64-hex syntax; it does
not calculate a digest.

`Model(id,sha256,precision,inputs,outputs)` binds the artifact digest, complete
port metadata and precision policy. IDs/port names are bounded Unicode strings
without NUL. Each direction needs1..16 unique ordered ports, rank1..4 with
positive dimensions and at most262144 elements per port. Combined input/output
storage is capped at786432 bytes, within the normal typed-FFI copy budget.
`validate_model`, `tensor` and `validate_request` return recoverable errors for
invalid metadata/data; every provider independently validates its native input.

`Precision::MatchCPU()` requests a separately attributed CPU comparison;
`Precision::Vendor()` selects vendor arithmetic without that extra inference.
A provider must implement or reject the policy. CPU reference work is not
fallback and its cost must be reported separately. No built-in inference engine
is supplied by this library, including for explicit CPU requests.

## Select a provider

Import `std/compute.nex` for `Kind`, `Selection` and `Fallback`.
`Device(kind,id,provider,version,provenance,models)` advertises complete supported
model bindings. A server Context holds checked devices and an ordinary
`server fn(Request,Device)->result<Response> !{ffi}` callback. Create it with
`context`, create a request with `request`, then call `execute` from a server
function declaring ffi. Context is non-wire and grants no host permission.
It is not an owned model/device resource. Existing opaque callable forwarding
and passive resource-free capture rules still apply; invocation needs server/ffi.

An explicit device ID never switches to another accelerator. Dispatch checks
version/correlation, exact model digest/ports/precision, complete selected
device and output tensor validity. Provider responses cannot invent fallback.
`Fallback::CPU()` handles only unavailable/unsupported placement and invokes the
declared CPU provider. The final response reports its actual CPU device, flag
and reason. Invalid input/output, precision mismatch, runtime failures, traps,
cancellation and host limits remain errors. A model/device descriptor alone
does not prove physical execution.

## Prepare an external ONNX provider

Check the actual source template and foreign signature against your installed
compiler before supplying a native runtime or model:

```sh
python3 /path/to/sdk/share/nex/tools/models/prepare.py --sdk /path/to/sdk --check-sdk
```

This mode checks the compiler's source-FFI capabilities, parses/checks the real
provider template with vendored model/compute libraries, and queries its actual
foreign signature in a temporary project. It works on any SDK host and does not
build a native worker, load an inference runtime or execute a device. The result
reports the checked language, compiler/library/source hashes and signature hash.
Normal preparation still targets Linux ARM64. The template checker also prevents
an old fixed list of language versions from rejecting a compatible newer SDK.

The installed `tools/models/prepare.py` generates a pinned project/catalogue
from a separate self-contained model, its SHA256/port spec and an installed ONNX
Runtime C API20. Current native preparation targets Linux ARM64. The operator
supplies runtime, compatible headers and optional Zhouyi operator directory;
these installed dependencies remain outside the bundle's immutable pin.

```sh
python3 /path/to/sdk/share/nex/tools/models/prepare.py \
  --sdk /path/to/sdk --model /path/model.onnx --spec /path/spec.json \
  --ort-library /absolute/libonnxruntime.so --include /path/headers \
  --output /new/model-project
cd /new/model-project
/path/to/sdk/bin/nex run --foreign ./host.json --json
```

The generated project vendors both standard source libraries and binds its
prepared native module, worker, model, normalized spec and notices by manifest.
Preparation checks signatures/source/catalogue without initializing a device.
Without `--example`, main prints metadata and exported `run` accepts validated
tensor input. Add `--example` to check known data; Zhouyi is opt-in via
`--enable-zhouyi --operator-path /absolute/operators`.

The current compatible0.120 CIX experiment ran two small F32 graphs on Zhouyi;
a two-input MatMul graph was refused when CPU EP fallback was disabled. These
[recorded receipts](evidence/named-models-0.121-development.json) retain their
exact earlier source/compiler scope. They do not validate every graph or the
new0.122 installed SDK. The matching library/delivery gates are recorded in
STATUS.md. Other formats, dynamic/scalar shapes, larger artifacts, owned device
buffers/session handles, persistent workers and task/async integration remain
pending.

Keep source, `nex.json`, ordered specs, model provenance and preparation recipes
in Git. Retain exact pinned model/bundle artifacts and dependency versions for
replay/deployment. Source replay does not package the installed driver/runtime.
