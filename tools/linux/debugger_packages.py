"""Fetch/cache the exact public LLDB packages independently of a rolling index."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time
import urllib.request

NAMES={"lldb-23","python3-lldb-23","liblldb-23","libllvm23","libclang-cpp23"}


def selected(lock,arch):
    if lock.get("schema")!="nex.linux-debugger-packages/1" or arch not in ("amd64","arm64"):
        raise ValueError("unsupported debugger package lock/architecture")
    if lock.get("repository")!="https://apt.llvm.org/noble/":raise ValueError("unexpected debugger repository")
    packages=lock["packages"][arch]
    if set(packages)!=NAMES:raise ValueError("debugger package inventory differs")
    for entry in packages.values():
        name=entry["Filename"]
        if (not name.startswith("pool/main/l/llvm-toolchain-23/") or
            not re.fullmatch(r"[A-Za-z0-9_.+~-]+\.deb",Path(name).name) or
            entry["Architecture"]!=arch or entry["Version"]!=lock["apt_version"] or
            not re.fullmatch(r"[0-9a-f]{64}",entry["SHA256"]) or not 0<int(entry["Size"])<256*1024*1024):
            raise ValueError("invalid debugger package record")
    return packages


def matches(path,entry):
    if not path.is_file() or path.stat().st_size!=int(entry["Size"]):return False
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while chunk:=stream.read(1024*1024):digest.update(chunk)
    return digest.hexdigest()==entry["SHA256"]


def prepare(lock,cache,arch,*,opener=urllib.request.urlopen,fetch=True):
    packages=selected(lock,arch);directory=Path(cache)/arch
    if fetch:directory.mkdir(parents=True,exist_ok=True)
    rows=[]
    for name,entry in sorted(packages.items()):
        path=directory/Path(entry["Filename"]).name;cached=matches(path,entry)
        if not cached:
            if not fetch:raise ValueError("missing or differing pinned debugger package: "+name)
            url=lock["repository"]+entry["Filename"]
            temporary=None
            try:
                with tempfile.NamedTemporaryFile(prefix=".lldb-",dir=directory,delete=False) as stream:
                    temporary=Path(stream.name)
                    for attempt in range(3):
                        try:
                            stream.seek(0);stream.truncate();size=0
                            with opener(url,timeout=30) as response:
                                while chunk:=response.read(1024*1024):
                                    size+=len(chunk)
                                    if size>int(entry["Size"]):raise ValueError("debugger package exceeds locked size")
                                    stream.write(chunk)
                            break
                        except OSError:
                            if attempt==2:raise
                            time.sleep(attempt+1)
                if not matches(temporary,entry):raise ValueError("download differs from debugger package lock: "+name)
                # Public package bytes must remain readable by the host cache
                # action after the full workflow's root-owned preparation.
                temporary.chmod(0o644);os.replace(temporary,path)
            finally:
                if temporary is not None:temporary.unlink(missing_ok=True)
        rows.append({"package":name,"path":str(path.resolve()),"sha256":entry["SHA256"],"bytes":int(entry["Size"]),"cached":cached})
    return {"schema":"nex.debugger-package-cache/1","ok":True,"architecture":arch,"apt_version":lock["apt_version"],"packages":rows}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock",type=Path,default=Path(__file__).with_name("debugger-packages.json"))
    parser.add_argument("--cache",type=Path,required=True)
    parser.add_argument("--arch",choices=("amd64","arm64"),required=True)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--install",action="store_true",help="verify supplied packages and install exact files; never fetch")
    parser.add_argument("--expected-version")
    args=parser.parse_args();raw=args.lock.read_bytes();lock=json.loads(raw)
    if args.expected_version and args.expected_version!=lock["apt_version"]:raise ValueError("Docker and debugger lock versions differ")
    report=prepare(lock,args.cache,args.arch,fetch=not args.install)
    report["lock_sha256"]=hashlib.sha256(raw).hexdigest()
    if args.output:args.output.write_text(json.dumps(report,indent=2)+"\n")
    print(json.dumps(report),flush=True)
    if args.install:subprocess.run(["apt-get","install","-y","--no-install-recommends",*[entry["path"]for entry in report["packages"]]],check=True)


if __name__=="__main__":main()
