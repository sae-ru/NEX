"""Synchronous finally foundation; native/task completion remains pending."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import unittest

import support as harness

SOURCE = r'''module finalizers;
fn normal()->str{var trace:str="B";try{trace=trace+"0";}finally{trace=trace+"F";}return trace;}
fn before()->str{var trace:str="original";try{return trace;}finally{trace="changed";}}
fn replace()->str{try{return "discarded";}finally{return "final";}}
fn final_return()->i64{try{let value:i64=0;}finally{return 42;}}
fn nested()->str{var trace:str="";try{try{trace="B";}finally{trace=trace+"1";}}finally{trace=trace+"2";}return trace;}
fn failed()->i64 !{throw}{throw("OLD","λ\u0000🙂");}
fn handled()->i64 !{io}{
 try{try{return failed();}catch(c,m) if true{assert(c=="OLD"&&m=="λ\u0000🙂");return 42;}}
 finally{print("handled-finally");}
}
fn declined()->i64 !{io}{
 try{try{try{return failed();}catch(c,m) if false{return 0;}}finally{print("declined-finally");}}
 catch(c,m){assert(c=="OLD"&&m=="λ\u0000🙂");return 42;}
}
fn replaced()->i64{
 try{try{return failed();}finally{throw("NEW","finalizer");}}
 catch(c,m){assert(c=="NEW"&&m=="finalizer");return 42;}
}
fn propagated()->result<i64> !{io}{try{let value:i64=err<i64>("RESULT","body")?;return ok(value);}finally{print("result-finally");}}
fn override_result()->result<i64>{try{return ok(0);}finally{let value:i64=err<i64>("RESULT","finalizer")?;return ok(value);}}
fn lexical()->i64 !{throw}{
 try{throw("OUTER","original");}catch(c,m){
  try{try{throw("INNER","discarded");}catch(c,m){return 0;}}finally{throw;}
 }
}
fn lexical_caught()->i64{try{return lexical();}catch(c,m){assert(c=="OUTER"&&m=="original");return 42;}}
fn main()->unit !{io}{
 assert(normal()=="B0F");assert(before()=="original");assert(replace()=="final");assert(final_return()==42);
 assert(nested()=="B12");assert(handled()==42);assert(declined()==42);assert(replaced()==42);
 assert(propagated()==err<i64>("RESULT","body"));assert(override_result()==err<i64>("RESULT","finalizer"));
 assert(lexical_caught()==42);print(42);
}
test fn ordinary()->unit{assert(normal()=="B0F"&&nested()=="B12");}
test fn returns()->unit{assert(before()=="original"&&replace()=="final"&&final_return()==42);}
test fn catches()->unit !{io}{assert(handled()==42&&declined()==42&&replaced()==42);}
test fn results()->unit !{io}{assert(propagated()==err<i64>("RESULT","body"));assert(override_result()==err<i64>("RESULT","finalizer"));}
test fn lexical_rethrow()->unit{assert(lexical_caught()==42);}
'''


class FinallyFoundation(harness.ToolchainCase):
    def web(self, entry, driver):
        folder=self.root/('web-'+entry)
        self.cli('emit','--kind','typescript','--entry',entry,'--directory',folder)
        path=folder/'observe.ts';path.write_text(driver)
        result=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',path],
                              cwd=folder,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stderr)
        return result.stdout

    def test_normal_returns_result_propagation_and_error_replacement(self):
        self.source(SOURCE)
        feature=self.cli('describe','--field','source_exceptions')['value']
        self.assertFalse(feature['finally'])
        self.assertEqual(feature['finally_development'],json.loads((harness.REPO/'llm/language-pack.json').read_text())['source_exceptions']['finally_development'])
        expected='handled-finally\ndeclined-finally\nresult-finally\n42\n'
        self.assertEqual(self.cli('eval')['stdout'],expected)
        observed=self.web('main',"import { entry } from './program.ts';entry();\n")
        self.assertEqual(observed,expected)
        tests=self.cli('test','--target','web',timeout=240)
        self.assertTrue(tests['ok']);self.assertEqual(len(tests['tests']),5)
        operations=self.cli('operations','--symbol','normal','--limit','1000')
        self.assertTrue(any(node['kind']=='statement.finally' for node in operations['nodes']))

    def test_original_source_error_and_site_survive_finalization(self):
        self.source(r'''module original;
fn fail()->unit !{throw}{throw("ORIGINAL","λ\u0000🙂");}
fn plain()->unit !{throw}{fail();}
fn finalized()->unit !{throw}{try{fail();}finally{assert(true);}}
fn main()->unit{}
''')
        records=[]
        for entry in ('plain','finalized'):
            value=self.cli('eval','--entry',entry,ok=False)
            self.assertEqual(value['code'],'E_SOURCE_EXCEPTION')
            self.assertEqual(value['source_exception'],{'code':'ORIGINAL','message':'λ\0🙂'})
            text=self.web(entry,"import { entry } from './program.ts';import { details } from './nex-source-exception-runtime.ts';\nlet value;try{entry();}catch(error){value=details(error);}if(!value)throw Error('missing source error');process.stdout.write(JSON.stringify(value));\n")
            records.append(json.loads(text))
        self.assertEqual(records[0],records[1])

    def test_fatal_traps_skip_user_finalizers(self):
        self.source('module fatal;fn main()->unit{try{let zero:i64=0;let value:i64=1/zero;}finally{assert(false);}}')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_DIV_ZERO')
        output=self.web('main',"import { entry } from './program.ts';let code;try{entry();}catch(error){code=(error as {code:string}).code;}process.stdout.write(JSON.stringify({code}));\n")
        self.assertEqual(json.loads(output),{'code':'E_DIV_ZERO'})

    def test_scope_effects_types_and_pending_engines_are_explicit(self):
        cases=[
            ('fn main()->unit{try{let inner:i64=1;}finally{assert(inner==1);}}','E_NAME'),
            ('fn main()->unit{try{throw("A","B");}catch(c,m){}finally{assert(c=="A");}}','E_NAME'),
            ('fn main()->i64{try{return 1;}finally{return "wrong";}}','E_TYPE'),
            ('fn main()->unit{try{}finally{throw("A","B");}}','E_EFFECT'),
            ('fn main()->unit !{task}{try{task_yield();}finally{}}','E_FINALLY_TASK'),
            ('fn helper()->i64{try{return 1;}finally{}}fn main()->unit !{task}{task_yield();let x:i64=helper();}','E_FINALLY_TASK'),
            ('fn main()->unit{try{}}','E_PARSE'),
            ('fn main()->unit{try{}finally{}finally{}}','E_PARSE'),
        ]
        for source,code in cases:
            with self.subTest(source=source):
                self.source('module rejected;'+source)
                self.assertEqual(self.cli('check',ok=False)['code'],code)
        self.source('module pending;fn main()->i64{try{return 42;}finally{}}')
        self.assertEqual(self.cli('build',ok=False)['code'],'E_FINALLY_BACKEND')

    def test_actual_prefinally026_graph_and_canonical_identities_are_unchanged(self):
        fixture=harness.REPO/'tests/fixtures/language-0.26-finally-origin'
        metadata=json.loads(Path(str(fixture)+'.json').read_text())
        sql=Path(str(fixture)+'.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        self.assertEqual(metadata['producer']['toolchain'],'0.137.1')
        self.assertFalse(metadata['retagged_source'])
        self.source(metadata['source']);graph=self.root/'.nex/graph.db';graph.parent.mkdir(exist_ok=True)
        with sqlite3.connect(str(graph)) as db:db.executescript(sql.decode())
        before=harness.database_rows(graph)
        self.assertEqual({k:len(v) for k,v in before[1].items()},metadata['table_counts'])
        self.assertEqual(self.cli('eval','--revision',metadata['revision'])['value'],42)
        self.assertEqual(harness.database_rows(graph),before)
        fresh=self.root/'fresh';fresh.mkdir()
        (fresh/'main.nex').write_text(metadata['source'])
        (fresh/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'}))
        self.assertEqual(self.cli('check',cwd=fresh)['revision'],metadata['revision'])


if __name__=='__main__':unittest.main()
