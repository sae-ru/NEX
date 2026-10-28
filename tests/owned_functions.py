import json
import subprocess
import sys
import unittest

PROBE = sys.argv.pop(1)


class OwnedFunctions(unittest.TestCase):
    def test_actual_runtime_ownership_exits(self):
        process = subprocess.run([PROBE], capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        report = json.loads(process.stdout)
        self.assertTrue(report['ok'])
        self.assertGreaterEqual(report['cases'], 18)
        self.assertEqual((report['live_handles'], report['live_objects']), (0, 0))

    def test_unscoped_private_entry_is_rejected(self):
        process = subprocess.run([PROBE, '--unscoped'], capture_output=True, text=True, timeout=10)
        self.assertEqual(process.returncode, 70, process.stdout + process.stderr)
        self.assertIn('E_CONTEXT', process.stderr)


if __name__ == '__main__':
    unittest.main()
