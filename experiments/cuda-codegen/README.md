The backend is now also available through `nex emit --kind cuda` and shares
its implementation with `src/cuda.cpp`. See [the public guide](../../docs/gpu-codegen.md#cuda-source-emission).
This directory retains standalone developer controls and historical receipts;
those earlier receipts keep their original scope.

# Checked-AST CUDA emission experiment

This separate source tool lowers checked language0.28 functions directly to CUDA
C++20. It uses the existing NEX frontend and canonical function identities. It
does not parse NEX again or translate generated Metal text. The initial lowering
walk follows `src/metal.cpp`; the CUDA runtime and kernel ABI are explicit here.

The public compiler now provides `nex emit --kind cuda`; this executable is an
optional standalone developer harness. The descriptor and language pack advertise
its exact scalar/fixed-value scope. Matching hardware and immutable SDK acceptance
remain separate. No syntax, graph format, task ABI or
language migration changes are introduced by this experiment.

## Build and emit

First build the matching NEX source. Select LLVM22.1, SQLite and OpenSSL3 as in the
root build guide. This independent CMake project links that build's frontend:

```sh
cmake -S experiments/cuda-codegen -B build/cuda-codegen \
  -DNEX_BUILD_ROOT=/absolute/path/to/NEX/build
cmake --build build/cuda-codegen -j 4
build/cuda-codegen/nex-cuda-emit /path/to/project transform columns kernel.cu
```

The project needs its ordinary `nex.json` and checked0.28 source. Emission
initializes no driver. Its experimental JSON record includes the actual frontend
archive SHA256, checked program revision, reachable canonical function hashes,
function line ranges, parameter/result types and exact CUDA source SHA256.
Source rejection happens before the selected output is opened.

The subset is shared pure concrete `i64`/`f64`/`bool`/`unit`, locals, assignment,
branches, bounded execution of loops, scalar `match` expressions/statements,
helper/concrete generic calls, assertions and lowered source contracts.
Unsupported reachable code is rejected. Only the
reachable call graph is emitted; unused server/foreign code is excluded. There
are at most8 root arguments,128 functions/call levels and16MiB of generated code.
Fixed records/enums/Results, bounded device text and nested constructor patterns
are supported with the versioned value ABI. Recursion, dynamic heap allocation,
source errors and closures remain unsupported. Scalar matches support integer/bool literals, immutable bindings,
wildcards, ordered lazy guards, nested values, unit arms and normal returns.
The subject is evaluated once. Each attempted arm consumes the lane budget;
false guards retain the original subject and later arms do not run after a match.
Exhaustiveness, unreachable patterns and binding mutability use the NEX checker.

## Physical ABI and arithmetic

`i64` is explicitly `long long` with a64-bit static assertion, including on
Windows where the C++ `long` type is32-bit. Arithmetic uses unsigned64-bit bits
and explicit checks, preserving `MIN / -1` overflow, `MIN % -1 == 0`, truncating
division, evaluation order and lazy boolean operands. Each lane has its own
remaining-step counter and fatal status. CUDA C++20 is required; see NVIDIA's
[NVRTC12.1 guide](https://docs.nvidia.com/cuda/archive/12.1.0/pdf/NVRTC_User_Guide.pdf).

The exported kernel is `nex_generated_cuda_map`. `rows` takes one interleaved
`const long long*`; `columns` takes one such pointer per argument, including no
input pointers for a zero-argument root. Both then take `long long* output`,
`unsigned int* errors`, `unsigned int lanes`, `unsigned int steps`. Lane/index
arithmetic widens before multiplication. Bool inputs must be exactly0 or1;
bool output is0/1, and unit output is0. Nonzero status always writes zero output:

| Status | Meaning |
|---|---|
| 0 | Completed lane |
| 1 | Checked integer overflow |
| 2 | Division/remainder by zero |
| 3 | Failed assertion or source contract |
| 4 | Lane step budget exhausted |
| 5 | Invalid checked control flow or value-function fallthrough |
| 6 | Noncanonical bool input |
| 7 | Non-finite f64 input or arithmetic result |
| 8 | Host lowering control cannot select its floating environment |

For `f64`, each eight-byte input/output word carries its IEEE754 binary64 bits.
Values are finite, and all zero inputs/results normalize to positive zero.
The emitter supports arithmetic, negation, comparisons, `as_f64`, concrete
`number` generics and binding/wildcard matches with guards. `as_i64` returns a
`result<i64>` and now uses the fixed-value ABI, with a recoverable E_RANGE
outside the integer domain. Floating literal
patterns are rejected by the ordinary NEX checker.

GPU arithmetic uses explicit PTX round-to-nearest/ties-to-even instructions;
separate operations cannot contract into FMA. Remainder reduces integer binary
significands, including subnormals, without a device math library. The exponent
reduction has at most2097 iterations. The device path uses no NVIDIA headers or
libdevice. See the [PTX instructions](https://docs.nvidia.com/cuda/parallel-thread-execution/index.html)
and [inline assembly constraints](https://docs.nvidia.com/cuda/inline-ptx-assembly/index.html).
The explicitly labelled CPU lowering control selects the default floating
environment for arithmetic and restores its caller's mode/status flags.

`verify_f64.py` checks exact word values/statuses, signed-zero normalization,
subnormals, non-finite rejection, overflow, zero division, uncontracted operations,
guard/evaluation order and geometry sentinels in both layouts. It compares
positive programs with actual NEX reference/native/TypeScript execution and
checks source fatal errors. It also compiles all layouts through Clang22.1,
`opt -passes=verify` and `llc -verify-machineinstrs` at O0/O2 for sm_52/PTX4.2 and
sm_86/PTX7.1. Supply explicit emitter/compiler/resources/frontend-archive/cxx,
LLVM `--llvm-bin` and a fresh `--output`; use the usual `NEX_NODE`/`NEX_TSC` paths.
The [versioned f64 evidence](../../docs/evidence/cuda-f64-source-PTX-0.165.0-2026-11-10.json)
records these compiler/CPU controls. NVRTC, ptxas and physical GPU acceptance
retain their own pending gates. Typed f64 transport and original fatal-status
mapping are implemented. Public CLI/value-ABI source checks and current native
NVIDIA/immutable SDK qualification remain distinct.

A trusted host must validate allocation shapes, every pointer, launch geometry
and budgets, then settle the GPU command and examine **all** statuses before
publishing a batch. Emitted source alone grants no device authority and adds no
NEX resource owner, task bridge, CPU fallback or general device discovery.

## Verification

`verify_source.py` executes generated kernels as an explicitly labelled **CPU
lowering control**, with host index variables and UBSan. It compares scalar
results/errors and untouched extra lanes in both layouts, then runs positive
NEX agreement tests on reference/native/TypeScript, checks reference fatal-error
precedence and verifies unsupported programs preserve an existing output file:

```sh
python3 -B experiments/cuda-codegen/verify_source.py \
  --emitter build/cuda-codegen/nex-cuda-emit --compiler build/nex \
  --cxx /path/to/clang++ --output /new/source-controls
```

Set the usual `NEX_NODE`/`NEX_TSC` paths for TypeScript tests. The initial source
control passed 28 fixtures, 56 layouts, 256 lane outcomes and 9 rejected programs.
Match cases cover guard traps, skipped arms, binding shadowing, generic patterns,
loops and a subject-once budget control. The original 16 fixtures / 32 layouts
retain identical emitted source, metadata and data; their separately queued
hardware check is still applicable to that exact subset. The 24 new match kernels
need their own physical qualification.
These results do not establish CUDA compilation or GPU execution.
The [versioned source evidence](../../docs/evidence/cuda-scalar-match-source-0.165.0-2026-11-10.json)
records the tested emitter, checked frontend and exact limits of these results.

### Offline LLVM compilation

`verify_ptx.py` compiles the pinned source corpus through actual Clang22.1,
LLVM IR verification and the NVPTX backend, without a CUDA driver or Toolkit.
`clang_device.h` supplies device attributes and uses Clang's own builtin register
header; NVIDIA headers, libdevice and host-runtime shims are not used. Select
`clang++`, `opt` and `llc` from the same LLVM22.1 installation:

```sh
python3 -B experiments/cuda-codegen/verify_ptx.py \
  --matrix /path/to/source-controls/report.json \
  --clang /path/to/llvm22/bin/clang++ \
  --opt /path/to/llvm22/bin/opt --llc /path/to/llvm22/bin/llc \
  --gate experiments/owned-cuda-codegen/gate.cu \
  --combined /path/to/gated-preparation/generation/compilation.cu \
  --output /new/offline-PTX-controls
```

The combined input is the actual two-argument columns preparation produced with
`--acceptance-gate` by the [owned CUDA experiment](../owned-cuda-codegen/README.md).
This maintained control expects the28-program source matrix, all56 layouts, the
separate gate and that combined input. It checks232 compilations: each source
at O0/O2 for sm_52/PTX4.2 and sm_86/PTX7.1. Both frontend and backend select the
PTX version explicitly; the initial no-Toolkit sm_86 run failed because Clang's
default PTX4.2 was too old. That diagnostic is retained with the evidence.

Every LLVM module passes `opt -passes=verify`; `llc -verify-machineinstrs` checks
code generation. The control checks64-bit addresses, kernel parameter widths,
target/PTX versions, no unresolved device functions and the gate's device clock.
It retains all IR, PTX, commands, diagnostics and source/tool hashes. The
[versioned compilation evidence](../../docs/evidence/cuda-offline-PTX-0.165.0-2026-11-10.json)
records the successful LLVM22.1.8 run on macOS ARM64. These are compiler controls;
NVRTC, CUBIN assembly, physical execution and SDK qualification remain separate.

`verify_device.py` separately uses an explicitly selected NVRTC12+ library and
the installed CUDA Driver API. It compiles the pinned `.cu` files as C++20 for
the selected physical GPU, records PTX and compiler logs, and checks actual
values/statuses, unchanged inputs and extra-lane guards. Completion events and
stream settlement precede copies and releases; allocation/free counts must
balance. Run it against the source-control `report.json` and retain the source
tree referenced by its relative shader paths:

```sh
python3 -B experiments/cuda-codegen/verify_device.py \
  --matrix /path/to/source-controls/report.json \
  --nvrtc /absolute/path/to/nvrtc-library --index 0 --output /new/physical-proof
```

Physical execution and a separate Compute Sanitizer run remain required. CUDA
event timing here is diagnostic evidence, not NEX source-level GPU profiling or
debugging. Successful source controls do not qualify a CUDA SDK or provider.

The separate [owned generated CUDA experiment](../owned-cuda-codegen/README.md)
prepares this emission for NEX sessions, buffers and tasks. Its source/FFI and
unavailable-driver host controls remain separate from NVRTC, physical resource
lifetime, cancellation and sanitizer acceptance.
