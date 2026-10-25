"""Strict workload data and real supervised native server observations."""
import copy,hashlib,importlib.util,json,os,signal,subprocess,sys,time,unittest
from pathlib import Path
import support as harness
import source_ffi as ffi_fixture

HELPER=harness.REPO/'tools/server_workload.py'
spec=importlib.util.spec_from_file_location('nex_workload_helper',HELPER)
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)

def definition():
    return {'schema':'nex.server-workload/1','requests':[{'path':'/api/compute','expect':{'status':200,'text':'4704 🧠'}}],
        'phases':[{'concurrency':1,'iterations':2},{'concurrency':4,'iterations':3}],'warmup':2,
        'authorization_env':'NEX_TEST_WORKLOAD_TOKEN'}

def assert_json_text_excludes(test,value,marker):
    # Numeric observations may contain the same digits as the response body.
    if isinstance(value,str):test.assertNotIn(marker,value)
    elif isinstance(value,dict):
        for key,item in value.items():
            assert_json_text_excludes(test,key,marker)
            assert_json_text_excludes(test,item,marker)
    elif isinstance(value,list):
        for item in value:assert_json_text_excludes(test,item,marker)

def project_fixture(self):
    for name in ['core','server']:(self.root/name).mkdir()
    (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.23','entry':'server/main.nex'}))
    (self.root/'core/value.nex').write_text('''module workload::core;
pub fn calculate(seed:i64)->str{
 let offset:fn(i64)->i64=fn(x:i64)->i64{return seed+x;};
 var total:i64=0;var i:i64=0;
 while i<64{total=total+offset(i);i=i+1;}
 return str(total)+" 🧠";
}
''')
    (self.root/'server/main.nex').write_text('''module workload::service;
import "std/http.nex" as http;import "../core/value.nex" as core;
server fn handle(request:http::Request)->http::Response{
 let answer:str=core::calculate(42);
 if request.path=="/api/fail"{assert(false);}
 return http::text_response(200,answer);
}
''')
    (self.root/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'measured',
        'configurations':{'measured':{'profile':'profile'}},'components':{
        'core':{'kind':'shared_library','root':'core','entry':'core/value.nex','entry_function':'calculate'},
        'server':{'kind':'server','root':'server','entry':'server/main.nex','dependencies':{'core':'dynamic'}}}}))

class Protocol(unittest.TestCase):
    def test_payload_exclusion_checks_text_without_numeric_latency_collisions(self):
        metrics={'schema':'nex.server-workload-result/1','authorization_values_captured':False,
            'request_payloads_captured':False,'phases':[{'duration_ns':1047042,'requests_per_second':4704.25,
                'latency_ns':{'min':4704,'p50':1047042},'samples_ns':[4704,1047042]}],'error':None}
        assert_json_text_excludes(self,metrics,'4704')
        # Keep the original substring criterion for every textual key/value,
        # including nested body fields and a wrongly stringified observation.
        for captured in [{'body':'4704 🧠'},{'phases':[{'response':{'body':'prefix4704suffix'}}]},
            {'4704':0},{'nested':[{'4704 🧠':False}]},{'samples':['4704']},{'duration_ns':'1047042'}]:
            with self.subTest(captured=captured):
                with self.assertRaises(AssertionError):assert_json_text_excludes(self,captured,'4704')

    def test_bounds_strict_utf8_and_no_executable_or_header_authority(self):
        valid=definition();raw=json.dumps(valid,ensure_ascii=False).encode();normalized,plan=helper.inspect(raw)
        self.assertEqual(plan['total_requests'],16);self.assertEqual(plan['sha256'],hashlib.sha256(raw).hexdigest())
        self.assertEqual(normalized['requests'][0]['expect']['text'],'4704 🧠')
        for malformed in [b'{}',b'\xff',b'{"schema":"a","schema":"b"}',b'{"x":NaN}',b'{"x":1.5}',b'{"x":123456789012345678901}',b'{"x":"\\ud800"}',b' '*1048577]:
            with self.subTest(malformed=malformed[:64]):
                with self.assertRaises(helper.WorkloadError):helper.inspect(malformed)
        mutations=[lambda x:x.update(executable='/bin/echo'),lambda x:x.update(environment={'TOKEN':'secret'}),
            lambda x:x['requests'][0].update(headers={'Authorization':'secret'}),lambda x:x['requests'][0].update(path='https://external.test/'),
            lambda x:x['requests'][0].update(path='//external.test/'),lambda x:x['requests'][0].update(path='/api/a\r\nX:bad'),
            lambda x:x['requests'][0].update(content_type='text/plain\nX:bad'),lambda x:x['phases'][0].update(concurrency=True),
            lambda x:x['phases'][0].update(iterations=0),lambda x:x['phases'][0].update(concurrency=65),
            lambda x:x['phases'][0].update(iterations=4096),lambda x:x['requests'][0]['expect'].update(status=600),
            lambda x:x['requests'][0]['expect'].update(sha256='0'*64),lambda x:x.update(authorization_env='A=B')]
        for mutate in mutations:
            data=copy.deepcopy(valid);mutate(data)
            with self.subTest(data=data):
                with self.assertRaises(helper.WorkloadError):helper.inspect(json.dumps(data).encode())

    def test_exact_total_request_limit_includes_warmup_and_each_definition(self):
        value=definition();value.update(phases=[{'concurrency':64,'iterations':64}],warmup=0)
        self.assertEqual(helper.inspect(json.dumps(value).encode())[1]['total_requests'],4096)
        value['warmup']=1
        with self.assertRaises(helper.WorkloadError):helper.inspect(json.dumps(value).encode())
        value['warmup']=0;value['requests']*=2
        with self.assertRaises(helper.WorkloadError):helper.inspect(json.dumps(value).encode())

