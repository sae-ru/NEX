"""Deterministic agreement generator: seeds, reproducers and a real run."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
COMPILER=Path(sys.argv.pop(1)).resolve()
GENERATOR=REPO/'tools/agreement_generate.py'
RUNNER=REPO/'tools/agreement.py'


def run(command,timeout=300,env=None):
    child=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=timeout,env=env)
    return child


def tree(root):
    return {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*')) if path.is_file() and path.name!='cases.json'}


class Generator(unittest.TestCase):
    def test_command_capture_preserves_utf8_and_exact_line_endings(self):
        # The controller may use a single-byte locale while NEX and Node emit UTF-8.
        sample='Я🌍\r\nA\rB\0\n\n'.encode()
        driver="""import runpy, sys
runner = runpy.run_path(sys.argv[1])
child = 'import sys; sys.stdout.buffer.write(bytes.fromhex(' + repr(sys.argv[2]) + '))'
result = runner['run']([sys.executable, '-c', child], '.', 30)
assert result['exit_code'] == 0
print(result['stdout'].encode('utf-8').hex())
"""
        env={**os.environ,'LC_ALL':'C','PYTHONCOERCECLOCALE':'0','PYTHONUTF8':'0'}
        result=run([sys.executable,'-B','-c',driver,RUNNER,sample.hex()],env=env)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),sample.hex())

    def test_seed_reproducer_and_real_agreement(self):
        with tempfile.TemporaryDirectory(prefix='nex agreement generator ') as temporary:
            root=Path(temporary)
            first=root/'first';second=root/'second';other=root/'other'
            for seed,directory in ((7,first),(7,second),(8,other)):
                result=run([sys.executable,'-I','-B',GENERATOR,'--seed',str(seed),'--count','3','--directory',directory,'--json'])
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                summary=json.loads(result.stdout)
                self.assertEqual((summary['seed'],summary['count']),(seed,3))
                self.assertEqual(hashlib.sha256((directory/'cases.json').read_bytes()).hexdigest(),
                                 summary['manifest_sha256'])
            self.assertEqual(tree(first),tree(second))
            manifest=json.loads((first/'cases.json').read_text())
            self.assertEqual(manifest['schema'],'nex.agreement/1')
            self.assertEqual(len(manifest['cases']),3)
            for case in manifest['cases']:
                self.assertEqual(case['kind'],'valid')
                source=(first/case['source']).read_bytes()
                self.assertEqual(hashlib.sha256(source).hexdigest(),case['program_sha256'])
            self.assertNotEqual(tree(first),tree(other))
            output=root/'run'
            result=run([sys.executable,'-I','-B',RUNNER,'--compiler',COMPILER,'--root',first,
                '--output',output,'--no-typescript'])
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads((output/'report.json').read_text())
            self.assertTrue(report['ok'],report['failures'])
            self.assertEqual(len(report['cases']),3)
            self.assertFalse(report['typescript_executed'])

    def test_selected_project_version_preserves_pinned_cases_and_reports_reduced_scope(self):
        with tempfile.TemporaryDirectory(prefix='nex agreement modes ') as folder:
            root=Path(folder)
            corpus=root/'cases'
            corpus.mkdir()
            source=(REPO/'tests/agreement/cases/cell_alias_snapshot.nex').read_bytes()
            (corpus/'cells.nex').write_bytes(source)
            portable={'name':'new','kind':'valid','source':'cells.nex','expected_stdout':'41\n42\n42\n'}
            pinned={'name':'legacy','kind':'rejected','source':'cells.nex','language':'0.28','expected_check_code':'E_TYPE'}
            (corpus/'cases.json').write_text(json.dumps({'schema':'nex.agreement/1','language':'0.28',
                'cases':[pinned],'additional_cases':{'0.30':[portable]}}))
            output=root/'run'
            env={**os.environ,'NEX_SKIP_TYPESCRIPT':'1'}
            result=run([sys.executable,'-I','-B',RUNNER,'--compiler',COMPILER,'--root',corpus,
                '--output',output,'--language-version','0.30'],env=env)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads((output/'report.json').read_text())
            self.assertTrue(report['ok'])
            self.assertEqual(report['requested_language'],'0.30')
            self.assertEqual(report['project_languages'],['0.28','0.30'])
            self.assertEqual([(r['name'],r['language']) for r in report['cases']],[('legacy','0.28'),('new','0.30')])
            self.assertFalse(report['typescript_requested'])
            self.assertFalse(report['typescript_executed'])
            self.assertEqual(report['coverage'],{'check':2,'reference':1,'native-debug':1,'native-release':1,
                'typescript':0,'typescript_executed':0,'typescript_strict':0,'executable_cases':1})

            old=root/'legacy-run'
            result=run([sys.executable,'-I','-B',RUNNER,'--compiler',COMPILER,'--root',corpus,
                '--output',old,'--no-typescript'])
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads((old/'report.json').read_text())
            self.assertEqual([(r['name'],r['language']) for r in report['cases']],[('legacy','0.28')])
            self.assertFalse(report['typescript_executed'])


if __name__=='__main__':unittest.main()
