"""Verify insertion ordering against a Python dictionary on all ordinary backends."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PROGRAM = '''module insertion_order_corpus;
import "std/insertion_ordered_map.nex" as maps;
struct Key { group: i64; label: i64; }
struct Op { add: bool; key: Key; value: i64; }
fn equal(a: Key, b: Key) -> bool { return a.group == b.group; }

fn observe(m: maps::Map<Key,i64>) -> unit !{io} {
  let items: list<maps::Entry<Key,i64>> = maps::entries(m);
  let keys: list<Key> = maps::keys(m);
  let values: list<i64> = maps::values(m);
  assert(len(items) == maps::size(m) && len(keys) == len(items) && len(values) == len(items));
  assert(maps::is_empty(m) == (len(items) == 0));
  print(len(items));
  var i: i64 = 0;
  while i < len(items) {
    let k: Key = keys[i];
    assert(items[i].key == k && items[i].value == values[i]);
    let equivalent: Key = Key(k.group, -99);
    assert(maps::has(m,equivalent) && unwrap(maps::get(m,equivalent)) == values[i]);
    print(k.group); print(k.label); print(values[i]); i = i+1;
  }
}
fn main() -> unit !{io} {
  let salt: i64 = 17;
  // Many unequal keys collide, while other pairs exercise distinct trie paths.
  var m: maps::Map<Key,i64> = maps::empty(fn(k:Key)->i64{return (k.group%3)*salt;}, equal);
  var saved: maps::Map<Key,i64> = m;
  let ops: list<Op> = OPERATIONS;
  observe(m);
  var i: i64=0;
  while i < len(ops) {
    let op: Op = ops[i];
    if op.add { m = maps::put(m,op.key,op.value); }
    else {
      m = maps::remove(m,op.key);
      assert(!maps::has(m,op.key) && error_code(maps::get(m,op.key)) == "E_NOT_FOUND");
    }
    if i == 5 { saved = m; }
    observe(m); i = i + 1;
  }
  observe(saved);
  let branch: maps::Map<Key,i64> = maps::put(saved,Key(93,719),-5);
  observe(branch); observe(m);
  // Reproduce an exhausted monotonic counter without requiring 2^63 writes.
  let full_counter: maps::Map<Key,i64> = maps::Map(m.by_key,m.by_position,9223372036854775807);
  let changed: maps::Map<Key,i64> = maps::put(full_counter,Key(27,4),314);
  let rebased: maps::Map<Key,i64> = maps::put(changed,Key(100,40),71);
  assert(changed.next_position == 9223372036854775807 && rebased.next_position == maps::size(rebased));
  observe(changed); observe(rebased); observe(full_counter);
  let singleton: maps::Map<Key,i64> = maps::put(maps::empty<Key,i64>(m.by_key.hash,equal), Key(1,10),10);
  let cleared: maps::Map<Key,i64> = maps::remove(singleton,Key(1,20));
  let restarted: maps::Map<Key,i64> = maps::put(cleared,Key(1,30),30);
  assert(maps::is_empty(cleared) && cleared.next_position == 0);
  assert(maps::keys(restarted) == [Key(1,30)] && maps::keys(singleton) == [Key(1,10)]);
}
'''


def corpus():
    operations = [(True, g, i, 100+i) for i, g in enumerate((3, 6, -3, 4, 7, 0, 27))]
    operations += [(True, 3, 70, 9), (False, 6, 999, 0), (False, -3, 2, 0), (True, 6, 101, 3),
                   (False, 88, 51, 0), (True, -3, 11, 14), (True, 4, 39, 44), (False, 3, 27, 0),
                   (True, 9, 16, 93), (True, 3, 22, 80), (True, 0, 32, 91), (False, 7, 90, 0)]
    source = PROGRAM.replace('OPERATIONS', '['+', '.join(
        f'Op({str(add).lower()},Key({key},{label}),{value})' for add,key,label,value in operations)+']')
    expected = []
    def observe(state):
        expected.append(len(state))
        for key, (label,value) in state.items():
            expected.extend((key,label,value))
    def put(state,key,label,value):
        first_label = state.get(key,(label,None))[0]
        state[key] = (first_label,value)
    current = {}
    observe(current)
    for index,(add,key,label,value) in enumerate(operations):
        if add: put(current,key,label,value)
        else: current.pop(key,None)
        if index == 5: saved = current.copy()
        observe(current)
    observe(saved)
    branch = saved.copy()
    put(branch,93,719,-5)
    observe(branch)
    observe(current)
    replaced = current.copy()
    put(replaced,27,4,314)
    observe(replaced)
    put(replaced,100,40,71)
    observe(replaced)
    observe(current)
    return source, ''.join(f'{n}\n' for n in expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiler',type=Path)
    parser.add_argument('--output-parent',type=Path)
    args = parser.parse_args()
    output = Path(tempfile.mkdtemp(prefix='insertion-order-',dir=args.output_parent)).resolve()
    compiler = args.compiler.resolve(strict=True)
    description = subprocess.check_output([compiler,'describe','--field','standard_library','--json'],cwd=output)
    capability = json.loads(description)['value']['modules']['insertion_ordered_map']
    resource = ROOT/capability['resource']
    assert capability['sha256'] == hashlib.sha256(resource.read_bytes()).hexdigest()
    source,expected = corpus()
    inp = output/'corpus'
    inp.mkdir()
    (inp/'trace.nex').write_text(source)
    (inp/'invalid.nex').write_text('''module rejected;import "std/insertion_ordered_map.nex" as maps;
fn noisy(i:i64)->i64!{io}{print(i); return i;}
fn main()->unit{let m:maps::Map<i64,str> = maps::empty(noisy,fn(a:i64,b:i64)->bool{return a==b;});}
''')
    cases = [{'name':'trace','kind':'valid','source':'trace.nex','expected_stdout':expected},
             {'name':'reject_effectful_hash','kind':'rejected','source':'invalid.nex','expected_check_code':'E_EFFECT'}]
    (inp/'cases.json').write_text(json.dumps({'schema':'nex.agreement/1','language':'0.30','cases':cases}))
    env = os.environ.copy()
    env.pop('NEX_SKIP_TYPESCRIPT',None)
    env.setdefault('NEX_TSC',str(ROOT/'web/node_modules/typescript/bin/tsc'))
    dest = output/'agreement'
    subprocess.run([sys.executable,'-B',ROOT/'tools/agreement.py','--compiler',compiler,
                    '--root',inp,'--output',dest,'--timeout','300'],env=env,check=True)
    receipt = json.loads((dest/'report.json').read_text())
    assert receipt['project_languages'] == ['0.30'] and receipt['ok'] and receipt['typescript_executed']
    assert receipt['coverage'] == {'check':2,'reference':1,'native-debug':1,'native-release':1,
                                  'typescript':1,'typescript_executed':1,'typescript_strict':1,'executable_cases':1}
    print(json.dumps({'ok':True,'report':str(dest/'report.json'),'expected_lines':len(expected.splitlines())}))


if __name__ == '__main__':
    main()
