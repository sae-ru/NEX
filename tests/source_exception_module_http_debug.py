"""Real modular HTTP logical debugging, request identity and joined completion."""
import hashlib,json,os,platform,shutil,sys
from pathlib import Path
import source_exception_module_http as modules
from source_exception_module_debug_support import bind_images

LLDB_DRIVER=r'''
import base64,http.client,json,os,re,signal,socket,ssl,threading,time,traceback
from pathlib import Path
import lldb

def session(debugger,command,result,internal_dict):
 config=json.loads(Path(command.strip()).read_text());report={'ok':False,'observations':[],'responses':[],'commands':[],'captures':[]}
 target=debugger.GetSelectedTarget();process=None;clients=[];stdout='';stderr='';hidden=[];shutdown_lock=threading.Lock();shutdown_sent=False
 def run(text):
  response=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,response);out=response.GetOutput() or '';err=response.GetError() or '';report['commands'].append({'command':text,'output':out,'error':err,'ok':response.Succeeded()});assert response.Succeeded(),(text,out,err);return out
 def request(command,**arguments):return json.loads(run('nex-task-request-encoded '+base64.b64encode(json.dumps({'command':command,'arguments':arguments}).encode()).decode()))
 def watch(task,expression,index=0):
  payload=base64.b64encode(json.dumps({'expression':expression,'task_id':task,'frame_index':index}).encode()).decode();value=json.loads(run('nex-eval-encoded '+payload));assert value['ok'] and value['archived'] is False and 'revision' not in value;return value['value']
 def drain():
  nonlocal stdout,stderr
  out=Path(config['directory'])/'inferior-stdout';err=Path(config['directory'])/'inferior-stderr';stdout=out.read_text() if out.exists() else '';stderr=err.read_text() if err.exists() else ''
 def wait(predicate,seconds=40):
  until=time.monotonic()+seconds
  while time.monotonic()<until:
   drain()
   if predicate():return
   if process.GetState() in (lldb.eStateExited,lldb.eStateCrashed):raise AssertionError(('inferior ended',process.GetState(),stdout,stderr))
   time.sleep(.01)
  raise AssertionError(('HTTP debug observation timed out',process.GetState(),stdout[-2000:],stderr[-2000:]))
 def pulse():
  value=target.FindFirstGlobalVariable('nex_private_debug_pulse');assert value.IsValid();error=lldb.SBError();number=process.ReadUnsignedFromMemory(value.GetLoadAddress(),8,error);assert error.Success();return number
 def resume():
  debugger.SetAsync(True);request('continue')
 def client(port,index):
  nonlocal shutdown_sent
  row={'index':index};report['responses'].append(row)
  try:
   item=config['requests'][index];tls=config.get('TLS');connection=http.client.HTTPSConnection('127.0.0.1',port,context=ssl.create_default_context(cafile=config['certificate']),timeout=40) if tls else http.client.HTTPConnection('127.0.0.1',port,timeout=40)
   until=time.monotonic()+30
   while not item.get('background'):
    probe=http.client.HTTPSConnection('127.0.0.1',port,context=ssl.create_default_context(cafile=config['certificate']),timeout=.2) if tls else http.client.HTTPConnection('127.0.0.1',port,timeout=.2)
    try:
     probe.request('GET','/health');ready=probe.getresponse();ready.read()
     if ready.status==200:break
    except OSError:
     if time.monotonic()>until:raise
     time.sleep(.02)
    finally:probe.close()
   try:
    connection.request('POST',item['path'],body=item['body'].encode(),headers={'Authorization':'Bearer fixture-'+item['user']});row['sent']=True;response=connection.getresponse();row.update(status=response.status,body=response.read().decode(),request_id=response.getheader('X-Request-Id'))
   finally:connection.close()
  except Exception:row['failure']=traceback.format_exc()
  finally:
   row['done']=True
   with shutdown_lock:
    if not shutdown_sent and len(report['responses'])==len(config['requests']) and all(r.get('done') for r in report['responses']):
     shutdown_sent=True;pid=target.GetProcess().GetProcessID()
     if pid:
      try:os.kill(pid,signal.SIGTERM)
      except ProcessLookupError:pass
 try:
  for name in config['source_files']:
   file=Path(name);temporary=file.with_name(file.name+'.hidden');assert file.is_file() and not temporary.exists();file.rename(temporary);hidden.append((file,temporary))
  report['source_files_absent']=all(not f.exists() for f,_ in hidden)
  response=request('breakpoints',source=config['break_file'],breakpoints=[{'line':config['break_line']}]);assert all(row['verified'] for row in response['breakpoints'])
  address=socket.socket();address.bind(('127.0.0.1',0));port=address.getsockname()[1];address.close();arguments=list(config['arguments']);arguments[arguments.index('--port')+1]=str(port)
  watched=[i for i,item in enumerate(config['requests']) if not item.get('background')]
  for index in watched:
   thread=threading.Thread(target=client,args=(port,index),daemon=True);clients.append(thread);thread.start()
  debugger.SetAsync(False);run('process launch -o '+json.dumps(str(Path(config['directory'])/'inferior-stdout'))+' -e '+json.dumps(str(Path(config['directory'])/'inferior-stderr'))+' -- '+ ' '.join(json.dumps(str(value)) for value in arguments));process=target.GetProcess();assert process.IsValid() and process.GetState()==lldb.eStateStopped
  run('process handle -s false -p true -n false SIGTERM');seen=set()
  for index in range(len(watched)):
   tasks=request('tasks');assert not tasks.get('marker_error'),tasks;identity=tasks['selected'];assert identity not in seen;seen.add(identity);stack=request('stack',task_id=identity);assert stack['frames'][0]['name']==config['function'],stack
   req_index=next(i for i,row in enumerate(stack['frames']) if row['name']=='mid::run');path=watch(identity,'req.path',req_index);request_id=watch(identity,'req.request_id',req_index);user=watch(identity,'req.user',req_index);body=watch(identity,'req.body',req_index)
   item=next(r for r in config['requests'] if r['path']==path and r['user']==user and r['body']==body);assert request_id.isdecimal() and int(request_id)>0
   if config.get('overlap'):
    background=next(i for i,item in enumerate(config['requests']) if item.get('background'));thread=threading.Thread(target=client,args=(port,background),daemon=True);clients.append(thread);thread.start();until=time.monotonic()+3
    while not any(r.get('index')==background and r.get('sent') for r in report['responses']) and time.monotonic()<until:time.sleep(.01)
    assert any(r.get('index')==background and r.get('sent') and not r.get('done') for r in report['responses']);report['overlap_queued_while_all_stop']=True
   before=pulse();time.sleep(.025);assert pulse()==before
   if config.get('owned'):assert watch(identity,'f==f') is True
   if config.get('generic'):assert stack['frames'][0]['source_identity']['source_component']=='leaf' and stack['frames'][0]['source_identity']['machine_component']=='mid' and watch(identity,'v.body')=='GENERIC'
   capture=json.loads(run('nex-frame '+('v.body' if config.get('generic') else 'f==f' if config.get('owned') else 'body')));assert capture['schema']=='nex.private-task-debug-frame/2';file=Path(config['directory'])/('frame-'+str(index)+'.json');file.write_text(json.dumps(capture,ensure_ascii=False)+'\n');report['captures'].append({'file':str(file),'expression':'v.body' if config.get('generic') else 'f==f' if config.get('owned') else 'body','value':watch(identity,'v.body' if config.get('generic') else 'f==f' if config.get('owned') else 'body')})
   if config.get('deadline'):time.sleep(1.1)
   # Out may reach a handler, or a terminal task if this request has no handler.
   request(config.get('step_command','out'),task_id=identity);assert process.GetState()==lldb.eStateStopped;after=request('stack',task_id=identity);state=request('tasks');assert not state.get('marker_error'),state
   completed=not after['frames']
   if completed:
    record=next(row for row in state['tasks'] if row['id']==identity);assert record['state']=='terminal' and record['terminal'],record
   else:
    assert after['frames'][0]['name']=='mid::run',after
    assert watch(identity,'req.request_id')==request_id
   report['observations'].append({'task_id':identity,'request_id':request_id,'path':path,'user':user,'all_stop':True,'stack':stack,'after_out':after,'terminal_completion':completed})
   if index+1==len(watched):request('breakpoints',source=config['break_file'],breakpoints=[])
   request('continue')
   # Linux LLDB can surface its internal loader rendezvous while another
   # thread auto-continues a source marker. No NEX breakpoint/step remains
   # armed here. Preserve real reader errors, signals and unexpected stops.
   if index+1==len(watched):
    for attempt in range(8):
     if process.GetState()!=lldb.eStateStopped:break
     reasons=[(t.GetStopReason(),t.GetStopDescription(512),t.GetFrameAtIndex(0).GetFunctionName()) for t in process]
     state=request('tasks');assert not state.get('marker_error'),state
     assert any(reason[1]=='shared-library-event' for reason in reasons),reasons
     assert all(reason[0] in (lldb.eStopReasonNone,lldb.eStopReasonInvalid) or reason[1]=='shared-library-event' or reason[0]==lldb.eStopReasonBreakpoint and 'nex_task_debug_' in (reason[2] or '') for reason in reasons),reasons
     report.setdefault('internal_loader_stops',[]).append({'reasons':reasons,'verified_tasks':state});request('continue')
   if index+1<len(watched):assert process.GetState()==lldb.eStateStopped
  for thread in clients:thread.join(timeout=2)
  drain();assert process.GetState()==lldb.eStateExited,(process.GetState(),[(t.GetStopReason(),t.GetStopDescription(512),t.GetFrameAtIndex(0).GetFunctionName()) for t in process],stdout,stderr);assert process.GetExitStatus()==0,(process.GetExitStatus(),stdout,stderr)
  for observed in report['observations']:
   item=next(r for r in config['requests'] if r['path']==observed['path'] and r['user']==observed['user']);index=config['requests'].index(item);response=next(r for r in report['responses'] if r['index']==index)
   assert 'failure' not in response and response['done'] and response['request_id']==observed['request_id'] and response['status']==item['status'],response
  if config.get('overlap'):
   background=next(r for r in report['responses'] if config['requests'][r['index']].get('background'));assert 'failure' not in background and background['status']==200 and background['body']=='bob:background' and background['request_id'] not in [r['request_id'] for r in report['observations']]
  cleanup=json.loads(next(line.split(' ',1)[1] for line in stderr.splitlines() if line.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')));assert cleanup['ok'] and cleanup['live_frames']==0;report.update(ok=True,exit=0,cleanup=cleanup)
 except Exception:
  report['failure']=traceback.format_exc();result.SetError(report['failure'])
 finally:
  if process and process.IsValid():
   drain()
   if process.GetState() not in (lldb.eStateExited,lldb.eStateDetached):process.Kill()
  for original,temporary in hidden:
   if temporary.exists():temporary.rename(original)
  report['stdout']=stdout;report['stderr']=stderr;Path(config['report']).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
 if report['ok']:result.PutCString(json.dumps({'ok':True,'report':config['report']}))
def __lldb_init_module(debugger,internal_dict):debugger.HandleCommand('command script add -f '+__name__+'.session nex-private-http-test-session')
'''


