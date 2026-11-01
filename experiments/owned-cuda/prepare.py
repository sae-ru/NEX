"""Build a pinned Windows CUDA C-FFI provider without executing the driver."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    development=ROOT/'build/windows-host/nex.exe'
    installed=ROOT.parent.parent/'bin/nex.exe'
    parser.add_argument('--compiler',type=Path,default=development if development.is_file() else installed)
    parser.add_argument('--cxx',type=Path,help='Override the native C++ compiler reported by nex doctor')
    parser.add_argument('--sysroot',type=Path,help='Override the native Windows sysroot reported by nex doctor')
    parser.add_argument('--cuda',type=Path,default=Path(os.environ.get('CUDA_PATH','C:/Program Files/NVIDIA GPU Computing Toolkit/CUDA/v12.1')))
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--index',type=int,default=0)
    args=parser.parse_args()
    if os.name!='nt':parser.error('use native Windows Python')
    if not 0<=args.index<64:parser.error('device ordinal must be0..63')
    compiler=args.compiler.resolve(strict=True);cuda=args.cuda.resolve(strict=True)
    if not (cuda/'include/cuda.h').is_file():parser.error('CUDA Driver API headers are required')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False);evidence=out/'preparation';evidence.mkdir()
    commands=[]
    def run(label,argv):
        row={'label':label,'argv':list(map(str,argv)),'cwd':str(out)};commands.append(row);write(evidence/'commands.json',commands)
        result=subprocess.run(row['argv'],cwd=out,capture_output=True,timeout=300)
        (evidence/(label+'.stdout')).write_bytes(result.stdout);(evidence/(label+'.stderr')).write_bytes(result.stderr)
        row['exit_code']=result.returncode;write(evidence/'commands.json',commands)
        if result.returncode:raise RuntimeError(label+': '+result.stdout.decode('utf-8','replace')[-1500:]+result.stderr.decode('utf-8','replace')[-3000:])
        return result.stdout
    index=json.loads(run('index',[compiler,'describe','--kind','index','--json']))
    doctor=json.loads(run('doctor',[compiler,'doctor','--json']))
    cxx=(args.cxx or Path(doctor['native_compiler'])).resolve(strict=True)
    sysroot=(args.sysroot or Path(doctor['native_sysroot'])).resolve(strict=True)
    target=['--target='+doctor['host'],'--sysroot='+str(sysroot)]
    language=index['language']
    if language!='0.27':raise RuntimeError('this provider acceptance targets the current0.27 source cohort')
    (out/'stdlib').mkdir()
    for name in ('compute.nex','device.nex'):shutil.copy2(ROOT/'lib'/name,out/'stdlib'/name)
    write(out/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':'./stdlib'}})
    source=Path(__file__).resolve().parent
    template=(source/'main.nex.in').read_bytes().decode('utf-8').replace('@INDEX@',str(args.index))
    (out/'main.nex').write_bytes(template.replace('@PIN@','0'*64).encode('utf-8'))
    run('check-template',[compiler,'check','--json'])
    signatures={}
    for name,local in [('open','open_raw'),('upload','upload_raw'),('dispatch','dispatch_raw'),('download','download_raw'),('name','name_raw'),('kernel_ns','kernel_ns_raw'),('busy','busy_raw')]:
        signatures[name]=json.loads(run('signature-'+name,[compiler,'ffi','--symbol',local,'--json']))
    digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode('utf-8')).hexdigest()
    generated=out/'generated';generated.mkdir()
    (generated/'signatures.h').write_bytes(('\n'.join('#define PIN_'+name.upper()+' "'+digest(value)+'"' for name,value in signatures.items())+'\n').encode('utf-8'))
    inputs=evidence/'inputs';inputs.mkdir()
    for name in ('module.cpp','main.nex.in','context_probe.cpp'):shutil.copy2(source/name,inputs/name)
    bundle=out/'bundle';bundle.mkdir()
    temporary=Path(tempfile.gettempdir())
    while not str(temporary).isascii() or '%' in str(temporary):temporary=temporary.parent
    with tempfile.TemporaryDirectory(prefix='nex-cuda-cxx-',dir=temporary) as stage:
        run('compile-module',[cxx,*target,'-std=c++20','-O2','-shared','-static',
                             '-Wall','-Wextra','-I'+str(ROOT/'runtime'),'-I'+str(generated),'-I'+str(cuda/'include'),
                             inputs/'module.cpp','-o',Path(stage)/'module.dll'])
        run('compile-context-probe',[cxx,*target,'-std=c++20','-O2','-static',
                                    '-DNEX_CUDA_PROBE_INDEX='+str(args.index),'-I'+str(ROOT/'runtime'),
                                    '-I'+str(generated),'-I'+str(cuda/'include'),inputs/'context_probe.cpp',
                                    '-o',Path(stage)/'context-probe.exe'])
        shutil.copy2(Path(stage)/'module.dll',bundle/'module.dll')
        shutil.copy2(Path(stage)/'context-probe.exe',evidence/'context-probe.exe')
    notice='NEX owned CUDA Driver API provider\n\n'+(ROOT/'LICENSE').read_bytes().decode('utf-8')+'\n\nnlohmann/json\n'+(ROOT/'runtime/third_party/JSON-LICENSE.MIT').read_bytes().decode('utf-8')
    notice+='\n\nNative compiler runtime notices\n'+Path(doctor['native_windows_notices']).read_text(encoding='utf-8')
    (bundle/'NOTICE').write_bytes(notice.encode('utf-8'))
    manifest={'schema':'nex.foreign-bundle/1','platform':'windows-x86_64','entry':'module.dll',
              'files':[{'path':name,'sha256':sha(bundle/name)} for name in ('module.dll','NOTICE')],
              'exports':{name:digest(value) for name,value in signatures.items()},'notices':['NOTICE']}
    write(bundle/'manifest.json',manifest);pin=sha(bundle/'manifest.json')
    (out/'main.nex').write_bytes(template.replace('@PIN@',pin).encode('utf-8'))
    write(out/'foreign.json',{'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':64,'resource_bytes':16777216,
                            'libraries':{'gpu':{'directory':'./bundle','manifest_sha256':pin,'exports':list(signatures)}}})
    run('check-pinned',[compiler,'check','--json']);run('catalogue',[compiler,'foreign',out/'foreign.json','--json'])
    report={'schema':'nex.owned-cuda-preparation/1','ok':True,'environment':'native Windows','requires_WSL':False,
            'compiler_sha256':sha(compiler),'source_language':language,'index':index,'cxx':str(cxx),'cxx_sha256':sha(cxx),'native_target':doctor['host'],'native_sysroot':str(sysroot),
            'cuda_header':str(cuda/'include/cuda.h'),'cuda_header_sha256':sha(cuda/'include/cuda.h'),
            'manifest_sha256':pin,'module_sha256':sha(bundle/'module.dll'),'context_probe_sha256':sha(evidence/'context-probe.exe'),'source_sha256':{p.name:sha(p) for p in inputs.iterdir()},
            'library_sha256':{p.name:sha(p) for p in (out/'stdlib').iterdir()},
            'hardware_executed':False,'driver_initialized':False,'CUDA_from_NEX_accepted':False,'commands':commands}
    write(evidence/'report.json',report);print(json.dumps({'ok':True,'output':str(out),'manifest_sha256':pin,'hardware_executed':False}))

if __name__=='__main__':main()
