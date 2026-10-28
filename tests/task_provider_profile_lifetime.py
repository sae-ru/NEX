#!/usr/bin/env python3
"""Actual startup-linked generated DSO/private physical fence; no production hook."""
import hashlib,json,os,platform,shutil,subprocess,sys,tempfile,time
from pathlib import Path

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    compiler=Path(sys.argv[1]).resolve(); driver=Path(sys.argv[2]).resolve()
    retained=os.environ.get('NEX_TASK_PROVIDER_PROFILE_LIFETIME_OUTPUT')
    temporary=None
    if retained:
        root=Path(retained).resolve(); root.mkdir(parents=True,exist_ok=False)
    else:
        temporary=tempfile.TemporaryDirectory(prefix='nex-shared-lifetime-'); root=Path(temporary.name)
    captured_driver=root/'driver.cpp';shutil.copyfile(driver,captured_driver)
    sanitizers=os.environ.get('NEX_TASK_PROVIDER_PROFILE_SANITIZERS','')
    if sanitizers not in ('','address,undefined','thread'):raise ValueError('unsupported private sanitizer selection')
    report={'schema':'nex.task-provider-profile-private-lifetime/1','state':'running','scope':'actual source-built startup-linked DSOs/common runtime; private observer physical fence, distinct from public source regular-file IO','compiler':str(compiler),'compiler_sha256':sha(compiler),'driver_source':str(driver),'driver_source_sha256':sha(driver),'harness_source_sha256':sha(__file__),'driver_snapshot':str(captured_driver),'commands':[]}
    env=dict(os.environ);env.pop('NEX_RESOURCE_DIR',None)
    if sanitizers=='address,undefined':env.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',LSAN_OPTIONS='exitcode=86')
    if sanitizers=='thread':env['TSAN_OPTIONS']='halt_on_error=1:exitcode=87'
    def command(argv,cwd=root,timeout=180):
        start=time.monotonic();run=subprocess.run([str(a) for a in argv],cwd=cwd,env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
        row={'argv':[str(a) for a in argv],'cwd':str(cwd),'exit_code':run.returncode,'seconds':time.monotonic()-start,'stdout':run.stdout,'stderr':run.stderr};report['commands'].append(row)
        (root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        if run.returncode:raise RuntimeError('command failed: '+str(argv)+'\n'+run.stderr+'\n'+run.stdout)
        return run.stdout
    try:
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':json.loads(command([compiler,'describe','--kind','index','--json']))['language']})+'\n')
        for name in ('leaf','mid','app'):(root/name).mkdir()
        (root/'leaf/value.nex').write_text('module shared_leaf;pub fn work()->i64!{task}{let held:list<str>=["owned🧠"];task_yield();return 40+len(held);}\n')
        (root/'mid/value.nex').write_text('module shared_middle;import "../leaf/value.nex" as leaf;pub fn work()->i64!{task,throw}{task_yield();return with_tasks(1,fn(scope:task_scope)->i64!{task,throw}{let child:task<i64>=task_spawn(scope,fn()->i64!{task}{return leaf::work()+1;});return task_wait(child);});}\n')
        (root/'app/main.nex').write_text('module lifetime_app;import "../mid/value.nex" as mid;fn main()->unit!{task,io,throw}{print(mid::work());}\n')
        manifest={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'profile','task_limits':{'steps':1000000,'timeout_ms':5000,'workers':1}}},'components':{'leaf':{'kind':'shared_library','root':'leaf','entry':'leaf/value.nex','entry_function':'work'},'mid':{'kind':'shared_library','root':'mid','entry':'mid/value.nex','entry_function':'work','dependencies':{'leaf':'dynamic'}},'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'mid':'dynamic'}}}}
        (root/'nex.build.json').write_text(json.dumps(manifest,indent=2)+'\n')
        built=json.loads(command([compiler,'project','--kind','build','--component','app','--json']))
        artifacts={r['component']:r for r in built['artifacts']}; app=Path(artifacts['app']['artifact']);mid=Path(artifacts['mid']['artifact']);leaf=Path(artifacts['leaf']['artifact'])
        if command([app],cwd=Path('/'))!='42\n':raise RuntimeError('actual source application result differs')
        meta=json.loads((app.parent/'build.json').read_text());links=json.loads((app.parent/'image-inputs.json').read_text()); runtimes=[r for r in links['images'] if r['kind']=='runtime']
        if len(runtimes)!=1:raise RuntimeError('actual image inventory requires one runtime')
        original_runtime=Path(runtimes[0]['path']);runtime=original_runtime;projection=Path(meta['runtime_source_projection']);cxx=meta['compiler'];binary=root/'lifetime-driver'
        if sha(runtime)!=runtimes[0]['sha256']:raise RuntimeError('completed production runtime changed')
        runtime_hashes={name:sha(projection/name) for name in meta['runtime_inputs']}
        report['captured_runtime_sha256']=runtime_hashes
        flags=['-std=c++20','-O1','-g','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_PROFILE_ENABLED','-DNEX_TASK_PROFILE_ENABLED','-DNEX_SHARED_PROFILE_RUNTIME']
        flags+=['-D'+x for x in ('TRACY_ENABLE','TRACY_ON_DEMAND','TRACY_DELAYED_INIT','TRACY_MANUAL_LIFETIME','TRACY_ONLY_LOCALHOST','TRACY_NO_BROADCAST','TRACY_NO_CODE_TRANSFER','TRACY_NO_CALLSTACK','TRACY_NO_SYSTEM_TRACING','TRACY_NO_SAMPLING','TRACY_NO_CRASH_HANDLER','TRACY_NO_FRAME_IMAGE')]
        report['instrumentation']={'requested':sanitizers or 'none','common_runtime_instrumented':False,'driver_instrumented':False,'generated_provider_ir_instrumented':False,'production_runtime':{'path':str(original_runtime),'sha256':sha(original_runtime)},'production_records_retagged':False}
        if sanitizers:
            cxx=os.environ.get('NEX_TASK_PROVIDER_PROFILE_SANITIZER_CXX',cxx)
            flags+=['-fsanitize='+sanitizers,'-fno-sanitize-recover=all','-fno-omit-frame-pointer']
            san=root/'instrumented';projection_copy=san/'runtime-inputs';shutil.copytree(projection,projection_copy);projection=projection_copy
            if runtime_hashes!={name:sha(projection/name) for name in meta['runtime_inputs']}:raise RuntimeError('private runtime copy differs')
            runtime=san/original_runtime.name;objects=[]
            for i,name in enumerate(meta['runtime_components']):
                obj=san/('runtime-'+str(i)+'.o');command([cxx,*flags,'-fPIC','-I',projection,'-c',projection/name,'-o',obj]);objects.append(obj)
            shared=['-dynamiclib','-Xlinker','-install_name','-Xlinker','@rpath/'+runtime.name] if platform.system()=='Darwin' else ['-shared','-Xlinker','-soname','-Xlinker',runtime.name,'-Xlinker','--build-id=sha1','-ldl']
            command([cxx,*flags,*shared,*objects,'-o',runtime])
            report['instrumentation'].update(common_runtime_instrumented=True,driver_instrumented=True,compiler=str(cxx),flags=flags,derived_runtime={'path':str(runtime),'sha256':sha(runtime)},sources_verified_equal=True)
        args=[cxx,*flags,'-I',projection,captured_driver,runtime,mid,leaf]
        # The directly linked same-SONAME runtime is first and its rpath first.
        # Provider startup dependencies then reuse that already mapped identity.
        directories=[str(runtime.parent),str(mid.parent),str(leaf.parent)]
        for directory in dict.fromkeys(directories):args+=['-Xlinker','-rpath','-Xlinker',directory]
        if platform.system()=='Linux':args+=['-ldl']
        args+=['-Xlinker','-export_dynamic' if platform.system()=='Darwin' else '--export-dynamic','-o',binary];command(args)
        env['NEX_PROFILE_OUTPUT']=str(root/'private-profile.json');env['NEX_PROFILE_EVENTS']='0';env['NEX_TRACY']='0'
        result=json.loads(command([binary,mid.name,leaf.name,runtime],cwd=Path('/')))
        profile=json.loads((root/'private-profile.json').read_text())
        if profile.get('schema')!='nex.profile-runtime/3' or not profile['completeness']['aggregates'] or not profile['completeness']['memory']:raise RuntimeError('private DSO profile not complete for calls/memory')
        if profile['completeness']['timeline'] or not profile['dropped_events']:raise RuntimeError('events0 bounded timeline loss not reported')
        if profile['task_execution']['executor_workers']!=1:raise RuntimeError('private host executor metadata differs')
        functions={f['name']:f for f in profile['functions']}
        for name,completed,aborted in [('shared_middle::work',1,3),('shared_leaf::work',4,0)]:
            f=functions[name]
            if (f['calls'],f['completed'],f['aborted'])!=(4,completed,aborted):raise RuntimeError('source invocation count/fatal boundary mismatch')
        if any(p['live'] for p in profile['memory']):raise RuntimeError('profiled managed memory not retired')
        report['private_profile']={'path':str(root/'private-profile.json'),'sha256':sha(root/'private-profile.json'),'functions':functions,'strict_public_reader_claim':False,'identity_scope':'private controlled host; generated provider catalogs and original image pins independently checked'}
        if not result.get('ok') or result.get('execution_abi')!=6 or result.get('cases')!=4 or result.get('runtime_mappings')!=1 or result.get('live_objects')!=0:raise RuntimeError('private mapped driver invariants failed')
        if Path(result['runtime_image_path']).resolve()!=runtime.resolve():raise RuntimeError('driver mapped the wrong runtime instrumentation image')
        if runtime_hashes!={name:sha(projection/name) for name in meta['runtime_inputs']} or sha(captured_driver)!=report['driver_source_sha256']:raise RuntimeError('probe inputs changed')
        report.update(state='passed',result=result,artifacts={k:{'path':v['artifact'],'sha256':sha(v['artifact']),'metadata_sha256':sha(Path(v['artifact']).parent/'build.json'),'provider_record_sha256':sha(Path(v['artifact']).parent/'task-provider.json')} for k,v in artifacts.items()},runtime={'path':str(runtime),'sha256':sha(runtime)},runtime_inputs=meta['runtime_inputs'],driver_sha256=sha(binary),compiler_unchanged=sha(compiler)==report['compiler_sha256'])
        assert report['compiler_unchanged'];(root/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps({'ok':True,'cases':4,'runtime_mappings':1,'physical_barrier_cases':4,'sanitizers':sanitizers or 'none','report':str(root/'report.json')}))
    except BaseException as error:
        report.update(state='failed',failure=repr(error));(root/'report.json').write_text(json.dumps(report,indent=2)+'\n');raise
    finally:
        if temporary:temporary.cleanup()

if __name__=='__main__':main()