class Launcher(harness.ToolchainCase):
    def test_readonly_check_does_not_read_credentials_execute_or_write(self):
        data=self.root/'workload.json';data.write_text(json.dumps(definition()))
        environment={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};environment.pop('NEX_TEST_WORKLOAD_TOKEN',None)
        p=subprocess.run([sys.executable,str(HELPER),'--workload',str(data),'--check'],capture_output=True,text=True,env=environment,timeout=5)
        self.assertEqual(p.returncode,0,p.stderr);self.assertEqual(json.loads(p.stdout)['total_requests'],16)
        self.assertEqual({p.name for p in self.root.iterdir()},{'workload.json'})
        result=self.root/'never-created.json'
        p=subprocess.run([sys.executable,str(HELPER),'--workload',str(data),'--result',str(result),'--','/usr/bin/true'],capture_output=True,text=True,env=environment,timeout=5)
        self.assertNotEqual(p.returncode,0);self.assertEqual(json.loads(p.stderr)['code'],'E_SERVER_WORKLOAD_AUTH');self.assertFalse(result.exists())
        self.assertFalse((self.root/'.nex').exists())

    def test_real_dynamic_server_success_failure_profile_identity_and_owned_cleanup(self):
        project_fixture(self)
        built=self.cli('project','--kind','build','--component','server',timeout=240)
        artifact=next(row for row in built['artifacts'] if row['component']=='server')
        compilation=json.loads((Path(artifact['artifact']).parent/'compilation.json').read_text())
        self.assertEqual(len(compilation['owned_images']),2)
        self.assertFalse(any(row['identity'].startswith('workload::core::') for row in compilation['units']))
        token=self.cli('token','--auth',self.root/'auth.json','--user','bench')['token']
        cases=[('success',definition(),True),('unexpected',definition(),False),('caught-trap',definition(),True)]
        cases[1][1]['requests'][0]['expect']['text']='different';cases[1][1]['phases']=[{'concurrency':1,'iterations':1}];cases[1][1]['warmup']=0
        cases[2][1]['requests']=[{'path':'/api/fail','expect':{'status':500}}];cases[2][1]['phases']=[{'concurrency':4,'iterations':2}];cases[2][1]['warmup']=0
        for name,workload,ok in cases:
            with self.subTest(name=name):
                path=self.root/(name+'-workload.json');path.write_text(json.dumps(workload));output=self.root/(name+'-result.json');profile=self.root/(name+'-profile.json')
                p=subprocess.run([sys.executable,str(HELPER),'--workload',str(path),'--expected-hash',hashlib.sha256(path.read_bytes()).hexdigest(),
                    '--result',str(output),'--',artifact['artifact'],'--auth',str(self.root/'auth.json'),'--database',str(self.root/'state.sqlite'),'--workers','4'],
                    capture_output=True,text=True,timeout=30,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NEX_TEST_WORKLOAD_TOKEN':token,
                    'NEX_PROFILE_OUTPUT':str(profile),'NEX_TRACY':'0'})
                result=json.loads(output.read_text());self.assertEqual(p.returncode,0 if ok else 1,p.stdout+p.stderr);self.assertEqual(result['ok'],ok)
                self.assertNotIn(token,output.read_text());self.assertEqual(result['server_exit_code'],0)
                raw=json.loads(profile.read_text());self.assertEqual(raw['build']['build_key'],artifact['build_key'])
                self.assertTrue(all(pool['live']==0 and pool['allocations']==pool['frees'] for pool in raw['memory']))
                if ok:
                    expected=helper.inspect(path.read_bytes())[1]['total_requests'];self.assertEqual(result['completed_requests'],expected);self.assertTrue(result['all_expectations_met'])
                    measured={row['name']:row for row in raw['functions']}
                    self.assertEqual(measured['workload::core::calculate']['calls'],expected)
                    self.assertEqual(measured['workload::service::handle']['calls'],expected)
                    if name=='caught-trap':self.assertEqual(measured['workload::service::handle']['aborted'],expected)
                else:self.assertEqual(result['error']['code'],'E_SERVER_WORKLOAD_RESPONSE')
        self.assertFalse((self.root/'.nex/graph.db').exists())

