"""Real NEX external declarations, checked C modules and preserved language history."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import sqlite3
import subprocess
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness
import server_http as http_harness

PIN='0'*64
C=r'''
#include "nex_ffi_module.h"
#include <fcntl.h>
#include <stdlib.h>
#include <unistd.h>
static void mark(char c){const char *p=getenv("NEX_SOURCE_FFI_MARKER");if(p){int f=open(p,O_WRONLY|O_CREAT|O_APPEND,0600);if(f>=0){(void)write(f,&c,1);close(f);}}}
__attribute__((constructor)) static void start(void){mark('I');}
__attribute__((destructor)) static void end(void){mark('D');}
static nex_ffi_status echo(const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref *v,uint64_t n,nex_ffi_ref *o,void *u){(void)u;if(n!=1)return NEX_FFI_ARGUMENT;mark('C');(void)a->poll(c);*o=v[0];return NEX_FFI_OK;}
static nex_ffi_status unit(const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref *v,uint64_t n,nex_ffi_ref *o,void *u){(void)v;(void)u;if(n)return NEX_FFI_ARGUMENT;mark('U');(void)a->poll(c);*o=0;return NEX_FFI_OK;}
static nex_ffi_status wrong(const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref *v,uint64_t n,nex_ffi_ref *o,void *u){(void)v;(void)n;(void)u;mark('W');return a->make_bool(c,1,o);}
static nex_ffi_status aggregate(const nex_ffi_api_v1 *a,nex_ffi_call c,const nex_ffi_ref *v,uint64_t n,nex_ffi_ref *o,void *u){nex_ffi_type t=0;(void)u;mark('A');nex_ffi_status s=a->result_type(c,&t);return s?s:a->make_nominal(c,t,0,v,n,o);}
static const nex_ffi_export_v1 exports[]={EXPORTS};
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){static const nex_ffi_module_v1 module={1,sizeof(nex_ffi_module_v1),sizeof(exports)/sizeof(exports[0]),sizeof(nex_ffi_export_v1),exports};mark('G');return abi==1&&size>=sizeof(nex_ffi_api_v1)?&module:0;}
'''

class SourceFFI(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.marker=self.root/'events'
        self.env={'NEX_SOURCE_FFI_MARKER':str(self.marker)}

    def program(self,source,exports,*,symbols=None):
        self.source(source.replace('@PIN@',PIN))
        self.signatures={name:self.cli('ffi','--symbol',(symbols or {}).get(name,name),env=self.env) for name in exports}
        rows=[]
        for name,body in exports.items():
            digest=hashlib.sha256(json.dumps(self.signatures[name],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            rows.append('{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(digest)+','+body+',0}')
        bundle=self.root/'bundle';bundle.mkdir()
        c=self.root/'producer.c';c.write_text(C.replace('EXPORTS',','.join(rows)))
        driver=self.cli('doctor')['native_compiler']
        result=subprocess.run([driver,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden','-I'+str(harness.REPO/'runtime'),str(c),'-o',str(bundle/'module')],capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        (bundle/'NOTICE').write_text('NEX source FFI independent C fixture\n')
        machine={'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','AMD64':'x86_64'}[platform.machine()]
        manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+machine,'entry':'module','files':[{'path':n,'sha256':hashlib.sha256((bundle/n).read_bytes()).hexdigest()} for n in ('module','NOTICE')],'exports':{n:hashlib.sha256(json.dumps(v,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest() for n,v in self.signatures.items()},'notices':['NOTICE']}
        (bundle/'manifest.json').write_text(json.dumps(manifest))
        self.pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()
        self.host=self.root/'host.json'
        self.catalogue={'schema':'nex.foreign-host/1','module_limit':64,'libraries':{'test':{'directory':'bundle','manifest_sha256':self.pin,'exports':list(exports)}}}
        self.host.write_text(json.dumps(self.catalogue))
        self.source(source.replace('@PIN@',self.pin))
        return bundle

    def events(self):
        return self.marker.read_text() if self.marker.exists() else ''

    def test_static_archive_calls_foreign_module_through_one_consumer_runtime(self):
        self.program('''module archiveffi;
server extern fn echo(value:str)->str !{ffi}=foreign("test","echo","@PIN@");
pub server fn exported(value:str)->str !{ffi}{return echo(value);}
server fn main()->unit !{ffi,io}{print(exported("ok"));}
''', {'echo':'echo'})
        core=self.root/'core';core.mkdir();self.file.rename(core/'main.nex')
        app=self.root/'app';app.mkdir();(app/'main.nex').write_text('''module consumer;
import "../core/main.nex" as c;
server fn main()->unit !{ffi,io}{print(c::exported("Я🧠"));}
''')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'app/main.nex'}))
        (self.root/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{'debug':{'profile':'debug'},'release':{'profile':'release'}},'components':{
                'core':{'kind':'static_library','root':'core','entry':'core/main.nex','entry_function':'exported'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'static'}}}}))
        # The runtime-bearing legacy archive must contain objects, not linker
        # flags or target Crypto libraries passed as archive member names.
        legacy=self.cli('build',core/'main.nex','--library','--entry','archiveffi::exported',timeout=180)
        self.assertTrue(Path(legacy['executable']).read_bytes().startswith(b'!<arch>\n'))
        self.assertEqual(self.events(),'')
        for profile in ['debug','release']:
            built=self.cli('project','--kind','build','--configuration',profile,timeout=180)
            artifact=next(a for a in built['artifacts'] if a['component']=='app')
            compilation=json.loads(Path(artifact['compilation']).read_text())
            self.assertFalse(any(f.startswith('archiveffi::') for u in compilation['units'] for f in u['functions']))
            if profile=='debug':
                denied=subprocess.run([artifact['artifact']],env={**os.environ,**self.env},capture_output=True,text=True,timeout=30)
                self.assertNotEqual(denied.returncode,0);self.assertIn('E_FFI_GRANT',denied.stderr)
                self.assertEqual(self.events(),'')
            result=subprocess.run([artifact['artifact'],'--nex-foreign',str(self.host)],env={**os.environ,**self.env},capture_output=True,text=True,timeout=30)
            self.assertEqual((result.returncode,result.stdout),(0,'Я🧠\n'),result.stderr)
        self.assertEqual(self.events().count('C'),2)

    def both(self,expected):
        self.assertEqual(self.cli('eval','--foreign',self.host,env=self.env)['stdout'],expected)
        for profile in ('debug','release'):
            result=self.cli('run','--foreign',self.host,'--profile',profile,env=self.env,timeout=120)
            self.assertEqual((result['exit_code'],result['stdout']),(0,expected))
        self.cli('test','--foreign',self.host,env=self.env,timeout=120)

    def test_scalar_unit_short_circuit_and_left_to_right_calls(self):
        self.program('''module interop;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server extern fn done()->unit!{ffi}=foreign("test","done","@PIN@");
server fn value(x:i64)->i64!{io}{print(x);return x;}
server fn main()->unit!{io,ffi}{print(echo(value(41))+1);assert((false&&(echo(0)==1))==false);done();}
server test fn checks()->unit!{ffi}{assert(echo(42)==42);done();}
''',{'echo':'echo','done':'unit'})
        self.cli('check',env=self.env);self.assertEqual(self.events(),'')
        self.both('41\n42\n')
        context=self.cli('context','--symbol','echo');self.assertEqual(context['foreign'],{'library':'test','export':'echo','manifest_sha256':self.pin})

    @unittest.skipUnless(platform.system()=='Darwin','Darwin @rpath install-name regression')
    def test_external_native_program_finds_explicit_rpath_crypto_library(self):
        self.program('''module interop;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server fn main()->unit!{ffi,io}{print(echo(42));}
''',{'echo':'echo'})
        doctor=self.cli('doctor')
        folder=self.root/'crypto "quoted" \\ % 🧠';folder.mkdir()
        crypto=folder/'nex_test_crypto.dylib'
        shutil.copyfile(Path(doctor['native_openssl_crypto']).resolve(),crypto)
        for command in [['/usr/bin/install_name_tool','-id','@rpath/nex_test_crypto.dylib',str(crypto)],
                        ['/usr/bin/codesign','--force','--sign','-',str(crypto)]]:
            result=subprocess.run(command,capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        config=self.root/'toolchain.json'
        config.write_text(json.dumps({'schema':'nex.toolchain/1','target':doctor['host'],
            'openssl':{'include':doctor['native_openssl_include'],'ssl':doctor['native_openssl_ssl'],'crypto':str(crypto)}}))
        for profile in ('debug','release'):
            native=self.cli('run','--foreign',self.host,'--toolchain',config,'--profile',profile,env=self.env,timeout=120)
            self.assertEqual((native['exit_code'],native['stdout']),(0,'42\n'))
        build=self.cli('build','--toolchain',config,'--profile','release')
        dependencies=subprocess.run(['/usr/bin/otool','-L',build['executable']],capture_output=True,text=True,timeout=30)
        self.assertEqual(dependencies.returncode,0,dependencies.stderr)
        self.assertIn('@rpath/nex_test_crypto.dylib',dependencies.stdout)
        self.file.unlink()
        result=subprocess.run([build['executable'],'--nex-foreign',str(self.host)],cwd=self.root,
            env={**os.environ,**self.env,'NEX_RESOURCE_DIR':str(self.root/'absent-resources')},capture_output=True,text=True,timeout=30)
        self.assertEqual((result.returncode,result.stdout),(0,'42\n'),result.stderr)

    def test_all_value_kinds_and_nominal_result_owners(self):
        source='''module interop;
struct Packet{value:i64;}enum Maybe{None;Some(value:Packet);}
struct Bundle{number:i64;flag:bool;real:f64;text:str;data:bytes;handle:file;callback:fn(i64)->i64;nested:list<result<Maybe>>;}
server extern fn collect(number:i64,flag:bool,real:f64,text:str,data:bytes,handle:file,callback:fn(i64)->i64,nested:list<result<Maybe>>)->Bundle!{ffi}=foreign("test","collect","@PIN@");
server fn check()->unit!{ffi,fs}{var offset:i64=2;let callback:fn(i64)->i64=fn(x:i64)->i64{return x+offset;};offset=9;let handle:file=unwrap(file_open_read("payload"));let data:bytes=unwrap(bytes([0,255,128,1]));let value:Bundle=collect(42,true,1.25,"Я\\u0000🧠",data,handle,callback,[ok(Maybe::Some(Packet(7)))]);assert(value.number==42&&value.flag&&value.real==1.25);assert(value.text=="Я\\u0000🧠"&&value.data==data);assert(value.handle==handle&&value.callback==callback&&value.callback(40)==42);assert(value.nested==[ok(Maybe::Some(Packet(7)))]);assert(file_close(handle));assert(!file_is_open(value.handle));}
server fn main()->unit!{ffi,fs,io}{check();print("owners OK");}
server test fn checks()->unit!{ffi,fs}{check();}
'''
        self.program(source,{'collect':'aggregate'})
        folder=self.root/'data';folder.mkdir();(folder/'payload').write_bytes(b'data')
        self.env['NEX_FILES_ROOT']=str(folder)
        self.both('owners OK\n')

    def test_forwarded_callable_retains_real_closure_semantics(self):
        self.program('''module interop;
server extern fn forward(value:fn(i64)->i64)->(fn(i64)->i64)!{ffi}=foreign("test","forward","@PIN@");
server fn main()->unit!{ffi,io}{var offset:i64=2;let value:fn(i64)->i64=fn(x:i64)->i64{return x+offset;};let returned:fn(i64)->i64=forward(value);offset=9;assert(value==returned);print(returned(40));}
server test fn checks()->unit!{ffi}{let value:fn(i64)->i64=fn(x:i64)->i64{return x+1;};assert(forward(value)(41)==42);}
''',{'forward':'echo'})
        self.both('42\n')

    def test_imported_external_function_can_be_passed_as_a_checked_server_callable(self):
        native=self.root/'native.nex'
        native.write_text('module bridge;pub server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","'+PIN+'");')
        self.program('''module interop;import "./native.nex" as native;
server fn invoke(callback:server fn(i64)->i64!{ffi})->i64!{ffi}{return callback(42);}
server fn main()->unit!{ffi,io}{let callback:server fn(i64)->i64!{ffi}=native::echo;print(invoke(callback));}
server test fn checks()->unit!{ffi}{assert(invoke(native::echo)==42);}
''',{'echo':'echo'},symbols={'echo':'bridge::echo'})
        native.write_text(native.read_text().replace(PIN,self.pin))
        self.both('42\n')

    def test_explicit_authority_is_required_and_environment_cannot_grant_it(self):
        self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'echo'})
        env={**self.env,'NEX_FOREIGN_CONFIG':str(self.host)}
        self.assertEqual(self.cli('eval',env=env,ok=False)['code'],'E_FFI_GRANT')
        native=self.cli('run',env=env,ok=False,timeout=120);self.assertEqual(native['exit_code'],70);self.assertIn('E_FFI_GRANT',native['stderr']);self.assertEqual(self.events(),'')
        self.catalogue['libraries']['test']['exports']=['missing'];self.host.write_text(json.dumps(self.catalogue))
        self.assertEqual(self.cli('eval','--foreign',self.host,env=self.env,ok=False)['code'],'E_FFI_GRANT');self.assertEqual(self.events(),'')

    def test_standalone_binary_uses_only_explicit_catalogue_and_archived_binding(self):
        self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'echo'})
        revision=self.cli('check')['revision'];built=self.cli('build','--profile','release',timeout=120);self.file.unlink()
        result=subprocess.run([built['executable'],'--nex-foreign',str(self.host)],capture_output=True,text=True,timeout=20,cwd='/',env={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':str(self.root/'absent')})
        self.assertEqual((result.returncode,result.stdout),(0,'42\n'),result.stderr)
        self.assertEqual(self.cli('eval','--revision',revision,'--foreign',self.host)['stdout'],'42\n')
        self.assertEqual(self.cli('run','--revision',revision,'--foreign',self.host,timeout=120)['stdout'],'42\n')

    def test_pin_and_signature_fail_before_initialization_and_bad_returns_are_checked(self):
        self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'wrong'})
        original=self.file.read_text();self.file.write_text(original.replace(self.pin,'f'*64))
        self.assertEqual(self.cli('eval','--foreign',self.host,env=self.env,ok=False)['code'],'E_FFI_HASH');self.assertEqual(self.events(),'')
        self.file.write_text(original.replace('echo(x:i64)->i64','echo(x:i64)->bool'))
        self.assertEqual(self.cli('eval','--foreign',self.host,env=self.env,ok=False)['code'],'E_FFI_SIGNATURE');self.assertEqual(self.events(),'')
        self.file.write_text(original)
        self.assertEqual(self.cli('eval','--foreign',self.host,env=self.env,ok=False)['code'],'E_FFI_TYPE')
        native=self.cli('run','--foreign',self.host,env=self.env,ok=False,timeout=120);self.assertEqual(native['exit_code'],70);self.assertIn('E_FFI_TYPE',native['stderr']);self.assertTrue(self.events().endswith('D'))
        mapped=native['native_diagnostics']['diagnostics'][0]
        self.assertEqual(mapped['status'],'mapped');self.assertEqual(mapped['symbol'],'interop::echo')
        self.assertEqual(mapped['report']['code'],'E_FFI_TYPE')
        self.assertEqual(mapped['report']['source']['kind'],'block')
        self.assertEqual(self.cli('context','--site',mapped['operation_site'])['nodes'][0]['id'],mapped['operation_id'])


    def test_rejected_declarations_effects_realms_and_bindings(self):
        valid='module rejected;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","'+PIN+'");'
        cases=[(valid.replace('server extern','extern'),'E_REALM'),(valid.replace('!{ffi}',''),'E_EFFECT'),(valid.replace('fn echo(x:i64)','fn echo<T>(x:T)'),'E_FFI_DECLARATION'),(valid.replace('"test"','"../test"'),'E_FFI_BINDING'),(valid.replace(PIN,'bad'),'E_FFI_BINDING'),(valid+'fn main()->i64{return echo(1);}','E_EFFECT'),(valid+'client fn main()->i64!{ffi}{return echo(1);}','E_REALM')]
        for source,code in cases:
            self.source(source);self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_unreachable_external_code_and_metadata_are_absent_from_browser_and_native_runtime(self):
        source='''module projection;server extern fn secret(x:i64)->i64!{ffi}=foreign("native_secret_library","native_secret_export","'''+PIN+'''");fn main()->unit!{io}{print("pure");}client test fn browser()->unit{assert(1+1==2);}'''
        self.source(source);self.cli('test','--target','web');folder=self.root/'web';self.cli('emit','--kind','typescript','--entry','browser','--directory',folder)
        for p in folder.rglob('*'):
            if p.is_file():
                text=p.read_text();self.assertNotIn('native_secret_library',text);self.assertNotIn('native_secret_export',text);self.assertNotIn(PIN,text)
        built=self.cli('build',timeout=120);metadata=Path(built['metadata']).read_text();self.assertNotIn('nex_foreign.cpp',metadata)
        self.assertEqual(self.cli('emit','--kind','typescript','--entry','secret',ok=False)['code'],'E_REALM')

    def test_migration_preserves_genuine_014_history_and_ordinary_identifier_names(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.14.json').read_text());self.source(fixture['source']);old=self.historical_store('0.14')['revision'];self.file.unlink()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:ids=db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall();source=db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0]
        self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION');current=self.cli('migrate');self.assertEqual(current['language'],'0.16');self.assertNotEqual(current['revision'],old)
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],fixture['stdout']);self.assertEqual(self.cli('run','--revision','HEAD',timeout=120)['stdout'],fixture['stdout']);self.cli('test','--revision','HEAD','--target','web')
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(),ids);self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0],source);self.assertEqual(db.execute('SELECT language FROM revisions WHERE hash=?',(old,)).fetchone()[0],'0.14')

    def test_profile_debug_context_and_package_requires_operator_catalogue(self):
        self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'echo'})
        report=self.cli('profile','--foreign',self.host,'--output',self.root/'profile',timeout=120);self.assertEqual(report['exit_code'],0)
        session=self.cli('debug','--kind','nex-dap','--foreign',self.host,timeout=120);self.assertEqual(session['launch']['args'],['--nex-foreign',str(self.host)])
        self.assertEqual(self.cli('package','--directory',self.root/'package',ok=False,timeout=120)['code'],'E_FFI_PACKAGE')

    def test_catalogue_errors_keep_their_public_diagnostics(self):
        self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'echo'})
        for text in ('{', '{"schema":"wrong"}'):
            self.host.write_text(text)
            for command in ('eval','test'):
                diagnostic=self.cli(command,'--foreign',self.host,ok=False)
                self.assertTrue(diagnostic['code'].startswith('E_FFI'),diagnostic)
                self.assertEqual(diagnostic['schema'],'nex.diagnostic/1')
        self.assertEqual(self.events(),'')

    def test_http_authorization_precedes_module_initialization_and_calls_use_request_scopes(self):
        self.program('''module interop;
import "std/http.nex" as http;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server fn handle(request:http::Request)->http::Response!{ffi}{return http::json_response(200,encode_json(echo(42)));}
''',{'echo':'echo'})
        auth=self.root/'auth.json';token=self.cli('token','--user','alice','--auth',auth)['token']
        assets=self.root/'assets';assets.mkdir();(assets/'index.html').write_text('NEX source FFI')
        built=self.cli('build','--target','server','--profile','release',timeout=180)
        process=http_harness.HTTP.launch(self,built['executable'],auth,env=self.env)
        try:
            status,body,_=http_harness.HTTP.request(self,'/api/value',token=token)
            self.assertEqual((status,body['error']['code']),(500,'E_FFI_GRANT'))
        finally:http_harness.HTTP.stop(self,process)
        self.assertEqual(self.events(),'')
        process=http_harness.HTTP.launch(self,built['executable'],auth,foreign=self.host,env=self.env)
        try:
            self.assertEqual(http_harness.HTTP.request(self,'/health')[0],200)
            self.assertEqual(http_harness.HTTP.request(self,'/api/value')[0],401)
            self.assertEqual(self.events(),'')
            for _ in range(3):self.assertEqual(http_harness.HTTP.request(self,'/api/value',token=token)[:2],(200,'42'))
            before=self.events();self.assertEqual(before.count('C'),3)
            self.assertEqual(http_harness.HTTP.request(self,'/api/value',token='invalid')[0],401)
            self.assertEqual(self.events(),before)
        finally:http_harness.HTTP.stop(self,process)
        # Startup must reject serving the operator catalogue as a public asset.
        exposed=assets/'host.json';exposed.write_text(json.dumps({**self.catalogue,'libraries':{'test':{**self.catalogue['libraries']['test'],'directory':str(self.root/'bundle')}}}))
        denied=subprocess.run([built['executable'],'--auth',str(auth),'--database',str(self.root/'private.sqlite'),'--static',str(assets),'--foreign',str(exposed)],capture_output=True,text=True,timeout=15)
        self.assertNotEqual(denied.returncode,0);self.assertIn('outside the static root',denied.stderr)
        shutil.copytree(self.root/'bundle',assets/'bundle')
        self.catalogue['libraries']['test']['directory']='assets/bundle';self.host.write_text(json.dumps(self.catalogue))
        denied=subprocess.run([built['executable'],'--auth',str(auth),'--database',str(self.root/'private.sqlite'),'--static',str(assets),'--foreign',str(self.host)],capture_output=True,text=True,timeout=15)
        self.assertNotEqual(denied.returncode,0);self.assertIn('module directories must be outside',denied.stderr)

    def test_changed_source_manifest_pin_invalidates_native_wrapper_and_preserves_old_binary(self):
        bundle=self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn helper()->i64{return 42;}server fn main()->unit!{ffi,io}{print(echo(helper()));}''',{'echo':'echo'})
        first=self.cli('build',timeout=120);old_pin=self.pin
        notice=bundle/'NOTICE';notice.write_text(notice.read_text()+'Reviewed bundle update\n')
        manifest=json.loads((bundle/'manifest.json').read_text())
        for item in manifest['files']:
            if item['path']=='NOTICE':item['sha256']=hashlib.sha256(notice.read_bytes()).hexdigest()
        (bundle/'manifest.json').write_text(json.dumps(manifest));new_pin=hashlib.sha256((bundle/'manifest.json').read_bytes()).hexdigest()
        self.catalogue['libraries']['test']['manifest_sha256']=new_pin;self.host.write_text(json.dumps(self.catalogue))
        self.file.write_text(self.file.read_text().replace(old_pin,new_pin))
        second=self.cli('build',timeout=120);self.assertNotEqual(first['build_key'],second['build_key'])
        self.assertGreater(second['compiled_functions'],0);self.assertGreater(second['reused_functions'],0)
        self.assertEqual(self.cli('run','--foreign',self.host,timeout=120)['stdout'],'42\n')
        old=subprocess.run([first['executable'],'--nex-foreign',str(self.host)],capture_output=True,text=True,timeout=15)
        self.assertEqual(old.returncode,70);self.assertIn('E_FFI_HASH',old.stderr)

    if LIVE:
        def test_live_lldb_external_wrapper_watch_and_explicit_execution_arguments(self):
            self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'echo'})
            session=self.cli('debug','--kind','nex-dap','--foreign',self.host,timeout=120)
            symbol=self.cli('context','--symbol','echo')['native_symbol']
            commands=session['launch']['initCommands']+['settings set target.disable-aslr false','breakpoint set -n '+symbol,'run','nex-eval x','continue']
            arguments=[shutil.which('lldb'),'--batch',session['launch']['program']]
            for command in commands:arguments+=['-o',command]
            result=subprocess.run(arguments,capture_output=True,text=True,timeout=60,env={**os.environ,**self.env})
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertNotIn('unknown or ambiguous option',result.stdout+result.stderr)
            values=[json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]
            self.assertTrue(any(value.get('schema')=='nex.expression/1' and value.get('value')=='42' for value in values),result.stdout)
            self.assertIn('exited with status = 0',result.stdout)
            self.assertEqual(self.events().count('C'),1);self.assertTrue(self.events().endswith('D'))

if __name__=='__main__':unittest.main()
