"""Runtime invariant/ranking semantics over actual projected NEX programs."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import unittest
import support as harness
import runtime_contracts as contract_harness


class RuntimeLoopContracts(harness.ToolchainCase):
    contract=contract_harness.RuntimeContracts.contract
    web=contract_harness.RuntimeContracts.web
    agreement=contract_harness.RuntimeContracts.agreement

    def rules(self,symbol,rules,requires=(),ensures=('true',)):
        contract=self.contract(symbol,requires,ensures)
        annotations=contract['functions'][0]['loops']
        self.assertEqual(len(annotations),len(rules))
        for annotation,(invariants,decreases) in zip(annotations,rules):
            annotation.update(invariants=list(invariants),decreases=decreases)
        return contract

    def generate(self,contract,name='guarded',ok=True):
        path=self.root/(name+'.json');path.write_text(json.dumps(contract,ensure_ascii=False))
        directory=self.root/name
        report=self.cli('contract','--kind','runtime','--contracts',path,'--directory',directory,ok=ok,timeout=120)
        if not ok:
            self.assertFalse(directory.exists());return directory,report
        self.assertTrue(report['loop_checks']);self.assertFalse(report['proof_performed'])
        self.assertEqual(report['schema'],'nex.runtime-contract-session/2')
        self.assertEqual(self.cli('check',cwd=directory)['revision'],report['revision'])
        receipt=json.loads(Path(report['receipt']).read_text())
        self.assertEqual(receipt['schema'],'nex.runtime-contract-candidate/2')
        self.assertEqual(receipt['contracts'],contract)
        for function in report['functions']:
            for loop in function['loops']:
                self.assertTrue(loop['decreases']);self.assertGreater(loop['invariants'],0)
                self.assertEqual(len(loop['head_helper_content_hash']),64)
        return directory,report

    def test_counted_loop_discovery_history_receipt_and_source_relocation(self):
        self.source('''module looped;
fn double(n:i64)->i64{var i:i64=0;var total:i64=0;while i<n{total=total+2;i=i+1;}return total;}
fn main()->i64{return double(4);}
test fn values()->unit{assert(double(0)==0);assert(double(4)==8);}
''')
        feature=self.cli('describe','--field','runtime_contracts')['value']
        self.assertEqual(feature,json.loads((harness.REPO/'llm/language-pack.json').read_text())['runtime_contracts'])
        self.assertTrue(feature['loop_checks']);self.assertFalse(feature['unannotated_loops_instrumented'])
        contract=self.rules('double',[(['i>=0','i<=n','total==i*2'],'n-i')],['n>=0','n<10'],['result==n*2'])
        before=self.file.read_bytes();state=harness.database_rows(self.root/'.nex/graph.db')
        directory,report=self.generate(contract)
        self.assertEqual(self.file.read_bytes(),before);self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),state)
        self.assertEqual(len(report['functions'][0]['loops']),1)
        _,again=self.generate(contract,'repeated');self.assertEqual(again['revision'],report['revision']);self.assertEqual(again['source_hash'],report['source_hash'])
        self.cli('test',cwd=directory,timeout=240);self.cli('test','--target','web',cwd=directory,timeout=240)
        self.file.unlink();shutil.move(str(directory),str(self.root/'relocated'))
        self.agreement(self.root/'relocated',value=8)

    def test_invariant_entry_even_when_condition_false_and_fatal_cleanup(self):
        self.source('''module initial;
fn guarded()->i64{var i:i64=1;let owned:list<str>=["λ🙂"];while i<0{return 9;}return i;}
fn main()->unit !{io}{let owned:list<str>=["outer"];print("before");try{guarded();}catch(c,m){print("caught");}finally{print("finalized");}}
''')
        directory,_=self.generate(self.rules('guarded',[(['i==0'],'1/0')]))
        self.agreement(directory,failure='E_ASSERT',stdout='before\n')
        profile=self.cli('profile','--scenario','loop-entry-trap',cwd=directory,ok=False,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_final_back_edge_checks_invariant_and_strict_descent_before_exit(self):
        self.source('''module edge;
fn run()->i64{var i:i64=0;while i<1{i=i+1;}return i;}
fn main()->i64{return run();}
''')
        for name,invariants,rank in [('invariant',['i==0'],'1-i'),('ranking',['true'],'1')]:
            with self.subTest(name=name):
                directory,_=self.generate(self.rules('run',[(invariants,rank)]),name)
                self.agreement(directory,failure='E_ASSERT')

    def test_rank_initial_false_nonnegative_checked_and_negative_final_value(self):
        self.source('''module rank;
fn run(n:i64)->i64{var i:i64=0;while i<n{i=i+1;}return i;}
fn zero()->i64{return run(0);}
fn main()->i64{return run(1);}
''')
        contract=self.rules('run',[(['true'],'1/0')]);directory,_=self.generate(contract)
        self.agreement(directory,entry='zero',value=0);self.agreement(directory,failure='E_DIV_ZERO')
        directory,_=self.generate(self.rules('run',[(['true'],'-1')]),'negative')
        self.agreement(directory,failure='E_ASSERT')
        directory,_=self.generate(self.rules('run',[(['true'],'0-i')]),'negative-final')
        self.agreement(directory,value=1)
        self.source('module overflow; fn run()->i64{var i:i64=0;while i==0{i=i-1;}return i;} fn main()->unit{run();}\n')
        directory,_=self.generate(self.rules('run',[(['true'],'9223372036854775807-i')]),'overflow')
        self.agreement(directory,failure='E_OVERFLOW')

    def test_early_return_and_finally_return_do_not_create_back_edges(self):
        self.source('''module early;
fn run()->i64{var i:i64=0;while i<1{try{return 3;}finally{return 7;}}return 0;}
fn main()->i64{return run();}
''')
        directory,_=self.generate(self.rules('run',[(['i==0'],'1')],ensures=['result==7']))
        self.agreement(directory,value=7)

    def test_nested_loops_and_shadowed_bindings(self):
        self.source('''module nesting;
fn run(n:i64)->i64{
 var i:i64=0;var total:i64=0;
 while i<n{var j:i64=0;while j<2{let i:bool=true;assert(i);total=total+1;j=j+1;}
 if true{var i:i64=4;while i>0{i=i-1;}assert(i==0);}i=i+1;}
 return total;
}
fn main()->i64{return run(3);}
''')
        contract=self.rules('run',[(['i>=0','i<=n'],'n-i'),(['j>=0','j<=2'],'2-j'),(['i>=0','i<=4'],'i')])
        directory,_=self.generate(contract);self.agreement(directory,value=6)

    def test_match_typed_catch_and_finalizer_lexical_scopes(self):
        self.source('''module scopes;
enum Box{Value(value:i64);}
fn run(n:i64)->i64{var total:i64=0;
 match Box::Value(n){Box::Value(limit)=>{var i:i64=0;while i<limit{i=i+1;total=total+1;}}}
 try{throw(n);}catch(limit:i64){var i:i64=0;while i<limit{i=i+1;total=total+1;}}
 finally{var j:i64=1;while j>0{j=j-1;total=total+1;}}
 return total;}
fn main()->i64{return run(3);}
''')
        contract=self.rules('run',[(['i>=0','i<=limit'],'limit-i'),(['i>=0','i<=limit'],'limit-i'),(['j>=0','j<=1'],'j')])
        directory,_=self.generate(contract);self.agreement(directory,value=7)

    def test_source_error_escape_and_finalizer_mutations(self):
        self.source('''module outcomes;
fn escaped()->i64{var i:i64=0;try{while i<1{throw(1);}}catch(e:i64){return 7;}return 0;}
fn finalized()->i64{var i:i64=0;while i<2{try{throw(1);}catch(e:i64){}finally{i=i+1;}}return i;}
fn main()->i64{return escaped()+finalized();}
''')
        contract=self.rules('escaped',[(['i==0'],'1')]);contract['functions']+=self.rules('finalized',[(['i>=0','i<=2'],'2-i')])['functions']
        directory,_=self.generate(contract);self.agreement(directory,value=9)

    def test_invalid_rules_are_rejected_without_output_or_graph_change(self):
        self.source('''module invalid;
fn run(n:i64)->i64{var i:i64=0;let label:str="x";while i<n{let inside:i64=4;i=i+1;}return i;}
''')
        original=self.rules('run',[(['i>=0'],'n-i')]);state=harness.database_rows(self.root/'.nex/graph.db')
        for index,change in enumerate([{'invariants':[]},{'decreases':''},{'decreases':'true'},{'decreases':'len(label)'},{'invariants':['inside==0']},{'invariants':['result==0']},{'invariants':['label==label']},{'invariants':['run==run']},{'invariants':['true || run==run']},{'invariants':['i']},{'line':999},{'column':999}]):
            contract=copy.deepcopy(original);contract['functions'][0]['loops'][0].update(change)
            _,report=self.generate(contract,'invalid'+str(index),ok=False)
            self.assertIn(report['code'],['E_CONTRACT_RUNTIME','E_CONTRACT_EXPRESSION','E_CONTRACT_STALE'])
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),state)

    def test_comments_parentheses_unicode_and_short_circuit(self):
        self.source('''module lexical;
fn run(n:i64)->i64{var i:i64=0;
 while (i<n // } {
 ) {let text:str="λ🙂 } {";assert(len(text)==6);i=i+1;}return i;}
fn main()->i64{return run(3);}
''')
        contract=self.rules('run',[(['true || 1/0==0 // trailing','i>=0 && i<=n'],'n-i // trailing')])
        directory,_=self.generate(contract);self.agreement(directory,value=3)

    def test_partial_annotation_and_mixed_pre_post_roots_remain_explicit(self):
        self.source('''module selected;
fn identity(x:i64)->i64{return x;}
fn run()->i64{var i:i64=0;while i<2{i=i+1;}while i<3{i=i+1;}return identity(i);}
fn main()->i64{return run();}
''')
        contract=self.rules('run',[(['i>=0','i<=2'],'2-i'),(['true'],'1')])
        contract['functions'][0]['loops'].pop();contract['functions']+=self.contract('identity',ensures=['result==x'])['functions']
        directory,report=self.generate(contract)
        rows={r['symbol']:r['loops'] for r in report['functions']}
        self.assertEqual(sorted(map(len,rows.values())),[0,1]);self.agreement(directory,value=3)

    def test_fresh_helper_names_and_no_added_closure_allocations(self):
        source='module collision; fn run()->i64{var i:i64=0;while i<50{i=i+1;}return i;} fn main()->unit{assert(run()==50);}\n'
        self.source(source)
        _,first=self.generate(self.rules('run',[(['i>=0','i<=50'],'50-i')]),'first')
        helper=first['functions'][0]['loops'][0]['head_helper_symbol'].split('::')[-1]
        self.source(source+'fn '+helper+'()->i64{return 99;}\n')
        directory,second=self.generate(self.rules('run',[(['i>=0','i<=50'],'50-i')]),'collision')
        self.assertNotEqual(first['functions'][0]['loops'][0]['head_helper_symbol'],second['functions'][0]['loops'][0]['head_helper_symbol'])
        self.agreement(directory)
        profile=self.cli('profile','--scenario','loop-contract-allocations',cwd=directory,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['allocations'],0);self.assertEqual(pool['live'],0)



    def test_unprojected_pure_typed_catch_finally_and_genuine_escape(self):
        self.source("""module ordinary;
