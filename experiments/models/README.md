# Experimental named model inference

This provider uses the ordinary language0.20 standard model contract and executes separately supplied ONNX artifacts
through a pinned native module and private child worker. Toolchain0.122 installs the source contract, guide and provider preparation files;
the earlier0.121 experiment and compatible0.120 hardware receipts remain preserved. It adds no language syntax,
implicit f64 conversion, owned model handle or task/FFI bridge.

The canonical `lib/model.nex` (installed as `std/model.nex`) defines named Tensor/Port/Model/Request/Response/Device/Context values.
Static dense ports use finite IEEE754 binary32 little-endian, U8, I8 or I32;
rank1..4,262144 elements and786432 combined input/output bytes are explicit
limits. Model SHA256, complete port metadata and precision are part of the
selected source binding. Both source and native adapter validate input bytes;
the runtime independently checks actual model port names, order, dtype and shape.
Model files are capped at32MiB. Broader formats, dynamic/scalar shapes, larger
artifacts and other targets remain planned.

Precision is explicit. `MatchCPU()` compares NPU output bytes with an additional
CPU reference in the child before returning selected NPU output; this costs an
extra inference. Traces attribute that CPU work as `precision-reference`, without
reporting it as fallback. `Vendor()` explicitly selects vendor arithmetic without
that comparison. F32 IO does not promise that every vendor kernel accumulates in
F32, or change NEX's finite f64 arithmetic. The exact-integer packing helpers
accept only integers in[-16777216,16777216]; arbitrary finite F32 data may use
raw bytes. Negative-zero bits remain intact in tensors.

`execute` validates the complete context, request and provider response. An
explicit device never switches to another accelerator. CPU fallback requires
`Fallback::CPU()` and only handles unavailable/unsupported placement. It invokes
the declared CPU model backend and reports the actual CPU device, reason and
fallback flag. Malformed responses, invalid data, nonfinite results, precision
mismatches, runtime faults and host stops remain errors. Context is an ordinary
non-wire server/ffi callable without a host grant; execution still requires the
operator's pinned foreign catalogue.

## Prepare

Current native preparation requires Linux ARM64, C++20, a compatible installed
NEX SDK and an installed ONNX Runtime with C API20. Zhouyi additionally needs
the vendor runtime/driver/operator directory. Preparation builds/checks a new
project and catalogue without initializing the runtime or device.

```sh
python3 experiments/models/make_fixtures.py --output /new/model-fixtures
python3 experiments/models/prepare.py --sdk /path/to/sdk \
  --model /new/model-fixtures/mul3x2/model.onnx \
  --spec /new/model-fixtures/mul3x2/spec.json \
  --example /new/model-fixtures/mul3x2/example.json \
  --ort-library /absolute/installed/libonnxruntime.so \
  --include /path/to/ONNX-and-Zhouyi-headers \
  --enable-zhouyi --operator-path /absolute/installed/operators \
  --output /new/model-project
python3 experiments/models/verify.py --sdk /path/to/sdk \
  --project /new/model-project --output /new/model-evidence
```

`--spec` uses schema `nex.model-artifact/1`: `id`, lowercase artifact `sha256`,
ordered `inputs` and `outputs` arrays of `{name,dtype,shape}`. Optional precision
is `match-cpu` or `vendor`; the default is `match-cpu`. `--precision` selects it
explicitly. Without `--example`, the generated program prints its model metadata
and exports `run(inputs,kind,fallback)`. With an example, it also tests known data.
Constant byte data uses existing strict base64 decoding, avoiding thousands of
scalar AST nodes. The installed SDK remains unchanged; the project vendors its
source model contract and checked compute dependency.

An enabled Zhouyi binding is a candidate route, not proof that the vendor accepts
every graph. The tested two-input MatMul graph is rejected by the installed CIX
EP when CPU EP fallback is disabled. The exact known assignment diagnostic is
reported as `E_MODEL_UNSUPPORTED`; other parse/runtime errors retain their own
classification. `--expect-npu-unsupported` only builds a negative acceptance
example which verifies denial and a separately requested actual CPU fallback.
It does not alter the production dispatcher or disguise CPU output as NPU work.

