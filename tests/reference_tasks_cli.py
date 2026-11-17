"""Ordinary030 owned tasks: CLI/backends, immutable exports, replay and HTTP."""
import argparse, concurrent.futures, hashlib, http.client, json, os, queue, re, subprocess, tempfile, threading
from pathlib import Path
from host_fixture import stop_server
p=argparse.ArgumentParser(description=__doc__);p.add_argument('compiler',type=Path);p.add_argument('reference',type=Path);p.add_argument('--output',type=Path);p.add_argument('--output-parent',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];compiler=a.compiler.resolve();reference=a.reference.resolve()
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-reference-tasks-cli-',dir=a.output_parent))
if a.output:out.mkdir(parents=True,exist_ok=False)
node=os.environ.get('NEX_NODE','node');tsc=os.environ.get('NEX_TSC',str(root/'web/node_modules/typescript/bin/tsc'))
sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
report={'schema':'nex.reference-tasks-cli/1','ok':False,'compiler_sha256':sha(compiler),'reference_sha256':sha(reference),'source_language':'0.30','task_ABI':'0x4e45585400000008','private_development_ABI_unchanged':'0x4e45585400003001','cases':[],'exports':[],'HTTP':[],'portable_SDK':False}
def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def run(label,args,folder=out,expected=0,env=None):
 r=subprocess.run(list(map(str,args)),cwd=folder,capture_output=True,text=True,timeout=300,env=env)
 (folder/(label+'.stdout')).write_text(r.stdout);(folder/(label+'.stderr')).write_text(r.stderr)
 assert r.returncode==expected,(label,r.returncode,r.stdout[-2000:],r.stderr[-3000:]);return r

def cli(label,args,folder=out,expected=0,env=None):return json.loads(run(label,[compiler,*args,'--json'],folder,expected,env).stdout)
def project(folder,source):
 folder.mkdir();(folder/'main.nex').write_text(source);(folder/'nex.json').write_text('{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}\n');return folder
corpus=out/'corpus';assert json.loads(run('corpus',[reference,corpus]).stdout)=={'ok':True,'cases':21,'owner_cases':7,'native_session_cases':14}
cases=json.loads((corpus/'cases.json').read_text())['cases'];assert len(cases)==13
build_dir=Path(os.environ.get('NEX_REFERENCE_TASK_CLI_BUILD',str(out/'native'))).resolve()
baseline=project(out/'baseline','module retained;fn main()->unit!{task,io}{task_yield();print(7);}\n')
old=cli('build',['build','--profile','release','--build-directory',build_dir],baseline)
assert json.loads(Path(old['metadata']).read_text())['task_execution_abi']==0x4e45585400000007
assert run('run',[old['executable']],baseline).stdout=='7\n'
for case in cases:
 folder=project(out/Path(case['file']).stem,(corpus/case['file']).read_text());error=case.get('error');limits=['--task-steps',str(case.get('steps',1000000))]
 env={**os.environ,'NEX_FILES_ROOT':str(corpus),'NEX_FILES_WRITE':'1'}
 checked=cli('check',['check'],folder,env=env)
 observed=cli('eval',['eval',*limits],folder,expected=1 if error else 0,env=env)
 assert observed['stdout']==case['stdout'] and observed['ok']==(not error),(case,observed)
 if error:assert observed['code']==error,(case,observed)
 source_message=None
 if error=='E_SOURCE_EXCEPTION':
  oracle_code,oracle_message=case['message'].split(': ',1);source_error=observed['source_exception']
  assert source_error['message']==oracle_message and (source_error['code']==oracle_code or source_error['code'].endswith('::'+oracle_code)),observed
  source_message=source_error['code']+': '+source_error['message']
 for profile in ['debug','release']:
  built=cli('build-'+profile,['build','--profile',profile,'--build-directory',build_dir,*limits],folder,env=env);meta=json.loads(Path(built['metadata']).read_text())
  assert meta['revision']==built['revision']==checked['revision'] and meta['task_execution_abi']==0x4e45585400000008,meta
  actual=run('run-'+profile,[built['executable']],folder,expected=70 if error else 0,env=env);assert actual.stdout==case['stdout'],(case,actual)
  if error:
   prefix='NEX_SOURCE_EXCEPTION 'if error=='E_SOURCE_EXCEPTION'else'NEX_NATIVE_TRAP ';packets=[json.loads(line[len(prefix):])for line in actual.stderr.splitlines()if line.startswith(prefix)];assert len(packets)==1,(case,actual.stderr)
   assert (packets[0]['code']+': '+packets[0]['message']==source_message)if error=='E_SOURCE_EXCEPTION'else packets[0]['code']==error,(case,packets)
  else:assert not actual.stderr,actual.stderr
  assert 'E_INTERNAL_LEAK'not in actual.stderr and not(corpus/'wrong').exists()
  report['cases'].append({'file':case['file'],'source_sha256':sha(folder/'main.nex'),'profile':profile,'revision':checked['revision'],'binary_sha256':sha(built['executable']),'metadata_sha256':sha(built['metadata']),'genuine_files':case['files'],'error':error,'passed':True});save()
 if not case['files']:
  cli('emit',['emit','--kind','typescript','--directory',folder/'generated'],folder)
  generated=folder/'generated';mapping=json.loads((generated/'nex-map.json').read_text());assert mapping['schema']=='nex.typescript-map/4' and mapping['revision']==checked['revision'] and mapping['public_source_enabled'] and mapping['ordinary_CLI']
  run('strict',[node,tsc,'--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--noEmit',generated/'program.ts'],folder)
  (generated/'package.json').write_text('{"type":"module"}\n');(generated/'run.mjs').write_text("import {entry} from './program.ts';try{await entry({steps:"+str(case.get('steps',1000000))+"});}catch(e){console.error(JSON.stringify({code:e.code,message:e.message}));process.exitCode=70;}\n")
  actual=run('node',[node,'--no-warnings','--experimental-strip-types',generated/'run.mjs'],folder,expected=70 if error else 0);assert actual.stdout==case['stdout']
  if error:
   diagnostic=json.loads(actual.stderr);assert diagnostic['code']==error,actual.stderr
   if source_message is not None:assert diagnostic['message']==source_message,diagnostic
  report['exports'].append({'file':case['file'],'revision':checked['revision'],'kind':'ordinary no-argument entry','error':error,'strict_types':True,'passed':True});save()
