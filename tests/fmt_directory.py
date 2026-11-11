"""Directory-scoped nex fmt check/write."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()

def run(args,cwd):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=120)

class FmtDirectory(unittest.TestCase):
    def test_check_write_ignore_and_errors(self):
        with tempfile.TemporaryDirectory(prefix='nex fmt dir ') as temporary:
            root=Path(temporary);src=root/'src';(src/'.nex').mkdir(parents=True);(src/'nested').mkdir()
            (src/'a.nex').write_text('module a;\nfn main()->unit{print(1);}\n')
            (src/'nested'/'b.nex').write_text('module b;\nfn x()->i64{return 1;}\n')
            (src/'.nex'/'ignored.nex').write_text('module ignored;\nfn y()->unit{}\n')
            (src/'notes.txt').write_text('unchanged\n')
            checked=run(['fmt','src','--check','--json'],root);self.assertEqual(checked.returncode,1,checked.stdout+checked.stderr)
            report=json.loads(checked.stdout);self.assertEqual(report['schema'],'nex.format-directory/1')
            self.assertFalse(report['ok']);self.assertEqual(report['mode'],'check');self.assertEqual(report['file_count'],2)
            self.assertEqual(report['written_files'],0);self.assertTrue(report['changed'])
            self.assertIn('print(1);',(src/'a.nex').read_text())
            written=run(['fmt','src','--write','--json'],root);self.assertEqual(written.returncode,0,written.stdout+written.stderr)
            report=json.loads(written.stdout);self.assertEqual(report['mode'],'write');self.assertEqual(report['written_files'],2)
            self.assertIn('print(1);\n}',(src/'a.nex').read_text())
            self.assertIn('return 1;\n}',(src/'nested'/'b.nex').read_text())
            self.assertIn('fn y()->unit{}',(src/'.nex'/'ignored.nex').read_text())
            self.assertEqual((src/'notes.txt').read_text(),'unchanged\n')
            again=run(['fmt','src','--check','--json'],root);self.assertEqual(again.returncode,0,again.stdout+again.stderr)
            self.assertTrue(json.loads(again.stdout)['ok'])
            preview=run(['fmt','src','--json'],root);self.assertNotEqual(preview.returncode,0)
            self.assertEqual(json.loads(preview.stdout)['code'],'E_OPTION')
            both=run(['fmt','src','--check','--write','--json'],root);self.assertNotEqual(both.returncode,0)
            file_preview=run(['fmt','src/a.nex','--json'],root);self.assertEqual(file_preview.returncode,0,file_preview.stdout+file_preview.stderr)
            self.assertEqual(json.loads(file_preview.stdout)['schema'],'nex.format/1')

if __name__=='__main__':unittest.main()