The worker loads the runtime through an explicit prepared path and model bytes
through the pinned bundle. Runtime SHA at preparation is provenance; it does
not make installed driver/operator dependencies immutable. Each call checks raw
ORT profiles: selected NPU nodes must all identify `ZhouyiExecutionProvider`,
with CPU EP fallback disabled and the physical AIPU descriptor observed. CPU and
precision-reference profiles identify `CPUExecutionProvider` separately.

## Lifetime, versioning and scope

Only bounded immutable byte lists cross the typed C value FFI. Vendor stdout and
stderr are confined to the child; parent machine JSON remains intact. The broker
polls host cancellation while queued and while waiting. Queued cancellation
starts no child. Failure/cancellation reaps the owned child and removes private
files. The60-second timer starts abort/drain; it is not a proof of a hard bound
on kernel/device settlement. There is no persistent worker/session cache or
source task integration in this experiment.

Keep NEX source, `nex.json`, vendored libraries, model/spec provenance and build
recipes in version control. Exact native bundles and model artifacts must remain
available wherever their pins are retained. Replay archives NEX source, not all
installed platform dependencies. The acceptance removes main/model/stdlib source
files for replay and standalone, then restores them. The standalone still needs
its pinned external catalogue/bundle and installed runtime/device dependencies.

The source contract passed native/reference/TypeScript, finite/shape/precision
checks,357 exact binary32 comparisons, response/fallback boundaries and native
managed-memory checks. Model acceptance and the production broker's controlled
process tests have separate receipts. A successful small model is not full Linux
compiler delivery, arbitrary-model support on every NPU or completion of PLAN.

## Verified CIX scope

The current provider was tested with the compatible0.120/language0.20 Linux
ARM64 SDK. MatchCPU acceptance ran reference/nativeRelease/tests/profile/build,
source-deleted replay and standalone for each fixture:

| Artifact | Selected CPU | Actual NPU | Extra CPU references | NPU refusal checks |
| --- | ---: | ---: | ---: | ---: |
| Mul, one3x2 F32 input | 7 | 7 | 7 | 0 |
| MatMul32, two F32 inputs | 14 | 0 | 0 | 14 |
| Add/Sub, two inputs/two outputs | 7 | 7 | 7 | 0 |

The MatMul fixture additionally checked7 explicit CPU fallbacks. Combined
selected outputs checked14588 values; NPU/CPU references compared126 values
bit-for-bit. Raw invalid FFI requests started no child. A separate three-command
Vendor-precision check ran3 CPU and3 NPU calls with no extra CPU reference;
replay/standalone were not part of that focused check. The production broker
passed17 controlled process/protocol/cancellation cases. The returned791-file
archive, current56+6 ORT profiles and retained previous56 profiles were independently
verified. Native managed-memory balances passed; this does not measure all vendor
allocations. Read [receipt hashes and limitations](../../docs/evidence/named-models-0.121-development.json).

For an LLM, read this guide and the vendored `stdlib/model.nex`, then query the actual
compiler with `nex describe --json` and `nex ffi --symbol model_run --json`.
Use the generated pinned definition and `run` function. Keep ordered port names,
dtype, static shape, model digest and precision together; use the advertised `std/model.nex` contract and do not infer general device
availability from these preparation files.
Use `--foreign /absolute/project/host.json` for eval/run/test/profile. A missing
host catalogue remains an error. Version the source/spec/preparation recipe and
artifact provenance, and retain the exact pinned model/bundle separately as
needed for reproducible delivery.

The owned fixture writer follows the
[official ONNX schema](https://github.com/onnx/onnx/blob/v1.17.0/onnx/onnx.proto3).
It writes tests, not a project converter. Existing C API/factory header licenses
and the matching NEX JSON notice are included in each prepared bundle.
