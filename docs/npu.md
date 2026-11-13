# NPU status

NEX's `std/device` API accepts external GPU/NPU devices, but a general
model/kernel compiler and portable NPU provider remain pending.

## Current source on CIX P1

The current `experiments/cix-p1` source was prepared with the retained 0.165
Linux ARM64 SDK (language 0.28) and executed on a CIX P1 CD8160:

- 9 actual Mali-G720 GPU calls;
- 6 actual Zhouyi NPU calls;
- `cpu_ep_fallback_disabled: true`, `aipu_open: true`;
- `nex eval`, `nex run --profile release` and `nex test --profile release` passed.

See the [CIX NPU receipt](evidence/cix-npu-0.245.0-2026-11-13.json). The receipt
does **not** qualify the current 0.245 compiler on CIX, a portable SDK, or a
general NPU compiler. RK3588 RKNN and Apple NPU remain pending current-toolchain
acceptance.
