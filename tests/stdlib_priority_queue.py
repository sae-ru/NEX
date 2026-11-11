"""Checked std/priority_queue consumption across backends."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module stdlib_priority_queue;
import "std/priority_queue.nex" as pq;
fn main() -> unit !{io} {
  var q: pq::PriorityQueue<i64> = pq::empty();
  q = pq::push_value(q, 5);
  q = pq::push_value(q, 1);
  q = pq::push_value(q, 3);
  assert(pq::size(q) == 3);
  assert(pq::peek(q) == ok(1));
  let first: pq::Popped<i64> = unwrap(pq::pop(q));
  assert(first.value == 1);
  let second: pq::Popped<i64> = unwrap(pq::pop(first.queue));
  assert(second.value == 3);
  assert(!pq::is_empty(second.queue));
  print("pq-ok");
}
test fn priority_test() -> unit {
  assert(pq::pop(pq::empty<i64>()) == err<pq::Popped<i64>>("E_EMPTY", "priority queue is empty"));
}
'''

def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=300,
        env={**os.environ,**(environment or {})})

class StdlibPriorityQueue(unittest.TestCase):
    def test_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex stdlib pq ') as temporary:
            root=Path(temporary);(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n');(root/'main.nex').write_text(SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'pq-ok\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'pq-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            capability=json.loads(run(['describe','--field','standard_library','--json'],root).stdout)['value']
            self.assertIn('priority_queue',capability['modules'])

if __name__=='__main__':unittest.main()
