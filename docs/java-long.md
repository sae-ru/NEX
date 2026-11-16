---
status: current
applies_to: "language 0.30; toolchain 0.266.0"
owner: repository
---

# Explicit Java long semantics

`std/java_long.nex` supplies a nominal `Int64 { value:i64; }` domain for Java
primitive-long computations. It is ordinary checked NEX source, with 21 public
functions. It adds no syntax, compiler mode, JVM dependency or project converter.
Ordinary NEX `i64` operators remain checked.

```nex
import "std/java_long.nex" as longs;
fn example()->unit {
  let maximum:longs::Int64=longs::from_i64(9223372036854775807);
  let minimum:longs::Int64=longs::add(maximum,longs::from_i64(1));
  assert(longs::to_i64(minimum)==-9223372036854775808);
}
```

The [complete example](../examples/java-long/README.md) selects source0.30 and
includes multiplication, logical shifts, narrowing and a caught division error.
Discover `standard_library.modules.java_long` and read
`nex guide --kind java-long --json` on the selected compiler.

## Operations and conversions

`from_i64` and `to_i64` preserve the signed64 value; every i64 payload is a
canonical `Int64`. `add`, `subtract`, `multiply`, `negate` and the bitwise helpers
explicitly retain the low64 result bits. Raw i64, `Int32` and `Int64` operands
cannot be silently mixed. `compare` returns -1,0 or1 in signed order.

`divide` and `remainder` truncate toward zero and declare `!{throw}`. MIN/-1
returns MIN; MIN%-1 returns0. A zero divisor raises this module's nominal
`ArithmeticError { operation:str; }`, with `"divide"` or `"remainder"`.
It is distinct from `java_int::ArithmeticError` and from a fatal NEX arithmetic
trap. A Java exception hierarchy, causes, suppression and stack objects remain
separate work. Source `finally` and fatal cleanup keep their existing meanings.

`bit_and`, `bit_or`, `bit_xor` and `bit_not` operate on all64 bits.
`shift_left`, `shift_right` and `unsigned_shift_right` accept an i64 distance;
only its low six bits are used, including for negative distances. Signed right
shift propagates the sign; logical right shift inserts zeros. A masked zero
distance preserves the original pattern, including a negative value.

`from_int` sign-extends a canonical `java_int::Int32`. `narrow_int`,
`narrow_byte`, `narrow_short` and `narrow_char` return an `Int32` containing the
Java narrowing result. Char is an unsigned16 code-unit number; this API does
not change NEX's scalar-indexed UTF-8 strings or implement UTF-16 strings.

The contracts follow the Java specifications for
[integer operations](https://docs.oracle.com/javase/specs/jls/se26/html/jls-4.html#jls-4.2.2),
[division and shifts](https://docs.oracle.com/javase/specs/jls/se26/html/jls-15.html#jls-15.17.2)
and [narrowing conversions](https://docs.oracle.com/javase/specs/jls/se26/html/jls-5.html#jls-5.1.3).

## Representation, cost and ownership

This is a nominal aggregate over existing i64 source arithmetic, rather than a
new primitive machine type or Java boxed `Long` object. Ordinary immutable
snapshot, ownership, JSON and ABI rules apply. JSON retains the existing nominal
record shape and decimal-string i64 fields; it does not introduce another wire
format. Physical signatures must still be read from matching native metadata.

Addition checks the two overflow ranges before calculating a representable
wrapped result. Multiplication uses four base-2^16 columns, with ten partial
products. Every column and carry remains below2^34. Signed reconstruction starts
with a signed top16 digit and adds only the remaining nonnegative low48 bits,
keeping all intermediate values representable in checked i64.

Bitwise helpers operate through two canonical32 words and scan64 positions.
Shifts also use these word helpers. Direct native bit instructions, specialized
primitive lowering and comparable throughput remain unqualified; no Java/C++
performance claim follows from semantic agreement.

## Pins and qualification

The module imports `std/java_int.nex`. Both source hashes participate in ordinary
dependency locks and captured source graphs. Review changes before running
`nex lock`; retained archives keep their captured sources and identities. There
is no language-version migration for adding this source-library API.

The [handwritten JDK oracle](../tests/fixtures/java-long/Oracle.java) and
[fixed observations](../tests/fixtures/java-long/oracle.json) contain790 cases:
integer extremes, signed products/carries, division errors, MIN/-1, bits,
negative and cross-word shifts, narrowing and sign extension. An independent
unbounded-integer model checks the same results. Acceptance compares NEX
reference, native Debug/Release and strict executed TypeScript, together with
rejected type/effect programs and preserved ordinary checked overflow. Set
`NEX_JAVA_HOME` for a live JDK comparison; no project is parsed or translated.
Matching full source/platform/portable-SDK acceptance remains a separate gate.

[The0.266 record](evidence/java-long-0.266.0-2026-11-16.json) retains matching
compiler/source pins,20 unique core/affected groups, live JDK observations,
reference/native/TypeScript agreement, wire extrema, archive export and a moved
normal installation. That installation keeps host dependencies; it is not a new
portable SDK release.

По-русски: модуль явно задаёт арифметику Java `long`, включая переполнение и
сдвиги. Он расширяет основу для миграции; обычные операции NEX продолжают
проверять переполнение. Классы, библиотечная совместимость, Java IEEE-числа и
динамическая модель Python ещё требуют реализации.
