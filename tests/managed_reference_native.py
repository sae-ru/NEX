"""Private reference/native cell semantics and context cleanup, Debug/Release."""
from host_fixture import run_native,exit_code,probe_dll_inputs
from pathlib import Path
import argparse,hashlib,json,os,platform,re,subprocess,tempfile

parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('compiler',type=Path)
parser.add_argument('--output',type=Path);args=parser.parse_args();probe=args.probe.resolve();compiler=args.compiler.absolute()
root=Path(__file__).resolve().parents[1]
folder=(args.output or Path(tempfile.mkdtemp(prefix='nex-managed-native-'))).resolve();folder.mkdir(parents=True,exist_ok=True)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def run(command,**kwargs):
    result=run_native(list(map(str,command)),text=True,capture_output=True,timeout=120,**kwargs)
    if result.returncode:raise RuntimeError(str(command)+'\n'+result.stdout+'\n'+result.stderr)
    return result
def error_agrees(stderr,reference):
    if reference['code']=='E_SOURCE_EXCEPTION':
        record=next(json.loads(line.split(' ',1)[1])for line in stderr.splitlines()if line.startswith('NEX_SOURCE_EXCEPTION '))
        assert record['code']+': '+record['message']==reference['message']and record['line']==reference['line'],(record,reference)
    else:
        record=next(json.loads(line.split(' ',1)[1])for line in stderr.splitlines()if line.startswith('NEX_NATIVE_TRAP '))
        assert record['code']==reference['code']and record['reported_line']==reference['line'],(record,reference)
