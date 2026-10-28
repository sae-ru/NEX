"""Observable language, native/interpreter, graph and LLM protocol checks."""
import json
import hashlib
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


def database_rows(path):
    """Complete logical graph state, including local IDs and task history."""
    # SQLite can need WAL sidecars even for SELECTs after the writer exits.
    # Open an existing DB, then prohibit SQL writes while comparing every row.
    connection=sqlite3.connect(path.resolve().as_uri()+'?mode=rw',uri=True)
    connection.execute('PRAGMA query_only=ON')
    try:
        schema=connection.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
        tables=[r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return schema,{name:sorted(connection.execute('SELECT * FROM "'+name+'"').fetchall(),key=repr) for name in tables}
    finally:connection.close()


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

    def historical_store(self, language):
        """Restore a real archived SDK database without executing foreign binaries."""
        fixture=REPO/'tests/fixtures'/('language-'+language)
        metadata=json.loads(Path(str(fixture)+'.json').read_text())
        sql=Path(str(fixture)+'.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        self.assertEqual(self.file.read_text(),metadata['source'])
        self.assertEqual(hashlib.sha256(metadata['source'].encode()).hexdigest(),metadata['source_sha256'])
        directory=self.root/'.nex';directory.mkdir(exist_ok=True)
        # The genuine SDK 0.22 sidecar predates this optional filename field.
        # Keep its archived SQL/JSON bytes intact; NEX stores use graph.db.
        with sqlite3.connect(directory/metadata.get('database','graph.db')) as connection:
            connection.executescript(sql.decode())
            connection.execute('PRAGMA user_version='+str(metadata.get('user_version',0)))
        return metadata
