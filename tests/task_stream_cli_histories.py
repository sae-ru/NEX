from host_fixture import run_native, probe_dll_inputs
"""Public CLI migration of all genuine SDK1335 stream and mixed FFI revisions."""
import argparse,copy,json,os,re,sqlite3,subprocess,tempfile,time
from collections import Counter
from contextlib import closing
from pathlib import Path
from task_stream_ffi_fixture import build_provider,sha,write

p=argparse.ArgumentParser();p.add_argument('compiler',type=Path);p.add_argument('--resources',type=Path);p.add_argument('--retained-sdk',type=Path);p.add_argument('--output',type=Path);p.add_argument('--case',action='append',dest='selected');a=p.parse_args()
compiler=a.compiler.resolve();resources=(a.resources or Path(__file__).resolve().parents[1]).resolve();temporary=None
if a.output:root=a.output.resolve();root.mkdir()
else:temporary=tempfile.TemporaryDirectory(prefix='nex public025 histories ');root=Path(temporary.name).resolve()
if a.retained_sdk:a.retained_sdk=a.retained_sdk.resolve(strict=True)
fixtures=resources/'tests/fixtures'
if not (fixtures/'language-0.23-sdk1335-stream-generic-modules.json').is_file():fixtures=resources/'examples/task-stream-migration'
started=time.monotonic();report={'schema':'nex.public025-stream-cli-histories/1','ok':False,'state':'starting','commands':[],'cases':[],'rejections':[],'providers':{},'compiler_sha256':sha(compiler),'language':'0.27','installed_SDK_accepted':False,'full_objective_complete':False}
def save():report['seconds']=round(time.monotonic()-started,3);write(root/'report.json',report)
def run(label,argv,cwd=None,env=None,expected=0):
 report['state']=label;save();r=run_native(argv,cwd=cwd or root,env=env or os.environ,capture_output=True,text=True,timeout=300)
 (root/(label+'.stdout')).write_text(r.stdout, newline="\n");(root/(label+'.stderr')).write_text(r.stderr, newline="\n");report['commands'].append({'name':label,'argv':list(map(str,argv)),'cwd':str(cwd or root),'exit_code':r.returncode,'expected':expected});save();assert r.returncode==expected,(label,r.returncode,r.stdout[-2500:],r.stderr[-2500:]);return r
