# Finite binary64 numbers

This is the implemented design and acceptance scope for the development
0.24 / language 0.11 milestone. Its verified host matrix is recorded below;
broader platforms and portable SDK delivery remain open. The preserved 0.23 SDK
and genuine language 0.10 SQL fixture are the migration baseline.

## Source and values

`f64` is a finite IEEE binary64 value. Decimal literals with a fraction or an
exponent denote f64 (`1.5`, `1e0`, `5e-324`); plain integer literals remain i64.
There is no implicit conversion between those types. A fraction needs digits
on both sides of its dot; an exponent needs digits after its optional sign.
Literal conversion rounds to nearest, ties to even. Overflow is rejected;
gradual underflow, including rounding to zero, is allowed. All zero values are
normalized to positive zero. NaN and infinities cannot enter the language.

The ordinary arithmetic operators apply to two equal numeric types. f64
operations round independently to binary64, nearest/ties-to-even, without
contraction or reassociation. Division and remainder by zero trap with
`E_DIV_ZERO`; a non-finite result traps with `E_FLOAT`. `%` is the truncating
remainder, with the sign of its dividend before zero normalization. Comparison
and structural aggregate equality use the ordinary finite numeric relation.
The runtime saves/restores its host floating environment around arithmetic;
NEX must not depend on a caller's rounding mode or leak status flags to it.

`as_f64(i64) -> f64` explicitly rounds an integer, with possible loss of
precision. `as_i64(f64) -> result<i64>` truncates toward zero and returns an
`E_RANGE` error when the result is outside the signed 64-bit range. There must
be no out-of-range C++ cast or LLVM conversion with undefined/poison behavior.

`number` is a builtin generic capability for i64/f64 arithmetic and negation;
it implies `add`, `ordered`, and `wire`. `integer` implies `number`, retaining
its previous contextual integer literals. `number` alone does not make an
i64 literal into an arbitrary T: use operands of T in generic arithmetic.
`add` and `ordered` gain the concrete f64 implementation. Floating literal
patterns are omitted: a binding with a guard expresses numeric selection and
the existing coverage checker remains honest about open numeric domains.

## Representation and boundaries

Native function parameters/results/slots use real double values, including
indirect calls and DWARF. Aggregate storage retains the existing scalar payload
slot and appends a distinct floating tag; its i64 bits are not an integer
conversion. Cleanup and reference ownership remain unchanged.

Use shortest round-trippable scientific decimal for print/str and JSON numbers,
with a lowercase `e`, no positive exponent sign or leading exponent zeros
(`1e0`, `1.25e0`, `5e-324`, `0e0`). This avoids backend-specific thresholds for
fixed notation. The pinned Dragonbox converter and ECMAScript
`toExponential()` provide the corresponding shortest decimal conversion.
Dragonbox avoids floating `to_chars`, whose macOS availability would otherwise
raise the existing target's minimum OS version from 13.0 to 13.3.
No locale participates. i64 wire values remain canonical decimal strings.
Decoders accept finite JSON numeric tokens for f64, including integer-shaped
numbers, with normal binary64 rounding. They reject strings and non-finite
results. f64 participates in recursive `wire` models, API schemas and clients.

Debugger captures must distinguish f64 from integer payload bits, reject
non-finite forged inputs, and preserve all finite values. Watch evaluation,
partial aggregate reads, callback captures, DAP children and source-deleted
replay must use the checked type. Scalar Z3 verification must explicitly reject
floating operations instead of treating their bit payload as an integer.

## Compatibility and acceptance

The source language is 0.11, with function/9 and program/10 canonical formats.
Migration must use the actual preserved 0.23 store,
retain old archived sources/history and persistent function/operation identities,
and require explicit new task/proof snapshot pins without changing their intent.

Acceptance includes native debug/release, reference and TypeScript agreement;
literal rounding, subnormals, ties, zero normalization and arithmetic boundaries;
conversion limits around 2^53 and both i64 bounds; left-to-right evaluation and
short circuit; aggregate/callback/generic use and cleanup on success/traps;
strict JSON, API schemas and browser execution; live/offline LLDB/DAP; actual
old-store migration; capability/prompt/pack consistency; the full CTest suite
and installed, source-free SDK checks on the verified platform matrix.

Authoritative conversion references:
[Dragonbox 1.1.3](https://github.com/jk-jeon/dragonbox/tree/3053a74ac81099591a12a55341a203d9688fbb92),
[ECMAScript binary64](https://tc39.es/ecma262/multipage/ecmascript-data-types-and-values.html#sec-ecmascript-language-types-number-type),
[ECMAScript toExponential](https://tc39.es/ecma262/multipage/numbers-and-dates.html#sec-number.prototype.toexponential).

Decimal/money types, transcendental math and hardware-specific fast-math modes
remain separate work; this design does not claim their semantics or performance.

## Current integration evidence (not a completed release)

The working 0.24 / language 0.11 compiler implements the primitive, literals and
number bounds, interpreter/native/TypeScript semantics, wire/API model support,
real double ABI/validation, exact full/partial watches and LLDB/DAP float reads.
Source semantics, native ABI/trap cleanup, generic context, generated clients and
genuine 0.10 migration are covered by tests/numbers.py, api_contracts.py and the
verification rejection cases. Native float operator calls preserve the host
environment; scalar aggregate transport uses bitcasts with scalar tag 2 (runtime
Value::Floating is tag 3). Canonical formats advance to function/9 and program/10.
All 27 regression suites passed on macOS ARM64, Linux ARM64 and emulated Linux
x86-64. The compiler/runtime/adapter/library inputs match the frozen Linux
source tree; the later browser example was additionally tested on each SDK.

The finite-number browser example is now part of the language pack and SDK
acceptance. Its native/TypeScript transitions and two independent production
interaction scenarios per Chromium/Firefox/WebKit engine passed; the tests
include JSON rounding, smallest subnormal, maximum finite value, zero
normalization and unchanged state after invalid input. The installed macOS
SDK builds identical browser assets and passes all nine maintained phases.
Linux ARM64 passed seven live debugger suites. Both Linux architectures passed
the updated source-free, network-disabled nine-phase SDK workflow, including
native/TypeScript numeric browser transitions and locked Vite builds. Linux
x86-64 is emulated and does not claim live debugging. STATUS.md records exact
counts, reports and remaining full-system scope. The conservative descriptor
marker for full platform/SDK validation remains until that broader coverage
and redistributable delivery are implemented and verified.
