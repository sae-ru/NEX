"""Observable runtime contracts across source projection, history and backends."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as harness


class RuntimeContracts(harness.ToolchainCase):
    def contract(self, symbol, requires=(), ensures=('true',)):
        value=self.cli('contract','--symbol',symbol)
        value['functions'][0]['requires']=list(requires)
        value['functions'][0]['ensures']=list(ensures)
        return value

    def generate(self, contract, name='guarded', ok=True):
        path=self.root/(name+'.json');path.write_text(json.dumps(contract,ensure_ascii=False))
        directory=self.root/name
        result=self.cli('contract','--kind','runtime','--contracts',path,'--directory',directory,ok=ok,timeout=120)
        if ok:
            self.assertEqual(result['schema'],'nex.runtime-contract-session/1')
            self.assertFalse(result['proof_performed']);self.assertFalse(result['loop_checks'])
            self.assertNotEqual(result['origin_revision'],result['revision'])
            self.assertEqual(self.cli('check',cwd=directory)['revision'],result['revision'])
        else:self.assertFalse(directory.exists())
        return directory,result

    def web(self,directory,entry='main'):
        folder=directory/('typescript-'+entry)
        self.cli('emit','--kind','typescript','--entry',entry,'--directory',folder,cwd=directory)
        (folder/'package.json').write_text('{"type":"module"}')
        (folder/'driver.ts').write_text("""import { entry } from './program.ts';
import { str, NexError } from './nex-runtime.ts';
let stdout = ''; console.log = value => { stdout += String(value) + '\\n'; };
let result; try { const value=entry(); result={ok:true,value:value===undefined?null:str(value),stdout}; }
catch(e) { if (!(e instanceof NexError)) throw e; result={ok:false,code:e.code,stdout}; }
process.stdout.write(JSON.stringify(result));
""")
        process=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',folder/'driver.ts'],capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        return json.loads(process.stdout)

    def agreement(self,directory,entry='main',value=None,stdout='',failure=None):
        reference=self.cli('eval','--entry',entry,cwd=directory,ok=failure is None)
        web=self.web(directory,entry)
        if failure is None:
            self.assertEqual(reference['value'],value);self.assertEqual(reference['stdout'],stdout)
            self.assertEqual(web,{'ok':True,'value':None if value is None else str(value).lower(),'stdout':stdout})
        else:
            self.assertEqual(reference['code'],failure)
            self.assertEqual(web,{'ok':False,'code':failure,'stdout':stdout})
        for profile in ('debug','release'):
            native=self.cli('run','--entry',entry,'--profile',profile,cwd=directory,ok=failure is None and (value is None or value == 0),timeout=240)
            self.assertEqual(native['stdout'],stdout)
            if failure:self.assertIn(failure,native['stderr'])
            else:self.assertEqual(native['exit_code'],0 if value is None else value & 255);self.assertEqual(native['stderr'],'')

    def test_discovery_pins_history_and_relocated_source(self):
        self.source("""module guards;
pub fn increment(x:i64)->i64{return x+1;}
fn main()->i64{return increment(4);}
test fn sample()->unit{assert(increment(4)==5);}
""")
        feature=self.cli('describe','--field','runtime_contracts')['value']
        pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(feature,pack['runtime_contracts'])
        self.assertEqual(self.cli('guide','--kind','runtime-contract')['text'],(harness.REPO/feature['guide']).read_text())
        contract=self.contract('increment',['x < 9223372036854775807'],['result == x + 1'])
        original=self.file.read_bytes();state=harness.database_rows(self.root/'.nex/graph.db')
        directory,report=self.generate(contract)
        self.assertEqual(self.file.read_bytes(),original)
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),state)
        receipt=json.loads(Path(report['receipt']).read_text())
        self.assertEqual(receipt['contracts'],contract)
        self.assertEqual(receipt['origin_bundle']['files']['main.nex'].encode(),original)
        self.assertEqual(len(receipt['contract_hash']),64)
        regenerated,second=self.generate(contract,'same-guards')
        self.assertEqual(second['contract_hash'],receipt['contract_hash'])
        self.assertEqual(second['revision'],receipt['revision'])
        self.assertEqual(second['source_hash'],receipt['source_hash'])
        self.cli('test',cwd=directory,timeout=240);self.cli('test','--target','web',cwd=directory,timeout=240)
        self.file.unlink();(self.root/'guarded.json').unlink()
        self.agreement(directory,value=5)
        self.cli('export','--directory',self.root/'reexported',cwd=directory)
        self.assertEqual(self.cli('eval',cwd=self.root/'reexported')['value'],5)

    def test_requires_precede_body_and_checked_order(self):
        self.source("""module pre;
