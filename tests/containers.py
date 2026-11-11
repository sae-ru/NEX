"""Source map/set containers: checker, reference/native and optional TypeScript."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module containers;
import "std/map.nex" as maps;
import "std/set.nex" as sets;

fn main() -> unit !{io} {
  let empty_map: maps::Map<str, i64> = maps::empty();
  assert(maps::size(empty_map) == 0);
  let one: maps::Map<str, i64> = maps::put(empty_map, "a", 1);
  let two: maps::Map<str, i64> = maps::put(one, "b", 2);
  assert(maps::size(two) == 2);
  assert(unwrap(maps::get(two, "a")) == 1);
  assert(unwrap(maps::get(two, "b")) == 2);
  assert(!is_ok(maps::get(two, "missing")));
  assert(maps::has(two, "a") && !maps::has(two, "missing"));
  let replaced: maps::Map<str, i64> = maps::put(two, "a", 9);
  assert(maps::size(replaced) == 2);
  assert(unwrap(maps::get(replaced, "a")) == 9);
  assert(maps::keys(replaced) == ["a", "b"]);
  assert(maps::values(replaced) == [9, 2]);
  let shorter: maps::Map<str, i64> = maps::remove(replaced, "a");
  assert(maps::size(shorter) == 1);
  assert(!maps::has(shorter, "a"));
  assert(maps::size(maps::remove(shorter, "missing")) == 1);

  let empty_set: sets::Set<i64> = sets::empty();
  let s1: sets::Set<i64> = sets::add(empty_set, 2);
  let s2: sets::Set<i64> = sets::add(s1, 1);
  assert(sets::size(s2) == 2);
  assert(sets::has(s2, 1) && sets::has(s2, 2) && !sets::has(s2, 3));
  assert(sets::size(sets::add(s2, 2)) == 2);
  assert(sets::items(s2) == [2, 1]);
  assert(sets::items(sets::remove(s2, 2)) == [1]);
  assert(sets::size(sets::remove(s2, 99)) == 2);
  print("containers-ok");
}
'''


def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,
        timeout=300,env={**os.environ,**(environment or {})})


class Containers(unittest.TestCase):
    def test_check_native_and_optional_web(self):
        with tempfile.TemporaryDirectory(prefix='nex containers ') as temporary:
            root=Path(temporary)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'main.nex').write_text(SOURCE)
            checked=run(['check','--json'],root)
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            checked=json.loads(checked.stdout)
            self.assertTrue(checked['ok'])
            native=run(['test','--json'],root)
            self.assertEqual(native.returncode,0,native.stdout+native.stderr)
            native=json.loads(native.stdout)
            self.assertTrue(native['ok'])
            names={test['name'] for test in native['tests']}
            self.assertIn('std::map::map_test',names)
            self.assertIn('std::set::set_test',names)
            self.assertTrue(all(test['native'] for test in native['tests']))
            executed=run(['run','--profile','release','--json'],root)
            self.assertEqual(executed.returncode,0,executed.stdout+executed.stderr)
            self.assertEqual(json.loads(executed.stdout)['stdout'],'containers-ok\n')
            tsc=os.environ.get('NEX_TSC')
            if tsc:
                web=run(['test','--target','web','--json'],root,{'NEX_TSC':tsc})
                self.assertEqual(web.returncode,0,web.stdout+web.stderr)
                web=json.loads(web.stdout)
                self.assertTrue(web['ok'])
                self.assertTrue(all(test['web'] for test in web['tests']))
            descriptor=json.loads(run(['describe','--field','standard_library','--json'],root).stdout)['value']
            self.assertIn('map',descriptor['modules'])
            self.assertIn('set',descriptor['modules'])
            self.assertIn('has',descriptor['modules']['map']['functions'])
            self.assertIn('has',descriptor['modules']['set']['functions'])


if __name__=='__main__':unittest.main()
