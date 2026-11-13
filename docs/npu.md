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
portable SDK installation or a general NPU compiler. RK3588 RKNN was also exercised with the current fixture source and the retained
0.185 compiler: `nex eval` passed with **3 actual RKNPU calls**, `provider:
RKNN`, `rknpu_fd_open: true`, CPU fallback disabled. Native run/test were blocked
by the retained compiler's libstdc++ include discovery, so only eval is claimed
([RK3588 receipt](evidence/rk-npu-0.245.0-2026-11-13.json)). Apple NPU remains
pending current-toolchain acceptance.
