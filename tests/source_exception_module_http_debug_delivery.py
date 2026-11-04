"""Real HTTP DAP sessions: checked caller/request identity and terminal steps."""
import hashlib,http.client,json,os,platform,shutil,signal,socket,ssl,subprocess,sys,threading,time,traceback
from pathlib import Path
from types import SimpleNamespace
from host_fixture import control_event, debugger_tool

def verify(state):
 source=state['source'];out=state['out'];compiler=state['debug_compiler'];target=out/'debug-delivery';target.mkdir();report={'ok':False,'DAP':[]}
 def save():(target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 previous=list(sys.argv)
 try:
  sys.argv=[sys.argv[0],str(state['emitter'])];from debugging import DAP
 finally:sys.argv=previous
 backend=debugger_tool('lldb-dap')
 if not backend and platform.system()=='Darwin':backend=subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
 assert backend
 for image in state['report']['module_images']:
  if image['optimization']!='2':continue
  name=image['program'];e=out/name/'O2';foreign=name.startswith('host-');d=target/name;d.mkdir();files=d/'files';files.mkdir();(files/'input').write_text('abcdef', newline="\n");trace=[];hidden=[];response={};client=None;adapter=None;pid=None
  manifest=json.loads((e/'debug.json').read_text());fn='leaf::render<mid::Payload>' if foreign else 'leaf::fail';row=next(v for v in manifest['functions'] if v['name']==fn);file=row['task_debug']['file'];text=next(v['source'] for v in manifest['source_context']['units'] if v['file']==file);line=next(i for i,t in enumerate(text.splitlines(),1) if ('throw("TEMPLATE"' if foreign else 'throw("PURE"') in t)
  address=socket.socket();address.bind(('127.0.0.1',0));port=address.getsockname()[1];address.close();path='/api/generic-error' if foreign else '/api/uncaught';args=['--auth',str(out/'auth.json'),'--database',str(d/'database.sqlite'),'--port',str(port),'--workers','4','--timeout-ms','60000'];env={'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(d/'events')}
  if foreign:args+=['--foreign',str(state['catalogue'])]
  tls=name=='host-mixed'
  if tls:args+=['--cert',str(out/'cert.pem'),'--key',str(out/'key.pem')]
  class Recorded(DAP):
   def send(self,command,arguments=None):trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
   def wait(self,predicate,timeout=40):
    value=super().wait(predicate,timeout);trace.append({'received':value});return value
  def connect(timeout):return http.client.HTTPSConnection('127.0.0.1',port,timeout=timeout,context=ssl.create_default_context(cafile=str(out/'cert.pem'))) if tls else http.client.HTTPConnection('127.0.0.1',port,timeout=timeout)
  def request():
   try:
    until=time.monotonic()+30
    while True:
     probe=connect(.2)
     try:
      probe.request('GET','/health');ready=probe.getresponse();ready.read()
      if ready.status==200:break
     except OSError:
      if time.monotonic()>until:raise
      time.sleep(.02)
     finally:probe.close()
    connection=connect(60)
    try:
     connection.request('POST',path,body='DAP🌍\0β'.encode(),headers={'Authorization':'Bearer fixture-bob'});r=connection.getresponse();response.update(status=r.status,body=r.read().decode(),request_id=r.getheader('X-Request-Id'))
    finally:connection.close()
   except Exception:response['failure']=traceback.format_exc()
  try:
   for namefile in [out/name/'source-context.json',*[Path(v['file']) for v in manifest['source_context']['units']]]:
    temporary=namefile.with_name(namefile.name+'.hidden');assert namefile.is_file() and not temporary.exists();namefile.rename(temporary);hidden.append((namefile,temporary))
   adapter=Recorded([sys.executable,str(source/'debug/nex_dap.py'),'--backend',backend],d);adapter.request('initialize',{'clientID':'private-HTTP-test','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
   launch=adapter.send('launch',{'program':str(e/('server.exe' if os.name=='nt' else 'server')),**({'stdio':[None,str(d/'inferior.stdout'),str(d/'inferior.stderr')]} if os.name=='nt' else {}),'cwd':str(d),'stopOnEntry':False,'nexTaskDebug':True,'args':args,'env':env,'initCommands':['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(e/'debug.json'))+' --compiler '+json.dumps(str(compiler))],'postRunCommands':[] if os.name=='nt' else ['process handle -s false -p true -n false SIGTERM']});adapter.event('initialized');bp=adapter.request('setBreakpoints',{'source':{'path':file},'breakpoints':[{'line':line}]});assert all(v['verified'] for v in bp['breakpoints']);adapter.request('configurationDone');adapter.response(launch)
   pid=adapter.event('process')['systemProcessId'];assert type(pid) is int and pid>0
   client=threading.Thread(target=request,daemon=True);client.start();stop=adapter.event('stopped');assert stop['allThreadsStopped'];identity=adapter.request('threads')['nex']['selected'];stack=adapter.request('stackTrace',{'threadId':identity});frames=stack['stackFrames'];assert frames[0]['name']==fn;caller=next(f for f in frames if f['name']=='mid::run');frame=frames[0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
   def watch(expression,frame):return adapter.request('evaluate',{'expression':expression,'frameId':frame,'context':'watch'})['nex']['value']
   request_id=watch('req.request_id',caller['id']);assert request_id.isdecimal() and watch('req.path',caller['id'])==path and watch('req.user',caller['id'])=='bob' and watch('req.body',caller['id'])=='DAP🌍\0β'
   if foreign:assert watch('v.body',frame)=='GENERIC' and stack['nex']['frames'][0]['source_identity']['source_component']=='leaf' and stack['nex']['frames'][0]['source_identity']['machine_component']=='mid'
   adapter.request('setBreakpoints',{'source':{'path':file},'breakpoints':[]});adapter.request('stepOut',{'threadId':identity,'singleThread':True});assert adapter.event('stopped')['allThreadsStopped'];after=adapter.request('stackTrace',{'threadId':identity});assert after['stackFrames']==[] and after['nex']['frames']==[]
   stale=adapter.send('variables',{'variablesReference':scope});rejected=adapter.wait(lambda v:v.get('type')=='response' and v.get('request_seq')==stale);assert not rejected['success']
   stale=adapter.send('evaluate',{'expression':'1','frameId':frame,'context':'watch'});rejected=adapter.wait(lambda v:v.get('type')=='response' and v.get('request_seq')==stale);assert not rejected['success']
   adapter.request('continue',{'threadId':identity});client.join(timeout=40);assert not client.is_alive() and 'failure' not in response and response['status']==500 and response['request_id']==request_id,response
   if os.name=='nt':control_event(SimpleNamespace(pid=pid),'Server')
   else:os.kill(pid,signal.SIGTERM)
   assert adapter.event('exited')['exitCode']==0
   if os.name=='nt':raw=(d/'inferior.stderr').read_text(encoding='utf-8')
   else:
    output=adapter.wait(lambda v:v.get('type')=='event' and v.get('event')=='output' and 'NEX_PRIVATE_MODULE_DEBUG_CLEANUP' in v.get('body',{}).get('output',''))
    raw=output['body']['output']
   cleanup=json.loads(next(v.split(' ',1)[1] for v in raw.splitlines() if v.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')));assert cleanup['ok'] and cleanup['live_frames']==0
   report['DAP'].append({'program':name,'optimization':'2','request_id':request_id,'TLS':tls,'source_files_absent':True,'all_stop':True,'terminal_step_out':True,'stale_frame_and_reference_rejected':True,'response':response,'cleanup':cleanup,'exit':0,'passed':True});save()
  finally:
   if adapter:
    try:adapter.close()
    finally:(d/'protocol.json').write_text(json.dumps({'trace':trace,'pending':adapter.pending,'response':response},ensure_ascii=False,indent=2)+'\n', newline="\n")
   for file,temporary in hidden:
    if temporary.exists():temporary.rename(file)
   if client:client.join(timeout=2)
  report['DAP'][-1]['protocol_sha256']=hashlib.sha256((d/'protocol.json').read_bytes()).hexdigest();save()
 report.update(ok=True,DAP_sessions=len(report['DAP']));save();return report
