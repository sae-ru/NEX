"""Checked std/queue and std/stack consumption across backends."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module stdlib_queue_stack;
import "std/queue.nex" as queue;
import "std/stack.nex" as stack;
fn main() -> unit !{io} {
  var q: queue::Queue<i64> = queue::empty();
  q = queue::enqueue(q, 1);
  q = queue::enqueue(q, 2);
  let first: queue::Popped<i64> = unwrap(queue::dequeue(q));
  assert(first.value == 1);
  assert(queue::peek(first.queue) == ok(2));
  assert(queue::size(first.queue) == 1);
  assert(!queue::is_empty(first.queue));
  var s: stack::Stack<i64> = stack::empty();
  s = stack::push_value(s, 3);
  s = stack::push_value(s, 4);
  let top: stack::Popped<i64> = unwrap(stack::pop(s));
  assert(top.value == 4);
  assert(stack::peek(top.stack) == ok(3));
  assert(stack::size(top.stack) == 1);
  assert(!stack::is_empty(top.stack));
  print("queue-stack-ok");
}
test fn queue_stack_test() -> unit {
  assert(queue::dequeue(queue::empty<i64>()) == err<queue::Popped<i64>>("E_EMPTY", "queue is empty"));
  assert(stack::pop(stack::empty<i64>()) == err<stack::Popped<i64>>("E_EMPTY", "stack is empty"));
}
'''

def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=300,
        env={**os.environ,**(environment or {})})

class StdlibQueueStack(unittest.TestCase):
    def test_reference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex stdlib queue ') as temporary:
            root=Path(temporary);(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n');(root/'main.nex').write_text(SOURCE)
            checked=run(['check','--json'],root);self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            evaluated=run(['eval','--entry','main','--json'],root);self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            self.assertEqual(json.loads(evaluated.stdout)['stdout'],'queue-stack-ok\n')
            native=run(['test','--json'],root);self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout);self.assertTrue(native['ok']);self.assertTrue(all(t['native'] for t in native['tests']))
            ran=run(['run','--profile','release','--json'],root);self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertEqual(json.loads(ran.stdout)['stdout'],'queue-stack-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc});self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout);self.assertTrue(web['ok']);self.assertTrue(all(t['web'] for t in web['tests']))
            capability=json.loads(run(['describe','--field','standard_library','--json'],root).stdout)['value']
            self.assertEqual(set(capability['modules'])>= {'queue','stack'},True)

if __name__=='__main__':unittest.main()
