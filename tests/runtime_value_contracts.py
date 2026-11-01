"""Effectful/owned runtime contract boundaries and pure expression predicates."""
import copy
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import unittest
import runtime_contracts as common
import support as harness


class RuntimeValueContracts(harness.ToolchainCase):
    contract=common.RuntimeContracts.contract
    generate=common.RuntimeContracts.generate
    web=common.RuntimeContracts.web
    agreement=common.RuntimeContracts.agreement

    def value_projection(self,contract,name='guarded'):
        directory,session=self.generate(contract,name)
        self.assertEqual(session['schema'],'nex.runtime-contract-session/3')
        self.assertEqual(session['predicate_scope'],'pure_source_expressions')
        receipt=json.loads(Path(session['receipt']).read_text())
        self.assertEqual(receipt['schema'],'nex.runtime-contract-candidate/3')
        self.assertEqual(receipt['predicate_scope'],session['predicate_scope'])
        for function in receipt['functions']:
            self.assertIn(function['realm'],('shared','server','client'))
            self.assertIn('parameters',function);self.assertIn('result_type',function)
            self.assertIn('effects',function);self.assertIn('loops',function)
        return directory,session

    def settled_profile(self,directory,ok=True):
        profile=self.cli('profile','--scenario','value-contract-ownership',cwd=directory,ok=ok,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_imported_generic_values_original_signature_and_normal_finalizers(self):
        self.source('''module application;
import "./service.nex" as service;
import "./model.nex" as model;
fn main()->unit !{io}{
 let input:model::Packet<f64>=model::Packet<f64>("λ🙂",[1.25,2.5],utf8_bytes("raw"));
 let output:model::Packet<f64>=service::transform(input);
 assert(input.text=="λ🙂" && output.text=="done🙂");
}
''')
        (self.root/'model.nex').write_text('module model; pub struct Packet<T>{text:str;values:list<T>;raw:bytes;}\n',newline='\n')
        (self.root/'service.nex').write_text('''module service;
import "./model.nex" as types;
pub fn transform(input:types::Packet<f64>) -> (types::Packet<f64>) !{io}{
 print("body");
 try{return input;}finally{print("finally");return types::Packet<f64>("done🙂",input.values,input.raw);}
}
''',newline='\n')
        contract=self.contract('service::transform',
            ['len(input.text)==2','input.values[0]==1.25 && input.raw==utf8_bytes("raw")'],
            ['result.text=="done🙂"','result.values==input.values && result.raw==input.raw','input.text=="λ🙂"'])
        before=harness.database_rows(self.root/'.nex/graph.db')
        directory,report=self.value_projection(contract)
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)
        self.assertEqual(report['functions'][0]['effects'],['io'])
        source=(directory/'service.nex').read_text()
        self.assertIn('-> (types::Packet<f64>) !{io}',source)
        self.assertEqual(source.count('pub fn transform'),1)
        self.agreement(directory,stdout='body\nfinally\n')
        self.settled_profile(directory)

    def test_returned_effectful_callable_keeps_inner_and_outer_effects(self):
        self.source('''module callbacks;
fn sink(value:str)->unit !{io}{print(value);}
pub fn choose(callback:fn(str)->unit !{io})->(fn(str)->unit !{io}) !{io}{
 try{return callback;}finally{print("choose");}
}
fn main()->unit !{io}{let callback:fn(str)->unit !{io}=choose(sink);callback("called");}
''')
        directory,_=self.value_projection(self.contract('choose',ensures=['result==callback']))
        self.agreement(directory,stdout='choose\ncalled\n')
        rejected=self.contract('choose',requires=['callback("forbidden")==callback("again")'])
        _,error=self.generate(rejected,'impure-indirect',ok=False)
        self.assertEqual(error['code'],'E_EFFECT')

    def test_typed_and_legacy_escapes_skip_postconditions_after_finalizers(self):
        self.source('''module errors;
struct Fault{message:str;}
fn risky(typed:bool)->list<str> !{io,throw}{
 let owned:list<str>=["kept🙂"];
 print("body");
 try{if typed{throw(Fault(owned[0]));}throw("E_CUSTOM",owned[0]);}
 finally{print("finally");}
}
fn main()->unit !{io}{
 try{let ignored:list<str>=risky(true);}catch(error:Fault){print(error.message);}catch(code,message){assert(false);}
 try{let ignored:list<str>=risky(false);}catch(code,message){print(code);print(message);}
}
''')
        directory,_=self.value_projection(self.contract('risky',ensures=['false']))
        self.agreement(directory,stdout='body\nfinally\nkept🙂\nbody\nfinally\nE_CUSTOM\nkept🙂\n')
        self.settled_profile(directory)

    def test_result_propagation_remains_an_ordinary_postcondition_value(self):
        self.source('''module results;
fn checked(x:result<list<str>>)->result<list<str>>{
 let items:list<str>=x?;return ok(push(items,"tail"));
}
fn main()->unit{
 assert(is_ok(checked(ok(["head"]))));
 assert(error_code(checked(err<list<str>>("E_INPUT","message")))=="E_INPUT");
}
''')
        directory,_=self.value_projection(self.contract('checked',ensures=[
            'is_ok(x)==is_ok(result)',
            '!is_ok(x) || unwrap(result)==push(unwrap(x),"tail")',
            'is_ok(x) || error_code(result)==error_code(x)']))
        self.agreement(directory)

    def test_pure_helpers_match_closures_and_lexical_tokens(self):
        self.source('''module predicates;
enum Choice{Some(text:str);None;}
fn identity<T>(x:T)->T{return x;}
fn checked(x:Choice)->Choice{return x;}
fn main()->unit{assert(checked(Choice::Some("} // λ🙂
"))==Choice::Some("} // λ🙂
"));}
'''.replace('λ🙂\n','λ🙂\\n'))
        contract=self.contract('checked',requires=[
            'match x {Choice::Some(text)=>len(text)>0,Choice::None()=>true} // removed',
            '(fn(value:bool)->bool{return value;})(true)'],ensures=[
            'result==identity<Choice>(x) // } ; assert(false);',
            '(fn(value:bool)->bool{return !value;})(false)',
            'len([1,2])==2 && [1,2][1]==2 && 1.0==1e0'])
        directory,_=self.value_projection(contract)
        self.agreement(directory)

    def test_predicate_traps_preserve_order_short_circuit_and_owned_cleanup(self):
        self.source('''module traps;
fn guarded(text:str)->str !{io}{print("body");return text;}
fn main()->unit !{io}{let owned:list<str>=["λ🙂"];print("before");
 try{let value:str=guarded(owned[0]);}finally{print("finally");}}
''')
        contract=self.contract('guarded',requires=['false && text[9]=="x"'],ensures=['false'])
        directory,_=self.value_projection(contract)
        self.agreement(directory,failure='E_ASSERT',stdout='before\n')
        self.settled_profile(directory,ok=False)
        contract=self.contract('guarded',ensures=['result[2]=="x"'])
        directory,_=self.value_projection(contract,'bounds')
        self.agreement(directory,failure='E_BOUNDS',stdout='before\nbody\n')
        self.settled_profile(directory,ok=False)
        contract=self.contract('guarded',ensures=['len(unwrap(decode_utf8(unwrap(bytes([255])))))==0'])
        directory,_=self.value_projection(contract,'utf8')
        self.agreement(directory,failure='E_RESULT',stdout='before\nbody\n')

    def test_effectful_task_root_suspends_and_checks_the_completed_value(self):
        self.source('''module tasks;
fn work(text:str)->list<str> !{task}{try{task_yield();return [text];}finally{task_yield();}}
fn main()->unit !{task,throw}{with_tasks(2,fn(scope:task_scope)->unit !{task,throw}{
 let future:task<list<str>>=task_spawn(scope,fn()->list<str> !{task}{return work("λ🙂");});
 assert(task_wait(future)==["λ🙂"]);});}
''')
        directory,_=self.value_projection(self.contract('work',['len(text)==2'],['result==[text]']))
        self.agreement(directory)
        self.settled_profile(directory)
        directory,_=self.value_projection(self.contract('work',ensures=['false']),'bad-post')
        self.agreement(directory,failure='E_ASSERT')
        self.settled_profile(directory,ok=False)

    def test_root_effects_never_authorize_predicates_and_rejections_are_atomic(self):
        self.source('''module purity;
fn side()->bool !{io}{print("side");return true;}
fn raise()->bool !{throw}{throw("E","message");}
server fn disk()->bool !{fs}{return is_ok(file_read_text("input"));}
server fn checked(x:str)->str !{fs,io,db,ffi,task,throw}{return x;}
''')
        original=self.contract('checked')
        before=harness.database_rows(self.root/'.nex/graph.db')
        for index,predicate in enumerate(['side()','true || side()','raise()','disk()',
                                          'is_ok(file_read_text("input"))','task_cancel(x)',
                                          '(fn()->bool !{io}{print("side");return true;})()',
                                          'missing=="x"','1','x?==x']):
            with self.subTest(predicate=predicate):
                contract=copy.deepcopy(original);contract['functions'][0]['requires']=[predicate]
                self.generate(contract,'rejected-'+str(index),ok=False)
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)

    def test_cancellation_and_deadline_skip_contract_posts_and_user_finalizers(self):
        self.source('''module cancellation;
fn work(ready:channel<bool>,text:str)->list<str> !{task}{let kept:list<str>=[text];
 try{assert(task_send(ready,true));while true{task_yield();}return kept;}
 finally{assert(false);}}
fn main()->unit !{task,throw}{with_tasks(2,fn(scope:task_scope)->unit !{task,throw}{
 let ready:channel<bool>=channel_new<bool>(scope,1);
 let child:task<list<str>>=task_spawn(scope,fn()->list<str> !{task}{return work(ready,"λ🙂");});
 assert(unwrap(task_recv(ready)));assert(task_cancel(child));let ignored:list<str>=task_wait(child);
});}
''')
        contract=self.contract('work',ensures=['false']);contract['functions'][0]['loops']=[]
        directory,_=self.value_projection(contract)
        self.agreement(directory,failure='E_CANCELLED')
        self.settled_profile(directory,ok=False)
        self.source('''module deadline;
fn work(text:str)->list<str> !{task}{let kept:list<str>=[text];
 try{while true{task_yield();}return kept;}finally{assert(false);}}
fn main()->unit !{task}{let ignored:list<str>=work("λ🙂");}
''')
        contract=self.contract('work',ensures=['false']);contract['functions'][0]['loops']=[]
        directory,_=self.value_projection(contract,'deadline')
        flags=['--task-steps','1000000000','--task-timeout-ms','30']
        self.assertEqual(self.cli('eval',*flags,cwd=directory,ok=False)['code'],'E_TIMEOUT')
        for profile in ('debug','release'):
            native=self.cli('run','--profile',profile,*flags,cwd=directory,ok=False,timeout=240)
            self.assertIn('E_TIMEOUT',native['stderr']);self.assertNotIn('E_ASSERT',native['stderr'])
        profile=self.cli('profile','--scenario','value-deadline',*flags,cwd=directory,ok=False,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_file_owner_aliases_and_effectful_reads_keep_operator_grants(self):
        self.source('''module files;
server fn identity(owner:file)->file{return owner;}
server fn read(path:str)->result<str> !{fs}{return file_read_text(path);}
server fn main()->unit !{fs,io}{
 let owner:file=unwrap(file_open_read("input"));let alias:file=identity(owner);
 assert(file_close(alias));assert(!file_close(owner));
 print(unwrap(read("input")));assert(!is_ok(read("missing")));
}
''')
        contract=self.contract('identity',ensures=['result==owner'])
        contract['functions']+=self.contract('read',ensures=[
            '(path=="input" && is_ok(result) && unwrap(result)=="λ🙂") || (path=="missing" && !is_ok(result))'])['functions']
        directory,_=self.value_projection(contract)
        data=self.root/'data';data.mkdir();(data/'input').write_text('λ🙂',newline='\n')
        environment={'NEX_FILES_ROOT':str(data)}
        reference=self.cli('eval',env=environment,cwd=directory)
        self.assertEqual(reference['stdout'],'λ🙂\n')
        for profile in ('debug','release'):
            native=self.cli('run','--profile',profile,env=environment,cwd=directory,timeout=240)
            self.assertEqual(native['stdout'],'λ🙂\n');self.assertEqual(native['stderr'],'')
        self.assertEqual(self.cli('emit','--kind','typescript',cwd=directory,ok=False)['code'],'E_REALM')
        profile=self.cli('profile','--scenario','value-file-owners',env=environment,cwd=directory,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])
        rejected=self.contract('identity',requires=['file_is_open(owner)'])
        _,error=self.generate(rejected,'forbidden-file-observation',ok=False)
        self.assertEqual(error['code'],'E_EFFECT')

    def test_effectful_unit_fallthrough_and_explicit_return(self):
        self.source('''module units;
fn report(text:str,early:bool)->unit !{io}{print(text);if early{return;}assert(len(text)==2);}
fn main()->unit !{io}{report("λ🙂",true);report("λ🙂",false);}
''')
        contract=self.contract('report',['len(text)==2'],['text[1]=="🙂"'])
        self.assertEqual(contract['functions'][0]['returns'],'')
        directory,_=self.value_projection(contract)
        self.agreement(directory,stdout='λ🙂\nλ🙂\n')

    def test_foreign_body_runs_once_with_the_original_pin_and_explicit_grant(self):
        source='''module foreign_contract;
server extern fn echo(text:str)->str !{ffi}=foreign("contract","echo","@PIN@");
server extern fn calls()->i64 !{ffi}=foreign("contract","calls","@PIN@");
server fn guarded(text:str)->str !{ffi}{return echo(text);}
server fn main()->unit !{ffi,io}{assert(guarded("λ🙂")=="λ🙂");assert(calls()==1);print("once");}
'''
        self.source(source.replace('@PIN@','0'*64))
        signatures={name:self.cli('ffi','--symbol',name) for name in ('echo','calls')}
        digests={name:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
                 for name,value in signatures.items()}
        producer=self.root/'provider.c'
        producer.write_text('''#include "nex_ffi_module.h"
static int64_t count;
static nex_ffi_status echo(const nex_ffi_api_v1*a,nex_ffi_call c,const nex_ffi_ref*v,uint64_t n,nex_ffi_ref*o,void*u){
 (void)a;(void)c;(void)u;if(n!=1)return NEX_FFI_ARGUMENT;++count;*o=v[0];return NEX_FFI_OK;}
static nex_ffi_status calls(const nex_ffi_api_v1*a,nex_ffi_call c,const nex_ffi_ref*v,uint64_t n,nex_ffi_ref*o,void*u){
 (void)v;(void)u;if(n)return NEX_FFI_ARGUMENT;return a->make_i64(c,count,o);}
static const nex_ffi_export_v1 exports[]={'''+','.join(
            '{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(digests[name])+','+name+',0}'
            for name in digests)+'''};
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1*nex_ffi_module_entry(uint32_t abi,uint32_t size){
 static const nex_ffi_module_v1 m={1,sizeof(nex_ffi_module_v1),2,sizeof(nex_ffi_export_v1),exports};
 return abi==1&&size>=sizeof(nex_ffi_api_v1)?&m:0;}
''',newline='\n')
        bundle=self.root/'bundle';bundle.mkdir();binary=bundle/('module.dll' if os.name=='nt' else 'module')
        driver=self.cli('doctor')['native_compiler']
        if os.name=='nt':driver=str(Path(driver).with_name('clang.exe'))
        compiled=subprocess.run([driver,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden',
                                 '-I'+str(harness.REPO/'runtime'),str(producer),'-o',str(binary)],
                                capture_output=True,text=True,timeout=60)
        self.assertEqual(compiled.returncode,0,compiled.stdout+compiled.stderr)
        if os.name=='nt':binary.rename(bundle/'module')
        (bundle/'NOTICE').write_text('NEX runtime-contract FFI test fixture\n',newline='\n')
        machine={'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','AMD64':'x86_64'}[platform.machine()]
        manifest={'schema':'nex.foreign-bundle/1','platform':{'Darwin':'macos','Linux':'linux','Windows':'windows'}[platform.system()]+'-'+machine,
                  'entry':'module','files':[{'path':name,'sha256':hashlib.sha256((bundle/name).read_bytes()).hexdigest()} for name in ('module','NOTICE')],
                  'exports':digests,'notices':['NOTICE']}
        (bundle/'manifest.json').write_text(json.dumps(manifest),newline='\n')
        pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()
        host=self.root/'host.json';host.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':1,
            'libraries':{'contract':{'directory':'bundle','manifest_sha256':pin,'exports':['echo','calls']}}}),newline='\n')
        self.source(source.replace('@PIN@',pin))
        directory,_=self.value_projection(self.contract('guarded',['len(text)==2'],['result==text']))
        for action in [('eval',),('run','--profile','debug'),('run','--profile','release')]:
            observed=self.cli(*action,'--foreign',host,cwd=directory,timeout=240)
            self.assertEqual(observed['stdout'],'once\n')
        self.assertEqual(self.cli('eval',cwd=directory,ok=False)['code'],'E_FFI_GRANT')
        _,error=self.generate(self.contract('guarded',requires=['echo(text)==text']),'impure-ffi',ok=False)
        self.assertEqual(error['code'],'E_EFFECT')
        self.assertEqual(self.cli('emit','--kind','typescript',cwd=directory,ok=False)['code'],'E_REALM')

    def test_effectful_roots_compose_with_scalar_loop_rules(self):
        self.source('''module loops;
fn work(text:str,n:i64)->str !{io}{var i:i64=0;while i<n{print(i);i=i+1;}return text;}
fn main()->unit !{io}{assert(work("λ🙂",2)=="λ🙂");}
''')
        contract=self.contract('work',['n>=0'],['result==text'])
        rule=contract['functions'][0]['loops'][0];rule['invariants']=['i>=0','i<=n'];rule['decreases']='n-i'
        directory,report=self.value_projection(contract)
        self.assertTrue(report['loop_checks']);self.assertEqual(len(report['functions'][0]['loops']),1)
        self.agreement(directory,stdout='0\n1\n')

    def test_shipped_value_example_pins_and_backends(self):
        shutil.copytree(harness.REPO/'examples/runtime-value-contracts',self.root,dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns('.nex'))
        contract=json.loads((self.root/'contracts.json').read_text())
        self.assertEqual(contract['expected_revision'],self.cli('check')['revision'])
        proof=self.cli('verify','--contracts','contracts.json',ok=False,timeout=90)
        self.assertFalse(proof['ok']);self.assertEqual(proof['functions'][0]['status'],'unsupported')
        directory,_=self.value_projection(contract)
        self.agreement(directory,stdout='NEX🙂\n[1,2,42]\n')
        self.cli('test',cwd=directory,timeout=240)
        self.cli('test','--target','web',cwd=directory,timeout=240)


if __name__=='__main__':unittest.main()