def cli(label,project,argv,env=None,expected=0,exe=compiler):return json.loads(run(label,[exe,*argv,'--json'],project,env,expected).stdout)
def state(project):
 db=(project/'.nex/graph.db').resolve();uri=db.as_uri()+'?mode=ro'+('&immutable=1' if not Path(str(db)+'-wal').exists() else '')
 with closing(sqlite3.connect(uri,uri=True)) as connection:
  tables=[n for n, in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
  return {'schema':connection.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),'tables':{n:sorted(connection.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in tables}}
def preserved(before,after):
 assert before['schema']==after['schema'] and len(before['tables'])==len(after['tables'])==16
 for name,rows in before['tables'].items():
  if name!='head':assert not Counter(rows)-Counter(after['tables'][name]),name
 assert before['tables']['metadata']==after['tables']['metadata']
def restore(label,meta,sql):
 project=root/label;project.mkdir();(project/'.nex').mkdir();write(project/'nex.json',meta['project_manifest'])
 for name,text in meta['revisions'][-1]['physical_files'].items():
  path=Path(name);assert not path.is_absolute() and '..' not in path.parts;path=project/path;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(text, newline="\n")
 if meta.get('lock') is not None:write(project/'nex.lock.json',meta['lock'])
 with closing(sqlite3.connect(project/'.nex/graph.db')) as db:db.executescript(sql)
 for backend in ['reference','native']:
  folder=project/backend;folder.mkdir();(folder/'input').write_bytes(b'abcdef')
 return project
def reviewed_delivery_sources(sources):
 # This is an explicit candidate for these genuine histories, not a mutation
 # of their archived rows. Keep task callable declarations and types coherent.
 target=copy.deepcopy(sources)
 for name,text in target['files'].items():
  masked=re.sub(r'//[^\n]*|"(?:\\.|[^"\\])*"',lambda m:' '*len(m[0]),text)
  edits=[m.end(1) for m in re.finditer(r'!\{([^{}]*)\}',masked)
         if 'task' in {v.strip() for v in m[1].split(',')} and 'throw' not in {v.strip() for v in m[1].split(',')}]
  for end in reversed(edits):text=text[:end]+',throw'+text[end:]
  target['files'][name]=text
 return target
try:
 descriptor=cli('describe',root,['describe']);assert descriptor['version']=='0.27' and descriptor['task_file_streams']['public_enabled'] and descriptor['task_file_streams']['native_source_lowering']
 # Completion of this current migration matrix is evidence produced below;
 # do not require or silently change a compiler-wide delivery acceptance flag.
 report['descriptor_history_migration_complete']=descriptor['task_file_streams']['public_history_migration_complete']
 names=[('stream-'+name,'stream-'+name) for name in ['generic-modules','aggregate-aliases','callable-unicode','whole-file-tasks','locked-library']]
 names += [('mixed-'+d+'-'+k,'mixed-'+d+'-'+k) for d in ['c11','cxx20'] for k in ['stream','whole-file']]
 if a.selected:
  assert set(a.selected)<={name for name,_ in names};names=[row for row in names if row[0] in a.selected]
 for name,stem in names:
  fixture=fixtures/('language-0.23-sdk1335-'+stem+'.json');meta=json.loads(fixture.read_text());sql=fixture.with_suffix('.sql');assert sha(sql)==meta['SQL_sha256'] and len(meta['revisions'])==3 and meta['all_revisions_produced_by_actual023_SDK'] and not meta['retagged_history']
  host=None;original_available=True;projected=False
  if 'provider' in meta:
   if meta['dialect'] not in report['providers']:
    report['providers'][meta['dialect']]=build_provider(resources,root/(meta['dialect']+'-provider'),meta['dialect'],meta['provider']['source'],meta['provider']['signatures'],run,meta['dialect'])
   provider=report['providers'][meta['dialect']];host=provider['host'];projected=provider['manifest_sha256']!=meta['provider']['manifest_sha256'];original_available=not projected
  for index,row in enumerate(meta['revisions']):
   label=name+'-'+str(index);project=restore(label,meta,sql.read_text());before=state(project)
   physical={n:(project/n).read_bytes() for n in [*meta['revisions'][-1]['physical_files'],'nex.json',*(['nex.lock.json'] if meta.get('lock') is not None else [])]}
   refused=cli(label+'-old-root',project,['check'],expected=1);assert refused['code']=='E_LANGUAGE_VERSION' and state(project)==before
   arguments=['migrate','--revision',row['revision']]
   plan=cli(label+'-plan',project,[*arguments,'--kind','plan']);assert plan['origin_verified'] and state(project)==before
   if not plan['target_valid']:
    assert plan['target_diagnostic']['code']=='E_EFFECT'
    refused=cli(label+'-unreviewed-delivery',project,arguments,expected=1);assert refused['code']=='E_EFFECT' and state(project)==before
   candidate=copy.deepcopy(plan['candidate']);assert candidate['sources']==row['bundle']
   if not plan['target_valid']:candidate['sources']=reviewed_delivery_sources(candidate['sources'])
   reviewed_effects=candidate['sources']!=row['bundle']
   if projected:
    # A reviewed candidate is backed by the genuine retained archive. The CLI
    # verifies that original row before checking these changed manifest pins.
    text=candidate['sources']['files']['main.nex'];assert text.count(meta['provider']['manifest_sha256'])==3
    candidate['sources']['files']['main.nex']=text.replace(meta['provider']['manifest_sha256'],provider['manifest_sha256'])
   reviewed_candidate=candidate['sources']!=row['bundle']
   if reviewed_candidate:
    path=root/(label+'-reviewed-target.json');write(path,candidate);arguments.extend(['--candidate',path])
    valid=cli(label+'-reviewed-plan',project,[*arguments,'--kind','plan']);assert valid['origin_verified'] and valid['target_valid'] and valid['candidate_used'] and state(project)==before
   else:assert plan['target_valid']
   migrated=cli(label+'-migrate',project,[*arguments,'--expected-revision',meta['head']]);assert migrated['origin_verified'] and migrated['origin_language']=='0.23' and migrated['language']=='0.27' and not migrated['materialized'] and migrated['revision']!=row['revision']
   assert migrated['candidate_used']==reviewed_candidate and migrated['declared_original_revision']==row['revision']
   after=state(project);preserved(before,after);assert len(after['tables']['revisions'])==4 and after['tables']['head']==[(1,migrated['revision'])]
   with closing(sqlite3.connect(project/'.nex/graph.db')) as db:
    original=db.execute('SELECT source,language FROM revisions WHERE hash=?',(row['revision'],)).fetchone();assert json.loads(original[0])==row['bundle'] and original[1]=='0.23'
    target=db.execute('SELECT source,language FROM revisions WHERE hash=?',(migrated['revision'],)).fetchone();assert json.loads(target[0])==candidate['sources'] and target[1]=='0.27'
   assert all((project/n).read_bytes()==data for n,data in physical.items())
   repeated=cli(label+'-idempotent',project,['migrate','--revision',migrated['revision'],'--expected-revision',migrated['revision']]);assert repeated['revision']==migrated['revision'] and not repeated['changed'] and state(project)==after
   current_env={**os.environ,'NEX_FILES_ROOT':str(project/'reference'),'NEX_FILES_WRITE':'1'}
   marker=root/(label+'-reference.events');current_env['NEX_TYPED_RESOURCE_MARKER']=str(marker)
   foreign=['--foreign',host] if host else []
   reference=cli(label+'-reference',project,['eval','--revision',migrated['revision'],*foreign],current_env);assert reference['value']==row['expected_value'] and reference['stdout']==''
   built=cli(label+'-build',project,['build','--revision',migrated['revision'],'--profile','release']);binary=Path(built['executable'])
   hidden=[]
   for n in meta['revisions'][-1]['physical_files']:
    path=project/n;other=path.with_name(path.name+'.hidden');path.rename(other);hidden.append((path,other))
   native_marker=root/(label+'-native.events')
   try:
    native=run(label+'-source-absent-native',[binary,*(['--nex-foreign',host] if host else [])],env={'PATH':'/usr/bin:/bin','NEX_FILES_ROOT':str(project/'native'),'NEX_FILES_WRITE':'1','NEX_TYPED_RESOURCE_MARKER':str(native_marker)},expected=row['expected_value']);assert native.stdout==native.stderr==''
   finally:
    for path,other in hidden:other.rename(path)
   if host:
    for event in [marker,native_marker]:
     text=event.read_text();assert text.startswith('I') and text.endswith('D') and text.count('F')==text.count('X')==1
   for backend in ['reference','native']:
    assert (project/backend/'input').read_bytes()==b'abcdef'
    if name=='stream-whole-file-tasks':assert (project/backend/'output').read_text()=='Привет 🧠'
    else:assert not (project/backend/'output').exists()
   old_sdk_rechecked=False
   if a.retained_sdk and original_available:
    assert sha(a.retained_sdk)==meta['producer_compiler_sha256'];env=dict(current_env);env.pop('NEX_RESOURCE_DIR',None);env['NEX_TYPED_RESOURCE_MARKER']=str(root/(label+'-old.events'))
    old=cli(label+'-retained-sdk',project,['eval','--revision',row['revision'],*foreign],env,1 if row['old_error'] else 0,a.retained_sdk)
    if row['old_error']:assert old['code']==row['old_error']
    else:assert old['value']==row['old_value'] and old['stdout']==''
    assert state(project)==after;old_sdk_rechecked=True
   old_refused=cli(label+'-old-execution-guard',project,['eval','--revision',row['revision']],expected=1);assert old_refused['code']=='E_LANGUAGE_VERSION' and state(project)==after
   destination=root/(label+'-export');cli(label+'-export',project,['export','--revision',migrated['revision'],'--directory',destination]);assert json.loads((destination/'nex.json').read_text())['language']=='0.27'
   materialized=cli(label+'-materialized-check',destination,['check']);assert materialized['revision']==migrated['revision']
   report['cases'].append({'name':label,'origin_revision':row['revision'],'revision':migrated['revision'],'expected_value':row['expected_value'],'native_reference':True,'all16_tables_schema_rows_ids_preserved':True,'physical_sources_manifest_lock_preserved':True,'idempotent':True,'materialized_current_project_checked':True,'source_absent_native':True,'old_SDK_rechecked':old_sdk_rechecked,'original_pinned_provider_available':original_available,'reviewed_foreign_pin_projection':projected,'reviewed_delivery_effects':reviewed_effects,'candidate_used':reviewed_candidate,'executable':str(binary),'executable_sha256':sha(binary),'fixture_sha256':sha(fixture),'SQL_sha256':meta['SQL_sha256']});save()
  project=restore(name+'-stale',meta,sql.read_text());before=state(project);refused=cli(name+'-stale',project,['migrate','--expected-revision','0'*64],expected=1);assert refused['code']=='E_CONFLICT' and state(project)==before
  report['rejections'].append({'name':name+'-stale','code':'E_CONFLICT','store_unchanged':True});save()
 report.update(ok=True,state='passed',genuine023_histories=len(names),genuine023_revisions=len(report['cases']),native_reference_pairs=len(report['cases']),retained_SDK_cases=sum(row['old_SDK_rechecked'] for row in report['cases']),rejected_migrations=len(report['rejections']))
except BaseException as error:report.update(ok=False,state='failed',error=repr(error));raise
finally:save();print(json.dumps({k:report.get(k) for k in ['ok','state','genuine023_revisions','native_reference_pairs','rejected_migrations','error']}),flush=True)
