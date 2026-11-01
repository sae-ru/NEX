"""Explicit027 native typed catch values through real LLDB and NEX-DAP."""
from pathlib import Path
from types import SimpleNamespace
import argparse,hashlib,json,os,platform,shutil,subprocess,sys,tempfile,time

parser=argparse.ArgumentParser()
parser.add_argument('probe',type=Path)
parser.add_argument('nex',type=Path)
parser.add_argument('--output',type=Path)
parser.add_argument('--source-language',choices=['0.27','0.28'],default='0.27')
parser.add_argument('--resources',type=Path)
parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1])
args=parser.parse_args();language=args.source_language
args.probe=args.probe.resolve();args.nex=args.nex.resolve();args.source_root=args.source_root.resolve()
if args.resources:args.resources=args.resources.resolve(strict=True)
if platform.system() not in ('Darwin','Linux','Windows'):
 print('Typed native debugger platform acceptance remains pending on '+platform.system());sys.exit(77)
output=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-typed-debug-'))
output.mkdir(parents=True,exist_ok=args.output is None)

def run_case(scenario,mode,directory):
 a=SimpleNamespace(mode=mode,scenario=scenario)
 O=directory;O.mkdir();root=O/'project';root.mkdir()
 compiler=args.nex;resources=args.resources or args.source_root
 leaf=r'''module leaf;
 pub struct Problem<T>{value:T;note:str;}
 pub fn later(value:i64)->i64 !{task,throw}{
  task_yield();throw(Problem<i64>(value,"λ\u0000🙂"));
 }
 '''
 middle=r'''module middle;
 import "../leaf/main.nex" as leaf;
 pub fn reject(value:i64)->bool !{task}{task_yield();assert(value==42);return false;}
 pub fn forward(value:i64)->i64 !{task,throw}{
  try{return leaf::later(value);}
  catch(e:leaf::Problem<i64>) if reject(e.value){return 0;}
  finally{task_yield();}
 }
 '''
 app=r'''module app;
 import "../middle/main.nex" as middle;
 import "../leaf/main.nex" as leaf;
 fn main()->unit !{task,io,throw}{
  try{middle::forward(42);assert(false);}
  catch(e:leaf::Problem<i64>){
   task_yield();
   let answer:i64=e.value;
   assert(e.note=="λ\u0000🙂");
   print(answer);
  }
  catch(code,message){assert(false);}
 }
 '''
 watches=[{'expression':'e.value','value':'42'},{'expression':'e.note','value':'λ\0🙂'}]
 frame_expression='e';guard=True;out_of_scope='code';effectful='task_yield()'
 if a.scenario=='list':
  values=','.join(str(i) for i in range(299))+',value'
  leaf=leaf.replace('Problem<i64>(value,','Problem<list<i64>>(['+values+'],')
  middle=middle.replace('Problem<i64>','Problem<list<i64>>').replace('reject(e.value)','reject(e.value[299])')
  app=app.replace('Problem<i64>','Problem<list<i64>>').replace('e.value;','e.value[299];')
  watches[0]['expression']='e.value[299]'
 elif a.scenario=='legacy':
  leaf=leaf.replace('throw(Problem<i64>(value,','throw("LEGACY",')
  # Remove the constructor's extra close parenthesis when using a legacy raise.
  leaf=leaf.replace('🙂"));','🙂");')
  app=app.replace(' catch(e:leaf::Problem<i64>){',' catch(e:leaf::Problem<i64>){assert(false);}\n catch(code,message){').replace('let answer:i64=e.value;','let answer:i64=42;').replace('e.note==','message==').replace(' catch(code,message){assert(false);}\n','')
  watches=[{'expression':'code','value':'LEGACY'},{'expression':'message','value':'λ\0🙂'}]
  frame_expression='code';guard=False;out_of_scope='e'
 elif a.scenario=='file':
  leaf=leaf.replace('pub fn later(value:i64)->i64 !{task,throw}','pub server fn later(value:i64)->i64 !{task,fs,throw}').replace(' task_yield();throw(Problem<i64>(value,"λ\\u0000🙂"));',' let owner:file=unwrap(file_open_read("input"));task_yield();throw(owner);')
  # The fixture has one NEX Unicode escape, not a Python NUL in source text.
  leaf=leaf.replace(' task_yield();throw(Problem<i64>(value,"λ\u0000🙂"));',' let owner:file=unwrap(file_open_read("input"));task_yield();throw(owner);')
  middle=middle.replace('pub fn forward(value:i64)->i64 !{task,throw}','pub server fn forward(value:i64)->i64 !{task,fs,throw}').replace('catch(e:leaf::Problem<i64>) if reject(e.value)','catch(e:file) if reject(42)')
  app=app.replace('fn main()->unit !{task,io,throw}','server fn main()->unit !{task,fs,io,throw}').replace('catch(e:leaf::Problem<i64>)','catch(e:file)').replace('let answer:i64=e.value;','let answer:i64=42;').replace('  assert(e.note=="λ\\u0000🙂");','  assert(file_is_open(e));assert(file_close(e));').replace('  assert(e.note=="λ\u0000🙂");','  assert(file_is_open(e));assert(file_close(e));')
  watches=[{'expression':'e==e','value':True},{'expression':'e','file_identity':True}]
  effectful='file_is_open(e)'
 if language=='0.28':
  leaf=leaf.replace('!{task,throw}{','!{task,throw} requires(value==42) ensures(result=>false){').replace('!{task,fs,throw}{','!{task,fs,throw} requires(value==42) ensures(result=>false){')
 (root/'files').mkdir();(root/'files/input').write_bytes(b'abc')
 for name,text in [('leaf',leaf),('middle',middle),('app',app)]:
  d=root/name;d.mkdir();(d/'main.nex').write_text(text, newline="\n")
 (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'app/main.nex'})+'\n', newline="\n")
 source=a.mode=='source';leaf_shared=a.mode=='shared';middle_shared=a.mode in ['shared','mixed']
 architecture={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug','task_limits':{'steps':1000000,'timeout_ms':60000,'workers':2}}},'components':{
  'leaf':{'kind':'source' if source else 'shared_library' if leaf_shared else 'static_library','root':'leaf','entry':'leaf/main.nex','entry_function':'later','exports':['later']},
  'middle':{'kind':'source' if source else 'shared_library' if middle_shared else 'static_library','root':'middle','entry':'middle/main.nex','entry_function':'forward','exports':['forward','reject'],'dependencies':{'leaf':'source' if source else 'dynamic' if leaf_shared else 'static'}},
  'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'middle':'source' if source else 'dynamic' if middle_shared else 'static','leaf':'source'}}}}
 if source:
  for name in ['leaf','middle']:
   architecture['components'][name].pop('entry_function');architecture['components'][name].pop('exports')
 (root/'nex.build.json').write_text(json.dumps(architecture,indent=2)+'\n', newline="\n")
 request={'action':'debug','root':str(root),'source_language':language,'compiler':str(compiler),'adapter':'nex-dap'}
 (O/'debug.request.json').write_text(json.dumps(request)+'\n', newline="\n")
 env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'NEX_FILES_ROOT':str(root/'files'),'PYTHONDONTWRITEBYTECODE':'1'}
 started=time.monotonic();report={'ok':False,'scope':'explicit C++'+language+' native debugger','compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'mode':a.mode,'scenario':a.scenario,'resources':str(resources),'watches':watches,'frame_expression':frame_expression,'has_guard':guard,'out_of_scope_expression':out_of_scope,'effectful_expression':effectful,'environment':{'NEX_FILES_ROOT':str(root/'files')}}
 def save():(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 save()
 r=subprocess.run([str(args.probe),str(O/'debug.request.json')],cwd=root,env=env,text=True,capture_output=True,timeout=600)
 (O/'build.stdout').write_text(r.stdout, newline="\n");(O/'build.stderr').write_text(r.stderr, newline="\n");report['build_exit']=r.returncode;save()
 assert r.returncode==0,(r.stdout[-3500:],r.stderr[-3500:])
 built=json.loads(r.stdout);session=built['observation'];manifest_path=Path(session['manifest']);manifest=json.loads(manifest_path.read_text())
 report['manifest']=str(manifest_path);report['session']=session;save()
 function=next(f for f in manifest['functions'] if f['name']=='app::main');file=function['task_debug']['file'];line=next(i for i,l in enumerate(app.splitlines(),1) if 'let answer:' in l);report['catch_line']=line;save()
 commands=['settings set target.disable-aslr false','command script import '+json.dumps(manifest['formatter']),
  'nex-load-debug '+json.dumps(str(manifest_path))+' --compiler '+json.dumps(str(compiler)),
  'nex-task-break line '+json.dumps(file)+' '+str(line),'run','nex-task-stack','nex-task-values','nex-frame '+frame_expression,
  *['nex-eval '+w['expression'] for w in watches],'breakpoint disable','continue']
 argv=[os.environ.get('NEX_LLDB') or shutil.which('lldb'),'--no-lldbinit','--batch',session['launch']['program']]
 for command in commands:argv+=['-o',command]
 (O/'lldb-command.json').write_text(json.dumps(argv,ensure_ascii=False,indent=2)+'\n', newline="\n")
 r=subprocess.run(argv,cwd=root,env=env,text=True,capture_output=True,timeout=180)
 (O/'lldb.stdout').write_text(r.stdout, newline="\n");(O/'lldb.stderr').write_text(r.stderr, newline="\n")
 rows=[json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
 report.update(lldb_exit=r.returncode,rows=rows,seconds=round(time.monotonic()-started,3))
 def matches(spec,value):
  if spec.get('file_identity'):return isinstance(value,dict) and set(value)=={'file'} and isinstance(value['file'],str) and value['file'].isdigit() and int(value['file'])>0
  return value==spec['value'] and type(value)==type(spec['value'])
 expected_schema='nex.task-expression/1' if a.mode=='source' else 'nex.task-expression/2'
 report['ok']=r.returncode==0 and all(any(v.get('schema')==expected_schema and v.get('expression')==w['expression'] and matches(w,v.get('value')) for v in rows) for w in watches) and 'exited with status = 0' in r.stdout
 save();print(json.dumps({'ok':report['ok'],'build_exit':report['build_exit'],'lldb_exit':r.returncode,'report':str(O/'report.json')}))

 assert report["ok"],str(O/"report.json")
 return report

def run_dap(directory):
 a=SimpleNamespace(case=directory,compiler=args.nex)
 O=a.case.resolve();compiler=a.compiler.resolve();base=json.loads((O/'report.json').read_text());session=base['session'];manifest=json.loads(Path(session['manifest']).read_text());root=O/'project';W=args.source_root
 sys.path.insert(0,str(W/'tests'));previous=sys.argv;sys.argv=[sys.argv[0],str(compiler)]
 try:from debugging import DAP
 finally:sys.argv=previous
 trace=[]
 class Recorded(DAP):
  def send(self,command,arguments=None):trace.append({'request':command,'arguments':arguments});return super().send(command,arguments)
  def wait(self,predicate,timeout=30):
   result=super().wait(predicate,timeout);trace.append({'response_or_event':result});return result
 backend=shutil.which('lldb-dap') or subprocess.check_output(['xcrun','--find','lldb-dap'],text=True).strip()
 os.environ['NEX_RESOURCE_DIR']=str(args.resources or args.source_root);os.environ['PYTHONDONTWRITEBYTECODE']='1';os.environ.update(base.get('environment',{}))
 adapter=Recorded([sys.executable,manifest['dap_adapter'],'--backend',backend],O)
 report={'ok':False,'mode':base['mode'],'scenario':base.get('scenario','record'),'real_NEX_DAP':True,'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'scope':'explicit C++'+language+' native debugger','observations':[]};started=time.monotonic();hidden=[]
 def save():(O/'dap-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 def reject(command,arguments):
  identity=adapter.send(command,arguments);value=adapter.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==identity)
  assert not value['success'],value;return value
 def reject_effect(frame):
  value=reject('evaluate',{'expression':base.get('effectful_expression','task_yield()'),'frameId':frame,'context':'watch'})
  message=value['message'];raw=message[message.index('error: ')+7:];diagnostic=json.JSONDecoder().raw_decode(raw)[0]
  assert diagnostic['code']=='E_EFFECT' and diagnostic['frontend']['language']==language,diagnostic
  report.setdefault('watch_diagnostics',[]).append(diagnostic);report['effectful_watch_rejected']=True
 specs=base.get('watches',[{'expression':'e.value','value':'42'},{'expression':'e.note','value':'λ\0🙂'}])
 def observe(frame,where):
  for spec in specs:
   value=adapter.request('evaluate',{'expression':spec['expression'],'frameId':frame,'context':'watch'})['nex'];wire=value['value']
   if spec.get('file_identity'):assert isinstance(wire,dict) and set(wire)=={'file'} and isinstance(wire['file'],str) and wire['file'].isdigit() and int(wire['file'])>0,value
   else:assert wire==spec['value'] and type(wire)==type(spec['value']),value
   if base['mode']=='source':
    assert value['schema']=='nex.task-expression/1' and value['language']==language and value['revision']==manifest['revision'] and 'source_identity' not in value,value
    identity={'combined_source_revision':value['revision'],'language':value['language']}
   else:identity=value['source_identity']
   if where=='guard caller' and base['mode']!='source':
    owner={'source':'app','static':'app','shared':'middle','mixed':'middle'}[base['mode']]
    assert identity['component']=='middle' and identity['owner_image']==owner,identity
   report['observations'].append({'where':where,'expression':spec['expression'],'value':wire,'source_identity':identity})
 try:
  for name in ['app','leaf','middle']:
   file=root/name/'main.nex';renamed=file.with_suffix('.source-absent');file.rename(renamed);hidden.append((file,renamed))
  assert all(not file.exists() for file,_ in hidden)
  report['source_absent_during_watch']=True;save()
  adapter.request('initialize',{'clientID':'nex-typed-debug-preflight','adapterID':'nex','linesStartAt1':True,'columnsStartAt1':True,'pathFormat':'path'})
  launch=adapter.send('launch',{'program':session['launch']['program'],'cwd':str(root),'stopOnEntry':False,'nexTaskDebug':True,
   'initCommands':['settings set target.disable-aslr false','command script import '+json.dumps(manifest['formatter']),
    'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(str(compiler))]})
  adapter.event('initialized')
  point=adapter.request('setFunctionBreakpoints',{'breakpoints':[{'name':'middle::reject'}] if base.get('has_guard',True) else []})
  if base.get('has_guard',True):assert point['breakpoints'][0]['verified'],point
  appfn=next(f for f in manifest['functions'] if f['name']=='app::main');file=appfn['task_debug']['file']
  point=adapter.request('setBreakpoints',{'source':{'path':file},'breakpoints':[{'line':base.get('catch_line',8)}]});assert point['breakpoints'][0]['verified'],point
  adapter.request('configurationDone');adapter.response(launch)
  stop=adapter.event('stopped');assert stop['allThreadsStopped']
  tasks=adapter.request('threads');selected=tasks['nex']['selected'];stack=adapter.request('stackTrace',{'threadId':selected})
  if base.get('has_guard',True):
   assert [v['name'] for v in stack['stackFrames']][:3]==['middle::reject','middle::forward','app::main'],stack
   parent=stack['stackFrames'][1]['id'];scope=adapter.request('scopes',{'frameId':parent})['scopes'][0]['variablesReference']
   values=adapter.request('variables',{'variablesReference':scope})['variables'];assert any(v['name']=='e' for v in values),values
   observe(parent,'guard caller')
   reject_effect(parent)
   adapter.request('continue',{'threadId':selected});stop=adapter.event('stopped');assert stop['allThreadsStopped']
   reject('variables',{'variablesReference':scope});report['stale_guard_variables_rejected']=True
  stack=adapter.request('stackTrace',{'threadId':selected});assert stack['stackFrames'][0]['name']=='app::main',stack
  frame=stack['stackFrames'][0]['id'];scope=adapter.request('scopes',{'frameId':frame})['scopes'][0]['variablesReference']
  observe(frame,'catch after yield')
  reject_effect(frame)
  reject('evaluate',{'expression':base.get('out_of_scope_expression','code'),'frameId':frame,'context':'watch'});report['sibling_handler_binding_rejected']=True
  adapter.request('next',{'threadId':selected});stop=adapter.event('stopped');assert stop['allThreadsStopped']
  reject('variables',{'variablesReference':scope});report['stale_catch_variables_rejected']=True
  reject('evaluate',{'expression':'e.value','frameId':frame,'context':'watch'});report['stale_catch_frame_rejected']=True
  fresh=adapter.request('stackTrace',{'threadId':selected});freshframe=fresh['stackFrames'][0]['id']
  spec=specs[0];watch=adapter.request('evaluate',{'expression':spec['expression'],'frameId':freshframe,'context':'watch'})['nex'];assert watch['value']==spec['value'] and type(watch['value'])==type(spec['value'])
  adapter.request('setBreakpoints',{'source':{'path':file},'breakpoints':[]});adapter.request('setFunctionBreakpoints',{'breakpoints':[]})
  adapter.request('continue',{'threadId':selected});exited=adapter.event('exited');assert exited['exitCode']==0,exited
  report.update(ok=True,exit_code=0,all_threads_stopped=True,seconds=round(time.monotonic()-started,3));save()
 finally:
  try:adapter.close()
  finally:
   for file,renamed in hidden:renamed.rename(file)
   (O/'dap-protocol.json').write_text(json.dumps({'trace':trace,'pending':adapter.pending},ensure_ascii=False,indent=2)+'\n', newline="\n");save()
 print(json.dumps({'ok':report['ok'],'real_NEX_DAP':True,'typed_watches':len(report['observations'])+1,'report':str(O/'dap-report.json')}))

 assert report["ok"],str(O/"dap-report.json")
 return report

def run_synchronous(directory):
 O=directory;O.mkdir();root=O/'project';root.mkdir()
 source=r'''module synchronous;
 struct Problem<T>{value:T;note:str;}
 fn fail(value:i64)->i64 !{throw}{throw(Problem<i64>(value,"λ\u0000🙂"));}
 fn main()->unit !{io,throw}{
  try{fail(42);assert(false);}
  catch(e:Problem<i64>){
   let answer:i64=e.value;
   assert(e.note=="λ\u0000🙂");
   print(answer);
  }
  catch(code,message){assert(false);}
 }
 '''
 if language=='0.28':source=source.replace('fn fail(value:i64)->i64 !{throw}{','fn fail(value:i64)->i64 !{throw} requires(value==42) ensures(result=>false){')
 (root/'main.nex').write_text(source, newline="\n");(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n', newline="\n")
 (root/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{'app':{'kind':'executable','root':'.','entry':'main.nex'}}})+'\n', newline="\n")
 compiler=args.nex;request={'action':'debug','root':str(root),'source_language':language,'compiler':str(compiler),'adapter':'nex-dap'};(O/'request.json').write_text(json.dumps(request)+'\n', newline="\n")
 env={**os.environ,'NEX_RESOURCE_DIR':str(args.resources or args.source_root),'PYTHONDONTWRITEBYTECODE':'1'}
 r=subprocess.run([str(args.probe),str(O/'request.json')],cwd=root,env=env,text=True,capture_output=True,timeout=300);(O/'build.stdout').write_text(r.stdout, newline="\n");(O/'build.stderr').write_text(r.stderr, newline="\n");assert r.returncode==0,(r.stdout,r.stderr)
 session=json.loads(r.stdout)['observation'];m=json.loads(Path(session['manifest']).read_text());assert m['schema']=='nex.debug/1',m['schema']
 file=m['sources'][0]['debug_path'];line=next(i for i,l in enumerate(source.splitlines(),1) if 'let answer:' in l)
 argv=[os.environ.get('NEX_LLDB') or shutil.which('lldb'),'--no-lldbinit','--batch',session['launch']['program']]
 for command in ['settings set target.disable-aslr false','command script import '+json.dumps(m['formatter']),
  'nex-load-debug '+json.dumps(session['manifest'])+' --compiler '+json.dumps(str(compiler)),
  'breakpoint set --file '+json.dumps(file)+' --line '+str(line),'run','nex-frame e','nex-eval e.value','nex-eval e.note','breakpoint disable','continue']:
  argv+=['-o',command]
 r=subprocess.run(argv,cwd=root,env=env,text=True,capture_output=True,timeout=120);(O/'lldb.stdout').write_text(r.stdout, newline="\n");(O/'lldb.stderr').write_text(r.stderr, newline="\n")
 rows=[json.loads(l) for l in r.stdout.splitlines() if l.startswith('{')]
 ok=r.returncode==0 and any(v.get('schema')=='nex.expression/1' and v.get('expression')=='e.value' and v.get('value')=='42' for v in rows) and any(v.get('expression')=='e.note' and v.get('value')=='λ\0🙂' for v in rows) and 'exited with status = 0' in r.stdout
 report={'ok':ok,'synchronous_DWARF':True,'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'session':session,'lldb_exit':r.returncode,'rows':rows};(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n");print(json.dumps({'ok':ok,'report':str(O/'report.json')}))

 assert report["ok"],str(O/"report.json")
 return report

report={'ok':False,'public027_CLI_enabled':False,'cases':[],'compiler_sha256':hashlib.sha256(args.nex.read_bytes()).hexdigest()}
started=time.monotonic()
for scenario,mode in [('record','source'),('record','static'),('record','shared'),('record','mixed'),('list','mixed'),('legacy','mixed'),('file','mixed')]:
 directory=output/(scenario+'-'+mode)
 lldb=run_case(scenario,mode,directory);dap=run_dap(directory)
 assert lldb['ok'] and dap['ok']
 report['cases'].append({'scenario':scenario,'mode':mode,'real_LLDB':True,'real_NEX_DAP':True,'source_absent':dap['source_absent_during_watch'],'passed':True})
 (output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
synchronous=run_synchronous(output/'synchronous-source');assert synchronous['ok']
report['cases'].append({'scenario':'synchronous','mode':'source','real_DWARF_LLDB':True,'passed':True})
report.update(ok=True,seconds=round(time.monotonic()-started,3))
(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
print(json.dumps({'ok':True,'cases':len(report['cases']),'report':str(output/'report.json')}))