fn guarded(x:i64)->i64{return 9223372036854775807+x;}
fn main()->i64{return guarded(1);}
""")
        directory,_=self.generate(self.contract('guarded',['x==0','10/x>0']))
        self.agreement(directory,failure='E_ASSERT')
        directory,_=self.generate(self.contract('guarded',['10/(x-1)>0']),'undefined')
        self.agreement(directory,failure='E_DIV_ZERO')
        directory,_=self.generate(self.contract('guarded',ensures=['false']),'body-fault')
        self.agreement(directory,failure='E_OVERFLOW')

    def test_postconditions_observe_actual_finally_return_and_original_parameters(self):
        self.source("""module post;
fn choose(x:i64)->i64{try{let x:i64=99;return x;}finally{return 7;}}
fn main()->i64{return choose(2);}
""")
        directory,_=self.generate(self.contract('choose',['x==2'],['result==7 && x==2']))
        self.agreement(directory,value=7)
        directory,_=self.generate(self.contract('choose',ensures=['result==99']),'bad-post')
        self.agreement(directory,failure='E_ASSERT')

    def test_recursion_function_references_and_multiple_roots(self):
        self.source("""module recursive;
fn sum(n:i64)->i64{if n==0{return 0;}return n+sum(n-1);}
fn apply(f:fn(i64)->i64,x:i64)->i64{return f(x);}
fn identity(x:i64)->i64{return x;}
fn main()->i64{return apply(sum,3)+identity(4);}
fn bad()->i64{return sum(-1);}
""")
        contract=self.contract('sum',['n>=0'],['result>=0'])
        contract['functions']+=self.contract('identity',ensures=['result==x'])['functions']
        directory,_=self.generate(contract)
        self.agreement(directory,value=10)
        self.agreement(directory,'bad',failure='E_ASSERT')

    def test_unit_fallthrough_explicit_return_and_short_circuit(self):
        self.source("""module units;
fn complete(x:bool)->unit{if x{return;}let result:i64=1;assert(result==1);}
fn main()->unit{complete(true);complete(false);}
""")
        directory,_=self.generate(self.contract('complete',['true || 1/0==1'],['x || !x']))
        self.agreement(directory)
        directory,_=self.generate(self.contract('complete',ensures=['!x']),'unit-post')
        self.agreement(directory,failure='E_ASSERT')

    def test_fatal_contracts_skip_handlers_and_finalizers_and_cleanup_owned_values(self):
        self.source("""module fatal;
fn guarded(x:i64)->i64{let owned:list<str>=["λ🙂", "kept"];assert(len(owned)==2);return x;}
fn main()->unit !{io}{
 let owned:list<str>=["outer"];
 print("before");
 try{try{let value:i64=guarded(1);}catch(c,m){print("caught");}}
 finally{print("finalized");}
}
""")
        directory,_=self.generate(self.contract('guarded',ensures=['result==0']))
        self.agreement(directory,failure='E_ASSERT',stdout='before\n')
        profile=self.cli('profile','--scenario','postcondition-failure',cwd=directory,ok=False,timeout=300)
        self.assertEqual(profile['stdout'],'before\n')
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_comment_braces_and_predicate_text_cannot_swallow_checks(self):
        self.source("""module lexical;
fn guarded(x:i64)->i64{let braces:str="}{"; // } {
assert(len(braces)==2);return x;}
fn main()->i64{return guarded(1);}
""")
        directory,_=self.generate(self.contract('guarded',['true // trailing comment'],['result==0 // trailing comment']))
        self.agreement(directory,failure='E_ASSERT')

    def test_imported_roots_same_module_names_and_server_realm(self):
        self.source("""module imports;
