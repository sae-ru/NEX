"""Observable filtered-handler semantics and genuine retained025 migration."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import sqlite3
import unittest

import support as harness


SOURCE = r'''module filtered_errors;
fn fail()->i64 !{throw}{let held:list<str>=["heap","λ\u0000🙂"];assert(len(held)==2);throw("APP\u0000CODE","λ\u0000🙂");}
fn accepted()->i64 !{throw}{try{return fail();}catch(code,message) if code=="APP\u0000CODE" && len(message)==3 {return 42;}}
fn declined()->i64 {
 try{try{return fail();}catch(code,message) if false && 1/0==0 {assert(false);return 0;}}
 catch(code,message){assert(code=="APP\u0000CODE" && message=="λ\u0000🙂");return 42;}
}
fn total()->i64 {try{return fail();}catch(code,message) if true {return 42;}}
fn replacement()->bool !{throw}{throw("FILTER","replacement");}
fn replaced()->i64 {
 try{try{return fail();}catch(code,message) if replacement() {return 0;}}
 catch(code,message){assert(code=="FILTER" && message=="replacement");return 42;}
}
fn early()->result<i64> !{throw}{
 try{return ok(fail());}catch(code,message) if err<bool>("RESULT","guard")? {return ok(0);}
}
fn predicate(code:str,message:str)->bool !{task}{task_yield();return code=="APP\u0000CODE" && message=="λ\u0000🙂";}
fn suspended()->i64 !{task,throw}{try{return fail();}catch(code,message) if predicate(code,message) {return 42;}}
fn child()->i64 !{task,throw}{task_yield();return fail();}
fn delegated()->i64 !{task}{
 try{
  try{return with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{let future:task<i64>=task_spawn(scope,child);return task_wait(future);});}
  catch(code,message) if predicate(code,message) && code=="OTHER" {assert(false);return 0;}
 }catch(code,message){assert(code=="APP\u0000CODE" && message=="λ\u0000🙂");return 42;}
}
fn rethrown()->i64 !{throw}{try{return fail();}catch(code,message) if true {throw;}}
fn uncaught()->i64 !{throw}{try{return fail();}catch(code,message) if false {return 0;}}
fn main()->unit !{task,throw,io}{assert(accepted()==42);assert(declined()==42);assert(total()==42);assert(replaced()==42);assert(early()==err<i64>("RESULT","guard"));assert(suspended()==42);assert(delegated()==42);print(42);}
test fn accept()->unit !{throw}{assert(accepted()==42);}
test fn decline()->unit{assert(declined()==42);}
test fn total_filter()->unit{assert(total()==42);}
test fn replacement_error()->unit{assert(replaced()==42);}
test fn result_return()->unit !{throw}{assert(early()==err<i64>("RESULT","guard"));}
test fn suspended_filter()->unit !{task,throw}{assert(suspended()==42);}
test fn child_delivery()->unit !{task}{assert(delegated()==42);}
'''


class ExceptionHandlers(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':'main.nex'}), newline="\n")

    def test_sync_task_reference_native_typescript_and_owned_cleanup(self):
        self.source(SOURCE)
        feature=self.cli('describe','--field','source_exceptions')['value']
        self.assertEqual(feature['source_language'],'0.27');self.assertTrue(feature['handler_filters'])
        self.assertTrue(feature['finally']);self.assertTrue(feature['typed_payloads'])
        self.assertEqual(self.cli('eval')['stdout'],'42\n')
        for profile in ('debug','release'):
            native=self.cli('test','--profile',profile,timeout=300)
            self.assertTrue(native['ok']);self.assertEqual(len(native['tests']),7)
        web=self.cli('test','--target','web',timeout=300)
        self.assertTrue(web['ok']);self.assertEqual(len(web['tests']),7)
        profiled=self.cli('profile','--scenario','filtered source errors',timeout=300)
        self.assertEqual(profiled['stdout'],'42\n')
        report=json.loads(Path(profiled['output']).read_text())
        self.assertTrue(report['ok'])
        for pool in report['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])

    def test_rejected_filter_and_rethrow_preserve_original_payload_and_site(self):
        self.source(SOURCE);records=[];web_records=[]
        for entry in ('uncaught','rethrown'):
            reference=self.cli('eval','--entry',entry,ok=False)
            self.assertEqual(reference['code'],'E_SOURCE_EXCEPTION')
            self.assertEqual(reference['source_exception'],{'code':'APP\0CODE','message':'λ\0🙂'})
            native=self.cli('run','--entry',entry,ok=False,timeout=240)
            self.assertEqual(native['exit_code'],70)
            errors=[json.loads(line[len('NEX_SOURCE_EXCEPTION '):]) for line in native['stderr'].splitlines()
                    if line.startswith('NEX_SOURCE_EXCEPTION ')]
            self.assertEqual(len(errors),1,native['stderr']);records.extend(errors)
            self.assertEqual(errors[0]['code'],'APP\0CODE');self.assertEqual(errors[0]['message'],'λ\0🙂')
            folder=self.root/('web-'+entry);self.cli('emit','--kind','typescript','--entry',entry,'--directory',folder)
            driver=folder/'verify-error.ts';driver.write_text('''import { entry } from './program.ts';
import { details } from './nex-source-exception-runtime.ts';
let payload;try{entry();}catch(error){payload=details(error);}
if(!payload)throw new Error('source error missing');
process.stdout.write(JSON.stringify(payload));
''', newline="\n")
            p=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',driver],
                             capture_output=True,text=True,cwd=folder,timeout=60)
            self.assertEqual(p.returncode,0,p.stderr);web_records.append(json.loads(p.stdout))
            self.assertEqual(web_records[-1]['code'],'APP\0CODE');self.assertEqual(web_records[-1]['message'],'λ\0🙂')
        self.assertEqual(records[0]['source']['operation_site'],records[1]['source']['operation_site'])
        self.assertEqual(records[0]['line'],records[1]['line'])
        self.assertEqual(web_records[0],web_records[1])

    def test_filter_runs_once_only_after_an_explicit_source_error(self):
        self.source('''module ordered;
fn code()->str !{io}{print("code");return "APP";}
fn message()->str !{io}{print("message");return "value";}
fn filter(c:str,m:str)->bool !{io}{print("filter");return c=="APP" && m=="value";}
fn handled()->i64 !{io,throw}{try{throw(code(),message());}catch(c,m) if filter(c,m){return 42;}}
fn untouched()->i64 !{io,throw}{try{return 42;}catch(c,m) if filter(c,m){assert(false);return 0;}}
fn main()->unit !{io,throw}{assert(untouched()==42);print(handled());}
test fn order()->unit !{io,throw}{main();}
''')
        expected='code\nmessage\nfilter\n42\n'
        self.assertEqual(self.cli('eval')['stdout'],expected)
        self.assertEqual(self.cli('run',timeout=240)['stdout'],expected)
        self.cli('test','--target','web',timeout=240)
        folder=self.root/'web-order';self.cli('emit','--kind','typescript','--directory',folder)
        driver=folder/'run.ts';driver.write_text("import {entry} from './program.ts';entry();\n", newline="\n")
        p=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',driver],
                         capture_output=True,text=True,cwd=folder,timeout=60)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(p.stdout,expected)

    def test_fatal_guard_does_not_enter_an_enclosing_source_handler(self):
        self.source('''module fatal_guard;
fn fail()->i64 !{throw}{throw("APP","value");}
fn guard()->bool{return 1/0==0;}
fn main()->i64{try{try{return fail();}catch(c,m) if guard(){return 0;}}catch(c,m){return 42;}}
test fn boundary()->unit{assert(main()==42);}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_DIV_ZERO')
        native=self.cli('run',ok=False,timeout=240)
        self.assertEqual(native['exit_code'],70);self.assertIn('E_DIV_ZERO',native['stderr'])
        self.assertNotIn('NEX_SOURCE_EXCEPTION ',native['stderr'])
        self.assertIn('E_DIV_ZERO',json.dumps(self.cli('test','--target','web',ok=False,timeout=240)))

    def test_filter_types_effects_lexical_scope_and_reserved_finally(self):
        cases=[
            ('fn main()->i64{try{throw("A","B");}catch(c,m) if false{return 0;}}','E_EFFECT'),
            ('fn main()->i64 !{throw}{try{throw("A","B");}catch(c,m) if 1{return 0;}}','E_TYPE'),
            ('fn predicate()->bool !{io}{print(1);return true;} fn main()->i64 !{throw}{try{throw("A","B");}catch(c,m) if predicate(){return 0;}}','E_EFFECT'),
            ('fn main()->unit{try{throw("A","B");}catch(c,m){c="changed";}}','E_MUTABILITY'),
            ('fn main()->i64{try{throw("A","B");}catch(c,m) if true{return 0;} return len(c);}','E_UNREACHABLE'),
            ('fn main()->unit !{io}{try{assert(true);}catch(c,m) if true{} print(c);}','E_NAME'),
            ('fn finally()->unit{} fn main()->unit{}','E_PARSE'),
        ]
        for source,code in cases:
            with self.subTest(code=code,source=source):
                self.source('module rejected;'+source)
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_filter_bindings_shadow_outer_values_and_function_names(self):
        self.source('''module shadow;
fn code()->i64{return 7;}
fn main()->i64 !{throw}{
 let code:i64=99;let message:i64=1;var found:i64=0;
 try{throw("APP","λ\\u0000🙂");}
 catch(code,message) if code=="APP" && len(message)==3 {found=42;}
 return code+message+found;
}
test fn values()->unit !{throw}{assert(main()==142);}
''')
        self.assertEqual(self.cli('eval')['value'],142)
        self.assertTrue(self.cli('test',timeout=240)['ok'])
        self.assertTrue(self.cli('test','--target','web',timeout=240)['ok'])

    def test_genuine025_fixture_preserves_rows_schema_and_local_ids(self):
        fixtures=harness.REPO/'tests/fixtures'
        metadata=json.loads((fixtures/'language-0.25-handler-origin.json').read_text())
        sql=(fixtures/'language-0.25-handler-origin.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        self.assertEqual(metadata['producer']['language'],'0.25')
        self.assertFalse(metadata['retagged_source'])
        graph=self.root/'.nex/graph.db';graph.parent.mkdir()
        connection=sqlite3.connect(str(graph));connection.executescript(sql.decode());connection.close()
        self.source(metadata['source'])
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.25','entry':'main.nex'}), newline="\n")
        before=harness.database_rows(graph)
        self.assertEqual({name:len(rows) for name,rows in before[1].items()},metadata['table_counts'])
        plan=self.cli('migrate','--kind','plan')
        self.assertTrue(plan['origin_verified']);self.assertFalse(plan['target_valid'])
        self.assertEqual(plan['origin_revision'],metadata['head'])
        self.assertEqual(harness.database_rows(graph),before)
        candidate=plan['candidate'];candidate['sources']['files']['main.nex']=metadata['source'].replace('finally','finished')
        reviewed=self.root/'reviewed.json';reviewed.write_text(json.dumps(candidate), newline="\n")
        changed=self.cli('migrate','--candidate',reviewed,'--expected-revision',metadata['head'])
        after=harness.database_rows(graph);self.assertEqual(before[0],after[0])
        self.assertEqual(set(before[1]),set(after[1]))
        for name,rows in before[1].items():
            if name!='head':self.assertLessEqual(set(rows),set(after[1][name]),name)
        self.assertEqual(len(before[1]),16);self.assertEqual(len(after[1]['revisions']),3)
        self.assertEqual(self.cli('eval','--revision',changed['revision'])['stdout'],metadata['actual_origin_eval_stdout'])
        self.assertEqual(self.file.read_text(),metadata['source'])
        self.assertEqual(json.loads((self.root/'nex.json').read_text())['language'],'0.25')
        connection=sqlite3.connect(str(graph));self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(),[]);connection.close()

    @unittest.skipUnless(os.environ.get('NEX_GENUINE025_COMPILER'),'set NEX_GENUINE025_COMPILER for actual025 history migration')
    def test_actual025_keyword_origin_reviewed_repair_and_all_history_rows(self):
        origin=Path(os.environ['NEX_GENUINE025_COMPILER']).resolve()
        origin_resources=Path(os.environ['NEX_GENUINE025_RESOURCES']).resolve()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.25','entry':'main.nex'}), newline="\n")
        text='module origin;fn finally()->i64{return 41;}fn main()->unit !{io}{print(finally());}'
        def old_check():
            p=subprocess.run([origin,'check','--json'],cwd=self.root,capture_output=True,text=True,
                             env={**os.environ,'NEX_RESOURCE_DIR':str(origin_resources)},timeout=60)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr);return json.loads(p.stdout)
        self.source(text);old_check();self.source(text.replace('41','42'));head=old_check()['revision']
        graph=self.root/'.nex/graph.db';before=harness.database_rows(graph)
        plan=self.cli('migrate','--kind','plan')
        self.assertTrue(plan['origin_verified']);self.assertFalse(plan['target_valid'])
        self.assertEqual(plan['origin_language'],'0.25');self.assertEqual(plan['target_language'],'0.27')
        self.assertEqual(harness.database_rows(graph),before)
        candidate=plan['candidate'];candidate['sources']['files']['main.nex']=text.replace('41','42').replace('finally','finished')
        path=self.root/'reviewed.json';path.write_text(json.dumps(candidate), newline="\n")
        migrated=self.cli('migrate','--candidate',path,'--expected-revision',head)
        after=harness.database_rows(graph)
        self.assertEqual(before[0],after[0]);self.assertEqual(set(before[1]),set(after[1]))
        for table,rows in before[1].items():
            if table!='head':self.assertLessEqual(set(rows),set(after[1][table]),table)
        self.assertEqual(len(after[1]['revisions']),len(before[1]['revisions'])+1)
        self.assertEqual(self.cli('eval','--revision',head,ok=False)['code'],'E_LANGUAGE_VERSION')
        old=subprocess.run([origin,'eval','--revision',head,'--json'],cwd=self.root,capture_output=True,text=True,
                           env={**os.environ,'NEX_RESOURCE_DIR':str(origin_resources)},timeout=60)
        self.assertEqual(old.returncode,0,old.stdout+old.stderr);self.assertEqual(json.loads(old.stdout)['stdout'],'42\n')
        self.assertEqual(self.cli('eval','--revision',migrated['revision'])['stdout'],'42\n')
        self.assertEqual(json.loads((self.root/'nex.json').read_text())['language'],'0.25')


if __name__=='__main__':unittest.main()
