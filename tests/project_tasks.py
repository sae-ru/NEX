"""Task acceptance and replay must retain the declared physical architecture."""
import copy,json,os,shutil,subprocess
from pathlib import Path
import unittest
import support as harness

class ProjectTasks(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.root=self.root/'project % 🧠';self.root.mkdir()
        for name in ('core','producer','app','browser','unused'):(self.root/name).mkdir()
        self.package=self.root.parent/'external words';self.package.mkdir()
        (self.package/'text.nex').write_text('module words;pub fn decorate(value:str)->str{return value+" 🧠";}')
        (self.package/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':'text.nex'}))
        (self.package/'secret.txt').write_text('NEX_UNRELATED_PACKAGE_FILE_078')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':'app/main.nex','libraries':{'words':str(self.package)}}))
        (self.root/'core/value.nex').write_text('module core;pub fn compute(n:i64)->i64{return n*2;}test fn twice()->unit{assert(compute(21)==42);}')
        (self.root/'producer/main.nex').write_text('''module producer;import "../core/value.nex" as c;import "words/text.nex" as w;
pub fn render()->str{return w::decorate(str(c::compute(21)));}test fn rendered()->unit{assert(render()=="42 🧠");}''')
        (self.root/'app/main.nex').write_text('''module app;import "../producer/main.nex" as p;
fn main()->unit!{io}{print(p::render());}test fn correct()->unit{assert(p::render()=="42 🧠");}''')
        (self.root/'browser/main.nex').write_text('''module browser;import "std/web.nex" as w;import "../core/value.nex" as c;
client fn initial()->i64{return c::compute(21);}client fn title()->str{return "Tasks";}
client fn update(s:i64,e:w::Event)->i64{return s+1;}
client fn view(s:i64)->w::View{return w::element("main",[],[],[w::text(str(s))]);}
client test fn correct()->unit{assert(initial()==42);}''')
        (self.root/'unused/main.nex').write_text('module unused;pub fn value()->str{return "NEX_UNSELECTED_SOURCE_SENTINEL_078";}')
        self.architecture={'schema':'nex.project-build/1','default_configuration':'debug',
          'configurations':{p:{'profile':p} for p in ('debug','release','profile')},
          'components':{
            'core':{'kind':'static_library','root':'core','entry':'core/value.nex','entry_function':'compute'},
            'producer':{'kind':'shared_library','root':'producer','entry':'producer/main.nex','entry_function':'render','dependencies':{'core':'static'}},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'producer':'dynamic'}},
            'browser':{'kind':'web','root':'browser','entry':'browser/main.nex','dependencies':{'core':'source'}},
            'unused':{'kind':'source','root':'unused','entry':'unused/main.nex'}}}
        self.save_architecture()
    def save_architecture(self):(self.root/'nex.build.json').write_text(json.dumps(self.architecture))
    def scaffold(self,component='app',configuration='debug'):
        return self.cli('task','nex.build.json','--kind','init','--component',component,'--configuration',configuration,timeout=120)
    def save_task(self,task):
        task.update(id='architecture-task',title='Project acceptance',goal='Preserve checked binary dependencies and observable behavior')
        (self.root/'task.json').write_text(json.dumps(task))
    def task(self,kind,*args,**kwargs):return self.cli('task','task.json','--kind',kind,*args,timeout=600,**kwargs)
    def add(self,task,check,symbol):
        check['program']='app';task['checks'].append(check)
        task['requirements'].append({'id':check['id'],'text':'Reviewed architecture acceptance','targets':[check['target']],
            'checks':[check['id']],'bindings':[{'program':'app','kind':'function','symbol':symbol}]})
    def test_scaffold_check_are_readonly_architecture_and_pin_exact_configurations_and_tests(self):
        task=self.scaffold();self.assertFalse((self.root/'.nex').exists())
        plan=self.cli('project','--component','app');self.assertEqual(task['programs'][0]['project']['architecture_hash'],plan['architecture_hash'])
        self.assertEqual({c['configuration'] for c in task['checks']},{'debug'});self.assertFalse(any('profile' in c for c in task['checks']))
        self.save_task(task);before=self.cli('check')['revision'];checked=self.task('check');self.assertTrue(checked['ok'])
        self.assertEqual(self.cli('history')['head'],before);self.assertFalse((self.root/'.nex/build').exists())
        self.architecture['components']['app']['dependencies']['producer']='source';self.save_architecture()
        self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_PROJECT')
    def test_real_binary_run_tests_profile_artifacts_and_source_deleted_replay(self):
        task=self.scaffold();self.add(task,{'id':'run','kind':'run','target':'native','configuration':'debug','expect':{'stdout':'42 🧠\n','exit_code':0}},'app::main')
        self.add(task,{'id':'profile','kind':'profile','target':'native','configuration':'profile','entry':'app::main','scenario':'one render',
            'budget':{'max_calls':{'producer::render':'1'},'max_peak_handles':'100000'}},'producer::render')
        self.save_task(task);checked=self.task('check');run=self.task('run','--task-hash',checked['task_hash']);self.assertTrue(run['ok'])
        receipt=Path(run['output']);full=json.loads(receipt.read_text());self.assertTrue(all(c['status']=='passed' for c in full['checks']))
        capture=json.loads((receipt.parent/'inputs/projects/app.json').read_text());raw=json.dumps(capture,ensure_ascii=False)
        self.assertNotIn('NEX_UNRELATED_PACKAGE_FILE_078',raw);self.assertNotIn('NEX_UNSELECTED_SOURCE_SENTINEL_078',raw)
        native=next(c for c in full['checks'] if c['id']=='build-native');artifact=receipt.parent/next(c['directory'] for c in native['components'] if c['component']=='app')/'app'
        child=subprocess.run([str(artifact)],cwd='/',capture_output=True,text=True,timeout=20);self.assertEqual((child.returncode,child.stdout),(0,'42 🧠\n'))
        app_compile=json.loads((artifact.parent/'compilation.json').read_text());self.assertTrue(all(u['identity'].startswith('app::') for u in app_compile['units']))
        self.assertEqual(len(app_compile['owned_images']),2);self.assertEqual(sum(i['kind']=='runtime' for i in app_compile['owned_images']),1)
        run_check=next(c for c in full['checks'] if c['id']=='run');self.assertIn('once',run_check['reference_skip_reason']);self.assertNotIn('reference',run_check)
        moved=self.root.parent/'moved run';shutil.copytree(receipt.parent,moved,symlinks=True)
        shutil.rmtree(self.package);shutil.rmtree(self.root)
        replay=self.cli('task',moved/'receipt.json','--kind','replay','--directory',moved.parent/'replayed',cwd=moved.parent,timeout=600)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],run['programs'])
    def test_archived_graph_candidate_overlays_code_without_materializing_it_in_original_sources(self):
        task=self.scaffold();self.add(task,{'id':'run','kind':'run','target':'native','configuration':'debug','expect':{'stdout':'42 🧠\n','exit_code':0}},'app::main');self.save_task(task)
        old=self.cli('check')['revision'];p=self.root/'core/value.nex';changed=p.read_text().replace('n*2','n*3');p.write_text(changed)
        run=self.task('run','--revision',old);self.assertTrue(run['ok']);self.assertEqual(p.read_text(),changed);self.assertEqual(self.cli('history')['head'],old)
    def test_current_toolchain_catalogue_is_required_and_check_never_executes_its_driver(self):
        doctor=self.cli('doctor');driver=self.root/'compiler';marker=self.root/'driver-ran'
        driver.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\nexec "'+doctor['native_compiler']+'" "$@"\n');driver.chmod(0o700)
        config=self.root/'toolchain.json';config.write_text(json.dumps({'schema':'nex.toolchain/1','target':doctor['host'],'compiler':str(driver)}))
        self.architecture['configurations']['debug']['toolchain']='toolchain.json';self.save_architecture();task=self.scaffold();self.save_task(task)
        self.assertTrue(all(c.get('toolchain')=='project' for c in task['checks']));self.assertFalse(marker.exists())
        self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_TOOLCHAIN');self.assertFalse(marker.exists())
        catalog=self.root/'trusted.json';catalog.write_text(json.dumps({'project':str(config)}));self.assertTrue(self.task('check','--toolchains',catalog)['ok']);self.assertFalse(marker.exists())
    def test_browser_task_retains_client_sources_and_reuses_project_web_artifacts(self):
        task=self.scaffold('browser');self.save_task(task);run=self.task('run');self.assertTrue(run['ok'])
        receipt=Path(run['output']);full=json.loads(receipt.read_text());web=next(c for c in full['checks'] if c['id']=='build-web')
        component=next(c for c in web['components'] if c['component']=='browser');dist=receipt.parent/component['directory']/'dist';self.assertTrue((dist/'index.html').is_file())
        capture=json.loads((receipt.parent/'inputs/projects/app.json').read_text());self.assertTrue(any('/lib/web.nex' in p for p in capture['files']))
    def test_component_package_aliases_retain_actual_archive_ownership(self):
        p=self.root/'nex.json';metadata=json.loads(p.read_text());metadata['libraries']['alias']='core';p.write_text(json.dumps(metadata))
        p=self.root/'producer/main.nex';p.write_text(p.read_text().replace('"../core/value.nex"','"alias/value.nex"'))
        self.save_task(self.scaffold());run=self.task('run');self.assertTrue(run['ok'])
        full=json.loads(Path(run['output']).read_text());self.assertTrue(all(c['status']=='passed' for c in full['checks']))
    def test_build_test_preserves_effectful_code_without_executing_or_opening_a_graph(self):
        p=self.root/'app/main.nex';p.write_text(p.read_text()+'\nserver test fn once()->unit!{fs}{unwrap(file_write_text("executed","once"));}\n')
        env={'NEX_FILES_ROOT':str(self.root),'NEX_FILES_WRITE':'1'}
        result=self.cli('project','--kind','build-test','--component','app','--symbol','app::once',env=env,timeout=300)
        self.assertEqual(result['schema'],'nex.project-test-build/1');self.assertFalse(result['test_execution']);self.assertFalse(result['graph_store_opened'])
        self.assertFalse((self.root/'executed').exists());self.assertFalse((self.root/'.nex/graph.db').exists())
        artifact=next(a for a in result['build']['artifacts'] if a['component']=='app')
        child=subprocess.run([artifact['artifact']],cwd=self.root,env={**os.environ,**env},capture_output=True,text=True,timeout=30)
        self.assertEqual(child.returncode,0,child.stdout+child.stderr);self.assertEqual((self.root/'executed').read_text(),'once')
    def test_project_capture_is_indexed_and_tampering_rejects_before_replay(self):
        task=self.scaffold();task['checks']=[];task['requirements']=[]
        self.add(task,{'id':'effects','kind':'effects','target':'source','configuration':'debug','symbols':['app::main'],'allowed_effects':['io']},'app::main');self.save_task(task)
        result=self.task('run');receipt=Path(result['output']);index=json.loads((receipt.parent/'inputs/manifest.json').read_text())
        self.assertIn('inputs/projects/app.json',index['files']);capture=receipt.parent/'inputs/projects/app.json';capture.write_text('{}\n')
        rejected=self.cli('task',receipt,'--kind','replay','--directory',self.root/'rejected-replay',ok=False,timeout=120)
        self.assertEqual(rejected['code'],'E_TASK_INTEGRITY');self.assertFalse((self.root/'rejected-replay').exists())

    def test_source_deleted_project_replay_does_not_use_an_enclosing_project_graph(self):
        ancestor=self.root.parent;(ancestor/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':'ancestor.nex'}))
        (ancestor/'ancestor.nex').write_text('module outer;fn main()->i64{return 77;}');self.cli('check',ancestor/'ancestor.nex',cwd=ancestor)
        task=self.scaffold();task['checks']=[];task['requirements']=[]
        self.add(task,{'id':'effects','kind':'effects','target':'source','configuration':'debug','symbols':['app::main'],'allowed_effects':['io']},'app::main');self.save_task(task)
        run=self.task('run','--directory',ancestor/'captured/run');receipt=Path(run['output']);before=harness.database_rows(ancestor/'.nex/graph.db')
        shutil.rmtree(self.root);shutil.rmtree(self.package)
        replay=self.cli('task',receipt,'--kind','replay','--directory',ancestor/'replayed',cwd=ancestor,timeout=180)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],run['programs']);self.assertEqual(harness.database_rows(ancestor/'.nex/graph.db'),before)
        self.assertTrue((Path(replay['output']).parent/'state/.nex/graph.db').is_file());self.assertFalse((receipt.parent/'.nex/graph.db').exists())

if __name__=='__main__':unittest.main()
