"""Explicit027 checked web maps, production builds, workers and retained026 identity."""
from pathlib import Path
from types import SimpleNamespace
import argparse,base64,copy,hashlib,json,os,shutil,subprocess,tempfile,time

parser=argparse.ArgumentParser();parser.add_argument('project_probe',type=Path);parser.add_argument('reference_probe',type=Path);parser.add_argument('nex',type=Path)
parser.add_argument('--source-language',choices=['0.27','0.28'],default='0.27');parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--resources',type=Path);parser.add_argument('--output',type=Path)
args=parser.parse_args();language=args.source_language;W=args.source_root.resolve();output=(args.output if args.output else Path(tempfile.mkdtemp(prefix='nex-typed-web-'))).resolve()
output.mkdir(parents=True,exist_ok=args.output is None)
args.project_probe=args.project_probe.resolve();args.reference_probe=args.reference_probe.resolve();args.nex=args.nex.resolve()
env={**os.environ,'NEX_RESOURCE_DIR':str(args.resources.resolve() if args.resources else W),'PYTHONDONTWRITEBYTECODE':'1','NEX_NODE':os.environ.get('NEX_NODE','node'),'NEX_NPM':os.environ.get('NEX_NPM','npm')}

def build_case(variant):
 a=SimpleNamespace(variant=variant);O=output/variant;O.mkdir();root=O/'project';root.mkdir()
 original=(W/'examples/task-workers/main.nex').read_text().split('client test fn',1)[0]
 prefix=r'''struct UIFault<T>{value:T;}
 struct WorkerFault<T>{value:T;label:str;}
 struct ServerOnlyFault{secret:str;}
 client fn recover()->str{
  try{throw(UIFault<str>("λ\u0000🙂"));}
  catch(e:UIFault<i64>){return "wrong type";}
  catch(e:UIFault<str>){return str(len(e.value))+":42";}
  catch(code,message){return "unexpected legacy";}
 }
 client fn wrong_guard(value:str)->bool{assert(false);return true;}
 '''
 body=r'''client fn worker_compute(input: Input) -> Output !{task,throw} {
  task_yield();
  if input.mode=="loop"{while true{task_yield();}}
  if input.mode=="uncaught"{throw(WorkerFault<i64>(42,"PRIVATE_TYPED_WORKER_PAYLOAD λ\u0000🙂"));}
  try{
   if input.mode=="trap"{return Output(1/0,"",utf8_bytes(""));}
   let unused:i64=with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{
    let job:task<i64>=task_spawn(scope,fn()->i64 !{task,throw}{
     task_yield();
     if input.mode=="legacy"{throw("LEGACY","PRIVATE_TYPED_LEGACY λ\u0000🙂");}
     if input.mode=="callable"{throw(fn()->i64{return input.seed+input.rounds;});}
     throw(WorkerFault<list<i64>>([input.seed+input.rounds],"PRIVATE_TYPED_WORKER_PAYLOAD λ\u0000🙂"));
    });return task_wait(job);
   });assert(false);return Output(unused,"",utf8_bytes(""));
  }
  catch(e:WorkerFault<str>) if wrong_guard(e.value){return Output(0,"wrong type",utf8_bytes(""));}
  catch(e:WorkerFault<list<i64>>){
   task_yield();assert(e.label=="PRIVATE_TYPED_WORKER_PAYLOAD λ\u0000🙂");
   if input.mode=="rethrow"{throw;}
   return Output(e.value[0],"Worker 🧠",utf8_bytes("A🧠\u0000"));
  }
  catch(callback:fn()->i64){task_yield();return Output(callback(),"Worker 🧠",utf8_bytes("A🧠\u0000"));}
  catch(code,message){if code=="LEGACY"{return Output(42,"legacy",utf8_bytes("A🧠\u0000"));}throw;}
  finally{task_yield();}
 }
 '''
 pure=r'''client fn worker_compute(input: Input) -> Output !{throw} {
  if input.mode=="loop"{while true{}}
  if input.mode=="uncaught"{throw(WorkerFault<i64>(42,"PRIVATE_TYPED_WORKER_PAYLOAD λ\u0000🙂"));}
  try{
   if input.mode=="trap"{return Output(1/0,"",utf8_bytes(""));}
   if input.mode=="legacy"{throw("LEGACY","PRIVATE_TYPED_LEGACY λ\u0000🙂");}
   if input.mode=="callable"{throw(fn()->i64{return input.seed+input.rounds;});}
   throw(WorkerFault<list<i64>>([input.seed+input.rounds],"PRIVATE_TYPED_WORKER_PAYLOAD λ\u0000🙂"));
  }
  catch(e:WorkerFault<str>) if wrong_guard(e.value){return Output(0,"wrong type",utf8_bytes(""));}
  catch(e:WorkerFault<list<i64>>){
   assert(e.label=="PRIVATE_TYPED_WORKER_PAYLOAD λ\u0000🙂");if input.mode=="rethrow"{throw;}
   return Output(e.value[0],"Worker 🧠",utf8_bytes("A🧠\u0000"));
  }
  catch(callback:fn()->i64){return Output(callback(),"Worker 🧠",utf8_bytes("A🧠\u0000"));}
  catch(code,message){if code=="LEGACY"{return Output(42,"legacy",utf8_bytes("A🧠\u0000"));}throw;}
 }
 '''
 begin=original.index('client fn worker_compute(');end=original.index('client fn update(',begin)
 text=original[:begin]+prefix+(body if a.variant=='async' else pure)+original[end:]
 text=text.replace('  if event.name == "click"','  if event.name=="recover"{return State(state.sequence,state.current,recover(),state.clicks);}\n  if event.name == "click"',1)
 old='event.name == "start" || event.name == "slow" || event.name == "trap" || event.name == "timeout"'
 new=old+' || event.name=="uncaught" || event.name=="rethrow" || event.name=="legacy" || event.name=="callable"';assert old in text;text=text.replace(old,new,1)
 old='    return [worker::request(after.current, Input(9007199254740993, 7, "normal"), "done", 10000)];'
 new='''    if event.name=="uncaught" || event.name=="rethrow" || event.name=="legacy" || event.name=="callable"{return [worker::request(after.current,Input(9007199254740993,7,event.name),"done",10000)];}
 '''+old;assert old in text;text=text.replace(old,new,1)
 old='web::button("Trap", "trap")';new='web::button("Recover typed", "recover"), web::button("Typed uncaught", "uncaught"), web::button("Typed rethrow", "rethrow"), web::button("Legacy error", "legacy"), web::button("Callable payload", "callable"), '+old;assert old in text;text=text.replace(old,new,1)
 text+='\nserver fn never_ship()->unit !{throw}{throw(ServerOnlyFault("SERVER_MUST_NOT_SHIP_150"));}\nclient fn unused_client()->str{return "UNUSED_CLIENT_MUST_NOT_SHIP_150";}\n'
 if language=='0.28':
  text=text.replace('worker_compute(input: Input) -> Output !{task,throw}', 'worker_compute(input: Input) -> Output !{task,throw} requires(input.rounds>=0 && input.mode!="pre") ensures(value=>input.mode!="post" && value.value>=0)')
  text=text.replace('worker_compute(input: Input) -> Output !{throw}', 'worker_compute(input: Input) -> Output !{throw} requires(input.rounds>=0 && input.mode!="pre") ensures(value=>input.mode!="post" && value.value>=0)')
  text=text.replace('client fn recover()->str{','client fn recover()->str ensures(value=>len(value)>0){')
  text=text.replace('event.name=="uncaught" || event.name=="rethrow" || event.name=="legacy" || event.name=="callable"','event.name=="uncaught" || event.name=="rethrow" || event.name=="legacy" || event.name=="callable" || event.name=="pre" || event.name=="post"')
  text=text.replace('web::button("Recover typed", "recover")','web::button("Contract pre", "pre"), web::button("Contract post", "post"), web::button("Recover typed", "recover")')

 (root/'main.nex').write_text(text, newline="\n");(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n', newline="\n")
 manifest={'schema':'nex.project-build/1','default_configuration':'release','configurations':{'release':{'profile':'release'},'debug':{'profile':'debug'}},'components':{'app':{'kind':'web','root':'.','entry':'main.nex'}}};(root/'nex.build.json').write_text(json.dumps(manifest)+'\n', newline="\n")
 report={'ok':False,'variant':a.variant,'scope':'explicit C++'+language+' checked web delivery','commands':[],'cases':[]};started=time.monotonic()
 def save():(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 def run(label,argv,cwd=root,timeout=600,expected=0):
  r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,text=True,capture_output=True,timeout=timeout);(O/(label+'.stdout')).write_text(r.stdout, newline="\n");(O/(label+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'label':label,'argv':list(map(str,argv)),'exit':r.returncode});save();assert r.returncode==expected,(label,r.stdout[-3500:],r.stderr[-3000:]);return r
 def request(label,action='build',**extra):
  data={'action':action,'root':str(root),'source_language':language,'configuration':'release',**extra};file=O/(label+'.request.json');file.write_text(json.dumps(data)+'\n', newline="\n");return json.loads(run(label,[args.project_probe,file]).stdout)
 plan=request('plan','plan');assert not plan['graph_store_opened'];checked=plan['components'][0]
 built=request('build');assert not built['graph_store_opened'];app=Path(built['artifacts'][0]['result']['directory']);report['generated_project']=str(app);save()
 for name,execution in [('nex-map.json','synchronous'),('nex-worker-map.json','task-generator' if a.variant=='async' else 'synchronous')]:
  m=json.loads((app/name).read_text());assert m['schema']=='nex.typescript-map/2' and m['language']==language and len(m['revision'])==64 and len(m['source_hash'])==64 and m['execution']==execution and 'public_revision' not in m,m
  assert m['revision']==checked['revision'] and m['source_hash']==checked['source_bundle_hash'],m
  assert m['task_source_exceptions']==(execution=='task-generator') and type(m['source_transfer_contracts']) is int and 0<=m['source_transfer_contracts']<=4096
  assert m['source_exceptions']=='nex.source-errors/2'
 metadata=json.loads((app/'nex-web.json').read_text());assert metadata['schema']=='nex.web/2' and metadata['language']==language
 assert metadata['revision']==checked['revision'] and metadata['key']==checked['web_projection']['key']
 main=(app/'src/program.ts').read_text();worker=(app/'src/worker-program.ts').read_text();assert 'PRIVATE_TYPED_WORKER_PAYLOAD' not in main and 'PRIVATE_TYPED_WORKER_PAYLOAD' in worker
 for file in list((app/'src').glob('*'))+list((app/'dist').rglob('*'))+[app/'nex-map.json',app/'nex-worker-map.json']:
  if file.is_file():
   data=file.read_bytes();assert b'SERVER_MUST_NOT_SHIP_150' not in data and b'UNUSED_CLIENT_MUST_NOT_SHIP_150' not in data and b'ServerOnlyFault' not in data,file
 driver=app/'src/probe.ts';driver.write_text('''import assert from 'node:assert/strict';
 import * as ui from './program.ts';
 const initial=ui.initial();const updated=ui.update(initial,ui.makeEvent('recover','','/'));
 assert.equal(initial.status,'Ready');assert.equal(updated.status,'3:42');assert(Object.isFrozen(ui.sourceErrorContracts));
 const sent:any[]=[];let closed=0;(globalThis as any).postMessage=(v:any)=>sent.push(v);(globalThis as any).close=()=>{++closed;};
 await import('./worker-entry.ts');await (globalThis as any).onmessage({data:{protocol:'nex.worker/1',ticket:1,body:JSON.stringify({seed:'9007199254740993',rounds:'7',mode:process.argv[2]})}});
 assert.equal(sent.length,1);assert.equal(closed,1);const result=sent[0];assert.equal(result.code,process.argv[3]);
 if(result.code===''){const value=JSON.parse(result.body);assert.equal(value.value,process.argv[2]==='legacy'?'42':'9007199254741000');assert.equal(value.data,EXPECTED_BYTES);}
 else {assert.equal(result.body,'');assert(!JSON.stringify(result).includes('PRIVATE_TYPED'));if(result.code==='E_SOURCE_EXCEPTION')assert.equal(result.message,'Uncaught NEX source exception');}
 process.stdout.write(JSON.stringify({ok:true,mode:process.argv[2],code:result.code})+'\\n');
 '''.replace('EXPECTED_BYTES',json.dumps(base64.b64encode('A🧠\0'.encode()).decode())), newline="\n")
 for mode,code in [('normal',''),('callable',''),('legacy',''),('uncaught','E_SOURCE_EXCEPTION'),('rethrow','E_SOURCE_EXCEPTION'),('trap','E_DIV_ZERO')]:
  run('node-'+mode,[env['NEX_NODE'],'--experimental-strip-types','--no-warnings',driver,mode,code]);report['cases'].append({'mode':mode,'Node_UI_and_worker_entry':True,'code':code,'passed':True});save()
 cached=request('cached-build');assert cached['artifacts'][0]['result']['cached']
 report.update(ok=True,production_build_passed=True,checked_maps=True,client_closure_only=True,seconds=round(time.monotonic()-started,3));save();print(json.dumps({'ok':True,'variant':a.variant,'cases':len(report['cases']),'project':str(app),'report':str(O/'report.json')}))

 assert report["ok"]
 return report

def agreement_cases():
 O=output/'agreement';O.mkdir();report={'ok':False,'cases':[],'commands':[]};started=time.monotonic()
 def save():(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 def run(label,argv,cwd=O,expected=0):
  r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,text=True,capture_output=True,timeout=600)
  (O/(label+'.stdout')).write_text(r.stdout, newline="\n");(O/(label+'.stderr')).write_text(r.stderr, newline="\n")
  report['commands'].append({'label':label,'exit':r.returncode});save();assert r.returncode==expected,(label,r.stdout[-3000:],r.stderr[-2500:]);return r
 for variant in ['async','pure']:
  source=(output/variant/'project/main.nex').read_text().replace('client fn','shared fn')
  source+='''\nfn main()->unit !{task,io,throw}{
  assert(recover()=="3:42");
  let value:Output=worker_compute(Input(9007199254740993,7,"normal"));assert(value.value==9007199254741000);
  assert(decode_utf8(value.data)==ok("A🧠\\u0000"));
  assert(worker_compute(Input(9007199254740993,7,"callable")).value==9007199254741000);
  assert(worker_compute(Input(0,0,"legacy")).value==42);
  print(42);
 }\n'''
  root=O/variant;root.mkdir();(root/'main.nex').write_text(source, newline="\n");(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n', newline="\n");(root/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'release','configurations':{'release':{'profile':'release'}},'components':{'app':{'kind':'executable','root':'.','entry':'main.nex'}}})+'\n', newline="\n")
  reference=json.loads(run(variant+'-reference',[args.reference_probe,('contracts-' if language=='0.28' else '')+'project-reference',root/'main.nex']).stdout);assert reference=={'kind':'return','value':None,'output':'42\n'},reference
  request=O/(variant+'.request.json');request.write_text(json.dumps({'action':'run','root':str(root),'source_language':language,'configuration':'release'})+'\n', newline="\n");native=json.loads(run(variant+'-native',[args.project_probe,request],root).stdout);actual=native['observation'];assert actual['exit_code']==0 and actual['stdout']=='42\n' and not actual['stderr'],actual
  generated=root/'retained-typescript';run(variant+'-typescript',[args.reference_probe,('contracts-' if language=='0.28' else '')+'project-typescript',root/'main.nex',generated]);mapping=json.loads((generated/'nex-map.json').read_text());assert mapping['schema']==('nex.development-typescript/028-1' if language=='0.28' else 'nex.development-typescript/027-3') and mapping['public_revision'] is False and 'revision' not in mapping
  (generated/'runner.ts').write_text("import { main, sourceErrorContracts } from './program.ts';import * as task from './nex-task-runtime.ts';await task.runTypedSourceErrors(task.call(()=>main()),sourceErrorContracts);\n", newline="\n")
  actual=run(variant+'-node',[env['NEX_NODE'],'--experimental-strip-types','--no-warnings',generated/'runner.ts']);assert actual.stdout=='42\n',actual.stdout
  assert not (root/'.nex/graph.db').exists()
  report['cases'].append({'variant':variant,'reference_native_Node_agreement':True,'retained_development_map_preserved':True,'stdout':'42\n','passed':True});save()
 golden=json.loads((Path(__file__).resolve().parent/'fixtures/web-026-sdk149-origin.json').read_text())
 control=O/'retained026';control.mkdir();(control/'main.nex').write_text(golden['source'], newline="\n")
 for name,text in golden['library_sources'].items():
  file=control/'lib'/name;file.parent.mkdir(parents=True,exist_ok=True);file.write_text(text, newline="\n")
 (control/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex','libraries':{'std':'lib'}})+'\n', newline="\n")
 (control/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{'app':{'kind':'web','root':'.','entry':'main.nex'}}})+'\n', newline="\n")
 request=O/'retained026.request.json';request.write_text(json.dumps({'action':'plan','root':str(control),'source_language':'0.26'})+'\n', newline="\n")
 new=json.loads(run('retained026-new',[args.project_probe,request],control).stdout)['components'][0]
 assert new['web_projection']==golden['web_projection'] and new['revision']==golden['revision'] and new['source_bundle_hash']==golden['source_bundle_hash']
 report['cases'].append({'genuine026_web_asset_and_source_identity_preserved':True,'passed':True})
 report.update(ok=True,seconds=round(time.monotonic()-started,3));save();return report

def contract_cases():
 O=output/'contracts';O.mkdir()
 text=(output/'async/project/main.nex').read_text();manifest=json.loads((output/'async/project/nex.build.json').read_text())
 report={'ok':False,'cases':[]}
 def save():(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
 def request(root,label,action,expected=0,**extra):
  data={'action':action,'root':str(root),'source_language':language,'configuration':'release',**extra};f=O/(label+'.request.json');f.write_text(json.dumps(data)+'\n', newline="\n");r=subprocess.run([str(args.project_probe),str(f)],cwd=root,env=env,text=True,capture_output=True,timeout=600);(O/(label+'.stdout')).write_text(r.stdout, newline="\n");(O/(label+'.stderr')).write_text(r.stderr, newline="\n");assert r.returncode==expected,(label,r.stdout[-2500:],r.stderr[-2000:]);return json.loads(r.stdout)
 begin=text.index('client fn worker_compute(');end=text.index('client fn update(',begin)
 negatives=[
  ('worker-io',text.replace('worker_compute(input: Input) -> Output !{task,throw}','worker_compute(input: Input) -> Output !{task,throw,io}'),{'E_WEB_SIGNATURE'}),
  ('UI-task',text.replace('client fn initial() -> State {','client fn initial() -> State !{task} {task_yield();'),{'E_TASK_UNIMPLEMENTED'}),
  ('UI-server',text.replace('client fn initial()','server fn initial()'),{'E_WEB_SIGNATURE'}),
  ('function-wire',text[:begin]+'client fn worker_compute(input:Input)->fn()->i64{return fn()->i64{return input.seed;};}\n'+text[end:],{'E_WEB_SIGNATURE'}),
  ('channel-wire',text[:begin]+'client fn worker_compute(input:channel<i64>)->i64 !{task}{return unwrap(task_recv(input));}\n'+text[end:],{'E_WEB_SIGNATURE'}),
  ('file-wire',text[:begin]+'server fn worker_compute(input:file)->file !{fs}{return input;}\n'+text[end:],{'E_WEB_SIGNATURE'}),
 ]
 for label,source,codes in negatives:
  root=O/label;root.mkdir();(root/'main.nex').write_text(source, newline="\n");(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':language,'entry':'main.nex'})+'\n', newline="\n");(root/'nex.build.json').write_text(json.dumps(manifest)+'\n', newline="\n")
  actual=request(root,label,'plan',expected=1);assert actual['code'] in codes,(label,actual);assert not (root/'.nex').exists()
  report['cases'].append({'rejection':label,'code':actual['code'],'no_generated_state':True,'passed':True});save()
 root=output/'async/project';r=subprocess.run([str(args.nex),'project','--kind','plan','--component','app','--configuration','release','--json'],cwd=root,env=env,text=True,capture_output=True);actual=json.loads(r.stdout)
 ordinary=json.loads(subprocess.check_output([str(args.nex),'describe','--kind','index','--json'],env=env,text=True))['language']
 if ordinary==language:
  assert r.returncode==0 and actual['language']==language and not actual['graph_store_opened'],actual
  control=request(root,'ordinary-CLI-control','plan');assert actual['components']==control['components'] and actual['plan_hash']==control['plan_hash']
 else:assert r.returncode==1 and actual['code']=='E_LANGUAGE_VERSION',actual
 report['cases'].append({'ordinary_CLI_language':ordinary,'selected_language':language,'explicit_selection_preserved':True,'passed':True});save()
 capture=request(root,'capture','capture');file=O/'capture.json';file.write_text(json.dumps(capture,ensure_ascii=False,indent=2)+'\n', newline="\n");assert request(root,'validate','validate',capture=str(file))['ok']
 restored=request(root,'restore','restore',capture=str(file),directory=str(O/'restored'));assert restored['language']==language;plan=request(Path(restored['root']),'restored-plan','plan');assert plan['language']==language and not plan['graph_store_opened']
 report['cases'].append({'checked027_web_capture_replay':True,'passed':True});save()
 packaged=request(root,'package','package',package_directory=str(O/'package'),compiler=str(args.nex));assert packaged['ok'] and packaged['language']==language
 moved=O/'relocated λ web';(O/'package').rename(moved);assert (moved/'web/app/index.html').exists()
 source=root/'main.nex';hidden=source.with_suffix('.source-absent');cache=root/'.nex';hidden_cache=root/'.nex-hidden';source.rename(hidden);cache.rename(hidden_cache)
 try:
  assert not source.exists() and not cache.exists()
  inventory=[p for p in moved.rglob('*') if p.is_file()]
  assert not any(p.name in ['nex','package-lock.json','package.json'] for p in inventory)
  for p in inventory:
   data=p.read_bytes();assert b'SERVER_MUST_NOT_SHIP_150' not in data and b'UNUSED_CLIENT_MUST_NOT_SHIP_150' not in data,p
  report['cases'].append({'relocated_source_absent_web_package':True,'requires_compiler_or_LLM':False,'passed':True});save()
 finally:hidden.rename(source);hidden_cache.rename(cache)
 for i,bad in enumerate(['fs/../escape','fs/.','fs/','/absolute','fs/x/./y']):
  value=copy.deepcopy(capture);value['project_root']=bad;file=O/('invalid-path-'+str(i)+'.json');file.write_text(json.dumps(value)+'\n', newline="\n")
  rejected=request(root,'invalid-path-'+str(i),'validate',expected=1,capture=str(file));assert rejected['code']=='E_PROJECT_CAPTURE'
  report['cases'].append({'strict_untrusted_path_rejected':bad,'passed':True})
 report['package']=str(moved);report['ok']=True;save();print(json.dumps({'ok':True,'cases':len(report['cases']),'report':str(O/'report.json')}))

 return report

report={'ok':False,'public027_CLI_enabled':True,'cases':[]}
for variant in ['async','pure']:
 value=build_case(variant);assert value['ok'];report['cases'].append({'variant':variant,'Node_cases':len(value['cases']),'production_build':True,'passed':True})
value=agreement_cases();assert value['ok'];report['engine_agreement_and_retained026_cases']=len(value['cases'])
value=contract_cases();assert value['ok'];report['boundary_capture_package_cases']=len(value['cases'])
report['ok']=True;(output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
print(json.dumps({'ok':True,'production_projects':2,'Node_cases':12,'engine_agreement_and_retained026_cases':report['engine_agreement_and_retained026_cases'],'boundary_capture_package_cases':report['boundary_capture_package_cases'],'report':str(output/'report.json')}))