again=cli('build-again',['build','--profile','release','--build-directory',build_dir],baseline);assert again['cached'] and again['build_key']==old['build_key'] and run('run-again',[again['executable']],baseline).stdout=='7\n';report['retained_ABI7_cache']=True
# An ordinary exported async function accepts copied host values, not boxed cells.
values=project(out/'value-export','''module exported;
fn echo(input:list<i64>)->list<i64>!{state,task}{let value:cell<list<i64>>=cell_new(input);task_yield();cell_collect();return cell_read(value);}
fn main()->unit{}
''');cli('emit',['emit','--kind','typescript','--entry','echo','--directory',values/'generated'],values)
generated=values/'generated';run('strict',[node,tsc,'--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--noEmit',generated/'program.ts'],values);(generated/'package.json').write_text('{"type":"module"}\n')
(generated/'run.mjs').write_text('''import {entry} from './program.ts';
import {taskOwner} from './nex-managed-context.ts';
const require=(v,m)=>{if(!v)throw new Error(m);};
const source=[40n,2n];const pending=entry(source);source[0]=99n;
const result=await pending;require(result[0]===40n&&result[1]===2n,'input snapshot changed');
for(const r of await Promise.all([entry([1n]),entry([2n]),entry([3n])]))require(r.length===1,'concurrent value export failed');
let invalid=false;try{await entry([1]);}catch(e){invalid=e.code==='E_CELL_HOST';}require(invalid,'untyped host value was admitted');
const signal=new AbortController();signal.abort();let cancelled=false;try{await entry([42n],{signal:signal.signal});}catch(e){cancelled=e.code==='E_CANCELLED';}require(cancelled,'public cancellation did not reject');
require((await entry([42n]))[0]===42n,'failed call retained context');
let closed=false;try{taskOwner();}catch(e){closed=e.code==='E_CELL_CONTEXT';}require(closed,'ambient context escaped');
console.log(JSON.stringify({ok:true,input_snapshot:true,concurrent_calls:3,invalid_input:true,cancelled:true,context_closed:true}));
''');exported=json.loads(run('node',[node,'--no-warnings','--experimental-strip-types',generated/'run.mjs'],values).stdout);report['host_values']=exported
# Actual CLI test adapters and captured task replay use the same source030 cohort.
example=project(out/'example',(root/'examples/references/tasks.nex').read_text());revision=cli('check',['check'],example)['revision']
assert cli('web-test',['test','--target','web'],example)['ok'];assert cli('native-test',['test','--profile','release','--build-directory',build_dir],example)['ok']
cli('task-init',['task','main.nex','--kind','init','-o',example/'task.json'],example)
checked=cli('task-check',['task','task.json','--kind','check','--revision',revision],example)
accepted=cli('task-run',['task','task.json','--kind','run','--revision',revision,'--task-hash',checked['task_hash'],'--directory',out/'task-run'],example);assert accepted['ok']
(example/'main.nex').rename(example/'main.retained')
try:assert cli('task-replay',['task',out/'task-run/receipt.json','--kind','replay','--directory',out/'task-replay'])['ok']
finally:(example/'main.retained').rename(example/'main.nex')
report['source_deleted_replay']=True;save()
if os.name!='nt':
 server=project(out/'http','''module task_reference_http;
import "std/http.nex" as http;
struct Fault{value:cell<str>;}
struct Reply{before:str;after:str;same:bool;}
server fn handle(req:http::Request)->http::Response!{state,task,throw}{
 let value:cell<str>=cell_new(req.body);let before:str=cell_read(value);
 let received:cell<str>=with_tasks(2,fn(scope:task_scope)->cell<str>!{state,task,throw}{
  let child:task<cell<str>>=task_spawn(scope,fn()->cell<str>!{state,task,throw}{task_yield();cell_write(value,before+"!");if req.path=="/api/fail"{throw(Fault(value));}return value;});return task_wait(child);
 });cell_collect();return http::json_response(200,encode_json(Reply(before,cell_read(received),received==value)));
}
''')
 auth=out/'auth.json';auth.write_text(json.dumps({'schema':'nex.auth/1','tokens':[{'user':'fixture','sha256':hashlib.sha256(b'local-reference-task').hexdigest()}]}))
 for profile in ['debug','release']:
  built=cli('build-'+profile,['build','--target','server','--profile',profile,'--build-directory',build_dir],server);meta=json.loads(Path(built['metadata']).read_text());assert meta['task_execution_abi']==0x4e45585400000008 and meta['reference_context']['task_transfer'] is True
  stderr=server/(profile+'-server.stderr');log=stderr.open('w');process=subprocess.Popen([built['executable'],'--auth',str(auth),'--database',str(out/(profile+'.sqlite')),'--port','0','--workers','4'],cwd=out,stdout=subprocess.PIPE,stderr=log,text=True,env={**os.environ,'NEX_RESOURCE_DIR':str(out/'absent-resources')})
  try:
   lines=queue.Queue();threading.Thread(target=lambda:lines.put(process.stdout.readline()),daemon=True).start();line=lines.get(timeout=20);match=re.fullmatch(r'NEX server http://127\.0\.0\.1:([0-9]+)\n',line);assert match,(line,stderr.read_text());port=int(match[1])
   def request(path,body):
    c=http.client.HTTPConnection('127.0.0.1',port,timeout=10)
    try:c.request('POST',path,body=body.encode(),headers={'Authorization':'Bearer local-reference-task'});r=c.getresponse();return r.status,json.loads(r.read())
    finally:c.close()
   inputs=['λ\0🙂', 'one','two','🧠']*3
   with concurrent.futures.ThreadPoolExecutor(max_workers=4)as pool:answers=list(pool.map(lambda body:request('/api/echo',body),inputs))
   for text,(status,body)in zip(inputs,answers):assert status==200 and body=={'before':text,'after':text+'!','same':True},(text,status,body)
   assert request('/api/fail','failure')[0]==500
   assert request('/api/echo','next')==(200,{'before':'next','after':'next!','same':True})
   report['HTTP'].append({'profile':profile,'independent_requests':len(answers),'uncaught_source_error':True,'next_request_healthy':True,'binary_sha256':sha(built['executable']),'passed':True})
  finally:
   stop_server(process);log.close()
  assert 'E_INTERNAL_LEAK'not in stderr.read_text() and 'left live values'not in stderr.read_text(),stderr.read_text();save()
else:report['HTTP_pending']='Windows HTTP source030 qualification remains separate'
report['ok']=True;report['native_comparisons']=len(report['cases']);report['typescript_comparisons']=len(report['exports']);save();print(json.dumps({'ok':True,'native_comparisons':len(report['cases']),'typescript_comparisons':len(report['exports']),'report':str(out/'report.json')}))
