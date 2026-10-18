"""Real NEX external declarations, checked C modules and preserved language history."""
import hashlib
import json
from pathlib import Path
import platform
import sqlite3
import subprocess
import unittest
import support as harness

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

    def program(self,source,exports):
        self.source(source.replace('@PIN@',PIN))
        self.signatures={name:self.cli('ffi','--symbol',name,env=self.env) for name in exports}
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
        self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION');current=self.cli('migrate');self.assertEqual(current['language'],'0.15');self.assertNotEqual(current['revision'],old)
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],fixture['stdout']);self.assertEqual(self.cli('run','--revision','HEAD',timeout=120)['stdout'],fixture['stdout']);self.cli('test','--revision','HEAD','--target','web')
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(),ids);self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0],source);self.assertEqual(db.execute('SELECT language FROM revisions WHERE hash=?',(old,)).fetchone()[0],'0.14')

    def test_profile_debug_context_and_explicit_package_pending(self):
        self.program('''module interop;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");server fn main()->unit!{ffi,io}{print(echo(42));}''',{'echo':'echo'})
        report=self.cli('profile','--foreign',self.host,'--output',self.root/'profile',timeout=120);self.assertEqual(report['exit_code'],0)
        session=self.cli('debug','--kind','nex-dap','--foreign',self.host,timeout=120);self.assertEqual(session['launch']['args'],['--nex-foreign',str(self.host)])
        self.assertEqual(self.cli('package','--directory',self.root/'package',ok=False,timeout=120)['code'],'E_FFI_PACKAGE')

if __name__=='__main__':unittest.main()
