"""Portable native build driver; every subprocess receives literal argv."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from build_provider import build as build_provider

PROJECT = Path(__file__).resolve().parent
REPO = PROJECT.parents[1]
EXPORTS = ('open', 'event', 'draw', 'adapter', 'verify_gpu')

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('build', 'test', 'run', 'package', 'all'))
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--sdl-archive', type=Path, help='Offline copy of the pinned SDL source archive')
    parser.add_argument('--notices', type=Path, help='Additional nex.sdk-notices/1 registry for source-built toolchains')
    args = parser.parse_args()
    fallback=REPO/('build/windows-host/nex.exe' if os.name=='nt' else 'build/nex')
    selected=args.compiler or os.environ.get('NEX_EXE') or (fallback if fallback.is_file() else shutil.which('nex') or fallback)
    compiler = Path(selected).resolve()
    if not compiler.is_file():
        parser.error('Set NEX_EXE to the absolute path of nex.exe, or pass --compiler.')
    work = PROJECT/'.build'
    work.mkdir(exist_ok=True)
    environment = {**os.environ, 'PYTHONUTF8':'1', 'NEX_PYTHON':sys.executable}
    commands = []
    def run(label, argv, **options):
        command = list(map(str, argv))
        result = subprocess.run(command, cwd=PROJECT, env=environment, capture_output=True,
                                timeout=600, **options)
        (work/(label+'.stdout')).write_bytes(result.stdout)
        (work/(label+'.stderr')).write_bytes(result.stderr)
        commands.append({'name':label, 'argv':command, 'exit_code':result.returncode})
        write(work/'commands.json',commands)
        if result.returncode:
            raise RuntimeError(label+'\n'+result.stdout.decode('utf-8','replace')+
                               result.stderr.decode('utf-8','replace'))
        print(label+': OK', flush=True)
        return result.stdout
    if args.action in ('build','test','package','all') or not (work/'application.json').is_file():
        index = json.loads(run('capabilities',[compiler,'describe','--kind','index','--json']))
        if index['language'] != '0.27':
            raise RuntimeError('This example requires language 0.27; migrate explicitly for another language.')
        doctor = json.loads(run('doctor',[compiler,'doctor','--json']))
        template = (PROJECT/'src/gui.nex.in').read_text(encoding='utf-8')
        bindings = PROJECT/'src/gui.nex'
        bindings.write_text(template.replace('@PIN@','0'*64),encoding='utf-8')
        run('check-template',[compiler,'check','--json'])
        run('context-rules',[compiler,'context','--symbol','rules::move'])
        signatures={}
        for name in EXPORTS:
            value = json.loads(run('signature-'+name,[compiler,'ffi','--symbol','gui::'+name,'--json']))
            signatures[name] = hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
        generated = work/'generated'
        generated.mkdir(exist_ok=True)
        (generated/'signatures.h').write_text(''.join('#define PIN_'+k.upper()+' "'+v+'"\n' for k,v in signatures.items()),encoding='utf-8')
        bundle=work/'provider'
        bundle.mkdir(exist_ok=True)
        module=build_provider(PROJECT,REPO,work,generated,doctor,run,args.sdl_archive)
        shutil.copy2(module,bundle/module.name)
        notice=(PROJECT/'LICENSE').read_bytes()+b'\n\nSDL 3.4.18\n'+(PROJECT/'vendor/SDL-LICENSE.txt').read_bytes()+b'\n\n'+(PROJECT/'vendor/SDL-THIRD-PARTY-NOTICES.txt').read_bytes()
        if doctor.get('native_windows_notices'):
            notice+=b'\n\nNative compiler runtime notices\n'+Path(doctor['native_windows_notices']).read_bytes()
        (bundle/'NOTICE').write_bytes(notice)
        architecture={'amd64':'x86_64','x86_64':'x86_64','arm64':'arm64','aarch64':'arm64'}[doctor['host'].split('-',1)[0].lower()]
        system='windows' if os.name=='nt' else 'macos' if sys.platform=='darwin' else 'linux'
        manifest={'schema':'nex.foreign-bundle/1','platform':system+'-'+architecture,'entry':module.name,
                  'files':[{'path':name,'sha256':sha(bundle/name)} for name in (module.name,'NOTICE')],
                  'exports':signatures,'notices':['NOTICE']}
        write(bundle/'manifest.json',manifest)
        pin=sha(bundle/'manifest.json')
        bindings.write_text(template.replace('@PIN@',pin),encoding='utf-8')
        host=work/'foreign.json'
        write(host,{'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':4,
                    'resource_bytes':1048576,'libraries':{'gui':{'directory':'./provider',
                        'manifest_sha256':pin,'exports':list(EXPORTS)}}})
        notices=json.loads(args.notices.read_bytes()) if args.notices else {'schema':'nex.sdk-notices/1','components':[]}
        notices['components'].append({'name':'nex-tic-tac-toe-sdl','version':'1',
            'url':'https://github.com/sae-ru/NEX','roots':[str(bundle)],'license_files':[str(bundle/'NOTICE')]})
        vendor=[doctor[k] for k in ('native_openssl_ssl','native_openssl_crypto','native_sqlite_library') if doctor.get(k)]
        if doctor.get('native_windows_notices'):
            notices['components'].append({'name':'nex-windows-native-dependencies','version':'LLVM22.1-UCRT-SQLite-OpenSSL',
                'url':'https://github.com/sae-ru/NEX','roots':vendor,'license_files':[doctor['native_windows_notices']]})
        write(work/'notices.json',notices)
        run('check-pinned',[compiler,'check','--json'])
        run('catalogue',[compiler,'foreign',host,'--json'])
        built=json.loads(run('build-native',[compiler,'build','--json']))
        write(work/'application.json',{'executable':built['executable'],'compiler_sha256':sha(compiler),
                                      'provider_sha256':sha(bundle/module.name),'manifest_sha256':pin})
    host=work/'foreign.json'
    if args.action in ('test','all'):
        run('rules-native-reference',[compiler,'test','--foreign',host,'--json'])
        node=os.environ.get('NEX_NODE') or (shutil.which('node') or shutil.which('node.exe'))
        if not node:
            raise RuntimeError('Native Node.js is required for the TypeScript agreement test.')
        ts=work/'typescript'
        run('emit-portable-rules',[compiler,'emit','--kind','typescript','--entry','portable_demo','--directory',ts])
        (ts/'package.json').write_text('{"type":"module"}\n',encoding='utf-8')
        (ts/'verify.ts').write_text("import {entry} from './program.ts'; if(entry()!==1n)throw Error('wrong winner');console.log('TYPESCRIPT_RULES_OK');\n",encoding='utf-8')
        run('rules-typescript',[node,'--experimental-strip-types','--no-warnings',ts/'verify.ts'])
        application=json.loads((work/'application.json').read_bytes())
        previous=environment.get('NEX_GAME_SMOKE')
        environment['NEX_GAME_SMOKE']='1'
        try:
            result=run('gpu-smoke',[application['executable'],'--nex-foreign',host])
            if b'GPU_SMOKE_OK:' not in result:
                raise RuntimeError('missing hardware GPU smoke receipt')
            print(result.decode('utf-8'),end='')
        finally:
            if previous is None:environment.pop('NEX_GAME_SMOKE',None)
            else:environment['NEX_GAME_SMOKE']=previous
    if args.action in ('package','all'):
        output=PROJECT/'dist'
        output.mkdir(exist_ok=True)
        folder=output/('tic-tac-toe-'+str(__import__('time').time_ns()))
        run('package',[compiler,'package','--foreign',host,'--notices',work/'notices.json','--directory',folder,'--json'])
        (work/'last-package.txt').write_text(str(folder),encoding='utf-8')
        print('Standalone game: '+str(folder/('bin/app.exe' if os.name=='nt' else 'bin/app')))
    if args.action=='run':
        app=json.loads((work/'application.json').read_bytes())
        # Hide only the console; the native game creates its own visible window.
        child=subprocess.Popen([app['executable'],'--nex-foreign',str(host)],cwd=PROJECT,
                               env=environment,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
        return child.wait()
    return 0

if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        print(str(error),file=sys.stderr)
        raise SystemExit(1)
