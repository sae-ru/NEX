"""Version-selected030 graphs, normal backends and retained029 migration."""
from pathlib import Path
from host_fixture import run_native, exit_code, probe_dll_inputs
from managed_reference_cases import source_cases, host_cases
from managed_reference_module_cases import module_cases
import argparse, collections, hashlib, json, os, platform, re, sqlite3, subprocess, tempfile

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('probe',type=Path);p.add_argument('compiler',type=Path);p.add_argument('migration',type=Path)
p.add_argument('--native-host',type=Path,required=True);p.add_argument('--clang',type=Path,required=True)
p.add_argument('--output',type=Path);p.add_argument('--origin-compiler',type=Path);p.add_argument('--migration-only',action='store_true')
p.add_argument('--entry-only',action='store_true')
a=p.parse_args();root=Path(__file__).resolve().parents[1]
out=(a.output or Path(tempfile.mkdtemp(prefix='nex-references030-'))).resolve();out.mkdir(parents=True,exist_ok=True)
probe=a.probe.resolve();compiler=a.compiler.resolve();migration=a.migration.resolve();native=a.native_host.resolve();clang=a.clang.absolute()
node=os.environ.get('NEX_NODE','node');tsc=os.environ.get('NEX_TSC',str(root/'web/node_modules/typescript/bin/tsc'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
report={'schema':'nex.references030-acceptance/1','ok':False,'language':'0.30','ordinary_CLI':True,'probe_sha256':sha(probe),
        'compiler_sha256':sha(compiler),'native_host_sha256':sha(native),'cases':[],'native':[],'migration':[],'gates':[]}
def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def run(command,folder,name,allowed=(0,),cwd=None):
    folder.mkdir(parents=True,exist_ok=True)
    r=run_native(list(map(str,command)),text=True,capture_output=True,timeout=180,cwd=cwd)
    (folder/(name+'.stdout')).write_text(r.stdout);(folder/(name+'.stderr')).write_text(r.stderr)
    assert r.returncode in allowed,(name,r.returncode,r.stdout[-2500:],r.stderr[-4500:]);return r
def record_error(r,ref):
    prefix='NEX_SOURCE_EXCEPTION 'if ref['code']=='E_SOURCE_EXCEPTION'else'NEX_NATIVE_TRAP '
    v=next(json.loads(line[len(prefix):])for line in r.stderr.splitlines()if line.startswith(prefix))
    if ref['code']=='E_SOURCE_EXCEPTION':assert v['code']+': '+v['message']==ref['message'] and v['line']==ref['line'],(v,ref)
    else:assert v['code']==ref['code']and v['reported_line']==ref['line'],(v,ref)
def source(folder,case):
    path=folder/('bundle.json'if'bundle'in case else'main.nex')
    if 'bundle' in case:
        path=folder/'bundle.json';bundle={**case['bundle'],'schema':'nex.sources/1'};path.write_text(json.dumps(bundle))
    else:path.write_text('module managed_native;\n'+case['source']+'\n')
    return path

if a.entry_only or not a.migration_only:
    path=root/'tests/fixtures/managed-references/value-exports.nex'
    reference=json.loads(run([probe,'reference',path],out,'entry-reference').stdout)
    result=json.loads(run([probe,'entry-test',path,out/'entry adapter 🧠\nline'],out,'entry-test').stdout)
    assert result['ok']and result['stdout']==reference['output']and not result['stderr'],result
    report['entry_adapter']={'passed':True,'stdout':result['stdout'],'unicode_newline_path':True}
if not a.migration_only and not a.entry_only:
    layout_file=out/'host.ll';run([clang,'-x','c','-S','-emit-llvm',os.devnull,'-o',layout_file],out,'host-layout')
    text=layout_file.read_text();triple=re.search(r'target triple = "(.*?)"',text)[1];layout=re.search(r'target datalayout = "(.*?)"',text)[1]
    # Tiny private budget cases retain their private acceptance. This API stage
    # uses normal execution defaults; never silently claim those custom limits.
    cases=[c for c in source_cases(root)if c.get('error')!='E_CELL_LIMIT']+[{**c,'host_only':True}for c in host_cases()]
    cases += [{**c,'name':'030-'+c['name']}for c in module_cases()if c.get('error')!='E_CELL_LIMIT']
    for case in cases:
        folder=out/case['name'];folder.mkdir(exist_ok=True);path=source(folder,case)
        inspection=json.loads(run([probe,'inspect',path],folder,'inspect').stdout)
        assert inspection['language']=='0.30'and inspection['task_language']and len(inspection['revision'])==64
        reference=json.loads(run([probe,'reference',path],folder,'reference').stdout)
        assert reference['live_delta']==0,(case['name'],reference)
        if 'error'in case:assert reference['kind']=='trap'and reference['code']==case['error'],(case['name'],reference)
        else:assert reference['kind']=='return'and reference['output']==case.get('output',''),(case['name'],reference)
        generated=folder/'generated';run([probe,'typescript',path,generated],folder,'emit-typescript')
        mapping=json.loads((generated/'nex-map.json').read_text())
        assert mapping['schema']==('nex.typescript-map/3'if inspection['references']else'nex.typescript-map/2')and mapping['revision']==inspection['revision'],(case['name'],mapping)
        if inspection['references']:assert mapping['public_revision']and mapping['ordinary_CLI']is True
        if 'absent'in case:assert case['absent']not in(generated/'program.ts').read_text()+(generated/'nex-map.json').read_text()
        source_errors=""if inspection['references']else"import * as errors from './nex-source-exception-runtime.ts';\n"
        normalize="if(!(error instanceof base.NexError))throw error;result={kind:'trap',output,code:error.code,message:error.message,line:error.site?.[1]??0,file:error.site?.[0]??''};"if inspection['references']else"if(error instanceof base.NexError)result={kind:'trap',output,code:error.code,message:error.message,line:error.site?.[1]??0,file:error.site?.[0]??''};else {const detail=errors.details(error);if(detail===undefined)throw error;result={kind:'trap',output,code:'E_SOURCE_EXCEPTION',message:detail.code+': '+detail.message,line:detail.site[1],file:detail.site[0]};}"
        (generated/'run.ts').write_text(source_errors+"""import {main} from './program.ts';import * as base from './nex-runtime.ts';
let output='';const previous=console.log;console.log=(value:unknown)=>{output+=String(value)+'\\n';};
let result;try {const value=main();result={kind:'return',output,value_json:value===undefined?'null':base.representation(value)};}
catch(error) {"""+normalize+"""}
finally {console.log=previous;}console.log(JSON.stringify(result));
""")
        run([node,tsc,'--noEmit','--strict','--target','ES2022','--module','nodenext','--allowImportingTsExtensions',generated/'run.ts'],folder,'typecheck')
        actual=json.loads(run([node,'--experimental-strip-types','--no-warnings',generated/'run.ts'],folder,'typescript').stdout)
        assert actual['kind']==reference['kind']and actual['output']==reference['output'],(case['name'],actual,reference)
        if reference['kind']=='return':assert json.loads(actual['value_json'])==reference['value'],(case['name'],actual,reference)
        else:assert all(actual.get(k)==reference.get(k)for k in ['code','message','line','file']),(case['name'],actual,reference)
        report['cases'].append({'name':case['name'],'revision':inspection['revision'],'source_sha256':sha(path),'typescript_sha256':sha(generated/'program.ts'),'outcome':reference['kind'],'passed':True})
        if not case.get('host_only'):
            for opt in ['0','2']:
                dest=folder/('native-O'+opt);dest.mkdir(exist_ok=True)
                run([native,'030-bundle-emit'if'bundle'in case else'030-emit',path,dest,triple,layout,'true'if opt=='2'else'false',1048576,4194304,16777216],folder,'emit-native-'+opt)
                library=dest/('program.dylib'if platform.system()=='Darwin'else'program.dll'if os.name=='nt'else'program.so')
                flags=['-dynamiclib','-undefined','dynamic_lookup']if platform.system()=='Darwin'else['-shared',*probe_dll_inputs(native,out)]if os.name=='nt'else['-shared','-fPIC']
                run([clang,'-O'+opt,*flags,dest/'program.ll','-o',library],dest,'compile')
                r=run([native,'run',library],dest,'run',allowed=(exit_code(reference['value']),)if reference['kind']=='return'else(70,))
                assert r.stdout==reference['output'],(case['name'],opt,r.stdout,reference)
                if reference['kind']=='return':assert not r.stderr
                else:record_error(r,reference)
                assert 'E_INTERNAL_LEAK'not in r.stderr and 'left live values'not in r.stderr
                report['native'].append({'name':case['name'],'optimization':opt,'artifact_sha256':sha(library),'passed':True})
        save()
    # Real normal build API, independent executable/runtime components and cache
    # records, rather than only the matching-host image harness above.
    path=out/'normal-build.nex';path.write_text('module normal;fn main()->unit!{io,state}{let value:cell<i64>=cell_new(41);cell_write(value,42);print(cell_read(value));}')
    report['normal_builds']=[]
    for profile in ['debug','release']:
        dest=out/('normal-'+profile);v=json.loads(run([probe,'build',path,dest,profile],out,'normal-build-'+profile).stdout)
        r=run([v['artifact']],out,'normal-run-'+profile);assert r.stdout=='42\n'and not r.stderr
        meta=json.loads((Path(v['artifact']).parent/'build.json').read_text())
        assert all(n in meta['runtime_components']for n in ['nex_cells.cpp','nex_cell_host.cpp'])
        plain=out/'normal-plain.nex';plain.write_text('module plain;fn main()->unit!{io}{print(42);}')
        no_refs=json.loads(run([probe,'build',plain,out/('normal-plain-'+profile),profile],out,'normal-plain-'+profile).stdout)
        assert no_refs['library_abi']==v['library_abi'],'source030 cohort must not vary with local reference effects'
        report['normal_builds'].append({'profile':profile,'artifact_sha256':sha(v['artifact']),'key':v['key'],'library_abi':v['library_abi'],'reference_free_cohort_match':True,'runtime_components':meta['runtime_components'],'passed':True})
    # Existing no-cell tasks retain their parser, generators and scheduler.
    task=out/'tasks.nex';task.write_text('module inherited;fn identity<F<_>,T>(value:F<T>)->F<T>{return value;}fn main()->i64!{task,throw}{return with_tasks(1,fn(s:task_scope)->i64!{task,throw}{let q:channel<i64>=channel_new<i64>(s,1);let alias:channel<i64>=identity<channel,i64>(q);assert(task_send(alias,42));assert(unwrap(task_recv(q))==42);let value:task<i64>=task_spawn(s,fn()->i64{return 42;});return task_wait(value);});}')
    task_ref=json.loads(run([probe,'reference',task],out,'tasks-reference').stdout);assert task_ref['value']==42 and task_ref['live_delta']==0,task_ref
    task_dest=out/'tasks-ts';run([probe,'typescript',task,task_dest],out,'tasks-emit')
    (task_dest/'package.json').write_text('{"type":"module"}\n')
    assert json.loads((task_dest/'nex-map.json').read_text())['execution']=='task-generator'
    (task_dest/'run.ts').write_text("import {main,sourceErrorContracts}from './program.ts';import * as task from './nex-task-runtime.ts';const result=await task.runTypedSourceErrors(task.call(()=>main()),sourceErrorContracts);if(result!==42n)throw Error('task result');console.log('42');")
    run([node,tsc,'--noEmit','--strict','--target','ES2022','--module','nodenext','--allowImportingTsExtensions',task_dest/'run.ts'],out,'tasks-typecheck')
    assert run([node,'--experimental-strip-types','--no-warnings',task_dest/'run.ts'],out,'tasks-typescript').stdout=='42\n'
    task_build=json.loads(run([probe,'build',task,out/'tasks-native','release'],out,'tasks-native-build').stdout)
    run([task_build['artifact']],out,'tasks-native-run',allowed=(42,))
    report['inherited_tasks']={'reference':42,'typescript':42,'native_status':42,'passed':True}
    device=out/'scalar-devices.nex';device.write_text('module inherited;fn main(value:i64)->i64{return value+1;}')
    report['scalar_device_emission']=json.loads(run([probe,'scalar-devices',device,out/'scalar-devices'],out,'scalar-devices').stdout)
    assert report['scalar_device_emission']['ok']and all((out/'scalar-devices'/n).stat().st_size for n in ['program.metal','program.cu','program.cl','program-wasm.mlir'])
    for name,body,mode,code in [
        ('parallel-context','fn main()->unit!{state,task,throw}{let value:cell<i64>=cell_new(1);let items:list<i64>=parallel_map([1],fn(x:i64)->i64{return x;},1);task_yield();}','reference','E_CELL_CONCURRENCY'),
        ('cell-wasm','fn main()->i64!{state}{return cell_read(cell_new(42));}','wasm','E_CELL_TARGET'),
        ('missing-effect','fn main()->unit{let value:cell<i64>=cell_new(1);}','inspect','E_EFFECT')]:
        path=out/(name+'.nex');path.write_text('module rejected;'+body)
        r=run([probe,mode,path,out/(name+'.mlir')],out,name,allowed=(0,1))
        assert code in r.stderr or json.loads(r.stdout).get('code')==code,(name,r.stdout,r.stderr)
        report['gates'].append({'name':name,'code':code,'passed':True})

# Isolated actual retained029 graph store. Changing metadata alone cannot
# select030 or downgrade its new HEAD back into029.
origin=(a.origin_compiler or compiler).resolve()
migration_root=Path(tempfile.mkdtemp(prefix='migration-run-',dir=out))
report['migration_root']=str(migration_root)
def snapshot(project):
    with sqlite3.connect('file:'+str(project/'.nex/graph.db')+'?mode=ro',uri=True)as c:
        schema=tuple(c.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
        rows={name:collections.Counter(tuple(row)for row in c.execute('SELECT * FROM "'+name+'"'))for name, in c.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return schema,rows
def project(name,source):
    path=migration_root/name;path.mkdir();(path/'main.nex').write_text(source)
    (path/'nex.json').write_text('{"schema":"nex.project/1","language":"0.29","entry":"main.nex"}')
    result=json.loads(run([origin,'check','--json'],path,'origin-check',cwd=path).stdout)
    return path,result['revision']
def migrate(name,path,head,mode='plan',allowed=(0,),**extra):
    request={'schema':'nex.typed-error-migration-request/1','mode':mode,'target_language':'0.30','project':str(path),'expected_revision':head,**extra}
    f=out/(name+'.json');f.write_text(json.dumps(request))
    r=run([migration,f],out,name,allowed=allowed);v=json.loads(r.stdout);report['migration'].append({'name':name,'result':v,'exit_code':r.returncode});save();return v
plain='module origin;fn main()->i64{return 42;}'
path,head=project('migration-plain',plain);before=snapshot(path);plan=migrate('plan',path,head)
assert plan['origin_verified']and plan['language']=='0.30'and snapshot(path)==before
bad=migrate('unguarded',path,head,'unguarded',allowed=(1,));assert bad['code']=='E_LANGUAGE_VERSION'and snapshot(path)==before
applied=migrate('apply',path,head,'apply');after=snapshot(path);assert applied['language']=='0.30'and after[0]==before[0]
for table,rows in before[1].items():
    if table!='head':assert not rows-after[1][table],table
assert json.loads((path/'nex.json').read_text())['language']=='0.29'and(path/'main.nex').read_text()==plain
rejected=run([compiler,'check','--json'],path,'reject-implicit-downgrade',allowed=(1,),cwd=path)
assert json.loads(rejected.stdout)['code']=='E_LANGUAGE_VERSION'and snapshot(path)==after
v=migrate('idempotent',path,applied['revision'],'apply');assert not v['changed']and snapshot(path)==after
race,old_head=project('migration-race',plain)
v=migrate('race',race,old_head,'race',allowed=(1,),race_sources={'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':plain.replace('42','43')}})
assert v['code']=='E_CONFLICT'
# A genuine old source name becomes a builtin only in030. Rejection must leave
# every old row and identity intact; a reviewed rename supplies the new source.
collision='module collision;fn cell_new(value:i64)->i64{return value;}fn main()->i64{return cell_new(42);}'
path,head=project('migration-collision',collision);before=snapshot(path)
v=migrate('collision-plan',path,head,allowed=(1,));assert v['code']=='E_DUPLICATE'and snapshot(path)==before,v
old=migrate('collision-origin',path,head,'origin-info');origin_hash=old['source_hash']
assert old['revision']==head and old['language']=='0.29'and snapshot(path)==before
replacement=collision.replace('cell_new','legacy_cell_new')
candidate={'schema':'nex.migration-candidate/1','origin_revision':head,'origin_language':'0.29','origin_source_hash':origin_hash,'target_language':'0.30',
           'sources':{'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':replacement}}}
reviewed=migrate('collision-reviewed',path,head,'apply',candidate=candidate,export=str(migration_root/'exported030'))
assert reviewed['export_roundtrip']and json.loads((migration_root/'exported030/nex.json').read_text())['language']=='0.30'
after=snapshot(path)
for table,rows in before[1].items():
    if table!='head':assert not rows-after[1][table],table
report['origin_compiler']={'path':str(origin),'sha256':sha(origin),'retained_sdk':a.origin_compiler is not None}
doctor=json.loads(run([origin,'doctor','--json'],out,'origin-doctor').stdout)
report['origin_compiler']['toolchain']=doctor['version']
assert sha(probe)==report['probe_sha256']and sha(compiler)==report['compiler_sha256']and sha(native)==report['native_host_sha256'],'compiler cohort changed during acceptance'
report.update(ok=True,comparisons=len(report['cases']),native_comparisons=len(report['native']))
save();print(json.dumps({'ok':True,'comparisons':len(report['cases']),'native_comparisons':len(report['native']),'migration_cases':len(report['migration']),'report':str(out/'report.json')}))
