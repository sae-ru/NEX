"""Actual ABI5 provider profiles and LLDB/DAP File-bearing source frames."""
import argparse,base64,hashlib,json,os,shutil,subprocess,sys,time
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('compiler',type=Path);p.add_argument('fixtures',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
probe=a.probe.resolve();compiler=a.compiler.resolve();fixtures=a.fixtures.resolve();root=a.output.resolve();root.mkdir();started=time.monotonic()
report={'schema':'nex.private024-stream-project-observability/1','ok':False,'state':'starting','commands':[],'profiles':[],'debug_sessions':[],
 'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
 'public_language':'0.27','private_language':'0.24','public025_delivery_accepted':False,'full_objective_complete':False}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n', newline="\n")
def save():report['seconds']=round(time.monotonic()-started,3);write(root/'report.json',report)
def invoke(name,request):
 report['state']=name;save();path=root/(name+'.request.json');write(path,{'compiler':str(compiler),**request})
 r=subprocess.run([probe,path],cwd=root,capture_output=True,text=True,timeout=600)
 (root/(name+'.stdout')).write_text(r.stdout, newline="\n");(root/(name+'.stderr')).write_text(r.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':[str(probe),str(path)],'exit_code':r.returncode});save()
 assert r.returncode==0,(name,r.stdout[-4500:],r.stderr[-4500:]);return json.loads(r.stdout)
def dap_session(name,session,files,mode):
 from debugging import DAP
 directory=root/name;directory.mkdir();manifest=json.loads(Path(session['manifest']).read_text())
 assert manifest['schema']=='nex.debug/3' and manifest['language']=='0.24'
 assert {row['language'] for row in manifest['task_debug']['source_union']['components']}=={'0.24'}
 backend=shutil.which('lldb-dap')
 if not backend and sys.platform=='darwin':backend=subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
 assert backend,'actual LLDB DAP is required';trace=[]
 class Recorded(DAP):
  def send(self,command,arguments=None):trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
  def wait(self,predicate,timeout=30):
   result=super().wait(predicate,timeout);trace.append({'response_or_event':result});return result
 adapter=Recorded([sys.executable,manifest['dap_adapter'],'--backend',backend],directory)
 try:
  adapter.request('initialize',{'clientID':'nex-stream-provider-test','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
  launch=adapter.send('launch',{'program':session['launch']['program'],'cwd':str(root),'env':{'NEX_FILES_ROOT':str(files)},'stopOnEntry':False,
   'nexTaskDebug':True,'initCommands':['settings set target.disable-aslr false','command script import '+json.dumps(manifest['formatter']),
    'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(str(compiler))]})
  adapter.event('initialized');points=adapter.request('setFunctionBreakpoints',{'breakpoints':[{'name':'leaf::transit'}]})
  assert points['breakpoints'][0]['verified'];adapter.request('configurationDone');adapter.response(launch)
  stopped=adapter.event('stopped');assert stopped['allThreadsStopped'] and 'threadId' not in stopped
  tasks=adapter.request('threads');selected=tasks['nex']['selected'];assert selected
  stack=adapter.request('stackTrace',{'threadId':selected});assert stack['stackFrames'][0]['name']=='leaf::transit'
  frame=stack['stackFrames'][0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
  values=adapter.request('variables',{'variablesReference':scope})['variables'];assert any(row['name']=='p' for row in values)
  watch=adapter.request('evaluate',{'expression':'p.value == p.value','frameId':frame,'context':'watch'})
  assert watch['nex']['value'] is True and watch['nex']['source_identity']['language']=='0.24'
  assert watch['nex']['source_identity']['component']=='leaf' and watch['nex']['source_identity']['owner_image']==('leaf' if mode=='shared' else 'app')
  denied=adapter.send('evaluate',{'expression':'file_read(p.value,1)','frameId':frame,'context':'watch'})
  refused=adapter.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==denied);assert not refused['success']
  adapter.request('continue',{'threadId':selected});exited=adapter.event('exited');assert exited['exitCode']==0
  return {'mode':mode,'manifest':session['manifest'],'manifest_sha256':sha(session['manifest']),'task_source_frame':'leaf::transit',
   'File_identity_watch':True,'effectful_watch_rejected':True,'source_identity':watch['nex']['source_identity'],'actual_LLDB_DAP':True}
 finally:
  try:adapter.close()
  finally:write(directory/'dap-protocol.json',{'trace':trace,'pending':adapter.pending})
try:
 data=json.loads((fixtures/'report.json').read_text());assert data['execution_matrix_complete'] and data['native_reference_pairs']==len(data['cases'])==8
 for mode in ['static','shared']:
  for debug in [False,True]:
   case=next(row for row in data['cases'] if row['mode']==mode and row['profile']==('debug' if debug else 'profile') and row['task_debug']==debug)
   directory=fixtures/case['name'];capture=json.loads(Path(case['capture']).read_text());container=directory/'capture-root';source=container/capture['project_root'];files=directory/'files'
   request={'root':str(source),'configuration':'debug' if debug else 'profile','directory':str(directory/'replay-native')}
   name=mode+('-debug' if debug else '-profile')
   if debug:request.update(action='debug',adapter='nex-dap')
   else:request.update(action='profile',profile_output=str(root/(mode+'-profile.json')),environment={'NEX_FILES_ROOT':str(files)})
   result=invoke(name,request);session=result['observation']
   original=directory/'project';hidden_original=directory/'project.hidden';original.rename(hidden_original)
   hidden_container=directory/'capture-root.hidden';container.rename(hidden_container)
   try:
    if debug:report['debug_sessions'].append(dap_session(name,session,files,mode))
    else:
     assert session['schema']=='nex.profile-session/3' and session['stdout']=='42\n'
     profile=json.loads(Path(session['output']).read_text());assert profile['schema']=='nex.profile/3' and profile['language']=='0.24'
     assert profile['build']['language']=='0.24' and profile['build']['schema']=='nex.profile-build/2'
     functions={row['name']:row for row in profile['functions']};assert set(functions)=={'app::main','leaf::opened','leaf::transit'}
     for row in functions.values():assert (row['calls'],row['completed'],row['aborted'])==(1,1,0)
     assert all(row['terminal'] and row['active_invocations']==0 for row in profile['tasks'])
     assert all(row['live']==row['live_shallow_bytes']==0 and row['allocations']==row['frees'] for row in profile['memory'])
     assert all(profile['completeness'][key] for key in ['aggregates','memory','cpu','elapsed','lifetime','timeline'])
     report['profiles'].append({'mode':mode,'output':session['output'],'sha256':sha(session['output']),'actual_execution':True,'completed_source_calls':3,'live_profile_memory':0})
   finally:hidden_container.rename(container);hidden_original.rename(original)
   assert (files/'input').read_bytes()==b'abcdef' and not (files/'UNREACHABLE_WRITE').exists();save()
 report.update(ok=True,state='passed',actual_profiles=len(report['profiles']),actual_LLDB_DAP_sessions=len(report['debug_sessions']),
  File_watch_and_effect_rejection=True,source_projects_hidden_during_DAP=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','actual_profiles','actual_LLDB_DAP_sessions','error']}),flush=True)
