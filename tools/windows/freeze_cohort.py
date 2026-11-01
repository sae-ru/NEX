"""Freeze a native Windows build and its resource inputs for verify_native.py."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,default=Path('build/windows-host'))
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    root=Path(__file__).resolve().parents[2]
    build=args.build.resolve(strict=True);out=args.output.resolve()
    if not (build/'nex.exe').is_file() or not (build/'CTestTestfile.cmake').is_file():
        parser.error('--build must contain a complete native Windows CMake build')
    if out.exists():parser.error('--output must be a new directory')
    tests=(build/'CTestTestfile.cmake').read_bytes().decode('utf-8')
    if build.as_posix() not in tests:parser.error('CTest paths do not name the selected build')
    out.mkdir(parents=True);resource=out/'resources';resource.mkdir();pins={}
    def copy(source,destination):
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,destination)
        pins[destination.relative_to(out).as_posix()]=hashlib.sha256(destination.read_bytes()).hexdigest()
    for source in sorted(build.iterdir()):
        if source.is_file() and (source.suffix in ('.exe','.dll') or source.name.endswith('.dll.a')):
            copy(source,out/source.name)
    fixtures=build/'typed-resource-fixtures'
    if fixtures.is_dir():
        for path in sorted(fixtures.rglob('*')):
            if path.is_file():copy(path,out/path.relative_to(build))
    names=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=root).decode('utf-8').split('\0')
    folders={'runtime','web','lib','docs','llm','tools','debug','editor','examples','experiments'}
    for name in sorted(set(names)):
        path=Path(name)
        if name and (path.parts[0] in folders or name in ('LICENSE','README.md','README.ru.md','PLAN.md','AGENTS.md')) and (root/path).is_file():
            copy(root/path,resource/path)
    target=out/'CTestTestfile.cmake'
    target.write_bytes(tests.replace(build.as_posix(),out.as_posix()).encode('utf-8'))
    pins[target.name]=hashlib.sha256(target.read_bytes()).hexdigest()
    record={'schema':'nex.windows-test-cohort/1','build':str(build),'compiler_sha256':pins['nex.exe'],'resource_root':str(resource),'sha256':pins}
    (out/'cohort.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(out),'files':len(pins),'compiler_sha256':pins['nex.exe']},ensure_ascii=False))


if __name__=='__main__':main()
