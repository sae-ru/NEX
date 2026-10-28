"""Pre-language binary64 runtime acceptance; exact bits and independent oracles."""
import json
import math
import os
from pathlib import Path
import random
import struct
import subprocess
import sys
import unittest

PROBE = str(Path(sys.argv.pop(1)).resolve())
NODE = sys.argv.pop(1) if len(sys.argv) > 1 and not sys.argv[1].startswith('-') else os.environ.get('NEX_NODE', 'node')
ROOT = Path(__file__).resolve().parents[1]


def bits(value):
    return struct.pack('>d', value).hex()


def number(text):
    return struct.unpack('>d', bytes.fromhex(text))[0]


class FloatingRuntime(unittest.TestCase):
    def compare(self, requests, expected=None):
        encoded = ''.join(json.dumps(request) + '\n' for request in requests)
        results = []
        for command in ([PROBE], [NODE, '--no-warnings', str(ROOT / 'tests/float-runtime-runner.mjs')]):
            completed = subprocess.run(command, input=encoded, text=True, capture_output=True, timeout=60)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            values = [json.loads(line) for line in completed.stdout.splitlines()]
            self.assertEqual(len(values), len(requests))
            results.append(values)
        for i, request in enumerate(requests):
            with self.subTest(request=request):
                self.assertEqual(results[0][i], results[1][i])
                result = results[0][i]
                if 'bits' in result:
                    self.assertEqual(result['bits'], result['json_bits'])
                    self.assertEqual(result['display'], result['wire'])
                    self.assertRegex(result['display'], r'^-?[0-9](\.[0-9]+)?e-?(0|[1-9][0-9]*)$')
                if expected is not None:
                    for key, value in expected[i].items():
                        self.assertEqual(result[key], value)
        return results[0]

    def test_native_rounding_flags_threads_traps_ownership_and_storage(self):
        completed = subprocess.run([PROBE, '--self-test'], text=True, capture_output=True, timeout=60)
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        self.assertEqual(json.loads(completed.stdout), {'ok': True})

    def test_finite_bit_patterns_roundtrip_and_shared_shortest_decimal(self):
        values = [0.0, -0.0, 1.0, -1.25, 0.1, 0.3, 1e23, 1e-7, 1e21,
                  math.ldexp(1.0, -1074), math.ldexp(1.0, -1022), sys.float_info.max]
        for edge in [1.0, 0.1, 1e-6, 1e21, math.ldexp(1.0, -1022)]:
            values.extend([math.nextafter(edge, 0.0), math.nextafter(edge, math.inf)])
        randomizer = random.Random(230024)
        while len(values) < 2000:
            value = number(f'{randomizer.getrandbits(64):016x}')
            if math.isfinite(value):
                values.append(value)
        expected = [{'ok': True, 'bits': bits(0.0 if value == 0 else value)} for value in values]
        self.compare([['value', bits(value)] for value in values], expected)

    def test_arithmetic_exact_bits_against_python_and_javascript(self):
        pairs = [(1.0, 2**-53), (math.nextafter(1.0, 2.0), 2**-53),
                 (sys.float_info.max, 2.0), (2**-1022, 2.0), (2**-1074, 2.0),
                 (-5.5, 2.0), (1.0, 0.0), (0.0, 0.0), (-0.0, -1.0)]
        randomizer = random.Random(640023)
        while len(pairs) < 500:
            pair = tuple(number(f'{randomizer.getrandbits(64):016x}') for _ in range(2))
            if all(math.isfinite(value) for value in pair):
                pairs.append(pair)
        requests, expected = [], []
        operations = {'add': lambda a, b: a + b, 'sub': lambda a, b: a - b,
                      'mul': lambda a, b: a * b, 'div': lambda a, b: a / b, 'rem': math.fmod}
        for a, b in pairs:
            for operation, evaluate in operations.items():
                requests.append([operation, bits(a), bits(b)])
                if operation in ('div', 'rem') and b == 0:
                    expected.append({'ok': False, 'code': 'E_DIV_ZERO'})
                else:
                    value = evaluate(a, b)
                    expected.append({'ok': True, 'bits': bits(0.0 if value == 0 else value)} if math.isfinite(value)
                                    else {'ok': False, 'code': 'E_FLOAT'})
        self.compare(requests, expected)

    def test_checked_conversions_at_integer_and_precision_boundaries(self):
        integers = [0, 1, -1, 2**53 - 1, 2**53, 2**53 + 1, 2**53 + 3, -2**63, 2**63 - 1]
        self.compare([['from_integer', str(value)] for value in integers],
                     [{'ok': True, 'bits': bits(float(value))} for value in integers])
        floats = [0.0, -0.0, 1.9, -1.9, 2**-1074, -2**63, float(2**63),
                  math.nextafter(float(2**63), 0.0), math.nextafter(float(-2**63), -math.inf),
                  sys.float_info.max, math.inf, -math.inf, math.nan]
        expected = []
        for value in floats:
            if not math.isfinite(value):
                expected.append({'ok': False, 'code': 'E_FLOAT'})
            elif value < -2**63 or value >= 2**63:
                expected.append({'ok': False, 'code': 'E_RANGE'})
            else:
                expected.append({'ok': True, 'integer': str(int(value))})
        self.compare([['to_integer', bits(value)] for value in floats], expected)

    def test_strict_numeric_json_and_nonfinite_rejection(self):
        accepted = ['0', '-0.0', '1.25', '5e-324', '1e-9999', '9007199254740993', '\ufeff1.25']
        expected = [{'ok': True, 'bits': bits(float(text.lstrip('\ufeff')) or 0.0)} for text in accepted]
        self.compare([['decode', text] for text in accepted], expected)
        rejected = ['"1.25"', 'true', 'null', '[]', '{}', 'NaN', 'Infinity', '1e309', '-1e309',
                    '1.0 trailing', '01.0', '1.', '.5', '{"x":1,"x":2}']
        self.compare([['decode', text] for text in rejected], [{'ok': False, 'code': 'E_JSON'}] * len(rejected))
        self.compare([['value', bits(value)] for value in [math.inf, -math.inf, math.nan]],
                     [{'ok': False, 'code': 'E_FLOAT'}] * 3)


if __name__ == '__main__':
    unittest.main(verbosity=2)
