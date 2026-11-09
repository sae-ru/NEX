# macOS SDK and LLVM22 float headers

The owned Metal provider exposed an interaction between the selected Apple SDK
and LLVM22.1.8's libc++ `float.h`. Apple's `math.h` requests `INFINITY` and `NAN`
through `__need_infinity_nan`; the libc++ wrapper's ordinary guard can discard
that request. Including math first instead can discard later `FLT_*`/`DBL_*`
definitions. Both failures were reproduced with the real packaged compiler.

The macOS SDK bundler changes only its newly copied, exactly pinned libc++
wrapper. A partial request delegates to the next `float.h` before entering the
ordinary header guard. The original complete header remains intact inside the
other branch. No numerical constant or compiler feature is redefined. Native
LLVM/MLIR22.1, C++20, language0.28 and taskABI7 remain unchanged.

The bundle records source and patched SHA256 values in
`share/nex/licenses/sdk/llvm22-float-compat.json`. Its normal inventory pins the
resulting bytes and retains the original LLVM source/license provenance.
An unknown header digest stops assembly before rewriting it. Source LLVM
installations and existing SDKs are untouched. Both include orders must retain
`FLT_MAX`, `DBL_MAX`, `INFINITY`, `NAN` and standard finite/NaN predicates.

The original Metal worker then compiled unchanged with packaged Clang22 and the
private header correction. Matching complete SDK, relocation and physical Metal
acceptance still need their actual gates. This header correction is not a
general claim about every Apple SDK or LLVM version.

Primary implementation references: LLVM's [partial float header protocol](https://github.com/llvm/llvm-project/blob/main/clang/lib/Headers/float.h)
and the newer [libc++ cfloat forwarding](https://github.com/llvm/llvm-project/blob/main/libcxx/include/cfloat).
