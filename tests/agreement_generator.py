"""Deterministic agreement generator: seeds, reproducers and a real run."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
COMPILER=Path(sys.argv.pop(1)).resolve()
GENERATOR=REPO/'tools/agreement_generate.py'
RUNNER=REPO/'tools/agreement.py'


def run(command,timeout=300):
    child=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=timeout)
    return child


def tree(root):
    return {path.relative_to(root).as_posix():hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob('*')) if path.is_file() and path.name!='cases.json'}


class Generator(unittest.TestCase):
    def test_seed_reproducer_and_real_agreement(self):
        with tempfile.TemporaryDirectory(prefix='nex agreement generator ') as temporary:
            root=Path(temporary)
            first=root/'first';second=root/'second';other=root/'other'
            for seed,directory in ((7,first),(7,second),(8,other)):
                result=run([sys.executable,'-I','-B',GENERATOR,'--seed',str(seed),'--count','3','--directory',directory,'--json'])
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                summary=json.loads(result.stdout)
                self.assertEqual((summary['seed'],summary['count']),(seed,3))
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


if __name__=='__main__':unittest.main()
