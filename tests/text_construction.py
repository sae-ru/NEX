"""Sequential text construction, effect/ownership behavior and backend agreement."""
import json
import os
from pathlib import Path
import unittest
import support as h
import standard_library as helpers


class TextConstruction(h.ToolchainCase):
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

    def test_all_shapes_values_and_one_argument_formatting(self):
        self.agreement('''module text_values;
struct Pair {left:i64;right:i64;}
fn identity<T>(value:T)->T{return value;}
fn main()->unit!{io}{
  assert(str(42)=="42");assert(str(true)=="true");assert(str("x")=="x");
  assert(str(0,fn(i:i64)->str{return str(1/i);})=="");
  assert(str(4,fn(i:i64)->str{return str(i*i);})=="0149");
  assert(str(["a","b"],identity)=="ab");
  let empty:str=str([],fn(x:i64)->str{return str(x);});assert(empty=="");
  let original:list<str>=["a","bb","c"];let alias:list<str>=original;
  assert(str(original,fn(x:str)->str{return x+x;})=="aabbbbcc");
  assert(str(original,fn(x:str)->bool{return len(x)>1;},fn(x:str)->str{return "["+x+"]";})=="[bb]");
  assert(str(3,10,fn(s:i64)->i64{return s+10;},fn(s:i64)->str{return str(s);})=="102030");
  assert(str(4,Pair(1,2),fn(p:Pair)->Pair{return Pair(p.right,p.left+p.right);},fn(p:Pair)->str{return str(p.left);})=="1235");
  assert(original==alias && alias==["a","bb","c"]);
  let unicode:str=str(2,fn(i:i64)->str{return "Я🌍\\u0000"+str(i);});
  assert(len(unicode)==8);assert(unicode=="Я🌍\\u00000Я🌍\\u00001");
  let closures:str=str(3,fn(i:i64)->str{return str(i)+"-";});assert(closures=="0-1-2-");
  print("text-values-ok");
}
''','text-values-ok\n')

    def test_effect_order_and_typed_source_errors(self):
        self.agreement('''module ordered;
struct Stopped {index:i64;}
fn count()->i64!{io}{print("count");return 4;}
fn maker()->(fn(i64)->str !{io})!{io}{print("factory");return fn(i:i64)->str!{io}{print(i);return str(i);};}
fn main()->unit!{io,throw}{
  let made:str=str(count(),maker());assert(made=="0123");
  let chosen:str=str([0,1,2],fn(x:i64)->bool!{io}{print("p"+str(x));return x%2==0;},fn(x:i64)->str!{io}{print("m"+str(x));return str(x+10);});
  assert(chosen=="1012");
  try {
    let stopped:str=str(5,fn(i:i64)->str!{io,throw}{print("s"+str(i));if i==2 {throw(Stopped(i));}return str(i);});
    print(stopped);
  } catch(error:Stopped) {print(error.index);} finally {print("finally");}
  let values:str=str(3,0,fn(x:i64)->i64!{io}{print("n"+str(x));return x+1;},fn(x:i64)->str!{io}{print("e"+str(x));return str(x);});
  assert(values=="012");
}
''','count\nfactory\n0\n1\n2\n3\np0\nm0\np1\np2\nm2\ns0\ns1\ns2\n2\nfinally\ne0\nn0\ne1\nn1\ne2\n')

    def test_suspending_callbacks_and_genuine_task_values(self):
        self.agreement('''module task_text;
struct Stopped {value:i64;}
fn main()->unit!{task,io,throw}{
  let output:str=str(3,0,
    fn(x:i64)->i64!{task,io}{task_yield();print("next"+str(x));return x+1;},
    fn(x:i64)->str!{task,io}{task_yield();print("emit"+str(x));return str(x);});
  assert(output=="012");
  try {let stopped:str=str(4,fn(i:i64)->str!{task,throw}{task_yield();if i==2{throw(Stopped(i));}return str(i);});}
  catch(error:Stopped){print(error.value);}finally{print("drained");}
  let total:i64=with_tasks(2,fn(scope:task_scope)->i64!{task,throw}{
    let jobs:list<task<i64>>=list(4,fn(i:i64)->task<i64>!{task}{return task_spawn(scope,fn()->i64{return i*2;});});
    let values:str=str(jobs,fn(job:task<i64>)->str!{task,throw}{return str(task_wait(job));});
    assert(values=="0246");return 6;
  });
  assert(total==6);print("task-text-ok");
}
''','emit0\nnext0\nemit1\nnext1\nemit2\n2\ndrained\ntask-text-ok\n')

    def test_rejected_effects_types_arity_and_negative_count(self):
        cases=[('module bad;fn main()->unit{let x:str=str(1,fn(i:i64)->str!{io}{print(i);return "";});}','E_EFFECT'),
            ('module bad;fn main()->unit{let x:str=str(1,fn(i:str)->str{return i;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:str=str(1,fn(i:i64)->i64{return i;});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:str=str(1,true,fn(i:i64)->str{return "";});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:str=str(2,0,fn(i:i64)->str{return "";},fn(i:i64)->str{return "";});}','E_TYPE'),
            ('module bad;fn main()->unit{let x:str=str(1,fn(i:i64)->str{return "";},fn(i:i64)->str{return "";},fn(i:i64)->str{return "";},fn(i:i64)->str{return "";});}','E_ARITY')]
        for source,code in cases:
            self.source(source);self.assertEqual(self.cli('check',ok=False)['code'],code)
        self.source('''module negative;
fn main()->unit!{io}{let output:str=str(-1,fn(i:i64)->str{return str(i);});print(output);}
''')
        reference=self.cli('eval',ok=False);self.assertEqual(reference['code'],'E_ASSERT')
        for profile in ['debug','release']:
            native=self.cli('run','--profile',profile,ok=False,timeout=240)
            self.assertIn('E_ASSERT',native['stderr'])
        self.source('''module negative_ts;
fn main()->unit!{io}{let output:str=str(-1,fn(i:i64)->str{return str(i);});print(output);}
''')
        self.assertEqual(self.typescript('main',failure='E_ASSERT'),'E_ASSERT')

    def test_generated_bindings_do_not_capture_source_shadows(self):
        self.agreement('''module hygiene;
fn main()->unit!{io}{
 let len:fn(list<i64>)->i64=fn(values:list<i64>)->i64{return 0;};
 let assert:fn(bool)->unit=fn(ignored:bool)->unit{};
 let nex_text_count:i64=7;
 let output:str=str([1,2],fn(x:i64)->str{return str(x+len([])+nex_text_count);});
 if output=="89"{print("hygiene-ok");}else{print("wrong");}
}
''','hygiene-ok\n')

    def test_large_output_and_current_descriptor(self):
        self.source('''module large;
fn main()->unit!{io}{let output:str=str(20000,fn(i:i64)->str{return "x";});
 assert(len(output)==20000);print("large-ok");}
''')
        self.assertEqual(self.cli('eval','--steps','4000000',timeout=180)['stdout'],'large-ok\n')
        self.assertEqual(self.cli('run','--profile','release',timeout=240)['stdout'],'large-ok\n')
        self.assertEqual(self.typescript(),'large-ok\n')
        cap=self.cli('describe','--field','text_construction')['value']
        self.assertEqual(cap,json.loads((h.REPO/'llm/language-pack.json').read_text())['text_construction'])
        self.assertIn('str(',self.cli('guide','--kind','text-construction')['text'])

    def test_partial_constructor_values_are_released_on_native_exit(self):
        self.source('''module cleanup;
fn main()->unit!{io}{
 let retained:str=str(8,fn(i:i64)->str{return "retained"+str(i);});
 let partial:str=str(16,fn(i:i64)->str{assert(i!=8);return "partial"+str(i);});
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
