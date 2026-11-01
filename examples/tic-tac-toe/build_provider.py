"""Build the portable SDL provider with the selected native NEX C++ toolchain."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import urllib.request


def build(project, repo, work, generated, doctor, run, archive=None):
    dependency=json.loads((project/'vendor/dependencies.json').read_bytes())['SDL']
    cxx=Path(doctor['native_compiler']).resolve(strict=True)
    root=Path(os.environ.get('NEX_GAME_BUILD_ROOT',tempfile.gettempdir()))
    if os.name=='nt':
        while not str(root).isascii() or '%' in str(root):root=root.parent
    identity='format2\n'+'\n'.join((str(project),str(cxx),doctor.get('native_sysroot',''),dependency['sha256']))
    cache=root/'nex-tic-tac-toe-builds'/hashlib.sha256(identity.encode('utf-8')).hexdigest()[:20]
    cache.mkdir(parents=True,exist_ok=True)
    if archive is None:
        shared=repo/'build/deps'/('SDL3-'+dependency['version']+'.tar.gz')
        archive=shared if shared.is_file() else cache/'SDL-source.tar.gz'
    archive=Path(archive).resolve()
    if not archive.exists():
        print('Downloading SDL '+dependency['version']+' (first build only)...',flush=True)
        request=urllib.request.Request(dependency['url'],headers={'User-Agent':'NEX-tic-tac-toe-example'})
        with urllib.request.urlopen(request,timeout=90) as response:
            data=response.read(32*1024*1024+1)
        if len(data)>32*1024*1024:raise RuntimeError('SDL archive exceeds the declared bound')
        if hashlib.sha256(data).hexdigest()!=dependency['sha256']:raise RuntimeError('SDL archive SHA-256 mismatch')
        archive.write_bytes(data)
    if hashlib.sha256(archive.read_bytes()).hexdigest()!=dependency['sha256']:
        raise RuntimeError('SDL archive SHA-256 mismatch: '+str(archive))
    source=cache/('SDL3-'+dependency['version'])
    if not source.is_dir():
        with tarfile.open(archive) as package:
            for member in package.getmembers():
                target=cache/member.name
                if not target.resolve().is_relative_to(cache.resolve()) or not (member.isdir() or member.isfile()):
                    raise RuntimeError('unexpected SDL archive member')
            # Every member has been bounded and checked as a regular file/directory.
            package.extractall(cache)
    cmake=shutil.which('cmake') or ('C:/Program Files/CMake/bin/cmake.exe' if os.name=='nt' else '')
    ninja=shutil.which('ninja')
    if not ninja and os.name=='nt':
        candidate=repo/'build/deps/windows-host/clang64/bin/ninja.exe'
        if candidate.is_file():ninja=str(candidate)
    if not cmake or not Path(cmake).is_file() or not ninja:
        raise RuntimeError('Install native CMake 3.24+ and Ninja, or put them on PATH.')
    # Keep vendor linker outputs and generated build paths ASCII on Windows.
    staging=cache/'input'
    staging.mkdir(exist_ok=True)
    for name in ('gui.cpp','CMakeLists.txt'):shutil.copy2(project/'native'/name,staging/name)
    headers=staging/'headers'
    headers.mkdir(exist_ok=True)
    runtime=Path(doctor['runtime']).parent
    for name in ('nex_ffi.h','nex_ffi_module.h'):shutil.copy2(runtime/name,headers/name)
    shutil.copy2(generated/'signatures.h',headers/'signatures.h')
    binary=cache/'build'
    cc=cxx.with_name('clang.exe' if os.name=='nt' else 'clang')
    if not cc.is_file():
        cc=Path(shutil.which('cc') or '')
        if not cc.is_file():raise RuntimeError('A native C compiler is required to build SDL.')
    options=['-S',staging,'-B',binary,'-G','Ninja','-DCMAKE_BUILD_TYPE=Release',
        '-DCMAKE_MAKE_PROGRAM='+ninja,'-DCMAKE_C_COMPILER='+str(cc),'-DCMAKE_CXX_COMPILER='+str(cxx),
        '-DNEX_SDL_SOURCE='+str(source),'-DNEX_RUNTIME='+str(headers),'-DNEX_SIGNATURES='+str(headers),
        '-U','CMAKE_NINJA_FORCE_RESPONSE_FILE']
    if 'clang' in cxx.name.lower():
        options+=['-DCMAKE_C_COMPILER_TARGET='+doctor['host'],'-DCMAKE_CXX_COMPILER_TARGET='+doctor['host']]
    if doctor.get('native_sysroot'):
        options+=['-DCMAKE_SYSROOT='+doctor['native_sysroot']]
    if sys.platform=='darwin' and os.environ.get('SDKROOT'):
        options+=['-DCMAKE_OSX_SYSROOT='+os.environ['SDKROOT']]
    if doctor.get('native_archiver'):options+=['-DCMAKE_AR='+doctor['native_archiver']]
    if os.name=='nt' and (cxx.parent/'llvm-rc.exe').is_file():options+=['-DCMAKE_RC_COMPILER='+str(cxx.parent/'llvm-rc.exe')]
    if os.name=='nt':options=[str(value).replace('\\','/') for value in options]
    run('configure-gui',[cmake,*options])
    run('compile-gui',[cmake,'--build',binary,'--target','module','--config','Release','-j','4'])
    extension='.dll' if os.name=='nt' else '.dylib' if sys.platform=='darwin' else '.so'
    module=binary/'out'/('module'+extension)
    if not module.is_file():raise RuntimeError('CMake did not produce the native provider: '+str(module))
    (work/'provider-build.json').write_text(json.dumps({'SDL':dependency,'compiler':str(cxx),
        'compiler_sha256':hashlib.sha256(cxx.read_bytes()).hexdigest(),'build_directory':str(binary)},indent=2)+'\n',encoding='utf-8')
    return module
