# NPU status

NEX's `std/device` API accepts external GPU/NPU devices, but a general
model/kernel compiler and portable NPU provider remain pending.

## Current source on CIX P1

The **current 0.245.0 compiler** was built natively on CIX and used to prepare
and execute the current `experiments/cix-p1` source on a CIX P1 CD8160:

- 12 actual Mali-G720 GPU calls;
- 8 actual Zhouyi NPU calls;
- `cpu_ep_fallback_disabled: true`, `aipu_open: true`;
- `nex eval`, `nex run --profile release` and `nex test --profile release` passed.

See the [current CIX NPU receipt](evidence/cix-npu-current-0.245.0-2026-11-13.json)
and the earlier retained-SDK [receipt](evidence/cix-npu-0.245.0-2026-11-13.json).
The current receipt qualifies this fixed fixture on the actual board, but not a
portable SDK installation or a general NPU compiler. RK3588 RKNN was exercised with current source at both the retained 0.185
compiler (**3 RKNPU calls**) and the **current 0.245 compiler** (**6 RKNPU calls**):
`provider: RKNN`, `rknpu_fd_open: true`, CPU fallback disabled. The current
compiler was built on RK3588 against the retained static LLVM22 archive; a
portability fix isolates the JSON formatter in its own RTTI-free translation
unit because that archive omits `format_adapter` typeinfo. The runtime keeps
dynamic_cast. Native run/test also pass with an explicit `NEX_CLANG` wrapper adding
`--gcc-install-dir=/usr/lib/gcc/aarch64-linux-gnu/11`, so the retained clang++
finds libstdc++ headers; the fixed native test `rk_npu::npu_test` passed
([current receipt](evidence/rk-npu-current-0.245.0-2026-11-13.json),
[retained receipt](evidence/rk-npu-0.245.0-2026-11-13.json)). Apple Neural Engine: a CoreML ReLU model's compute plan selected
`MLNeuralEngineComputeDevice` and executed with `CPU_AND_NE`, producing the
correct output on the M5 Max ([receipt](evidence/apple-coreml-ane-0.245.0-2026-11-13.json)).
This is a device experiment, not yet a NEX `std/device` provider; fixed-model
transport and general NPU compilation remain pending.
