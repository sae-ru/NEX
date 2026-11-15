#!/usr/bin/env python3
"""Offline checks for dependency-build failure reporting; no Docker required."""
import contextlib
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/linux'))
from check import prepare_image


class PreparationTests(unittest.TestCase):
    def test_success_keeps_log_without_failure_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix='nex-image-log-') as folder:
            path = Path(folder) / 'image.log'
            console = io.StringIO()
            with contextlib.redirect_stderr(console):
                prepare_image([sys.executable, '-I', '-B', '-c', 'print("prepared")'], path)
            self.assertEqual(path.read_bytes(), b'prepared\n')
            self.assertEqual(console.getvalue(), '')

    def test_failure_preserves_exit_code_complete_bytes_and_bounded_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix='nex-image-log-') as folder:
            path = Path(folder) / 'image.log'
            console = io.StringIO()
            command = [sys.executable, '-I', '-B', '-c',
                       'import sys;sys.stdout.buffer.write(b"x"*100000+b"\\xff\\nupstream connection failed\\n");sys.exit(7)']
            with contextlib.redirect_stderr(console), self.assertRaises(subprocess.CalledProcessError) as failure:
                prepare_image(command, path)
            self.assertEqual(failure.exception.returncode, 7)
            self.assertEqual(failure.exception.cmd, command)
            self.assertEqual(path.read_bytes(), b'x'*100000+b'\xff\nupstream connection failed\n')
            self.assertIn('NEX checks have not started', console.getvalue())
            self.assertIn('upstream connection failed', console.getvalue())
            self.assertIn('\ufffd', console.getvalue())
            self.assertLess(len(console.getvalue()), 17000)


if __name__ == '__main__':
    unittest.main()
