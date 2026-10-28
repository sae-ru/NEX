"""Independent byte/UTF-8/base64 oracle across managed C++ and TypeScript values."""
import base64
import json
import pathlib
import random
import subprocess
import sys
import unittest

PROBE, NODE = sys.argv[1:3]
del sys.argv[1:3]
RUNNER = pathlib.Path(__file__).with_name('bytes-values-runner.mjs')


def observed(value):
    encoded = base64.b64encode(value).decode('ascii')
    wire = json.dumps(encoded)
    try:
        text, valid = value.decode('utf-8'), True
    except UnicodeDecodeError:
        text, valid = 'E_UTF8', False
    return dict(ok=True, hex=value.hex(), length=str(len(value)), display=wire,
                wire=wire, wire_hex=value.hex(), utf8_ok=valid, utf8=text)


def oracle(request):
    op, *args = request
    if op == 'construct':
        numbers = [int(v) for v in args[0]]
        return dict(ok=False, code='E_RANGE') if any(v < 0 or v > 255 for v in numbers) else observed(bytes(numbers))
    if op == 'decode':
        try:
            if len(args[0].encode('utf-8')) > 1024 * 1024:
                raise ValueError()
            encoded = json.loads(args[0])
            if not isinstance(encoded, str):
                raise ValueError()
            decoded = base64.b64decode(encoded, validate=True)
            if base64.b64encode(decoded).decode('ascii') != encoded:
                raise ValueError()
            return observed(decoded)
        except (ValueError, UnicodeError):
            return dict(ok=False, code='E_JSON')
    value = bytes.fromhex(args[0])
    if op in ('at', 'set'):
        at = int(args[1])
        if at < 0 or at >= len(value):
            return dict(ok=False, code='E_BOUNDS')
        if op == 'at':
            return dict(ok=True, integer=str(value[at]))
        item = int(args[2])
        return dict(ok=False, code='E_RANGE') if item < 0 or item > 255 else observed(value[:at] + bytes([item]) + value[at+1:])
    if op == 'push':
        item = int(args[1])
        return dict(ok=False, code='E_RANGE') if item < 0 or item > 255 else observed(value + bytes([item]))
    if op == 'slice':
        start, count = map(int, args[1:])
        if start < 0 or count < 0 or start > len(value) or count > len(value) - start:
            return dict(ok=False, code='E_BOUNDS')
        return observed(value[start:start+count])
    if op == 'concat':
        return observed(value + bytes.fromhex(args[1]))
    return observed(value)


class ManagedBytes(unittest.TestCase):
    def compare(self, requests):
        source = ''.join(json.dumps(v, ensure_ascii=True) + '\n' for v in requests)
        expected = [oracle(v) for v in requests]
        for command in ([PROBE, '--stream'], [NODE, '--experimental-strip-types', '--disable-warning=ExperimentalWarning', str(RUNNER)]):
            completed = subprocess.run(command, input=source, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            values = [json.loads(v) for v in completed.stdout.splitlines()]
            self.assertEqual(len(values), len(expected))
            for i, (actual, wanted) in enumerate(zip(values, expected)):
                with self.subTest(runtime=command[0], case=i, request=str(requests[i])[:180]):
                    self.assertEqual(actual, wanted)

    def test_owned_values_and_host_boundaries(self):
        for command in ([PROBE], [NODE, '--experimental-strip-types', '--disable-warning=ExperimentalWarning', str(RUNNER), '--self-test']):
            completed = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
            self.assertIn('cases passed', completed.stdout)

    def test_independent_values_operations_and_utf8(self):
        rng = random.Random(0x4e455842)
        requests = [['value', text] for text in ('', '00', 'ff', '00ff8041', '80', 'c080', 'c328', 'eda080', 'f4908080', 'f09f92', 'efbbbf', bytes(range(256)).hex())]
        requests += [['value', text.encode('utf-8').hex()] for text in ('A\0B', 'Я🧠', '\ufefftext', 'e\u0301', '\u0000\U0010ffff')]
        for size in (0, 1, 2, 3, 4, 7, 31, 256, 1023, 4096, 16384):
            value = bytes(rng.randrange(256) for _ in range(size)).hex()
            requests.append(['value', value])
            for _ in range(8):
                at = rng.randrange(-1, size+2)
                byte = rng.choice((-1, 0, 127, 128, 255, 256))
                requests += [['at', value, str(at)], ['set', value, str(at), str(byte)], ['push', value, str(byte)]]
                start = rng.randrange(-1, size+2)
                count = rng.randrange(-1, size+2)
                requests.append(['slice', value, str(start), str(count)])
            requests.append(['concat', value, '00ff'])
        for numbers in ([], [0, 255], [-1], [256], [0, 1, 128, 255], [9223372036854775807], [-9223372036854775808]):
            requests.append(['construct', [str(v) for v in numbers]])
        for op in ('at', 'set', 'slice'):
            requests.append([op, '00', '9223372036854775807', '256'])
        self.compare(requests)

    def test_strict_wire_codec_and_size(self):
        requests = [['decode', text] for text in ('""', '"Zg=="', '"Zm8="', '"Zm9v"', '"Zh=="', '"Zm9="', '"AA-_"', '"AA== "', '"AA==\\n"', '"===="', '"A==="', '"AA==AAAA"', '[]', '{}', 'null', 'false', '7', '"Я"', '"AA==" trailing')]
        for value in (bytes(range(256)), b'\xef\xbb\xbfA\0', b'\xff' * 786429):
            requests.append(['decode', json.dumps(base64.b64encode(value).decode('ascii'))])
        requests.append(['decode', '"' + 'A' * 1048576 + '"'])
        self.compare(requests)


if __name__ == '__main__':
    unittest.main()
