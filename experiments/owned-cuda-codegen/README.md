# Owned generated scalar CUDA experiment

This experimental provider connects the public `nex emit --kind cuda` backend
to the versioned NEX C FFI. A standalone developer harness remains optional.
It prepares a selected pure scalar function, its reachable helpers and an owned
session/buffer/cursor interface. The compiler advertises its preparation tools in `gpu_codegen.cuda.owned_provider`;
source support and complete installed/hardware acceptance remain separate. Physical CUDA acceptance remains pending.

The preparer checks the public emission's compiler/descriptor identity, program
revision and every reachable function hash against the selected compiler. The
optional standalone mode also checks its frontend archive hash. It checks
the generated NEX wrapper and obtains eleven actual FFI signatures. A mismatched
frontend or unsupported root fails before a provider bundle is created.
The compiler must support language 0.28, dependent resources, the source task
bridge and the append-only fatal trap API.
The preparer also accepts finite `f64` roots. The wrapper exposes bounded
`encode_f64s`/`decode_f64s` and `try_apply_f64`/`apply_f64` for all-f64 roots.
Codecs exchange IEEE754 little-endian words in actual1024-value chunks, up to
32768 values per column, preserving standard C-call reference/byte/operation
limits. NaNs/infinities return `E_FLOAT`; zeros normalize positive. Status7 maps
to the original fatal `E_FLOAT` after physical settlement. These paths have
[actual reference/native Debug/Release host controls](../../docs/evidence/owned-cuda-f64-host-0.165.0-2026-11-10.json);
NVIDIA execution of this11-export module remains unqualified.

From a checkout with a built compiler:

```sh
python3 -B experiments/owned-cuda-codegen/prepare.py \
  --compiler /absolute/build/nex --resources /absolute/NEX \
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

The preparer then builds a pinned FFI bundle and a separate context probe, and
checks the source and catalogue. The probe uses the actual provider classes
with three CUDA contexts to test caller preservation, nested buffer cleanup,
reentry rejection before polling and constructor rollback. It runs explicitly
before the physical scalar/parent corpus.
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
Trace schema `nex.experimental-owned-CUDA-trace/2` identifies each allocation,
cursor parent and dispatch. The reader matches every dispatch's input/output
buffers to their allocation and release, checks completion before their release
and requires each cursor to close before its physical parent buffer.

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
It also compiles the context probe and runs its explicit
`--expect-unavailable` control. That control reports zero CUDA contexts and
does not qualify context-stack behavior on NVIDIA hardware.
This exercises the FFI and constructor rollback without creating a CUDA context
or launching a kernel. It cannot qualify CUDA compilation or device execution.
The local [source evidence](../../docs/evidence/owned-cuda-gate-source-0.165.0-2026-11-10.json)
records four prepared roots, 36 checked signatures, two rejected preparations
and 96 unavailable-driver calls across those three backends. A 256 KiB resource
limit admits one session reservation but not two unreleased reservations;
repeated constructor failures restored capacity on each call.
The later f64 transport record adds five prepared roots/55 checked signatures,
nine actual codec/fatal runtime processes and a repeat of the96 unavailable-driver
calls and15 parent-case source checks. The earlier record remains scoped to its
original module.
The full public compiler/platform/SDK and broader original roadmap gates remain.

## Scalar and parent-resource corpus

Use `fixture.nex` as `main.nex` in a new language 0.28 project and prepare its
`transform` root. The acceptance runner pins that exact root and checks the
same mathematical/lifetime programs used by the Metal provider:

```sh
python3 -B experiments/owned-cuda-codegen/verify.py \
  --compiler /absolute/build/nex --resources /absolute/NEX \
  --project /absolute/prepared-provider --check-only \
  --output /absolute/new/source-case-checks
```

`--check-only` checks all 15 NEX programs and loads no provider. On an available
Windows/Linux NVIDIA host, prepare a native provider first and omit this flag
to execute the interpreter/native Release pairs. The physical runner requires
exact values/errors, device identity, generated-source/PTX hashes, CUDA
completions, closed cursors and balanced buffer/event/context/module/stream
counters. It first requires the actual three-context probe to succeed.
This phase covers byte codecs, maximum geometry, typed errors,
parent retention, cross-session rejection, quotas and fatal error forwarding.
Actual NVIDIA execution of this phase remains unverified. Source-deleted
replay/standalone, other scalar roots and Compute Sanitizer also remain
mandatory gates. Its report never marks complete owned CUDA
acceptance.

## Captured replay and relocated delivery

`verify_delivery.py` exercises the ordinary compiler's task capture/replay and
application packager with this provider. Supply explicit native dependency
notices in the `nex.sdk-notices/1` format. Use a fresh output outside every NEX
project so temporary inputs cannot enter a parent semantic graph:

```sh
python3 -B experiments/owned-cuda-codegen/verify_delivery.py \
  --compiler /absolute/build/nex --resources /absolute/NEX \
  --project /absolute/prepared-provider \
  --notices /absolute/native-dependency-notices.json \
  --output /new/temporary/delivery-proof
