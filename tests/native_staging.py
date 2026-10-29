"""Real PIC object reuse before a final shared-image link (private build API)."""
import ctypes,hashlib,json,os,platform,shutil,subprocess,sys,tempfile,unittest
from pathlib import Path
PROBE=str(Path(sys.argv.pop(2)).resolve())
import support as harness

class NativeStaging(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.root=self.root/'PIC % 🧠';self.root.mkdir()
        self.cache=self.root/'cache'
        for name in ('producer','consumer','app'):(self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}))
        (self.root/'producer/main.nex').write_text('''module producer;
pub struct Payload{text:str;data:bytes;values:list<f64>;callback:fn(i64)->i64;}
pub fn make(offset:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return x+offset;};}
pub fn create()->Payload{return Payload("Я",utf8_bytes("hi"),[1.5,2.25],make(40));}
pub fn decorate(text:str)->str{return text+"🧠";}
pub server fn opened()->file!{fs}{return unwrap(file_open_write("data.bin"));}
pub fn divide(x:i64)->i64{let held:list<str>=["held","🧠"];assert(len(held)==2);return 10/x;}
''')
        (self.root/'consumer/main.nex').write_text('''module consumer;import "../producer/main.nex" as a;
pub fn transform(p:a::Payload)->a::Payload{return a::Payload(a::decorate(p.text),p.data,p.values,p.callback);}
pub fn invoke(f:fn(i64)->i64,x:i64)->i64{return f(x);}
pub server fn write(f:file)->unit!{fs}{assert(unwrap(file_write(f,utf8_bytes("Я🧠")))==6);}
''')
        self.app='''module app;import "../producer/main.nex" as a;import "../consumer/main.nex" as b;
fn check_values()->unit{let p:a::Payload=a::create();let q:a::Payload=b::transform(p);
 assert(p.text=="Я");assert(q.text=="Я🧠");assert(q.data==utf8_bytes("hi"));
 assert(q.values[1]==2.25);assert(b::invoke(q.callback,2)==42);}
test fn values()->unit{check_values();}
server fn main()->unit!{fs,io}{var i:i64=0;while(i<64){check_values();i=i+1;}
 let f:file=a::opened();b::write(f);assert(file_close(f));assert(!file_close(f));print("NEX_PIC_OK");}
'''
        (self.root/'app/main.nex').write_text(self.app)
    def run_tool(self,command,*,env=None,ok=True):
        p=subprocess.run(list(map(str,command)),cwd=self.root,env=env,capture_output=True,text=True,timeout=180)
        self.assertEqual(p.returncode==0,ok,p.stdout+p.stderr)
        return p
    def stage(self,name='app',*,ok=True,**options):
        p=self.run_tool([PROBE,self.root/name/'main.nex',self.cache,json.dumps(options)],ok=ok)
        return json.loads(p.stdout)
    def link_output(self,command,output):
        # LLVM ELF output writers interpret '%' as a template marker. Keep
        # literal user paths in inputs/loader policy, and publish the linked
        # bytes from an owned output path without template characters.
        with tempfile.TemporaryDirectory(prefix='nex-pic-link-') as temporary:
            linked=Path(temporary)/output.name
            self.run_tool([*command,'-o',linked])
            shutil.copy2(linked,output)
    def closure(self,pic=True,defer=True,profile="debug"):
        a=self.stage('producer',entry='create',exports=['make','decorate','opened','divide'],library=True,code_only=True,pic=pic,defer=defer,profile=profile)
        b=self.stage('consumer',entry='transform',exports=['invoke','write'],library=True,code_only=True,pic=pic,defer=defer,libraries=[a],profile=profile)
        app=self.stage(libraries=[b,a],pic=pic,defer=defer,profile=profile)
        return {'producer':a,'consumer':b,'app':app}
    def test_entry_validation_and_explicit_pic_are_required_before_staging(self):
        self.assertEqual(self.stage(defer=True,ok=False)['code'],'E_OPTION')
        self.assertEqual(self.stage(defer=True,pic=True,entry='check_values',library=False,exports=['check_values'],ok=False)['code'],'E_OPTION')
        self.assertEqual(self.stage(defer=True,pic=True,entry='values',ok=False)['code'],'E_ENTRY')
        # Deferred output must not relax the executable contract into a library.
        (self.root/'app/main.nex').write_text('module app;fn main(x:i64)->i64{return x;}')
        self.assertEqual(self.stage(defer=True,pic=True,ok=False)['code'],'E_ENTRY')
    def test_stage_preserves_main_and_profile_and_server_contracts_without_runtime(self):
        profiled=self.stage(pic=True,defer=True,profile='profile')
        folder=Path(profiled['artifact']).parent;meta=json.loads(Path(profiled['metadata']).read_text())
        self.assertTrue(meta['runtime_requirements']['profiling'])
        self.assertIn('nex_profile.cpp',meta['runtime_components'])
        self.assertIn('define i32 @main(', (folder/'program.ll').read_text())
        self.assertIn('nex_profile_enter',(folder/'program.ll').read_text())
        self.assertFalse((folder/'application-identity.cpp').exists())
        self.assertFalse((folder/'profile-identity.cpp').exists())
        (self.root/'app/main.nex').write_text('''module app;import "std/http.nex" as http;
server fn handle(request:http::Request)->http::Response{return http::text_response(200,request.path);}
''')
        server=self.stage(pic=True,defer=True,entry='handle',target='server')
        folder=Path(server['artifact']).parent;meta=json.loads(Path(server['metadata']).read_text())
        self.assertEqual((meta['kind'],meta['final_kind']),('object_archive','http_server'))
        self.assertTrue(meta['runtime_requirements']['storage'])
        self.assertIn('http_main.cpp',meta['runtime_components'])
        self.assertFalse((folder/'server-bridge.cpp').exists())
        self.assertFalse((folder/'http_main.o').exists())
    def test_pic_abi_and_cache_are_distinct_and_integrity_checked(self):
        staged=self.closure()
        for name,item in staged.items():
            meta=json.loads(Path(item['metadata']).read_text())
            self.assertEqual((meta['kind'],meta['position_independent'],meta['deferred_link']),('object_archive',True,True))
            folder=Path(item['artifact']).parent
            for component in meta['runtime_components']:self.assertFalse((folder/Path(component).with_suffix('.o')).exists())
            self.assertTrue(meta['runtime_inputs'])
            units=json.loads(Path(item['compilation']).read_text())['units']
            self.assertTrue(all(u['identity'].startswith(name+'::') for u in units))
        warm=self.closure();self.assertTrue(all(a['cached'] for a in warm.values()))
        # Final ordinary PIC links reuse the exact generated function objects.
        pic=self.closure(defer=False)
        for name,item in pic.items():
            self.assertEqual(item['library_abi'],staged[name]['library_abi'])
            self.assertEqual(item['compiled_functions'],0)
            self.assertGreater(item['reused_functions'],0)
        plain=self.closure(pic=False,defer=False)
        self.assertNotEqual(plain['app']['library_abi'],pic['app']['library_abi'])
        for name in staged:
            def keys(item):return {u['input_key'] for u in json.loads(Path(item['compilation']).read_text())['units']}
            self.assertFalse(keys(staged[name])&keys(plain[name]))
        self.assertEqual(self.stage(pic=True,defer=True,libraries=[plain['producer']],ok=False)['code'],'E_PROJECT_ABI')
        bad=dict(staged['producer']);bad['hash']='0'*64
        self.assertEqual(self.stage(pic=True,defer=True,libraries=[bad],ok=False)['code'],'E_PROJECT_INPUT_CHANGED')
        folder=Path(staged['app']['artifact']).parent
        (folder/'library-abi.json').write_text('{}')
        repaired=self.closure()['app'];self.assertFalse(repaired['cached'])
        self.assertEqual(repaired['compiled_functions'],0)
        self.assertEqual(repaired['hash'],staged['app']['hash'])
    @unittest.skipUnless(platform.system() in ('Darwin','Linux'),'shared link test needs Mach-O or ELF')
    def test_real_archives_link_two_dsos_with_one_runtime_and_move(self):
        self.exercise_shared_link('debug')
    @unittest.skipUnless(platform.system() in ('Darwin','Linux'),'shared profile needs Mach-O or ELF')
    def test_shared_profile_binds_final_executable_and_keeps_unbound_host_null(self):
        self.exercise_shared_link('profile')
    def exercise_shared_link(self,profile):
        profiling=profile=='profile'
        self.cli('test','--symbol','values');self.cli('test','--symbol','values','--target','web')
        built=self.closure(profile=profile);meta=json.loads(Path(built['app']['metadata']).read_text())
        driver=json.loads(meta['toolchain_inputs'])['driver'];darwin=platform.system()=='Darwin'
        link_driver=driver+(['--ld-path='+meta['linker']] if meta['linker'] else [])
        bundle=self.root/'bundle';lib=bundle/'lib';lib.mkdir(parents=True);(bundle/'bin').mkdir()
        objects=self.root/'objects';objects.mkdir();extension='.dylib' if darwin else '.so'
        # dyld caches install names process-wide, including libraries loaded by
        # earlier fixtures. Distinct runtime inputs/profile flags need distinct
        # image names, as the production final linker will require too.
        runtime_tag=hashlib.sha256(json.dumps({'inputs':meta['runtime_inputs'],'profile':profile,'target':meta['compiler_target']},sort_keys=True).encode()).hexdigest()[:16]
        runtime=lib/('libnex_runtime_'+runtime_tag+extension)
        libraries={name:lib/('libnex_'+name+'_'+built[name]['key'][:16]+extension) for name in ('producer','consumer')}
        def rpath(value):return ['-Xlinker','-rpath','-Xlinker',value]
        def from_archive(artifact,stem):
            destination=objects/stem;destination.mkdir()
            toolchain=json.loads(meta['toolchain_inputs'])
            archiver=toolchain['archiver']
            # Consume the actual checked compiler objects, never recompiling IR.
            p=subprocess.run([archiver,'x',artifact],cwd=destination,capture_output=True,text=True,timeout=30)
            self.assertEqual(p.returncode,0,p.stdout+p.stderr)
            result=list(destination.glob('*.o'));self.assertTrue(result)
            return result
        def shared(output,inputs):
            flags=['-dynamiclib'] if darwin else ['-shared','-Xlinker','-z','-Xlinker','defs']
            self.link_output(link_driver+flags+list(inputs)+['-Xlinker','-install_name' if darwin else '-soname','-Xlinker',('@rpath/' if darwin else '')+output.name,*rpath('@loader_path' if darwin else '$ORIGIN'),'-g'],output)
        projection=Path(meta['runtime_source_projection']);runtime_objects=[]
        for index,component in enumerate(meta['runtime_components']):
            self.assertNotEqual(component,'http_main.cpp')
            obj=objects/('runtime-'+str(index)+'.o')
            arguments=driver+['-std=c++20','-c',projection/component,'-I',projection,'-g','-O0','-fPIC','-o',obj]
            if profiling:
                arguments+=['-D'+flag for flag in ('NEX_PROFILE_ENABLED','NEX_SHARED_PROFILE_RUNTIME','TRACY_ENABLE','TRACY_ON_DEMAND','TRACY_DELAYED_INIT','TRACY_MANUAL_LIFETIME','TRACY_ONLY_LOCALHOST','TRACY_NO_BROADCAST','TRACY_NO_CODE_TRANSFER','TRACY_NO_CALLSTACK','TRACY_NO_SYSTEM_TRACING','TRACY_NO_SAMPLING','TRACY_NO_CRASH_HANDLER','TRACY_NO_FRAME_IMAGE')]+['-pthread']
            self.run_tool(arguments)
            runtime_objects.append(obj)
        shared(runtime,runtime_objects+(['-pthread']+([] if darwin else ['-ldl']) if profiling else []))
        for name in ('producer','consumer'):
            shared(libraries[name],[*from_archive(built[name]['artifact'],name),*([libraries['producer']] if name=='consumer' else []),runtime])
        first=ctypes.CDLL(str(libraries['producer']));second=ctypes.CDLL(str(libraries['consumer']))
        pointer=lambda library:ctypes.cast(library.nex_release,ctypes.c_void_p).value
        self.assertEqual(pointer(first),pointer(second));self.assertTrue(pointer(first))
        # The test link has its own explicit identity. Staging receipts do not
        # describe these manually linked images or grant production provenance.
        identity={'schema':'nex.test-shared-link/1','marker':'PIC stage'}
        profile_identity={'schema':'nex.test-profile-link/1','marker':'bound shared PIC runtime'}
        source=objects/'identity.cpp';text='extern "C" const char *nex_application_identity()noexcept{return '+json.dumps(json.dumps(identity))+';}'
        if profiling:text+='extern "C" const char *nex_profile_build_info(){return '+json.dumps(json.dumps(profile_identity))+';}'
        source.write_text(text)
        identity_object=objects/'identity.o';self.run_tool(driver+['-std=c++20','-c',source,'-fPIC','-o',identity_object])
        def executable(item,filename):
            app=bundle/'bin'/filename
            self.link_output(link_driver+[*from_archive(item['artifact'],filename),identity_object,libraries['consumer'],libraries['producer'],runtime,'-Xlinker','-export_dynamic' if darwin else '--export-dynamic',*rpath('@executable_path/../lib' if darwin else '$ORIGIN/../lib'),'-g'],app)
            return app
        app=executable(built['app'],'app')
        data=self.root/'data';data.mkdir();environment={'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(data),'NEX_FILES_WRITE':'1'}
        if profiling:
            environment.update(NEX_TRACY='0',NEX_PROFILE_OUTPUT=str(data/'bound-profile.json'))
        run=self.run_tool([app],env=environment);self.assertEqual((run.stdout,run.stderr),('NEX_PIC_OK\n',''))
        if profiling:
            measured=json.loads((data/'bound-profile.json').read_text())
            self.assertEqual(measured['build'],profile_identity)
            functions={f['name']:f for f in measured['functions']}
            self.assertEqual(functions['producer::create']['calls'],64)
            self.assertEqual(functions['consumer::transform']['calls'],64)
            self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in measured['memory']))
            # An ordinary C++ process owns no NEX application/profile identity.
            debug=json.loads((Path(built['producer']['artifact']).parent/'debug.json').read_text())
            symbol=next(f['native_symbol'] for f in debug['functions'] if f['name']=='producer::create')
            host=objects/'unbound.cpp';host.write_text('extern "C" void *'+symbol+'();extern "C" void nex_release(void*);extern "C" void nex_runtime_finish();int main(){auto p='+symbol+'();nex_release(p);nex_runtime_finish();}')
            host_image=bundle/'bin/unbound-host'
            self.link_output(link_driver+[host,libraries['producer'],runtime,*rpath('@executable_path/../lib' if darwin else '$ORIGIN/../lib')],host_image)
            unbound_environment={**environment,'NEX_PROFILE_OUTPUT':str(data/'unbound-profile.json')}
            denied=self.run_tool([host_image],env=unbound_environment,ok=False)
            self.assertEqual(denied.returncode,70);self.assertIn('E_CONTEXT',denied.stderr)
            # An ownership boundary does not bind a profile/application identity.
            # Keep the host unbound while enclosing owned generated functions.
            host.write_text('#include <cstdint>\nextern "C" void *'+symbol+'();extern "C" void nex_release(void*);extern "C" int64_t nex_application_run(void*,int64_t,const char*const*);static int64_t entry(int64_t,const char*const*){auto p='+symbol+'();nex_release(p);return 0;}int main(){return static_cast<int>(nex_application_run(reinterpret_cast<void*>(&entry),0,nullptr));}')
            self.link_output(link_driver+[host,libraries['producer'],runtime,*rpath('@executable_path/../lib' if darwin else '$ORIGIN/../lib')],host_image)
            observed=self.run_tool([host_image],env=unbound_environment);self.assertEqual((observed.stdout,observed.stderr),('',''))
            unbound=json.loads((data/'unbound-profile.json').read_text())
            self.assertIsNone(unbound['build'])
            self.assertEqual(next(f['calls'] for f in unbound['functions'] if f['name']=='producer::create'),1)
            self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in unbound['memory']))
        self.assertEqual((data/'data.bin').read_bytes(),'Я🧠'.encode())
        (self.root/'app/main.nex').write_text(self.app.replace('print("NEX_PIC_OK");','print(a::divide(0));'))
        failed=self.closure(profile=profile);self.assertTrue(failed['producer']['cached']);self.assertTrue(failed['consumer']['cached'])
        trap=self.run_tool([executable(failed['app'],'failing')],env=environment,ok=False)
        self.assertEqual(trap.returncode,70);self.assertIn('E_DIV_ZERO',trap.stderr);self.assertNotIn('E_INTERNAL_LEAK',trap.stderr)
        diagnostic=next(json.loads(line.split(' ',1)[1]) for line in trap.stderr.splitlines() if line.startswith('NEX_NATIVE_TRAP '))
        self.assertEqual(diagnostic['application'],identity)
        if profiling:
            measured=json.loads((data/'bound-profile.json').read_text())
            self.assertEqual(measured['build'],profile_identity)
            functions={f['name']:f for f in measured['functions']}
            self.assertEqual(functions['producer::divide']['aborted'],1)
            self.assertEqual(functions['app::main']['aborted'],1)
            self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in measured['memory']))
        moved=self.root/'moved % 🧠';bundle.rename(moved)
        run=self.run_tool([moved/'bin/app'],env=environment);self.assertEqual((run.stdout,run.stderr),('NEX_PIC_OK\n',''))

if __name__=='__main__':unittest.main()
