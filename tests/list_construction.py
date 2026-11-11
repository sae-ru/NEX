"""Sequential bulk construction, effect/ownership behavior and backend agreement."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import support as h
import standard_library as helpers


class Construction(h.ToolchainCase):
    run_child=helpers.StandardLibrary.run_child
    strict_ts=helpers.StandardLibrary.strict_ts
    def typescript(self,entry='main',failure=None):
        folder=self.root/('typescript-'+entry)
        self.cli('emit','--kind','typescript','--entry',entry,'--directory',folder)
        (folder/'package.json').write_text('{"type":"module"}\n')
        code=(folder/'program.ts').read_text()
        task_mode="import * as task from './nex-task-runtime.ts'" in code
        driver=folder/'driver.mjs'
        imports="import {entry} from './program.ts';\n"
        execute='entry();'
        if task_mode:
            imports+="import {sourceErrorContracts} from './program.ts';import * as task from './nex-task-runtime.ts';\n"
            execute='await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts);'
        if failure:
            imports+="import {NexError} from './nex-runtime.ts';\n"
            execute="try{"+execute+"process.stdout.write('unexpected-success');}catch(e){if(!(e instanceof NexError))throw e;process.stdout.write(e.code);}"
        driver.write_text(imports+execute+'\n')
        result=self.run_child([os.environ.get('NEX_NODE','node'),'--experimental-strip-types',driver])
        self.strict_ts(folder);return result

    def test_generated_bindings_do_not_capture_source_shadows(self):
        source='''module hygiene;
fn main()->unit!{io}{
 let len:fn(list<i64>)->i64=fn(values:list<i64>)->i64{return 0;};
 let assert:fn(bool)->unit=fn(ignored:bool)->unit{};
 let nex_bulk_count:i64=7;
 let output:list<i64>=list([1,2],fn(x:i64)->i64{return x+len([])+nex_bulk_count;});
 if output==[8,9]{print("hygiene-ok");}else{print("wrong");}
}
fn negative()->unit{
 let assert:fn(bool)->unit=fn(ignored:bool)->unit{};
 let output:list<i64>=list(-1,fn(i:i64)->i64{return i;});
}
'''
        self.agreement(source,'hygiene-ok\n')
        self.assertEqual(self.cli('eval','--entry','negative',ok=False)['code'],'E_ASSERT')
        for profile in ['debug','release']:
            observed=self.cli('run','--entry','negative','--profile',profile,ok=False,timeout=240)
            self.assertIn('E_ASSERT',observed['stderr'])
        self.assertEqual(self.typescript('negative',failure='E_ASSERT'),'E_ASSERT')

    def test_existing_028_graph_and_local_ids_are_unchanged(self):
        path=h.REPO/'tests/fixtures/list-construction-before-028'
        metadata=json.loads(Path(str(path)+'.json').read_text())
        raw=Path(str(path)+'.sql').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(),metadata['sql_sha256'])
        self.source(metadata['source']);(self.root/'.nex').mkdir()
        with h.sqlite_connection(self.root/'.nex/graph.db') as connection:
            connection.executescript(raw.decode())
            connection.execute('PRAGMA user_version='+str(metadata['user_version']))
        before=h.database_rows(self.root/'.nex/graph.db')[1]
        self.assertEqual(self.cli('check')['revision'],metadata['revision'])
        after=h.database_rows(self.root/'.nex/graph.db')[1]
        for table in ['node_ids','declaration_ids','revisions','identity_revisions']:
            self.assertIn(table,before);self.assertEqual(before[table],after[table],table)

    def agreement(self,source,expected,steps='1000000'):
        self.source(source)
        self.cli('check')
        self.assertEqual(self.cli('eval','--steps',steps,timeout=180)['stdout'],expected)
        for profile in ['debug','release']:
            self.assertEqual(self.cli('run','--profile',profile,timeout=240)['stdout'],expected)
        self.assertEqual(self.typescript(),expected)

    def test_all_shapes_generics_values_and_immutable_aliases(self):
        self.agreement('''module bulk;
struct Pair {left:i64;right:i64;}
enum Choice {None();Some(value:i64);}
fn identity<T>(value:T)->T{return value;}
fn main()->unit!{io}{
  let original:list<i64>=[3,1,2];let alias:list<i64>=original;
  assert(list(0,fn(i:i64)->i64{return 1/i;})==[]);
  assert(list(4,fn(i:i64)->i64{return i*i;})==[0,1,4,9]);
  assert(list(original,identity)==original);
  let empty:list<i64>=list([],identity);assert(empty==[]);
  assert(list(original,fn(x:i64)->bool{return x>1;},fn(x:i64)->str{return str(x);})==["3","2"]);
  assert(original==alias && alias==[3,1,2]);
  var offset:i64=7;let transform:fn(i64)->i64=fn(x:i64)->i64{return x+offset;};
  offset=99;assert(list(original,transform)==[10,8,9]);
  let matrix:list<list<i64>>=list(3,fn(i:i64)->list<i64>{return [i,i+1];});
  assert(matrix==[[0,1],[1,2],[2,3]]);
  assert(list(3,fn(i:i64)->f64{return as_f64(i)+0.5;})==[0.5,1.5,2.5]);
  let choices:list<Choice>=list(original,fn(x:i64)->Choice{return Choice::Some(x);});
  assert(choices[0]==Choice::Some(3));
  let octets:list<bytes>=list(2,fn(i:i64)->bytes{return utf8_bytes("Я🌍\\u0000"+str(i));});
  assert(unwrap(decode_utf8(octets[1]))=="Я🌍\\u00001");
  let closures:list<fn(i64)->i64>=list(3,fn(i:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return x+i;};});
  assert(closures[2](5)==7);
  let states:list<i64>=list(4,Pair(1,2),fn(p:Pair)->Pair{return Pair(p.right,p.left+p.right);},fn(p:Pair)->i64{return p.left;});
  assert(states==[1,2,3,5]);
  assert(list(2,9223372036854775806,fn(x:i64)->i64{return x+1;},identity)==[9223372036854775806,9223372036854775807]);
  print("bulk-values-ok");
}
''','bulk-values-ok\n')

    def test_effect_order_and_typed_source_errors(self):
        self.agreement('''module ordered;
struct Stopped {index:i64;}
fn count()->i64!{io}{print("count");return 4;}
fn maker()->fn(i64)->i64!{io} !{io}{print("factory");return fn(i:i64)->i64!{io}{print(i);return i;};}
fn main()->unit!{io,throw}{
  let made:list<i64>=list(count(),maker());assert(made==[0,1,2,3]);
  let chosen:list<i64>=list([0,1,2],fn(x:i64)->bool!{io}{print("p"+str(x));return x%2==0;},fn(x:i64)->i64!{io}{print("m"+str(x));return x+10;});
  assert(chosen==[10,12]);
  try {
    let stopped:list<str>=list(5,fn(i:i64)->str!{io,throw}{print("s"+str(i));if i==2 {throw(Stopped(i));}return str(i);});
    print(stopped);
  } catch(error:Stopped) {print(error.index);} finally {print("finally");}
  let values:list<i64>=list(3,0,fn(x:i64)->i64!{io}{print("n"+str(x));return x+1;},fn(x:i64)->i64!{io}{print("e"+str(x));return x;});
  assert(values==[0,1,2]);
}
''','count\nfactory\n0\n1\n2\n3\np0\nm0\np1\np2\nm2\ns0\ns1\ns2\n2\nfinally\ne0\nn0\ne1\nn1\ne2\n')

    def test_suspending_callbacks_and_genuine_task_values(self):
        self.agreement('''module task_bulk;
struct Stopped {value:i64;}
fn main()->unit!{task,io,throw}{
  let output:list<i64>=list(3,0,
    fn(x:i64)->i64!{task,io}{task_yield();print("next"+str(x));return x+1;},
    fn(x:i64)->i64!{task,io}{task_yield();print("emit"+str(x));return x;});
  assert(output==[0,1,2]);
  try {let stopped:list<i64>=list(4,fn(i:i64)->i64!{task,throw}{task_yield();if i==2{throw(Stopped(i));}return i;});}
  catch(error:Stopped){print(error.value);}finally{print("drained");}
  let total:i64=with_tasks(2,fn(scope:task_scope)->i64!{task,throw}{
    let jobs:list<task<i64>>=list(4,fn(i:i64)->task<i64>!{task}{return task_spawn(scope,fn()->i64{return i*2;});});
    let values:list<i64>=list(jobs,fn(job:task<i64>)->i64!{task,throw}{return task_wait(job);});
    assert(values==[0,2,4,6]);return values[3];
  });
  assert(total==6);print("task-bulk-ok");
}
''','emit0\nnext0\nemit1\nnext1\nemit2\n2\ndrained\ntask-bulk-ok\n')

    def test_rejected_effects_types_and_borrowed_scope_escape(self):
        cases=[('module bad;fn main()->unit{let x:list<i64>=list(1,fn(i:i64)->i64!{io}{print(i);return i;});}','E_EFFECT'),
            ('module bad;fn main()->unit{let x:list<i64>=list(1,fn(i:str)->i64{return 1;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:list<i64>=list(1,fn(i:i64)->unit{});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:list<i64>=list(1,true,fn(i:i64)->i64{return i;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:list<i64>=list(2,0,fn(i:i64)->str{return "x";},fn(i:i64)->i64{return i;});}','E_TYPE')]
        for source,code in cases:
            self.source(source);self.assertEqual(self.cli('check',ok=False)['code'],code)
        self.source('''module escape;
fn main()->list<task_scope>!{task,throw}{return with_tasks(1,fn(scope:task_scope)->list<task_scope>!{task}{
 return list(1,fn(i:i64)->task_scope{return scope;});});}
''')
        result=self.cli('check',ok=False)
        self.assertIn(result['code'],['E_TASK_LIFETIME','E_TASK_SCOPE','E_TASK_REGION_ESCAPE','E_TASK_TYPE'])

    def test_negative_count_arguments_and_native_exit_cleanup(self):
        self.source('''module failure;
fn count()->i64!{io}{print("count");return -1;}
fn make()->(fn(i64)->str !{io})!{io}{print("factory");return fn(i:i64)->str!{io}{print("callback");return "value";};}
fn main()->unit!{io}{let output:list<str>=list(count(),make());print(output);}
''')
        reference=self.cli('eval',ok=False);self.assertEqual(reference['code'],'E_ASSERT')
        self.assertEqual(reference['stdout'] if 'stdout' in reference else reference.get('output'),'count\nfactory\n')
        for profile in ['debug','release']:
            native=self.cli('run','--profile',profile,ok=False,timeout=240)
            self.assertEqual(native['stdout'],'count\nfactory\n');self.assertIn('E_ASSERT',native['stderr'])
        self.source('''module cleanup;
fn main()->unit!{io}{
 let retained:list<str>=list(8,fn(i:i64)->str{return "retained"+str(i);});
 let partial:list<str>=list(16,fn(i:i64)->str{assert(i!=8);return "partial"+str(i);});
 print(retained);print(partial);
}
''')
        failed=self.cli('profile',ok=False,timeout=240)
        self.assertEqual(failed['exit_code'],70);self.assertIn('E_ASSERT',failed['stderr'])
        report=json.loads(Path(failed['output']).read_text())
        self.assertTrue(report['memory'])
        for pool in report['memory']:
            self.assertEqual(pool['live'],0,pool);self.assertEqual(pool['allocations'],pool['frees'],pool)
        self.assertEqual(report['untracked_frees'],0)

    def test_no_parallel_capacity_limit_and_current_descriptor(self):
        self.source('''module large;
fn main()->unit!{io}{let values:list<i64>=list(65537,fn(i:i64)->i64{return i;});
 assert(len(values)==65537 && values[0]==0 && values[65536]==65536);print("large-ok");}
''')
        self.assertEqual(self.cli('eval','--steps','8000000',timeout=180)['stdout'],'large-ok\n')
        self.assertEqual(self.cli('run','--profile','release',timeout=240)['stdout'],'large-ok\n')
        self.assertEqual(self.typescript(),'large-ok\n')
        cap=self.cli('describe','--field','list_construction')['value']
        self.assertEqual(cap,json.loads((h.REPO/'llm/language-pack.json').read_text())['list_construction'])
        self.assertIn('list(',self.cli('guide','--kind','list-build')['text'])

    def test_result_propagation_stays_inside_each_callback(self):
        self.source('''module result_boundary;
fn source(i:i64)->result<i64>{if i==0{return err<i64>("EMPTY","zero");}return ok(i);}
fn main()->unit!{io}{
 let values:list<result<i64>>=list(3,fn(i:i64)->result<i64>{let value:i64=source(i)?;return ok(value+10);});
 assert(len(values)==3 && error_code(values[0])=="EMPTY");
 assert(unwrap(values[1])==11 && unwrap(values[2])==12);print("result-boundary-ok");
}
fn tasks()->unit!{task,io}{
 let values:list<result<i64>>=list(3,fn(i:i64)->result<i64>!{task}{task_yield();let value:i64=source(i)?;return ok(value+10);});
 assert(len(values)==3 && error_code(values[0])=="EMPTY");
 assert(unwrap(values[1])==11 && unwrap(values[2])==12);print("task-result-boundary-ok");
}
''')
        for entry in ['main','tasks']:
            expected=('task-' if entry=='tasks' else '')+'result-boundary-ok\n'
            self.assertEqual(self.cli('eval','--entry',entry)['stdout'],expected)
            for profile in ['debug','release']:
                self.assertEqual(self.cli('run','--entry',entry,'--profile',profile,timeout=240)['stdout'],expected)
            self.assertEqual(self.typescript(entry),expected)

    def test_task_budget_exit_retires_partial_constructor_values(self):
        self.source('''module budget_cleanup;
fn main()->unit!{task,io}{
 try {
  let values:list<str>=list(100000,fn(i:i64)->str!{task,io}{
    if i==0{print("started");}task_yield();return "item"+str(i);
  });
  print("completed");print(values);
 } finally {print("user-finally");}
}
''')
        reference=self.cli('eval','--task-steps','5000',ok=False)
        self.assertEqual(reference['code'],'E_LIMIT');self.assertEqual(reference['stdout'],'started\n')
        failed=self.cli('profile','--task-steps','5000',ok=False,timeout=240)
        self.assertEqual(failed['exit_code'],70);self.assertIn('E_LIMIT',failed['stderr'])
        self.assertEqual(failed['stdout'],'started\n')
        report=json.loads(Path(failed['output']).read_text())
        self.assertTrue(report['memory'])
        for pool in report['memory']:
            self.assertEqual(pool['live'],0,pool);self.assertEqual(pool['allocations'],pool['frees'],pool)
        self.assertEqual(report['untracked_frees'],0)


if __name__=='__main__':unittest.main()
