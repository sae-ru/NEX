"""Real SDK131022 history exercises the shared migration preflight and Store."""
from sqlite_fixture import connection as sqlite_connection
import argparse,copy,hashlib,json,os,shutil,sqlite3,subprocess,tempfile,time
from pathlib import Path
parser=argparse.ArgumentParser();parser.add_argument('probe');parser.add_argument('nex');parser.add_argument('--output',type=Path);args=parser.parse_args()
probe=Path(args.probe).resolve();compiler=Path(args.nex).resolve();repo=Path(__file__).resolve().parents[1]
fixture=repo/'tests/fixtures/language-0.22-sdk131-task-writes.json';metadata=json.loads(fixture.read_text());raw=fixture.with_suffix('.sql').read_bytes()
assert metadata['schema']=='nex.language-022-write-migration-fixture/1' and metadata['language']=='0.22'
assert hashlib.sha256(raw).hexdigest()==metadata['sql_sha256']=='f9f11160f3b16a7fcb949598a0c804e2230180a26a034e3e9dfe9545e0b8056e'
assert metadata['sdk']['binary_sha256']=='5f23165c9e1be54fbe504adc244ea65e5b6a66721a579db4a8d364f63e4a897f'
assert metadata['sdk']['toolchain']=='0.131.0' and metadata['sdk']['acceptance_ok'] is True
assert len(metadata['revisions'])==3 and len(metadata['tables'])==16 and metadata['metadata']['schema']=='4'
temporary=None
if args.output:root=args.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex genuine022 write migration 🧠 ');root=Path(temporary.name)
started=time.monotonic();report={'schema':'nex.private023-write-migration-verification/1','ok':False,'state':'starting','commands':[],'checks':[],
 'fixture_sql_sha256':metadata['sql_sha256'],'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),
 'genuine022_revisions':3,'genuine_schema_tables':16,'public023_enabled':True,'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-started,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n', newline="\n")
