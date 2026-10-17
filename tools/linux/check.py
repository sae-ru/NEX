#!/usr/bin/env python3
"""Build the pinned Linux environment, then verify NEX without external network."""
import argparse
import json
from pathlib import Path
import platform
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output',type=Path)
    parser.add_argument('--arch',choices=('arm64','amd64'),default='arm64' if platform.machine() in ('arm64','aarch64') else 'amd64')
    parser.add_argument('--jobs',type=int,default=2)
    parser.add_argument('--skip-image-build',action='store_true')
    parser.add_argument('--live',action='store_true',help='Also run real LLDB/DAP tests; requires native ptrace support')
    args=parser.parse_args()
    source=args.source.resolve();output=(args.output or source/'build'/('linux-'+args.arch)).resolve()
    if not (source/'CMakeLists.txt').is_file():parser.error('--source must name a NEX source checkout')
    if not 1<=args.jobs<=8:parser.error('--jobs must be 1..8')
    output.mkdir(parents=True,exist_ok=True);image='nex-linux-toolchain:'+args.arch
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
    print(json.dumps({'ok':True,'directory':str(output),**metadata},indent=2))


if __name__=='__main__':main()
