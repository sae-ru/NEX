"""Private references with real files and an independent C resource producer."""
from host_fixture import run_native,exit_code,probe_dll_inputs
from managed_reference_resource_cases import CASES
from source_exception_host import DECLARATIONS,MODULE
from pathlib import Path
import argparse,hashlib,json,os,platform,re,tempfile

p=argparse.ArgumentParser();p.add_argument('probe',type=Path);p.add_argument('compiler',type=Path)
p.add_argument('--output',type=Path);p.add_argument('--crypto-library');p.add_argument('--crypto-include');p.add_argument('--case',action='append');a=p.parse_args()
if a.case:
    unknown=set(a.case)-{row[0]for row in CASES}
    if unknown:p.error('unknown source cases: '+', '.join(sorted(unknown)))
    CASES=[row for row in CASES if row[0]in a.case]
source=Path(__file__).resolve().parents[1];runtime=source/'runtime';probe=a.probe.resolve();compiler=a.compiler.absolute()
out=(a.output or Path(tempfile.mkdtemp(prefix='nex-cell-resources-'))).resolve();out.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
inputs=sorted(path for path in runtime.rglob('*')if path.is_file()and path.suffix in ['.h','.hpp','.c','.cpp','.manifest'])
identity=''.join(path.relative_to(source).as_posix()+':'+sha(path)+'\n'for path in inputs)
report={'schema':'nex.managed-reference-resource-agreement/1','ok':False,'public_source_enabled':False,'private_language':'0.30-refs-prototype','probe_sha256':sha(probe),'compiler_sha256':sha(compiler),'runtime_source_tree_sha256':hashlib.sha256(identity.encode()).hexdigest(),'selected_cases':[row[0]for row in CASES],'cases':[],'commands':[]}
def save():(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
def run(label,command,allowed=(0,),env=None):
    result=run_native(list(map(str,command)),capture_output=True,text=True,timeout=180,env=env)
    (out/(label+'.stdout')).write_text(result.stdout);(out/(label+'.stderr')).write_text(result.stderr)
    report['commands'].append({'label':label,'argv':list(map(str,command)),'exit_code':result.returncode});save()
    assert result.returncode in allowed,(label,result.returncode,result.stdout[-2500:],result.stderr[-4000:])
    return result
save()
target=out/'target.ll';run('target',[compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',target]);text=target.read_text()
triple=re.search(r'target triple = "(.*?)"',text)[1];layout=re.search(r'target datalayout = "(.*?)"',text)[1]
signature_source=out/'signature.nex';signature_source.write_text('module managed_resources;'+DECLARATIONS.replace('@PIN@','0'*64)+'fn main()->unit{}')
signatures=json.loads(run('signatures',[probe,'resources-signatures',signature_source]).stdout)
bundle=out/'bundle';bundle.mkdir(exist_ok=True);rows=[]
for name,op in [('create',1),('read',2),('add',3),('ordinary',4),('bad',5)]:
    digest=hashlib.sha256(json.dumps(signatures[name],sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
    rows.append('{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(digest)+',callback,(void*)'+str(op)+'}')
producer=out/'producer.c';producer.write_text(MODULE.replace('EXPORTS',','.join(rows)))
run('producer',[compiler,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden','-I',runtime,producer,'-o',bundle/'module'])
(bundle/'NOTICE').write_text('Independent C producer for private NEX reference/resource conformance\n')
machine={'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64','amd64':'x86_64'}[platform.machine().lower()]
manifest={'schema':'nex.foreign-bundle/1','platform':('windows'if os.name=='nt'else'macos'if platform.system()=='Darwin'else'linux')+'-'+machine,'entry':'module','files':[{'path':name,'sha256':sha(bundle/name)}for name in ['module','NOTICE']],'exports':{name:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()for name,value in signatures.items()},'notices':['NOTICE']}
(bundle/'manifest.json').write_text(json.dumps(manifest)+'\n');pin=sha(bundle/'manifest.json');catalogue=out/'host.json'
catalogue.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':64,'resource_limit':64,'resource_bytes':512,'libraries':{'host':{'directory':'bundle','manifest_sha256':pin,'exports':list(signatures)}}})+'\n')
for name,body,foreign,error in CASES:
    directory=out/name;directory.mkdir(exist_ok=True);file=directory/'main.nex'
    file.write_text('module managed_resources;\n'+(DECLARATIONS.replace('@PIN@',pin)if foreign else'')+body+'\n')
    run(name+'-check',[probe,'resources-signatures',file])
crypto=[a.crypto_library]if a.crypto_library else['-lcrypto']
objects={}
units=['runtime.cpp','nex_cells.cpp','nex_cell_host.cpp','nex_files.cpp','files_runtime.cpp','foreign_runtime.cpp','nex_foreign.cpp','nex_ffi_loader.cpp','nex_ffi.cpp','nex_ffi_types.cpp','nex_ffi_resources.cpp','nex_external_resource.cpp','nex_resource_region.cpp','nex_resource_executor.cpp','nex_json.cpp','wire_runtime.cpp']
for opt in ['0','2']:
    directory=out/('runtime-O'+opt);directory.mkdir(exist_ok=True);objects[opt]=[]
    for unit in units:
        obj=directory/(unit+'.o');flags=['-std=c++20','-O'+opt,'-fPIC','-pthread','-I',runtime]
        if a.crypto_include:flags+=['-I',a.crypto_include]
        run('compile-O'+opt+'-'+unit,[compiler,*flags,'-c',runtime/unit,'-o',obj]);objects[opt].append(obj)
for name,body,foreign,error in CASES:
    directory=out/name;directory.mkdir(exist_ok=True);file=directory/'main.nex'
    file.write_text('module managed_resources;\n'+(DECLARATIONS.replace('@PIN@',pin)if foreign else'')+body+'\n')
    def environment(path):
        path.mkdir(exist_ok=True);(path/'input').write_text('abcdef')
        return {**os.environ,'NEX_FILES_ROOT':'/absent-explicit-host-must-win','NEX_FILES_WRITE':'0','NEX_PRIVATE_HOST_EVENTS':str(path/'events')}
    refroot=directory/'reference';env=environment(refroot)
    reference=json.loads(run(name+'-reference',[probe,'resources-reference',file,refroot,catalogue if foreign else'-'],env=env).stdout)
    assert reference['live_delta']==reference['file_delta']==reference['external_bytes']==0,(name,reference)
    if error:assert reference['kind']=='trap'and reference['code']==error,(name,reference)
    else:assert reference['kind']=='return'and reference['value']==42 and reference['remaining_nodes']==reference['remaining_cells']==0,(name,reference)
    for opt in ['0','2']:
        for request in [False,True]:
            build=directory/('request-'if request else'application-')/('O'+opt);build.mkdir(parents=True,exist_ok=True)
            run(name+'-emit-'+str(request)+'-O'+opt,[probe,'request-emit'if request else'emit',file,build,triple,layout,str(opt=='2').lower(),1048576,4194304,16777216])
            image=build/('program.dylib'if platform.system()=='Darwin'else'program.dll'if os.name=='nt'else'program.so')
            flags=['-dynamiclib','-undefined','dynamic_lookup']if platform.system()=='Darwin'else['-shared',*probe_dll_inputs(str(probe),out)]if os.name=='nt'else['-shared','-fPIC']
            run(name+'-image-'+str(request)+'-O'+opt,[compiler,'-O'+opt,*flags,build/'program.ll','-o',image])
            consumer=build/'consumer.ll';consumer.write_text((build/'program.ll').read_text().replace('@main(', '@nex_private_reference_application(')if not request else(build/'program.ll').read_text())
            host=build/'host.cpp';symbol='nex_private_reference_request'if request else'nex_private_reference_application'
            declaration='int64_t '+symbol+'(nexrt::Handle **)'if request else'int '+symbol+'(int,const char *const*)'
            host.write_text('#include "managed_reference_resource_host.h"\nextern "C" '+declaration+';\nint main(int argc,char **argv){if(argc!=4)return 1;return runManagedReferenceResources(reinterpret_cast<void*>('+symbol+'),'+str(request).lower()+',argv[1],argv[2],argv[3]);}\n')
            executable=build/('standalone.exe'if os.name=='nt'else'standalone');libraries=['-lntdll','-lbcrypt','-ladvapi32']if os.name=='nt'else[]
            run(name+'-link-'+str(request)+'-O'+opt,[compiler,'-std=c++20','-O'+opt,'-pthread','-I',source/'tests','-I',runtime,consumer,host,*objects[opt],*crypto,*libraries,'-o',executable])
            observations=[]
            for kind in ['host','standalone']:
                files=build/(kind+'-files');env=environment(files);requests=files/'requests.json'
                command=[probe,'resources-request-run'if request else'resources-run',image]if kind=='host'else[executable]
                command+=[files,catalogue if foreign else'-',requests]
                result=run(name+'-'+str(request)+'-O'+opt+'-'+kind,command,allowed=(70,)if error else(exit_code(42),),env=env)
                assert result.stdout==reference['output']*(4 if request and not error else 2 if request else 1),(name,result.stdout,reference)
                clean=[json.loads(line.split(' ',1)[1])for line in result.stderr.splitlines()if line.startswith('NEX_REFERENCE_RESOURCES ')]
                assert clean==[{'live_delta':0,'file_delta':0,'external_bytes':0}],(name,result.stderr)
                if error:
                    prefix='NEX_SOURCE_EXCEPTION 'if error=='E_SOURCE_EXCEPTION'else'NEX_NATIVE_TRAP '
                    records=[json.loads(line.split(' ',1)[1])for line in result.stderr.splitlines()if line.startswith(prefix)]
                    assert len(records)==(2 if request else 1),(name,reference,result.stderr)
                    if error=='E_SOURCE_EXCEPTION':assert all(r['code']+': '+r['message']==reference['message']and r['line']==reference['line']for r in records),(name,reference,result.stderr)
                    else:assert all(r['code']==error and r['reported_line']==reference['line']for r in records),(name,reference,result.stderr)
                assert not(files/'wrong').exists(),(name,'fatal executed user finalizer')
                events=(files/'events').read_text()if(files/'events').exists()else''
                assert events.count('F')==events.count('X'),(name,events)
                observation={'hosting':kind,'live_delta':0,'file_delta':0,'external_bytes':0,'created':events.count('F'),'destroyed':events.count('X')}
                if request:
                    rows=json.loads(requests.read_text());assert len(rows)==2 and all(r['live_delta']==0 and r['failed']==bool(error)for r in rows),(name,rows)
                    if not error:assert all(r['calls']==2 and r['result']==42 for r in rows),(name,rows)
                    observation['requests']=rows
                observations.append(observation)
            report['cases'].append({'name':name,'optimization':'O'+opt,'context':'request'if request else'application','expected_error':error,'reference':reference,'source_sha256':sha(file),'mlir_sha256':sha(build/'program.mlir'),'llvm_sha256':sha(build/'program.ll'),'image_sha256':sha(image),'executable_sha256':sha(executable),'observations':observations,'passed':True});save()
assert sha(probe)==report['probe_sha256']and sha(compiler)==report['compiler_sha256'],'tools changed during qualification'
report.update(ok=True,source_programs=len(CASES),native_comparisons=len(report['cases']),machine_runs=2*len(report['cases']),source_sha256={p.name:sha(p)for p in [Path(__file__),source/'tests/managed_reference_resource_cases.py',source/'tests/managed_reference_resources.cpp',source/'tests/managed_reference_resource_host.h',source/'tests/source_exception_host.py',source/'tests/host_file_observers.h']},runtime_objects={opt:{p.name:sha(p)for p in units}for opt,units in objects.items()})
save();print(json.dumps({'ok':True,'source_programs':len(CASES),'native_comparisons':len(report['cases']),'report':str(out/'report.json')}))