def context(directory,text,source,default):
 path=modules.context(directory,text,source,default)
 value=json.loads(path.read_text())
 for row in value['units']:
  row['source']=row['source'].replace('task_yield();throw("PURE",body);','\n task_yield();\n throw("PURE",body);\n').replace('if s=="GENERIC"{throw("TEMPLATE","λ\\u0000🙂");}return s;','if s=="GENERIC"{\n throw("TEMPLATE","λ\\u0000🙂");\n}return s;')
  Path(row['file']).write_text(row['source'])
 value['source']=next(row['source'] for row in value['units'] if row['unit']==value['entry_unit']);path.write_text(json.dumps(value,ensure_ascii=False)+'\n');return path


def observe(binary,row):
 modules.observe(binary,row);cleanup=[json.loads(line.split(' ',1)[1]) for line in row['stderr'].splitlines() if line.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')];assert len(cleanup)==1 and cleanup[0]['ok'] and cleanup[0]['live_frames']==0;row['debug_cleanup']=cleanup[0]


def main():
 # Use the same ordinary HTTP oracle, image ownership and provider-delivery tests.
 import source_exception_http as http
 native_only='--http-debug-native-only' in sys.argv
 if native_only:sys.argv.remove('--http-debug-native-only')
 state=http.main(modules.build,context,'NEX_EXCEPTION_MODULE_HTTP_DEBUG_OUTPUT',['static','shared','mixed'],['/api/generic-error'],False,observe,False,True);modules.contracts(state);modules.reuse_and_relocate(state);out=state['out'];source=state['source'];report=state['report'];run=state['run'];report['debug_sessions']=[];report['captures']=[];driver=out/'http_lldb_session.py';driver.write_text(LLDB_DRIVER);compiler=state['debug_compiler'];assert compiler
 report.update(private_modular_HTTP=True,actual_symbol_and_loader_ownership=True,joined_shutdown_cleanup=True,native_only=native_only)
 if native_only:
  report.update(ok=True,private_module_HTTP_debugging=True,HTTP_requests=len(report['requests']),HTTP_server_launches=len(report['servers']),LLDB_sessions=0);state['save']();return
 for image in report['module_images']:
  name=image['program'];directory=out/name;e=directory/('O'+image['optimization']);binary=e/'server';plan=json.loads((e/'plan.json').read_text());foreign=name.startswith('host-');label=name+'-O'+image['optimization']
  if platform.system()=='Darwin':
   for file in [e/v['file'] for v in image['images'].values()]+([e/('libnex-private-runtime-http'+('.dylib' if platform.system()=='Darwin' else '.so'))] if plan['runtime_linkage']=='shared' else []):run(label+'-dsym-'+file.name,['dsymutil',file])
  unlinked=json.loads(run(label+'-debug-context',[state['module_probe'],'debug-context',directory/'source-context.json',directory/'architecture.json']).stdout)
  def identity(file):return run(label+'-identity-'+file.name,[state['emitter'],'identity',file]).stdout.strip().replace('-','').lower()
  manifest=bind_images(unlinked,plan,e,identity);manifest.update(formatter=str(source/'debug/lldb_nex.py'),dap_adapter=str(source/'debug/nex_dap.py'));file=e/'debug.json';file.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
  variants=[('recover','leaf::leaf' if foreign else 'leaf::fail','/api/recover',200,False,False),('uncaught','leaf::leaf' if foreign else 'leaf::fail','/api/uncaught',500,False,False)]
  if foreign:variants += [('generic','leaf::render<mid::Payload>','/api/generic-error',500,True,False)]
  if name=='host-mixed':variants += [('deadline','leaf::leaf','/api/recover',504,False,True)]
  if name=='host-mixed':variants += [('next','leaf::leaf','/api/uncaught',500,False,False),('overlap','leaf::leaf','/api/recover',200,False,False),('TLS','leaf::leaf','/api/recover',200,False,False)]
  for tag,fn,path,status,generic,deadline in variants:
   live=e/('debug-'+tag);live.mkdir();files=live/'files';files.mkdir();(files/'input').write_text('abcdef');context_row=next(row for row in manifest['functions'] if row['name']==fn);points=context_row['task_debug']['points'];lines=Path(context_row['task_debug']['file']).read_text().splitlines();line=next(i for i,text in enumerate(lines,1) if ('throw("TEMPLATE"' if generic else 'throw("HOST"' if foreign else 'throw("PURE"') in text);assert any(point['line']==line and point['phase']=='statement' for point in points)
   arguments=['--auth',str(out/'auth.json'),'--database',str(live/'database.sqlite'),'--port','0','--workers','4','--timeout-ms','800' if deadline else '60000']
   if foreign:arguments+=['--foreign',str(state['catalogue'])]
   options={'arguments':arguments,'directory':str(live),'report':str(live/'report.json'),'source_files':[str(directory/'source-context.json'),*[row['file'] for row in manifest['source_context']['units']]],'break_file':context_row['task_debug']['file'],'break_line':line,'function':fn,'owned':foreign and not generic,'generic':generic,'deadline':deadline,'requests':[{'path':path,'user':'alice','body':'A🌍\0β','status':status}]}
   if tag=='next':options['step_command']='next'
   if tag=='overlap':options['overlap']=True;options['requests'].append({'path':'/api/echo','user':'bob','body':'background','status':200,'background':True})
   if tag=='TLS':
    options.update(TLS=True,certificate=str(out/'cert.pem'));arguments+=['--cert',str(out/'cert.pem'),'--key',str(out/'key.pem')]
   config=live/'session.json';config.write_text(json.dumps(options,ensure_ascii=False,indent=2)+'\n');argv=[shutil.which('lldb'),'--no-lldbinit','--batch',binary]
   for command in ['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(file))+' --compiler '+json.dumps(str(compiler)),'command script import '+json.dumps(str(driver)),'nex-private-http-test-session '+str(config)]:argv+=['-o',command]
   env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1','NEX_PRIVATE_HOST_EVENTS':str(live/'events')};result=run(label+'-debug-'+tag,argv,env);observed=json.loads((live/'report.json').read_text());assert observed['ok'] and observed['source_files_absent']
   observe(binary,observed);assert observed['cleanup']['ok']
   assert observed['observations'][0]['terminal_completion']==(tag in ['uncaught','generic','next'])
   for i,capture in enumerate(observed['captures']):
    offline=json.loads(run(label+'-'+tag+'-offline-'+str(i),[compiler,'inspect-private-task',capture['file'],'--manifest',file,'--expression',capture['expression'],'--json']).stdout);assert offline['ok'] and offline['value']==capture['value'];report['captures'].append({'file':capture['file'],'sha256':hashlib.sha256(Path(capture['file']).read_bytes()).hexdigest(),'passed':True})
   report['debug_sessions'].append({'program':name,'optimization':image['optimization'],'variant':tag,'report_sha256':hashlib.sha256((live/'report.json').read_bytes()).hexdigest(),'all_stop':True,'terminal_completion':observed['observations'][0]['terminal_completion'],'request_identity':True,'passed':True});state['save']()
 from source_exception_module_http_debug_delivery import verify
 report['debug_delivery']=verify(state);state['save']()
 report.update(ok=True,private_module_HTTP_debugging=True,HTTP_requests=len(report['requests']),HTTP_server_launches=len(report['servers']),LLDB_sessions=len(report['debug_sessions']));state['save']();print(json.dumps({'ok':True,'LLDB_sessions':report['LLDB_sessions']}))

if __name__=='__main__':main()
