"""Checked std/deque consumption across backends."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module stdlib_deque;
import "std/deque.nex" as dq;
fn main() -> unit !{io} {
  var q: dq::Deque<i64> = dq::empty();
  q = dq::push_back(q, 2);
  q = dq::push_front(q, 1);
  assert(dq::size(q) == 2);
  assert(dq::peek_front(q) == ok(1));
  assert(dq::peek_back(q) == ok(2));
  let front: dq::Popped<i64> = unwrap(dq::pop_front(q));
  assert(front.value == 1);
  let back: dq::Popped<i64> = unwrap(dq::pop_back(front.deque));
  assert(back.value == 2);
  assert(dq::is_empty(back.deque));
  print("deque-ok");
}
test fn deque_test() -> unit {
  assert(dq::pop_front(dq::empty<i64>()) == err<dq::Popped<i64>>("E_EMPTY", "deque is empty"));
  assert(dq::pop_back(dq::empty<i64>()) == err<dq::Popped<i64>>("E_EMPTY", "deque is empty"));
}
'''

def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=300,
        env={**os.environ,**(environment or {})})

class StdlibDeque(unittest.TestCase):
    def test_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex stdlib deque ') as temporary:
            root=Path(temporary);(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n');(root/'main.nex').write_text(SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'deque-ok\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'deque-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            capability=json.loads(run(['describe','--field','standard_library','--json'],root).stdout)['value']
            self.assertIn('deque',capability['modules'])

if __name__=='__main__':unittest.main()
