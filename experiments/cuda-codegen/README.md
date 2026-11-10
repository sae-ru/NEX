# Checked-AST CUDA emission experiment

This separate source tool lowers checked language0.28 functions directly to CUDA
C++20. It uses the existing NEX frontend and canonical function identities. It
does not parse NEX again or translate generated Metal text. The initial lowering
walk follows `src/metal.cpp`; the CUDA runtime and kernel ABI are explicit here.

This is not an installed `nex emit --kind cuda` command. The compiler descriptor
and language pack continue to advertise their actual public Metal backend.
Public CLI integration, a generated owned CUDA provider, coherent SDK delivery
and broader types/backends remain pending. No syntax, graph format, task ABI or
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

The subset is shared pure concrete `i64`/`bool`/`unit`, locals, assignment,
branches, bounded execution of loops, scalar `match` expressions/statements,
helper/concrete generic calls, assertions and lowered source contracts.
Unsupported reachable code is rejected. Only the
reachable call graph is emitted; unused server/foreign code is excluded. There
are at most8 root arguments,128 functions/call levels and16MiB of generated code.
Recursion, heap values, f64, source errors, closures and aggregate patterns remain
unsupported. Scalar matches support integer/bool literals, immutable bindings,
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