import "./helper.nex" as helper;
fn value(x:i64)->i64{return x;}
fn main()->i64{return helper::value(value(2));}
""")
        (self.root/'helper.nex').write_text('module helper; pub fn value(x:i64)->i64{return x+1;}\n')
        directory,_=self.generate(self.contract('helper::value',ensures=['result==x+1']))
        self.agreement(directory,value=3)
        self.source("""module realms;
server fn helper(x:i64)->i64{return x+1;}
server fn guarded(x:i64)->i64{return helper(x);}
server fn main()->i64{return guarded(2);}
""")
        directory,_=self.generate(self.contract('guarded',ensures=['result==x+1']),'server')
        self.assertEqual(self.cli('eval',cwd=directory)['value'],3)
        self.assertEqual(self.cli('run',cwd=directory,ok=False,timeout=240)['exit_code'],3)
        self.assertEqual(self.cli('emit','--kind','typescript',cwd=directory,ok=False)['code'],'E_REALM')

    def test_stale_pins_unknown_fields_and_invalid_predicates_create_no_output(self):
        self.source('module rejected; fn guarded(x:i64)->i64{return x;}\n')
        original=self.contract('guarded')
        variants=[]
        for field in ('expected_revision','source_hash'):
            changed=copy.deepcopy(original);changed[field]='0'*64;variants.append((changed,'E_CONTRACT_STALE'))
        changed=copy.deepcopy(original);changed['functions'][0]['content_hash']='0'*64;variants.append((changed,'E_CONTRACT_STALE'))
        changed=copy.deepcopy(original);changed['unexpected']=True;variants.append((changed,'E_CONTRACT'))
        for predicate in ('assert(true)','len("x")==1','x.field==0','[1][0]==1','1','missing==0'):
            changed=copy.deepcopy(original);changed['functions'][0]['requires']=[predicate];variants.append((changed,None))
        state=harness.database_rows(self.root/'.nex/graph.db')
        for index,(contract,code) in enumerate(variants):
            with self.subTest(index=index):
                _,result=self.generate(contract,'rejected'+str(index),ok=False)
                if code:self.assertEqual(result['code'],code)
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),state)

    def test_scope_rejections_and_loop_annotations_are_explicit(self):
        self.source("""module scope;
