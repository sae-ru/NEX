"""Nominal type-parameter defaults: parsing, resolution and backend execution."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module type_defaults;
struct Box<T = i64> { value: T; }
struct Pair<A, B = str> { first: A; second: B; }
fn main() -> unit !{io} {
  let boxed: Box = Box(42);
  assert(boxed.value == 42);
  let text: Box<str> = Box("x");
  assert(text.value == "x");
  let pair: Pair<i64> = Pair(7, "seven");
  assert(pair.first == 7 && pair.second == "seven");
  print("type-defaults-ok");
}
test fn defaults_test() -> unit {
  let boxed: Box = Box(1);
  assert(boxed.value == 1);
}
'''


def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=240,
        env={**os.environ,**(environment or {})})

class TypeDefaults(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_resolution_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex type defaults ') as temporary:
            root=Path(temporary);self.project(root,SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'type-defaults-ok\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'type-defaults-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            descriptor=json.loads(run(['describe','--field','generic_features','--json'],root).stdout)['value']
            self.assertIn('type_defaults',descriptor)

    def test_non_trailing_and_function_defaults_rejected(self):
        with tempfile.TemporaryDirectory(prefix='nex type defaults reject ') as temporary:
            root=Path(temporary)
            for source,code in [
                ('module bad;\nstruct Bad<T = i64, U> { a: T; b: U; }\nfn main()->unit{}\n','E_GENERIC_DEFAULT'),
                ('module bad;\nstruct Bad<T = unit> { a: T; }\nfn main()->unit{}\n','E_TYPE')]:
                self.project(root,source);result=run(['check','--json'],root);self.assertNotEqual(result.returncode,0)
                self.assertEqual(json.loads(result.stdout)['code'],code,result.stdout)

if __name__=='__main__':unittest.main()
