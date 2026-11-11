"""Type-parameter defaults on generic functions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module fn_defaults;
fn marker<T = i64>() -> str { return "x"; }
fn pair<A, B = str>(a: A, b: B) -> str { return "pair"; }
fn main() -> unit !{io} {
  assert(marker() == "x");
  assert(marker<str>() == "x");
  assert(pair<i64>(1, "y") == "pair");
  assert(pair<i64, bool>(1, true) == "pair");
  let f: fn() -> str = marker;
  assert(f() == "x");
  print("fn-defaults-ok");
}
test fn defaults_test() -> unit {
  assert(marker() == "x");
  assert(pair<i64>(1, "y") == "pair");
}
'''


def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=240,
        env={**os.environ,**(environment or {})})

class FunctionTypeDefaults(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_resolution_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex fn defaults ') as temporary:
            root=Path(temporary);self.project(root,SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'fn-defaults-ok\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'fn-defaults-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            descriptor=json.loads(run(['describe','--field','generic_features','--json'],root).stdout)['value']
            self.assertIn('function_type_defaults',descriptor)

    def test_invalid_function_defaults_rejected(self):
        with tempfile.TemporaryDirectory(prefix='nex fn defaults reject ') as temporary:
            root=Path(temporary)
            for source,code in [
                ('module bad;\nfn bad<T = i64, U>() -> i64 { return 1; }\nfn main()->unit{}\n','E_GENERIC_DEFAULT'),
                ('module bad;\nfn bad<T = unit>() -> i64 { return 1; }\nfn main()->unit{}\n','E_TYPE')]:
                self.project(root,source);result=run(['check','--json'],root);self.assertNotEqual(result.returncode,0)
                self.assertEqual(json.loads(result.stdout)['code'],code,result.stdout)

if __name__=='__main__':unittest.main()
