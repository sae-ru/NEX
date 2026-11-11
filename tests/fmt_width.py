"""Conservative width wrapping for nex fmt."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module w;
fn long(first:i64,second:i64,third:i64,fourth:i64)->i64{return first;}
fn main()->unit !{io}{print("a, b, c, d, e, f, g, h, i, j, k, l, m");}
'''

def run(args,cwd):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=120)

class FmtWidth(unittest.TestCase):
    def test_width_wraps_unquoted_lines_and_is_optional(self):
        with tempfile.TemporaryDirectory(prefix='nex fmt width ') as temporary:
            root=Path(temporary);(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'main.nex').write_text(SOURCE)
            narrow=run(['fmt','main.nex','--width','40','--json'],root);self.assertEqual(narrow.returncode,0,narrow.stdout+narrow.stderr)
            report=json.loads(narrow.stdout);self.assertEqual(report['width'],40)
            source=report['source'];lines=source.splitlines()
            self.assertTrue(any('fn long(' in line for line in lines))
            self.assertTrue(any(line.startswith('   third: i64') for line in lines))
            self.assertIn('print("a, b, c, d, e, f, g, h, i, j, k, l, m");',source)
            for line in lines:
                if '"' not in line and '//' not in line:self.assertLessEqual(len(line),40,line)
            unchanged=run(['fmt','main.nex','--json'],root);self.assertEqual(unchanged.returncode,0)
            self.assertNotEqual(json.loads(unchanged.stdout)['source'],source)
            for value in ('5','1001','x'):
                invalid=run(['fmt','main.nex','--width',value,'--json'],root);self.assertNotEqual(invalid.returncode,0)
                self.assertEqual(json.loads(invalid.stdout)['code'],'E_OPTION')
            directory=run(['fmt','.','--check','--width','40','--json'],root);self.assertIn(directory.returncode,(0,1))

if __name__=='__main__':unittest.main()
