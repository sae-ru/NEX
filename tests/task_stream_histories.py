"""Migrate five genuine installed SDK1335 histories, including every old revision."""
import argparse,hashlib,json,os,sqlite3,subprocess,tempfile,time
from collections import Counter
from contextlib import closing
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('compiler',type=Path);p.add_argument('source_probe',type=Path);p.add_argument('--output',type=Path);p.add_argument('--retained-sdk',type=Path);a=p.parse_args()
probe=a.probe.resolve();compiler=a.compiler.resolve();source_probe=a.source_probe.resolve();temporary=None
if a.retained_sdk:a.retained_sdk=a.retained_sdk.resolve(strict=True)
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex stream histories ');root=Path(temporary.name).resolve()
fixtures=Path(__file__).resolve().parent/'fixtures';started=time.monotonic()
report={'schema':'nex.private024-expanded-stream-histories/1','ok':False,'state':'starting','commands':[],'cases':[],'rejections':[],
 'probe_sha256':hashlib.sha256(probe.read_bytes()).hexdigest(),'compiler_sha256':hashlib.sha256(compiler.read_bytes()).hexdigest(),'source_probe_sha256':hashlib.sha256(source_probe.read_bytes()).hexdigest(),
 'public_language':'0.28','private_language':'0.24','public025_delivery_accepted':False,'full_objective_complete':False}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,d):p.write_text(json.dumps(d,indent=2,ensure_ascii=False)+'\n', newline="\n")
def save():report['seconds']=round(time.monotonic()-started,3);write(root/'report.json',report)
def state(project):
 database=(project/'.nex/graph.db').resolve();uri=database.as_uri()+'?mode=ro'+('&immutable=1' if not Path(str(database)+'-wal').exists() else '')
 with closing(sqlite3.connect(uri,uri=True)) as db:
  names=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  return {'schema':db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),'tables':{n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}}
def preserved(before,after):
 assert before['schema']==after['schema'] and len(before['tables'])==len(after['tables'])==16
 for table,rows in before['tables'].items():
  if table!='head':assert not (Counter(rows)-Counter(after['tables'][table])),table
 assert before['tables']['metadata']==after['tables']['metadata']
def run(label,argv,project=None,expected=0,env=None):
 report['state']=label;save();r=subprocess.run(list(map(str,argv)),cwd=project or root,env=env or os.environ,capture_output=True,text=True,timeout=240)
 (root/(label+'.stdout')).write_text(r.stdout, newline="\n");(root/(label+'.stderr')).write_text(r.stderr, newline="\n")
 report['commands'].append({'name':label,'argv':list(map(str,argv)),'cwd':str(project or root),'exit_code':r.returncode,'expected':expected});save()
 assert r.returncode==expected,(label,r.returncode,r.stdout[-2500:],r.stderr[-2500:]);return r

def restore(name,meta,sql):
 project=root/name;project.mkdir();(project/'.nex').mkdir();write(project/'nex.json',meta['project_manifest'])
 for n,text in meta['revisions'][-1]['physical_files'].items():
  relative=Path(n);assert not relative.is_absolute() and '..' not in relative.parts
  path=project/relative;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text, newline="\n")
 if meta['lock'] is not None:write(project/'nex.lock.json',meta['lock'])
 (project/'files').mkdir();(project/'files/input').write_bytes(b'abcdef')
 with closing(sqlite3.connect(project/'.nex/graph.db')) as db:db.executescript(sql)
 return project

def invoke(label,project,meta,row,extra=None,expected=0):
 request={'schema':'nex.private-stream-migration-request/1','project':str(project),'expected_revision':meta['head'],'origin_revision':row['revision'],'target_language':'0.24',**(extra or {})}
 path=root/(label+'.request.json');write(path,request);env={**os.environ,'NEX_FILES_ROOT':str(project/'files'),'NEX_FILES_WRITE':'1'}
 return json.loads(run(label,[probe,path,root/(label+'-evidence')],env=env,expected=expected).stdout)
