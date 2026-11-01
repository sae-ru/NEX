"""Parametric runtime contracts cover present and future source instantiations."""
import copy
import json
from pathlib import Path
import unittest
import runtime_contracts as common
import support as harness


class RuntimeGenericContracts(harness.ToolchainCase):
    contract=common.RuntimeContracts.contract
    generate=common.RuntimeContracts.generate
    web=common.RuntimeContracts.web
    agreement=common.RuntimeContracts.agreement

    def generic_projection(self,contract,name='guarded'):
        directory,session=self.generate(contract,name)
        self.assertEqual(session['schema'],'nex.runtime-contract-session/4')
        self.assertEqual(session['generic_root_scope'],'source_template_all_instantiations')
        self.assertEqual(session['predicate_scope'],'pure_source_expressions')
        receipt=json.loads(Path(session['receipt']).read_text())
        self.assertEqual(receipt['schema'],'nex.runtime-contract-candidate/4')
        self.assertEqual(receipt['functions'],session['functions'])
        self.assertTrue(any(f['type_parameters'] for f in session['functions']))
        self.assertFalse(session['proof_performed'])
        return directory,session

    def test_imported_template_annotations_all_instances_and_preserved_history(self):
        self.source('''module application;
import "./library.nex" as guards;
fn main()->unit !{io}{
 assert(guards::identity<i64>(42)==42);
 assert(guards::identity("λ🙂")=="λ🙂");
 assert(guards::identity([1,2])==[1,2]);
}
''')
        (self.root/'library.nex').write_text('''module library;
fn same<T>(left:T,right:T)->bool{return left==right;}
pub fn identity<T>(value:T)->(T) !{io}{print("body");return value;}
''',newline='\n')
        feature=self.cli('describe','--field','runtime_contracts')['value']
        self.assertEqual(feature,json.loads((harness.REPO/'llm/language-pack.json').read_text())['runtime_contracts'])
        self.assertTrue(feature['generic_roots']);self.assertFalse(feature['concrete_instance_roots'])
        contract=self.contract('library::identity',['same<T>(value,value)'],
            ['same<T>(result,value)','(fn(item:T)->T{return item;})(result)==value'])
        original=(self.root/'library.nex').read_bytes()
        state=harness.database_rows(self.root/'.nex/graph.db')
        directory,session=self.generic_projection(contract)
        self.assertEqual((self.root/'library.nex').read_bytes(),original)
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),state)
        parameter=session['functions'][0]['type_parameters'][0]
        self.assertTrue(parameter['name'].endswith('::T'));self.assertEqual(parameter['arity'],0)
        self.assertEqual(parameter['bounds'],[])
        projected=(directory/'library.nex').read_text()
        self.assertIn('->(T) !{io}',projected)
        self.assertEqual(projected.count('pub fn identity<T>'),1)
        _,again=self.generic_projection(contract,'same-candidate')
        self.assertEqual(again['revision'],session['revision'])
        self.agreement(directory,stdout='body\nbody\nbody\n')

    def test_phantom_parameters_and_builtin_bounds_are_carried_explicitly(self):
        self.source('''module phantom;
fn permitted<T:wire>()->bool{return true;}
fn count<T:wire>()->i64{return 7;}
fn maximum<T:add+ordered>(left:T,right:T)->T{if left<right{return right;}return left;}
fn combine<T:add>(left:T,right:T)->T{return left+right;}
fn main()->unit{
 assert(count<i64>()==7 && count<str>()==7);
 assert(maximum<i64>(4,8)==8);
 assert(maximum<f64>(1.25,2.5)==2.5);
 assert(combine<str>("a","b")=="ab");
}
''')
        contract=self.contract('count',['permitted<T>()'],['result==7'])
        contract['functions']+=self.contract('maximum',ensures=['result>=left && result>=right'])['functions']
        contract['functions']+=self.contract('combine',ensures=['result==left+right'])['functions']
        directory,session=self.generic_projection(contract)
        found={f['symbol'].split('::')[-1]:f['type_parameters'] for f in session['functions']}
        self.assertEqual(found['count'][0]['bounds'],['wire'])
        self.assertEqual(set(found['maximum'][0]['bounds']),{'add','ordered'})
        self.agreement(directory)

    def test_trait_projection_and_constructor_parameters_keep_their_kinds(self):
        self.source('''module kinds;
trait Content{type Item;fn get(value:Self)->Content::Item<Self>;}
struct Box<T>{value:T;}
fn extract<T>(value:Box<T>)->T{return value.value;}
impl boxed<T>:Content for Box<T>{type Item=T;get=extract<T>;}
fn read<T:Content>(value:T)->Content::Item<T>{return Content<T>::get(value);}
fn identity<F<_>,T>(value:F<T>)->F<T>{return value;}
fn main()->unit{
 assert(read(Box<str>("🙂"))=="🙂");
 assert(read(Box<i64>(42))==42);
 assert(identity<list,i64>([1,2])==[1,2]);
 assert(identity<Box,str>(Box<str>("owned"))==Box<str>("owned"));
}
''')
        contract=self.contract('read',ensures=['result==Content<T>::get(value)'])
        contract['functions']+=self.contract('identity',ensures=['result==value'])['functions']
        directory,session=self.generic_projection(contract)
        kinds={f['symbol'].split('::')[-1]:f['type_parameters'] for f in session['functions']}
        self.assertEqual([p['arity'] for p in kinds['identity']],[1,0])
        self.assertTrue(kinds['read'][0]['bounds'][0].endswith('::Content'))
        self.agreement(directory)

    def test_new_instantiations_inherit_preconditions_before_body_effects(self):
        self.source('''module future;
pub fn identity<T>(value:T)->T !{io}{print("body");return value;}
fn main()->unit !{io}{assert(identity<i64>(42)==42);}
''')
        directory,_=self.generic_projection(self.contract('identity',['str(value)!="blocked"'],['result==value']))
        # This str specialization did not exist in the input program. It must
        # receive the template's checks when an ordinary later edit adds it.
        path=directory/'main.nex';source=path.read_text()
        self.assertIn('identity<i64>(42)',source)
        path.write_text(source.replace('identity<i64>(42)==42','identity<str>("blocked")=="blocked"'),newline='\n')
        self.agreement(directory,failure='E_ASSERT')

    def test_scalar_loop_rules_and_mixed_concrete_roots_keep_receipt_coverage(self):
        self.source('''module mixed;
fn repeat<T>(value:T,n:i64)->list<T>{
 var i:i64=0;var output:list<T>=[];
 while i<n{output=output+[value];i=i+1;}
 return output;
}
fn marker()->i64{return 0;}
fn main()->unit{assert(repeat<str>("🙂",3)==["🙂","🙂","🙂"]);assert(marker()==0);}
''')
        contract=self.contract('repeat',['n>=0 && n<5'],['len(result)==n'])
        loop=contract['functions'][0]['loops'][0];loop.update(invariants=['i>=0','i<=n'],decreases='n-i')
        contract['functions']+=self.contract('marker',ensures=['result==0'])['functions']
        directory,session=self.generic_projection(contract)
        self.assertTrue(session['loop_checks'])
        by_name={f['symbol'].split('::')[-1]:f for f in session['functions']}
        self.assertEqual(by_name['marker']['type_parameters'],[])
        self.assertEqual(len(by_name['repeat']['loops']),1)
        self.agreement(directory)

    def test_generic_normal_finally_result_and_post_trap_owned_cleanup(self):
        self.source('''module finalizer;
fn choose<T>(before:T,after:T)->T !{io}{
 try{return before;}finally{print("finally");return after;}
}
fn main()->unit !{io}{assert(choose<list<str>>(["before"],["after🙂"])==["after🙂"]);}
''')
        contract=self.contract('choose',ensures=['result==after','before!=after'])
        directory,_=self.generic_projection(contract)
        self.agreement(directory,stdout='finally\n')
        trapped=copy.deepcopy(contract);trapped['functions'][0]['ensures']=['false']
        directory,_=self.generic_projection(trapped,'post-trap')
        self.agreement(directory,failure='E_ASSERT',stdout='finally\n')
        profile=self.cli('profile','--scenario','generic-contract-post-trap',cwd=directory,ok=False,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_generic_typed_errors_run_finally_and_skip_postconditions(self):
        self.source('''module typed_generic;
fn fail<T:wire>(value:T)->T !{io,throw}{try{throw(value);}finally{print("finally");}}
fn main()->unit !{io,throw}{
 try{let ignored:str=fail<str>("λ🙂");}catch(error:str){assert(error=="λ🙂");print("str");}
 try{let ignored:list<str>=fail<list<str>>(["owned🙂"]);}catch(error:list<str>){assert(error==["owned🙂"]);print("list");}
}
''')
        directory,_=self.generic_projection(self.contract('fail',ensures=['false']))
        self.agreement(directory,stdout='finally\nstr\nfinally\nlist\n')
        profile=self.cli('profile','--scenario','generic-typed-errors',cwd=directory,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_file_instantiation_preserves_alias_authority_and_fatal_cleanup(self):
        self.source('''module generic_files;
server fn identity<T>(owner:T)->T{return owner;}
server fn main()->unit !{fs}{
 let owner:file=unwrap(file_open_read("input"));
 let alias:file=identity<file>(owner);
 assert(file_close(alias));assert(!file_close(owner));
}
''')
        contract=self.contract('identity',ensures=['result==owner'])
        directory,_=self.generic_projection(contract)
        data=self.root/'data';data.mkdir();(data/'input').write_text('owned🙂',newline='\n')
        environment={'NEX_FILES_ROOT':str(data)}
        self.cli('eval',env=environment,cwd=directory)
        for profile in ('debug','release'):
            native=self.cli('run','--profile',profile,env=environment,cwd=directory,timeout=240)
            self.assertEqual(native['stderr'],'')
        self.assertEqual(self.cli('emit','--kind','typescript',cwd=directory,ok=False)['code'],'E_REALM')
        trapped=copy.deepcopy(contract);trapped['functions'][0]['ensures']=['false']
        trapped_directory,_=self.generic_projection(trapped,'file-post-trap')
        self.assertEqual(self.cli('eval',env=environment,cwd=trapped_directory,ok=False)['code'],'E_ASSERT')
        for profile in ('debug','release'):
            native=self.cli('run','--profile',profile,env=environment,cwd=trapped_directory,ok=False,timeout=240)
            self.assertIn('E_ASSERT',native['stderr'])
        for candidate,ok in [(directory,True),(trapped_directory,False)]:
            profile=self.cli('profile','--scenario','generic-file-owners',env=environment,cwd=candidate,ok=ok,timeout=300)
            for pool in json.loads(Path(profile['output']).read_text())['memory']:
                self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_predicates_are_parametric_and_pure_even_for_unused_templates(self):
        self.source('''module rejected;
fn impure()->bool !{io}{print("forbidden");return true;}
fn identity<T>(value:T)->T !{io}{return value;}
fn unused<T>(value:T)->T{return value;}
fn main()->unit !{io}{assert(identity<i64>(42)==42);}
''')
        for name,symbol,requires,code in [('unbound-add','identity',['value+value==value'],'E_TYPE'),
                                     ('unused-unbound-add','unused',['value+value==value'],'E_TYPE'),
                                     ('root-effects','identity',['false && impure()'],'E_EFFECT')]:
            with self.subTest(name=name):
                _,failure=self.generate(self.contract(symbol,requires),name,ok=False)
                self.assertEqual(failure['code'],code)
                self.assertIn('requires',failure['message'])
        _,failure=self.generate(self.contract('rejected::identity<i64>'), 'derived-root',ok=False)
        self.assertEqual(failure['code'],'E_CONTRACT_RUNTIME')
        self.assertIn('source generic template',failure['message'])


if __name__=='__main__':
    unittest.main(verbosity=2)
