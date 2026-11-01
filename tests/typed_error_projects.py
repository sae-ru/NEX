"""Explicit027 source/static/shared/mixed project delivery acceptance."""
from pathlib import Path
import argparse,json,os,subprocess,time,hashlib,tempfile,shutil,copy

p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--compiler',type=Path);p.add_argument('--output',type=Path);p.add_argument('--sync-only',action='store_true');p.add_argument('--mode',action='append',choices=['source','static','shared','mixed']);a=p.parse_args()
O=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-typed-error-projects-'));O.mkdir(exist_ok=a.output is None);started=time.monotonic()
report={'ok':False,'language':'0.27','public027_enabled':False,'cases':[],'commands':[]}
LEAF=r'''module leaf;
pub struct Problem<T>{value:T;}
pub fn pure(value:i64)->i64 !{throw}{throw(Problem<i64>(value));}
pub fn text()->unit !{throw}{throw(Problem<str>("λ🙂"));}
pub fn later(value:i64)->i64 !{task,throw}{task_yield();return pure(value);}
pub fn next(value:i64)->i64{return value+1;}
pub fn callback(value:i64)->unit !{task,throw}{task_yield();throw(fn()->i64{return value;});}
pub server fn owned_file()->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));task_yield();throw(f);}
'''
MIDDLE=r'''module middle;
import "../leaf/main.nex" as leaf;
pub fn pure(value:i64)->i64 !{throw}{return leaf::pure(value);}
pub fn reject(value:i64)->bool !{task}{task_yield();assert(value==42);return false;}
pub fn forward(value:i64)->i64 !{task,throw}{
 try{return leaf::later(value);}
 catch(e:leaf::Problem<i64>) if reject(e.value){return 0;}
 finally{task_yield();}
}
pub fn text()->unit !{throw}{leaf::text();}
pub fn next(value:i64)->i64 !{task}{task_yield();return leaf::next(value);}
pub fn callback(value:i64)->unit !{task,throw}{leaf::callback(value);}
pub server fn owned_file()->unit !{task,fs,throw}{leaf::owned_file();}
'''
APP=r'''module app;
import "../middle/main.nex" as middle;
import "../leaf/main.nex" as leaf;
server fn main()->unit !{task,fs,io,throw}{
 try{middle::pure(42);assert(false);}
 catch(e:leaf::Problem<i64>){assert(e.value==42);}
 catch(c,m){assert(false);}
 try{
  with_tasks(2,fn(s:task_scope)->i64 !{task,throw}{
   let child:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{return middle::forward(42);});
   return task_wait(child);
  });assert(false);
 }catch(e:leaf::Problem<i64>){task_yield();assert(e.value==42);}
 catch(c,m){assert(false);}
 try{middle::text();assert(false);}
 catch(e:leaf::Problem<i64>) if middle::reject(e.value){assert(false);}
 catch(e:leaf::Problem<str>){assert(e.value=="λ🙂");}
 catch(c,m){assert(false);}
 try{middle::callback(42);assert(false);}
 catch(f:fn()->i64){task_yield();assert(f()==42);}
 catch(c,m){assert(false);}
 try{middle::owned_file();assert(false);}
 catch(f:file){task_yield();assert(file_is_open(f));assert(len(unwrap(file_read(f,1)))==1);assert(file_close(f));}
 catch(c,m){assert(false);}
 assert(middle::next(41)==42);print(42);
}
'''
SYNC_LEAF=r'''module leaf;
pub struct Problem<T>{value:T;}
pub fn pure(value:i64)->i64 !{throw}{throw(Problem<i64>(value));}
pub fn text()->unit !{throw}{throw(Problem<str>("λ🙂"));}
pub fn later(value:i64)->i64 !{throw}{return pure(value);}
pub fn next(value:i64)->i64{return value+1;}
pub fn callback(value:i64)->unit !{throw}{throw(fn()->i64{return value;});}
'''
SYNC_MIDDLE=r'''module middle;
import "../leaf/main.nex" as leaf;
pub fn pure(value:i64)->i64 !{throw}{return leaf::pure(value);}
pub fn reject(value:i64)->bool{assert(value==42);return false;}
pub fn forward(value:i64)->i64 !{throw}{
 try{return leaf::later(value);}
 catch(e:leaf::Problem<i64>) if reject(e.value){return 0;}
 finally{assert(leaf::next(41)==42);}
}
pub fn text()->unit !{throw}{leaf::text();}
pub fn next(value:i64)->i64{return leaf::next(value);}
pub fn callback(value:i64)->unit !{throw}{leaf::callback(value);}
'''
SYNC_APP=r'''module app;
import "../middle/main.nex" as middle;
import "../leaf/main.nex" as leaf;
fn main()->unit !{io,throw}{
 try{middle::pure(42);assert(false);}
 catch(e:leaf::Problem<i64>){assert(e.value==42);}
 catch(c,m){assert(false);}
 try{middle::forward(42);assert(false);}
 catch(e:leaf::Problem<i64>){assert(e.value==42);}
 catch(c,m){assert(false);}
 try{middle::text();assert(false);}
 catch(e:leaf::Problem<i64>) if middle::reject(e.value){assert(false);}
 catch(e:leaf::Problem<str>){assert(e.value=="λ🙂");}
 catch(c,m){assert(false);}
 try{middle::callback(42);assert(false);}
 catch(f:fn()->i64){assert(f()==42);}
 catch(c,m){assert(false);}
 assert(middle::next(41)==42);print(42);
}
'''
def save():
 report['seconds']=round(time.monotonic()-started,3);(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
def request(root,label,action,expected=0,**extra):
 data={'root':str(root),'source_language':'0.27','action':action,'component':'app',**extra};file=O/(label+'.request.json');file.write_text(json.dumps(data)+'\n', newline="\n")
 r=subprocess.run([str(Path(a.probe).resolve()),str(file)],text=True,capture_output=True,timeout=600,env={**os.environ,'NEX_FILES_ROOT':str(root/'files')})
 (O/(label+'.stdout')).write_text(r.stdout, newline="\n");(O/(label+'.stderr')).write_text(r.stderr, newline="\n")
 report['commands'].append({'label':label,'action':action,'exit_code':r.returncode});save()
 assert r.returncode==expected,(label,r.stdout[-4000:],r.stderr[-4000:])
 return json.loads(r.stdout)
try:
 for mode in ([] if a.sync_only else a.mode or ['source','static','shared','mixed']):
  root=O/mode;root.mkdir();(root/'files').mkdir();(root/'files/input').write_bytes(b'abc')
  for name,text in [('leaf',LEAF),('middle',MIDDLE),('app',APP)]:
   d=root/name;d.mkdir();(d/'main.nex').write_text(text, newline="\n")
  (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':'app/main.nex'})+'\n', newline="\n")
  leaf_shared=mode=='shared';middle_shared=mode in ['shared','mixed'];source=mode=='source'
  manifest={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'},'release':{'profile':'release'},'measured':{'profile':'profile'}},'components':{
   'leaf':{'kind':'source' if source else 'shared_library' if leaf_shared else 'static_library','root':'leaf','entry':'leaf/main.nex','entry_function':'later','exports':['pure','text','later','next','callback','owned_file']},
   'middle':{'kind':'source' if source else 'shared_library' if middle_shared else 'static_library','root':'middle','entry':'middle/main.nex','entry_function':'forward','exports':['pure','text','forward','reject','next','callback','owned_file'],'dependencies':{'leaf':'source' if source else 'dynamic' if leaf_shared else 'static'}},
   'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'middle':'source' if source else 'dynamic' if middle_shared else 'static','leaf':'source'}}}}
  if source:
   for name in ['leaf','middle']:
    manifest['components'][name].pop('entry_function');manifest['components'][name].pop('exports')
  (root/'nex.build.json').write_text(json.dumps(manifest,indent=2)+'\n', newline="\n")
  if mode=='mixed':
   invalid=copy.deepcopy(manifest);invalid['components']['app']['dependencies']['leaf']='static'
   (root/'nex.build.json').write_text(json.dumps(invalid)+'\n', newline="\n")
   rejected=request(root,'duplicate-owner','plan',expected=1);assert rejected['code']=='E_TASK_PROVIDER'
   assert not (root/'.nex').exists()
   (root/'nex.build.json').write_text(json.dumps(manifest,indent=2)+'\n', newline="\n")
  for profile in ['debug','release']:
   label=mode+'-'+profile;plan=request(root,label+'-plan','plan',configuration=profile)
   assert plan['language']=='0.27' and not plan['graph_store_opened']
   if not source:
    expected='nex.project-static-task-linkage/5' if mode=='static' else 'nex.project-task-linkage/14'
    for c in plan['components']:
     linkage=c['task_linkage'];assert linkage['schema']==expected and linkage['execution_abi']==7
     assert all(i['calling_mode']=='task-code/7' for i in linkage['imports'])
   built=request(root,label+'-run','run',configuration=profile)
   actual=built['observation'];assert actual['exit_code']==0 and actual['stdout']=='42\n' and not actual['stderr'],actual
   for artifact in built['artifacts']:
    if 'artifact' not in artifact:continue
    provider=Path(artifact['artifact']).parent/'task-provider.json'
    if provider.exists():
     record=json.loads(provider.read_text());assert record['schema']=='nex.native-task-provider/14' and record['language']=='0.27' and record['descriptor_abi']==0x4e45585400000007
   assert not (root/'.nex/graph.db').exists()
   report['cases'].append({'mode':mode,'profile':profile,'passed':True,'stdout':'42\n'});save()
  if mode=='mixed':
   captured=request(root,'capture','capture');capture=O/'capture.json';capture.write_text(json.dumps(captured,ensure_ascii=False)+'\n', newline="\n")
   assert request(root,'validate-capture','validate',capture=str(capture))['ok']
   for tag,edit in [
    ('old-language',lambda c:c.update(language='0.26')),
    ('wrong-abi',lambda c:c['expectations']['debug'][0]['task_linkage'].update(execution_abi=6)),
    ('retagged-schema',lambda c:c['expectations']['debug'][0]['task_linkage'].update(schema='nex.project-task-linkage/11')),
   ]:
    changed=copy.deepcopy(captured);edit(changed);bad=O/(tag+'.json');bad.write_text(json.dumps(changed)+'\n', newline="\n")
    rejected=request(root,tag,'validate',expected=1,capture=str(bad));assert rejected['code']=='E_PROJECT_CAPTURE'
   restored=request(root,'restore','restore',capture=str(capture),directory=str(O/'restored'))
   replay=Path(restored['root']);(replay/'files').mkdir();(replay/'files/input').write_bytes(b'abc')
   rebuilt=request(replay,'replay-run','run');assert rebuilt['observation']['exit_code']==0 and rebuilt['observation']['stdout']=='42\n'
   assert not (replay/'.nex/graph.db').exists()
   report['cases'].append({'mode':mode,'capture_replay':True,'retagged_capture_rejected':True,'passed':True});save()
   measured=request(root,'measured','profile',configuration='measured',profile_output=str(O/'profile.json'))
   assert measured['observation']['stdout']=='42\n'
   profile=json.loads((O/'profile.json').read_text());assert profile['ok'] and not profile['incomplete'] and profile['invalid_transitions']==0
   assert all(pool['live']==0 and pool['allocations']==pool['frees'] for pool in profile['memory'])
   assert next(f['calls'] for f in profile['functions'] if f['name']=='middle::reject')==1
   for artifact in measured['artifacts']:
    record=json.loads((Path(artifact['artifact']).parent/'task-provider.json').read_text());assert record['schema']=='nex.native-task-provider/15' and record['descriptor_abi']==0x4e45585400000007
   report['cases'].append({'mode':mode,'profile_memory_zero':True,'passed':True});save()
   if a.compiler:
    packaged=request(root,'package','package',package_directory=str(O/'package'),compiler=str(a.compiler.resolve()))
    assert packaged['ok'] and packaged['language']=='0.27'
    moved=O/'moved λ package';(O/'package').rename(moved);cache=root/'.nex';hidden=root/'.nex-hidden';cache.rename(hidden)
    try:
     environment={k:v for k,v in os.environ.items() if k not in ['NEX_RESOURCE_DIR','NEX_CLANG','NEX_NODE','NEX_NPM']}
     environment['NEX_FILES_ROOT']=str(root/'files')
     r=subprocess.run([str(moved/'apps/app/bin/app'),'--nex-task-workers','4'],text=True,capture_output=True,env=environment,timeout=60)
     (O/'moved.stdout').write_text(r.stdout, newline="\n");(O/'moved.stderr').write_text(r.stderr, newline="\n")
     assert r.returncode==0 and r.stdout=='42\n' and not r.stderr,(r.returncode,r.stdout,r.stderr)
    finally:hidden.rename(cache)
    report['cases'].append({'mode':mode,'relocated_package_source_absent':True,'workers':4,'passed':True});save()
   # All earlier source/receipt bytes are retained in the captured frontier.
   # Rebuild only the root entry to test the public uncaught-error boundary.
   (root/'app/main.nex').write_text('module app;import "../middle/main.nex" as middle;fn main()->unit !{task,throw}{task_yield();middle::text();}\n', newline="\n")
   uncaught=request(root,'uncaught','run')['observation'];assert uncaught['exit_code']==70 and not uncaught['stdout']
   rows=[json.loads(line.split(' ',1)[1]) for line in uncaught['stderr'].splitlines() if line.startswith('NEX_SOURCE_EXCEPTION ')]
   assert len(rows)==1 and rows[0]['message']=='typed source error' and 'Problem' in rows[0]['code']
   assert 'λ🙂' not in uncaught['stderr'] and '\\u03bb' not in uncaught['stderr'] and 'payload' not in rows[0]
   report['cases'].append({'mode':mode,'generic_uncaught_message':True,'passed':True});save()
 for mode in a.mode or ['source','static','shared','mixed']:
  root=O/('sync-'+mode);root.mkdir();(root/'files').mkdir()
  for name,text in [('leaf',SYNC_LEAF),('middle',SYNC_MIDDLE),('app',SYNC_APP)]:
   d=root/name;d.mkdir();(d/'main.nex').write_text(text, newline="\n")
  (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':'app/main.nex'})+'\n', newline="\n")
  source=mode=='source';leaf_shared=mode=='shared';middle_shared=mode in ['shared','mixed']
  components={
   'leaf':{'kind':'source' if source else 'shared_library' if leaf_shared else 'static_library','root':'leaf','entry':'leaf/main.nex','entry_function':'later','exports':['pure','text','later','next','callback']},
   'middle':{'kind':'source' if source else 'shared_library' if middle_shared else 'static_library','root':'middle','entry':'middle/main.nex','entry_function':'forward','exports':['pure','text','forward','reject','next','callback'],'dependencies':{'leaf':'source' if source else 'dynamic' if leaf_shared else 'static'}},
   'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'middle':'source' if source else 'dynamic' if middle_shared else 'static','leaf':'source'}}}
  if source:
   for name in ['leaf','middle']:components[name].pop('entry_function');components[name].pop('exports')
  manifest={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'},'release':{'profile':'release'}},'components':components}
  (root/'nex.build.json').write_text(json.dumps(manifest,indent=2)+'\n', newline="\n")
  for profile in ['debug','release']:
   label='sync-'+mode+'-'+profile;plan=request(root,label+'-plan','plan',configuration=profile)
   assert plan['language']=='0.27' and not plan['graph_store_opened']
   assert all('task_linkage' not in c for c in plan['components'])
   built=request(root,label+'-run','run',configuration=profile)['observation']
   assert built['exit_code']==0 and built['stdout']=='42\n' and not built['stderr'],built
   assert not (root/'.nex/graph.db').exists()
   report['cases'].append({'mode':mode,'synchronous':True,'profile':profile,'passed':True});save()
 report['ok']=True;save();print(json.dumps({'ok':True,'cases':len(report['cases']),'seconds':report['seconds']}))
except BaseException as e:
 report['error']=repr(e);save();raise
finally:
 if report['ok'] and a.output is None:shutil.rmtree(O)
