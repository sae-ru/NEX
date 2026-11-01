"""Observable language, native/interpreter, graph and LLM protocol checks."""
from sqlite_fixture import connection as sqlite_connection
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


def native_fixture_compiler():
    return json.loads(subprocess.check_output([NEX,'doctor','--json'],text=True))['native_compiler']


def host_toolchain_defaults(doctor):
    result={'schema':'nex.toolchain/1','target':doctor['host']}
    if os.name=='nt':
        result.update(compiler=doctor['native_compiler'],linker=doctor['native_linker'],
            archiver=doctor['native_archiver'],sysroot=doctor['native_sysroot'],
            windows={'runtime':doctor['native_windows_runtime'],'notices':doctor['native_windows_notices']})
    return result

def windows_notices(built):
    """Selected operator notices must survive the captured Windows runtime."""
    metadata=json.loads(Path(built['metadata']).read_bytes())
    selected=json.loads(metadata['toolchain_inputs'])
    path=selected.get('windows_notices','')
    if not path:return ''
    original=Path(path).read_bytes()
    captured=Path(metadata['runtime_source_projection'])/'third_party/windows-runtime-notices.txt'
    assert captured.read_bytes()==original,'operator Windows notices changed during capture'
    return 'Operator-supplied Windows UCRT/static C++ runtime notices\n\n'+Path(path).read_text()+'\n\n'
def __getattr__(name):
    # DAP clients reuse debugging.py from private host/probe processes. Import
    # alone must not execute that probe as if it were the compiler CLI. Actual
    # language tests discover their selected compiler when first needed.
    if name != 'CURRENT_LANGUAGE':
        raise AttributeError(name)
    language=json.loads(subprocess.check_output(
        [NEX,'describe','--kind','index','--json'],text=True))['language']
    globals()['CURRENT_LANGUAGE']=language
    return language


def database_rows(path):
    """Complete logical graph state, including local IDs and task history."""
    # SQLite can need WAL sidecars even for SELECTs after the writer exits.
    # Open an existing DB, then prohibit SQL writes while comparing every row.
    # These are private, quiescent test stores. Require an existing file before
    # opening it: the embedded Mac Python SQLite rejects file: URI paths.
    path=path.resolve()
    if not path.is_file():raise FileNotFoundError(path)
    connection=sqlite3.connect(str(path))
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
        destination=os.environ.get('NEX_TEST_FAILURE_ROOT')
        result=getattr(getattr(self,'_outcome',None),'result',None)
        rows=(list(result.errors)+list(result.failures)) if result else []
        # Python3.9 records phase errors on _Outcome until after tearDown.
        rows+=list(getattr(getattr(self,'_outcome',None),'errors',[]))
        failed=any(error is not None and (test is self or getattr(test,'test_case',None) is self)
                   for test,error in rows)
        if destination and failed:
            target=Path(destination)/(self.id()+'-'+self.root.name.replace(' ','_'))
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.move(str(self.root),str(target))
            print('Preserved failed fixture: '+str(target),file=sys.stderr)
        self.temp.cleanup()

    # Cold native C++ runtime compilation on Windows can exceed 60 s under
    # parallel CTest load. Source task deadlines and explicit call budgets stay
    # independent of this parent-process watchdog.
    def cli(self, *args, ok=True, machine=True, cwd=None, env=None, timeout=(180 if os.name == "nt" else 60)):
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
        manifest=self.root/'nex.json'
        if not manifest.exists():
            manifest.write_text(json.dumps({'schema':'nex.project/1','language':getattr(sys.modules[__name__],'CURRENT_LANGUAGE'),
                                            'entry':self.file.relative_to(self.root).as_posix()})+'\n', newline="\n")
        self.file.write_text(body, newline="\n")
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
        with sqlite_connection(directory/metadata.get('database','graph.db')) as connection:
            connection.executescript(sql.decode())
            connection.execute('PRAGMA user_version='+str(metadata.get('user_version',0)))
        return metadata
