"""Prepare a pinned persistent OpenCL provider; preparation executes no driver."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--sdk',required=True,type=Path);parser.add_argument('--output',required=True,type=Path)
 parser.add_argument('--opencl-library',type=Path);parser.add_argument('--index',type=int,default=0);parser.add_argument('--cxx',default=shutil.which('clang++') or shutil.which('g++'))
 parser.add_argument('--check-sdk',action='store_true',help='check actual source and FFI signatures without building or initializing a device')
 args=parser.parse_args();sdk=args.sdk.resolve(strict=True);out=args.output.absolute();compiler=sdk/'bin'/('nex.exe' if os.name=='nt' else 'nex');resources=sdk/'share/nex'
 if platform.machine().lower() not in ('arm64','aarch64','x86_64','amd64'):parser.error('owned OpenCL preparation requires a supported64-bit architecture')
 if platform.system() not in ('Darwin','Linux') and not (args.check_sdk and os.name=='nt'):parser.error('native OpenCL worker preparation currently supports macOS/Linux; --check-sdk also supports native Windows')
 if not 0<=args.index<64:parser.error('GPU index must be0..63')
 if out.exists():parser.error('output directory must be new')
 if not args.check_sdk and (not args.cxx or not Path(args.cxx).is_file()):parser.error('an actual C++20 compiler is required')
 library=args.opencl_library or (Path('/System/Library/Frameworks/OpenCL.framework/OpenCL') if platform.system()=='Darwin' else None)
 if not args.check_sdk and (library is None or not library.is_absolute()):parser.error('Linux requires an explicit absolute OpenCL loader path')
 if not args.check_sdk and platform.system()=='Linux' and not library.is_file():parser.error('the selected Linux OpenCL loader must exist')
 out.mkdir(parents=True);evidence=out/'preparation';evidence.mkdir();commands=[]
 env={**os.environ,'NEX_RESOURCE_DIR':str(resources),'PYTHONDONTWRITEBYTECODE':'1'}
 def run(name,argv,cwd=out):
  row={'name':name,'argv':list(map(str,argv)),'cwd':str(cwd)};commands.append(row);write(evidence/'commands.json',commands)
  p=subprocess.run(row['argv'],cwd=cwd,env=env,capture_output=True,text=True,timeout=300)
  (evidence/(name+'.stdout')).write_text(p.stdout);(evidence/(name+'.stderr')).write_text(p.stderr);row['exit_code']=p.returncode;write(evidence/'commands.json',commands)
  if p.returncode:raise RuntimeError(name+' failed: '+p.stderr[-2000:]+' '+p.stdout[-1500:])
  return p.stdout
 descriptor=json.loads(run('describe',[compiler,'describe','--json']));parent=descriptor.get('resource_regions',{}).get('dependency_graph',{})
 spec=importlib.util.spec_from_file_location('nex_owned_provider_sdk',ROOT/'tools/provider_sdk.py');helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
 language=helper.source_language(descriptor,'compute')
 if parent.get('C_table_parent_creation') is not True or descriptor.get('foreign_boundary',{}).get('owned_external_host',{}).get('source_task_bridge') is not True or descriptor.get('foreign_boundary',{}).get('module_loading',{}).get('executable_members') is not True:raise RuntimeError('selected compiler must support dependent C resources, source task/FFI and pinned executable members')
 (out/'stdlib').mkdir()
 for name in ['compute.nex','device.nex']:shutil.copy2(ROOT/'lib'/name,out/'stdlib'/name)
 write(out/'nex.json',{'schema':'nex.project/1','language':language,'entry':'main.nex','libraries':{'std':'./stdlib'}})
 template=(Path(__file__).parent/'main.nex.in').read_text().replace('@INDEX@',str(args.index));(out/'main.nex').write_text(template.replace('@PIN@','0'*64))
 run('check-template',[compiler,'check','--json']);signatures={}
 for name,local in [('open','open_raw'),('upload','upload_raw'),('dispatch','dispatch_raw'),('download','download_raw'),('name','name_raw'),('kernel_ns','kernel_ns_raw'),('busy','busy_raw')]:
  signatures[name]=json.loads(run('signature-'+name,[compiler,'ffi','--symbol',local,'--json']))
 digest=lambda value:hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
 generated=out/'generated';generated.mkdir();(generated/'signatures.h').write_text('\n'.join('#define PIN_'+name.upper()+' "'+digest(value)+'"' for name,value in signatures.items())+'\n')
 source=Path(__file__).parent;include=source/'include'
 if not include.is_dir():include=ROOT/'experiments/cix-p1/include'
 inputs=evidence/'inputs';inputs.mkdir()
 for name in ['worker.cpp','module.cpp','protocol.h','main.nex.in']:shutil.copy2(source/name,inputs/name)
 shutil.copytree(include,inputs/'include')
 source_hashes={p.relative_to(inputs).as_posix():sha(p) for p in sorted(inputs.rglob('*')) if p.is_file()}
 base={'schema':'nex.owned-opencl-preparation/1','ok':True,'compiler_sha256':sha(compiler),'source_language':language,
  'source_compiler_toolchain':json.loads(run('doctor',[compiler,'doctor','--json']))['version'],
  'source_checked':True,'signature_sha256':{name:digest(value) for name,value in signatures.items()},
  'source_input_sha256':source_hashes,'library_sha256':{name:sha(out/'stdlib'/name) for name in ['compute.nex','device.nex']},
  'native_provider_built':False,'driver_initialized':False,'hardware_executed':False,'persistent_worker':True,'parent_C_API_required':True}
 if args.check_sdk:
  write(evidence/'report.json',{**base,'commands':commands});print(json.dumps({'ok':True,'output':str(out),'source_checked':True,'native_provider_built':False,'hardware_executed':False}));return
 bundle=out/'bundle';bundle.mkdir();source=inputs;include=inputs/'include'
 flags=['-std=c++20','-O2','-pthread','-I'+str(resources/'runtime'),'-I'+str(include),'-I'+str(source),'-I'+str(generated)]
 run('compile-worker',[args.cxx,*flags,'-DNEX_OPENCL_LIBRARY='+json.dumps(str(library)),source/'worker.cpp','-o',bundle/'worker',*(['-ldl'] if platform.system()=='Linux' else [])])
 run('compile-module',[args.cxx,*flags,'-shared','-fPIC','-fvisibility=hidden',source/'module.cpp','-o',bundle/'module.so',*(['-ldl'] if platform.system()=='Linux' else [])])
 (bundle/'NOTICE').write_text('NEX owned OpenCL provider and persistent worker\n\n'+(include/'OPENCL-LICENSE').read_text()+'\n\nnlohmann/json\n'+(resources/'runtime/third_party/JSON-LICENSE.MIT').read_text())
 manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+('arm64' if platform.machine() in ('arm64','aarch64') else 'x86_64'),
  'entry':'module.so','executables':['worker'],'files':[{'path':name,'sha256':sha(bundle/name)} for name in ['module.so','worker','NOTICE']],
  'exports':{name:digest(value) for name,value in signatures.items()},'notices':['NOTICE']}
 write(bundle/'manifest.json',manifest);pin=sha(bundle/'manifest.json');(out/'main.nex').write_text(template.replace('@PIN@',pin))
 write(out/'foreign.json',{'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':64,'resource_bytes':16777216,
  'libraries':{'gpu':{'directory':'./bundle','manifest_sha256':pin,'exports':list(signatures)}}})
 run('check-pinned',[compiler,'check','--json']);run('catalogue',[compiler,'foreign',out/'foreign.json','--json'])
 assert all(sha(inputs/name)==value for name,value in source_hashes.items()),'provider source changed during preparation'
 report={**base,'manifest_sha256':pin,
  'worker_sha256':sha(bundle/'worker'),'module_sha256':sha(bundle/'module.so'),'OpenCL_library':str(library),
  'OpenCL_library_sha256':sha(library) if library.is_file() else None,'runtime_digest_is_immutable_pin':False,
  'native_provider_built':True,'driver_initialized':False,'hardware_executed':False,'persistent_worker':True,'parent_C_API_required':True,'commands':commands}
 write(evidence/'report.json',report);print(json.dumps({'ok':True,'output':str(out),'manifest_sha256':pin,'hardware_executed':False}))
if __name__=='__main__':main()