fn heap(x:str)->i64{return len(x);}
fn generic<T>(x:T)->T{return x;}
fn effect()->i64 !{io}{print(1);return 1;}
test fn tested()->unit{}
fn looped(n:i64)->i64{var i:i64=0;while i<n{i=i+1;}return i;}
fn main()->i64{return looped(3);}
""")
        for symbol in ('heap','generic','effect','tested','looped'):
            with self.subTest(symbol=symbol):
                _,result=self.generate(self.contract(symbol),'reject-'+symbol,ok=False)
                self.assertEqual(result['code'],'E_CONTRACT_RUNTIME')
        contract=self.contract('looped',ensures=['result==n']);contract['functions'][0]['loops']=[]
        directory,_=self.generate(contract)
        self.agreement(directory,value=3)

    def test_cli_rejects_unknown_kind_oversized_contract_and_existing_output(self):
        self.source('module cli; fn guarded()->unit{}\n')
        contract=self.contract('guarded')
        self.assertEqual(self.cli('contract','--kind','typo','--symbol','guarded',ok=False)['code'],'E_OPTION')
        huge=self.root/'huge.json';huge.write_bytes(b' '*1048577)
        output=self.root/'huge-output'
        self.assertEqual(self.cli('contract','--kind','runtime','--contracts',huge,'--directory',output,ok=False)['code'],'E_CONTRACT')
        self.assertFalse(output.exists())
        target=self.root/'existing';target.mkdir();(target/'keep').write_text('preserve')
        path=self.root/'contract.json';path.write_text(json.dumps(contract))
        self.assertEqual(self.cli('contract','--kind','runtime','--contracts',path,'--directory',target,ok=False)['code'],'E_EXISTS')
        self.assertEqual((target/'keep').read_text(),'preserve');self.assertEqual(len(list(target.iterdir())),1)



    def test_bool_result_fresh_binding_and_calls_from_joined_tasks(self):
        self.source("module bools; fn positive(result:i64)->bool{return result>0;} fn main()->i64{if positive(2){return 4;}return 0;}\n")
        contract=self.contract('positive',['result==2'],['result_'])
        self.assertEqual(contract['functions'][0]['returns'],'result_')
        directory,_=self.generate(contract)
        self.agreement(directory,value=4)
        self.source("module scheduled; fn inc(x:i64)->i64{return x+1;} test fn child()->unit !{task,throw}{with_tasks(2,fn(scope:task_scope)->unit !{task,throw}{let result:task<i64>=task_spawn(scope,fn()->i64{return inc(4);});assert(task_wait(result)==5);});}\n")
        directory,_=self.generate(self.contract('inc',['x>=0'],['result==x+1']),'scheduled')
        self.cli('test',cwd=directory,timeout=240)
        self.cli('test','--target','web',cwd=directory,timeout=240)

        self.source("module minimum; fn identity(x:i64)->i64{return x;} fn main()->unit{assert(identity(-9223372036854775808)==-9223372036854775808);}\n")
        directory,_=self.generate(self.contract('identity',['x == -9223372036854775808 && x % -1 == 0'],['result == x && (true || 1 / 0 == 0)']),'minimum')
        self.agreement(directory)

    def test_shipped_example_pins_and_runtime_projection(self):
        shutil.copytree(harness.REPO/'examples/runtime-contracts',self.root,dirs_exist_ok=True)
        contract=json.loads((self.root/'contracts.json').read_text())
        self.assertEqual(contract['expected_revision'],self.cli('check')['revision'])
        self.assertTrue(self.cli('verify','--contracts','contracts.json',timeout=90)['ok'])
        directory,_=self.generate(contract)
        self.agreement(directory,stdout='5\n')
        self.cli('test',cwd=directory,timeout=240)
        self.cli('test','--target','web',cwd=directory,timeout=240)



    def test_generated_scalar_proof_and_no_added_closure_allocations(self):
        self.source("module measured; fn increment(x:i64)->i64{return x+1;} fn main()->unit{var i:i64=0;var total:i64=0;while i<50000{total=total+increment(i);i=i+1;}assert(total==1250025000);}\n")
        original=self.contract('increment',['x>=0','x<9223372036854775807'],['result==x+1'])
        directory,report=self.generate(original)
        self.assertTrue(report['functions'][0]['implementation_symbol'].startswith('measured::'))
        proof=self.cli('contract','--symbol','increment',cwd=directory)
        proof['functions'][0]['requires']=original['functions'][0]['requires']
        proof['functions'][0]['ensures']=original['functions'][0]['ensures']
        path=directory/'proof.json';path.write_text(json.dumps(proof))
        verified=self.cli('verify','--contracts',path,cwd=directory,timeout=90)
        self.assertTrue(verified['ok']);self.assertEqual(verified['functions'][0]['status'],'proven')
        profile=self.cli('profile','--scenario','scalar-contract-allocations',cwd=directory,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['allocations'],0);self.assertEqual(pool['live'],0)

    def test_generated_names_preserve_existing_source_definitions(self):
        body='module collision; fn increment(x:i64)->i64{return x+1;} fn main()->unit{assert(increment(4)==5);}\n'
        self.source(body)
        _,first=self.generate(self.contract('increment',ensures=['result==x+1']),'first')
        implementation=first['functions'][0]['implementation_symbol'].split('::')[-1]
        changed=body.replace('assert(increment(4)==5);','assert(increment(4)==5);assert('+implementation+'()==99);')
        changed+='fn '+implementation+'()->i64{return 99;}\n'
        self.source(changed)
        directory,second=self.generate(self.contract('increment',ensures=['result==x+1']),'collision')
        self.assertNotEqual(first['functions'][0]['implementation_symbol'],second['functions'][0]['implementation_symbol'])
        self.agreement(directory)


if __name__=='__main__':unittest.main()
