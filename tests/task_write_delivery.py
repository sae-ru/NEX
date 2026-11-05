"""Public025 CLI migration, binary providers, captured replay and packaging."""
import argparse,copy,hashlib,json,os,shutil,sqlite3,subprocess,tempfile,time
from collections import Counter
from contextlib import closing
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--compiler',required=True,type=Path);p.add_argument('--resources',type=Path);p.add_argument('--output',type=Path);p.add_argument('--package-notices',type=Path,help='Explicit operator nex.sdk-notices/1 catalogue for packaged private runtime dependencies');a=p.parse_args()
compiler=a.compiler.resolve();resources=(a.resources or Path(__file__).resolve().parents[1]).resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex public writes 🧠 ');root=Path(temporary.name).resolve()
(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'scope.nex'}), newline="\n");(root/'scope.nex').write_text('module scope;fn main()->unit{}', newline="\n")
base={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
for key in ('NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_FILES_LIMIT','NEX_PROFILE_OUTPUT','NEX_TRACY'):base.pop(key,None)
started=time.monotonic();report={'schema':'nex.public-task-write-delivery/1','ok':False,'state':'starting','compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'commands':[],'migrations':[],'projects':[],'actual_GPU_NPU_resources':False,'full_objective_complete':False}
package_notices=a.package_notices.resolve(strict=True) if a.package_notices else None
if package_notices:
 assert package_notices.is_file()
 report['package_notices']={'path':str(package_notices),'sha256':hashlib.sha256(package_notices.read_bytes()).hexdigest()}
package_flags=['--notices',package_notices] if package_notices else []
def save():report['seconds']=round(time.monotonic()-started,3);(root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n', newline="\n")
def process(name,args,cwd=None,env=None,expected=0):
 if package_notices:assert hashlib.sha256(package_notices.read_bytes()).hexdigest()==report['package_notices']['sha256'],'operator notice catalogue changed'
 report['state']=name;save();r=subprocess.run(list(map(str,args)),cwd=cwd or root,env={**base,**(env or {})},capture_output=True,text=True,timeout=600)
 out=root/(name+'.stdout');err=root/(name+'.stderr');out.write_text(r.stdout, newline="\n");err.write_text(r.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':list(map(str,args)),'cwd':str(cwd or root),'exit_code':r.returncode,'expected':expected,'stdout':str(out),'stderr':str(err)});save()
 if package_notices:assert hashlib.sha256(package_notices.read_bytes()).hexdigest()==report['package_notices']['sha256'],'operator notice catalogue changed'
 assert r.returncode==expected,(name,r.returncode,r.stdout,r.stderr)
 return r
serial=0
def cli(name,*args,cwd=None,env=None,expected=0):
 global serial
 serial+=1;return json.loads(process(f'{serial:03d}-'+name,[compiler,*args,'--json'],cwd,env,expected).stdout)
def state(database):
 with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=rw',uri=True)) as db:
  db.execute('PRAGMA query_only=ON');tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  return {'ddl':db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),'tables':{n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in tables}}
def retained(before,after):
 assert before['ddl']==after['ddl'] and len(before['tables'])==len(after['tables'])==16
 for name,rows in before['tables'].items():
  if name!='head':assert not (Counter(rows)-Counter(after['tables'][name])),name
 assert before['tables']['metadata']==after['tables']['metadata']
def write(path,value):path.write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n', newline="\n")
def artifacts(result):return {row['component']:row for row in result['artifacts']}
try:
 descriptor=cli('describe','describe');assert descriptor['version']=='0.28' and descriptor['task_file_writes']['public_enabled'] and descriptor['task_providers']['execution_task_abi']==7
 report['language']='0.28';report['toolchain']=cli('doctor','doctor')['version'];save()
 fixture=resources/'examples/task-write-migration/language-0.22-sdk131-task-writes.json'
 if not fixture.exists():fixture=resources/'tests/fixtures/language-0.22-sdk131-task-writes.json'
 metadata=json.loads(fixture.read_text());sql=fixture.with_suffix('.sql').read_bytes()
 assert metadata['language']=='0.22' and metadata['sdk']['binary_sha256']=='5f23165c9e1be54fbe504adc244ea65e5b6a66721a579db4a8d364f63e4a897f'
 assert hashlib.sha256(sql).hexdigest()==metadata['sql_sha256']=='f9f11160f3b16a7fcb949598a0c804e2230180a26a034e3e9dfe9545e0b8056e'
 for index,row in enumerate(metadata['revisions']):
  project=root/('migration-'+str(index));database=project/'.nex/graph.db';database.parent.mkdir(parents=True)
  with closing(sqlite3.connect(database)) as db:db.executescript(sql.decode())
  head=next(r for r in metadata['revisions'] if r['revision']==metadata['head'])
  for name,text in head['bundle']['files'].items():
   path=project/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text, newline="\n")
  manifest=project/'nex.json';write(manifest,{'schema':'nex.project/1','language':'0.22','entry':head['bundle']['entry']});physical=manifest.read_bytes();before=state(database)
  try:
   current=json.loads(physical);current['language']='0.28';write(manifest,current)
   refused=cli('no-implicit-upgrade','check',cwd=project,expected=1);assert refused['code']=='E_LANGUAGE_VERSION' and state(database)==before
  finally:manifest.write_bytes(physical)
  migrated=cli('migrate','migrate','--revision',row['revision'],'--expected-revision',metadata['head'],cwd=project)
  assert migrated['language']=='0.28' and migrated['origin_language']=='0.22' and migrated['origin_verified'] and not migrated['materialized'] and migrated['revision']!=row['revision']
  after=state(database);retained(before,after);assert manifest.read_bytes()==physical and after['tables']['head']==[(1,migrated['revision'])]
  data=project/'external-files';data.mkdir();env={'NEX_FILES_ROOT':str(data),'NEX_FILES_WRITE':'1'}
  reference=cli('migrated-eval','eval','--revision',migrated['revision'],cwd=project,env=env)
  task=any('!{task' in text for text in row['bundle']['files'].values());value=42 if task else 0;stdout='' if task else '42\n'
  native=cli('migrated-run','run','--revision',migrated['revision'],cwd=project,env=env,expected=value)
  assert reference['value']==value and reference['stdout']==native['stdout']==stdout and native['exit_code']==value
  assert cli('retained-old-rejection','eval','--revision',row['revision'],cwd=project,expected=1)['code']=='E_LANGUAGE_VERSION'
  repeated=cli('idempotent','migrate','--revision',migrated['revision'],cwd=project);assert repeated['revision']==migrated['revision'] and state(database)==after
  report['migrations'].append({'origin_revision':row['revision'],'revision':migrated['revision'],'origin_verified':True,'all16_tables_schema_rows_ids_preserved':True,'physical_projection_unchanged':True,'implicit_upgrade_rejected':True,'native_reference':True});save()
 text='NEX 🧠\0complete\ufeff'
 leaf='''module writer_leaf;
pub server fn save(text:str,data:bytes)->result<bool> !{task,fs}{
 let first:bool=file_write_text("text",text)?;return file_write_bytes("bytes",data);
}
'''
 mid='''module writer_mid;import "../leaf/value.nex" as leaf;
pub server fn save(text:str,data:bytes)->result<bool> !{task,fs}{return leaf::save(text,data);}
'''
 app='''module writer_app;import "../mid/value.nex" as mid;
server fn solve()->result<bool> !{task,fs,throw}{
 return with_tasks(2,server fn(scope:task_scope)->result<bool> !{task,fs,throw}{
  let child:task<result<bool>>=task_spawn(scope,server fn()->result<bool> !{task,fs}{
   return mid::save("NEX 🧠\\u0000complete\\ufeff",unwrap(bytes([0,78,69,88,255])));
  });return task_wait(child);
 });
}
server fn main()->unit !{task,fs,io,throw}{assert(unwrap(solve()));print(42);}
server test fn writes()->unit !{task,fs,throw}{assert(unwrap(solve()));}
'''
 for mode in ('static','shared','mixed'):
  project=root/mode;data=root/(mode+'-files');data.mkdir();env={'NEX_FILES_ROOT':str(data),'NEX_FILES_WRITE':'1'}
  for name,body in [('leaf',leaf),('mid',mid),('app',app)]:
   path=project/name;path.mkdir(parents=True);(path/('main.nex' if name=='app' else 'value.nex')).write_text(body, newline="\n")
  write(project/'nex.json',{'schema':'nex.project/1','language':'0.28','entry':'app/main.nex'})
  leaf_kind='shared_library' if mode=='shared' else 'static_library';mid_kind='static_library' if mode=='static' else 'shared_library'
  definition={'schema':'nex.project-build/1','default_configuration':'release','configurations':{'release':{'profile':'release','task_limits':{'steps':2000000,'timeout_ms':15000,'workers':2}}},'components':{
   'leaf':{'kind':leaf_kind,'root':'leaf','entry':'leaf/value.nex','entry_function':'save'},
   'mid':{'kind':mid_kind,'root':'mid','entry':'mid/value.nex','entry_function':'save','dependencies':{'leaf':'dynamic' if mode=='shared' else 'static'}},
   'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'static' if mode=='static' else 'dynamic'}}}}
  write(project/'nex.build.json',definition)
  assert cli(mode+'-reference','eval',cwd=project,env=env)['stdout']=='42\n'
  plan=cli(mode+'-plan','project','--kind','plan','--component','app',cwd=project,env=env)
  for row in plan['components']:
   linkage=row['task_linkage'];assert linkage['execution_abi']==7 and linkage['task_file_writes'] is True
   assert linkage['schema']==('nex.project-static-task-linkage/5' if mode=='static' else 'nex.project-task-linkage/14')
   assert all(x['calling_mode'] in ('task-code/7','sync/1') for x in linkage['imports'])
  built=cli(mode+'-build','project','--kind','build','--component','app',cwd=project,env=env);images=artifacts(built)
  for row in images.values():
   folder=Path(row['artifact']).parent;provider=json.loads((folder/'task-provider.json').read_text());assert provider['schema']=='nex.native-task-provider/14' and provider['descriptor_abi']==0x4e45585400000007 and provider['task_file_writes'] is True
  assert cli(mode+'-run','project','--kind','run','--component','app',cwd=project,env=env)['observation']['stdout']=='42\n'
  assert (data/'text').read_text()==text and (data/'bytes').read_bytes()==bytes([0,78,69,88,255])
  prior={p.name:p.read_bytes() for p in data.iterdir()};denied_env={**env,'NEX_FILES_WRITE':'0'}
  denied=cli(mode+'-denied-reference','eval',cwd=project,env=denied_env,expected=1);assert denied['code']=='E_RESULT'
  denied_native=process(mode+'-denied-native',[images['app']['artifact']],env=denied_env,expected=70);assert 'E_RESULT' in denied_native.stderr and {p.name:p.read_bytes() for p in data.iterdir()}==prior
  deployment=root/(mode+'-package');package=cli(mode+'-package','project','--kind','package','--component','app','--directory',deployment,*package_flags,cwd=project,env=env);assert not package['application_execution']
  criteria=cli(mode+'-task-init','task','nex.build.json','--kind','init','--component','app','--configuration','release',cwd=project,env=env)
  # Replay has an empty native cache. Give its cold compilation an explicit
  # reviewed check; preserve the existing write-execution and source task limits.
  write_timeout=180 if os.name=='nt' else 30
  criteria['checks']=[
   {'id':'build-native','program':'app','kind':'build','target':'native','configuration':'release','timeout_seconds':300},
   {'id':'write','program':'app','kind':'run','target':'native','configuration':'release','entry':'writer_app::main','expect':{'stdout':'42\n','exit_code':0},'timeout_seconds':write_timeout}]
  criteria['requirements']=[
   {'id':'build-native','text':'Build the reviewed project from captured inputs, including a cold replay workspace','targets':['native'],'checks':['build-native'],'bindings':[{'program':'app','kind':'function','symbol':'writer_app::main'}]},
   {'id':'write','text':'Write through reviewed ABI7 binary providers with explicit external authority','targets':['native'],'checks':['write'],'bindings':[{'program':'app','kind':'function','symbol':'writer_app::main'}]}]
  task=project/'task.json';write(task,criteria);checked=cli(mode+'-task-check','task',task,'--kind','check',cwd=project,env=env)
  executed=cli(mode+'-task-run','task',task,'--kind','run','--task-hash',checked['task_hash'],'--directory',root/(mode+'-capture'),cwd=project,env=env);assert executed['ok'];receipt=Path(executed['output'])
  shutil.rmtree(project)
  moved=process(mode+'-detached-package',[deployment/'apps/app/bin/app'],env={**env,'NEX_RESOURCE_DIR':str(root/'absent-resources')});assert moved.stdout=='42\n' and not moved.stderr
  replayed=cli(mode+'-source-deleted-replay','task',receipt,'--kind','replay','--directory',root/(mode+'-replay'),env=env);assert replayed['ok'] and replayed['task_hash']==checked['task_hash']
  for result,directory in [(executed,receipt.parent),(replayed,root/(mode+'-replay'))]:
   assert [(row['id'],row['status'])for row in result['checks']]==[('build-native','passed'),('write','passed')]
   build=json.loads((directory/'artifacts/build-native/commands/build.json').read_text())
   write_build=json.loads((directory/'artifacts/write/commands/native-build.json').read_text())
   assert build['timeout_seconds']<=300 and not build['timed_out'] and build['exit_code']==0
   assert write_build['timeout_seconds']<=write_timeout and not write_build['timed_out'] and write_build['exit_code']==0
  report['projects'].append({'mode':mode,'actual_binary_edges':True,'native_reference':True,'write_grant_denied':True,'source_deleted_package':True,'source_deleted_replay':True,'receipt':str(receipt),'cold_build_check_seconds':300,'write_check_seconds':write_timeout,'both_checks_passed_original_and_replay':True});save()
 browser=root/'browser';shutil.copytree(resources/'examples/web',browser)
 source=browser/'main.nex';source.write_text(source.read_text()+'\nserver fn hidden_writer()->result<bool> !{task,fs}{return file_write_text("PRIVATE_SERVER_TARGET","private");}\n', newline="\n")
 generated=root/'browser-output';cli('browser-pruning','web',source,'--directory',generated,cwd=browser)
 client='\n'.join(p.read_text() for p in generated.rglob('*.ts'));assert client and 'PRIVATE_SERVER_TARGET' not in client and 'file_write_text' not in client
 source.write_text(source.read_text()+'\nclient fn forbidden_writer()->result<bool> !{task,fs}{return file_write_text("x","x");}\n', newline="\n")
 rejected=cli('browser-realm','check',source,cwd=browser,expected=1);assert rejected['code']=='E_REALM'
 report.update(ok=True,state='passed',genuine022_migrations=3,all16_tables_schema_rows_ids_preserved=True,native_reference=True,static_shared_binary_edges=True,mixed_static_shared=True,explicit_write_grant_denied=True,source_deleted_package=True,source_deleted_replay=True,browser_exclusion=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save()
print(json.dumps({'ok':True,'genuine022_migrations':3,'binary_project_modes':3,'source_deleted_replay':True}))
