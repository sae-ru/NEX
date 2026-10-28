"""Package the checked architecture, retaining real binary edges and notices."""
import hashlib,json,os,shutil,subprocess,unittest
from pathlib import Path
import support as harness
import packaging as native_packaging

class ProjectPackages(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.root=self.root.resolve()/'project % 🧠';self.root.mkdir()
        for name in ('core','bridge','app','browser'):(self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}))
        (self.root/'core/math.nex').write_text('''module model;
pub fn make(offset:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return x+offset;};}
pub fn decorate(x:str)->str{return x+" 🧠";}
pub server fn secret()->str{return "NEX_SERVER_ONLY_POISON";}
''')
        (self.root/'bridge/main.nex').write_text('module bridge;import "../core/math.nex" as m;pub fn answer()->str{return m::decorate(str(m::make(40)(2)));}')
        (self.root/'app/main.nex').write_text('module app;import "../bridge/main.nex" as b;fn main()->unit!{io}{print(b::answer());}')
        (self.root/'browser/main.nex').write_text('''module browser;import "std/web.nex" as web;
client fn initial()->i64{return 0;}client fn update(s:i64,e:web::Event)->i64{return s+1;}
client fn view(s:i64)->web::View{return web::element("main",[],[],[web::text(str(s))]);}
client fn title()->str{return "Packaged NEX";}
''')
        self.description={'schema':'nex.project-build/1','default_configuration':'release',
          'configurations':{p:{'profile':p} for p in ('debug','release','profile')},
          'components':{
            'core':{'kind':'shared_library','root':'core','entry':'core/math.nex','entry_function':'make','exports':['decorate']},
            'bridge':{'kind':'shared_library','root':'bridge','entry':'bridge/main.nex','entry_function':'answer','dependencies':{'core':'dynamic'}},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'bridge':'dynamic'}},
            'browser':{'kind':'web','root':'browser','entry':'browser/main.nex'}}}
        self.save()
    def save(self):(self.root/'nex.build.json').write_text(json.dumps(self.description))
    def package(self,*args,**kwargs):
        return self.cli('project','--kind','package','--directory',self.root/'package',*args,timeout=300,**kwargs)
    def inventory(self,folder):
        report=json.loads((folder/'project.json').read_text())
        actual={p.relative_to(folder).as_posix() for p in folder.rglob('*') if p.is_file() or p.is_symlink()}
        self.assertEqual(actual,set(report['files'])|{'project.json'})
        for name,row in report['files'].items():
            p=folder/name
            if p.is_symlink():self.assertEqual(p.readlink().as_posix(),row['symlink'])
            else:self.assertEqual(hashlib.sha256(p.read_bytes()).hexdigest(),row['sha256'])
        return report
    def test_whole_native_and_browser_package_runs_after_source_build_removal_and_move(self):
        result=self.package();self.assertEqual(result['schema'],'nex.project-package/1')
        self.assertFalse(result['application_execution']);self.assertFalse((self.root/'.nex/graph.db').exists())
        folder=self.root/'package';report=self.inventory(folder)
        self.assertEqual({a['component'] for a in report['components']},{'app','browser'})
        self.assertTrue(report['native_dependencies_inspected'])
        native=json.loads((folder/'apps/app/application.json').read_text())
        owned=[v for v in native['files'].values() if 'owned_image_kind' in v]
        self.assertEqual(len(owned),3);self.assertEqual(sum(v['owned_image_kind']=='runtime' for v in owned),1)
        self.assertIn('nex-generated-project-images',{c['name'] for c in native['components']})
        web=folder/'web/browser';self.assertTrue((web/'index.html').is_file());self.assertTrue((web/'THIRD_PARTY_NOTICES.txt').is_file())
        for p in web.rglob('*'):
            if p.is_file():self.assertNotIn(b'NEX_SERVER_ONLY_POISON',p.read_bytes())
        for name in ('core','bridge','app','browser','.nex'):shutil.rmtree(self.root/name)
        moved=self.root/'moved package % 🧠';folder.rename(moved)
        p=subprocess.run([str(moved/'apps/app/bin/app')],cwd='/',env={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':'/absent'},capture_output=True,text=True,timeout=20)
        self.assertEqual((p.returncode,p.stdout),(0,'42 🧠\n'),p.stderr)
        self.inventory(moved)
    def test_profiled_shared_package_keeps_final_identity_and_ownership(self):
        result=self.package('--component','app','--configuration','profile')
        app=next(c for c in result['components'] if c['component']=='app');profile=self.root/'profile.json'
        p=subprocess.run([str(self.root/'package'/app['entry'])],env={'PATH':'/usr/bin:/bin','NEX_TRACY':'0','NEX_PROFILE_OUTPUT':str(profile)},capture_output=True,text=True,timeout=30)
        self.assertEqual((p.returncode,p.stdout),(0,'42 🧠\n'),p.stderr)
        raw=json.loads(profile.read_text());self.assertEqual(raw['build']['build_key'],app['build_key'])
        self.assertTrue(raw['memory']);self.assertTrue(all(v['live']==0 and v['allocations']==v['frees'] for v in raw['memory']))
    def test_output_and_invalid_selection_fail_before_build_or_store_creation(self):
        output=self.root/'package';output.mkdir();marker=output/'keep';marker.write_text('keep')
        self.assertEqual(self.package(ok=False)['code'],'E_EXISTS');self.assertEqual(marker.read_text(),'keep');shutil.rmtree(output)
        self.assertEqual(self.package('--component','core',ok=False)['code'],'E_PROJECT_CAPABILITY')
        self.assertEqual(self.cli('project','--kind','package',ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('project','--directory',output,ok=False)['code'],'E_OPTION')
        self.assertFalse((self.root/'.nex').exists())
    def test_generated_images_do_not_grant_unrelated_library_provenance(self):
        helper=native_packaging.Packaging('test_storage_needs_provenance_and_survives_original_library_removal');helper.root=self.root
        config,library=helper.sqlite_toolchain(self.root/'private SQLite % 🧠')
        self.description['configurations']['release']['toolchain']=config.name
        (self.root/'app/main.nex').write_text('''module app;import "../bridge/main.nex" as b;
server fn main()->unit!{db,io}{assert(is_ok(store_put("key",b::answer())));print(unwrap(store_get("key")));}
''');self.save()
        database=self.root/'private.sqlite';env={'NEX_DATABASE':str(database),'NEX_STORAGE_OWNER':'alice'}
        failed=self.package('--component','app',ok=False,env=env)
        self.assertEqual(failed['code'],'E_PROJECT_PACKAGE');self.assertIn('provenance',failed['message']);self.assertFalse((self.root/'package').exists());self.assertFalse(database.exists())
        notices=helper.notice(helper.library_inputs([library]));self.package('--component','app','--notices',notices,env=env)
        self.assertFalse(database.exists());shutil.rmtree(library.parent);shutil.rmtree(self.root/'.nex')
        p=subprocess.run([str(self.root/'package/apps/app/bin/app')],env={'PATH':'/usr/bin:/bin',**env},capture_output=True,text=True,timeout=20)
        self.assertEqual((p.returncode,p.stdout),(0,'42 🧠\n'),p.stderr)

if __name__=='__main__':unittest.main()
