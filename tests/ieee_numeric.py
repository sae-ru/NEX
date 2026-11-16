"""Observe both IEEE kernels against retained JDK and exact rational results."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

from ieee_numeric_cases import cases, expected

parser = argparse.ArgumentParser()
parser.add_argument('probe', type=Path)
parser.add_argument('--fixtures', type=Path, default=Path(__file__).parent / 'fixtures/java-ieee')
args = parser.parse_args()


class IEEE(unittest.TestCase):
    def test_real_JDK_fixture_and_exact_mathematical_model(self):
        fixture = json.loads((args.fixtures / 'oracle.json').read_text())
        self.assertEqual(fixture['schema'], 'nex.java-ieee-oracle/1')
        self.assertEqual(fixture['generator_sha256'], hashlib.sha256(Path(__file__).with_name('ieee_numeric_cases.py').read_bytes()).hexdigest())
        self.assertEqual(fixture['java_sha256'], hashlib.sha256((args.fixtures / 'Oracle.java').read_bytes()).hexdigest())
        corpus = cases()
        self.assertEqual(fixture['case_count'], len(corpus))
        oracle_input = ''.join(' '.join(map(str, c)) + '\n' for c in corpus)
        self.assertEqual(fixture['input_sha256'], hashlib.sha256(oracle_input.encode()).hexdigest())
        actual = subprocess.run([str(args.probe)], input=''.join(json.dumps(c) + '\n' for c in corpus),
                                text=True, capture_output=True, timeout=60)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        lines = actual.stdout.splitlines()
        self.assertEqual(len(lines), len(corpus))
        self.assertEqual(len(fixture['results']), len(corpus))
        for case, retained, observed in zip(corpus, fixture['results'], lines, strict=True):
            with self.subTest(case=case):
                self.assertEqual(retained, expected(case))
                self.assertEqual(observed, retained)

    def test_rounding_flags_subnormals_conversions_and_thread_environment(self):
        actual = subprocess.run([str(args.probe), '--self-test'], text=True, capture_output=True, timeout=30)
        self.assertEqual(actual.returncode, 0, actual.stderr)
        self.assertEqual(json.loads(actual.stdout), {'ok': True})


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v'])
