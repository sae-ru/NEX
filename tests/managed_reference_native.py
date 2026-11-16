"""Private reference/native cell semantics and context cleanup, Debug/Release."""
from host_fixture import run_native,exit_code,probe_dll_inputs
from managed_reference_cases import source_cases
from pathlib import Path
import argparse,hashlib,json,os,platform,re,subprocess,tempfile

parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('compiler',type=Path)
parser.add_argument('--output',type=Path);parser.add_argument('--modules',action='store_true');parser.add_argument('--requests',action='store_true');args=parser.parse_args();probe=args.probe.resolve();compiler=args.compiler.absolute()
root=Path(__file__).resolve().parents[1]
folder=(args.output or Path(tempfile.mkdtemp(prefix='nex-managed-native-'))).resolve();folder.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command,**kwargs):
    result=run_native(list(map(str,command)),text=True,capture_output=True,timeout=120,**kwargs)
    if result.returncode:raise RuntimeError(str(command)+'\n'+result.stdout+'\n'+result.stderr)
    return result
def error_agrees(stderr,reference):
    if args.requests:
        prefix='NEX_SOURCE_EXCEPTION ' if reference['code']=='E_SOURCE_EXCEPTION' else 'NEX_NATIVE_TRAP '
        records=[line for line in stderr.splitlines() if line.startswith(prefix)]
        assert len(records)==2,(records,reference)
        for line in records:error_record_agrees(json.loads(line.split(' ',1)[1]),reference)
        return
    if reference['code']=='E_SOURCE_EXCEPTION':
        record=next(json.loads(line.split(' ',1)[1])for line in stderr.splitlines()if line.startswith('NEX_SOURCE_EXCEPTION '))
    else:
        record=next(json.loads(line.split(' ',1)[1])for line in stderr.splitlines()if line.startswith('NEX_NATIVE_TRAP '))
    error_record_agrees(record,reference)
def error_record_agrees(record,reference):
    if reference['code']=='E_SOURCE_EXCEPTION':assert record['code']+': '+record['message']==reference['message']and record['line']==reference['line'],(record,reference)
    else:assert record['code']==reference['code']and record['reported_line']==reference['line'],(record,reference)
    if args.modules:
        assert all(record.get('source',{}).get(key)==value for key,value in reference['origin'].items()),(record,reference)
