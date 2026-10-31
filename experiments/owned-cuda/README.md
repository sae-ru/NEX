# Owned CUDA on native Windows

This provider runs the CUDA Driver API through the versioned NEX C FFI. It uses
the installed Windows NVIDIA driver and CUDA headers, LLVM-MinGW, and PTX; it
does not invoke WSL, MSYS, NVCC, or an unsupported host-compiler override.

From the repository root in PowerShell:

```powershell
python experiments/owned-cuda/prepare.py --output build/my-cuda
Push-Location build/my-cuda
& ../../nex.cmd run --foreign foreign.json --profile release --json
Pop-Location
```

Preparation requires a new output directory and records the compiler, source,
signature, DLL, standard-library, license and manifest hashes. It does not
initialize the driver or claim hardware acceptance. The example selects CUDA
device ordinal zero; use `--index` to select a different physical device.

The checked GPU kernels implement exact U8 Add and Affine on 1..262144 elements.
Affine computes `scale * a + b`, with scale 0..255. Overflow is a typed error,
including when only the last element overflows. I8 and I32 buffers support
storage and round trips. Matmul is explicitly unsupported by this provider;
the compute library can use CPU fallback only when the caller permits it and
the result qualifies for fallback. Overflow and device API errors do not
silently become CPU success.

Sessions and buffers are owned FFI resources. Buffers retain their physical
session even after its public handle closes. Every operation serializes its
session and rejects reentry into an active session. Cancellation and deadlines
stop source execution, then wait for physical CUDA completion before releasing
buffers, events, modules, contexts, DLL code or capacity. If the driver cannot
confirm completion, the provider reports an unsettled state and retains its
resources instead of reporting free capacity.

Run the complete hardware acceptance matrix explicitly:

```powershell
python experiments/owned-cuda/verify.py `
  --compiler build/windows-host/nex.exe `
  --project build/my-cuda `
  --output build/my-cuda-verification
```

This checks the independent reference evaluator and native release executables,
actual GPU identity, arithmetic boundaries, overflow recovery, resource aliases,
scope return, typed exception payloads, close/revoke behaviour, cancellation and
deadlines after real GPU enqueue. JSONL traces account for physical completion
and each allocation/free pair. The two interruption cases use bounded repeated
GPU kernels to keep work pending without a single long watchdog-sensitive
kernel. Those test controls default to off in ordinary use.

A separate native host probe uses two real CUDA contexts to check buffer cleanup
inside nested session contexts, restored current-context identity, reentry rejection
and constructor rollback. Preparation compiles this probe without initializing CUDA;
the explicit hardware verifier runs it before the NEX acceptance matrix.

On 2026-10-31, the full 35-case matrix passed on a native Windows RTX 3090. The
receipt belongs to its exact pinned compiler and module; it is not acceptance
of unrelated Windows regressions or another provider build. Full Windows CTest
and all-target build results are recorded separately.
