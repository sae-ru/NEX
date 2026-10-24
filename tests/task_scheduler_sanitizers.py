"""Opt-in strict sanitizer checks for the private task runtime, from a source checkout."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import traceback


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cxx',default='clang++',help='Actual C++20 compiler executable; no shell arguments')
    parser.add_argument('--sanitizer',choices=['address,undefined','thread'],required=True)
    parser.add_argument('--output',type=Path,required=True,help='New or empty directory; previous evidence is preserved')
    parser.add_argument('--repeats',type=int,default=3)
    args=parser.parse_args()
    if not 1<=args.repeats<=100:parser.error('--repeats must be1..100')
    # Preserve argv[0]: resolving clang++ to clang changes C++ linker mode.
    compiler=Path(shutil.which(args.cxx) or args.cxx).absolute()
    if not compiler.is_file():parser.error('C++ compiler executable not found')
    source=Path(__file__).resolve().parents[1];out=args.output.resolve()
    if out.exists() and (not out.is_dir() or any(out.iterdir())):parser.error('--output must be new or empty')
    out.mkdir(parents=True,exist_ok=True)
    inputs=[p for p in (source/'runtime').rglob('*') if p.is_file()]
    inputs.append(source/'tests/task_scheduler.cpp')
    inputs.append(Path(__file__).resolve())
    hashes={str(p.relative_to(source)):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    started=time.monotonic();state=out/'report.json'
    report={'schema':'nex.task-runtime-sanitizers/1','ok':False,'source_async':False,
            'source':str(source),'sanitizer':args.sanitizer,'compiler':str(compiler),
            'inputs':hashes,'commands':[],'full_objective_complete':False}
    def save():
        report['seconds']=round(time.monotonic()-started,3)
        state.write_text(json.dumps(report,indent=2)+'\n')
    def guard():
        for name,digest in hashes.items():
            if hashlib.sha256((source/name).read_bytes()).hexdigest()!=digest:
                raise RuntimeError('Runtime input changed during verification: '+name)
    settings=({'ASAN_OPTIONS':'detect_leaks=1:halt_on_error=1','UBSAN_OPTIONS':'halt_on_error=1'}
              if args.sanitizer=='address,undefined' else {'TSAN_OPTIONS':'halt_on_error=1'})
    def run(name,command,timeout):
        guard();begin=time.monotonic()
        result=subprocess.run(list(map(str,command)),cwd=out,env={**os.environ,**settings},
                              capture_output=True,text=True,timeout=timeout)
        (out/(name+'.stdout')).write_text(result.stdout)
        (out/(name+'.stderr')).write_text(result.stderr)
        report['commands'].append({'name':name,'command':list(map(str,command)),
            'exit_code':result.returncode,'seconds':round(time.monotonic()-begin,3)})
        save();guard()
        if result.returncode:raise RuntimeError(name+' failed; inspect retained stdout/stderr')
        return result.stdout
    try:
        save();report['compiler_version']=run('compiler',[compiler,'--version'],30)
        binary=out/'task-runtime-probe'
        run('compile',[compiler,'-std=c++20','-O1','-g','-fno-omit-frame-pointer','-pthread',
            '-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_PROFILE_ENABLED',
            '-I',source/'runtime',source/'tests/task_scheduler.cpp',source/'runtime/runtime.cpp',
            source/'runtime/nex_files.cpp',source/'runtime/nex_task_external.cpp',source/'runtime/nex_resource_region.cpp','-fsanitize='+args.sanitizer,'-o',binary],300)
        report['binary_sha256']=hashlib.sha256(binary.read_bytes()).hexdigest()
        report['observations']=[]
        for index in range(args.repeats):
            observation=json.loads(run('run-'+str(index),[binary],60))
            if not observation.get('ok') or observation.get('source_async') is not False:
                raise RuntimeError('Unexpected task-runtime probe result')
            report['observations'].append(observation)
        guard();report['ok']=True
    except BaseException as error:
        report['error']=repr(error);traceback.print_exc()
    finally:
        save();print(json.dumps({'ok':report['ok'],'report':str(state),
            'source_async':False,'seconds':report['seconds']}))
    return 0 if report['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
