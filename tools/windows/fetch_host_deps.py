"""Install signature-checked native CLANG64 dependencies into a local prefix.

Uses Windows Python 3.14, curl and Git for Windows gpgv. No MSYS shell or WSL
runtime is installed. LLVM/MLIR and the C++ library retain their22.1.8 cohort.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor

ROOT=Path(__file__).resolve().parents[2]
PREFIX='mingw-w64-clang-x86_64-'
MIRROR='https://mirror.yandex.ru/mirrors/msys2/mingw/clang64/'
COHORT={name:'22.1.8-3' for name in ('llvm','llvm-libs','llvm-tools','clang','clang-libs','compiler-rt','lld')}
COHORT.update({name:'22.1.8-1' for name in ('mlir','libc++','libunwind')})


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def database(path):
    result={};provides={}
    with tarfile.open(path) as archive:
        for member in archive:
            if not member.name.endswith('/desc'):continue
            text=archive.extractfile(member).read().decode()
            fields={key:value.strip().splitlines() for key,value in re.findall(r'%([^%]+)%\n(.*?)(?=\n%|\Z)',text,re.S)}
            name=fields['NAME'][0];result[name]=fields
            for value in fields.get('PROVIDES',[]):provides[re.split('[<>=]',value)[0]]=name
    return result,provides


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',type=Path,required=True)
    parser.add_argument('--keyring',type=Path,required=True)
    parser.add_argument('--gpgv',type=Path,default=Path('C:/Program Files/Git/usr/bin/gpgv.exe'))
    parser.add_argument('--prefix',type=Path,default=ROOT/'build/deps/windows-host')
    parser.add_argument('--lock-output',type=Path,default=ROOT/'tools/windows/host-dependencies.lock.json')
    args=parser.parse_args();cache=ROOT/'build/deps/host-packages';cache.mkdir(parents=True,exist_ok=True)
    home=cache/'gpgv-home';home.mkdir(exist_ok=True)
    subprocess.run([str(args.gpgv.with_name('gpg.exe')),'--homedir',str(home),'--batch','--yes',
                    '--dearmor','--output',str(home/'msys2.gpg'),str(args.keyring)],check=True)
    index,providers=database(args.database)
    selected={};records={}

    def download(name):
        if name in records:return records[name]
        if name.startswith(PREFIX) and name[len(PREFIX):] in COHORT:
            version=COHORT[name[len(PREFIX):]];filename=name+'-'+version+'-any.pkg.tar.zst';expected=None
        else:
            fields=index[name];version=fields['VERSION'][0];filename=fields['FILENAME'][0];expected=fields['SHA256SUM'][0]
        assert '/' not in filename and '\\' not in filename
        path=cache/filename
        def fetch(url,destination):
            partial=destination.with_name(destination.name+'.part')
            subprocess.run(['curl.exe','-fL','--silent','--show-error','--connect-timeout','15','--max-time','300',
                            '--retry','2',url,'-o',str(partial)],check=True)
            partial.replace(destination)
        if not path.exists():fetch(MIRROR+filename,path)
        actual=sha(path)
        if expected and actual!=expected:raise RuntimeError('package SHA-256 mismatch: '+filename)
        signature=path.with_name(filename+'.sig')
        if not signature.exists():fetch(MIRROR+filename+'.sig',signature)
        checked=subprocess.run([str(args.gpgv),'--homedir',str(home),'--keyring','msys2.gpg',
                                '--status-fd','1',str(signature),str(path)],capture_output=True)
        (cache/(filename+'.verification.log')).write_bytes(checked.stdout+checked.stderr)
        if checked.returncode:raise RuntimeError('package signature verification failed: '+filename+'\n'+checked.stderr.decode(errors='replace'))
        fingerprints=re.findall(rb'\[GNUPG:\] VALIDSIG ([0-9A-F]+)',checked.stdout)
        if not fingerprints:raise RuntimeError('no valid package signature: '+filename)
        with tarfile.open(path) as archive:
            metadata=archive.extractfile('.PKGINFO').read().decode()
        package={}
        for line in metadata.splitlines():
            if ' = ' in line:
                key,value=line.split(' = ',1);package.setdefault(key,[]).append(value)
        if package['pkgname']!=[name] or package['pkgver']!=[version]:raise RuntimeError('package identity differs: '+filename)
        print('Verified '+filename,flush=True)
        return {'name':name,'version':version,'file':filename,'url':MIRROR+filename,'sha256':actual,
                'signature_sha256':sha(signature),'signer_fingerprints':[f.decode() for f in fingerprints],
                'dependencies':package.get('depend',[])}

    pending={PREFIX+name for name in (*COHORT,'openssl','sqlite3','z3','ninja')}
    while pending:
        names=sorted(pending-records.keys());pending=set()
        if not names:break
        with ThreadPoolExecutor(max_workers=4) as pool:
            for name,record in zip(names,pool.map(download,names)):
                records[name]=record
                for dependency in record['dependencies']:
                    dependency=re.split('[<>=]',dependency)[0]
                    if dependency==PREFIX+'cc-libs':dependency=PREFIX+'libc++'
                    if dependency==PREFIX+'cc':dependency=PREFIX+'clang'
                    if dependency not in index and dependency not in records:dependency=providers.get(dependency,dependency)
                    if not dependency.startswith(PREFIX):raise RuntimeError('non-native dependency: '+dependency)
                    if dependency not in records:pending.add(dependency)
    args.prefix.mkdir(parents=True,exist_ok=True)
    for name,record in sorted(records.items()):
        with tarfile.open(cache/record['file']) as archive:
            members=[member for member in archive if member.name.startswith('clang64/')]
            archive.extractall(args.prefix,members=members,filter='data')
        print('Extracted '+name,flush=True)
    lock={'schema':'nex.windows-host-dependencies/1','environment':'native Windows CLANG64/UCRT; no MSYS or WSL runtime',
          'keyring_source':'https://github.com/msys2/MSYS2-keyring/blob/master/msys2.gpg',
          'keyring_sha256':sha(args.keyring),'database_sha256':sha(args.database),'packages':list(records.values())}
    args.lock_output.write_bytes((json.dumps(lock,indent=2)+'\n').encode('utf-8'))
    print('Installed native Windows dependencies at '+str(args.prefix/'clang64'),flush=True)


if __name__=='__main__':main()
