"""Pinned workload tasks, synthetic server state, budgets and captured replay."""
import copy,hashlib,json,os,shutil,signal,subprocess,time
from pathlib import Path
import unittest
import support as harness
import server_workload as workload_fixture
import source_ffi as ffi_fixture

class TaskWorkloads(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.restore=None;self.outer=self.root;self.root=self.outer/'project';self.root.mkdir()
        workload_fixture.project_fixture(self)
        self.workload=self.root/'workload.json';self.definition=workload_fixture.definition();self.save_workload()
        self.path=self.root/'task.json'

    def tearDown(self):
        try:
            if self.restore:self.restore()
        finally:super().tearDown()

    def save_workload(self):self.workload.write_text(json.dumps(self.definition,ensure_ascii=False))

    def profile(self,identifier='measure'):
        return {'id':identifier,'program':'app','kind':'profile','target':'server','configuration':'measured',
            'entry':'workload::service::handle','scenario':'fresh authenticated server','workload':'workload.json',
            'workload_hash':hashlib.sha256(self.workload.read_bytes()).hexdigest(),'server_workers':4,
            'budget':{'max_peak_handles':'100000','max_calls':{'workload::core::calculate':'16'}},'timeout_seconds':180}

    def scaffold(self):
        task=self.cli('task','nex.build.json','--kind','init','--component','server','--configuration','measured',timeout=120)
        task['checks']=[];task['requirements']=[];self.add(task,self.profile());return task

    def add(self,task,check):
        task['checks'].append(check);task['requirements'].append({'id':check['id'],'text':'Reviewed local HTTP workload and native budget',
            'targets':[check['target']],'checks':[check['id']],'bindings':[{'program':'app','kind':'function','symbol':'workload::service::handle'}]})

    def save(self,task):self.path.write_text(json.dumps(task))
    def task(self,kind='run',*args,**kwargs):return self.cli('task',self.path,'--kind',kind,*args,timeout=600,**kwargs)

    def test_check_pins_raw_bytes_without_credentials_or_native_processes(self):
        self.save(self.scaffold());environment={'NEX_TEST_WORKLOAD_TOKEN':'INHERITED_VALUE_IS_NOT_A_TASK_CREDENTIAL'}
        checked=self.task('check',env=environment);self.assertTrue(checked['ok']);self.assertEqual(checked['checks'][0]['status'],'ready')
        summary=checked['workloads']['measure'];self.assertEqual(summary['definition_sha256'],hashlib.sha256(self.workload.read_bytes()).hexdigest())
        self.assertEqual(summary['planned_requests'],16);self.assertFalse((self.root/'.nex/build').exists())
        self.assertFalse(list(self.outer.glob('**/auth.json')));self.assertNotIn(environment['NEX_TEST_WORKLOAD_TOKEN'],json.dumps(checked))
        self.workload.write_text(self.workload.read_text()+'\n')
        self.assertEqual(self.task('check',ok=False)['code'],'E_TASK_WORKLOAD');self.assertFalse((self.root/'.nex/build').exists())

    def test_real_dynamic_profile_and_readonly_source_deleted_replay_use_fresh_private_state(self):
        (self.outer/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'ancestor.nex'}))
        (self.outer/'ancestor.nex').write_text('module ancestor;fn main()->i64{return 77;}')
        self.cli('check',self.outer/'ancestor.nex',cwd=self.outer);ancestor=harness.database_rows(self.outer/'.nex/graph.db')
        (self.root/'server/main.nex').write_text('''module workload::service;
import "std/http.nex" as http;import "../core/value.nex" as core;
server fn handle(request:http::Request)->http::Response!{db}{
 let text:str=core::calculate(42);
 if request.path=="/api/check"{
  if is_ok(store_get("seed")){return http::text_response(409,"dirty");}
  return http::text_response(200,"clean|"+request.user);
 }
 if request.path=="/api/seed"{assert(!is_ok(store_get("seed")));unwrap(store_put("seed",text));return http::text_response(200,"seeded");}
 return http::text_response(200,unwrap(store_get("seed")));
}
''')
        self.definition.update(warmup=0,phases=[{'concurrency':1,'iterations':1}],requests=[
            {'path':'/api/check','expect':{'status':200,'text':'clean|nex-task-workload'}},
            {'method':'POST','path':'/api/seed','expect':{'status':200,'text':'seeded'}},
            {'path':'/api/read','expect':{'status':200,'text':'4704 🧠'}}]);self.save_workload()
        task=self.scaffold();task['checks'][0]['budget']['max_calls']['workload::core::calculate']='3'
        second=copy.deepcopy(task['checks'][0]);second.update(id='second',server_workers=1);self.add(task,second);self.save(task)
        checked=self.task('check');ambient=self.outer/'ambient';ambient.mkdir()
        sentinel='USER_WORKLOAD_CREDENTIAL_MUST_NOT_BE_CAPTURED'
        run=self.task('run','--directory',self.outer/'original-run','--task-hash',checked['task_hash'],env={
            'TMPDIR':str(ambient),'NEX_TEST_WORKLOAD_TOKEN':sentinel})
        self.assertTrue(run['ok']);receipt=Path(run['output']);full=json.loads(receipt.read_text())
        self.assertEqual(len(full['checks']),2);self.assertEqual(list(ambient.iterdir()),[])
        for row in full['checks']:
            self.assertEqual(row['status'],'passed');self.assertFalse(row['workload_runtime']['credentials_captured']);self.assertFalse(row['workload_runtime']['database_captured'])
            profile=json.loads((receipt.parent/'artifacts'/row['id']/'profile.json').read_text())
            self.assertEqual(profile['workload']['completed_requests'],3);self.assertTrue(profile['workload']['all_expectations_met'])
            functions={f['name']:f for f in profile['functions']};self.assertEqual(functions['workload::core::calculate']['calls'],3)
            self.assertTrue(all(f['node_id'] is None and f['identity_scope']=='captured_project' for f in functions.values()))
            self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in profile['memory']))
            command=json.loads((receipt.parent/row['receipt']).read_text())['command']
            for flag in ['--auth','--database']:self.assertFalse(Path(command[command.index(flag)+1]).exists())
        index=json.loads((receipt.parent/'inputs/manifest.json').read_text());self.assertIn('inputs/workloads/measure/workload.json',index['files'])
        self.assertIn('inputs/resources/tools/server_workload.py',index['files'])
        self.assertFalse(any('auth.json' in name or 'state.sqlite' in name for name in index['files']))
        for path in (receipt.parent/'inputs').rglob('*'):
            if path.is_file():self.assertNotIn(sentinel.encode(),path.read_bytes())
        self.assertEqual(harness.database_rows(self.outer/'.nex/graph.db'),ancestor)
        original_inputs={p.relative_to(receipt.parent):p.read_bytes() for p in (receipt.parent/'inputs').rglob('*') if p.is_file()}
        shutil.rmtree(self.root)
        for path in receipt.parent.rglob('*'):
            if not path.is_symlink():path.chmod(0o555 if path.is_dir() else 0o444)
        receipt.parent.chmod(0o555)
        def writable():
            receipt.parent.chmod(0o755)
            for path in receipt.parent.rglob('*'):
                if not path.is_symlink():path.chmod(0o755 if path.is_dir() else 0o644)
        self.restore=writable
        process=subprocess.run([harness.NEX,'task',str(receipt),'--kind','replay','--directory',str(self.outer/'replayed'),'--json'],cwd=self.outer,
            capture_output=True,text=True,timeout=600)
        replay=json.loads(process.stdout)
        if process.returncode:
            saved=harness.REPO.parent/'native-083-task-workload-replay-failure-v2';saved.mkdir(exist_ok=True)
            (saved/'session.json').write_text(process.stdout);(saved/'stderr').write_text(process.stderr)
            for check in ['measure','second']:
                for part in ['logs','artifacts']:
                    base=self.outer/'replayed'/part/check
                    if base.exists():shutil.copytree(base,saved/part/check,dirs_exist_ok=True)
        self.assertEqual(process.returncode,0,{'checks':replay.get('checks'),'error':replay.get('message')})
        self.assertTrue(replay['ok']);self.assertEqual(replay['task_hash'],checked['task_hash'])
        self.assertEqual(harness.database_rows(self.outer/'.nex/graph.db'),ancestor)
        self.assertEqual({p.relative_to(receipt.parent):p.read_bytes() for p in (receipt.parent/'inputs').rglob('*') if p.is_file()},original_inputs)

    def test_request_budgets_require_hardware_and_impossible_limits_fail(self):
        task=self.scaffold();budget=task['checks'][0]['budget'];budget.update(max_p95_latency_ns='0',min_requests_per_second='18446744073709551615')
        self.save(task);self.assertEqual(self.task('check',ok=False)['code'],'E_TASK')
        doctor=self.cli('doctor');task['checks'][0]['hardware']={'cpu':'a deliberately different CPU','target':doctor['host']}
        self.save(task);probe=self.task('run',ok=False);self.assertEqual(probe['checks'][0]['status'],'unsupported')
        self.assertEqual(probe['hardware'],{'cpu':doctor['cpu'],'target':doctor['host']})
        task['checks'][0]['hardware']=probe['hardware']
        bad_definition=workload_fixture.definition();bad_definition['requests'][0]['expect']['text']='different'
        bad_definition.update(warmup=0,phases=[{'concurrency':1,'iterations':1}]);bad=self.root/'bad.json';bad.write_text(json.dumps(bad_definition))
        negative=self.profile('bad-response');negative.update(workload='bad.json',workload_hash=hashlib.sha256(bad.read_bytes()).hexdigest(),budget={'max_peak_handles':'100000'})
        self.add(task,negative)
        self.save(task);run=self.task('run',ok=False);row=run['checks'][0];self.assertEqual(row['status'],'failed')
        self.assertTrue(any(value.startswith('max_p95_latency_ns:phase') for value in row['budget_failures']))
        self.assertTrue(any(value.startswith('min_requests_per_second:phase') for value in row['budget_failures']))
        self.assertEqual(run['checks'][1]['status'],'failed')
        receipt=Path(run['output']);profile=json.loads((receipt.parent/'artifacts/bad-response/profile.json').read_text())
        self.assertEqual(profile['workload']['error']['code'],'E_SERVER_WORKLOAD_RESPONSE');self.assertEqual(profile['workload']['server_exit_code'],0)
        self.assertTrue(all(p['live']==0 and p['allocations']==p['frees'] for p in profile['memory']))
        captured=receipt.parent/'inputs/workloads/measure/workload.json';captured.write_bytes(captured.read_bytes()+b'\n')
        before=harness.database_rows(self.root/'.nex/graph.db');rejected=self.outer/'must-not-create'
        self.assertEqual(self.cli('task',receipt,'--kind','replay','--directory',rejected,ok=False)['code'],'E_TASK_INTEGRITY')
        self.assertFalse(rejected.exists());self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)

    def test_foreign_workload_timeout_and_interrupt_clean_server_state_and_forked_descendant(self):
        self.file=self.root/'server/main.nex';self.marker=self.outer/'heartbeat';children=self.outer/'children'
        self.env={'NEX_SOURCE_FFI_MARKER':str(self.marker),'NEX_WORKLOAD_CHILDREN':str(children)}
        original=ffi_fixture.C
        loop=r'''mark('C');const char *path=getenv("NEX_WORKLOAD_CHILDREN");int f=path?open(path,O_WRONLY|O_CREAT|O_EXCL,0600):-1;
if(f>=0){pid_t child=fork();if(child==0){close(f);for(;;){mark('H');struct timespec delay={0,20000000};nanosleep(&delay,0);}}
char line[128];int n=snprintf(line,sizeof(line),"%ld %ld %ld\n",(long)getpid(),(long)getpgrp(),(long)child);if(n>0&&n<(int)sizeof(line))write(f,line,n);close(f);}
if(getenv("NEX_WORKLOAD_INTERRUPT")){for(;;)pause();}
struct timespec delay={0,250000000};nanosleep(&delay,0);'''
        source='''module workload::service;import "std/http.nex" as http;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server fn handle(request:http::Request)->http::Response!{ffi}{return http::text_response(200,str(echo(42)));}
'''
        try:
            ffi_fixture.C='#define _POSIX_C_SOURCE 200809L\n'+original.replace('#include <fcntl.h>','#include <fcntl.h>\n#include <stdio.h>\n#include <time.h>').replace("mark('C');",loop,1)
            ffi_fixture.SourceFFI.program(self,source,{'echo':'echo'})
        finally:ffi_fixture.C=original
        self.definition.update(warmup=0,phases=[{'concurrency':1,'iterations':256}],requests=[{'path':'/api/wait','expect':{'status':200}}],request_timeout_ms=5000)
        self.save_workload();task=self.scaffold();measure=task['checks'].pop();task['requirements'].clear()
        build={'id':'warm-build','program':'app','kind':'build','target':'server','configuration':'measured','timeout_seconds':180};self.add(task,build)
        measure['foreign_hash']=self.cli('foreign',self.host)['hash'];measure['budget']={'max_calls':{'workload::service::handle':'1'}}
        self.add(task,measure);self.add(task,{'id':'later','program':'app','kind':'effects','target':'source','configuration':'measured',
            'symbols':['workload::service::handle'],'allowed_effects':['ffi']})
        ambient=self.outer/'ambient';ambient.mkdir();self.env['TMPDIR']=str(ambient)
        for mode in ['timeout','interrupt']:
            children.unlink(missing_ok=True);self.marker.unlink(missing_ok=True)
            measure['timeout_seconds']=30 if mode=='timeout' else 90;self.save(task)
            if mode=='interrupt':self.env['NEX_WORKLOAD_INTERRUPT']='1'
            else:self.env.pop('NEX_WORKLOAD_INTERRUPT',None)
            if mode=='timeout':
                denied=self.task('check',ok=False);self.assertEqual(denied['code'],'E_TASK_FOREIGN');self.assertFalse(self.marker.exists())
            process=subprocess.Popen([harness.NEX,'task',str(self.path),'--kind','run','--foreign',str(self.host),'--directory',str(self.outer/('run-'+mode)),'--json'],
                cwd=self.root,env={**os.environ,**self.env},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+240
                while (not children.exists() or len(children.read_text().split())!=3) and process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                if not children.exists():
                    out,err=process.communicate(timeout=10);self.fail('native callback was not reached: '+out+err)
                parent,group,child=map(int,children.read_text().split());self.assertNotEqual(parent,group);self.assertNotEqual(child,group)
                if mode=='interrupt':process.send_signal(signal.SIGINT)
                out,err=process.communicate(timeout=30);report=json.loads(out);rows={row['id']:row for row in report['checks']}
                self.assertEqual(rows['warm-build']['status'],'passed');self.assertFalse(report['ok'])
                if mode=='timeout':
                    self.assertEqual(rows['measure']['code'],'E_TASK_TIMEOUT',out+err);self.assertEqual(rows['later']['status'],'passed')
                else:
                    self.assertEqual(process.returncode,130,out+err);self.assertEqual(report['signal'],signal.SIGINT)
                    self.assertEqual(rows['measure']['status'],'interrupted');self.assertEqual(rows['later']['status'],'skipped')
                first=self.marker.read_bytes();time.sleep(.2);self.assertEqual(first,self.marker.read_bytes());self.assertEqual(list(ambient.iterdir()),[])
            finally:
                if process.poll() is None:process.send_signal(signal.SIGTERM);process.communicate(timeout=30)
                if children.exists():
                    try:os.killpg(int(children.read_text().split()[1]),signal.SIGKILL)
                    except ProcessLookupError:pass

if __name__=='__main__':unittest.main()
