---
status: current
applies_to: "language 0.28; toolchain 0.248.0"
owner: repository
---

# Explicit Java int semantics

`std/java_int.nex` is the first numerical foundation for
[language migration readiness](migration-readiness.md). It is an ordinary source
module using nominal `Int32 { value:i64; }` values. It adds no syntax or converter,
and does not change ordinary checked NEX arithmetic. Native machine-width i32,
Java float/double and the general Java object/exception model remain pending.
Toolchain0.266 separately adds an explicit [Java long domain](java-long.md).
No Java runtime is required to execute this NEX module.

```nex
import "std/java_int.nex" as ints;
fn example()->unit {
  let limit:ints::Int32=ints::from_i64(2147483647);
  let next:ints::Int32=ints::add(limit,ints::from_i64(1));
  assert(ints::to_i64(next)==-2147483648);
}
```

The [complete example](../examples/java-int/main.nex) selects language 0.29 and
also exercises a typed division error and `finally`. Query
`nex describe --field standard_library.modules.java_int --json` on the selected
compiler; review source changes before updating existing dependency pins.

## Values and arithmetic

`from_i64` performs Java-style narrowing: retain the low 32 bits and interpret
them as a signed value. `to_i64` returns the canonical signed value, sign-extended
to i64. `add`, `subtract`, `multiply`, and `negate` explicitly wrap to 32 bits.
Both operands are `Int32`; an ordinary i64 cannot be silently mixed with one.
This represents promoted int computations, not Java boxing or distinct byte,
short and char storage types.

`divide` and `remainder` take two `Int32` values and declare `!{throw}`. Division
truncates toward zero; `MIN/-1` returns `MIN`. Remainder has the dividend's sign
and `MIN%-1` returns zero. A zero divisor raises the nominal NEX
`ArithmeticError { operation:str; }`, with `"divide"` or `"remainder"`.
Catch it explicitly or declare `throw` in the caller. This error is not yet a
complete Java `ArithmeticException` object with inheritance, identity, stack,
cause and suppression behavior. Ordinary NEX arithmetic traps retain their
existing terminating behavior and are not converted into this source error.

The rules follow the [Java integer domain](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.2.2)
and [division/remainder specification](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.17.2).

## Bits, shifts and narrowing

`bit_and`, `bit_or`, `bit_xor`, and `bit_not` operate on the exact 32-bit pattern.
`shift_left`, `shift_right`, and `unsigned_shift_right` take an `Int32` value and
an i64 distance. Only the low five distance bits are used, including negative
or very large distances. Arithmetic right shift preserves the sign; unsigned
right shift fills with zeros. A zero masked distance leaves the pattern intact.
See the [Java shift rules](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.19).

`narrow_byte`, `narrow_short`, and `narrow_char` return an `Int32` containing the
value after the corresponding Java narrowing conversion: signed 8 bits, signed
16 bits, or unsigned 16 bits. A char result is a code-unit number; this operation
does not claim UTF-16 string support or convert lone surrogates to NEX text.

## Representation and acceptance

Public fields allow manually constructing an invalid representation. Functions
check that input values are within -2147483648..2147483647; construct values
through `from_i64`. The canonical range makes addition/subtraction and int
multiplication representable in checked i64 before reduction. Left shifts use a
nonnegative 32-bit magnitude and at most a 2^31 factor, whose product also fits
i64. Other operations retain those bounds.

The implementation uses source arithmetic and nominal values. Bitwise helpers
scan 32 positions. Machine-width types, direct native bit instructions and
representation optimization are separate work; no Java/C++ throughput claim is
made for this source implementation.

[The manual JDK oracle](../tests/fixtures/java-int32/Oracle.java) and
[recorded observations](../tests/fixtures/java-int32/oracle.json) cover 524 fixed
cases: boundary casts/arithmetic, division errors, MIN/-1, signed remainders,
bits and masked shifts. Tests compare the frozen JDK observations to an
independent mathematical model and actual NEX reference, native Debug/Release
and strict executed TypeScript. Set `NEX_JAVA_HOME` to a selected JDK for an
additional live comparison; without it, the frozen oracle is still verified
and all NEX backend checks execute. No project source is parsed or translated.

[The 0.248 record](evidence/java-int32-language-0.248.0-2026-11-15.json) retains
the live JDK comparison, all execution backends, selected-language diagnostics,
0.29 graph/context/patch/restore/export/import checks, 12 core groups and a
relocated local installation. Full compiler/platform/portable SDK qualification
is not claimed by this focused block.
