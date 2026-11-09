"""Build the isolated Windows LLDB backport from verified local inputs."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def git_apply_patch(source, patch, *, check=False):
    # Git's user/repository autocrlf settings otherwise rewrite the patched
    # working files on Windows. Hash-pinned LLVM inputs require exact LF bytes;
    # command-local settings leave the operator's Git configuration untouched.
    command = ['git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf', 'apply']
    if check:
        command.append('--check')
    subprocess.run([*command, str(patch)], cwd=source, check=True)


def prepare_source_patch(source, record, label):
    """Apply one hash-pinned patch only to its exact retained source bytes."""
    patch = (HERE / record['patch']).resolve(strict=True)
    target = source / record['source_file']
    if sha(patch) != record['patch_sha256']:
        raise ValueError(label + ' patch checksum differs')
    before = sha(target)
    if before == record['patched_sha256']:
        return dict(record, applied=False, source_sha256=before)
    if before != record['original_sha256']:
        raise ValueError(label + ' source checksum differs')
    git_apply_patch(source, patch, check=True)
    git_apply_patch(source, patch)
    if sha(target) != record['patched_sha256']:
        raise ValueError('patched ' + label + ' source checksum differs')
    return dict(record, applied=True, source_sha256=sha(target))


def prepare_indexed_pages(source, record):
    return prepare_source_patch(source, record, 'indexed paging')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / 'build/deps/llvm-project-23.1.4.src.tar.xz')
    parser.add_argument('--source', type=Path, default=ROOT / 'build/deps/llvm23-source/llvm-project-23.1.4.src')
    parser.add_argument('--sdk', type=Path, default=ROOT / 'build/deps/windows-debugger-build23/clang64')
    parser.add_argument('--runtime', type=Path, default=ROOT / 'build/deps/windows-debugger23-native/clang64')
    parser.add_argument('--build', type=Path, default=ROOT / 'build/lldb23-windows-source-a')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--cmake', type=Path, default=Path('C:/Program Files/CMake/bin/cmake.exe'))
    parser.add_argument('--jobs', type=int, default=4)
    parser.add_argument('--appcontainer-pipes', action='store_true',
                        help='Select the separately pinned per-package LOCAL pipe patch')
    args = parser.parse_args()
    if os.name != 'nt' or sys.version_info < (3, 12):
        raise RuntimeError('use native Windows Python 3.12 or later')
    manifest = json.loads((HERE / 'lldb23-windows-backport.json').read_bytes())
    patch = HERE / manifest['patch']
    if sha(args.archive) != manifest['source_sha256'] or sha(patch) != manifest['patch_sha256']:
        raise ValueError('LLVM source archive/backport patch checksum differs')
    source, sdk, runtime = (p.resolve() for p in (args.source, args.sdk, args.runtime))
    output = args.output.resolve()
    if output.exists():
        raise ValueError('choose a new output prefix; the existing debugger is retained')
    if not 1 <= args.jobs <= 16:
        raise ValueError('jobs must be 1..16')
    version = (sdk / 'lib/cmake/llvm/LLVMConfigVersion.cmake').read_text()
    if '"23.1.4"' not in version:
        raise ValueError('this backport requires the separate LLVM23.1.4 build SDK')
    if not source.exists():
        source.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(args.archive, 'r:xz') as archive:
            selected = [m for m in archive if '/lldb/' in m.name or '/cmake/' in m.name
                        or m.name.endswith('/LICENSE.TXT')]
            archive.extractall(source.parent, members=selected, filter='data')
        git_apply_patch(source, patch, check=True)
        git_apply_patch(source, patch)
    for record in manifest['source_files']:
        if sha(source / record['path']) != record['patched_sha256']:
            raise ValueError('patched source checksum differs: ' + record['path'])
    indexed_pages = prepare_indexed_pages(source, manifest['indexed_pages'])
    appcontainer_pipes = None
    if args.appcontainer_pipes:
        record = json.loads((HERE / 'lldb23-appcontainer-pipes.json').read_bytes())
        if record['base_manifest_sha256'] != sha(HERE / 'lldb23-windows-backport.json'):
            raise ValueError('AppContainer pipe base backport checksum differs')
        appcontainer_pipes = prepare_source_patch(source, record, 'AppContainer pipe')
    environment = dict(os.environ)
    environment['PATH'] = str(sdk / 'bin') + os.pathsep + str(runtime / 'bin') + os.pathsep + environment.get('PATH', '')
    build = args.build.resolve()
    build.mkdir(parents=True, exist_ok=True)
    process_manifest = HERE / 'debugger-windows.manifest'
    resource = build / 'nex-debugger-manifest.rc'
    compiled_resource = build / 'nex-debugger-manifest.res'
    resource.write_text('1 24 ' + json.dumps(process_manifest.as_posix(), ensure_ascii=False) + '\n', encoding='utf-8')
    compile_resource = [str(sdk / 'bin/llvm-rc.exe'), '/fo', str(compiled_resource), str(resource)]
    subprocess.run(compile_resource, cwd=ROOT, env=environment, check=True)
    revision = ('llvmorg-' + manifest['version'] + '+nex-windows-' + manifest['patch_sha256'][:12]
                + '-pages-' + indexed_pages['patch_sha256'][:12])
    if appcontainer_pipes:
        revision += '-appcontainer-pipes-' + appcontainer_pipes['patch_sha256'][:12]
    command = [str(args.cmake), '-G', 'Ninja', '-S', str(source / 'lldb'), '-B', str(build),
        '-DCMAKE_BUILD_TYPE=Release', '-DLLDB_INCLUDE_TESTS=OFF', '-DLLDB_ENABLE_PYTHON=ON',
        '-DLLDB_ENABLE_SWIG=ON', '-DLLDB_ENABLE_LUA=OFF', '-DLLDB_ENABLE_CURSES=OFF',
        '-DLLDB_ENABLE_LIBEDIT=OFF', '-DLLDB_ENABLE_LIBXML2=ON', '-DLLDB_ENABLE_LZMA=ON',
        '-DLLDB_ENABLE_LZ4=OFF', '-DLLVM_LINK_LLVM_DYLIB=ON', '-DLLVM_APPEND_VC_REV=OFF',
        '-DLLDB_PYTHON_HOME:STRING=..',
        '-DLLVM_FORCE_VC_REPOSITORY=https://github.com/llvm/llvm-project',
        '-DLLVM_FORCE_VC_REVISION=' + revision]
    command += ['-DCMAKE_EXE_LINKER_FLAGS:STRING="' + compiled_resource.as_posix() + '"']
    values = {'CMAKE_C_COMPILER': sdk / 'bin/clang.exe', 'CMAKE_CXX_COMPILER': sdk / 'bin/clang++.exe',
        'CMAKE_MAKE_PROGRAM': sdk / 'bin/ninja.exe', 'LLVM_DIR': sdk / 'lib/cmake/llvm',
        'Clang_DIR': sdk / 'lib/cmake/clang', 'LLVM_MAIN_SRC_DIR': source / 'llvm',
        'Python3_EXECUTABLE': runtime / 'bin/python.exe', 'Python3_INCLUDE_DIR': runtime / 'include/python3.14',
        'Python3_LIBRARY': runtime / 'lib/libpython3.14.dll.a', 'SWIG_EXECUTABLE': sdk / 'bin/swig.exe',
        'CMAKE_INSTALL_PREFIX': output}
    command += ['-D' + name + '=' + path.as_posix() for name, path in values.items()]
    command += ['-DCMAKE_PREFIX_PATH=' + sdk.as_posix() + ';' + runtime.as_posix()]
    commands = [command, [str(args.cmake), '--build', str(build), '-j', str(args.jobs)]]
    for command in commands:
        subprocess.run(command, cwd=ROOT, env=environment, check=True)
    shutil.copytree(runtime, output)
    install = [str(args.cmake), '--install', str(build)]
    subprocess.run(install, cwd=ROOT, env=environment, check=True)
    commands.append(install)
    startup = subprocess.run([str(output / 'bin/lldb.exe'), '--no-lldbinit', '--batch',
        '-o', 'version', '-o', 'script import lldb,sys; assert lldb.debugger.IsValid(); print("NEX_LLDB_PYTHON_READY",sys.version)'],
        cwd=ROOT, env=environment, text=True, encoding='utf-8', capture_output=True, timeout=30)
    if startup.returncode or 'NEX_LLDB_PYTHON_READY' not in startup.stdout:
        raise RuntimeError('LLDB/Python startup failed:\n' + startup.stdout + startup.stderr)
    receipt = {'schema': 'nex.windows-lldb-build/1', 'build_passed': True,
        'full_debugger_regression_accepted': False, 'source_manifest_sha256': sha(HERE / 'lldb23-windows-backport.json'),
        'indexed_pages': indexed_pages,
        'appcontainer_pipes': appcontainer_pipes,
        'commands': [compile_resource, *commands], 'startup': startup.stdout, 'runtime_source': str(runtime),
        'build_recipe_sha256': sha(Path(__file__)), 'process_manifest_sha256': sha(process_manifest),
        'dependency_locks': {name: sha(HERE / name) for name in (
            'debugger23-dependencies.lock.json', 'debugger-build23-dependencies.lock.json')},
        'files': {name: sha(output / 'bin' / name)
                  for name in ('lldb.exe', 'lldb-dap.exe', 'lldb-server.exe', 'liblldb.dll')}}
    (output / 'nex-debugger-build.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'build_passed': True, 'prefix': str(output)}))


if __name__ == '__main__':
    main()
