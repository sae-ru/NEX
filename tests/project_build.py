"""Project architecture must constrain actual imports and drive real artifacts."""
import copy,json,os,shlex,sqlite3,subprocess
from pathlib import Path
import unittest
import support as harness

class Projects(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        for name in ['core','app','bridge','browser']:(self.root/name).mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'app/main.nex'}))
        (self.root/'core/value.nex').write_text('module model;pub fn calculate(x:i64)->i64{return x*3+7;}pub server fn secret()->str{return "NEX_SERVER_ONLY_POISON";}')
        (self.root/'app/main.nex').write_text('module app;import "../core/value.nex" as m;fn main()->unit!{io}{print(m::calculate(5));}test fn check_value()->unit{assert(m::calculate(5)==22);}')
        (self.root/'bridge/main.nex').write_text('module bridge;import "../core/value.nex" as m;pub fn answer()->i64{return m::calculate(5);}')
        (self.root/'browser/main.nex').write_text('''module browser;
import "std/web.nex" as web;import "../core/value.nex" as m;
client fn initial()->i64{return m::calculate(0);}
client fn update(s:i64,e:web::Event)->i64{return s+1;}
client fn view(s:i64)->web::View{return web::element("main",[],[],[web::text(str(s))]);}
client fn title()->str{return "Project browser";}
''')
        self.description={'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{'debug':{'profile':'debug'},'release':{'profile':'release'}},
            'components':{
                'core':{'kind':'source','root':'core','entry':'core/value.nex'},
                'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'source'}},
                'bridge':{'kind':'static_library','root':'bridge','entry':'bridge/main.nex','entry_function':'answer','dependencies':{'core':'source'}},
                'browser':{'kind':'web','root':'browser','entry':'browser/main.nex','dependencies':{'core':'source'}}}}
        self.save()
    def save(self):
        (self.root/'nex.build.json').write_text(json.dumps(self.description))
    def plan(self,*args,**kwargs):return self.cli('project',*args,**kwargs)
    def rows(self):
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            tables=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in tables}
    def test_read_only_plan_binds_sources_configuration_and_direct_architecture_edges(self):
        a=self.plan();b=self.plan()
        self.assertEqual(a,b);self.assertEqual(a['schema'],'nex.project-plan/1')
        self.assertTrue(a['source_checked']);self.assertFalse(a['external_tools_invoked'])
        self.assertFalse((self.root/'.nex').exists())
        self.assertEqual(a['components'][0]['name'],'core')
        app=next(c for c in a['components'] if c['name']=='app')
        self.assertEqual(app['dependencies'],{'core':'source'})
        self.assertEqual({s['component'] for s in app['sources']},{'core','app'})
        selected=self.plan('--component','app','--configuration','release')
        self.assertEqual([c['name'] for c in selected['components']],['core','app'])
        self.assertNotEqual(a['plan_hash'],selected['plan_hash'])
        (self.root/'core/value.nex').write_text((self.root/'core/value.nex').read_text().replace('x*3+7','x*3+8'))
        self.assertNotEqual(self.plan()['plan_hash'],a['plan_hash'])
    def test_plan_does_not_execute_configured_native_compiler(self):
        target=self.cli('doctor')['host'];fake=self.root/'never-execute';marker=self.root/'executed'
        fake.write_text('#!/bin/sh\ntouch '+shlex.quote(str(marker))+'\nexit 97\n');fake.chmod(0o700)
        (self.root/'toolchain.json').write_text(json.dumps({'schema':'nex.toolchain/1','target':target,'compiler':str(fake)}))
        self.description['configurations']['debug']['toolchain']='toolchain.json';self.save()
        self.assertTrue(self.plan('--component','app')['ok']);self.assertFalse(marker.exists())
        self.assertFalse((self.root/'.nex').exists())
    def test_real_application_and_static_archive_agree_with_checked_source(self):
        del self.description['components']['browser'];self.save()
        built=self.plan('--kind','build','--configuration','release',timeout=180)
        self.assertEqual(built['schema'],'nex.project-build-result/1');self.assertFalse((self.root/'.nex/graph.db').exists())
        artifacts={a['component']:a for a in built['artifacts']};self.assertEqual(set(artifacts),{'app','bridge'})
        binary=Path(artifacts['app']['artifact']);run=subprocess.run([str(binary)],cwd='/',capture_output=True,text=True,timeout=10)
        self.assertEqual((run.returncode,run.stdout),(0,'22\n'))
        self.assertEqual(self.cli('eval')['stdout'],run.stdout)
        self.cli('test','--target','web')
        library=artifacts['bridge'];debug=json.loads(Path(library['debug_manifest']).read_text())
        symbol=next(f['native_symbol'] for f in debug['functions'] if f['name']=='bridge::answer')
        host=self.root/'host.cpp';host.write_text('extern "C" long long '+symbol+'();int main(){return '+symbol+'()==22?0:1;}')
        compiler=self.cli('doctor')['native_compiler'];exe=self.root/'host'
        linked=subprocess.run([compiler,'-std=c++20',str(host),library['artifact'],'-o',str(exe)],capture_output=True,text=True,timeout=30)
        self.assertEqual(linked.returncode,0,linked.stdout+linked.stderr)
        self.assertEqual(subprocess.run([str(exe)],timeout=10).returncode,0)
        warm=self.plan('--kind','build','--configuration','release',timeout=60)
        self.assertEqual(warm['plan_hash'],built['plan_hash']);self.assertTrue(all(a['cached'] for a in warm['artifacts']))
    def test_actual_browser_artifacts_exclude_unreachable_server_code(self):
        built=self.plan('--kind','build','--component','browser',timeout=180)
        artifact,=built['artifacts'];self.assertEqual(artifact['kind'],'web')
        generated=Path(artifact['result']['directory']);self.assertTrue((Path(artifact['result']['dist'])/'index.html').is_file())
        self.assertNotIn('NEX_SERVER_ONLY_POISON',(generated/'src/program.ts').read_text())
        self.assertFalse((self.root/'.nex/graph.db').exists())
    def test_undeclared_and_transitive_only_imports_reject_before_building(self):
        self.description['components']['app']['dependencies']={};self.save()
        for kind in ['plan','build']:
            error=self.plan('--kind',kind,'--component','app',ok=False)
            self.assertEqual(error['code'],'E_PROJECT_BOUNDARY');self.assertFalse((self.root/'.nex').exists())
        self.description['components']['app']['dependencies']={'bridge':'source'};self.save()
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY')
    def test_configured_package_alias_cannot_bypass_component_ownership(self):
        p=self.root/'nex.json';metadata=json.loads(p.read_text());metadata['libraries']={'alias':'core'};p.write_text(json.dumps(metadata))
        self.description['components']['app']['dependencies']={};self.save()
        (self.root/'app/main.nex').write_text('module app;import "alias/value.nex" as m;fn main()->i64{return m::calculate(5);}')
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY')
        self.description['components']['app']['dependencies']={'core':'source'};self.save()
        app=self.plan('--component','app')['components'][-1]
        self.assertEqual(next(s for s in app['sources'] if s['path']=='@pkg/alias/value.nex')['component'],'core')
    def test_cycles_even_outside_selection_and_nonlibrary_dependencies_reject(self):
        self.description['components']['core']['dependencies']={'bridge':'source'};self.save()
        self.assertEqual(self.plan('--component','browser',ok=False)['code'],'E_PROJECT_CYCLE')
        self.description['components']['core']['dependencies']={'app':'source'};self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD')
    def test_overlapping_roots_symlink_aliases_and_unowned_sources_reject(self):
        baseline=copy.deepcopy(self.description)
        self.description['components']['app']['root']='.';self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD')
        self.description=copy.deepcopy(baseline);(self.root/'alias').symlink_to(self.root/'core',target_is_directory=True)
        self.description['components']['app']['root']='alias';self.description['components']['app']['entry']='alias/value.nex';self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD')
        self.description=baseline;self.save();(self.root/'hidden.nex').write_text('module hidden;pub fn value()->i64{return 1;}')
        (self.root/'app/main.nex').write_text('module app;import "../hidden.nex" as h;fn main()->i64{return h::value();}')
        self.assertEqual(self.plan('--component','app',ok=False)['code'],'E_PROJECT_BOUNDARY')
    def test_unknown_configuration_component_fields_and_unsupported_linkage_reject(self):
        for option,value in [('--component','absent'),('--configuration','absent')]:
            self.assertEqual(self.plan(option,value,ok=False)['code'],'E_PROJECT_BUILD')
        base=copy.deepcopy(self.description)
        for value,code in [('static','E_PROJECT_CAPABILITY'),('dynamic','E_PROJECT_CAPABILITY'),(True,'E_PROJECT_CAPABILITY')]:
            self.description=copy.deepcopy(base);self.description['components']['app']['dependencies']['core']=value;self.save()
            self.assertEqual(self.plan('--kind','build',ok=False)['code'],code)
        self.description=copy.deepcopy(base);self.description['components']['bridge']['kind']='shared_library';self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_CAPABILITY')
        self.description=copy.deepcopy(base);self.description['execution']={'device':'npu'};self.save()
        self.assertEqual(self.plan(ok=False)['code'],'E_PROJECT_BUILD');self.assertFalse((self.root/'.nex').exists())
    def test_all_selected_sources_preflight_before_any_artifact_and_selection_is_explicit(self):
        (self.root/'browser/main.nex').write_text('module broken;fn broken(}')
        self.assertTrue(self.plan('--component','app')['ok'])
        out=self.root/'never-created'
        self.plan('--kind','build','--build-directory',out,ok=False)
        self.assertFalse(out.exists());self.assertFalse((self.root/'.nex').exists())
    def test_graph_history_remains_unchanged_on_success_and_rejection(self):
        self.cli('check');before=self.rows();self.plan();self.assertEqual(before,self.rows())
        self.description['components']['app']['dependencies']={};self.save();self.plan('--kind','build',ok=False)
        self.assertEqual(before,self.rows())
    def test_duplicate_json_invalid_utf8_and_oversized_manifests_reject(self):
        p=self.root/'nex.build.json'
        for raw in [b'{"schema":"nex.project-build/1","schema":"other"}',b'\xff',b' '*262145]:
            p.write_bytes(raw);self.plan(ok=False);self.assertFalse((self.root/'.nex').exists())
    def test_noncurrent_language_is_rejected_before_any_graph_or_artifact(self):
        p=self.root/'nex.json';x=json.loads(p.read_text());x['language']='0.15';p.write_text(json.dumps(x))
        self.assertEqual(self.plan('--kind','build',ok=False)['code'],'E_LANGUAGE_VERSION');self.assertFalse((self.root/'.nex').exists())

if __name__=='__main__':unittest.main()
