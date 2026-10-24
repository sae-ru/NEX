#!/usr/bin/env python3
"""Prepare pinned Linux ARM64 accelerator projects without executing devices."""
import argparse,hashlib,json,os,platform,shutil,subprocess
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--sdk',required=True,type=Path);p.add_argument('--backend',required=True,choices=['gpu','npu'])
 p.add_argument('--output',required=True,type=Path);p.add_argument('--cxx',default='g++')
 p.add_argument('--api',choices=['raw','compute'],default='raw')
 p.add_argument('--opencl-library',type=Path,help='operator-selected installed OpenCL loader; embedded in pinned worker')
 p.add_argument('--opencl-include',type=Path);p.add_argument('--vendor-include',type=Path);p.add_argument('--vendor-license',type=Path)
 a=p.parse_args()
 if platform.system()!='Linux' or platform.machine() not in ('aarch64','arm64'):p.error('requires Linux ARM64')
 if a.backend=='npu' and (not a.vendor_include or not a.vendor_license):p.error('NPU requires operator-provided RKNN SDK headers and license')
 if a.backend!='gpu' and (a.api=='compute' or a.opencl_library):p.error('--api compute and --opencl-library currently require --backend gpu')
 origin=Path(__file__).resolve().parent;sdk=a.sdk.resolve(strict=True);resources=sdk/'share/nex';compiler=sdk/'bin/nex'
 root=a.output.absolute();root.mkdir(exist_ok=False)
 env={**os.environ,'NEX_RESOURCE_DIR':str(resources)}
 commands=[]
 def run(args):
  r=subprocess.run(list(map(str,args)),cwd=root,env=env,capture_output=True,text=True,timeout=180)
  number=len(commands);(root/('prepare-'+str(number)+'.stdout')).write_text(r.stdout);(root/('prepare-'+str(number)+'.stderr')).write_text(r.stderr)
  commands.append({'command':list(map(str,args)),'exit_code':r.returncode})
  if r.returncode:raise RuntimeError(r.stderr or r.stdout)
  return r.stdout
 def cli(*args):return json.loads(run([compiler,*args,'--json']))
 descriptor=cli('describe')
 if descriptor['version'] not in ('0.20','0.21') or not descriptor['foreign_boundary']['source_support']:raise RuntimeError('requires language0.20 with source FFI')
 backend=a.backend;symbol='gpu_compute' if backend=='gpu' else 'npu_matmul_bytes';library='rk_'+backend
 template=(origin/('compute-gpu-main.nex.in' if a.api=='compute' else backend+'-main.nex.in')).read_text()
 if backend=='npu':template=template.replace('@API@',(origin/'npu-api.nex.in').read_text())
 main=root/'main.nex'
 project={'schema':'nex.project/1','language':descriptor['version'],'entry':'main.nex'}
 if a.api=='compute':
  (root/'stdlib').mkdir();shutil.copy2(origin.parents[1]/'lib/compute.nex',root/'stdlib/compute.nex');project['libraries']={'std':'./stdlib'}
 placeholder='c::Device(c::Kind::GPU(),"pending","OpenCL","3","preparation-only",[])'
 main.write_text(template.replace('@PIN@','0'*64).replace('@GPU_DEVICE@',placeholder));(root/'nex.json').write_text(json.dumps(project,indent=2)+'\n')
 signature=cli('ffi','--symbol','gpu_raw' if a.api=='compute' else symbol);digest=hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 bundle=root/'bundle';bundle.mkdir()
 for name in [backend+'-module.cpp',backend+'-worker.cpp']+(['npu-common.h','npu-broker.inc'] if backend=='npu' else []):shutil.copy2(origin/name,root/name)
 includes=['-I'+str(resources/'runtime')]
 if backend=='gpu':includes.append('-I'+str(a.opencl_include.resolve(strict=True) if a.opencl_include else origin.parent/'cix-p1/include'))
 vendor={}
 if backend=='npu':
  includes.append('-I'+str(a.vendor_include.resolve(strict=True)))
  for name in ['rknn_api.h','rknn_matmul_api.h']:vendor[name]=sha(a.vendor_include/name)
  vendor['license_sha256']=sha(a.vendor_license)
 flags=[a.cxx,'-std=c++20','-O2','-Wall','-Wextra',*includes]
 worker_flags=[];opencl={}
 if backend=='gpu':
  loader=(a.opencl_library or Path('/usr/lib/aarch64-linux-gnu/libOpenCL.so.1')).resolve(strict=True)
  if not loader.is_file():p.error('OpenCL loader must resolve to a regular file')
  opencl={'path':str(loader),'sha256_at_preparation':sha(loader),'runtime_immutable_pin':False}
  worker_flags=['-DNEX_OPENCL_LIBRARY='+json.dumps(str(loader),ensure_ascii=True)]
 run([*flags,*worker_flags,root/(backend+'-worker.cpp'),'-o',bundle/(backend+'-worker'),'-ldl','-pthread'])
 run([*flags,'-shared','-fPIC','-fvisibility=hidden','-DNEX_'+backend.upper()+'_SIGNATURE="'+digest+'"',root/(backend+'-module.cpp'),'-o',bundle/'module.so','-ldl','-pthread'])
 notice='NEX-owned experimental Linux ARM64 trusted FFI provider. Per-call pinned child worker.\n'
 notice+=(resources/'runtime/third_party/JSON-LICENSE.MIT').read_text()
 if backend=='gpu':notice+='\n'+((a.opencl_include if a.opencl_include else origin.parent/'cix-p1/include')/'OPENCL-LICENSE').read_text()
 else:notice+='\nOptional private Rockchip-compatible SDK/runtime dependency; not relicensed as NEX.\n'+a.vendor_license.read_text()
 (bundle/'NOTICE').write_text(notice)
 manifest={'schema':'nex.foreign-bundle/1','platform':'linux-arm64','entry':'module.so','files':[{'path':n,'sha256':sha(bundle/n)} for n in ['module.so',backend+'-worker','NOTICE']],'exports':{symbol:digest},'notices':['NOTICE']}
 (bundle/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');pin=sha(bundle/'manifest.json')
 if a.api=='compute':
  provenance='operator-selected OpenCL sha256:'+opencl['sha256_at_preparation']+'; pinned worker:'+sha(bundle/'gpu-worker')
  device='c::Device(c::Kind::GPU(),"opencl-gpu0","OpenCL checked-u8-worker","3",'+json.dumps(provenance)+',[c::Capability(c::OperationKind::Add(),c::DType::U8(),c::DType::U8()),c::Capability(c::OperationKind::Affine(),c::DType::U8(),c::DType::U8())])'
  template=template.replace('@GPU_DEVICE@',device)
 main.write_text(template.replace('@PIN@',pin))
 host={'schema':'nex.foreign-host/1','module_limit':64,'libraries':{library:{'directory':'bundle','manifest_sha256':pin,'exports':[symbol]}}}
 (root/'host.json').write_text(json.dumps(host,indent=2)+'\n');cli('check');catalogue=cli('foreign',root/'host.json')
 report={'ok':True,'commands':commands,'backend':backend,'hardware_executed':False,'compiler_sha256':sha(compiler),'manifest_sha256':pin,'sources':{n:sha(root/n) for n in [backend+'-module.cpp',backend+'-worker.cpp']},'optional_vendor_input':vendor,'catalogue':catalogue}
 report.update(api=a.api,opencl_loader=opencl)
 if a.api=='compute':report['library_sha256']=sha(root/'stdlib/compute.nex')
 if backend=='npu':report['installed_runtime_sha256']=sha(Path('/usr/lib/librknnrt.so'))
 (root/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='catalogue'}))
if __name__=='__main__':main()
