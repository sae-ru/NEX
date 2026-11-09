"""Task packages retain deployable binary edges without executing the app."""
import json,os,shutil,subprocess,unittest
from pathlib import Path
import support as harness
import package_notices
import packaging as native_packaging

class ProjectPackageTasks(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.base=self.root;self.root=self.base/'project % 🧠'
        shutil.copytree(harness.REPO/'examples/project-tasks',self.root,ignore=shutil.ignore_patterns('.nex'))
        self.architecture=json.loads((self.root/'nex.build.json').read_text())
    def save_architecture(self):
        (self.root/'nex.build.json').write_text(json.dumps(self.architecture), newline="\n")
    def scaffold(self,component='app',target='native'):
        task=self.cli('task','nex.build.json','--kind','init','--component',component,'--configuration','release')
        symbol={'app':'project_task::app::main','browser':'browser::initial','service':'service::handle'}[component]
        task.update(checks=[{'id':'package','kind':'package','program':'app','configuration':'release','target':target,'timeout_seconds':300}],
          requirements=[{'id':'delivery','text':'Capture the reviewed application package without running it',
            'targets':[target],'checks':['package'],'bindings':[{'program':'app','kind':'function','symbol':symbol}]}])
        if target!='web':
            if not hasattr(self,'operator_notices'):
                self.operator_notices=package_notices.retain(self.root/'operator-notices')
            notices=self.operator_notices
            if notices:
                inspected=self.cli('task',notices,'--kind','notices')
                task['checks'][0].update(notices=notices.relative_to(self.root).as_posix(),notices_hash=inspected['inputs_hash'])
        (self.root/'task.json').write_text(json.dumps(task), newline="\n");return task
    def run_task(self,directory):
        # A normal caller need not set Python's bytecode-cache policy. Package
        # helpers must not add unindexed files to the captured executable inputs.
        env={**os.environ};env.pop('PYTHONDONTWRITEBYTECODE',None)
        p=subprocess.run([harness.NEX,'task','task.json','--kind','run','--directory',str(directory),'--json'],
            cwd=self.root,env=env,capture_output=True,text=True,timeout=600)
        diagnostics=''
        if p.returncode:
            command=directory/'artifacts/package/commands/package.json'
            if command.is_file():diagnostics=command.read_text()[-16000:]
        self.assertEqual(p.returncode,0,p.stdout+p.stderr+diagnostics);return json.loads(p.stdout)

    def pin_notices(self,task,roots):
        license=self.root/'fixture-license.txt';license.write_text('Explicit test fixture provenance; not a redistribution licence.\n', newline="\n")
        catalogue=self.root/'notices.json';catalogue.write_text(json.dumps({'schema':'nex.sdk-notices/1','components':[
            {'name':'task-fixture-inputs','version':'fixture','url':'https://example.invalid/nex-test-inputs','roots':list(map(str,roots)),'license_files':['fixture-license.txt']}]}), newline="\n")
        inspected=self.cli('task','notices.json','--kind','notices');self.assertFalse(inspected['external_tools_invoked']);self.assertFalse(inspected['graph_store_opened'])
        task['checks'][0].update(notices='notices.json',notices_hash=inspected['inputs_hash']);(self.root/'task.json').write_text(json.dumps(task), newline="\n");return inspected
    def test_package_is_not_execution_and_replays_after_source_build_removal(self):
        main=self.root/'app/main.nex';main.write_text(main.read_text().replace('fn main()->unit!{io}{','server fn main()->unit!{io,fs}{unwrap(file_write_text("executed","once"));'), newline="\n")
        self.scaffold();checked=self.cli('task','task.json','--kind','check');self.assertTrue(checked['ok']);self.assertFalse((self.root/'.nex/build').exists())
        directory=self.base/'run';result=self.run_task(directory);self.assertTrue(result['ok']);self.assertFalse((self.root/'executed').exists())
        receipt=json.loads((directory/'receipt.json').read_text());row=receipt['checks'][0];self.assertFalse(row['application_execution'])
        package=directory/row['package'];report=json.loads((package/'project.json').read_text());self.assertFalse(report['application_execution'])
        app=package/'apps/app';metadata=json.loads((app/'application.json').read_text());self.assertEqual(sum('owned_image_kind' in r for r in metadata['files'].values()),2)
        self.assertTrue((app/'THIRD_PARTY_NOTICES.txt').is_file());self.assertFalse(list((directory/'inputs').rglob('__pycache__')))
        moved=self.base/'moved package % 🧠';shutil.copytree(package,moved,symlinks=True);shutil.rmtree(self.root)
        files=self.base/'files';files.mkdir();p=subprocess.run([str(moved/'apps/app'/native_packaging.APP)],cwd='/',
            env=native_packaging.deployed_environment(NEX_FILES_ROOT=str(files),NEX_FILES_WRITE='1'),capture_output=True,text=True,timeout=30)
        self.assertEqual((p.returncode,p.stdout),(0,'42 🧠\n'),p.stderr);self.assertEqual((files/'executed').read_text(),'once')
        replay=self.cli('task',directory/'receipt.json','--kind','replay','--directory',self.base/'replayed',cwd=self.base,timeout=600)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],result['programs'])
    def test_web_package_retains_notices_and_only_reachable_client_code(self):
        (self.root/'browser').mkdir();(self.root/'browser/main.nex').write_text('''module browser;import "std/web.nex" as web;import "../core/value.nex" as c;
client fn initial()->i64{return c::make(40)(2);}client fn title()->str{return "Package task";}
client fn update(s:i64,e:web::Event)->i64{return s+1;}
client fn view(s:i64)->web::View{return web::element("main",[],[],[web::text(str(s))]);}''', newline="\n")
        core=self.root/'core/value.nex';core.write_text(core.read_text()+'\npub server fn secret()->str{return "PACKAGE_TASK_SERVER_SENTINEL";}\n', newline="\n")
        self.architecture['components']['browser']={'kind':'web','root':'browser','entry':'browser/main.nex','dependencies':{'core':'source'}};self.save_architecture()
        self.scaffold('browser','web');directory=self.base/'web-run';self.assertTrue(self.run_task(directory)['ok'])
        package=directory/'artifacts/package/package';report=json.loads((package/'project.json').read_text());self.assertEqual([c['component'] for c in report['components']],['browser'])
        dist=package/'web/browser';self.assertTrue((dist/'index.html').is_file());self.assertTrue((dist/'THIRD_PARTY_NOTICES.txt').is_file())
        for p in dist.rglob('*'):
            if p.is_file():self.assertNotIn(b'PACKAGE_TASK_SERVER_SENTINEL',p.read_bytes())
    def test_source_tasks_and_configuration_overrides_cannot_select_packages(self):
        task=self.scaffold();task['programs'][0].pop('project');(self.root/'task.json').write_text(json.dumps(task), newline="\n")
        self.assertEqual(self.cli('task','task.json','--kind','check',ok=False)['code'],'E_TASK')
        task=self.scaffold();task['checks'][0]['profile']='release';(self.root/'task.json').write_text(json.dumps(task), newline="\n")
        self.assertEqual(self.cli('task','task.json','--kind','check',ok=False)['code'],'E_TASK')
        self.assertFalse((self.root/'.nex/build').exists())

    def test_server_package_retains_host_binary_and_build_only_evidence(self):
        (self.root/'service').mkdir();(self.root/'service/main.nex').write_text('''module service;import "std/http.nex" as http;
server fn handle(request:http::Request)->http::Response{return http::json_response(200,"42");}''', newline="\n")
        self.architecture['components']['service']={'kind':'server','root':'service','entry':'service/main.nex'};self.save_architecture()
        task=self.scaffold('service','server');doctor=self.cli('doctor')
        roots=native_packaging.Packaging.library_inputs(self,[Path(doctor[k]) for k in ('native_sqlite_library','native_openssl_ssl','native_openssl_crypto')])
        pin=self.pin_notices(task,roots);directory=self.base/'server-run';self.assertTrue(self.run_task(directory)['ok'])
        package=directory/'artifacts/package/package';report=json.loads((package/'project.json').read_text())
        self.assertEqual([(c['component'],c['kind']) for c in report['components']],[('service','server')]);self.assertFalse(report['application_execution'])
        app=json.loads((package/'apps/service/application.json').read_text());self.assertEqual(app['kind'],'http_server');self.assertFalse(app['execution_verified'])
        self.assertIn('task-fixture-inputs',[c['name'] for c in app['components']]);self.assertTrue((directory/'inputs/package-notices/package/licenses/0.txt').is_file())
        if os.name=='nt':
            self.assertEqual({v['name'] for v in app['static_link_inputs']},{'libsqlite3.a','libssl.a','libcrypto.a'})
            self.assertTrue(all(v['component']=='task-fixture-inputs' for v in app['static_link_inputs']))
        shutil.rmtree(self.root)
        replay=self.cli('task',directory/'receipt.json','--kind','replay','--directory',self.base/'server-replayed',cwd=self.base,timeout=600)
        self.assertTrue(replay['ok']);self.assertEqual(replay['checks'][0]['notices_hash'],pin['inputs_hash'])

    def test_notice_inspector_is_readonly_and_changed_or_escaping_licenses_are_rejected(self):
        task=self.scaffold();self.pin_notices(task,[self.root/'core/value.nex']);self.assertFalse((self.root/'.nex').exists())
        self.assertTrue(self.cli('task','task.json','--kind','check')['ok'])
        (self.root/'fixture-license.txt').write_text('Changed after review', newline="\n")
        self.assertEqual(self.cli('task','task.json','--kind','check',ok=False)['code'],'E_TASK_NOTICES');self.assertFalse((self.root/'.nex/build').exists())
        outside=self.base/'outside.txt';outside.write_text('Not a project input', newline="\n")
        catalogue=self.root/'notices.json';data=json.loads(catalogue.read_text());data['components'][0]['license_files']=['../outside.txt'];catalogue.write_text(json.dumps(data), newline="\n")
        self.assertEqual(self.cli('task','notices.json','--kind','notices',ok=False)['code'],'E_TASK_NOTICES')
        for malformed in ([],{'schema':'nex.sdk-notices/1','components':[None]}):
            catalogue.write_text(json.dumps(malformed), newline="\n");self.assertEqual(self.cli('task','notices.json','--kind','notices',ok=False)['code'],'E_TASK_NOTICES')

if __name__=='__main__':unittest.main()
