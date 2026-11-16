"""Fixed IEEE vectors and an independent exact-rational rounding model."""
from pathlib import Path
import random
import sys

# tests/numbers.py is an existing compiler test, not the stdlib ABC module
# imported by fractions. Keep the exact oracle independent of that filename.
_search_path = sys.path[:]
try:
    sys.path[:] = [p for p in sys.path if Path(p or '.').resolve() != Path(__file__).resolve().parent]
    from fractions import Fraction
finally:
    sys.path[:] = _search_path


def layout(width):
    fraction, exponent = (23, 8) if width == 32 else (52, 11)
    bias = (1 << (exponent - 1)) - 1
    return fraction, exponent, bias


def parts(width, bits):
    f, e, bias = layout(width)
    sign = bits >> (width - 1)
    fraction, exponent = bits & ((1 << f) - 1), (bits >> f) & ((1 << e) - 1)
    category = ('nan' if fraction else 'infinity') if exponent == (1 << e) - 1 else (
        'normal' if exponent else 'subnormal' if fraction else 'zero')
    value = None
    if category not in ('nan', 'infinity'):
        significand = (1 << f) | fraction if exponent else fraction
        power = (exponent - bias if exponent else 1 - bias) - f
        value = Fraction(significand << power) if power >= 0 else Fraction(significand, 1 << -power)
        if sign:
            value = -value
    return sign, category, value


def special(width, kind, sign=0):
    f, e, _ = layout(width)
    return (sign << (width - 1)) | (((1 << e) - 1) << f) | ((1 << (f - 1)) if kind == 'nan' else 0)


def rounded(width, value, negative_zero=False):
    f, _, bias = layout(width)
    sign = int(value < 0 or value == 0 and negative_zero)
    value = abs(value)
    if value == 0:
        return sign << (width - 1)
    n, d = value.numerator, value.denominator
    power = n.bit_length() - d.bit_length()
    below = n < (d << power) if power >= 0 else (n << -power) < d
    if below:
        power -= 1
    unit = max(power - f, 1 - bias - f)
    numerator, denominator = (n, d << unit) if unit >= 0 else (n << -unit, d)
    q, remainder = divmod(numerator, denominator)
    if 2 * remainder > denominator or 2 * remainder == denominator and q % 2:
        q += 1
    if q == 0:
        return sign << (width - 1)
    if q < 1 << f:
        return (sign << (width - 1)) | q
    if q == 1 << (f + 1):
        q >>= 1
        unit += 1
    exponent = unit + f + bias
    if exponent >= 2 * bias + 1:
        return special(width, 'infinity', sign)
    return (sign << (width - 1)) | (exponent << f) | (q - (1 << f))


def expected(case):
    width, op, a_text, *tail = case
    fmt = lambda x, w=width: f'{x:0{w // 4}x}'
    if op in ('from_int', 'from_long'):
        return fmt(rounded(width, Fraction(int(a_text))))
    a = int(a_text, 16)
    sign, category, value = parts(width, a)
    if op == 'raw': return fmt(a)
    if op == 'canonical': return fmt(special(width, 'nan') if category == 'nan' else a)
    if op == 'neg_raw': return fmt(a ^ (1 << (width - 1)))
    if op == 'abs_raw': return fmt(a & ((1 << (width - 1)) - 1))
    if op == 'neg': return fmt(special(width, 'nan') if category == 'nan' else a ^ (1 << (width - 1)))
    if op == 'classify': return category
    if op in ('to_int', 'to_long'):
        bits = 32 if op == 'to_int' else 64
        lo, hi = -(1 << (bits - 1)), (1 << (bits - 1)) - 1
        return str(0 if category == 'nan' else (lo if sign else hi) if category == 'infinity' else min(hi, max(lo, int(value))))
    if op == 'convert':
        other = 96 - width
        bits = special(other, category, sign if category == 'infinity' else 0) if value is None else rounded(other, value, bool(sign))
        return fmt(bits, other)
    b = int(tail[0], 16)
    bsign, bcategory, bvalue = parts(width, b)
    if op in ('eq', 'ne', 'lt', 'le', 'gt', 'ge', 'compare'):
        if category == 'nan' or bcategory == 'nan':
            relation = (category == 'nan') - (bcategory == 'nan')
            return str(relation) if op == 'compare' else str(op == 'ne').lower()
        def order_key(s, c, v):
            return (0 if s else 2, 0) if c == 'infinity' else (1, v)
        left, right = order_key(sign, category, value), order_key(bsign, bcategory, bvalue)
        relation = (left > right) - (left < right)
        if op == 'compare':
            return str(bsign - sign if category == bcategory == 'zero' else relation)
        return str({'eq': relation == 0, 'ne': relation != 0, 'lt': relation < 0,
                    'le': relation <= 0, 'gt': relation > 0, 'ge': relation >= 0}[op]).lower()
    if category == 'nan' or bcategory == 'nan': return fmt(special(width, 'nan'))
    if op == 'sub':
        bsign ^= 1
        if bvalue is not None: bvalue = -bvalue
        op = 'add'
    if op == 'add':
        if category == bcategory == 'infinity' and sign != bsign: return fmt(special(width, 'nan'))
        if category == 'infinity': return fmt(special(width, 'infinity', sign))
        if bcategory == 'infinity': return fmt(special(width, 'infinity', bsign))
        return fmt(rounded(width, value + bvalue, bool(sign and bsign)))
    result_sign = sign ^ bsign
    if op == 'mul':
        if (category == 'infinity' and bcategory == 'zero') or (category == 'zero' and bcategory == 'infinity'):
            return fmt(special(width, 'nan'))
        if category == 'infinity' or bcategory == 'infinity': return fmt(special(width, 'infinity', result_sign))
        return fmt(rounded(width, value * bvalue, bool(result_sign)))
    if op == 'div':
        if category == bcategory and category in ('zero', 'infinity'): return fmt(special(width, 'nan'))
        if category == 'infinity' or bcategory == 'zero': return fmt(special(width, 'infinity', result_sign))
        if bcategory == 'infinity': return fmt(result_sign << (width - 1))
        return fmt(rounded(width, value / bvalue, bool(result_sign)))
    if op == 'rem':
        if category == 'infinity' or bcategory == 'zero': return fmt(special(width, 'nan'))
        if bcategory == 'infinity': return fmt(a)
        return fmt(rounded(width, value - int(value / bvalue) * bvalue, bool(sign)))
    raise AssertionError(op)


