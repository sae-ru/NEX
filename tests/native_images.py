"""Actual project DSOs, shared ownership, captured link inputs and final identity."""
import copy,ctypes,importlib.util,json,os,platform,shutil,subprocess,sys
from pathlib import Path
import unittest
PROBE=str(Path(sys.argv.pop(2)).resolve())
import support as harness

@unittest.skipUnless(platform.system() in ('Darwin','Linux'),'native shared images require Mach-O/ELF')
class NativeImages(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.root=self.root/'images % 🧠';self.root.mkdir()
        for name in ('model','producer','consumer','app'):(self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'app/main.nex'}))
        (self.root/'model/value.nex').write_text('''module model;
pub struct Payload{text:str;data:bytes;values:list<f64>;callback:fn(i64)->i64;}
pub fn make(offset:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return x+offset;};}
pub fn create()->Payload{return Payload("Я",utf8_bytes("hi"),[1.5,2.25],make(40));}
pub server fn opened()->file!{fs}{return unwrap(file_open_write("data.bin"));}
pub fn divide(x:i64)->i64{let held:list<str>=["held","🧠"];assert(len(held)==2);return 10/x;}
''')
        (self.root/'producer/main.nex').write_text('''module producer;import "../model/value.nex" as m;
pub fn transform(p:m::Payload)->m::Payload{return m::Payload(p.text+"🧠",p.data,p.values,p.callback);}
pub fn divide(x:i64)->i64{return m::divide(x);}
pub fn identity<T>(x:T)->T{return x;}
''')
        (self.root/'consumer/main.nex').write_text('''module consumer;
import "../model/value.nex" as m;import "../producer/main.nex" as a;
pub fn transform(p:m::Payload)->m::Payload{return a::identity(a::transform(p));}
pub fn invoke(f:fn(i64)->i64,x:i64)->i64{return f(x);}
pub server fn write(f:file)->unit!{fs}{assert(unwrap(file_write(f,utf8_bytes("Я🧠")))==6);}
pub fn divide(x:i64)->i64{return a::divide(x);}
''')
        self.app='''module app;import "../model/value.nex" as m;import "../consumer/main.nex" as c;
fn check_values()->unit{let p:m::Payload=m::create();let q:m::Payload=c::transform(p);
 assert(p.text=="Я");assert(q.text=="Я🧠");assert(q.data==utf8_bytes("hi"));
 assert(q.values[1]==2.25);assert(c::invoke(q.callback,2)==42);}
test fn values()->unit{check_values();}
server fn main()->unit!{fs,io}{var i:i64=0;while(i<64){check_values();i=i+1;}
 let f:file=m::opened();c::write(f);assert(file_close(f));assert(!file_close(f));print("NEX_IMAGES_OK");}
'''
        (self.root/'app/main.nex').write_text(self.app)
        self.manifest={'schema':'nex.project-build/1','default_configuration':'debug',
          'configurations':{p:{'profile':p} for p in ('debug','release','profile')},
          'components':{
            'model':{'kind':'static_library','root':'model','entry':'model/value.nex','entry_function':'create','exports':['opened','divide']},
            'producer':{'kind':'shared_library','root':'producer','entry':'producer/main.nex','entry_function':'transform','exports':['divide'],'dependencies':{'model':'static'}},
            'consumer':{'kind':'shared_library','root':'consumer','entry':'consumer/main.nex','entry_function':'transform','exports':['invoke','write','divide'],'dependencies':{'model':'static','producer':'dynamic'}},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'model':'static','consumer':'dynamic'}}}}
        self.save()
    def save(self):
        (self.root/'nex.build.json').write_text(json.dumps(self.manifest))
    def build(self,profile='debug'):
        return self.cli('project','--kind','build','--configuration',profile,timeout=300)
    def artifacts(self,result):return {a['component']:a for a in result['artifacts']}
    def execute(self,artifact,*,profile=None,code=0):
        data=self.root/'data';data.mkdir(exist_ok=True)
        env={'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(data),'NEX_FILES_WRITE':'1','NEX_TRACY':'0'}
        if profile:env['NEX_PROFILE_OUTPUT']=str(profile)
        p=subprocess.run([str(artifact)],cwd='/',capture_output=True,text=True,env=env,timeout=30)
        self.assertEqual(p.returncode,code,p.stdout+p.stderr)
        return p
    def test_real_two_dsos_static_frontier_one_runtime_and_moved_execution(self):
        self.cli('test','--symbol','values');self.cli('test','--symbol','values','--target','web')
        graph=(self.root/'.nex/graph.db').read_bytes()
        built=self.build();artifacts=self.artifacts(built)
        self.assertEqual((self.root/'.nex/graph.db').read_bytes(),graph)
        self.assertEqual(self.execute(artifacts['app']['artifact']).stdout,'NEX_IMAGES_OK\n')
        self.assertEqual((self.root/'data/data.bin').read_bytes(),'Я🧠'.encode())
        contexts={n:json.loads(Path(a['compilation']).read_text()) for n,a in artifacts.items()}
        # Concrete generic instantiation belongs to its consumer, never silently
        # recompiling ordinary binary-provider functions.
        self.assertTrue(any('producer::identity' in u['identity'] for u in contexts['consumer']['units']))
        self.assertTrue(all(u['identity'].startswith('app::') for u in contexts['app']['units']))
        self.assertEqual(len(contexts['app']['static_libraries']),1)
        images=contexts['app']['owned_images'];self.assertEqual(len(images),3)
        self.assertEqual(sum(i['kind']=='runtime' for i in images),1)
        first=ctypes.CDLL(artifacts['producer']['artifact']);second=ctypes.CDLL(artifacts['consumer']['artifact'])
        self.assertEqual(ctypes.cast(first.nex_release,ctypes.c_void_p).value,ctypes.cast(second.nex_release,ctypes.c_void_p).value)
        executable=Path(artifacts['app']['artifact']);moved=self.root/'moved % 🧠';moved.mkdir()
        shutil.copy2(executable,moved/'app');shutil.copytree(executable.parent/'images',moved/'images')
        # The loader receives only the copied application and its first-party
        # closure; source and compiler are unnecessary for execution.
        shutil.rmtree(self.root/'app');shutil.rmtree(self.root/'producer');shutil.rmtree(self.root/'consumer');shutil.rmtree(self.root/'model')
        shutil.rmtree(executable.parent.parent)
        self.assertEqual(self.execute(moved/'app').stdout,'NEX_IMAGES_OK\n')
    def test_warm_cache_and_app_only_edit_preserve_provider_and_runtime_bytes(self):
        first=self.build();warm=self.build();a=self.artifacts(first);b=self.artifacts(warm)
        self.assertTrue(all(v['cached'] for v in b.values()))
        (self.root/'app/main.nex').write_text(self.app.replace('NEX_IMAGES_OK','NEX_IMAGES_EDIT'))
        edited=self.build();c=self.artifacts(edited)
        self.assertEqual(first['native_runtime_image'],edited['native_runtime_image'])
        for n in ('model','producer','consumer'):
            self.assertEqual(a[n]['build_key'],c[n]['build_key']);self.assertTrue(c[n]['cached'])
        self.assertNotEqual(a['app']['build_key'],c['app']['build_key'])
        self.assertEqual(self.execute(c['app']['artifact']).stdout,'NEX_IMAGES_EDIT\n')
        # Captured first-party input tampering is repaired from verified stages,
        # and output tampering causes a final relink rather than a cache hit.
        p=Path(c['app']['artifact']);p.write_bytes(b'corrupt')
        repaired=self.artifacts(self.build())['app'];self.assertFalse(repaired['cached'])
        self.assertEqual(self.execute(repaired['artifact']).stdout,'NEX_IMAGES_EDIT\n')
    def test_profile_identity_and_failure_cleanup_cross_both_dsos(self):
        normal=self.artifacts(self.build('profile'))['app'];path=self.root/'normal-profile.json'
        self.execute(normal['artifact'],profile=path)
        record=json.loads(path.read_text());self.assertEqual(record['build']['build_key'],normal['build_key'])
        self.assertTrue(record['memory']);self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in record['memory']))
        failed=self.app.replace('print("NEX_IMAGES_OK");','print(c::divide(0));')
        (self.root/'app/main.nex').write_text(failed)
        trapped=self.artifacts(self.build('profile'))['app'];path=self.root/'failed-profile.json'
        p=self.execute(trapped['artifact'],profile=path,code=70)
        self.assertIn('E_DIV_ZERO',p.stderr)
        record=json.loads(path.read_text());self.assertEqual(record['build']['build_key'],trapped['build_key'])
        self.assertTrue(record['memory']);self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in record['memory']))
    def test_fully_imported_entry_needs_no_local_function_object(self):
        (self.root/'producer/main.nex').write_text('module producer;pub fn start()->i64{return 42;}')
        self.manifest['components']={
            'producer':{'kind':'shared_library','root':'producer','entry':'producer/main.nex','entry_function':'start'},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','entry_function':'producer::start','dependencies':{'producer':'dynamic'}}}
        (self.root/'app/main.nex').write_text('module app;import "../producer/main.nex" as p;')
        self.save();a=self.artifacts(self.build())['app']
        self.assertEqual(json.loads(Path(a['compilation']).read_text())['units'],[])
        self.execute(a['artifact'],code=42)
    def test_completion_paths_are_bounded_typed_and_reject_traversal(self):
        a=self.artifacts(self.build())['app'];metadata=json.loads(Path(a['metadata']).read_text())
        spec=importlib.util.spec_from_file_location('nex_core_capsule',harness.REPO/'tools/core_capsule.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        paths=module.completion_inputs(metadata);self.assertIn('objects.a',paths)
        self.assertTrue(all('..' not in Path(p).parts for p in paths))
        variants=[]
        for entry in ({'kind':'owned_image','path':'../escape.so'}, {'kind':'owned_image','path':'images/arbitrary.so'}, {'kind':'objects','path':'objects.a'}):
            d=copy.deepcopy(metadata);d['completion_inputs'][3]=entry;variants.append(d)
        d=copy.deepcopy(metadata);d['completion_inputs'].reverse();variants.append(d)
        d=copy.deepcopy(metadata);d['completion_inputs'][0]['extra']='ignored';variants.append(d)
        d=copy.deepcopy(metadata);d['completion_inputs']=[{}]*1025;variants.append(d)
        def native(d,valid):
            p=subprocess.run([PROBE,'-','-',json.dumps({'completion_metadata':d})],capture_output=True,text=True,timeout=10)
            self.assertEqual(p.returncode==0,valid,p.stdout+p.stderr)
            return json.loads(p.stdout)
        self.assertEqual(native(metadata,True)['paths'],paths)
        for d in variants:
            with self.assertRaises(ValueError):module.completion_inputs(d)
            self.assertEqual(native(d,False)['code'],'E_CORE_BUILD')

if __name__=='__main__':unittest.main()
