"""Checked std/set union/intersection/difference across backends."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module stdlib_set_ops;
import "std/set.nex" as s;
fn main() -> unit !{io} {
  var a: s::Set<i64> = s::add(s::add(s::empty(), 1), 2);
  var b: s::Set<i64> = s::add(s::add(s::empty(), 2), 3);
  assert(s::items(s::union(a, b)) == [1, 2, 3]);
  assert(s::items(s::intersection(a, b)) == [2]);
  assert(s::items(s::difference(a, b)) == [1]);
  assert(s::items(s::union(s::empty<i64>(), s::empty<i64>())) == []);
  print("set-ops-ok");
}
test fn set_ops_test() -> unit {
  let a: s::Set<i64> = s::add(s::empty(), 1);
  assert(s::items(s::difference(a, a)) == []);
}
'''

def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=300,
        env={**os.environ,**(environment or {})})

class StdlibSetOps(unittest.TestCase):
    def test_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex stdlib set ') as temporary:
            root=Path(temporary);(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n');(root/'main.nex').write_text(SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'set-ops-ok\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'set-ops-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            capability=json.loads(run(['describe','--field','standard_library','--json'],root).stdout)['value']
            self.assertTrue({'union','intersection','difference'} <= set(capability['modules']['set']['functions']))

if __name__=='__main__':unittest.main()
