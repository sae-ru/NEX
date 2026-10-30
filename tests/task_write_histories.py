"""Public022->023 migration of genuine resources/callables/imports/task/model histories."""
import argparse,base64,copy,hashlib,json,lzma,os,re,sqlite3,subprocess,tempfile,time
from collections import Counter
from contextlib import closing
from pathlib import Path
PINS={
 'resources':'ce75df9e7fc77357599829d021f5e32eedb577874048aa7c7979d72eee755e4b',
 'nominal':'cdcaafd70f98640e07e119d94b195b54586eefe61310c908e97ce5ab8b38039f',
 'callable':'4e34432137a9facceadde894b7fecec47eb161e8ea304fb9b28f5181a4e6e103',
 'imports':'d0cad1f3efe080cfe6326731edc4b350b62c1683a365714c93725efa47504e1a',
 'tasks':'1d8b0b9d462209029adf24e070e52e2ff2956adbdfd87cd3546c8208a629702d',
 'model-compute-device-imports':'b7e59c7e69782b5ddc352073b9439c2f5e9235e7b80efac6bfaa1e54e61ecc75'}
SDK='a75421b899a7e47d617a8ef6257123f75db4ee4f9869fe2aa11c3be6b87bb1a8'
p=argparse.ArgumentParser();p.add_argument('--compiler',type=Path,required=True);p.add_argument('--resources',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
compiler=a.compiler.resolve();resources=(a.resources or Path(__file__).resolve().parents[1]).resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex023 histories 🧠 ');root=Path(temporary.name).resolve()
env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
for key in ['NEX_FILES_ROOT','NEX_FILES_WRITE','NEX_PROFILE_OUTPUT','NEX_TRACY']:env.pop(key,None)
started=time.monotonic();report={'schema':'nex.public-task-write-histories/1','ok':False,'state':'starting','language':'0.27','compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'origin_SDK_sha256':SDK,'origins':[],'migrations':[],'commands':[],'actual_opaque_resource_operations':False,'actual_GPU_NPU_execution':False,'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-started,3);(root/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
def cli(name,project,*args,expected=0):
 report['state']=name;save();label='%03d-'%(len(report['commands'])+1)+name
 command=[str(compiler),*map(str,args),'--json'];p=subprocess.run(command,cwd=project,env=env,capture_output=True,text=True,timeout=600)
 (root/(label+'.stdout')).write_text(p.stdout);(root/(label+'.stderr')).write_text(p.stderr)
 report['commands'].append({'name':name,'argv':command,'cwd':str(project),'exit_code':p.returncode,'expected':expected});save()
 assert p.returncode==expected,(name,p.returncode,p.stdout,p.stderr)
 return json.loads(p.stdout)
def state(database):
 with closing(sqlite3.connect(database.resolve().as_uri()+'?mode=rw',uri=True)) as db:
  db.execute('PRAGMA query_only=ON');names=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  return {'ddl':db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),'tables':{n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}}
def retained(before,after):
 assert before['ddl']==after['ddl'] and len(before['tables'])==len(after['tables'])==16
 for name,rows in before['tables'].items():
  if name!='head':assert not (Counter(rows)-Counter(after['tables'][name])),name
 assert before['tables']['metadata']==after['tables']['metadata']
def reviewed_delivery_sources(sources):
 target=copy.deepcopy(sources)
 for name,text in target['files'].items():
  masked=re.sub(r'//[^\n]*|"(?:\\.|[^"\\])*"',lambda m:' '*len(m[0]),text)
  edits=[m.end(1) for m in re.finditer(r'!\{([^{}]*)\}',masked)
         if 'task' in {v.strip() for v in m[1].split(',')} and 'throw' not in {v.strip() for v in m[1].split(',')}]
  for end in reversed(edits):text=text[:end]+',throw'+text[end:]
  target['files'][name]=text
 return target
try:
 assert cli('describe',root,'describe')['version']=='0.27'
 for name,pin in PINS.items():
  fixture=resources/'examples/task-write-history'/('language-0.22-sdk1326-'+name+'.json')
  if not fixture.exists():fixture=resources/'tests/fixtures'/fixture.name
  metadata=json.loads(fixture.read_text());path=fixture.with_suffix('.sql')
  if path.exists():sql=path.read_bytes()
  else:
   compressed=base64.b85decode(''.join(Path(str(path)+'.xz.b85').read_text().split()))
   decoder=lzma.LZMADecompressor();sql=decoder.decompress(compressed,max_length=8*1024*1024)
   assert decoder.eof and not decoder.unused_data,'fixture decompression exceeded its bound'
  assert hashlib.sha256(sql).hexdigest()==metadata['sql_sha256']==pin
  assert metadata['language']=='0.22' and metadata['sdk']['compiler_sha256']==SDK and len(metadata['revisions'])==3
  report['origins'].append({'name':name,'revisions':3,'sql_sha256':pin,'origin_SDK_sha256':SDK});save()
  for i,row in enumerate(metadata['revisions']):
   label=name+'-'+str(i);project=root/label;database=project/'.nex/graph.db';database.parent.mkdir(parents=True)
   with closing(sqlite3.connect(database)) as db:db.executescript(sql.decode())
   for relative,text in metadata['revisions'][-1]['bundle']['files'].items():
    path=Path(relative);assert not path.is_absolute() and '..' not in path.parts
    path=project/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text)
   manifest=project/'nex.json';manifest.write_text(json.dumps({'schema':'nex.project/1','language':'0.22','entry':row['bundle']['entry']}));physical=manifest.read_bytes();before=state(database)
   assert len(before['tables'])==16 and {n:len(v) for n,v in before['tables'].items()}==metadata['tables']
   manifest.write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':row['bundle']['entry']}))
   try:
    refused=cli(label+'-HEAD-guard',project,'check',expected=1);assert refused['code']=='E_LANGUAGE_VERSION' and state(database)==before
   finally:manifest.write_bytes(physical)
   arguments=['migrate','--revision',row['revision']]
   plan=cli(label+'-plan',project,*arguments,'--kind','plan');assert plan['origin_verified'] and state(database)==before
   expected_sources=row['bundle'];reviewed=not plan['target_valid']
   if reviewed:
    assert plan['target_diagnostic']['code']=='E_EFFECT'
    refused=cli(label+'-missing-delivery',project,*arguments,expected=1);assert refused['code']=='E_EFFECT' and state(database)==before
    candidate=copy.deepcopy(plan['candidate']);assert candidate['sources']==row['bundle']
    candidate['sources']=reviewed_delivery_sources(candidate['sources']);expected_sources=candidate['sources'];candidate_path=root/(label+'-reviewed-target.json');candidate_path.write_text(json.dumps(candidate))
    arguments.extend(['--candidate',candidate_path])
    valid=cli(label+'-reviewed-plan',project,*arguments,'--kind','plan');assert valid['origin_verified'] and valid['target_valid'] and valid['candidate_used'] and state(database)==before
   migrated=cli(label+'-migrate',project,*arguments,'--expected-revision',metadata['head'])
   assert migrated['origin_verified'] and migrated['origin_language']=='0.22' and migrated['language']=='0.27' and not migrated['materialized'] and migrated['revision']!=row['revision']
   assert migrated['candidate_used']==reviewed and migrated['declared_original_revision']==row['revision']
   after=state(database);retained(before,after);assert manifest.read_bytes()==physical and after['tables']['head']==[(1,migrated['revision'])]
   reference=cli(label+'-eval',project,'eval','--revision',migrated['revision']);native=cli(label+'-run',project,'run','--revision',migrated['revision'])
   assert reference['value']==row['value'] and reference['stdout']==native['stdout']==row['stdout'] and native['exit_code']==0
   web=cli(label+'-web',project,'test','--revision',migrated['revision'],'--target','web');assert web['ok'] is True
   repeated=cli(label+'-idempotent',project,'migrate','--revision',migrated['revision']);assert repeated['revision']==migrated['revision'] and state(database)==after
   with closing(sqlite3.connect(database)) as db:
    raw,language=db.execute('SELECT source,language FROM revisions WHERE hash=?',(row['revision'],)).fetchone();assert language=='0.22' and json.loads(raw)==row['bundle']
    raw,language=db.execute('SELECT source,language FROM revisions WHERE hash=?',(migrated['revision'],)).fetchone();assert language=='0.27' and json.loads(raw)==expected_sources
   report['migrations'].append({'name':label,'origin_revision':row['revision'],'revision':migrated['revision'],'all16_tables_schema_rows_ids_preserved':True,'native_reference':True,'retained_web_tests':True,'implicit_HEAD_upgrade_rejected':True,'physical_manifest_unchanged':True,'reviewed_delivery_candidate':reviewed,'idempotent':True});save()
 report.update(ok=True,state='passed',genuine022_histories=6,genuine022_revisions=18,all16_tables_schema_rows_ids_preserved=True,native_reference=True,retained_web_tests=True)
except BaseException as error:report.update(state='failed',error=repr(error));raise
finally:save()
print(json.dumps({'ok':True,'genuine022_histories':6,'genuine022_revisions':18}))
