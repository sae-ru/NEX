"""Synchronous finally agreement and ownership; task completion remains pending."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
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
fn alias_return(value:list<str>)->list<str>{try{return value;}finally{let discarded:list<str>=["temporary"];assert(len(discarded)==1);}}
fn nested_return()->str{try{try{return "pending";}finally{assert(true);}}finally{return "outer";}}
fn suppressed()->i64 !{throw}{try{throw("DISCARDED","source error");}finally{return 42;}}
fn shadow()->i64{var current:i64=40;try{let current:i64=0;return current+1;}finally{current=current+2;assert(current==42);}}
fn catch_alias()->str !{throw}{
 try{throw("OUTER","original");}catch(c,m){
  try{try{throw("INNER","kept");}catch(c,m){return m;}}finally{assert(c=="OUTER"&&m=="original");}
 }
}
fn main()->unit !{io}{
 assert(normal()=="B0F");assert(before()=="original");assert(replace()=="final");assert(final_return()==42);
 assert(nested()=="B12");assert(handled()==42);assert(declined()==42);assert(replaced()==42);
 assert(propagated()==err<i64>("RESULT","body"));assert(override_result()==err<i64>("RESULT","finalizer"));
 assert(lexical_caught()==42);assert(alias_return(["λ\u0000🙂"])==["λ\u0000🙂"]);
 assert(nested_return()=="outer");assert(shadow()==1);
 try{assert(suppressed()==42);assert(catch_alias()=="kept");}catch(c,m){assert(false);}
 print(42);
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
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile,timeout=240)['stdout'],expected)
            tested=self.cli('test','--profile',profile,timeout=300)
            self.assertTrue(tested['ok']);self.assertEqual(len(tested['tests']),5)
        profiled=self.cli('profile','--scenario','synchronous finally',timeout=300)
        self.assertEqual(profiled['stdout'],expected)
        for pool in json.loads(Path(profiled['output']).read_text())['memory']:
            self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])
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
            native=self.cli('run','--entry',entry,ok=False,timeout=240)
            payload=[json.loads(line.split(' ',1)[1]) for line in native['stderr'].splitlines() if line.startswith('NEX_SOURCE_EXCEPTION ')]
            self.assertEqual(len(payload),1);self.assertEqual(payload[0]['code'],'ORIGINAL')
            self.assertEqual(payload[0]['message'],'λ\0🙂')
            if entry=='plain':original_native=payload[0]
            else:
                self.assertEqual(payload[0]['source']['operation_site'],original_native['source']['operation_site'])
                self.assertEqual(payload[0]['line'],original_native['line'])
        self.assertEqual(records[0],records[1])

    def test_fatal_traps_skip_user_finalizers(self):
        self.source('module fatal;fn main()->unit{try{let zero:i64=0;let value:i64=1/zero;}finally{assert(false);}}')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_DIV_ZERO')
        native=self.cli('run',ok=False,timeout=240)
        self.assertEqual(native['exit_code'],70);self.assertIn('E_DIV_ZERO',native['stderr']);self.assertNotIn('E_ASSERT',native['stderr'])
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
        self.source('module available;fn value()->i64{try{return 42;}finally{}}fn main()->unit !{io}{print(value());}')
        self.assertEqual(self.cli('run',timeout=240)['stdout'],'42\n')
        self.assertEqual(self.cli('build','--target','wasm','--entry','value',ok=False)['code'],'E_WASM_TYPE')

    def test_nested_return_expansion_has_a_checked_bound(self):
        body='return 1;'
        for _ in range(14):body='try{'+body+'}finally{if flag{return 2;}}'
        self.source('module bounded;fn compute(flag:bool)->i64{'+body+'}fn main()->unit{assert(compute(false)==1);}')
        self.assertEqual(self.cli('build',ok=False,timeout=120)['code'],'E_FINALLY_LIMIT')

    @unittest.skipUnless(platform.system() in ('Darwin','Linux'),'actual native LLDB scope check')
    def test_native_finally_return_uses_outer_lexical_debug_scope(self):
        debugger=os.environ.get('NEX_LLDB') or shutil.which('lldb')
        if not debugger:self.skipTest('LLDB is not available')
        self.source('''module finally_debug;
fn main()->unit !{io}{
 var value:i64=40;
 try{
  let value:i64=0;
  return;
 }finally{
  value=value+2;
  print(value);
 }
}
''')
        built=self.cli('build','--profile','debug',timeout=240)
        manifest=json.loads(Path(built['debug_manifest']).read_text());paths=[]
        def collect(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key=='debug_path':paths.append(item)
                    elif isinstance(item,(dict,list)):collect(item)
            elif isinstance(value,list):
                for item in value:collect(item)
        collect(manifest['sources']);self.assertEqual(len(set(paths)),1)
        argv=[debugger,'--no-lldbinit','--batch',built['executable'],
              '-o','settings set target.disable-aslr false',
              '-o','command script import '+json.dumps(manifest['formatter']),
              '-o','nex-load-debug '+json.dumps(built['debug_manifest'])+' --compiler '+json.dumps(harness.NEX),
              '-o','breakpoint set --file '+json.dumps(paths[0])+' --line 9',
              '-o','run','-o','frame variable value','-o','expr value',
              '-o','nex-frame value','-o','nex-eval value','-o','continue']
        observed=subprocess.run(argv,cwd=self.root,capture_output=True,text=True,timeout=120)
        (self.root/'lldb-finally.stdout').write_text(observed.stdout)
        (self.root/'lldb-finally.stderr').write_text(observed.stderr)
        self.assertEqual(observed.returncode,0,observed.stdout+observed.stderr)
        self.assertRegex(observed.stdout,r'(?m)^\([^\n]*\) value = 42\s*$')
        self.assertIn('$0 = 42',observed.stdout)
        rows=[json.loads(line) for line in observed.stdout.splitlines() if line.startswith('{')]
        self.assertTrue(any(row.get('schema','').startswith('nex.debug-frame/') and
                            any(binding['name']=='value' for binding in row['bindings']) for row in rows),rows)
        self.assertTrue(any(row.get('schema')=='nex.expression/1' and row.get('ok') is True and row.get('value')=='42' for row in rows),rows)
        self.assertIn('exited with status = 0',observed.stdout)

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

    @unittest.skipUnless(platform.system() in ('Darwin','Linux'),'actual C11 provider requires native POSIX tools')
    def test_pending_return_and_partial_argument_release_physical_resource_before_catch_or_finalizer(self):
        source=r'''module owned_finalizers;
server resource Session;
server extern fn create(value:i64)->Session !{ffi}=foreign("owned","create","PIN");
server extern fn read(value:Session)->i64 !{ffi}=foreign("owned","read","PIN");
fn fail()->i64 !{throw}{throw("SOURCE","argument");}
server fn take(value:Session,ignored:i64)->Session{return value;}
server fn abandoned()->Session !{ffi,throw}{try{return create(42);}finally{throw("FINALIZER","replacement");}}
server fn partial()->unit !{ffi,throw}{
 try{let ignored:Session=take(create(1),fail());}
 finally{let next:Session=create(2);assert(read(next)==2);assert(resource_close(next));}
}
server fn main()->unit !{ffi,io}{
 try{let ignored:Session=abandoned();assert(false);}catch(c,m){assert(c=="FINALIZER"&&m=="replacement");}
 let next:Session=create(7);assert(read(next)==7);assert(resource_close(next));
 try{partial();assert(false);}catch(c,m){assert(c=="SOURCE"&&m=="argument");}
 print(42);
}
'''
        self.source(source.replace('PIN','0'*64))
        signatures={name:self.cli('ffi','--symbol',name) for name in ('create','read')}
        pins={name:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
              for name,value in signatures.items()}
        (self.root/'resource-signatures.h').write_text('\n'.join('#define PIN_'+name.upper()+' '+json.dumps(pin)
                                                             for name,pin in pins.items())+'\n')
        bundle=self.root/'bundle';bundle.mkdir();marker=self.root/'events';module=bundle/'module.so'
        compiler=Path(self.cli('doctor')['native_compiler']).with_name('clang')
        literal='"'+''.join(chr(b) if 32<=b<127 and b not in (34,92) else '\\%03o'%b
                            for b in str(marker).encode())+'"'
        produced=subprocess.run([compiler,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden',
            '-I'+str(harness.REPO/'runtime'),'-I'+str(self.root),'-DNEX_RESOURCE_MARKER='+literal,
            harness.REPO/'examples/source-resource-producer.c','-o',module],capture_output=True,text=True,timeout=60)
        self.assertEqual(produced.returncode,0,produced.stderr)
        (bundle/'NOTICE').write_text('NEX finally conformance producer\n')
        host_platform=('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x86_64')
        manifest={'schema':'nex.foreign-bundle/1','platform':host_platform,'entry':'module.so',
                  'files':[{'path':n,'sha256':hashlib.sha256((bundle/n).read_bytes()).hexdigest()} for n in ('module.so','NOTICE')],
                  'exports':pins,'notices':['NOTICE']}
        (bundle/'manifest.json').write_text(json.dumps(manifest))
        pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()
        host=self.root/'host.json';host.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':1,
            'resource_limit':1,'resource_bytes':8,'libraries':{'owned':{'directory':str(bundle),
            'manifest_sha256':pin,'exports':['create','read']}}}))
        self.source(source.replace('PIN',pin))
        for engine in ('reference','debug','release'):
            with self.subTest(engine=engine):
                if marker.exists():marker.unlink()
                args=['eval'] if engine=='reference' else ['run','--profile',engine]
                result=self.cli(*args,'--foreign',host,timeout=300)
                self.assertEqual(result['stdout'],'42\n')
                self.assertEqual(marker.read_text(),'I'+'FX'*4+'D')


if __name__=='__main__':unittest.main()
