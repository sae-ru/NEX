---
status: development
applies_to: "toolchain 0.267.0 internal runtime kernel"
owner: repository
---

# Explicit IEEE numeric domains

The C++ runtime foundation in `runtime/nex_ieee.h` provides separate binary32
and binary64 value domains. These are internal preparation for the
[migration prerequisites](migration-readiness.md), not source types or operators.
Discover `ieee_numeric_kernel.public_source_enabled`; it remains false.
Ordinary NEX checked i64 and finite, zero-normalized f64 keep their contracts.

Each domain stores exact unsigned bits, including signed zero, infinities,
subnormals and all NaN payloads. Raw admission, classification, sign changes
and raw inspection use integer operations, so observing a signaling NaN does
not evaluate it or alter the caller's floating status.

Addition, subtraction, multiplication, division and truncating remainder round
once to the destination width with nearest/ties-to-even and gradual underflow.
Each operation restores the caller's floating environment. Destination-width
volatile operands/results prevent reassociation, contraction and a deferred
conversion after environment restoration. Arithmetic NaNs are canonical quiet
NaNs; raw payload propagation is not a portable arithmetic promise.

Primitive comparisons treat NaN as unordered and the two zeros as equal.
Java total comparison additionally orders negative zero before positive zero
and NaNs after positive infinity. Java integral casts truncate toward zero,
saturate out-of-range values and map NaN to zero. Long-to-binary32 conversion
is direct, avoiding double rounding through binary64. Binary32/binary64
conversions preserve signed zero and use canonical NaNs.
Width conversion uses integer significands and exact ties-to-even rounding,
including binary32 overflow/subnormal boundaries. It does not rely on an
out-of-range C++ floating cast; see the [C++ conversion rule](https://eel.is/c++draft/conv.double).

The normative Java contracts are [floating values and operations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.2.3),
[multiplicative operations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.17)
and [primitive conversions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.1.3).
The retained oracle uses actual JDK21, with handwritten primitive observations.
This is not a Java parser or project converter.

## Qualification and remaining integration

`tests/ieee_numeric_cases.py` defines a fixed corpus and an independent model
using exact rational values and integer ties-to-even rounding. The retained
JDK fixture has31,748 observations. `tests/ieee_numeric.py` compares the actual
C++ probe with that fixture and the mathematical model. Its additional native
checks exercise caller rounding/status, FTZ, signaling NaNs, per-thread
environments, subnormals and direct long-to-float conversion. The small existing
core float probe checks coexistence with ordinary finite NEX arithmetic.

Reobserve the JDK fixture without replacing retained evidence:

```sh
python3 -B tests/fixtures/java-ieee/observe.py --jdk /absolute/JDK/home \
  --output /new/evidence-directory
```

For independent O0/O2 builds from source or an installed `share/nex` tree:

```sh
python3 -B tests/ieee_numeric_build.py --compiler /absolute/clang++ \
  --output /new/kernel-evidence
```

The helper retains compiler versions, exact commands, input/log hashes and
actual results. Repeat `--compiler` to check another selected compiler; it
downloads nothing. Installed checks qualify the kernel's packaged sources,
not a portable SDK or NEX source-language IEEE execution.

Source type checking, literal/decimal rules, reference/native/TypeScript
lowering, wire/JSON/API representations, debugger/watch/ABI contracts and an
explicit history-preserving source-version migration remain pending. Java
boxed values and library math, Python numerical behavior and matching full
source/platform/portable SDK qualification are separate requirements. The
internal kernel alone does not close those requirements or establish speedup.

The [0.267 focused receipt](evidence/ieee-numeric-0.267.0-2026-11-16.json)
records16 core and3 affected CTest groups, actual JDK21 capture and exact
source/compiler/manifest identities. Ten independent O0/O2 builds from
installed resources pass the same corpus: macOS ARM64 Clang, Linux ARM64
Clang/GCC and emulated Linux x86-64 Clang/GCC. Linux uses existing immutable
local images with networking disabled. This qualifies the kernel only, not
source-level IEEE execution or a complete SDK/platform release.

The final normal installation also passes actual relocation and eight CLI
commands from `/private/tmp`, with automatic adjacent-resource discovery.
That check exposed an oversized quick guide:6392 bytes exceeded its6144-byte
contract. The guide is now6095 bytes, and the existing core discovery group
loads it as a regression guard. Focused discovery/quick-reference checks and
their native/TypeScript examples pass; this remains separate from full SDK
archive/source-free acceptance.
