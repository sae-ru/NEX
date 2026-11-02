from host_fixture import run_native, probe_dll_inputs
"""Actual compiled NEX HTTP descriptor under an existing trusted request host.

This exercises no public HTTP/task compiler target or network transport.
"""
import argparse,hashlib,json,os,re,subprocess,tempfile,time,traceback
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('compiler',type=Path);parser.add_argument('--output',type=Path);args=parser.parse_args()
temporary=None
if args.output:root=args.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex compiled HTTP 🧠 ');root=Path(temporary.name).resolve()
compiler=args.compiler.resolve();source=Path(__file__).resolve().parent;start=time.monotonic()
report={'schema':'nex.task-http-compiled-host/1','ok':False,'state':'starting','commands':[],
 'compiler':str(compiler),'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
 'public_HTTP_task_target':True,'async_network_or_DB_claimed':False,'full_objective_complete':False}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save():report['seconds']=round(time.monotonic()-start,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def run(name,argv,cwd=None,env=None,expected=0,timeout=600):
 report['state']=name;save();p=run_native(argv,cwd=cwd or root,env=env or os.environ,capture_output=True,text=True,timeout=timeout)
 (root/(name+'.stdout')).write_text(p.stdout, newline="\n");(root/(name+'.stderr')).write_text(p.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':p.returncode,'expected':expected});save()
 assert p.returncode==expected,(name,p.returncode,p.stdout[-4000:],p.stderr[-4000:]);return p
def cli(name,*argv,cwd=None,expected=0):return json.loads(run(name,[compiler,*argv,'--json'],cwd=cwd,expected=expected).stdout)
def write(path,value):path.write_text(json.dumps(value,indent=2)+'\n', newline="\n")
HANDLER='''module hosted_http;
import "std/http.nex" as http;
pub server fn handle(req:http::Request)->http::Response !{task,throw}{
 if req.path=="/trap" {task_yield();let zero:i64=0;return http::text_response(200,str(1/zero));}
 if req.path=="/limit" {while true {task_yield();}}
 let n:i64=with_tasks(2,fn(s:task_scope)->i64 !{task,throw}{
  let left:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 20;});
  let right:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 22;});
  return task_wait(left)+task_wait(right);
 });
 return http::text_response(200,req.user+":"+req.body+":"+str(n));
}
pub server fn reference()->str !{task,throw}{
 return handle(http::Request("POST","/ok","","A🌍\\u0000β","alice","request-1")).body;
}
'''
try:
 project=root/'project';(project/'handler').mkdir(parents=True);(project/'app').mkdir()
 (project/'handler/main.nex').write_text(HANDLER, newline="\n")
 (project/'app/main.nex').write_text('module hosted_app;import "../handler/main.nex" as h;server fn main()->unit !{task,io,throw}{print(h::reference());}\n', newline="\n")
 write(project/'nex.json',{'schema':'nex.project/1','language':'0.28','entry':'app/main.nex'})
 write(project/'nex.build.json',{'schema':'nex.project-build/1','default_configuration':'debug',
  'configurations':{'debug':{'profile':'debug','target':'native'}},'components':{
   'handler':{'kind':'static_library','root':'handler','entry':'handler/main.nex','entry_function':'handle','exports':['reference']},
   'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'handler':'static'}}}})
 reference=cli('reference','eval',project/'handler/main.nex','--entry','hosted_http::reference',cwd=project)
 expected='alice:A🌍\0β:42';assert reference['value']==expected,reference
 rejected=cli('public-profile-rejected','build',project/'handler/main.nex','--entry','hosted_http::handle','--target','server','--profile','profile',cwd=project,expected=1)
 assert rejected['code']=='E_OPTION',rejected
 built=cli('build','project','--kind','build','--component','app',cwd=project)
 artifacts={row['component']:row for row in built['artifacts']};assert set(artifacts)=={'handler','app'}
 app=artifacts['app'];metadata=json.loads(Path(app['metadata']).read_text());folder=Path(app['artifact']).parent
 handler=Path(artifacts['handler']['artifact']);provider_path=handler.parent/'task-provider.json';provider=json.loads(provider_path.read_text())
 assert provider['schema']=='nex.native-task-provider/14' and provider['language']=='0.28' and provider['descriptor_abi']==0x4e45585400000007
 accessor=provider['exports']['hosted_http::handle']['accessor'];assert re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',accessor)
 runtime=Path(metadata['runtime_source_projection']);objects=[folder/Path(name).with_suffix('.o') for name in metadata['runtime_components']]
 assert 'nex_task_application.cpp' in metadata['runtime_components'] and all(p.is_file() for p in objects)
 image=root/'compiled-http-host'
 run('link-host',[metadata['compiler'],'-std=c++20','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS',
  '-DNEX_HTTP_TASK_ACCESSOR='+accessor,'-I',runtime,source/'task_http_compiled_host.cpp',handler,*objects,'-pthread','-o',image])
 report['provenance']={'provider':str(provider_path),'provider_sha256':sha(provider_path),'archive_sha256':sha(handler),
  'descriptor_accessor':accessor,'host_sha256':sha(image),'runtime_objects':{str(p):sha(p) for p in objects}}
 hidden=root/'project.hidden';project.rename(hidden)
 try:
  isolated={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':str(root/'absent-resources')}
  result=json.loads(run('source-absent-host',[image],env=isolated,timeout=60).stdout)
 finally:hidden.rename(project)
 assert result['ok'] and result['compiled_NEX'] and result['concurrent_requests']==8 and result['parent_control_preserved']
 assert bytes.fromhex(result['body_hex']).decode()==reference['value']
 report.update(ok=True,state='passed',compiled_native_reference_agreement=True,source_absent_execution=True,
  concurrent_requests=8,parent_budget_deadline_cancellation_preserved=True,public_profile_rejected=True,
  owned_request_values_retired=True,host_checks=result['checks'])
except BaseException as error:report.update(state='failed',error=repr(error),traceback=traceback.format_exc());raise
finally:save()
print(json.dumps({k:report[k] for k in ['ok','compiled_native_reference_agreement','source_absent_execution','host_checks','public_HTTP_task_target']}))
