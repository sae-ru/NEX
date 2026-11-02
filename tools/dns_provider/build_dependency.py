#!/usr/bin/env python3
"""Build the pinned public c-ares static PIC dependency in a new local folder."""
import argparse
import hashlib
import json
import platform
import re
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import urllib.request

VERSION='1.34.9'
URL='https://github.com/c-ares/c-ares/releases/download/v1.34.9/c-ares-1.34.9.tar.gz'
SHA256='9364b70a12eb59a06830fb488d9357f90100dff0d98b23ea3593a183d43e6f2f'
ARCHIVE_BYTES=1083895
MAC_PATCH_SHA256='908c595efdeba68c8abb40ef81c0fe3f36c07ef4c5b3c895dbf82bd99ddd0d24'
MAC_PATCH_FILE='patches/c-ares-macos-unaligned-v1.json'

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda:source.read(1048576),b''):h.update(block)
    return h.hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--archive',type=Path,help='Use these exact verified release bytes without network')
    parser.add_argument('--jobs',type=int,default=4)
    parser.add_argument('--cc',type=Path,help='Explicit matching C compiler; required on Windows')
    parser.add_argument('--generator',help='CMake generator; Windows defaults to Ninja')
    args=parser.parse_args()
    if not 1<=args.jobs<=8:parser.error('jobs must be1..8')
    cc=args.cc.resolve(strict=True) if args.cc else None
    if platform.system()=='Windows' and cc is None:parser.error('Windows requires --cc with the matching LLVM-MinGW clang.exe')
    out=args.output.absolute()
    if out.exists() or out.is_symlink():parser.error('output must be a new directory')
    out.mkdir(parents=True);report={'schema':'nex.cares-dependency/1','ok':False,'version':VERSION,'archive_url':URL,'archive_sha256':SHA256,'commands':[],'network_used':args.archive is None,'upstream_tests_run':False,'PGP_signature_verified':False}
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(label,argv):
        argv=list(map(str,argv));row={'label':label,'argv':argv,'state':'running'};report['commands'].append(row);save()
        with (out/(label+'.stdout')).open('w') as stdout,(out/(label+'.stderr')).open('w') as stderr:
            p=subprocess.run(argv,stdout=stdout,stderr=stderr,timeout=1800)
        row.update(exit_code=p.returncode,state='passed' if p.returncode==0 else 'failed');save()
        if p.returncode:raise RuntimeError(label+' failed; inspect retained logs')
    try:
        archive=out/('c-ares-'+VERSION+'.tar.gz')
        if args.archive:
            if args.archive.stat().st_size!=ARCHIVE_BYTES or sha(args.archive)!=SHA256:raise ValueError('release archive bytes/hash differ')
            shutil.copyfile(args.archive,archive)
        else:
            request=urllib.request.Request(URL,headers={'User-Agent':'NEX-public-dependency-builder'})
            with urllib.request.urlopen(request,timeout=60) as response,archive.open('xb') as target:
                total=0
                while True:
                    block=response.read(65536)
                    if not block:break
                    total+=len(block)
                    if total>ARCHIVE_BYTES:raise ValueError('release archive exceeds its pinned size')
                    target.write(block)
        if archive.stat().st_size!=ARCHIVE_BYTES or sha(archive)!=SHA256:raise ValueError('release archive bytes/hash differ')
        source=out/('c-ares-'+VERSION);files={};total=0
        with tarfile.open(archive,'r:gz') as tar:
            for member in tar:
                name=PurePosixPath(member.name)
                if name.is_absolute() or '..' in name.parts or not name.parts or name.parts[0]!=source.name:raise ValueError('unsafe release member')
                target=out/name
                if member.isdir():target.mkdir(parents=True,exist_ok=True);continue
                if not member.isfile() or member.mode&0o7000:raise ValueError('release contains unsupported link/special member')
                relative=str(name.relative_to(source.name))
                if relative in files or len(files)>=8192:raise ValueError('duplicate/too many release files')
                total+=member.size
                if total>64*1024*1024:raise ValueError('release expands beyond64MiB')
                target.parent.mkdir(parents=True,exist_ok=True)
                with tar.extractfile(member) as original,target.open('xb') as output:shutil.copyfileobj(original,output)
                target.chmod(0o755 if member.mode&0o111 else 0o644)
                files[relative]={'sha256':sha(target),'bytes':target.stat().st_size}
        header=(source/'include/ares_version.h').read_text()
        if not re.search(r'^#define\s+ARES_VERSION_STR\s+"'+re.escape(VERSION)+r'"\s*$',header,re.M):raise ValueError('source version differs')
        (out/'source-manifest.json').write_text(json.dumps({'schema':'nex.cares-source/1','archive_sha256':SHA256,'files':files},indent=2)+'\n')
        patches=[]
        if platform.system()=='Darwin':
            patchfile=Path(__file__).resolve().parent/MAC_PATCH_FILE
            if sha(patchfile)!=MAC_PATCH_SHA256:raise ValueError('macOS c-ares alignment patch identity differs')
            patch=json.loads(patchfile.read_text());target=source/patch['path']
            if sha(target)!=patch['original_sha256']:raise ValueError('macOS patch source differs from the pinned release')
            text=target.read_text()
            for old,new in patch['replacements']:
                if text.count(old)!=1:raise ValueError('macOS pointer-copy patch does not apply exactly')
                text=text.replace(old,new,1)
            target.write_text(text)
            if sha(target)!=patch['patched_sha256']:raise ValueError('macOS patched source identity differs')
            patches=[{'patch_sha256':MAC_PATCH_SHA256,'document':patch}]
        effective=dict(files)
        for row in patches:
            target=source/row['document']['path'];effective[row['document']['path']]={'sha256':sha(target),'bytes':target.stat().st_size}
        (out/'effective-source-manifest.json').write_text(json.dumps({'schema':'nex.cares-effective-source/1','archive_sha256':SHA256,'local_source_patches':patches,'files':effective},indent=2)+'\n')
        prefix=out/'prefix';build=out/'build'
        configure=['cmake','-S',source,'-B',build,'-DCMAKE_BUILD_TYPE=Release','-DCMAKE_INSTALL_PREFIX='+prefix.as_posix(),'-DCMAKE_INSTALL_LIBDIR=lib','-DCARES_STATIC=ON','-DCARES_SHARED=OFF','-DCARES_STATIC_PIC=ON','-DCARES_BUILD_TOOLS=OFF','-DCARES_BUILD_TESTS=OFF','-DCARES_INSTALL=ON']
        if cc:configure+=['-DCMAKE_C_COMPILER='+cc.as_posix()]
        generator=args.generator or ('Ninja' if platform.system()=='Windows' else None)
        if generator:configure+=['-G',generator]
        run('configure',configure)
        run('build',['cmake','--build',build,'--config','Release','-j',str(args.jobs)])
        run('install',['cmake','--install',build,'--config','Release'])
        license=source/'LICENSE.md'
        if not license.is_file():license=source/'COPYING'
        if not license.is_file():raise ValueError('release has no complete project license')
        notices=prefix/'share/licenses/c-ares';notices.mkdir(parents=True,exist_ok=True);shutil.copyfile(license,notices/'LICENSE.txt')
        record={'schema':'nex.cares-install/1','version':VERSION,'url':URL,'archive_sha256':SHA256,'license':'share/licenses/c-ares/LICENSE.txt','license_sha256':sha(notices/'LICENSE.txt'),'headers':{p.name:sha(p) for p in (prefix/'include').glob('ares*.h')},'static_library':'lib/libcares.a','static_library_sha256':sha(prefix/'lib/libcares.a'),'static_PIC':True,'upstream_source_manifest_sha256':sha(out/'source-manifest.json'),'effective_source_manifest_sha256':sha(out/'effective-source-manifest.json'),'local_source_patches':patches,'build_configuration':{'system':platform.system(),'machine':platform.machine(),'C_compiler':str(cc) if cc else None,'configure':list(map(str,configure))}}
        (prefix/'share/cares-source.json').write_text(json.dumps(record,indent=2)+'\n')
        report.update(ok=True,prefix=str(prefix),source_files=len(files),source_bytes=total,static_library_sha256=record['static_library_sha256'],complete_license_sha256=record['license_sha256'])
    except BaseException as error:report['error']=repr(error);raise
    finally:save()
    print(json.dumps({k:report[k] for k in ('ok','version','prefix','source_files','static_library_sha256')}))

if __name__=='__main__':main()
