"""Observable language, native/interpreter, graph and LLM protocol checks."""
import json
import os
from pathlib import Path
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

NEX = str(Path(sys.argv.pop(1)).resolve())
REPO = Path(__file__).resolve().parents[1]


class ToolchainCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nex test ")
        self.root = Path(self.temp.name)
        self.file = self.root / "main.nex"

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args, ok=True, machine=True, cwd=None, env=None, timeout=60):
        command = [NEX, *map(str, args)]
        if machine:
            command.append("--json")
        result = subprocess.run(command, cwd=cwd or self.root, capture_output=True, env=None if env is None else {**os.environ, **env},
                                text=True, timeout=timeout)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        if machine:
            try:
                return json.loads(result.stdout)
            except ValueError:
                self.fail("Invalid JSON protocol output: " + result.stdout + result.stderr)
        return result

    def source(self, body):
        self.file.write_text(body)
        return self.file
