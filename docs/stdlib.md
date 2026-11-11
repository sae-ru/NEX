# Checked source standard library

Toolchain0.167 extends the ordinary0.28 source modules. These functions compile
through the same checker/reference/native/TypeScript pipeline as application
source. No new syntax, builtin operation, authority or language migration is
introduced. Discover the selected compiler before importing:

This capability indexes the text/list/math helpers in this stage. Network, UI,
compute, model and provider modules retain their separate descriptor sections;
absence from this small index does not disable those libraries.

```sh
nex describe --field standard_library --json
nex guide --kind stdlib --json
```

```nex
import "std/text.nex" as text;
import "std/list.nex" as seq;
import "std/math.nex" as math;
```

Use `seq` or `lists` as the list import alias: `list` is a reserved type keyword.
The module's logical name is `std::lists`. Imports are checked source dependencies,
not implicit globals. The [runnable project](../examples/stdlib/nex.json) includes
its reviewed dependency lock.

## Text

| Function | Behavior |
| --- | --- |
| `starts_with(value,prefix)` / `ends_with(value,suffix)` | Existing exact, case-sensitive checks; empty prefix/suffix matches. |
| `join(list<str>,separator)` | Concatenate in order; empty list gives `""`. |
| `find(value,needle)` | First Unicode scalar index, or `-1`; empty needle gives0. |
| `split(value,separator)` | Left-to-right non-overlapping matches, retaining leading/trailing/adjacent empty fields. |
| `replace(value,needle,replacement)` | Replace all non-overlapping matches; no regex or replacement interpolation. |
| `trim(value)` | Remove leading/trailing Unicode17.0.0 `White_Space`; preserve interior text. |

All comparisons are exact. No normalization, locale or case folding is implied.
An empty split separator returns Unicode scalar strings (`"xЯ🌍"` becomes
`["x","Я","🌍"]`); empty input then returns `[]`. A nonempty separator on empty
input returns `[""]`. An empty replacement needle inserts before, between and
after scalars; on empty input it inserts once. Embedded NUL is ordinary text.
Scalars are not grapheme clusters, so a combining sequence can be split.

Trim uses the25 code points in the pinned
[Unicode17.0.0 property data](https://www.unicode.org/Public/17.0.0/ucd/PropList.txt).
It preserves U+200B, U+FEFF and Python's extra U+001C..U+001F whitespace.

The search is an independent NEX implementation of the Two-Way algorithm by
[Crochemore and Perrin](https://monge.univ-mlv.fr/~mac/Articles-PDF/CP-1991-jacm.pdf);
the [CPython algorithm notes](https://raw.githubusercontent.com/python/cpython/main/Objects/stringlib/stringlib_find_two_way_notes.txt)
also explain its periodic-memory and critical-factorization rules. Search uses
byte indices internally over already-valid UTF-8. A valid nonempty needle starts
with a leading byte, so a match starts/ends on scalar boundaries. Public `find`
converts the byte position to a scalar index. No arbitrary byte slice is exposed
as unchecked text.

For n input bytes and m needle bytes, search needs O(n+m) comparisons and a
constant number of search indices; UTF-8/bytes conversion still costs storage.
Split searches/counts then constructs balanced field lists: O(n+m+k log(k+1))
work for k fields. Join uses balanced concatenation, O(k+B log(k+1)) copied bytes
for B output bytes; replacement also includes its O(n+m) search work. These
source implementations avoid repeatedly copying a growing prefix. They do not
claim a linear-time text builder or a measured throughput improvement.

## Lists

| Function | Contract |
| --- | --- |
| `map<T,U>(values,fn(T)->U)` | One call per input, left-to-right; ordered output. |
| `filter<T>(values,fn(T)->bool)` | One call per input, left-to-right; preserve selected order. |
| `fold<T,U>(values,initial,fn(U,T)->U)` | Left fold; empty input returns initial. |
| `any` / `all` | Short-circuit in input order; empty results false/true respectively. |
| `find_index(values,predicate)` | First matching index, or `-1`. |
| `reverse(values)` | A new reversed list; input/aliases stay unchanged. |
| `sort_by(values,less)` | Stable mergesort; pure `less` must be a strict weak ordering. |
| `sort<T:ordered>(values)` | Ascending i64/f64; use `sort_by` for records or other supported values. |

Callbacks have no declared effects. These are sequential helpers and create no
worker threads, channels or implicit IO grants. Ordinary instantiated value,
realm, capture and ownership checks still apply. Use the separate `parallel_map`
operation only when its concurrency limits/semantics are intended. Effect
polymorphism and linear bulk builders remain pending.

The immutable representation copies references on concatenation. Balanced
map/filter/reverse cost O(n log(n+1)) copies, with O(log(n+1)) recursion depth.
Fold/any/all/find_index traverse at most n elements, excluding callback cost.
Sort performs O(n log(n+1)) comparisons and O(n log²(n+1)) reference copies:
each merge itself builds a balanced output rather than a quadratic push loop.
These bounds are explicit limitations, not a claim of C++ vector throughput.
Callback work, value construction and comparison costs are additional.

## Integer math

`min`, `max`, `clamp` and `abs` keep their existing i64 signatures. `clamp` checks
`lower<=upper`; `abs(MIN)` remains a checked overflow. New functions:

- `sign(value)` returns -1/0/1 without negating MIN.
- `floor_div(a,b)` and `ceil_div(a,b)` round the exact quotient toward negative
  and positive infinity. Divide-by-zero and MIN/-1 retain checked traps.
- `pow_i64(base,exponent)` uses exponentiation by squaring, O(log(exponent+1))
  multiplications. Exponent must be nonnegative (`E_ASSERT`);0⁰ is1. All products
  are checked, and the unnecessary final square is skipped (so MIN¹ is valid).
- `gcd(a,b)` and `lcm(a,b)` return a nonnegative `result<i64>`. Gcd(0,0) is0;
  lcm with either operand0 is0. Negative magnitudes allow MIN inputs without
  overflowing abs. An unrepresentable positive answer returns `E_MATH_OVERFLOW`;
  it is an ordinary result value, distinct from fatal arithmetic traps.

## Pins and validation

The compiled descriptor contains SHA256 pins for the three source files. CMake
refreshes them when a library file changes. `nex lock` still uses its existing
content-hash dependency format. A pre-existing project with old pins must fail
until its dependency update is reviewed and `nex lock` is run explicitly. A
retained graph/export keeps its captured old library; no pin is silently rewritten.
Commit the source/manifest and reviewed `nex.lock.json`; keep `.nex/` out of Git.

Focused checks cover the actual algorithms, Unicode/NUL/empty boundaries,
stable ordering/immutability, integer extremes, rejected effects/types and a
guarded dependency update. Reference/native Debug+Release and strict/executed
TypeScript are separate observations. Complete SDK/platform qualification and a
new versioned local-Qwen efficiency study remain pending.
