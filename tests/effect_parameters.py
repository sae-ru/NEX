"""Inferred effect parameters on named generic functions."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module effect_parameters;
import "std/list.nex" as seq;

fn apply<T, U>(value: T, transform: fn(T) -> U !{?E}) -> U !{?E} {
  return transform(value);
}

fn main() -> unit !{io} {
  let mapped: list<i64> = seq::map([1, 2], fn(x: i64) -> i64 !{io} {
      print(x);
      return x + 1;
    });
  assert(mapped == [2, 3]);
  let filtered: list<i64> = seq::filter([1, 2, 3], fn(x: i64) -> bool !{io} {
      print(x);
      return x > 1;
    });
  assert(filtered == [2, 3]);
  let folded: i64 = seq::fold([1, 2, 3], 0, fn(a: i64, b: i64) -> i64 !{io} {
      print(b);
      return a + b;
    });
  assert(folded == 6);
  let applied: i64 = apply(41, fn(x: i64) -> i64 !{io} {
      print(x);
      return x + 1;
    });
  assert(applied == 42);
  let pure: list<i64> = seq::map([1, 2], fn(x: i64) -> i64 {
      return x + 10;
    });
  assert(pure == [11, 12]);
  let mapper: fn(list<i64>, fn(i64)->i64 !{io}) -> list<i64> !{io} = seq::map;
  assert(mapper([1], fn(x: i64) -> i64 !{io} { print(x); return x; }) == [1]);
  let explicit: list<i64> = seq::map<i64, i64>!{io}([1], fn(x: i64) -> i64 !{io} {
      print(x);
      return x;
    });
  assert(explicit == [1]);
  let explicit_mapper: fn(list<i64>, fn(i64)->i64 !{io}) -> list<i64> !{io} = seq::map<i64, i64>!{io};
  assert(explicit_mapper([1], fn(x: i64) -> i64 !{io} { print(x); return x; }) == [1]);
  let generated: list<i64> = seq::generate(2, fn(i: i64) -> i64 !{io} { print(i); return i; });
  assert(generated == [0, 1]);
  let any_true: bool = seq::any([1, 2], fn(x: i64) -> bool !{io} { print(x); return x == 2; });
  assert(any_true);
  let all_true: bool = seq::all([1, 2], fn(x: i64) -> bool !{io} { print(x); return x > 0; });
  assert(all_true);
  let found: i64 = seq::find_index([1, 2, 3], fn(x: i64) -> bool !{io} { print(x); return x == 2; });
  assert(found == 1);
  let sorted: list<i64> = seq::sort_by([2, 1], fn(a: i64, b: i64) -> bool !{io} { print(a); return a < b; });
  assert(sorted == [1, 2]);
  let pure_mapper: fn(list<i64>, fn(i64)->i64) -> list<i64> = seq::map;
  assert(pure_mapper([1], fn(x: i64) -> i64 { return x + 1; }) == [2]);
  print("effect-parameters-ok");
}

test fn effect_test() -> unit !{io} {
  let mapped: list<i64> = seq::map([1, 2], fn(x: i64) -> i64 !{io} {
      print(x);
      return x * 2;
    });
  assert(mapped == [2, 4]);
  let applied: i64 = apply(1, fn(x: i64) -> i64 !{io} {
      print(x);
      return x + 1;
    });
  assert(applied == 2);
  let mapper: fn(list<i64>, fn(i64)->i64 !{io}) -> list<i64> !{io} = seq::map;
  assert(mapper([1], fn(x: i64) -> i64 !{io} { print(x); return x; }) == [1]);
  let explicit: list<i64> = seq::map<i64, i64>!{io}([1], fn(x: i64) -> i64 !{io} {
      print(x);
      return x;
    });
  assert(explicit == [1]);
  let explicit_mapper: fn(list<i64>, fn(i64)->i64 !{io}) -> list<i64> !{io} = seq::map<i64, i64>!{io};
  assert(explicit_mapper([1], fn(x: i64) -> i64 !{io} { print(x); return x; }) == [1]);
  let generated: list<i64> = seq::generate(2, fn(i: i64) -> i64 !{io} { print(i); return i; });
  assert(generated == [0, 1]);
  let any_true: bool = seq::any([1, 2], fn(x: i64) -> bool !{io} { print(x); return x == 2; });
  assert(any_true);
  let all_true: bool = seq::all([1, 2], fn(x: i64) -> bool !{io} { print(x); return x > 0; });
  assert(all_true);
  let found: i64 = seq::find_index([1, 2, 3], fn(x: i64) -> bool !{io} { print(x); return x == 2; });
  assert(found == 1);
  let sorted: list<i64> = seq::sort_by([2, 1], fn(a: i64, b: i64) -> bool !{io} { print(a); return a < b; });
  assert(sorted == [1, 2]);
}
'''
REJECT='''module effect_reject;
import "std/list.nex" as seq;
fn main() -> unit !{io} {
  let values: list<i64> = seq::map<i64, i64>!{task}([1], fn(x: i64) -> i64 !{io} {
      print(x);
      return x;
    });
  assert(values == [1]);
}
'''


def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=300,
        env={**os.environ,**(environment or {})})


class EffectParameters(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_inference_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex effect parameters ') as temporary:
            root=Path(temporary);self.project(root,SOURCE)
            checked=run(['check','--json'],root)
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            self.assertTrue(json.loads(checked.stdout)['ok'])
            evaluated=run(['eval','--entry','main','--json'],root)
            self.assertEqual(evaluated.returncode,0,evaluated.stdout+evaluated.stderr)
            stdout=json.loads(evaluated.stdout)['stdout']
            self.assertTrue(stdout.endswith('effect-parameters-ok\n'))
            native=run(['test','--json'],root)
            self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout)
            self.assertTrue(native['ok'])
            names={test['name'] for test in native['tests']}
            self.assertIn('effect_parameters::effect_test',names)
            self.assertTrue(all(test['native'] for test in native['tests']))
            ran=run(['run','--profile','release','--json'],root)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)
            self.assertTrue(json.loads(ran.stdout)['stdout'].endswith('effect-parameters-ok\n'))
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc})
                self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout)
                self.assertTrue(web['ok'])
                self.assertTrue(all(test['web'] for test in web['tests']))
            descriptor=json.loads(run(['describe','--field','effect_parameters','--json'],root).stdout)['value']
            self.assertEqual(descriptor['schema'],'nex.effect-parameters/1')
            self.assertIn('?E',descriptor['syntax'])
            self.assertTrue(descriptor['function_values'])
            self.assertTrue(descriptor['explicit_effect_witnesses'])

    def test_missing_caller_effect_is_rejected(self):
        with tempfile.TemporaryDirectory(prefix='nex effect reject ') as temporary:
            root=Path(temporary);self.project(root,REJECT)
            checked=run(['check','--json'],root)
            self.assertNotEqual(checked.returncode,0)
            diagnostic=json.loads(checked.stdout)
            self.assertEqual(diagnostic['code'],'E_EFFECT')
            self.assertIn('witness',diagnostic['message'])


if __name__=='__main__':unittest.main()
