"""Private024 migration from an actual SDK1332/023 history, preserving all16 tables."""
import argparse, hashlib, json, os, sqlite3, subprocess, tempfile, time
from collections import Counter
from contextlib import closing
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('compiler',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
probe=a.probe.resolve();compiler=a.compiler.resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex stream migration ');root=Path(temporary.name)
fixtures=Path(__file__).parent/'fixtures';base='language-0.23-sdk1332-task-streams';meta=json.loads((fixtures/(base+'.json')).read_text());sql=(fixtures/(base+'.sql')).read_text()
assert hashlib.sha256(sql.encode()).hexdigest()==meta['SQL_sha256'] and meta['all_revisions_produced_by_actual023_SDK'] and not meta['retagged_history']
report={'schema':'nex.private024-stream-migration/1','ok':False,'state':'starting','checks':[],'commands':[],
 'genuine023_revisions':3,'public_language':'0.26','target_language':'0.24','probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'full_objective_complete':False};start=time.monotonic()
def save():report['seconds']=round(time.monotonic()-start,3);(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def state(project):
 database=(project/'.nex/graph.db').resolve()
 # Every writer has terminated. With no WAL file, immutable readonly access
 # reads the complete main database without creating observer WAL/SHM files.
 uri=database.as_uri()+'?mode=ro'+('&immutable=1' if not Path(str(database)+'-wal').exists() else '')
 with closing(sqlite3.connect(uri,uri=True)) as db:
  names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  return {'schema':db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),'tables':{n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}}
def restore(name):
 project=root/name;project.mkdir();(project/'.nex').mkdir();(project/'nex.json').write_text(json.dumps(meta['project_manifest'])+'\n');(project/'main.nex').write_text(meta['source']);(project/'files').mkdir();(project/'files/input').write_text('abcdef')
 with closing(sqlite3.connect(project/'.nex/graph.db')) as db:db.executescript(sql)
 return project
def invoke(name,project,extra=None,expected=0):
 body={'schema':'nex.private-stream-migration-request/1','project':str(project),'expected_revision':meta['head'],'target_language':'0.24'}
 if extra:body.update(extra)
 request=root/(name+'.request.json');request.write_text(json.dumps(body));out=root/(name+'-evidence');env={**os.environ,'NEX_FILES_ROOT':str(project/'files'),'NEX_FILES_WRITE':'1'}
 r=subprocess.run([str(probe),str(request),str(out)],cwd=root,env=env,capture_output=True,text=True,timeout=240)
 (root/(name+'.stdout')).write_text(r.stdout);(root/(name+'.stderr')).write_text(r.stderr);report['commands'].append({'name':name,'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(name,r.returncode,r.stdout,r.stderr);return json.loads(r.stdout)
try:
 project=restore('positive');before=state(project);manifest=(project/'nex.json').read_bytes();source=(project/'main.nex').read_bytes()
 value=invoke('positive',project,{'execute':True});after=state(project)
 assert value['origin_verified'] is True and value['origin_language']=='0.23' and value['language']=='0.24' and value['public_default']=='0.26'
 assert value['old_error']=='E_TASK_UNIMPLEMENTED' and value['target_value']==42 and value['target_stdout']==''
 assert len(before['tables'])==len(after['tables'])==16 and before['schema']==after['schema']
 for table,rows in before['tables'].items():
  if table!='head':assert not (Counter(rows)-Counter(after['tables'][table])),table
 assert len(after['tables']['revisions'])==4 and after['tables']['head']==[(1,value['revision'])]
 with closing(sqlite3.connect(project/'.nex/graph.db')) as db:
  assert dict(db.execute('SELECT hash,language FROM revisions'))=={**dict.fromkeys(meta['revisions'],'0.23'),value['revision']:'0.24'}
 assert (project/'nex.json').read_bytes()==manifest and (project/'main.nex').read_bytes()==source
 binary=Path(value['executable']);r=subprocess.run([str(binary)],env={'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(project/'files')},capture_output=True,text=True,timeout=60)
 (root/'positive-native.stdout').write_text(r.stdout);(root/'positive-native.stderr').write_text(r.stderr);assert r.returncode==42 and not r.stdout and not r.stderr
 report['checks'].append({'name':'positive','executable':str(binary),'executable_sha256':hashlib.sha256(binary.read_bytes()).hexdigest(),'all16_tables_schema_rows_ids_preserved':True})
 invoke('idempotent',project,{'expected_revision':value['revision']});assert state(project)==after;report['checks'].append({'name':'idempotent'})
 # Ordinary source synchronization still refuses an unmaterialized old physical manifest.
 cli_env={**os.environ};cli_env.pop('NEX_RESOURCE_DIR',None)
 ordinary=subprocess.run([str(compiler),'check','--json'],cwd=project,env=cli_env,text=True,capture_output=True,timeout=120)
 (root/'ordinary-CLI.stdout').write_text(ordinary.stdout);(root/'ordinary-CLI.stderr').write_text(ordinary.stderr)
 assert ordinary.returncode==1 and json.loads(ordinary.stdout)['code']=='E_LANGUAGE_VERSION' and state(project)==after
 report['checks'].append({'name':'actual-public-CLI-physical-manifest-guard'})
 for name,extra,code in [
  ('implicit-sync',{'unversioned_synchronize':True},'E_LANGUAGE_VERSION'),
  ('future-disguise',{'declared_language':'0.24'},'E_REVISION'),
  ('legacy-disguise',{'declared_language':'0.16'},'E_REVISION'),
  ('stale-head',{'expected_revision':'0'*64},'E_CONFLICT')]:
  project=restore(name);before=state(project);value=invoke(name,project,extra,1);assert value['code']==code and state(project)==before
  report['checks'].append({'name':name,'code':code,'store_unchanged':True})
 project=restore('raced-head');candidate=root/'race.json';candidate.write_text(json.dumps({'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':'module race;fn main()->i64{return 43;}'}}))
 value=invoke('raced-head',project,{'race_candidate':str(candidate)},1);assert value['code']=='E_CONFLICT'
 snapshot=root/'raced-head-evidence/race-before-planned-save.db'
 with closing(sqlite3.connect(snapshot)) as db:
  for name,rows in state(project)['tables'].items():assert sorted(db.execute('SELECT * FROM "'+name+'"').fetchall(),key=repr)==rows
 report['checks'].append({'name':'raced-head','code':'E_CONFLICT','competing_history_preserved':True})
 report.update(ok=True,state='passed',checks_passed=len(report['checks']),all16_tables_schema_rows_ids_preserved=True,physical_projection_preserved=True)
except BaseException as e:report.update(state='failed',error=repr(e));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','checks_passed','error']}),flush=True)
