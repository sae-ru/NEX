#!/usr/bin/env python3
"""Executed inside the Linux toolchain container; retain all verification logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--live',action='store_true')
    args=parser.parse_args();root=Path('/build');started=time.monotonic()
    report={'ok':False,'source':'/src','network':'none','phases':[]}
    def save(): (root/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(name,command):
        row={'name':name,'command':list(map(str,command)),'status':'running'};report['phases'].append(row);save()
        with (root/(name+'.log')).open('w') as log:
            result=subprocess.run(row['command'],stdout=log,stderr=subprocess.STDOUT)
        row.update(status='passed' if result.returncode==0 else 'failed',exit_code=result.returncode);save()
        if result.returncode:raise RuntimeError(name+' failed; inspect /build/'+name+'.log')
    try:
        run('configure',['cmake','-S','/src','-B','/build','-DCMAKE_CXX_COMPILER=clang++','-DCMAKE_C_COMPILER=clang','-DCMAKE_BUILD_TYPE=Debug','-DCMAKE_EXE_LINKER_FLAGS=-fuse-ld=lld','-DLLVM_DIR=/usr/lib/llvm-22/lib/cmake/llvm','-DMLIR_DIR=/usr/lib/llvm-22/lib/cmake/mlir','-DNEX_Z3_ROOT=/opt/z3'])
        run('build',['cmake','--build','/build','-j',str(args.jobs)])
        run('ctest',['ctest','--test-dir','/build','--output-on-failure','-j',str(args.jobs)])
        text=(root/'Testing/Temporary/LastTest.log').read_text()
        report['case_counts']=[int(n) for n in re.findall(r'Ran (\d+) tests? in ',text)]
        report['skips']=re.findall(r"\.\.\. skipped ['\"]([^'\"]+)",text)
        run('install',['cmake','--install','/build','--prefix','/build/sdk'])
        run('sdk',['python3','/src/tools/linux/sdk_smoke.py','/build/sdk'])
        report['sdk']=json.loads((root/'sdk-smoke.json').read_text())
        if args.live:
            for suite in ('debugging','expressions','generics','constraints','matching','function_debug','bytes_debug','numbers','incremental'):
                run('live-'+suite,['python3','/src/tests/'+suite+'.py','/build/sdk/bin/nex','--live'])
        report['doctor']=json.loads(subprocess.check_output(['/build/sdk/bin/nex','doctor']))
        report['compiler_sha256']=hashlib.sha256((root/'nex').read_bytes()).hexdigest()
        report['sdk_compiler_sha256']=hashlib.sha256((root/'sdk/bin/nex').read_bytes()).hexdigest()
        report['packages']=subprocess.check_output(['dpkg-query','-W','-f=${Package}\t${Version}\n'],text=True).splitlines()
        report['ok']=True
    finally:
        report['seconds']=round(time.monotonic()-started,3);save()
    # Keep completed evidence when the rolling build directory is reused.
    checkpoint=root/'checkpoints'/report['doctor']['version']
    try:
        checkpoint.mkdir(parents=True,exist_ok=True)
        for name in ['verification.json','environment.json','sdk-smoke.json',*[p['name']+'.log' for p in report['phases']]]:
            if (root/name).is_file():shutil.copyfile(root/name,checkpoint/name)
        shutil.copyfile(root/'Testing/Temporary/LastTest.log',checkpoint/'LastTest.log')
    except OSError as error:
        report.update(ok=False,checkpoint_error=str(error));save();raise
    print(json.dumps({'ok':True,'cases':sum(report['case_counts']),'skips':report['skips'],'seconds':report['seconds'],'host':report['doctor']['host']}),flush=True)


if __name__=='__main__':main()
