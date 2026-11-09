# Exact Metal Matmul prototype

This checkout experiment extends the owned Metal provider with row-major
I8×I8→I32 Matmul through the existing NEX language0.28 `std/device` API.
The frozen0.163 SDK qualification still covers its original Add/Affine provider.
This prototype is not installed or advertised by that SDK. General GPU code
generation, arbitrary kernels and Apple NPU remain separate work.

The GPU accumulates each dot product using a low unsigned word and a signed high
word. It checks the final signed32 range before publishing a buffer. An
intermediate sum outside I32 may return into range; it must not be rejected
early. An exact sum of2³² must not become a valid zero. Integer products and
accumulation use no floating approximation or CPU substitute. The existing
262144-element input/output bounds limit all accesses and accumulation ranges.
The largest permitted matrix product has134217728 multiply-accumulates.

I32 output is explicit little-endian bytes. A full262144-element output is1MiB.
Reading uses a private resource cursor and chunks of at most262144 bytes so
each FFI call stays within the original copy budget including metadata.
The cursor physically retains its Buffer, which retains its Session; an
admitted read can finish after the original owners close. New reads from a
closed tensor are rejected. Cursor cleanup also runs on errors and cancellation.
Upload retains the documented1044480-byte transport bound.

The provider's framed protocol is version3, and its eight signatures are
obtained from the actual selected compiler. They differ from the installed
Add/Affine provider, so prepare a new bundle and preserve its exact manifest.
Use new output directories:

```sh
export SDKROOT="$(xcrun --sdk macosx --show-sdk-path)"
NEX_SDK=/absolute/path/to/current/nex-sdk
python3 -B experiments/owned-metal-matmul/prepare.py --sdk "$NEX_SDK" \
  --output /absolute/new/matmul-project --cxx "$(xcrun --find clang++)"
python3 -B experiments/owned-metal-matmul/verify.py --sdk "$NEX_SDK" \
  --project /absolute/new/matmul-project --output /absolute/new/matmul-hardware
python3 -B experiments/owned-metal-matmul/faults.py --sdk "$NEX_SDK" \
  --project /absolute/new/matmul-project --output /absolute/new/matmul-replies
python3 -B experiments/owned-metal-matmul/logs.py --sdk "$NEX_SDK" \
  --project /absolute/new/matmul-project --output /absolute/new/matmul-logs
```

Source-only `prepare.py --check-sdk` does not initialize a driver. Actual
hardware verification covers signed values, CPU agreement within the CPU work
limit, both I32 endpoints, overflow/recovery, both prefix-overflow directions,
maximum outputs/work, resource parent lifetime, cancellation and deadlines.
Larger GPU cases use exact known integer results because the independent source
CPU backend has its own1048576-operation work limit. Malformed replies and
large private diagnostics have separate physical cleanup checks. Test scripts
record results; source presence alone establishes no hardware acceptance.
