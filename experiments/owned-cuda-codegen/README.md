# Owned generated scalar CUDA experiment

This checkout experiment connects the independent
[checked-AST CUDA emitter](../cuda-codegen/README.md) to the versioned NEX C FFI.
It prepares a selected pure scalar function, its reachable helpers and an owned
session/buffer/cursor interface. It is outside the public compiler descriptor
and installed SDK. Physical CUDA acceptance remains pending.

The preparer compares the emitter's frontend archive hash, program revision and
every reachable function hash with the explicitly selected compiler. It checks
the generated NEX wrapper and obtains nine actual FFI signatures. A mismatched
frontend or unsupported root fails before a provider bundle is created.
The compiler must support language 0.28, dependent resources, the source task
bridge and the append-only fatal trap API.

From a checkout with a built compiler and standalone CUDA emitter:

```sh
python3 -B experiments/owned-cuda-codegen/prepare.py \
  --compiler /absolute/build/nex --resources /absolute/NEX \
  --emitter /absolute/cuda-build/nex-cuda-emit \
  --frontend-archive /absolute/build/libnex_frontend.a \
  --source-project /absolute/scalar-project --symbol transform \
  --source-only --output /absolute/new/provider-project
```

Source-only preparation requires no CUDA library, driver, headers or GPU. It
retains the emitted source, function maps, graph comparisons, checked wrapper,
FFI hashes and provider inputs. Its generated header contains no compiled PTX;
this output is a preparation artifact, not an executable CUDA bundle.

For native preparation on Windows x86-64 or Linux, omit `--source-only` and
select an installed NVRTC 12+ library with `--nvrtc /absolute/path/to/library`.
Use a native emitter/frontend/compiler cohort on that host. `--cxx` can select
the C++20 compiler explicitly. The preparer uses
[NVRTC](https://docs.nvidia.com/cuda/archive/12.1.0/nvrtc/index.html)
to compile the exact generated CUDA to PTX without initializing a driver. The
default target is `compute_52`; `--compute` selects an explicit supported target.
The resulting GPU must support that target. Compilation logs, options and
NVRTC/PTX hashes are retained. The PTX is embedded in the provider module;
NVRTC is a build dependency. No vendor header or implementation is bundled.

The preparer then builds a pinned FFI bundle and checks its source and catalogue.
Native Windows/Linux preparation, NVRTC compilation and actual CUDA execution
have not yet been qualified for this new provider.

## Resource and execution contract

The generated wrapper exposes `make_context`, `try_apply` and `apply` with the
same byte-column interface as the generated Metal experiment. Each input column
contains one little-endian signed 64-bit word per lane; bool uses exactly 0/1.
The selected root has 0..8 columns. The provider enforces 1..32768 lanes,
1..65536 steps per lane and `lanes * steps <= 16777216`. Results are one 64-bit
word per lane, including unit 0 and bool 0/1.

```nex
let session:d::Session=unwrap(make_context());
let output:bytes=apply(session,[encode_i64s([1,2,3])],3,65536);
print(decode_i64s(output));
resource_close(session);
```

This caller belongs in the prepared server program with `!{task,ffi,io}` and
assumes a one-argument root. Execute with the prepared `foreign.json` granting
the selected bundle. `try_apply` returns an explicit result; `apply` forwards a
failed lane's original fatal code through the negotiated C host API.

Buffers retain their session; read cursors retain their buffer. The module uses
the [CUDA Driver API context stack](https://docs.nvidia.com/cuda/archive/12.1.0/cuda-driver-api/group__CUDA__CTX.html)
and serializes each session. Its fence drains admitted GPU work on cancellation
or an error before freeing events, output, inputs or session resources. Unknown
physical settlement retains resources and capacity. Lane status validation
precedes publication; the lowest failed lane determines the error. This design
still requires actual GPU tests for success, errors, parent lifetimes, context
restoration, cancellation, deadlines, resource limits, replay and memory checking.

`NEX_OWNED_CUDA_MAP_TRACE` enables JSONL identity, allocation, enqueue,
completion and cleanup events. Kernel timing uses CUDA events. GPU stepping,
operation-level attribution and public profiling integration remain pending.

## Local controls

```sh
python3 -B experiments/owned-cuda-codegen/check_sources.py \
  --compiler /absolute/build/nex --resources /absolute/NEX \
  --emitter /absolute/cuda-build/nex-cuda-emit \
  --frontend-archive /absolute/build/libnex_frontend.a \
  --output /absolute/new/controls
```

On macOS, `--host-unavailable-controls --cxx /absolute/path/to/clang++` also
builds the real host module with warnings treated as errors, then checks the
typed unavailable-driver result through the interpreter and native Debug/Release.
This exercises the FFI and constructor rollback without creating a CUDA context
or launching a kernel. It cannot qualify CUDA compilation or device execution.
The local [source evidence](../../docs/evidence/owned-cuda-codegen-source-0.165.0-2026-11-10.json)
records four prepared roots, 36 checked signatures, two rejected preparations
and 96 unavailable-driver calls across those three backends. A 256 KiB resource
limit admits one session reservation but not two unreleased reservations;
repeated constructor failures restored capacity on each call.
The full public compiler/platform/SDK and broader original roadmap gates remain.