try:
 for name in ('generic-modules','aggregate-aliases','callable-unicode','whole-file-tasks','locked-library'):
  stem=fixtures/('language-0.23-sdk1335-stream-'+name+'.json');meta=json.loads(stem.read_text());sql=stem.with_suffix('.sql').read_text()
  assert meta['all_revisions_produced_by_actual023_SDK'] and not meta['retagged_history']
  assert hashlib.sha256(sql.encode()).hexdigest()==meta['SQL_sha256'] and meta['producer_language']=='0.23' and len(meta['revisions'])==3
  if a.retained_sdk:assert sha(a.retained_sdk)==meta['producer_compiler_sha256']
  for i,row in enumerate(meta['revisions']):
   label=name+'-'+str(i);project=restore(label,meta,sql);before=state(project)
   physical={n:(project/n).read_bytes() for n in [*meta['revisions'][-1]['physical_files'],'nex.json',*(['nex.lock.json'] if meta['lock'] else [])]}
   value=invoke(label+'-migrate',project,meta,row,{'execute':True});after=state(project);preserved(before,after)
   assert value['origin_verified'] and value['origin_revision']==row['revision'] and value['origin_language']=='0.23' and value['language']=='0.24' and value['public_default']=='0.28'
   assert value['target_value']==row['expected_value'] and value['target_stdout']==''
   if row['old_error']:assert value['old_error']==row['old_error']
   else:assert value['old_value']==row['old_value'] and value['old_stdout']==''
   assert len(after['tables']['revisions'])==4 and after['tables']['head']==[(1,value['revision'])]
   assert all((project/n).read_bytes()==data for n,data in physical.items())
   invoke(label+'-idempotent',project,meta,row,{'expected_revision':value['revision']});assert state(project)==after
   binary=Path(value['executable']);hidden=[]
   for n in meta['revisions'][-1]['physical_files']:
    path=project/n;other=path.with_name(path.name+'.hidden');path.rename(other);hidden.append((path,other))
   try:
    native=run(label+'-native',[binary],expected=row['expected_value'],env={**os.environ,'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(project/'files'),'NEX_FILES_WRITE':'1'})
    assert native.stdout==native.stderr==''
   finally:
    for path,other in hidden:other.rename(path)
   if name=='whole-file-tasks':assert (project/'files/output').read_text()=='Привет 🧠'
   else:assert not (project/'files/output').exists()
   assert (project/'files/input').read_bytes()==b'abcdef'
   cli_env=dict(os.environ);cli_env.pop('NEX_RESOURCE_DIR',None)
   if a.retained_sdk:
    old=run(label+'-installed-old-revision',[a.retained_sdk,'eval','--revision',row['revision'],'--json'],project,1 if row['old_error'] else 0,{**cli_env,'NEX_FILES_ROOT':str(project/'files'),'NEX_FILES_WRITE':'1'})
    old=json.loads(old.stdout)
    if row['old_error']:assert old['code']==row['old_error']
    else:assert old['value']==row['old_value'] and old['stdout']==''
    assert state(project)==after
   refused=run(label+'-public-head-guard',[compiler,'check','--json'],project,1,cli_env)
   assert json.loads(refused.stdout)['code']=='E_LANGUAGE_VERSION' and state(project)==after
   bundle=root/(label+'-bundle.json');write(bundle,row['bundle']);web=root/(label+'-web')
   emitted=json.loads(run(label+'-web-emission',[source_probe,'web',bundle,project,web,'0.24']).stdout);assert emitted['ok']
   text='\n'.join(q.read_text() for q in web.glob('program.ts'))
   assert 'file_open_read' not in text and 'file_read_bytes' not in text and 'histories::' not in text
   (web/'package.json').write_text('{"type":"module"}\n', newline="\n");(web/'run.mjs').write_text("import {entry} from './program.ts';process.stdout.write(String(entry())+'\\n');\n", newline="\n")
   client=run(label+'-typescript',[os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--disable-warning=ExperimentalWarning',web/'run.mjs'])
   assert client.stdout==str(row['expected_value'])+'\n' and client.stderr==''
   report['cases'].append({'name':label,'origin_revision':row['revision'],'revision':value['revision'],'expected_value':row['expected_value'],'old_error':row['old_error'],
    'all16_tables_schema_rows_ids_preserved':True,'physical_sources_manifest_lock_preserved':True,'old_revision_rechecked':True,'installed_old_sdk_rechecked':bool(a.retained_sdk),
    'native_reference':True,'pure_client_TypeScript':True,'source_absent_native':True,'idempotent':True,'physical_manifest_guard':True,
    'executable':str(binary),'executable_sha256':sha(binary),'fixture_sha256':sha(stem),'SQL_sha256':meta['SQL_sha256']});save()
  for suffix,extra,code in [('disguise',{'declared_language':'0.24'},'E_REVISION'),('stale',{'expected_revision':'0'*64},'E_CONFLICT'),('implicit',{'unversioned_synchronize':True},'E_LANGUAGE_VERSION')]:
   label=name+'-'+suffix;project=restore(label,meta,sql);before=state(project);result=invoke(label,project,meta,meta['revisions'][-1],extra,1)
   assert result['code']==code and state(project)==before
   report['rejections'].append({'name':label,'code':code,'store_unchanged':True});save()
 report.update(ok=True,state='passed',genuine023_histories=5,genuine023_revisions=len(report['cases']),native_reference_pairs=len(report['cases']),pure_client_TypeScript_cases=len(report['cases']),
  rejected_migrations=len(report['rejections']),all16_tables_schema_rows_ids_preserved=True,installed_old_SDK_cases=len(report['cases']) if a.retained_sdk else 0)
except BaseException as error:report.update(ok=False,state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ('ok','state','genuine023_revisions','rejected_migrations','error')}),flush=True)