def cases():
    result = []
    rng = random.Random(267031)
    for width in (32, 64):
        f, e, bias = layout(width)
        positive = [0, 1, 2, (1 << f) - 1, 1 << f, (1 << f) + 1,
                    (bias << f) - 1, bias << f, (bias << f) + 1,
                    (bias << f) + 2, ((2 * bias) << f) | ((1 << f) - 1),
                    special(width, 'infinity'), special(width, 'nan'), special(width, 'infinity') | 1,
                    special(width, 'infinity') | ((1 << f) - 1)]
        for power in (-f - 1, 23, 24, 31, 32, 53, 54, 63):
            mid = (bias + power) << f
            positive.extend((mid - 1, mid, mid + 1))
        if width == 64:
            # Binary32 narrowing: subnormal/normal, even/odd ties and overflow.
            for power in (-150, -149, -126, 127, 128):
                mid = (bias + power) << f
                positive.extend((mid - 1, mid, mid + 1))
            for mid in (0x47efffffe0000000, 0x47effffff0000000,
                        0x3ff0000010000000, 0x3ff0000030000000):
                positive.extend((mid - 1, mid, mid + 1))
        edges = list(dict.fromkeys(positive + [x | (1 << (width - 1)) for x in positive]))
        text = lambda x: f'{x:0{width // 4}x}'
        for a in edges:
            for op in ('raw', 'canonical', 'neg_raw', 'abs_raw', 'neg', 'classify', 'to_int', 'to_long', 'convert'):
                result.append([width, op, text(a)])
        pairs = [(a, b) for a in edges[:30] + edges[-12:] for b in edges[::5]]
        pairs += [(rng.getrandbits(width), rng.getrandbits(width)) for _ in range(300)]
        # All signed-zero, NaN and infinity comparison combinations.
        special_edges = [0, 1 << (width - 1), special(width, 'infinity'), special(width, 'infinity', 1),
                         special(width, 'nan'), special(width, 'infinity') | 1]
        pairs += [(a, b) for a in special_edges for b in special_edges]
        for a, b in pairs:
            for op in ('add', 'sub', 'mul', 'div', 'rem', 'eq', 'ne', 'lt', 'le', 'gt', 'ge', 'compare'):
                result.append([width, op, text(a), text(b)])
        for bits in (32, 64):
            values = [-(1 << (bits - 1)), (1 << (bits - 1)) - 1, -1, 0, 1]
            for power in (23, 24, 31, 53, 54, 62):
                values += [s * ((1 << power) + d) for s in (-1, 1) for d in (-1, 0, 1)]
            values += [(1 << 54) + (1 << 30) + 1, -((1 << 54) + (1 << 30) + 1)]
            for value in dict.fromkeys(values):
                if -(1 << (bits - 1)) <= value < 1 << (bits - 1):
                    result.append([width, 'from_int' if bits == 32 else 'from_long', str(value)])
    return result
