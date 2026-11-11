"""Sequential byte construction, effect/ownership behavior and backend agreement."""
import json
import os
from pathlib import Path
import unittest
import support as h
import standard_library as helpers


class ByteConstruction(h.ToolchainCase):
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

    def agreement(self,source,expected,steps='1000000'):
        self.source(source)
        self.cli('check')
        self.assertEqual(self.cli('eval','--steps',steps,timeout=180)['stdout'],expected)
        for profile in ['debug','release']:
            self.assertEqual(self.cli('run','--profile',profile,timeout=240)['stdout'],expected)
        self.assertEqual(self.typescript(),expected)

    def test_all_shapes_values_and_one_argument_conversion(self):
        self.agreement('''module byte_values;
struct Pair {left:i64;right:i64;}
fn identity<T>(value:T)->T{return value;}
fn main()->unit!{io}{
  assert(bytes(0,fn(i:i64)->i64{return 1/i;})==unwrap(bytes([])));
  assert(bytes(4,fn(i:i64)->i64{return i*i;})==unwrap(bytes([0,1,4,9])));
  assert(bytes([0,1],identity)==unwrap(bytes([0,1])));
  let empty:bytes=bytes([],fn(x:i64)->i64{return x;});assert(len(empty)==0);
  let original:list<i64>=[0,1,2];let alias:list<i64>=original;
  assert(bytes(original,fn(x:i64)->i64{return x+1;})==unwrap(bytes([1,2,3])));
  assert(bytes([0,1,2,3],fn(x:i64)->bool{return x%2==0;},fn(x:i64)->i64{return x+10;})==unwrap(bytes([10,12])));
  assert(bytes(3,0,fn(s:i64)->i64{return s+1;},fn(s:i64)->i64{return s;})==unwrap(bytes([0,1,2])));
  assert(bytes(4,Pair(1,2),fn(p:Pair)->Pair{return Pair(p.right,p.left+p.right);},fn(p:Pair)->i64{return p.left;})==unwrap(bytes([1,2,3,5])));
  assert(original==alias && alias==[0,1,2]);
  assert(is_ok(bytes([0,255])) && !is_ok(bytes([256])) && !is_ok(bytes([-1])));
  assert(len(bytes(255,fn(i:i64)->i64{return i;}))==255);
  print("byte-values-ok");
}
''','byte-values-ok\n')

    def test_effect_order_and_typed_source_errors(self):
        self.agreement('''module ordered;
struct Stopped {index:i64;}
fn count()->i64!{io}{print("count");return 4;}
fn maker()->(fn(i64)->i64 !{io})!{io}{print("factory");return fn(i:i64)->i64!{io}{print(i);return i;};}
fn main()->unit!{io,throw}{
  let made:bytes=bytes(count(),maker());assert(len(made)==4);
  let chosen:bytes=bytes([0,1,2],fn(x:i64)->bool!{io}{print("p"+str(x));return x%2==0;},fn(x:i64)->i64!{io}{print("m"+str(x));return x+10;});
  assert(len(chosen)==2 && chosen[0]==10 && chosen[1]==12);
  try {
    let stopped:bytes=bytes(5,fn(i:i64)->i64!{io,throw}{print("s"+str(i));if i==2{throw(Stopped(i));}return i;});
    print(stopped);
  } catch(error:Stopped) {print(error.index);} finally {print("finally");}
}
''','count\nfactory\n0\n1\n2\n3\np0\nm0\np1\np2\nm2\ns0\ns1\ns2\n2\nfinally\n')

    def test_suspending_callbacks_and_genuine_task_values(self):
        self.agreement('''module task_bytes;
fn main()->unit!{task,io}{
  let output:bytes=bytes(3,0,
    fn(x:i64)->i64!{task,io}{task_yield();print("next"+str(x));return x+1;},
    fn(x:i64)->i64!{task,io}{task_yield();print("emit"+str(x));return x;});
  assert(len(output)==3 && output[0]==0 && output[2]==2);
  print("task-bytes-ok");
}
''','emit0\nnext0\nemit1\nnext1\nemit2\ntask-bytes-ok\n')

    def test_rejected_effects_types_arity_count_and_range(self):
        cases=[('module bad;fn main()->unit{let x:bytes=bytes(1,fn(i:i64)->i64!{io}{print(i);return i;});}','E_EFFECT'),
            ('module bad;fn main()->unit{let x:bytes=bytes(1,fn(i:str)->i64{return 1;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:bytes=bytes(1,fn(i:i64)->str{return "";});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:bytes=bytes(1,true,fn(i:i64)->i64{return i;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:bytes=bytes(2,0,fn(i:i64)->str{return "";},fn(i:i64)->i64{return i;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:bytes=bytes(1,fn(i:i64)->i64{return 1;},fn(i:i64)->i64{return 1;},fn(i:i64)->i64{return 1;},fn(i:i64)->i64{return 1;});}','E_ARITY')]
        for source,code in cases:
            self.source(source);self.assertEqual(self.cli('check',ok=False)['code'],code)
        self.source('''module negative;
fn main()->unit!{io}{let output:bytes=bytes(-1,fn(i:i64)->i64{return i;});print(output);}
''')
        reference=self.cli('eval',ok=False);self.assertEqual(reference['code'],'E_ASSERT')
        for profile in ['debug','release']:
            native=self.cli('run','--profile',profile,ok=False,timeout=240)
            self.assertIn('E_ASSERT',native['stderr'])
        self.source('''module range;
fn main()->unit!{io}{let output:bytes=bytes(1,fn(i:i64)->i64{return 256;});print(output);}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_RANGE')
        for profile in ['debug','release']:
            native=self.cli('run','--profile',profile,ok=False,timeout=240)
            self.assertIn('E_RANGE',native['stderr'])
        self.assertEqual(self.typescript('main',failure='E_RANGE'),'E_RANGE')

    def test_generated_bindings_do_not_capture_source_shadows(self):
        self.agreement('''module hygiene;
fn main()->unit!{io}{
 let len:fn(list<i64>)->i64=fn(values:list<i64>)->i64{return 0;};
 let assert:fn(bool)->unit=fn(ignored:bool)->unit{};
 let nex_bytes_count:i64=7;
 let output:bytes=bytes([1,2],fn(x:i64)->i64{return x+len([])+nex_bytes_count;});
 if output[0]==8 && output[1]==9{print("hygiene-ok");}else{print("wrong");}
}
''','hygiene-ok\n')

    def test_large_output_and_current_descriptor(self):
        self.source('''module large;
fn main()->unit!{io}{let output:bytes=bytes(20000,fn(i:i64)->i64{return i%256;});
 assert(len(output)==20000 && output[0]==0 && output[19999]==31);print("large-ok");}
''')
        self.assertEqual(self.cli('eval','--steps','4000000',timeout=180)['stdout'],'large-ok\n')
        self.assertEqual(self.cli('run','--profile','release',timeout=240)['stdout'],'large-ok\n')
        self.assertEqual(self.typescript(),'large-ok\n')
        cap=self.cli('describe','--field','bytes_construction')['value']
        self.assertEqual(cap,json.loads((h.REPO/'llm/language-pack.json').read_text())['bytes_construction'])
        self.assertIn('bytes(',self.cli('guide','--kind','bytes-construction')['text'])

    def test_partial_constructor_values_are_released_on_native_exit(self):
        self.source('''module cleanup;
fn main()->unit!{io}{
 let retained:bytes=bytes(8,fn(i:i64)->i64{return i;});
 let partial:bytes=bytes(16,fn(i:i64)->i64{assert(i!=8);return i;});
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


if __name__=='__main__':unittest.main()