def state(database):
 with sqlite_connection(database) as db:
  schema=list(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"))
  names=[x[0] for x in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  return {'schema':schema,'tables':{n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}}
def retained(before,after):
 assert before['schema']==after['schema'] and set(before['tables'])==set(after['tables']) and len(after['tables'])==16
 for name,rows in before['tables'].items():
  if name=='head':continue
  assert set(rows)<=set(after['tables'][name]),name
 assert before['tables']['metadata']==after['tables']['metadata']
def restore(name):
 project=root/name;database=project/'.nex/graph.db';database.parent.mkdir(parents=True)
 with sqlite_connection(database) as db:db.executescript(raw.decode())
 head=next(r for r in metadata['revisions'] if r['revision']==metadata['head'])
 for key,text in head['bundle']['files'].items():
  p=project/key;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text, newline="\n")
 (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':head['bundle']['entry']}), newline="\n")
 physical={str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file() and '.nex' not in p.relative_to(project).parts}
 before=state(database);assert {k:len(v) for k,v in before['tables'].items()}==metadata['tables']
 return project,database,before,physical
def untouched(project,physical):
 for name,data in physical.items():assert (project/name).read_bytes()==data,name
def run(name,argv,env,cwd,expected=0):
 report['state']=name;save();result=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,capture_output=True,text=True,timeout=240)
 (root/(name+'.stdout')).write_text(result.stdout, newline="\n");(root/(name+'.stderr')).write_text(result.stderr, newline="\n")
 report['commands'].append({'name':name,'argv':list(map(str,argv)),'exit_code':result.returncode,'expected':expected});save()
 assert result.returncode==expected,(name,result.returncode,result.stdout,result.stderr)
 return result
def invoke(name,request,expected=0,env=None):
 path=root/(name+'.request.json');path.write_text(json.dumps({'schema':'nex.private-write-migration-request/1',**request},ensure_ascii=False), newline="\n")
 observed=run(name,[probe,path,root/(name+'-evidence')],env or os.environ,root,expected)
 return json.loads(observed.stdout)
def candidate(name,source):
 p=root/(name+'.sources.json');p.write_text(json.dumps({'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source}}), newline="\n");return str(p)
try:
 current_language=json.loads(run('describe',[compiler,'describe','--json'],os.environ,root).stdout)['version']
 assert current_language=='0.28'
 for index,row in enumerate(metadata['revisions']):
  name='positive-'+str(index);project,database,before,physical=restore(name);files=root/(name+'-files');files.mkdir();env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'}
  manifest=project/'nex.json';raw_manifest=manifest.read_bytes()
  try:
   current=json.loads(raw_manifest);current['language']='0.23';manifest.write_text(json.dumps(current), newline="\n")
   rejected=json.loads(run(name+'-no-implicit-upgrade',[compiler,'check','--json'],env,project,1).stdout)
   assert rejected['code']=='E_LANGUAGE_VERSION' and state(database)==before
  finally:manifest.write_bytes(raw_manifest)
  request={'project':str(project),'origin_revision':row['revision'],'expected_revision':metadata['head'],'execute':True}
  result=invoke(name,request,env=env)
  assert result['origin_verified'] and result['origin_language']=='0.22' and result['language']=='0.23' and result['public_default']==current_language
  assert result['revision']!=row['revision'] and result['previous_revision']==metadata['head']
  after=state(database);retained(before,after);assert after['tables']['head']==[(1,result['revision'])]
  assert len(after['tables']['revisions'])==4
  with sqlite_connection(database) as db:
   original=db.execute('SELECT source,language FROM revisions WHERE hash=?',(row['revision'],)).fetchone();assert json.loads(original[0])==row['bundle'] and original[1]=='0.22'
   selected=db.execute('SELECT source,language FROM revisions WHERE hash=?',(result['revision'],)).fetchone();assert json.loads(selected[0])==row['bundle'] and selected[1]=='0.23'
  body='\n'.join(row['bundle']['files'].values());task='!{task' in body
  if task:assert result['old_error']=='E_TASK_UNIMPLEMENTED' and result['target_value']==42;exit_code=42;stdout=''
  else:assert result['old_value']==result['target_value']==0 and result['old_stdout']==result['target_stdout']=='42\n';exit_code=0;stdout='42\n'
  executable=Path(result['executable']);native=run(name+'-native',[executable],{'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'},root,exit_code)
  assert native.stdout==stdout and not native.stderr
  if task:assert (files/'output.txt').read_text()=='NEX asynchronous write\n'
  untouched(project,physical)
  rejected=json.loads(run(name+'-unmaterialized-manifest',[compiler,'check','--json'],env,project,1).stdout)
  assert rejected['code']=='E_LANGUAGE_VERSION' and state(database)==after;untouched(project,physical)
  repeated=invoke(name+'-repeat',{**request,'execute':False,'expected_revision':result['revision']},env=env)
  assert repeated['revision']==result['revision'];again=state(database);retained(after,again);assert len(again['tables']['revisions'])==4
  report['checks'].append({'name':name,'all16_tables_schema_rows_ids_preserved':True,'original_revision':row['revision'],'revision':result['revision'],
   'native_reference':True,'executable':str(executable),'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),'physical_sources_unchanged':True,'idempotent_target':True,'implicit_cross_version_HEAD_rejected':True});save()
 # Current migration preserves the genuine022 origin. A separately reviewed
 # candidate supplies the025 task delivery effect; the retained023 path above
 # must continue to use the unchanged archived source and semantics.
 for index,row in enumerate(metadata['revisions']):
  name='public025-'+str(index);project,database,before,physical=restore(name)
  arguments=[compiler,'migrate','--revision',row['revision']]
  plan=json.loads(run(name+'-plan',[*arguments,'--kind','plan','--json'],os.environ,project).stdout)
  assert plan['origin_verified'] and state(database)==before
  expected_sources=copy.deepcopy(row['bundle']);task=any('!{task' in text for text in expected_sources['files'].values())
  needs_delivery=not plan['target_valid']
  if needs_delivery:
   assert not plan['target_valid'] and plan['target_diagnostic']['code']=='E_EFFECT'
   rejected=json.loads(run(name+'-missing-delivery-effect',[*arguments,'--json'],os.environ,project,1).stdout)
   assert rejected['code']=='E_EFFECT' and state(database)==before
   reviewed=copy.deepcopy(plan['candidate']);assert reviewed['sources']==expected_sources
   text=reviewed['sources']['files'][expected_sources['entry']];assert text.count('!{task,fs}')==2
   reviewed['sources']['files'][expected_sources['entry']]=text.replace('!{task,fs}','!{task,fs,throw}')
   expected_sources=reviewed['sources'];path=root/(name+'-reviewed-delivery.json');path.write_text(json.dumps(reviewed), newline="\n")
   arguments.extend(['--candidate',path])
   valid=json.loads(run(name+'-reviewed-plan',[*arguments,'--kind','plan','--json'],os.environ,project).stdout)
   assert valid['origin_verified'] and valid['target_valid'] and valid['candidate_used'] and state(database)==before
  else:assert plan['target_valid']
  result=json.loads(run(name,[*arguments,'--expected-revision',metadata['head'],'--json'],os.environ,project).stdout)
  assert result['origin_verified'] and result['origin_language']=='0.22' and result['language']==current_language and result['revision']!=row['revision']
  assert result['candidate_used']==needs_delivery and result['previous_revision']==metadata['head'] and not result['materialized']
  after=state(database);retained(before,after);untouched(project,physical)
  assert len(after['tables']['revisions'])==4 and after['tables']['head']==[(1,result['revision'])]
  with sqlite_connection(database) as db:
   original=db.execute('SELECT source,language FROM revisions WHERE hash=?',(row['revision'],)).fetchone();assert json.loads(original[0])==row['bundle'] and original[1]=='0.22'
   selected=db.execute('SELECT source,language FROM revisions WHERE hash=?',(result['revision'],)).fetchone();assert json.loads(selected[0])==expected_sources and selected[1]==current_language
  files=root/(name+'-files');files.mkdir();env={**os.environ,'NEX_FILES_ROOT':str(files),'NEX_FILES_WRITE':'1'}
  observed=json.loads(run(name+'-reference',[compiler,'eval','--revision',result['revision'],'--json'],env,project).stdout)
  expected_value=42 if task else 0;expected_stdout='' if task else '42\n'
  assert observed['value']==expected_value and observed['stdout']==expected_stdout
  built=json.loads(run(name+'-build',[compiler,'build','--revision',result['revision'],'--profile','release','--json'],env,project).stdout)
  executable=Path(built['executable']);native_files=root/(name+'-native-files');native_files.mkdir()
  hidden=[]
  for source_name in row['bundle']['files']:
   source=project/source_name;renamed=source.with_name(source.name+'.hidden');source.rename(renamed);hidden.append((source,renamed))
  try:
   native=run(name+'-source-absent-native',[executable],{'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(native_files),'NEX_FILES_WRITE':'1'},root,expected_value)
   assert native.stdout==expected_stdout and not native.stderr
  finally:
   for source,renamed in hidden:renamed.rename(source)
  if task:assert (files/'output.txt').read_text()==(native_files/'output.txt').read_text()=='NEX asynchronous write\n'
  if index==0:assert (files/'synchronous.txt').read_text()==(native_files/'synchronous.txt').read_text()=='old synchronous write\n'
  stable=state(database);same=json.loads(run(name+'-idempotent',[compiler,'migrate','--revision',result['revision'],'--expected-revision',result['revision'],'--json'],env,project).stdout)
  assert same['revision']==result['revision'] and not same['changed'] and state(database)==stable
  exported=root/(name+'-export');run(name+'-export',[compiler,'export','--revision',result['revision'],'--directory',exported,'--json'],env,project)
  assert json.loads((exported/'nex.json').read_text())['language']==current_language
  assert json.loads(run(name+'-export-check',[compiler,'check','--json'],env,exported).stdout)['revision']==result['revision']
  untouched(project,physical)
  report['checks'].append({'name':name,'ordinary_CLI_shared_preflight':True,'explicit_public025':True,'reviewed_delivery_candidate':needs_delivery,'all16_tables_schema_rows_ids_preserved':True,'physical_sources_unchanged':True,'native_reference':True,'source_absent_native':True,'idempotent_target':True,'exported_current_project_checked':True});save()
 # Negative target preflight must not create even an empty destination Store.
 origin,_,_,_=restore('read-only-origin');origin_revision=metadata['head']
 invalid=candidate('invalid-target','module wrong;fn main()->i64{return "wrong type";}')
 empty=root/'invalid-empty-destination';empty.mkdir()
 error=invoke('invalid-target-no-destination',{'project':str(empty),'origin_project':str(origin),'origin_revision':origin_revision,'expected_revision':'EMPTY','candidate':invalid},1)
 assert error['code']=='E_TYPE' and not (empty/'.nex').exists();report['checks'].append({'name':'invalid-target-no-destination','destination_not_created':True});save()
 for name,extra,code in [
  ('wrong-head',{'expected_revision':'0'*64},'E_CONFLICT'),
  ('empty-head',{'expected_revision':''},'E_OPTION'),
  ('bad-hash',{'declared_revision':'A'*64},'E_REVISION'),
  ('changed-hash',{'declared_revision':'0'*64},'E_REVISION'),
  ('unknown-origin',{'declared_language':'0.99'},'E_LANGUAGE_VERSION'),
  ('relabelled-origin',{'declared_language':'0.23'},'E_REVISION'),
  ('legacy-disguise',{'declared_language':'0.17'},'E_REVISION'),
  ('unknown-target',{'target_language':'0.99'},'E_LANGUAGE_VERSION'),
  ('invalid-target',{'candidate':invalid},'E_TYPE')]:
  project,database,before,physical=restore(name);error=invoke(name,{'project':str(project),'origin_revision':origin_revision,'expected_revision':metadata['head'],**extra},1)
  assert error['code']==code and state(database)==before;untouched(project,physical);report['checks'].append({'name':name,'rejected_without_history_writes':True,'code':code});save()
 for name,language,source in [('corrupt-source','0.22','module changed;fn main()->i64{return 7;}'),('corrupt-language','0.23',None)]:
  project,database,_,physical=restore(name)
  with sqlite_connection(database) as db:
   if source:
    changed=copy.deepcopy(next(r['bundle'] for r in metadata['revisions'] if r['revision']==origin_revision));changed['files'][changed['entry']]=source
    db.execute('UPDATE revisions SET source=? WHERE hash=?',(json.dumps(changed),origin_revision))
   else:db.execute('UPDATE revisions SET language=? WHERE hash=?',(language,origin_revision))
  before=state(database);error=invoke(name,{'project':str(project),'origin_revision':origin_revision,'expected_revision':metadata['head']},1)
  assert error['code']=='E_REVISION' and state(database)==before;untouched(project,physical);report['checks'].append({'name':name,'rejected_without_history_writes':True});save()
 # Interleave a real competing committed writer after preflight, before save.
 project,database,before,physical=restore('raced-head');race=candidate('race','module competing;fn main()->i64{return 9;}')
 error=invoke('raced-head',{'project':str(project),'origin_revision':origin_revision,'expected_revision':metadata['head'],'race_candidate':race},1)
 assert error['code']=='E_CONFLICT';snapshot=root/'raced-head-evidence/race-before-planned-save.db';assert state(database)==state(snapshot)
 retained(before,state(database));untouched(project,physical);report['checks'].append({'name':'raced-head','planned_transaction_rolled_back':True,'competing_write_preserved':True});save()
 project,database,before,physical=restore('raced-synchronize')
 error=invoke('raced-synchronize',{'project':str(project),'origin_revision':origin_revision,'expected_revision':metadata['head'],'target_language':'0.22','race_candidate':race,'unversioned_synchronize':True},1)
 assert error['code']=='E_LANGUAGE_VERSION';snapshot=root/'raced-synchronize-evidence/race-before-planned-save.db';assert state(database)==state(snapshot)
 retained(before,state(database));untouched(project,physical);report['checks'].append({'name':'raced-synchronize','atomic_cross_version_guard':True,'competing_write_preserved':True});save()
 # A future023 archive cannot evade hash verification by claiming old legacy17.
 future=root/'future-legacy-disguise';shutil.copytree(root/'positive-0',future);database=future/'.nex/graph.db'
 with sqlite_connection(database) as db:
  selected=db.execute('SELECT revision FROM head WHERE id=1').fetchone()[0];db.execute("UPDATE revisions SET language='0.17' WHERE hash=?",(selected,))
 before=state(database);error=invoke('future-legacy-disguise',{'project':str(future),'expected_revision':selected},1)
 assert error['code']=='E_REVISION' and state(database)==before
 public=json.loads(run('public-future-legacy-disguise',[compiler,'migrate','--expected-revision',selected,'--json'],os.environ,future,1).stdout)
 assert public['code']=='E_REVISION' and state(database)==before
 report['checks'].append({'name':'future-legacy-disguise','private023_hash_recognized':True,'ordinary_CLI_verified':True});save()
 # A deliberately synthetic schema1 control proves the CLI refuses a live
 # language switch before its writable Store can upgrade old physical schemas.
 # This is separate from the three genuine022 semantic-history fixtures.
 project=root/'schema1-readonly-control';database=project/'.nex/graph.db';database.parent.mkdir(parents=True)
 (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.23','entry':'main.nex'}), newline="\n");(project/'main.nex').write_text('module modern;fn main()->i64{return 0;}', newline="\n")
 with sqlite_connection(database) as db:
  db.executescript("CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);INSERT INTO metadata VALUES('schema','1');CREATE TABLE revisions(hash TEXT PRIMARY KEY,module TEXT,source TEXT,path TEXT);CREATE TABLE head(id INTEGER PRIMARY KEY,revision TEXT);")
  db.execute('INSERT INTO revisions VALUES(?,?,?,?)',('0'*64,'legacy','module legacy;fn main()->i64{return 0;}','main.nex'));db.execute('INSERT INTO head VALUES(1,?)',('0'*64,))
 before=state(database);rejected=json.loads(run('schema1-readonly-control',[compiler,'check','--json'],os.environ,project,1).stdout)
 assert rejected['code']=='E_LANGUAGE_VERSION' and state(database)==before
 report['checks'].append({'name':'schema1-readonly-control','synthetic_schema_control':True,'no_implicit_schema_upgrade':True});save()
 report.update(ok=True,state='passed',checks_passed=len(report['checks']),positive_migrations=3,native_reference_migrations=3,
  retained022_interpretation=True,all16_tables_schema_rows_ids_preserved=True,invalid_preflight_no_destination=True,conflict_rollback=True,
  public_language=current_language,public_migrations=3,public_native_reference_migrations=3)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','checks_passed','error']}),flush=True)