class PublicProject(harness.ToolchainCase):
    def setUp(self):
        super().setUp();project_fixture(self)
        self.workload=self.root/'workload.json';self.workload.write_text(json.dumps(definition()))

    def action(self,kind,*args,**kwargs):
        result=self.cli('project','--kind',kind,'--component','server','--workload',self.workload,'--json',*args,machine=False,timeout=240,**kwargs)
        return json.loads(result.stdout)

    def test_readonly_plan_matches_helper_and_rejects_invalid_inputs_before_source_tools_or_cache(self):
        environment={**os.environ};environment.pop('NEX_TEST_WORKLOAD_TOKEN',None)
        plan=self.action('plan',env=environment)['server_workload']
        expected=helper.inspect(self.workload.read_bytes())[1]
        self.assertEqual({key:plan[key] for key in expected},expected)
        self.assertEqual(plan['runner_sha256'],hashlib.sha256(HELPER.read_bytes()).hexdigest())
        self.assertEqual(Path(plan['definition_file']),self.workload)
        self.assertFalse((self.root/'.nex').exists())
        (self.root/'server/main.nex').write_text('This source must never be parsed.')
        marker=self.root/'driver-called';driver=self.root/'unreachable-driver'
        driver.write_text('#!/usr/bin/env python3\nfrom pathlib import Path\nPath('+repr(str(marker))+').touch()\n');driver.chmod(0o755)
        environment['NEX_CLANG']=str(driver)
        invalid=[b'{}',b'\xff',b'{"a":1,"a":2}',b' '*1048577]
        for change in [lambda x:x.update(authorization_env=None),lambda x:x['requests'][0]['expect'].update(sha256=None),
            lambda x:x['phases'][0].update(concurrency=True),lambda x:x['phases'][0].update(concurrency=1.0),
            lambda x:x.update(command=['touch','owned']),lambda x:x['requests'][0].update(path='//elsewhere.test/')]:
            value=definition();change(value);invalid.append(json.dumps(value).encode())
        for data in invalid:
            self.workload.write_bytes(data)
            self.assertEqual(self.action('plan',env=environment,ok=False)['code'],'E_SERVER_WORKLOAD')
        self.workload.write_text(json.dumps(definition()))
        self.assertEqual(self.action('profile',env={**environment,'NEX_TEST_WORKLOAD_TOKEN':''},ok=False)['code'],'E_SERVER_WORKLOAD_AUTH')
        self.assertEqual(self.action('profile','--','--port','9999',env=environment,ok=False)['code'],'E_SERVER_WORKLOAD')
        self.assertEqual(self.cli('project','--workload','',ok=False)['code'],'E_OPTION')
        alias=self.root/'alias.json';alias.symlink_to(self.workload)
        self.assertEqual(self.cli('project','--workload',alias,ok=False)['code'],'E_SERVER_WORKLOAD')
        self.assertFalse(marker.exists());self.assertFalse((self.root/'.nex').exists())

    def test_profile_final_dynamic_server_and_failed_expectations(self):
        token=self.cli('token','--auth',self.root/'auth.json','--user','bench')['token']
        env={'NEX_TEST_WORKLOAD_TOKEN':token}
        plan=self.action('plan');output=self.root/'profile.json'
        result=self.action('profile','--profile-output',output,'--','--auth',self.root/'auth.json','--database',self.root/'state.sqlite','--workers','4',env=env)
        self.assertEqual(result['plan']['server_workload'],plan['server_workload'])
        profile=result['observation'];metrics=profile['workload'];self.assertTrue(metrics['ok']);self.assertEqual(metrics['completed_requests'],16)
        self.assertEqual(metrics['definition_sha256'],plan['server_workload']['sha256'])
        self.assertEqual(metrics['runner_sha256'],plan['server_workload']['runner_sha256'])
        self.assertEqual([p['requests'] for p in metrics['phases']],[2,12]);self.assertEqual(metrics['warmup_completed'],2)
        artifact=next(row for row in result['artifacts'] if row['component']=='server')
        self.assertEqual(profile['build_key'],artifact['build_key']);self.assertEqual(len(json.loads(Path(artifact['compilation']).read_text())['owned_images']),2)
        self.assertTrue(all(row['node_id'] is None and row['identity_scope']=='captured_project' for row in profile['functions']))
        functions={row['name']:row for row in profile['functions']}
        for name in ['workload::core::calculate','workload::service::handle']:self.assertEqual(functions[name]['calls'],16)
        saved=json.loads(output.read_text());self.assertEqual(saved['workload'],metrics)
        self.assertTrue(all(pool['live']==0 and pool['allocations']==pool['frees'] for pool in saved['memory']))
        self.assertNotIn(token,output.read_text());self.assertNotIn(token,json.dumps(result));assert_json_text_excludes(self,metrics,'4704')
        value=definition();value['requests'][0]['expect']['text']='different';value['phases']=[{'concurrency':1,'iterations':1}];value['warmup']=0
        self.workload.write_text(json.dumps(value))
        failed=self.action('profile','--','--auth',self.root/'auth.json','--database',self.root/'state.sqlite',env=env,ok=False)
        self.assertEqual(failed['exit_code'],1);metrics=failed['observation']['workload'];self.assertFalse(metrics['ok']);self.assertEqual(metrics['error']['code'],'E_SERVER_WORKLOAD_RESPONSE')
        self.assertEqual(metrics['server_exit_code'],0);self.assertFalse((self.root/'.nex/graph.db').exists())

    def test_operator_change_during_measurement_rejects_the_reviewed_workload(self):
        value=definition();value['phases']=[{'concurrency':1,'iterations':512}];value['warmup']=0
        self.workload.write_text(json.dumps(value))
        token=self.cli('token','--auth',self.root/'auth.json','--user','bench')['token']
        output=self.root/'must-not-accept.json';ambient=self.root/'ambient';ambient.mkdir()
        process=subprocess.Popen([harness.NEX,'project','--kind','profile','--component','server','--workload',str(self.workload),
            '--profile-output',str(output),'--events','0','--timeout','60','--json','--','--auth',str(self.root/'auth.json'),
            '--database',str(self.root/'state.sqlite')],cwd=self.root,env={**os.environ,'NEX_TEST_WORKLOAD_TOKEN':token,'TMPDIR':str(ambient)},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            deadline=time.monotonic()+120;started=False
            while process.poll() is None and time.monotonic()<deadline:
                if any('NEX server http://' in path.read_text() for path in ambient.glob('nex-profile-*/logs/stdout')):
                    started=True;break
                time.sleep(.01)
            if not started:
                out,err=process.communicate(timeout=10);self.fail('did not observe real listener: '+out+err)
            self.workload.write_text('{}')
            out,err=process.communicate(timeout=90);self.assertNotEqual(process.returncode,0,out+err)
            self.assertEqual(json.loads(out)['code'],'E_PROJECT_INPUT_CHANGED',out+err)
            self.assertFalse(output.exists());self.assertEqual(list(ambient.iterdir()),[])
            self.assertFalse((self.root/'.nex/graph.db').exists())
        finally:
            if process.poll() is None:process.send_signal(signal.SIGTERM);process.communicate(timeout=15)

class Supervision(harness.ToolchainCase):
    program=ffi_fixture.SourceFFI.program

    def test_timeout_and_interrupt_stop_native_server_and_forked_foreign_descendant(self):
        self.marker=self.root/'heartbeat';children=self.root/'children'
        self.env={'NEX_SOURCE_FFI_MARKER':str(self.marker),'NEX_WORKLOAD_CHILDREN':str(children)}
        original=ffi_fixture.C
        loop=r'''mark('C');pid_t child=fork();if(child==0){for(;;){mark('H');struct timespec delay={0,20000000};nanosleep(&delay,0);}}
const char *path=getenv("NEX_WORKLOAD_CHILDREN");if(path){int f=open(path,O_WRONLY|O_CREAT|O_TRUNC,0600);if(f>=0){char line[128];int n=snprintf(line,sizeof(line),"%ld %ld %ld\n",(long)getpid(),(long)getpgrp(),(long)child);if(n>0&&n<(int)sizeof(line))write(f,line,n);close(f);}}for(;;)pause();'''
        source='''module supervised;
import "std/http.nex" as http;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server fn handle(request:http::Request)->http::Response!{ffi}{return http::text_response(200,str(echo(42)));}
'''
        try:
            ffi_fixture.C='#define _POSIX_C_SOURCE 200809L\n'+original.replace('#include <fcntl.h>','#include <fcntl.h>\n#include <stdio.h>\n#include <time.h>').replace("mark('C');",loop,1)
            self.program(source,{'echo':'echo'})
        finally:ffi_fixture.C=original
        (self.root/'app').mkdir();self.file.rename(self.root/'app/main.nex')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.23','entry':'app/main.nex'}))
        (self.root/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'measured',
            'configurations':{'measured':{'profile':'profile'}},'components':{'app':{'kind':'server','root':'app','entry':'app/main.nex'}}}))
        workload=self.root/'workload.json';workload.write_text(json.dumps({'schema':'nex.server-workload/1',
            'requests':[{'path':'/api/wait','expect':{'status':200}}],'phases':[{'concurrency':1,'iterations':1}],
            'request_timeout_ms':5000,'authorization_env':'NEX_TEST_WORKLOAD_TOKEN'}))
        token=self.cli('token','--auth',self.root/'auth.json','--user','bench')['token'];self.env['NEX_TEST_WORKLOAD_TOKEN']=token
        original_graph=harness.database_rows(self.root/'.nex/graph.db')
        self.cli('project','--kind','build',timeout=240)
        ambient=self.root/'ambient';ambient.mkdir();self.env['TMPDIR']=str(ambient)
        command=[harness.NEX,'project','--kind','profile','--workload',str(workload),'--foreign',str(self.host),'--json']
        runtime=['--','--auth',str(self.root/'auth.json'),'--database',str(self.root/'state.sqlite')]
        for mode in ['timeout','interrupt']:
            children.unlink(missing_ok=True);self.marker.unlink(missing_ok=True)
            process=subprocess.Popen([*command,'--timeout','3' if mode=='timeout' else '30',*runtime],cwd=self.root,
                env={**os.environ,**self.env},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            try:
                deadline=time.monotonic()+30
                while not children.exists() and process.poll() is None and time.monotonic()<deadline:time.sleep(.02)
                if not children.exists():
                    out,err=process.communicate(timeout=10);self.fail(out+err+'; events='+repr(self.marker.read_bytes() if self.marker.exists() else b''))
                parent,group,child=map(int,children.read_text().split());self.assertNotEqual(parent,group)
                self.assertNotEqual(child,group)
                if mode=='interrupt':process.send_signal(signal.SIGINT)
                out,err=process.communicate(timeout=15)
                self.assertNotEqual(process.returncode,0,out+err)
                self.assertEqual(json.loads(out)['code'],'E_PROFILE_TIMEOUT' if mode=='timeout' else 'E_PROFILE_INTERRUPTED',out+err)
                first=self.marker.read_bytes();time.sleep(.2);self.assertEqual(self.marker.read_bytes(),first,'native descendant survived supervision')
                self.assertEqual(list(ambient.iterdir()),[],'owned profiler/workload/foreign temporaries survived')
            finally:
                if process.poll() is None:process.send_signal(signal.SIGTERM);process.communicate(timeout=15)
                if children.exists():
                    group=int(children.read_text().split()[1])
                    try:os.killpg(group,signal.SIGKILL)
                    except ProcessLookupError:pass
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),original_graph)
        # The ordinary source profiler uses the same supervisor and owned native
        # temporary root, without the workload launcher or HTTP adapter.
        (self.root/'app/main.nex').write_text('module supervised;server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo",'+json.dumps(self.pin)+');server fn main()->unit!{ffi}{let value:i64=echo(42);}')
        children.unlink();self.marker.unlink()
        process=subprocess.Popen([harness.NEX,'profile','--timeout','3','--foreign',str(self.host),'--json'],cwd=self.root,
            env={**os.environ,**self.env},stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        try:
            out,err=process.communicate(timeout=180);self.assertNotEqual(process.returncode,0,out+err)
            self.assertEqual(json.loads(out)['code'],'E_PROFILE_TIMEOUT',out+err);self.assertTrue(children.exists())
            first=self.marker.read_bytes();time.sleep(.2);self.assertEqual(self.marker.read_bytes(),first)
            self.assertEqual(list(ambient.iterdir()),[])
        finally:
            if process.poll() is None:process.send_signal(signal.SIGTERM);process.communicate(timeout=15)
            if children.exists():
                try:os.killpg(int(children.read_text().split()[1]),signal.SIGKILL)
                except ProcessLookupError:pass

if __name__=='__main__':unittest.main()
