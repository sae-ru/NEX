"""Qualify existing graph-snapshot APIs on an actual migrated027 history.

Uses the selected compiler and explicit migration API; preserves original history.
"""
from sqlite_fixture import connection as sqlite_connection
from pathlib import Path
import argparse,collections,hashlib,json,os,shutil,sqlite3,subprocess,sys,tempfile,time
parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('nex',type=Path)
parser.add_argument('--source-root',type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument('--resources',type=Path);parser.add_argument('--output',type=Path)
args=parser.parse_args();W=args.source_root.resolve();O=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-typed-graph-snapshot-'));O.mkdir(parents=True,exist_ok=args.output is None)
compiler=args.nex.resolve();probe=args.probe.resolve();sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
env={**os.environ,'NEX_RESOURCE_DIR':str(args.resources.resolve() if args.resources else W),'PYTHONDONTWRITEBYTECODE':'1'}
report={'ok':False,'scope':'checked graph-snapshot027 recovery and retained026 history','public027_enabled':False,'compiler_sha256':sha(compiler),'cases':[],'commands':[]}
def save():(O/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
def run(label,argv,cwd=O,code=0):
 r=subprocess.run(list(map(str,argv)),cwd=cwd,env=env,text=True,capture_output=True,timeout=180)
 (O/(label+'.stdout')).write_text(r.stdout, newline="\n");(O/(label+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'label':label,'exit':r.returncode});save();assert r.returncode==code,(label,r.stdout[-3000:],r.stderr[-2500:]);return r
def api(label,project,mode,**extra):
 request={'schema':'nex.typed-error-migration-request/1','mode':mode,'project':str(project),**extra};f=O/(label+'.request.json');f.write_text(json.dumps(request,ensure_ascii=False)+'\n', newline="\n");return json.loads(run(label,[probe,f]).stdout)
def cli(label,root,*args,error=None):
 value=json.loads(run(label,[compiler,*args,'--json'],root,1 if error else 0).stdout)
 assert (value.get('code')==error if error else value.get('ok') is True),(label,value);return value
def rows(p):
 db=sqlite3.connect('file:'+str(p)+'?mode=rw',uri=True)
 try:
  db.execute('PRAGMA query_only=ON');schema=list(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
  result={}
  for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
   result[name]=collections.Counter(tuple(x) for x in db.execute('SELECT * FROM "'+name.replace('"','""')+'"'))
  return schema,result
 finally:db.close()
def passed(name,**data):report['cases'].append({'name':name,'passed':True,**data});save()

meta=json.loads((W/'tests/fixtures/language-0.26-typed-origin.json').read_text());sql=(W/'tests/fixtures/language-0.26-typed-origin.sql').read_bytes();assert sha(W/'tests/fixtures/language-0.26-typed-origin.sql')==meta['sql_sha256']
root=O/'project λ';root.mkdir();(root/'.nex').mkdir();(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'})+'\n', newline="\n");(root/'main.nex').write_text(meta['source'], newline="\n")
with sqlite_connection(root/'.nex/graph.db') as db:db.executescript(sql.decode())
before=rows(root/'.nex/graph.db');assert len(before[1])==16
plan=api('plan',root,'plan',expected_revision=meta['head'])
text=meta['source'].replace('throw("APP","λ\\u0000🙂");','throw(Box<i64>(value));').replace('catch(code,message) if code=="APP"{assert(message=="λ\\u0000🙂");}','catch(e:Box<str>){assert(false);}\n catch(e:Box<i64>){task_yield();assert(e.value==41);}\n catch(code,message){assert(false);}')
assert text!=meta['source'] and 'catch(e:Box<i64>)' in text
candidate={'schema':'nex.migration-candidate/1','origin_revision':meta['head'],'origin_language':'0.26','origin_source_hash':plan['origin_source_hash'],'target_language':'0.27','sources':{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':text}}}
applied=api('apply',root,'apply',expected_revision=meta['head'],candidate=candidate);target=applied['revision'];after=rows(root/'.nex/graph.db');assert before[0]==after[0]
for table,values in before[1].items():
 if table!='head':assert not (values-after[1][table]),table
passed('genuine026_migration_preserves_all16_tables_and_old_ids',target_revision=target)
with sqlite_connection(root/'.nex/graph.db') as db:revisions=list(db.execute('SELECT hash,language FROM revisions ORDER BY hash'))
assert {lang for _,lang in revisions}=={'0.26','0.27'} and len(revisions)==3
expected={}
for i,(revision,language) in enumerate(revisions):
 value=api('original-evaluate-'+str(i),root,'evaluate',revision=revision);assert value['ast']==value['ir'];expected[revision]=value
(root/'main.nex').unlink();snapshot=O/'snapshot'
created=cli('snapshot',root,'snapshot','--directory',snapshot);assert created['head']==target and rows(root/'.nex/graph.db')==after
manifest=json.loads((snapshot/'snapshot.json').read_text());assert manifest['state']['head_language']=='0.27';passed('source_absent_snapshot027',head=target,namespace=created['namespace'])
recovered=O/'recovered λ';cli('recover',O,'recover',snapshot,'--directory',recovered)
assert rows(recovered/'.nex/graph.db')==after and not (recovered/'main.nex').exists()
assert json.loads((recovered/'nex.json').read_text())['language']=='0.27'
for i,(revision,language) in enumerate(revisions):
 value=api('recovered-evaluate-'+str(i),recovered,'evaluate',revision=revision);assert value==expected[revision];passed('recovered_AST_TaskIR_'+language+'_'+str(i),stdout=value['ast']['stdout'],revision=revision)
native=api('native',recovered,'build-native',revision=target,output=str(O/'native'));assert native['execution_abi']==0x4e45585400000007

actual=run('native-run',[native['artifact']]);assert actual.stdout=='42\n' and not actual.stderr;passed('recovered027_native_ABI7_execution_without_original_source',stdout=actual.stdout)
advertised=json.loads(run('describe',[compiler,'describe','--json']).stdout)['version'];assert advertised in ['0.26','0.27']
if advertised=='0.27':
 observed=cli('public027-evaluation',recovered,'eval','--revision','HEAD');assert observed['stdout']=='42\n';passed('advertised027_CLI_executes_recovered_HEAD')
else:
 cli('ordinary027-rejection',recovered,'eval','--revision','HEAD',error='E_LANGUAGE_VERSION');passed('ordinary027_gate_stays_explicit')
report['public027_enabled']=advertised=='0.27';assert rows(recovered/'.nex/graph.db')==after
held=sqlite3.connect(root/'.nex/graph.db')
try:
 held.execute('PRAGMA journal_mode=WAL');held.execute('BEGIN IMMEDIATE');held.execute("INSERT INTO metadata(key,value) VALUES('snapshot_uncommitted_probe','must not appear')")
 wal_snapshot=O/'snapshot-wal';cli('wal-snapshot',root,'snapshot','--directory',wal_snapshot);wal_recovered=O/'recovered-wal';cli('wal-recover',O,'recover',wal_snapshot,'--directory',wal_recovered)
 assert rows(wal_recovered/'.nex/graph.db')==after;passed('uncommitted_WAL_writer_is_not_copied_or_blocking')
finally:held.rollback();held.close()
original_manifest=(snapshot/'snapshot.json').read_text()
for label,field,value in [('head','head','0'*64),('language','head_language','0.26')]:
 changed=json.loads(original_manifest);changed['state'][field]=value;(snapshot/'snapshot.json').write_text(json.dumps(changed)+'\n', newline="\n");destination=O/('bad-'+label)
 try:
  cli('bad-'+label,O,'recover',snapshot,'--directory',destination,error='E_SNAPSHOT_INTEGRITY');assert not destination.exists();passed('tampered_'+label+'_rejected_without_output')
 finally:(snapshot/'snapshot.json').write_text(original_manifest, newline="\n")
raw=(snapshot/'graph.db').read_bytes();(snapshot/'graph.db').write_bytes(raw+b'corrupt')
try:
 destination=O/'bad-database';cli('bad-database',O,'recover',snapshot,'--directory',destination,error='E_SNAPSHOT_INTEGRITY');assert not destination.exists();passed('tampered_database_rejected_without_output')
finally:(snapshot/'graph.db').write_bytes(raw)
sentinel=recovered/'keep';sentinel.write_text('keep', newline="\n");cli('existing-target',O,'recover',snapshot,'--directory',recovered,error='E_EXISTS');assert sentinel.read_text()=='keep' and rows(recovered/'.nex/graph.db')==after;passed('existing_recovery_never_overwritten')
assert rows(root/'.nex/graph.db')==after and sha(compiler)==report['compiler_sha256']
report.update(ok=True,history_tables=16,retained026_revisions=2,recovered027_revisions=1,source_absent=True,source_language_selection_changed=False,SDK_accepted=False,goal_complete=False);save();print(json.dumps({'ok':True,'cases':len(report['cases']),'history_tables':16,'report':str(O/'report.json')}),flush=True)

if not args.output:shutil.rmtree(O)
