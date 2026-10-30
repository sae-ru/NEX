#!/usr/bin/env python3
"""Genuine026 history, guarded027 publication and actual stored-code execution."""
import argparse,ast,collections,hashlib,json,os,platform,re,shutil,sqlite3,subprocess,tempfile
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--compiler',required=True);p.add_argument('--ordinary-compiler');p.add_argument('--output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];probe=str(Path(a.probe).resolve());runtime=root/'runtime'
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-typed-error-migration-'));out.mkdir(exist_ok=a.output is None,parents=True)
meta=json.loads((root/'tests/fixtures/language-0.26-typed-origin.json').read_text());sql=(root/'tests/fixtures/language-0.26-typed-origin.sql').read_bytes()
assert hashlib.sha256(sql).hexdigest()==meta['sql_sha256'] and meta['producer']['toolchain']=='0.139.0' and not meta['retagged_source']
report={'ok':False,'public027_enabled':False,'cases':[],'commands':[]}
def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def run(label,command,allowed=(0,)):
    r=subprocess.run(list(map(str,command)),text=True,capture_output=True,timeout=180,env={**os.environ,'NEX_RESOURCE_DIR':str(root)})
    (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
    report['commands'].append({'name':label,'exit_code':r.returncode});save()
    assert r.returncode in allowed,(label,r.returncode,r.stdout[-3000:],r.stderr[-5000:]);return r
def project(name,origin=meta,source_sql=sql):
    d=out/name;d.mkdir();(d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'}));(d/'.nex').mkdir()
    for filename,text in origin.get('files',{'main.nex':origin.get('source','')}).items():(d/filename).write_text(text)
    with sqlite3.connect(d/'.nex/graph.db') as db:db.executescript(source_sql.decode())
    return d
def snapshot(path):
    # The independent Python SQLite may need to initialize WAL bookkeeping
    # after the deliberate writable-Store negative control. SQL stays query-only;
    # the production migration preflight is separately opened READONLY in C++.
    db=sqlite3.connect('file:'+str(path)+'?mode=rw',uri=True)
    try:
        db.execute('PRAGMA query_only=ON')
        schema=tuple(db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name"))
        tables={}
        for (name,) in db.execute("SELECT name FROM sqlite_master WHERE type='table'"):
            tables[name]=collections.Counter(tuple(row) for row in db.execute('SELECT * FROM "'+name+'"'))
    finally:db.close()
    return schema,tables
def bundle(text):return {'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':text}}
def call(name,d,mode='plan',expected=None,code=None,**extra):
    request={'schema':'nex.typed-error-migration-request/1','mode':mode,'project':str(d),'expected_revision':meta['head'] if expected is None else expected,**extra}
    path=out/(name+'.json');path.write_text(json.dumps(request,ensure_ascii=False)+'\n');r=run(name,[probe,path],(1,) if code else (0,));v=json.loads(r.stdout)
    assert v['ok'] is (code is None),(name,v)
    if code:assert v['code']==code,(name,v)
    report['cases'].append({'name':name,'passed':True,'code':code});save();return v
def unchanged(d,before):assert snapshot(d/'.nex/graph.db')==before
def candidate(plan,text):return {'schema':'nex.migration-candidate/1','origin_revision':meta['head'],'origin_language':'0.26','origin_source_hash':plan['origin_source_hash'],'target_language':'0.27','sources':bundle(text)}

simple=project('same-source');before=snapshot(simple/'.nex/graph.db');assert len(before[1])==16
original_bytes=(simple/'.nex/graph.db').read_bytes();plan=call('same-plan',simple)
unchanged(simple,before);assert (simple/'.nex/graph.db').read_bytes()==original_bytes
assert plan['origin_verified'] and plan['target_revision']!=meta['head']
call('stale-head',simple,expected='f'*64,code='E_CONFLICT');unchanged(simple,before)
call('no-head-guard',simple,expected='',code='E_OPTION');unchanged(simple,before)
call('unguarded-save',simple,mode='unguarded',code='E_LANGUAGE_VERSION');unchanged(simple,before)
call('modified-plan',simple,mode='tampered-plan',code='E_REVISION');unchanged(simple,before)
bad=candidate(plan,'module bad;fn main()->unit{throw(42);}')
call('bad-candidate',simple,candidate=bad,code='E_EFFECT');unchanged(simple,before)
for key,value,code in [('origin_revision','0'*64,'E_MIGRATION_CANDIDATE'),('origin_language','0.25','E_MIGRATION_CANDIDATE'),('origin_source_hash','0'*64,'E_MIGRATION_CANDIDATE'),('target_language','0.26','E_MIGRATION_CANDIDATE')]:
    bad=candidate(plan,meta['source']);bad[key]=value;call('guard-'+key,simple,candidate=bad,code=code);unchanged(simple,before)
missing=out/'absent';call('missing-store',missing,code='E_STORE');assert not missing.exists()
retag=project('retagged');
with sqlite3.connect(retag/'.nex/graph.db') as db:db.execute('UPDATE revisions SET language=? WHERE hash=?',('0.1',meta['head']))
old=snapshot(retag/'.nex/graph.db');call('retagged-origin',retag,code='E_REVISION');unchanged(retag,old)
applied=call('same-apply',simple,mode='apply');assert applied['language']=='0.27' and applied['revision']==plan['target_revision'] and applied['identity_namespace']==plan['namespace'] and not applied['materialized']
after=snapshot(simple/'.nex/graph.db');assert after[0]==before[0]
for table,rows in before[1].items():
    if table!='head':assert not (rows-after[1][table]),table
assert (simple/'main.nex').read_text()==meta['source'] and json.loads((simple/'nex.json').read_text())['language']=='0.26'
for rev,text in zip(meta['revisions'],meta['actual_origin_eval_stdout']):
    v=call('retained-'+rev[:6],simple,mode='evaluate',revision=rev);assert v['language']=='0.26' and v['ast']==v['ir'] and v['ast']['stdout']==text
v=call('same-evaluate',simple,mode='evaluate',revision=applied['revision']);assert v['ast']==v['ir'] and v['ast']['stdout']=='42\n'
assert v['lock']['language']=='0.27'
second=call('same-idempotent',simple,mode='apply',expected=applied['revision']);assert not second['changed'];assert snapshot(simple/'.nex/graph.db')==after
call('delivery-guard',simple,mode='build-guard',revision=applied['revision'],output=str(out/'forbidden-native'),code='E_TYPED_EXCEPTION_DELIVERY');assert not (out/'forbidden-native').exists()
disguised=project('modern-retagged')
with sqlite3.connect(simple/'.nex/graph.db') as source_db, sqlite3.connect(disguised/'.nex/graph.db') as target_db:source_db.backup(target_db)
with sqlite3.connect(disguised/'.nex/graph.db') as db:db.execute('UPDATE revisions SET language=? WHERE hash=?',('0.26',applied['revision']))
old=snapshot(disguised/'.nex/graph.db');call('modern-retagged-origin',disguised,expected=applied['revision'],code='E_REVISION');unchanged(disguised,old)
corrupt=project('corrupt-origin')
with sqlite3.connect(corrupt/'.nex/graph.db') as db:db.execute('UPDATE revisions SET source=? WHERE hash=?',(json.dumps(bundle(meta['source'].replace('payload(error(40))','payload(error(41))'))),meta['head']))
old=snapshot(corrupt/'.nex/graph.db');call('corrupt-origin-source',corrupt,code='E_REVISION');unchanged(corrupt,old)

typed=project('typed-candidate');typed_before=snapshot(typed/'.nex/graph.db');initial=call('typed-plan',typed)
text=meta['source'].replace('throw("APP","λ\\u0000🙂");','throw(Failure::Missing("λ\\u0000🙂"));').replace('catch(code,message) if code=="APP"{assert(message=="λ\\u0000🙂");}','catch(error:Failure){match error{Failure::Missing(path)=>{assert(path=="λ\\u0000🙂");}Failure::Denied(code)=>{assert(false);}}}')
assert 'catch(error:Failure)' in text and 'throw(Failure::Missing' in text
typed_candidate=candidate(initial,text);typed_plan=call('reviewed-typed-plan',typed,candidate=typed_candidate)
unchanged(typed,typed_before);export=out/'exported027'
typed_result=call('typed-apply',typed,mode='apply',candidate=typed_candidate,export=str(export));assert typed_result['revision']==typed_plan['target_revision']
assert typed_result['export_roundtrip']
assert json.loads((export/'nex.json').read_text())['language']=='0.27' and (export/'main.nex').read_text()==text
if a.ordinary_compiler:
    r=subprocess.run([str(Path(a.ordinary_compiler).resolve()),'check','--json'],cwd=export,text=True,capture_output=True,timeout=30)
    assert r.returncode==1 and 'E_LANGUAGE_VERSION' in r.stdout+r.stderr and not (export/'.nex').exists(),(r.returncode,r.stdout,r.stderr)
typed_after=snapshot(typed/'.nex/graph.db');assert typed_after[0]==typed_before[0]
for table,rows in typed_before[1].items():
    if table!='head':assert not (rows-typed_after[1][table]),table
race=project('raced');race_plan=call('race-plan',race)
other=bundle(meta['source'].replace('payload(error(40))','payload(error(41))'))
call('competing-head',race,mode='race',race_sources=other,code='E_CONFLICT');assert snapshot(race/'.nex/graph.db')==snapshot(race/'race-before-apply.db')
ns=project('namespace-raced');call('competing-namespace',ns,mode='namespace-race',code='E_CONFLICT');assert snapshot(ns/'.nex/graph.db')==snapshot(ns/'race-before-apply.db')
older=project('older-origin');previous=snapshot(older/'.nex/graph.db')
old_target=call('older-origin-apply',older,mode='apply',origin_revision=meta['revisions'][0]);assert old_target['origin_revision']==meta['revisions'][0]
v=call('older-origin-execution',older,mode='evaluate',revision=old_target['revision']);assert v['ast']==v['ir'] and v['ast']['stdout']=='41\n'
latest=snapshot(older/'.nex/graph.db');assert latest[0]==previous[0]
for table,rows in previous[1].items():
    if table!='head':assert not (rows-latest[1][table]),table

modular_meta=json.loads((root/'tests/fixtures/language-0.26-modular-typed-origin.json').read_text())
modular_sql=(root/'tests/fixtures/language-0.26-modular-typed-origin.sql').read_bytes()
assert hashlib.sha256(modular_sql).hexdigest()==modular_meta['sql_sha256'] and not modular_meta['retagged_source'] and modular_meta['producer']['toolchain']=='0.146.0'
modular=project('modular-origin',modular_meta,modular_sql);modular_before=snapshot(modular/'.nex/graph.db')
modular_plan=call('modular-plan',modular,expected=modular_meta['head'])
files=dict(modular_meta['files']);files['errors.nex']=files['errors.nex'].replace('throw("LIB","old");','throw(Problem<T>(value));')
files['main.nex']=files['main.nex'].replace('catch(c,m){assert(c=="LIB");print(42);}','catch(e:errors::Problem<i64>){print(e.value);}catch(c,m){assert(false);}')
assert files['errors.nex']!=modular_meta['files']['errors.nex'] and files['main.nex']!=modular_meta['files']['main.nex']
reviewed={'schema':'nex.migration-candidate/1','origin_revision':modular_meta['head'],'origin_language':'0.26','origin_source_hash':modular_plan['origin_source_hash'],'target_language':'0.27','sources':{'schema':'nex.sources/1','entry':'main.nex','files':files}}
modular_result=call('modular-apply',modular,mode='apply',expected=modular_meta['head'],candidate=reviewed,export=str(out/'exported-modular027'));assert modular_result['export_roundtrip']
modular_after=snapshot(modular/'.nex/graph.db');assert modular_after[0]==modular_before[0]
for table,rows in modular_before[1].items():
    if table!='head':assert not (rows-modular_after[1][table]),table

# Emit the reloaded committed027 graph, not a freshly parsed stand-in. The host
# checks physical native Data/Handle retirement after each real worker execution.
tree=ast.parse((root/'tests/source_exception_task_native.py').read_text())
n=next(n for n in tree.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='host' and n.value.func.attr=='write_text')
host=out/'host.cpp';host.write_text(ast.literal_eval(n.value.args[0]));objects=[]
for name in ['runtime.cpp','nex_files.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp','nex_task_application.cpp']:
    obj=out/(name+'.o');run('compile-'+name,[a.compiler,'-std=c++20','-O1','-fPIC','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),'-c',runtime/name,'-o',obj]);objects.append(obj)
binary=out/'host';run('link-host',[a.compiler,'-std=c++20','-O1','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),host,*objects,'-Wl,-export_dynamic' if platform.system()=='Darwin' else '-Wl,--export-dynamic','-pthread',*(['-ldl'] if platform.system()!='Darwin' else []),'-o',binary])
run('target',[a.compiler,'-x','c','-S','-emit-llvm','/dev/null','-o',out/'target.ll']);ll=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',ll)[1];layout=re.search(r'target datalayout = "([^"]+)"',ll)[1]
native=0;node=0
for name,d,revision in [('same',simple,applied['revision']),('typed',typed,typed_result['revision']),('modular',modular,modular_result['revision'])]:
    for optimization in ['0','2']:
        emitted=out/(name+'-O'+optimization);v=call(name+'-emit'+optimization,d,mode='emit',revision=revision,output=str(emitted),triple=triple,layout=layout,optimized=optimization=='2');assert v['descriptor_abi']==0x4e45585400002702 and v['ast']==v['ir'] and v['ast']['stdout']=='42\n'
        library=emitted/('program.dylib' if platform.system()=='Darwin' else 'program.so');flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
        run(name+'-link'+optimization,[a.compiler,'-O'+optimization,*flags,emitted/'program.ll','-o',library])
        for workers in [1,4]:
            r=run(name+'-native'+optimization+'-'+str(workers),[binary,library,'workers',workers]);assert r.stdout=='42\n' and not r.stderr,(r.stdout,r.stderr);native+=1
        runner=emitted/'run.mjs';runner.write_text("import {entry,sourceErrorContracts} from './program.ts';import * as task from './nex-task-runtime.ts';await task.runTypedSourceErrors(task.call(()=>entry()),sourceErrorContracts);\n")
        r=run(name+'-node'+optimization,[os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',runner]);assert r.stdout=='42\n';node+=1
report.update(ok=True,history_tables=16,old_revisions=2,genuine_origin=meta['producer'],genuine_modular_origin=modular_meta['producer'],ordinary_language='0.26',target_language='0.27',native_executions=native,Node_executions=node,graph_namespace_preserved=True,materialized_only_explicit_export=True);save()
print(json.dumps({k:report[k] for k in ['ok','history_tables','old_revisions','native_executions','Node_executions','graph_namespace_preserved']}))
if not a.output:shutil.rmtree(out)
