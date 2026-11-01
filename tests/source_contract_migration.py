"""Actual027 snapshots, explicit028 migration and stored-program execution."""
from pathlib import Path
from sqlite_fixture import connection as sqlite_connection
from host_fixture import run_native,probe_dll_inputs
import argparse,collections,hashlib,json,os,platform,re,sqlite3,tempfile
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('runtime_probe');p.add_argument('--compiler',required=True);p.add_argument('--native-host',required=True);p.add_argument('--output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];probe=str(Path(a.probe).resolve());runtime_probe=str(Path(a.runtime_probe).resolve())
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-source-contract-migration-'));out.mkdir(parents=True,exist_ok=a.output is None)
stem=root/'tests/fixtures/language-0.27-contract-origin';meta=json.loads(Path(str(stem)+'.json').read_text());sql=Path(str(stem)+'.sql').read_bytes()
assert meta['language']=='0.27' and not meta['retagged_source'] and meta['producer']['toolchain']=='0.156.0'
assert hashlib.sha256(sql).hexdigest()==meta['sql_sha256']
env={**os.environ,'NEX_RESOURCE_DIR':str(root),'PYTHONDONTWRITEBYTECODE':'1'};report={'schema':'nex.source-contract-migration-tests/1','ok':False,'origin':'0.27','target':'0.28','cases':[],'commands':[]}
def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,command,allowed=(0,)):
 r=run_native(list(map(str,command)),env=env,text=True,capture_output=True,timeout=180)
 (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
 report['commands'].append({'name':label,'exit_code':r.returncode});save()
 assert r.returncode in allowed,(label,r.returncode,r.stdout[-3000:],r.stderr[-4000:]);return r
def project(name):
 d=out/name;d.mkdir();(d/'.nex').mkdir()
 (d/'main.nex').write_text(meta['source']);(d/'nex.json').write_text('{"schema":"nex.project/1","language":"0.27","entry":"main.nex"}\n')
 with sqlite_connection(d/'.nex/graph.db') as c:c.executescript(sql.decode())
 return d
def snapshot(d):
 c=sqlite3.connect('file:'+str(d/'.nex/graph.db')+'?mode=rw',uri=True)
 try:
  c.execute('PRAGMA query_only=ON');schema=tuple(c.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"))
  rows={n:collections.Counter(tuple(r) for r in c.execute('SELECT * FROM "'+n+'"')) for n, in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
 finally:c.close()
 return schema,rows
def call(label,d,mode='plan',expected=None,code=None,**extra):
 request={'schema':'nex.typed-error-migration-request/1','target_language':'0.28','mode':mode,'project':str(d),'expected_revision':meta['head'] if expected is None else expected,**extra}
 f=out/(label+'.json');f.write_text(json.dumps(request)+'\n')
 r=run(label,[probe,f],allowed=(1,) if code else (0,));v=json.loads(r.stdout)
 assert v['ok'] is (code is None),(label,v)
 if code:assert v['code']==code,(label,code,v)
 report['cases'].append({'name':label,'passed':True,'code':code});save();return v
def bundle(source):return {'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':source}}
def candidate(plan,source):
 return {'schema':'nex.migration-candidate/1','origin_revision':meta['head'],'origin_language':'0.27','origin_source_hash':plan['origin_source_hash'],'target_language':'0.28','sources':bundle(source)}
save()
d=project('ordinary-origin');before=snapshot(d);assert len(before[1])==16
original_bytes=(d/'.nex/graph.db').read_bytes();plan=call('readonly-plan',d)
assert snapshot(d)==before and (d/'.nex/graph.db').read_bytes()==original_bytes
assert plan['origin_verified'] and plan['target_revision']!=meta['head']
for key,value,code in [('origin_revision','0'*64,'E_MIGRATION_CANDIDATE'),('origin_language','0.26','E_MIGRATION_CANDIDATE'),('origin_source_hash','0'*64,'E_MIGRATION_CANDIDATE'),('target_language','0.27','E_MIGRATION_CANDIDATE')]:
 bad=candidate(plan,meta['source']);bad[key]=value;call('guard-'+key,d,candidate=bad,code=code);assert snapshot(d)==before
call('unguarded',d,mode='unguarded',code='E_LANGUAGE_VERSION');assert snapshot(d)==before
call('tampered-plan',d,mode='tampered-plan',code='E_REVISION');assert snapshot(d)==before
applied=call('ordinary-apply',d,mode='apply');after=snapshot(d)
assert applied['language']=='0.28' and applied['identity_namespace']==plan['namespace'] and not applied['materialized']
assert after[0]==before[0]
for table,rows in before[1].items():
 if table!='head':assert not rows-after[1][table],table
assert (d/'main.nex').read_text()==meta['source'] and json.loads((d/'nex.json').read_text())['language']=='0.27'
for old,expected in zip(meta['revisions'],meta['actual_origin_evaluation']):
 actual=call('retained-'+old[:8],d,mode='evaluate',revision=old);assert actual['language']=='0.27' and actual['ast']==actual['ir']
 assert actual['ast']['stdout']==expected['stdout'] and actual['ast']['value']==expected['value']
again=call('idempotent',d,mode='apply',expected=applied['revision']);assert not again['changed'] and snapshot(d)==after
# Same current-language source still receives distinct028 semantic revision.
v=call('new-ordinary-evaluate',d,mode='evaluate',revision=applied['revision']);assert v['ast']==v['ir'] and v['ast']['value']==42
reviewed=project('reviewed-source');prior=snapshot(reviewed);plan=call('reviewed-plan',reviewed)
source=meta['source'].replace('fn step(n:i64)->i64 !{io}{','fn step(n:i64)->i64 !{io} requires(n==42) ensures(value=>value==n){')
assert source!=meta['source']
invalid=candidate(plan,source.replace('requires(n==42)','requires(42)'))
call('invalid-predicate',reviewed,candidate=invalid,code='E_TYPE');assert snapshot(reviewed)==prior
export=out/'exported028';result=call('reviewed-apply-export',reviewed,mode='apply',candidate=candidate(plan,source),export=str(export))
assert result['export_roundtrip'] and json.loads((export/'nex.json').read_text())['language']=='0.28'
after_review=snapshot(reviewed);assert after_review[0]==prior[0]
for table,rows in prior[1].items():
 if table!='head':assert not rows-after_review[1][table],table
stored=call('stored-contract-evaluate',reviewed,mode='evaluate',revision=result['revision'])
assert stored['ast']==stored['ir']=={'stdout':'caught\nfinally\n','value':42}
host=out/'host.ll';run('host-layout',[a.compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',host]);text=host.read_text()
triple=re.search(r'target triple = "(.*?)"',text)[1];layout=re.search(r'target datalayout = "(.*?)"',text)[1]
for optimized in [False,True]:
 dest=out/('stored-O2' if optimized else 'stored-O0');dest.mkdir()
 emitted=call(dest.name,reviewed,mode='emit',revision=result['revision'],output=str(dest),triple=triple,layout=layout,optimized=optimized)
 lib=dest/('program.dylib' if platform.system()=='Darwin' else 'program.dll' if os.name=='nt' else 'program.so')
 flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared',*probe_dll_inputs(runtime_probe,out)] if os.name=='nt' else ['-shared','-fPIC']
 run(dest.name+'-compile',[a.compiler,'-O2' if optimized else '-O0',*flags,dest/'program.ll','-o',lib])
 actual=run(dest.name+'-execute',[a.native_host,'run',lib],allowed=(42,));assert actual.stdout=='caught\nfinally\n' and not actual.stderr
 assert snapshot(reviewed)==after_review
# Rechecking the source exported from the archive agrees with stored code.
checked=json.loads(run('exported-check',[runtime_probe,'check',export/'main.nex']).stdout);assert checked['revision']==result['revision']
for mode in ['reference','ast','ir']:
 actual=json.loads(run('exported-'+mode,[runtime_probe,mode,export/'main.nex']).stdout);assert actual['kind']=='return' and actual['value']==42 and actual['output']=='caught\nfinally\n'
corrupt=project('corrupt-origin')
with sqlite_connection(corrupt/'.nex/graph.db') as c:c.execute('UPDATE revisions SET language=? WHERE hash=?',('0.26',meta['head']))
previous=snapshot(corrupt);call('retagged-origin',corrupt,code='E_REVISION');assert snapshot(corrupt)==previous
race=project('race');previous=snapshot(race);plan=call('race-plan',race)
# The competing guarded writer commits another028 snapshot first. Applying the
# previously guarded plan must leave that writer's entire state intact.
other=source.replace('n==42','n>=0');call('race-guard',race,mode='race',candidate=candidate(plan,source),race_sources=bundle(other),code='E_CONFLICT')
assert (race/'race-before-apply.db').is_file()
with sqlite_connection(race/'race-before-apply.db') as old,sqlite_connection(race/'.nex/graph.db') as new:
 for name, in old.execute("SELECT name FROM sqlite_master WHERE type='table'"):
  assert collections.Counter(old.execute('SELECT * FROM "'+name+'"'))==collections.Counter(new.execute('SELECT * FROM "'+name+'"')),name
report.update(ok=True,original_tables=16,retained_revisions=2,all_original_rows_except_HEAD_preserved=True,original_physical_files_preserved=True,native_optimizations=['O0','O2'],explicit_reviewed_source=True);save()
print(json.dumps({'ok':True,'cases':len(report['cases']),'report':str(out/'report.json')}))
