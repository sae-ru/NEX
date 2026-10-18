#!/usr/bin/env python3
"""Build the pinned Linux environment, then verify NEX without external network."""
import argparse
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time
import uuid


def verify_installed_sdk(output,image,arch,live=False):
    # A second container sees only the installed SDK and a new evidence directory.
    # The earlier /src mount cannot accidentally satisfy missing SDK resources.
    verification=output/'verification.json'
    report=json.loads(verification.read_text())
    if not report['ok']:raise RuntimeError('source verification did not pass')
    evidence=output/'sdk-acceptance'/uuid.uuid4().hex
    evidence.mkdir(parents=True)
    isolated=['docker','run','--rm','--platform','linux/'+arch,'--network','none',
        '--mount','type=bind,src='+str(output/'sdk')+',dst=/sdk,readonly',
        '--mount','type=bind,src='+str(evidence)+',dst=/evidence','--workdir','/tmp']
    if live:isolated+=['--cap-add=SYS_PTRACE','--security-opt','seccomp=unconfined']
    isolated += [image,'python3','/sdk/share/nex/tools/sdk_acceptance.py','/sdk',
                 '--output','/evidence/workflow','--forbid-source','/src','--browser']
    if live:isolated.append('--live')
    phase={'name':'source-free-sdk','command':isolated,'status':'running'}
    report['phases'].append(phase);report['ok']=False
    def save():verification.write_text(json.dumps(report,indent=2)+'\n')
    save();started=time.monotonic()
    try:
        with (output/'source-free-sdk.log').open('w') as log:
            result=subprocess.run(isolated,stdout=log,stderr=subprocess.STDOUT)
        phase['exit_code']=result.returncode
        if result.returncode:raise RuntimeError('source-free SDK failed; inspect '+str(evidence/'workflow/report.json'))
        accepted=json.loads((evidence/'workflow/report.json').read_text())
        if not accepted['ok'] or accepted['compiler_sha256']!=report['sdk_compiler_sha256'] or any(accepted['doctor'][key]!=report['doctor'][key] for key in ('host','language','version','llvm','verifier_version','native_compiler')):
            raise RuntimeError('source-free SDK differs from the verified compiler')
        shutil.copyfile(evidence/'workflow/report.json',output/'source-free-sdk.json')
        report['source_free_sdk']={'ok':True,'report':str(evidence/'workflow/report.json'),
            'compiler_sha256':accepted['compiler_sha256'],'source_checkout_mounted':False,
            'network':'none','live_debugger':live,'browser_build':True,'seconds':accepted['seconds']}
        phase['status']='passed';report['ok']=True
    except BaseException as error:
        phase.update(status='failed',error=str(error));raise
    finally:
        report['seconds']+=round(time.monotonic()-started,3);save()
    checkpoint=output/'checkpoints'/report['doctor']['version']
    try:
        checkpoint.mkdir(parents=True,exist_ok=True)
        for name in ('verification.json','environment.json','source-free-sdk.json','source-free-sdk.log'):
            shutil.copyfile(output/name,checkpoint/name)
    except OSError as error:
        report.update(ok=False,checkpoint_error=str(error));save();raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--arch',choices=('arm64','amd64'),default='arm64' if platform.machine() in ('arm64','aarch64') else 'amd64')
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--skip-image-build',action='store_true')
    parser.add_argument('--image',help='Explicit toolchain image/tag; recorded with its immutable image ID')
    parser.add_argument('--live',action='store_true',help='Also run real LLDB/DAP tests; requires native ptrace support')
    args=parser.parse_args()
    source=args.source.resolve();output=(args.output or source/'build'/('linux-'+args.arch)).resolve()
    if not (source/'CMakeLists.txt').is_file():parser.error('--source must name a NEX source checkout')
    if not 1<=args.jobs<=8:parser.error('--jobs must be 1..8')
    output.mkdir(parents=True,exist_ok=True);image=args.image or 'nex-linux-toolchain:'+args.arch
    if not args.skip_image_build:
        with (output/'image.log').open('w') as log:
            subprocess.run(['docker','build','--platform','linux/'+args.arch,'--progress','plain','-f',str(source/'tools/linux/Dockerfile'),'-t',image,str(source)],stdout=log,stderr=subprocess.STDOUT,check=True)
    inspected=json.loads(subprocess.check_output(['docker','image','inspect',image]))[0]
    if inspected['Architecture']!=args.arch:raise RuntimeError('toolchain image architecture differs from selection')
    server=json.loads(subprocess.check_output(['docker','version','--format','{{json .Server}}']))
    metadata={'image':image,'image_id':inspected['Id'],'target_arch':args.arch,'docker_server_arch':server['Arch'],'emulated':server['Arch']!=args.arch}
    (output/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
    command=['docker','run','--rm','--platform','linux/'+args.arch,'--network','none',
        '--mount','type=bind,src='+str(source)+',dst=/src,readonly','--mount','type=bind,src='+str(output)+',dst=/build','--workdir','/build']
    if args.live:command+=['--cap-add=SYS_PTRACE','--security-opt','seccomp=unconfined']
    command += [image,'python3','/src/tools/linux/verify.py','--jobs',str(args.jobs)]
    if args.live:command.append('--live')
    subprocess.run(command,check=True)
    verify_installed_sdk(output,image,args.arch,args.live)
    print(json.dumps({'ok':True,'directory':str(output),**metadata},indent=2))


if __name__=='__main__':main()
