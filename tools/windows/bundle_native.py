"""Copy the measured native PE DLL closure beside a local Windows executable."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable',type=Path)
    parser.add_argument('--dependencies',type=Path,required=True)
    parser.add_argument('--readobj',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    if os.name!='nt':parser.error('run this with native Windows Python')
    executable=args.executable.resolve(strict=True);folder=executable.parent
    available={p.name.casefold():p for p in args.dependencies.resolve().glob('*.dll')}
    system=Path(os.environ['SystemRoot'])/'System32'
    pending=[executable];visited=set();records=[];system_imports=set()
    while pending:
        source=pending.pop();key=source.name.casefold()
        if key in visited:continue
        visited.add(key)
        result=subprocess.run([str(args.readobj),'--file-headers','--coff-imports',str(source)],capture_output=True,text=True,check=True)
        if 'IMAGE_FILE_MACHINE_AMD64' not in result.stdout:raise RuntimeError('expected native x64 PE: '+str(source))
        imports=sorted(set(re.findall(r'^\s*Name:\s+(\S+\.dll)\s*$',result.stdout,re.M|re.I)))
        for name in imports:
            lower=name.casefold()
            if lower in ('msys-2.0.dll','cygwin1.dll'):raise RuntimeError('non-native execution dependency: '+name)
            if lower in available:pending.append(available[lower])
            elif lower.startswith(('api-ms-win-','ext-ms-win-')) or (system/name).is_file():system_imports.add(name)
            else:raise RuntimeError('unresolved native DLL: '+name+' from '+source.name)
        destination=folder/source.name
        if source!=destination:
            if not destination.exists() or sha(source)!=sha(destination):shutil.copy2(source,destination)
        records.append({'file':source.name,'source':str(source),'destination':str(destination),
                        'sha256':sha(source),'imports':imports})
    report={'schema':'nex.windows-native-dll-closure/1','ok':True,'requires_WSL':False,'requires_MSYS_runtime':False,
            'executable_sha256':sha(executable),'files':records,'system_imports':sorted(system_imports)}
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':True,'files':len(records),'report':str(args.report)}))


if __name__=='__main__':main()