```

The runner creates its own working project and current operator catalogue.
It captures and executes a checked task, builds a package, deletes its working
source/module/graph, then replays from the captured inputs. Replay without
explicit current authority must fail before module initialization. The package
moves to a path containing spaces, `%` and Unicode, then runs with a minimal
environment and absent `NEX_RESOURCE_DIR`. The original prepared project is
preserved. Native NVIDIA mode checks the baseline scalar values and complete
resource traces in all five interpreter/native/standalone processes; that mode
still needs physical qualification.

On macOS, use `--host-unavailable-control` with the `match-prepared` project
created by `check_sources.py --host-unavailable-controls`. This executes the
real FFI module and requires32 typed `E_COMPUTE_UNAVAILABLE` results per process.
It never substitutes CPU computation for a CUDA kernel. The relocated package
runs under a sandbox denying reads of the original project, compiler resources,
compiler executable and external operator catalogue. Four actual rejected
file-open controls check those denials. This OS denial control is specific to
macOS; it is not claimed for Windows/Linux.

The [local delivery record](../../docs/evidence/owned-cuda-delivery-host-0.165.0-2026-11-10.json)
passed capture, source-deleted replay, authority rejection and relocated
standalone execution:160 typed unavailable results across five processes,
zero CUDA contexts/allocations/launches. NVIDIA delivery, memory checking,
other roots and coherent public compiler/SDK acceptance remain pending.

## Compute Sanitizer

`memcheck.py` requires a successful complete physical `verify.py` report in
`nex.experimental-owned-CUDA-scalar-parent-verification/2` format. That report
pins the retained executable, source, build receipt, foreign catalogue, module,
generated source/PTX and context probe. Earlier reports and source-only controls
cannot qualify this run. Keep the native build outputs until it finishes:

```sh
python3 -B experiments/owned-cuda-codegen/memcheck.py \
  --hardware-report /absolute/physical-corpus/report.json \
  --sanitizer /absolute/CUDA/compute-sanitizer/compute-sanitizer \
  --output /new/generated-provider-memcheck
```

Use the native `.exe` tool on Windows. The runner instruments the exact15
retained applications and the three-context probe with NVIDIA
[memcheck and full leak checking](https://docs.nvidia.com/compute-sanitizer/ComputeSanitizer/index.html).
It does not build or evaluate another program. Fresh resource traces must match
the original device, physical work and balanced counters. Values, fatal errors,
pending work, post-enqueue cancellation and physical drain checks remain in
force. The original5000ms cancellation and2000ms deadline budgets are unchanged;
instrumentation that prevents those conditions causes a failed run.

Every error/leak summary must be present and zero, including later summaries;
nonzero or malformed ignored/suppressed counts are rejected. Windows uses named
pipes and Linux uses Unix domain sockets for the tool's local connection. A
300-second process-tree timeout fails the command and retires its launched
processes; it never acknowledges successful GPU settlement.

`check_memcheck.py` accepts explicit compiler/resources/project/output arguments.
Use a source-only gated baseline preparation for local controls. The
[local record](../../docs/evidence/generated-cuda-memcheck-source-0.165.0-2026-11-10.json)
checks all15 actual NEX programs, rejects a source-only report before resolving
the supplied tool, checks17 synthetic log contracts, including Windows CRLF,
and7 argument contracts,
detects changed input bytes, and retires a real timed-out POSIX parent/child.
These controls run no Compute Sanitizer or GPU. Native Windows/Linux memcheck,
the physical corpus, NVIDIA delivery and complete compiler/SDK qualification
remain pending for this generated provider.

## Cancellation and deadline controls

Cancellation/deadline preparation additionally requires `--acceptance-gate`.
That explicit option appends a separate device-clock delay kernel to the NVRTC
compilation input; the original emitted function, source hash and function map
are retained. The normal provider rejects activation through environment
variables. The accepted test range is 1..200000000 device cycles per kernel and
1..32 repetitions, with both values zero by default. It queues the delay kernels
and then the unchanged generated root in the same CUDA stream. See NVIDIA's
[device clock contract](https://docs.nvidia.com/cuda/archive/12.1.0/cuda-c-programming-guide/index.html#time-function).

The full runner checks 15 programs, including cancel with its original 5000 ms
task budget and deadline with its original 2000 ms budget. Those two controls
require actual queued/pending work, 32 admitted GPU delay kernels, observation
of busy after enqueue, a sticky host interruption and a dispatch-matched
successful physical drain before used buffers close. The measured pending
interval must be at least 0.5 s. The cycle bound is not a wall-time guarantee;
an early timeout or missing physical acknowledgement fails the test.

`check_acceptance.py` accepts the same compiler/resources/emitter/frontend/output
arguments as `check_sources.py`. It prepares the pinned fixture, checks the
15 programs with the actual compiler and exercises the receipt reader with
synthetic records. Nineteen false reports are rejected, including leaked buffers,
contexts/events/streams, missing completion, an unsettled state, an unclosed
cursor, CPU fallback, a different compiled PTX and release before a dispatch,
cursor or parent lifetime has ended. Synthetic records are not
GPU evidence. `--host-gate-config-controls --cxx /absolute/clang++` checks the
actual C++ configuration parser on macOS without loading CUDA: disabled,
minimum/maximum and eight malformed/out-of-range settings.
The [versioned gate controls](../../docs/evidence/owned-cuda-gate-source-0.165.0-2026-11-10.json)
retain the exact scope and code identities.

## Fixed aggregate columns

Public CUDA emission can return `nex.cuda-emission/2`. The preparer retains its
`value_abi`, exact text pool and parameter/result widths. `try_apply`/`apply` still
accept canonical byte columns. They split wide inputs before FFI so each upload
and physical output is at most256KiB, then concatenate settled batches. Existing
C-call budgets are unchanged. `result<T>` errors are encoded output values;
`unwrap(err)` is a distinct fatal E_RESULT with the original bounded diagnostic.
See [the value ABI](../../docs/gpu-codegen.md#fixed-cuda-values-and-results).
