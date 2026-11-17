"""Compare owned-thread native continuations to the independent AST task corpus."""
from concurrent.futures import ThreadPoolExecutor
from host_fixture import run_native, deployed_environment
from pathlib import Path
import argparse,hashlib,json,os,platform,re,subprocess,tempfile

parser=argparse.ArgumentParser();parser.add_argument('emitter',type=Path);parser.add_argument('reference',type=Path)
parser.add_argument('--clang',required=True,type=Path);parser.add_argument('--output',type=Path)
parser.add_argument('--output-parent',type=Path);args=parser.parse_args()
root=Path(__file__).resolve().parents[1];runtime=root/'runtime'
out=args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-native-reference-tasks-',dir=args.output_parent))
if args.output:out.mkdir(parents=True,exist_ok=False)
emitter=args.emitter.resolve();reference=args.reference.resolve();compiler=args.clang.absolute()
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(name,command,expected=0,**kw):
    p=run_native(list(map(str,command)),text=True,capture_output=True,timeout=180,**kw)
    (out/(name+'.stdout')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr)
    if p.returncode!=expected:raise RuntimeError(str(command)+'\n'+p.stdout+'\n'+p.stderr)
    return p
corpus=out/'corpus';observed=json.loads(run('reference',[reference,corpus]).stdout)
assert observed=={'ok':True,'cases':21,'owner_cases':11,'native_session_cases':14},observed
cases=json.loads((corpus/'cases.json').read_text())['cases'];assert len(cases)==13,len(cases)
run('target',[compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',out/'target.ll'])
text=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',text)[1];layout=re.search(r'target datalayout = "([^"]+)"',text)[1]
flags=['-std=c++20','-pthread','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_MANAGED_TASKS','-I'+str(runtime)]
names=['runtime.cpp','nex_cells.cpp','nex_cell_host.cpp','nex_files.cpp','files_runtime.cpp','nex_task_external.cpp','nex_task_frame.cpp','nex_task_application.cpp','nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp']
report={'schema':'nex.native-reference-task-agreement/1','ok':False,'source_language':'0.30','public_source_enabled':False,'task_ABI':'0x4e45585400003001','source_workers':1,'platform':platform.platform(),'compiler_sha256':sha(compiler),'emitter_sha256':sha(emitter),'reference_probe_sha256':sha(reference),'reference_cases':21,'runtime_sources_sha256':{n:sha(runtime/n) for n in names},'runtime_headers_sha256':{p.relative_to(runtime).as_posix():sha(p) for p in sorted(runtime.rglob('*.h'))},'harness_sha256':sha(Path(__file__)),'owner_probe_source_sha256':sha(root/'tests/owner_task_runtime.cpp'),'cases':[],'owner_runtime':[]}
for optimization in ['0','2']:
    build=out/('runtime-O'+optimization);build.mkdir()
    def compile_one(name):
        obj=build/(name+'.o');run('O'+optimization+'-compile-'+name,[compiler,*flags,'-O'+optimization,'-c',runtime/name,'-o',obj]);return obj
    with ThreadPoolExecutor(max_workers=4) as pool:objects=list(pool.map(compile_one,names))
    libraries=['-lntdll','-lbcrypt','-ladvapi32'] if os.name=='nt' else []
    owner=build/('owner.exe' if os.name=='nt' else 'owner')
    run('O'+optimization+'-link-owner',[compiler,*flags,'-O'+optimization,root/'tests/owner_task_runtime.cpp',*objects,*libraries,'-o',owner])
    owner_result=json.loads(run('O'+optimization+'-owner',[owner],cwd=tempfile.gettempdir(),env=deployed_environment()).stdout)
    assert owner_result['ok'] and owner_result['cases']==11,owner_result
    report['owner_runtime'].append({'optimization':'O'+optimization,'result':owner_result,'binary_sha256':sha(owner)})
    for case in cases:
        name=Path(case['file']).stem;directory=out/(name+'-O'+optimization)
        emission=json.loads(run(name+'-O'+optimization+'-emit',[emitter,corpus/case['file'],directory,triple,layout,str(optimization=='2').lower()]).stdout)
        assert emission['revision']==case['revision'] and emission['descriptor_abi']==0x4e45585400003001,emission
        binary=directory/('app.exe' if os.name=='nt' else 'app')
        run(name+'-O'+optimization+'-link',[compiler,'-O'+optimization,'-pthread',directory/'program.ll',*objects,*libraries,'-o',binary])
        env=deployed_environment(NEX_FILES_ROOT=str(corpus),NEX_FILES_WRITE='1')
        error=case.get('error');arguments=['--nex-task-steps',str(case['steps'])] if error=='E_LIMIT' else []
        actual=run(name+'-O'+optimization+'-run',[binary,*arguments],expected=70 if error else 0,cwd=tempfile.gettempdir(),env=env)
        assert actual.stdout==case['stdout'],(case,actual.stdout,actual.stderr)
        if error:
            prefix='NEX_SOURCE_EXCEPTION ' if error=='E_SOURCE_EXCEPTION' else 'NEX_NATIVE_TRAP '
            records=[json.loads(line[len(prefix):]) for line in actual.stderr.splitlines() if line.startswith(prefix)]
            assert len(records)==1,(case,actual.stderr)
            if error=='E_SOURCE_EXCEPTION':assert records[0]['code']+': '+records[0]['message']==case['message'],(records,case)
            else:assert records[0]['code']==error,(records,case)
        else:assert not actual.stderr,(case,actual.stderr)
        assert 'E_INTERNAL_LEAK' not in actual.stderr and not (corpus/'wrong').exists(),(case,actual.stderr)
        report['cases'].append({'file':case['file'],'optimization':'O'+optimization,'revision':case['revision'],'source_sha256':sha(corpus/case['file']),'llvm_sha256':sha(directory/'program.ll'),'binary_sha256':sha(binary),'genuine_file_operations':case['files'],'error':error,'passed':True})
        (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
assert sha(emitter)==report['emitter_sha256'] and sha(reference)==report['reference_probe_sha256']
assert all(sha(runtime/n)==digest for n,digest in report['runtime_sources_sha256'].items())
assert all(sha(runtime/n)==digest for n,digest in report['runtime_headers_sha256'].items())
report['ok']=True;report['comparisons']=len(report['cases']);(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'ok':True,'comparisons':report['comparisons'],'report':str(out/'report.json')}))