fn total(n:i64)->i64{var i:i64=0;let owned:list<str>=["λ🙂"];
 try{throw(n);}catch(e:i64){i=e+len(owned);}finally{i=i+2;}return i;}
fn escaped()->unit !{io,throw}{try{throw(3);}finally{print("leave");}}
fn main()->unit !{io}{assert(total(3)==6);try{escaped();}catch(v:i64){assert(v==3);print("caught");}catch(c,m){assert(false);}}
""")
        self.agreement(self.root,stdout='leave\ncaught\n')
        profile=self.cli('profile','--scenario','pure-typed-finally',timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_shipped_loop_example_proof_projection_and_backends(self):
        shutil.copytree(harness.REPO/'examples/runtime-loop-contracts',self.root,dirs_exist_ok=True)
        contract=json.loads((self.root/'contracts.json').read_text())
        self.assertEqual(contract['expected_revision'],self.cli('check')['revision'])
        self.assertTrue(self.cli('verify','--contracts','contracts.json',timeout=90)['ok'])
        directory,_=self.generate(contract)
        self.agreement(directory,stdout='10\n')
        self.cli('test',cwd=directory,timeout=240);self.cli('test','--target','web',cwd=directory,timeout=240)

    def test_loop_contracts_in_joined_tasks_and_fatal_child_cleanup(self):
        self.source("""module child;
fn run()->i64{var i:i64=0;while i<2{i=i+1;}return i;}
fn main()->unit !{task,throw,io}{print("before");with_tasks(2,fn(scope:task_scope)->unit !{task,throw}{
 let child:task<i64>=task_spawn(scope,fn()->i64{return run();});assert(task_wait(child)==2);});}
""")
        directory,_=self.generate(self.rules('run',[(['i>=0','i<=2'],'2-i')]))
        self.agreement(directory,stdout='before\n')
        directory,_=self.generate(self.rules('run',[(['i==0'],'2-i')]),'fatal-child')
        self.agreement(directory,failure='E_ASSERT',stdout='before\n')
        profile=self.cli('profile','--scenario','loop-child-fatal',cwd=directory,ok=False,timeout=300)
        for pool in json.loads(Path(profile['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])


if __name__=='__main__':unittest.main()
