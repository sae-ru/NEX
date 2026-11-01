"""Actual DAP, unchanged-image relocation and rejected private debug records."""
import argparse,copy,hashlib,json,os,platform,shutil,subprocess,sys
from pathlib import Path
from source_exception_module_debug_support import bind_images

def verify(source,artifacts,compiler,emitter):
 report={'ok':False,'DAP':[],'relocations':[],'rejections':[],'commands':[]};target=artifacts/'debug-delivery';target.mkdir()
 def save():(target/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 def run(label,argv,env=None,allowed=(0,)):
  result=subprocess.run(list(map(str,argv)),cwd=artifacts,env=env,text=True,capture_output=True,timeout=240);(target/(label+'.stdout')).write_text(result.stdout, newline="\n");(target/(label+'.stderr')).write_text(result.stderr, newline="\n");report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit':result.returncode});save();assert result.returncode in allowed,(label,result.stdout[-2000:],result.stderr[-3000:]);return result
 previous=list(sys.argv)
 try:
  sys.argv=[sys.argv[0],str(emitter)];from debugging import DAP
 finally:sys.argv=previous
 backend=shutil.which('lldb-dap')
 if not backend and platform.system()=='Darwin':backend=subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
 assert backend
 root=artifacts/'debug-calls';leaf=root/'leaf/main.nex';app=root/'app/main.nex';leaf_line=next(i for i,t in enumerate(leaf.read_text().splitlines(),1) if '// STOP:leaf' in t);catch_line=next(i for i,t in enumerate(app.read_text().splitlines(),1) if '// STOP:catch' in t)
 for topology in ['static','shared','mixed']:
  for optimization in ['0','2']:
   d=root/topology/('O'+optimization);label='DAP-'+topology+'-O'+optimization;trace=[]
   class Recorded(DAP):
    def send(self,command,arguments=None):trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
    def wait(self,predicate,timeout=30):
     value=super().wait(predicate,timeout);trace.append({'received':value});return value
   adapter=Recorded([sys.executable,str(source/'debug/nex_dap.py'),'--backend',backend],d)
   try:
    adapter.request('initialize',{'clientID':'private-module-test','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
    launch=adapter.send('launch',{'program':str(d/('program.exe' if os.name=='nt' else 'program')),'stdio':[None,None,str(d/'dap-inferior.stderr')],'cwd':str(d),'stopOnEntry':False,'nexTaskDebug':True,'args':['--nex-task-workers','2'],'initCommands':['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(d/'debug.json'))+' --compiler '+json.dumps(str(compiler))]});adapter.event('initialized')
    for file,line in [(leaf,leaf_line),(app,catch_line)]:
     response=adapter.request('setBreakpoints',{'source':{'path':str(file)},'breakpoints':[{'line':line}]});assert all(v['verified'] for v in response['breakpoints'])
    adapter.request('configurationDone');adapter.response(launch);assert adapter.event('stopped')['allThreadsStopped']
    identity=adapter.request('threads')['nex']['selected'];stack=adapter.request('stackTrace',{'threadId':identity});assert [v['name'] for v in stack['stackFrames']]==['leaf::fail','mid::run','app::main']
    assert [v['source_identity']['source_component'] for v in stack['nex']['frames']]==['leaf','mid','app']
    frame=stack['stackFrames'][0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference'];values={v['name']:v['value'] for v in adapter.request('variables',{'variablesReference':scope})['variables']};assert values['v']=='41' and values['leaf_value']=='42'
    watch=adapter.request('evaluate',{'expression':'leaf_value+1','frameId':frame,'context':'watch'});assert watch['nex']['value']=='43' and watch['nex']['archived'] is False
    parent=stack['stackFrames'][1]['id'];assert adapter.request('evaluate',{'expression':'outer+1','frameId':parent,'context':'watch'})['nex']['value']=='42'
    adapter.request('setBreakpoints',{'source':{'path':str(leaf)},'breakpoints':[]});adapter.request('continue',{'threadId':identity});assert adapter.event('stopped')['allThreadsStopped']
    old=adapter.send('variables',{'variablesReference':scope});rejected=adapter.wait(lambda v:v.get('type')=='response' and v.get('request_seq')==old);assert not rejected['success']
    stack=adapter.request('stackTrace',{'threadId':identity});assert [v['name'] for v in stack['stackFrames']]==['app::main'];frame=stack['stackFrames'][0]['id'];assert adapter.request('evaluate',{'expression':'code','frameId':frame,'context':'watch'})['nex']['value']=='LEAF';assert adapter.request('evaluate',{'expression':'mid::plus(outer)','frameId':frame,'context':'watch'})['nex']['value']=='42'
    adapter.request('setBreakpoints',{'source':{'path':str(app)},'breakpoints':[]});adapter.request('next',{'threadId':identity,'singleThread':True});assert adapter.event('stopped')['allThreadsStopped'];assert adapter.request('stackTrace',{'threadId':identity})['stackFrames'][0]['id']!=frame
    adapter.request('continue',{'threadId':identity});assert adapter.event('exited')['exitCode']==42
   finally:
    try:adapter.close()
    finally:(target/(label+'.json')).write_text(json.dumps({'trace':trace,'pending':adapter.pending},ensure_ascii=False,indent=2)+'\n', newline="\n")
   messages={item['seq']:item for item in [*[row['received'] for row in trace if 'received' in row],*adapter.pending] if 'seq' in item}
   output=''.join(item.get('body',{}).get('output','') for _,item in sorted(messages.items()) if item.get('event')=='output')
   cleanup=json.loads(next(line.split(' ',1)[1] for line in (d/'dap-inferior.stderr').read_text(encoding='utf-8').splitlines() if line.startswith('NEX_PRIVATE_MODULE_DEBUG_CLEANUP ')))
   assert cleanup['ok'] is True and cleanup['live_frames']==0,output
   report['DAP'].append({'topology':topology,'optimization':optimization,'all_stop':True,'source_machine_stack':True,'caller_watch':True,'stale_reference_rejected':True,'checked_catch_after_unwind':True,'next_after_unwind':True,'protocol_sha256':hashlib.sha256((target/(label+'.json')).read_bytes()).hexdigest(),'passed':True});save()
 for topology in ['shared','mixed']:
  original=root/topology/'O2';d=target/('relocated-'+topology);d.mkdir();context=json.loads((original/'debug.json').read_text());plan=json.loads((artifacts/('debug-calls-'+topology+'-plan.stdout')).read_text());paths=[Path(row['path']) for row in context['task_debug']['images']]+[Path(context['task_debug']['runtime_image']['path'])];paths=list(dict.fromkeys(paths))
  for file in paths:
   shutil.copy2(file,d/file.name)
   if file.with_name(file.name+'.dSYM').is_dir():shutil.copytree(file.with_name(file.name+'.dSYM'),d/(file.name+'.dSYM'))
  def identity(file):return run('relocated-identity-'+topology+'-'+file.name,[emitter,'identity',file]).stdout.strip().replace('-','').lower()
  context=bind_images(context,plan,d,identity);manifest=d/'debug.json';manifest.write_text(json.dumps(context,ensure_ascii=False,indent=2)+'\n', newline="\n");options=json.loads((original/'session.json').read_text());options.update(report=str(d/'lldb-report.json'),directory=str(d));config=d/'session.json';config.write_text(json.dumps(options,ensure_ascii=False,indent=2)+'\n', newline="\n");hidden=[]
  try:
   for file in paths:
    temporary=file.with_name(file.name+'.hidden');assert not temporary.exists();file.rename(temporary);hidden.append((file,temporary))
   argv=[shutil.which('lldb'),'--no-lldbinit','--batch',d/('program.exe' if os.name=='nt' else 'program')]
   for command in ['settings set target.disable-aslr false','command script import '+json.dumps(str(source/'debug/lldb_nex.py')),'nex-load-private-task-debug '+json.dumps(str(manifest))+' --compiler '+json.dumps(str(compiler)),'command script import '+json.dumps(str(artifacts/'module_lldb_session.py')),'nex-private-test-session '+str(config)]:argv+=['-o',command]
   result=run('relocated-'+topology,argv);observed=json.loads((d/'lldb-report.json').read_text());assert observed['ok'] and observed['exit']==42 and observed['source_absent_during_watch'] and len(observed['observations'])==2
  finally:
   for file,temporary in hidden:
    if temporary.exists():temporary.rename(file)
  assert all(hashlib.sha256(file.read_bytes()).digest()==hashlib.sha256((d/file.name).read_bytes()).digest() for file in paths)
  report['relocations'].append({'topology':topology,'actual_unchanged_images':True,'original_images_absent':True,'all_stop':True,'source_files_absent':True,'watches':len(observed['watches']),'passed':True});save()
 # Validate changed context/architecture against one real captured source frame.
 original=root/'mixed/O0';manifest=json.loads((original/'debug.json').read_text());capture=original/'frame-0.json';assert capture.is_file()
 for name in ['machine-owner','source-owner','metadata','registry','plan-hash']:
  changed=copy.deepcopy(manifest)
  if name=='machine-owner':changed['functions'][0]['machine_component']='another'
  elif name=='source-owner':changed['functions'][0]['source_component']='another'
  elif name=='metadata':changed['task_debug']['metadata_hash']='0'*64
  elif name=='registry':changed['task_debug']['registries'][0]['code_count']+=1
  else:changed['module_plan_hash']='0'*64
  file=target/(name+'.json');file.write_text(json.dumps(changed,ensure_ascii=False,indent=2)+'\n', newline="\n");result=run('reject-'+name,[compiler,'inspect-private-task',capture,'--manifest',file,'--expression','v','--json'],allowed=(1,));error=json.loads(result.stdout);assert error['code']=='E_DEBUG_BUILD',error;report['rejections'].append({'name':name,'code':error['code'],'passed':True});save()
 context=root/'context.json';original_arch=json.loads((root/'mixed/architecture.json').read_text());probe=emitter.parent/('nex_source_exception_modules_probe.exe' if os.name=='nt' else 'nex_source_exception_modules_probe')
 for name,change in [('missing-timeout',lambda a:a.pop('debug_timeout_ms')),('zero-timeout',lambda a:a.update(debug_timeout_ms=0)),('too-large-timeout',lambda a:a.update(debug_timeout_ms=3600001)),('profile-instrumentation',lambda a:a.update(instrumentation='profile')),('old-schema',lambda a:a.update(schema='nex.private-task-architecture/5'))]:
  value=copy.deepcopy(original_arch);change(value);file=target/(name+'.json');file.write_text(json.dumps(value), newline="\n");result=run('reject-'+name,[probe,'plan',context,file],allowed=(1,));assert 'E_EXCEPTION_MODULE' in result.stderr;report['rejections'].append({'name':name,'code':'E_EXCEPTION_MODULE','passed':True});save()
 report.update(ok=True,DAP_comparisons=len(report['DAP']),relocated_debug_sessions=len(report['relocations']));save();return report

def main():
 p=argparse.ArgumentParser();p.add_argument('artifacts',type=Path);p.add_argument('compiler',type=Path);p.add_argument('emitter',type=Path);a=p.parse_args();r=verify(Path(__file__).resolve().parents[1],a.artifacts.resolve(),a.compiler.resolve(),a.emitter.resolve());print(json.dumps({'ok':r['ok'],'DAP_comparisons':r['DAP_comparisons'],'relocations':r['relocated_debug_sessions']}))
if __name__=='__main__':main()