layout=folder/'host.ll';run([compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',layout])
host=layout.read_text();triple=re.search(r'target triple = "(.*?)"',host)[1];layout_text=re.search(r'target datalayout = "(.*?)"',host)[1]
# The same source/expected observations feed the TypeScript acceptance path.
if args.modules:
    from managed_reference_module_cases import module_cases
    cases=module_cases()
else:cases=source_cases(root)
if args.requests:
    scalar='module request_scalar;fn main()->i64!{state}{let value:cell<i64>=cell_new(9223372036854775807);return cell_read(value);}'
    cases.append({'name':'request-full-i64','source':scalar.split(';',1)[1],'output':'','bundle':{'schema':'nex.private-reference-sources/1','entry':'main.nex','files':{'main.nex':scalar}}})
runtime_inputs=sorted(path for path in (root/'runtime').rglob('*')if path.is_file()and path.suffix in ['.h','.hpp','.c','.cpp','.manifest'])
runtime_identity=''.join(path.relative_to(root).as_posix()+':'+sha(path)+'\n'for path in runtime_inputs)
report={'schema':'nex.managed-reference-native-agreement/1','ok':False,'private_language':'0.30-refs-prototype','public_source_enabled':False,'platform':platform.platform(),'probe_sha256':sha(probe),'compiler_sha256':sha(compiler),'compiler_version':run([compiler,'--version']).stdout,'core_fixture_sha256':sha(root/'tests/managed_references.cpp'),'shared_corpus_sha256':sha(root/'tests/managed_reference_cases.py'),'runtime_source_tree_sha256':hashlib.sha256(runtime_identity.encode()).hexdigest(),'cases':[]}
if args.modules:report.update(input_kind='private_module_bundle',module_corpus_sha256=sha(root/'tests/managed_reference_module_cases.py'))
if args.requests:report.update(host_context='request',requests_per_run=2,calls_per_request=2,request_host_sha256=sha(root/'tests/managed_reference_request_host.h'),controls=[])
runtime_objects={}
for optimization in ['0','2']:
    objects=[];build=folder/('standalone-runtime-O'+optimization);build.mkdir(exist_ok=True)
    for name in ['runtime.cpp','nex_cells.cpp','nex_cell_host.cpp','nex_json.cpp','wire_runtime.cpp']:
        target=build/(name+'.o')
        run([compiler,'-std=c++20','-O'+optimization,'-pthread','-I',root/'runtime','-c',root/'runtime'/name,'-o',target]);objects.append(target)
    runtime_objects[optimization]=objects
for case in cases:
    directory=folder/case['name'];directory.mkdir(exist_ok=True);path=directory/('bundle.json' if args.modules else 'main.nex');path.write_text(json.dumps(case['bundle']) if args.modules else 'module managed_native;\n'+case['source']+'\n')
    limits=list(map(str,case.get('limits',[1048576,4194304,16777216])))
    reference=json.loads(run([probe,'bundle-reference' if args.modules else 'reference',path,*limits]).stdout)
    (directory/'reference.json').write_text(json.dumps(reference,indent=2)+'\n')
    if 'error'in case:assert reference['kind']=='trap'and reference['code']==case['error'],(case,reference)
    else:assert reference['kind']=='return'and reference['output']==case['output']and reference['remaining_nodes']==0,(case,reference)
    for optimization in ['0','2']:
        build=directory/('O'+optimization);build.mkdir(exist_ok=True)
        emit_mode=('bundle-' if args.modules else '')+('request-emit' if args.requests else 'emit')
        run([probe,emit_mode,path,build,triple,layout_text,str(optimization=='2').lower(),*limits])
        library=build/('program.dylib'if platform.system()=='Darwin'else'program.dll'if os.name=='nt'else'program.so')
        flags=['-dynamiclib','-undefined','dynamic_lookup']if platform.system()=='Darwin'else(['-shared',*probe_dll_inputs(str(probe),folder)]if os.name=='nt'else['-shared','-fPIC'])
        run([compiler,'-O'+optimization,*flags,build/'program.ll','-o',library])
        host_command=[str(probe),'request-run',str(library),'2',*limits,str(build/'host-requests.json')] if args.requests else [str(probe),'run',str(library)]
        actual=run_native(host_command,text=True,capture_output=True,timeout=45)
        (build/'stdout.txt').write_text(actual.stdout);(build/'stderr.txt').write_text(actual.stderr)
        expected_output=reference['output']*(4 if reference['kind']=='return' else 2) if args.requests else reference['output']
        assert actual.stdout==expected_output,(case['name'],optimization,actual.stdout,reference)
        if reference['kind']=='return':assert actual.returncode==exit_code(reference['value'])and not actual.stderr,(case['name'],optimization,actual.returncode,actual.stderr)
        else:
            assert actual.returncode==70,(case['name'],optimization,actual.returncode,actual.stderr)
            if reference['code']=='E_SOURCE_EXCEPTION':assert 'NEX_SOURCE_EXCEPTION' in actual.stderr,(case['name'],actual.stderr)
            else:assert reference['code']in actual.stderr and 'NEX_SOURCE_EXCEPTION'not in actual.stderr,(case['name'],actual.stderr)
            error_agrees(actual.stderr,reference)
        assert 'E_INTERNAL_LEAK'not in actual.stderr and 'native reference context left live values'not in actual.stderr,(case['name'],actual.stderr)
        executable=build/('standalone.exe'if os.name=='nt'else'standalone')
        platform_libraries=['-lntdll','-lbcrypt','-ladvapi32']if os.name=='nt'else[]
        extra=[]
        if args.requests:
            host=build/'request-host.cpp'
            host.write_text('#include "managed_reference_request_host.h"\nextern "C" int64_t nex_private_reference_request(nexrt::Handle **);\nint main(int argc,char **argv){if(argc!=2&&argc!=5)return 1;return runManagedRequests(nex_private_reference_request,2,2,{'+','.join(limits)+'},argv[1],argc==5?std::stoull(argv[2]):4000000,argc==5?std::stoul(argv[3]):0,argc==5?std::stoull(argv[4]):10000);}\n')
            extra=['-std=c++20','-I',root/'tests','-I',root/'runtime',host]
        run([compiler,'-O'+optimization,'-pthread',build/'program.ll',*extra,*runtime_objects[optimization],*platform_libraries,'-o',executable])
        independent=run_native([str(executable),str(build/'standalone-requests.json')] if args.requests else [str(executable)],text=True,capture_output=True,timeout=45)
        (build/'standalone-stdout.txt').write_text(independent.stdout);(build/'standalone-stderr.txt').write_text(independent.stderr)
        assert independent.returncode==actual.returncode and independent.stdout==actual.stdout,(case['name'],'standalone outcome',independent.returncode,independent.stdout,independent.stderr)
        if reference['kind']=='return':assert not independent.stderr,(case['name'],'standalone stderr',independent.stderr)
        elif reference['code']=='E_SOURCE_EXCEPTION':assert 'NEX_SOURCE_EXCEPTION'in independent.stderr,(case['name'],independent.stderr)
        else:assert reference['code']in independent.stderr and 'NEX_SOURCE_EXCEPTION'not in independent.stderr,(case['name'],independent.stderr)
        if reference['kind']!='return':error_agrees(independent.stderr,reference)
        assert 'E_INTERNAL_LEAK'not in independent.stderr,(case['name'],independent.stderr)
        if args.requests:
            host_requests=json.loads((build/'host-requests.json').read_text());standalone_requests=json.loads((build/'standalone-requests.json').read_text())
            assert host_requests==standalone_requests and len(host_requests)==2,(case['name'],host_requests,standalone_requests)
            assert all(item['live_delta']==0 and item['failed']==(reference['kind']!='return') for item in host_requests)
            if reference['kind']=='return':
                assert all(item['calls']==2 for item in host_requests)
                if isinstance(reference['value'],int):assert all(item['result']==reference['value'] for item in host_requests)
            if case['name']=='module-fatal-cleanup':
                for control,budget,cancel,timeout,code in [('budget',1,0,10000,'E_LIMIT'),('cancel',4000000,6,10000,'E_CANCELLED'),('deadline',4000000,0,0,'E_TIMEOUT')]:
                    records=[]
                    for hosting,command,record in [('host',[str(probe),'request-run',str(library),'2',*limits],build/(control+'-host.json')),('standalone',[str(executable)],build/(control+'-standalone.json'))]:
                        controlled=run_native([*command,str(record),str(budget),str(cancel),str(timeout)],text=True,capture_output=True,timeout=45)
                        (build/(control+'-'+hosting+'.stdout')).write_text(controlled.stdout);(build/(control+'-'+hosting+'.stderr')).write_text(controlled.stderr)
                        events=json.loads(record.read_text());records.append(events)
                        assert controlled.returncode==70 and controlled.stdout=='',(case['name'],control,hosting,controlled)
                        assert len(events)==2 and all(event['failed'] and event['code']==code and event['live_delta']==0 for event in events),(control,events)
                    assert records[0]==records[1],(control,records)
                    report['controls'].append({'optimization':'O'+optimization,'control':control,'code':code,'requests':records[0],'passed':True})
        outcome='source_error'if reference.get('code')=='E_SOURCE_EXCEPTION'else reference['kind']
        report['cases'].append({'name':case['name'],'optimization':'O'+optimization,'outcome':outcome,'exit_code':actual.returncode,'matching_host_image':True,'independent_executable':True,'source_sha256':sha(path),'mlir_sha256':sha(build/'program.mlir'),'llvm_sha256':sha(build/'program.ll'),'image_sha256':sha(library),'executable_sha256':sha(executable),'passed':True})
        if args.requests:report['cases'][-1].update(requests=host_requests,host_request_report_sha256=sha(build/'host-requests.json'),standalone_request_report_sha256=sha(build/'standalone-requests.json'))
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
assert sha(probe)==report['probe_sha256']and sha(compiler)==report['compiler_sha256'],'native tool changed during acceptance'
report['runtime_objects']={optimization:{path.name:sha(path)for path in objects}for optimization,objects in runtime_objects.items()}
report['ok']=True;report['comparisons']=len(report['cases']);(folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'ok':True,'comparisons':report['comparisons'],'report':str(folder/'report.json')}))
