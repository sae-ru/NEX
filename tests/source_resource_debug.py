"""Actual CLI/DAP launch arguments and archived views of genuine owned resources."""
from pathlib import Path
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,tempfile,time,traceback

# CMake also installs this script under tools/, beside the sibling tests/.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tests'))

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('compiler',type=Path);parser.add_argument('resources',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--require-live',action='store_true');args=parser.parse_args()
 COMPILER=args.compiler.resolve();RESOURCE=args.resources.resolve();explicit=args.output or os.environ.get('NEX_RESOURCE_DEBUG_OUTPUT')
 OUT=Path(explicit).resolve() if explicit else Path(tempfile.mkdtemp(prefix='nex-resource-debug-'))
 if explicit:OUT.mkdir(parents=True,exist_ok=False)
 require_live=args.require_live or os.environ.get('NEX_REQUIRE_RESOURCE_DAP')=='1'
 language=json.loads(subprocess.check_output([str(COMPILER),'describe','--kind','index','--json'],text=True))['language']
 PROJECT=OUT/'project';PROJECT.mkdir();(PROJECT/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n', newline="\n")
 ENV={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NEX_RESOURCE_DIR':str(RESOURCE)}
 sys.path.insert(0,str(RESOURCE/'tools'))
 from sdk_host import compile_fixture
 doctor=None
 report={'schema':'nex.resource-debug-tests/1','ok':False,'commands':[]};started=time.monotonic()
 def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
 def save():(OUT/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
 def run(label,args,parse=False):
  row={'label':label,'command':list(map(str,args))};report['commands'].append(row);save()
  p=compile_fixture(row['command'],doctor=doctor,cwd=PROJECT,env=ENV,capture_output=True,text=True,timeout=180)
  (OUT/(label+'.stdout')).write_text(p.stdout, newline="\n");(OUT/(label+'.stderr')).write_text(p.stderr, newline="\n");row['exit']=p.returncode;save()
  assert p.returncode==0,(label,p.stdout[-4000:],p.stderr[-4000:])
  return json.loads(p.stdout) if parse else p.stdout
 def cli(label,*args):return run(label,[COMPILER,*args,'--json'],True)
 try:
  doctor=cli('doctor','doctor');assert doctor['language']==language
  text='''module resource_debug;
 server resource Session;
 server extern fn create(x:i64)->Session!{ffi}=foreign("owned","create","PIN");
 server extern fn read(x:Session)->i64!{ffi}=foreign("owned","read","PIN");
 server fn observe(value:Session)->i64!{ffi}{
  let alias:Session=value;
  let number:i64=read(alias);
  return number;
 }
 server fn main()->unit!{ffi,io}{let held:Session=create(42);print(observe(held));assert(resource_close(held));}
 '''
  source=PROJECT/'main.nex';source.write_text(text.replace('PIN','0'*64), newline="\n")
  signatures={name:cli('signature-'+name,'ffi','main.nex','--symbol',name) for name in ('create','read')}
  pins={name:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,value in signatures.items()}
  (PROJECT/'resource-signatures.h').write_text('\n'.join('#define PIN_'+name.upper()+' '+json.dumps(pin) for name,pin in pins.items())+'\n', newline="\n")
  bundle=PROJECT/'bundle';bundle.mkdir();module=bundle/'module.so';marker=OUT/'events'
  sys.path.insert(0,str(RESOURCE/'tools'))
  from sdk_source_resources import c_string_literal
  run('compile-producer',[doctor['native_compiler'],'-x','c++','-std=c++20','-shared','-fPIC','-fvisibility=hidden','-I'+str(RESOURCE/'runtime'),'-I'+str(PROJECT),'-DNEX_RESOURCE_MARKER='+c_string_literal(marker),RESOURCE/'examples/source-resource-producer.c','-o',module])
  (bundle/'NOTICE').write_text('NEX actual resource debugger fixture\n', newline="\n")
  manifest={'schema':'nex.foreign-bundle/1','platform':('windows' if os.name=='nt' else 'macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x86_64'),'entry':'module.so','files':[{'path':name,'sha256':sha(bundle/name)} for name in ('module.so','NOTICE')],'exports':pins,'notices':['NOTICE']}
  (bundle/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n', newline="\n");pin=sha(bundle/'manifest.json')
  host=PROJECT/("operator 'quoted' 🧠.json" if os.name=="nt" else 'operator \"quoted\" 🧠.json');host.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':4,'resource_bytes':32,'libraries':{'owned':{'directory':str(bundle),'manifest_sha256':pin,'exports':['create','read']}}},indent=2)+'\n', newline="\n")
  source.write_text(text.replace('PIN',pin), newline="\n")
  import re
  sys.path.insert(0,str(RESOURCE/'tools'))
  from sdk_acceptance import DAP
  session=cli('prepare-DAP','debug','--kind','nex-dap','--foreign',host)
  debug=json.loads(Path(session['manifest']).read_text());projected=next(s['projection'] for s in debug['sources'] if Path(s['original']).name=='main.nex')
  if not session['nex_adapter']['available']:
   assert not require_live,'actual resource debugger requires lldb-dap'
   report.update(ok=True,actual_resource_DAP=False,skip_reason='lldb-dap is unavailable on this host');return 0
  cli_output=run('native-CLI-LLDB',[COMPILER,'debug','--foreign',host,'--','--no-lldbinit','--batch','-o','settings set target.disable-aslr false','-o','breakpoint set --file source.nex --line 8','-o','run','-o','nex-values','-o','continue'])
  inspections=[json.loads(line) for line in cli_output.splitlines() if line.startswith('{')]
  inspected=next(x for x in inspections if x.get('schema')=='nex.debug-values/1')
  aliases={v['name']:v['value'] for v in inspected['variables']}
  assert aliases['value']==aliases['alias'] and 'resource' in aliases['value'] and marker.read_text()=='IFXD',inspected
  assert 'exited with status = 0' in cli_output
  marker.unlink();report['native_CLI_arguments_delivered_once']=True
  source.unlink()
  class RecordedDAP(DAP):
   def send(self,command,arguments=None):
    sequence=super().send(command,arguments);report.setdefault('DAP_requests',[]).append({'sequence':sequence,'command':command,'arguments':arguments});save();return sequence
   def wait(self,predicate,timeout=30):
    try:
     response=super().wait(predicate,timeout);report.setdefault('DAP_responses',[]).append(response);return response
    finally:report['DAP_pending']=self.pending;save()
  client=RecordedDAP(session['adapter_command'],OUT,ENV)
  try:
   client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'columnsStartAt1':True,'supportsVariableType':True,'supportsVariablePaging':True})
   launch=dict(session['launch'],disableASLR=False)
   pending=client.send('launch',launch)
   client.event('initialized')
   placed=client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':8}]})
   assert placed['breakpoints'][0]['verified'],placed
   client.request('configurationDone');client.response(pending)
   terminal=client.wait(lambda m:m.get('type')=='event' and m.get('event') in ('stopped','exited'));report['first_stop_or_exit']=terminal;save();assert terminal['event']=='stopped',terminal
   stopped=terminal['body'];assert stopped['reason']=='breakpoint'
   stack=client.request('stackTrace',{'threadId':stopped['threadId']})['stackFrames'];frame=stack[0]['id'];assert stack[0]['line']==8,stack
   scopes=client.request('scopes',{'frameId':frame})['scopes'];variables=[];references=[]
   for scope in scopes:
    if not scope.get('expensive'):
     references.append(scope['variablesReference']);variables+=client.request('variables',{'variablesReference':scope['variablesReference']})['variables']
   report['native_variables']=variables
   by_name={v['name']:v for v in variables}
   identities=[re.search(r'<resource ([1-9][0-9]*)>',by_name[name]['value']) for name in ('value','alias')]
   assert all(identities) and identities[0].group(1)==identities[1].group(1),variables
   assert by_name['value']['variablesReference']==by_name['alias']['variablesReference']==0,variables
   checked=client.request('evaluate',{'expression':'`nex-values','context':'repl','frameId':frame})
   report['checked_values']=json.loads(checked['result']);assert report['checked_values']['function']=='resource_debug::observe'
   scalar=client.request('evaluate',{'expression':'number+1','context':'watch','frameId':frame});assert scalar['nex']['value']=='43',scalar
   failed=client.send('evaluate',{'expression':'value','context':'watch','frameId':frame})
   refusal=client.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==failed)
   assert refusal.get('success') is False and 'E_DEBUG_UNAVAILABLE' in json.dumps(refusal),refusal
   report['resource_watch_refusal']=refusal
   raw=client.request('evaluate',{'expression':'`nex-frame value','context':'repl','frameId':frame})
   snapshot=json.loads(raw['result']);assert snapshot['captures']==[] and all('value' not in b for b in snapshot['bindings'])
   (OUT/'frame.json').write_text(json.dumps(snapshot,indent=2)+'\n', newline="\n")
   client.request('continue',{'threadId':stopped['threadId']});assert client.event('exited')['exitCode']==0
   stale=client.send('variables',{'variablesReference':references[0]})
   stale_response=client.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==stale)
   assert stale_response.get('success') is False and 'stale' in json.dumps(stale_response),stale_response
   report['stale_reference_refusal']=stale_response
  finally:client.close()
  assert DAP.successful_shutdowns==1 and marker.read_text()=='IFXD'
  report.update(ok=True,compiler_sha256=sha(COMPILER),actual_resource_DAP=True,source_deleted_archived_debug=True,opaque_resource_aliases=True,pure_scalar_watch=True,resource_watch_authority_refused=True,stale_references_refused=True,destruction_before_unload=True,graceful_adapter_shutdown=True)
 except BaseException as error:report.update(error=repr(error),traceback=traceback.format_exc());raise
 finally:
  report['seconds']=time.monotonic()-started;save();print(json.dumps({k:report.get(k) for k in ['ok','seconds','error','actual_resource_DAP']}))
 
 if report["ok"] and not explicit:shutil.rmtree(OUT)
 return 0 if report["ok"] else 1

if __name__=="__main__":raise SystemExit(main())
