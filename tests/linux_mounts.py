#!/usr/bin/env python3
"""Actual Docker bind-path and kernel isolation regression; requires a local image."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
sys.dont_write_bytecode=True

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args=parser.parse_args();root=args.output.resolve()
    if root.exists():parser.error('--output must be a new directory')
    root.mkdir(parents=True);source=Path(__file__).resolve().parents[1]
    sys.path.insert(0,str(source/'tools/linux'))
    from nex_docker_mount import mount
    image=json.loads(subprocess.check_output(['docker','image','inspect',args.image]))[0]
    pinned=image['Id'];started=time.monotonic();commands=[];cases=[]
    def run(label,command,success=True):
        p=subprocess.run(command,capture_output=True,text=True,timeout=60)
        (root/(label+'.stdout')).write_text(p.stdout, newline="\n");(root/(label+'.stderr')).write_text(p.stderr, newline="\n")
        commands.append({'name':label,'command':command,'exit_code':p.returncode})
        if (p.returncode==0)!=success:raise RuntimeError(label+': '+p.stdout+p.stderr)
        return p
    program="""import errno,hashlib,json,pathlib,runpy,socket,sys
src=pathlib.Path('/source');out=pathlib.Path('/evidence')
assert hashlib.sha256((src/'input.bin').read_bytes()).hexdigest()==sys.argv[1]
try:(src/'must-not-write').write_bytes(b'forbidden')
except OSError as error:
 assert error.errno in (errno.EROFS,errno.EACCES),str(error)
else:raise RuntimeError('readonly source became writable')
interfaces=sorted(p.name for p in pathlib.Path('/sys/class/net').iterdir())
# Docker's VM can expose inactive tunnel entries through sysfs; test routing.
with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as connection:
 connection.settimeout(1)
 try:connection.connect(('192.0.2.1',443))
 except OSError as error:assert error.errno==errno.ENETUNREACH,str(error)
 else:raise RuntimeError('unexpected outbound route')
probe=runpy.run_path(str(src/'verify.py'))['check_scratch_filesystem']
scratch=probe()
assert scratch['raw_filename_roundtrip'] and scratch['directory']=='/tmp'
try:probe(src)
except RuntimeError as error:
 assert 'Linux checks require a writable scratch filesystem' in str(error)
 assert 'container-native /tmp' in str(error)
else:raise RuntimeError('readonly scratch passed the preflight')
(out/'probe.json').write_text(json.dumps({'ok':True,'source_readonly':True,'evidence_writable':True,'outbound_route_absent':True,'network_interfaces':interfaces,'native_scratch':scratch,'readonly_scratch_rejected':True}))
"""
    names=[('source,readonly=false,"quoted" \\ % 🧠','evidence, "quoted" \\ % 🧠'),
           ('source\nnewline 🌍','evidence\nnewline 🌍')]
    for index,(srcname,outname) in enumerate(names):
        src=root/srcname;out=root/outname;src.mkdir();out.mkdir()
        (src/'verify.py').write_bytes((source/'tools/linux/verify.py').read_bytes())
        payload=b'NEX'+bytes([0,255])+('Я🧠\r\n').encode();(src/'input.bin').write_bytes(payload)
        digest=hashlib.sha256(payload).hexdigest()
        command=['docker','run','--rm','--platform','linux/'+image['Architecture'],'--network','none',
                 '--env','TMPDIR=/tmp',*mount(src,'/source'),*mount(out,'/evidence',readonly=False),pinned,
                 'python3','-c',program,digest]
        run('case-'+str(index),command)
        observed=json.loads((out/'probe.json').read_text())
        assert observed['ok'] and observed['source_readonly'] and observed['evidence_writable']
        assert {p.name for p in src.iterdir()}=={'input.bin','verify.py'} and (src/'input.bin').read_bytes()==payload
        assert (src/'verify.py').read_bytes()==(source/'tools/linux/verify.py').read_bytes()
        legacy=['docker','run','--rm','--platform','linux/'+image['Architecture'],'--network','none',
                '--mount','type=bind,src='+str(src)+',dst=/source,readonly',pinned,'true']
        rejected=run('legacy-'+str(index),legacy,success=False)
        if index==0:assert 'invalid argument' in rejected.stderr and '--mount' in rejected.stderr
        else:assert 'invalid mount config' in rejected.stderr and 'Target must not be empty' in rejected.stderr
        cases.append({'case':index,'source_path':str(src),'evidence_path':str(out),
                      'payload_sha256':digest,'observed':observed,'source_files_unchanged':True,
                      'legacy_raw_field_rejected':True})
    proof={'ok':True,'scope':'actual Docker CSV paths, payload identity and kernel readonly/evidence-write/network-none controls; no compiler/full-SDK acceptance claim',
           'image_id':pinned,'architecture':image['Architecture'],'helper_sha256':hashlib.sha256((source/'tools/linux/nex_docker_mount.py').read_bytes()).hexdigest(),
           'cases':cases,'commands':commands,'seconds':round(time.monotonic()-started,3)}
    (root/'report.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n', newline="\n")
    print(json.dumps({'ok':True,'cases':len(cases),'seconds':proof['seconds']}))

if __name__=='__main__':main()