layout=folder/'host.ll';run([compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',layout])
host=layout.read_text();triple=re.search(r'target triple = "(.*?)"',host)[1];layout_text=re.search(r'target datalayout = "(.*?)"',host)[1]
# Reuse the same hand-written sources/expected outputs as the core reference
# probe, rather than maintaining a second translation of these scenarios.
source=(root/'tests/managed_references.cpp').read_text()
pattern=r'runs\(R"nex\((.*?)\)nex",("(?:[^"\\]|\\.)*"(?:\s*"(?:[^"\\]|\\.)*")*)(?:,\{([^}]*)\})?\);'
cases=[]
for index,match in enumerate(re.finditer(pattern,source,re.S)):
    expected=''.join(json.loads(part) for part in re.findall(r'"(?:[^"\\]|\\.)*"',match[2]))
    limits=[int(value)for value in match[3].split(',')]if match[3]else[1048576,4194304,16777216]
    cases.append({'name':'core-'+str(index+1),'source':match[1],'output':expected,'limits':limits})
assert len(cases)==9,('core reference source extraction changed',len(cases))
cases.extend([
 {'name':'bool-float-bytes','source':'fn main()->unit!{state,io}{let flag:cell<bool>=cell_new(false);cell_write(flag,true);print(cell_read(flag));let real:cell<f64>=cell_new(1.25);cell_write(real,cell_read(real)+0.5);assert(cell_read(real)==1.75);let octets:cell<bytes>=cell_new(utf8_bytes("Я🌍"));let old:bytes=cell_read(octets);cell_write(octets,utf8_bytes("new"));assert(unwrap(decode_utf8(old))=="Я🌍");print("scalar-octets-ok");}','output':'true\nscalar-octets-ok\n'},
 {'name':'uncaught-cell','source':'fn main()->unit!{state,throw}{let value:cell<i64>=cell_new(1);throw(value);}','error':'E_SOURCE_EXCEPTION'},
 {'name':'overflow-cleanup','source':'struct Node{next:list<cell<Node>>;}fn main()->unit!{state,io}{let value:cell<Node>=cell_new(Node([]));cell_write(value,Node([value]));try{let bad:i64=9223372036854775807+1;}finally{print("wrong-finalizer");}}','error':'E_OVERFLOW'},
 {'name':'limit-cleanup','source':'fn main()->unit!{state}{let a:cell<i64>=cell_new(1);let b:cell<i64>=cell_new(2);let c:cell<i64>=cell_new(3);}','limits':[2,8,16],'error':'E_CELL_LIMIT'},
])
runtime_inputs=sorted(path for path in (root/'runtime').rglob('*')if path.is_file()and path.suffix in ['.h','.hpp','.c','.cpp','.manifest'])
runtime_identity=''.join(path.relative_to(root).as_posix()+':'+sha(path)+'\n'for path in runtime_inputs)
report={'schema':'nex.managed-reference-native-agreement/1','ok':False,'private_language':'0.30-refs-prototype','public_source_enabled':False,'platform':platform.platform(),'probe_sha256':sha(probe),'compiler_sha256':sha(compiler),'compiler_version':run([compiler,'--version']).stdout,'core_fixture_sha256':sha(root/'tests/managed_references.cpp'),'runtime_source_tree_sha256':hashlib.sha256(runtime_identity.encode()).hexdigest(),'cases':[]}
runtime_objects={}
for optimization in ['0','2']:
    objects=[];build=folder/('standalone-runtime-O'+optimization);build.mkdir(exist_ok=True)
    for name in ['runtime.cpp','nex_cells.cpp','nex_cell_host.cpp']:
        target=build/(name+'.o')
        run([compiler,'-std=c++20','-O'+optimization,'-pthread','-I',root/'runtime','-c',root/'runtime'/name,'-o',target]);objects.append(target)
    runtime_objects[optimization]=objects
for case in cases:
    directory=folder/case['name'];directory.mkdir(exist_ok=True);path=directory/'main.nex';path.write_text('module managed_native;\n'+case['source']+'\n')
    limits=list(map(str,case.get('limits',[1048576,4194304,16777216])))
    reference=json.loads(run([probe,'reference',path,*limits]).stdout)
    (directory/'reference.json').write_text(json.dumps(reference,indent=2)+'\n')
    if 'error'in case:assert reference['kind']=='trap'and reference['code']==case['error'],(case,reference)
    else:assert reference['kind']=='return'and reference['output']==case['output']and reference['remaining_nodes']==0,(case,reference)
    for optimization in ['0','2']:
        build=directory/('O'+optimization);build.mkdir(exist_ok=True)
        run([probe,'emit',path,build,triple,layout_text,str(optimization=='2').lower(),*limits])
        library=build/('program.dylib'if platform.system()=='Darwin'else'program.so')
        flags=['-dynamiclib','-undefined','dynamic_lookup']if platform.system()=='Darwin'else(['-shared',*probe_dll_inputs(str(probe),folder)]if os.name=='nt'else['-shared','-fPIC'])
        run([compiler,'-O'+optimization,*flags,build/'program.ll','-o',library])
        actual=run_native([str(probe),'run',str(library)],text=True,capture_output=True,timeout=45)
        (build/'stdout.txt').write_text(actual.stdout);(build/'stderr.txt').write_text(actual.stderr)
        assert actual.stdout==reference['output'],(case['name'],optimization,actual.stdout,reference)
        if reference['kind']=='return':assert actual.returncode==exit_code(reference['value'])and not actual.stderr,(case['name'],optimization,actual.returncode,actual.stderr)
        else:
            assert actual.returncode==70,(case['name'],optimization,actual.returncode,actual.stderr)
            if reference['code']=='E_SOURCE_EXCEPTION':assert 'NEX_SOURCE_EXCEPTION' in actual.stderr,(case['name'],actual.stderr)
            else:assert reference['code']in actual.stderr and 'NEX_SOURCE_EXCEPTION'not in actual.stderr,(case['name'],actual.stderr)
            error_agrees(actual.stderr,reference)
        assert 'E_INTERNAL_LEAK'not in actual.stderr and 'native reference context left live values'not in actual.stderr,(case['name'],actual.stderr)
        executable=build/('standalone.exe'if os.name=='nt'else'standalone')
        platform_libraries=['-lntdll','-lbcrypt','-ladvapi32']if os.name=='nt'else[]
        run([compiler,'-O'+optimization,'-pthread',build/'program.ll',*runtime_objects[optimization],*platform_libraries,'-o',executable])
        independent=run_native([str(executable)],text=True,capture_output=True,timeout=45)
        (build/'standalone-stdout.txt').write_text(independent.stdout);(build/'standalone-stderr.txt').write_text(independent.stderr)
        assert independent.returncode==actual.returncode and independent.stdout==actual.stdout,(case['name'],'standalone outcome',independent.returncode,independent.stdout,independent.stderr)
        if reference['kind']=='return':assert not independent.stderr,(case['name'],'standalone stderr',independent.stderr)
        elif reference['code']=='E_SOURCE_EXCEPTION':assert 'NEX_SOURCE_EXCEPTION'in independent.stderr,(case['name'],independent.stderr)
        else:assert reference['code']in independent.stderr and 'NEX_SOURCE_EXCEPTION'not in independent.stderr,(case['name'],independent.stderr)
        if reference['kind']!='return':error_agrees(independent.stderr,reference)
        assert 'E_INTERNAL_LEAK'not in independent.stderr,(case['name'],independent.stderr)
        outcome='source_error'if reference.get('code')=='E_SOURCE_EXCEPTION'else reference['kind']
        report['cases'].append({'name':case['name'],'optimization':'O'+optimization,'outcome':outcome,'exit_code':actual.returncode,'matching_host_image':True,'independent_executable':True,'source_sha256':sha(path),'mlir_sha256':sha(build/'program.mlir'),'llvm_sha256':sha(build/'program.ll'),'image_sha256':sha(library),'executable_sha256':sha(executable),'passed':True})
        (folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
assert sha(probe)==report['probe_sha256']and sha(compiler)==report['compiler_sha256'],'native tool changed during acceptance'
report['runtime_objects']={optimization:{path.name:sha(path)for path in objects}for optimization,objects in runtime_objects.items()}
report['ok']=True;report['comparisons']=len(report['cases']);(folder/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'ok':True,'comparisons':report['comparisons'],'report':str(folder/'report.json')}))
