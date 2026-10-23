#!/usr/bin/env python3
"""Prepare explicit, pinned RK3588 FFI fixtures; do not execute accelerators."""
import argparse,hashlib,json,os,platform,shutil,subprocess
from pathlib import Path

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--sdk',required=True,type=Path);p.add_argument('--backend',required=True,choices=['gpu','npu'])
 p.add_argument('--output',required=True,type=Path);p.add_argument('--cxx',default='g++')
 p.add_argument('--vendor-include',type=Path);p.add_argument('--vendor-license',type=Path)
 a=p.parse_args()
 if platform.system()!='Linux' or platform.machine() not in ('aarch64','arm64'):p.error('requires Linux ARM64')
 if a.backend=='npu' and (not a.vendor_include or not a.vendor_license):p.error('NPU requires operator-provided RKNN SDK headers and license')
 origin=Path(__file__).resolve().parent;sdk=a.sdk.resolve(strict=True);resources=sdk/'share/nex';compiler=sdk/'bin/nex'
 root=a.output.absolute();root.mkdir(exist_ok=False)
 env={**os.environ,'NEX_RESOURCE_DIR':str(resources)}
 def run(args):
  r=subprocess.run(list(map(str,args)),cwd=root,env=env,capture_output=True,text=True,timeout=180)
  if r.returncode:raise RuntimeError(r.stderr or r.stdout)
  return r.stdout
 def cli(*args):return json.loads(run([compiler,*args,'--json']))
 descriptor=cli('describe')
 if descriptor['version']!='0.20' or not descriptor['foreign_boundary']['source_support']:raise RuntimeError('requires language0.20 with source FFI')
 backend=a.backend;symbol='gpu_affine' if backend=='gpu' else 'npu_matmul_bytes';library='rk_'+backend
 template=(origin/(backend+'-main.nex.in')).read_text()
 if backend=='npu':template=template.replace('@API@',(origin/'npu-api.nex.in').read_text())
 main=root/'main.nex'
 main.write_text(template.replace('@PIN@','0'*64));(root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'main.nex'}))
 signature=cli('ffi','--symbol',symbol);digest=hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
 bundle=root/'bundle';bundle.mkdir()
 for name in [backend+'-module.cpp',backend+'-worker.cpp']+(['npu-common.h','npu-broker.inc'] if backend=='npu' else []):shutil.copy2(origin/name,root/name)
 includes=['-I'+str(resources/'runtime'),'-I'+str(origin.parent/'cix-p1/include')]
 vendor={}
 if backend=='npu':
  includes.append('-I'+str(a.vendor_include.resolve(strict=True)))
  for name in ['rknn_api.h','rknn_matmul_api.h']:vendor[name]=sha(a.vendor_include/name)
  vendor['license_sha256']=sha(a.vendor_license)
 flags=[a.cxx,'-std=c++20','-O2','-Wall','-Wextra',*includes]
 run([*flags,root/(backend+'-worker.cpp'),'-o',bundle/(backend+'-worker'),'-ldl','-pthread'])
 run([*flags,'-shared','-fPIC','-fvisibility=hidden','-DNEX_'+backend.upper()+'_SIGNATURE="'+digest+'"',root/(backend+'-module.cpp'),'-o',bundle/'module.so','-ldl','-pthread'])
 notice='NEX-owned experimental RK3588 trusted FFI fixture. Per-call child worker, no stable generic compute API.\n'
 notice+=(resources/'runtime/third_party/JSON-LICENSE.MIT').read_text()
 if backend=='gpu':notice+='\n'+(origin.parent/'cix-p1/include/OPENCL-LICENSE').read_text()
 else:notice+='\nOptional private Rockchip-compatible SDK/runtime dependency; not relicensed as NEX.\n'+a.vendor_license.read_text()
 (bundle/'NOTICE').write_text(notice)
 manifest={'schema':'nex.foreign-bundle/1','platform':'linux-arm64','entry':'module.so','files':[{'path':n,'sha256':sha(bundle/n)} for n in ['module.so',backend+'-worker','NOTICE']],'exports':{symbol:digest},'notices':['NOTICE']}
 (bundle/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2)+'\n');pin=sha(bundle/'manifest.json');main.write_text(template.replace('@PIN@',pin))
 host={'schema':'nex.foreign-host/1','module_limit':64,'libraries':{library:{'directory':'bundle','manifest_sha256':pin,'exports':[symbol]}}}
 (root/'host.json').write_text(json.dumps(host,indent=2)+'\n');cli('check');catalogue=cli('foreign',root/'host.json')
 report={'ok':True,'backend':backend,'hardware_executed':False,'compiler_sha256':sha(compiler),'manifest_sha256':pin,'sources':{n:sha(root/n) for n in [backend+'-module.cpp',backend+'-worker.cpp']},'optional_vendor_input':vendor,'catalogue':catalogue}
 if backend=='npu':report['installed_runtime_sha256']=sha(Path('/usr/lib/librknnrt.so'))
 (root/'preparation.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='catalogue'}))
if __name__=='__main__':main()
