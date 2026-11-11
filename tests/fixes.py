"""Compiler-checked diagnostic fixes: preview, apply, refusal and rollback."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

COMPILER=Path(sys.argv.pop(1)).resolve()
NAME_SOURCE='''module fix_case;
fn main() -> unit !{io} {
  let total: i64 = 1;
  print(totl);
}
'''
FIELD_SOURCE='''module fix_field;
struct Item { value: i64; }
fn main() -> unit !{io} {
  let item: Item = Item(2);
  print(item.valu);
}
'''


def run(args,cwd):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=120)


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixes(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_name_and_field_fixes_preview_apply_and_descriptor(self):
        with tempfile.TemporaryDirectory(prefix='nex fixes ') as temporary:
            root=Path(temporary);self.project(root,NAME_SOURCE)
            before=digest(root/'main.nex')
            preview=run(['fix','--json'],root)
            self.assertEqual(preview.returncode,0,preview.stdout+preview.stderr)
            report=json.loads(preview.stdout)
            self.assertEqual(report['schema'],'nex.fix/1')
            self.assertFalse(report['applied'])
            self.assertEqual(report['diagnostic']['code'],'E_NAME')
            self.assertEqual(report['fix']['replacement'],'total')
            self.assertEqual(report['fix']['safety'],'unique closest visible identifier')
            self.assertEqual(digest(root/'main.nex'),before)
            checked=run(['check','--json'],root)
            self.assertNotEqual(checked.returncode,0)
            diagnostic=json.loads(checked.stdout)
            self.assertEqual(diagnostic['code'],'E_NAME')
            self.assertEqual(diagnostic['fixes'][0]['replacement'],'total')
            self.assertEqual((diagnostic['fixes'][0]['begin'],diagnostic['fixes'][0]['end']),
                (report['fix']['begin'],report['fix']['end']))
            applied=run(['fix','--apply','--json'],root)
            self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr)
            result=json.loads(applied.stdout)
            self.assertTrue(result['applied'])
            self.assertTrue(result['revision'])
            self.assertIn('print(total);',(root/'main.nex').read_text())
            self.assertEqual(run(['check','--json'],root).returncode,0)

            self.project(root,FIELD_SOURCE)
            preview=run(['fix','--json'],root)
            self.assertEqual(preview.returncode,0,preview.stdout+preview.stderr)
            field=json.loads(preview.stdout)
            self.assertEqual(field['diagnostic']['code'],'E_FIELD')
            self.assertEqual(field['fix']['replacement'],'value')
            applied=run(['fix','--apply','--json'],root)
            self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr)
            self.assertIn('item.value',(root/'main.nex').read_text())
            self.assertEqual(run(['check','--json'],root).returncode,0)

            descriptor=json.loads(run(['describe','--field','diagnostic_fixes','--json'],root).stdout)['value']
            self.assertEqual(descriptor['schema'],'nex.fix/1')
            self.assertIn('E_NAME',descriptor['codes'])
            help=json.loads(run(['help','fix','--json'],root).stdout)
            self.assertIn('--apply',[option['name'] for option in help['options']])

    def test_unavailable_fix_and_rollback(self):
        with tempfile.TemporaryDirectory(prefix='nex fixes refusal ') as temporary:
            root=Path(temporary)
            self.project(root,'''module fix_none;
fn main() -> unit !{io} { print(zzzzzzzz); }
''')
            unavailable=run(['fix','--apply','--json'],root)
            self.assertNotEqual(unavailable.returncode,0)
            self.assertEqual(json.loads(unavailable.stdout)['code'],'E_FIX_UNAVAILABLE')
            self.project(root,'''module fix_rollback;
fn main() -> unit !{io} {
  let total: i64 = 1;
  print(totl);
  let bad: i64 = "text";
}
''')
            before=digest(root/'main.nex')
            rejected=run(['fix','--apply','--json'],root)
            self.assertNotEqual(rejected.returncode,0)
            self.assertEqual(json.loads(rejected.stdout)['code'],'E_FIX_REJECTED')
            self.assertEqual(digest(root/'main.nex'),before)
            self.assertIn('print(totl);',(root/'main.nex').read_text())
            revision=run(['fix','--revision','HEAD','--json'],root)
            self.assertNotEqual(revision.returncode,0)
            self.assertEqual(json.loads(revision.stdout)['code'],'E_OPTION')


if __name__=='__main__':unittest.main()
