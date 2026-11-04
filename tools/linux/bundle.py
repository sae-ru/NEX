#!/usr/bin/env python3
"""Package a Linux SDK and verify it in a separate environment without LLVM/Z3."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nex_docker_mount import mount
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_archive
import sdk_acceptance


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def verify(sdk, output):
    """Runs from the installed SDK in the clean container, with no source mount."""
    report = {'ok': False, 'sdk': str(sdk), 'commands': []}
    def run(arguments, *, timeout=600, **options):
        result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True, timeout=timeout, **options)
        report['commands'].append({'arguments': list(map(str, arguments)), 'exit_code': result.returncode,
                                    'stdout': result.stdout, 'stderr': result.stderr})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        return result.stdout
    host_libraries = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2', 'librt.so.1',
                      'libresolv.so.2', 'libutil.so.1', 'libstdc++.so.6', 'libgcc_s.so.1'}
    def dependencies(executable):
        text = run(['ldd', executable])
        for name, filename in re.findall(r'^\s*(\S+)\s*=>\s*(.*?)\s+\(0x', text, re.M):
            if name not in host_libraries and sdk not in Path(filename).resolve().parents:
                raise RuntimeError('non-platform dependency outside SDK: ' + name + ' => ' + filename)
        if 'not found' in text:
            raise RuntimeError('missing dependency: ' + text)
        return text
    started = time.monotonic()
    try:
        for path in ('/src', '/opt/z3', '/usr/lib/llvm-22'):
            if Path(path).exists():
                raise RuntimeError('source/toolchain path must be absent: ' + path)
        if shutil.which('clang') or shutil.which('clang++'):
            raise RuntimeError('clean verification environment contains a host Clang')
        cached = run(['ldconfig', '-p'])
        if any(name in cached for name in ('libLLVM', 'libMLIR', 'libz3.so')):
            raise RuntimeError('clean verification environment contains LLVM/MLIR/Z3')
        manifest = json.loads((sdk / 'share/nex/sdk-bundle.json').read_text())
        for name, item in manifest['files'].items():
            path = sdk / name
            if 'symlink' in item:
                if not path.is_symlink() or str(path.readlink()) != item['symlink']:
                    raise RuntimeError('SDK link differs: ' + name)
            elif digest(path) != item['sha256'] or bool(path.stat().st_mode & 0o111) != item['executable']:
                raise RuntimeError('SDK file differs: ' + name)
        report['compiler_dependencies'] = dependencies(sdk / 'bin/nex')
        for name in ('clang++', 'llvm-ar', 'ld.lld'):
            dependencies(sdk / 'libexec/nex/llvm/bin' / name)
        command = ['python3', sdk / 'share/nex/tools/sdk_acceptance.py', sdk,
                   '--output', output / 'workflow', '--forbid-source', '/src', '--browser']
        # The maintained workflow contains independently bounded phases. Use
        # the same overall budget as the macOS SDK verifier, rather than a
        # single tool command's ten-minute limit for the entire workflow.
        run(command, timeout=18000)
        accepted = json.loads((output / 'workflow/report.json').read_text())
        sdk_acceptance.validate_completed_report(accepted)
        server = Path(accepted['evidence']['authenticated_storage']['executable'])
        report['server_dependencies'] = dependencies(server)
        report.update(ok=True, compiler_sha256=digest(sdk / 'bin/nex'),
                      files_verified=len(manifest['files']), source_checkout_mounted=False,
                      host_llvm_mlir_z3_present=False, browser_build=True, live_debugger=False,
                      workflow=str(output / 'workflow/report.json'), workflow_seconds=accepted['seconds'])
    finally:
        report['seconds'] = round(time.monotonic() - started, 3)
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def package(arguments, output):
    source, sdk = arguments.source.resolve(), arguments.sdk.resolve()
    if not (sdk / 'bin/nex').is_file():
        raise RuntimeError('input must contain bin/nex')
    if any(path.is_symlink() for path in sdk.rglob('*')):
        raise RuntimeError('unbundled SDK input cannot contain symlinks')
    report = {'ok': False, 'sdk_input': str(sdk), 'arch': arguments.arch, 'phases': []}
    started = time.monotonic()
    def save():
        (output / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    def run(name, command):
        log = output / (name + '.log')
        row = {'name': name, 'command': list(map(str, command)), 'status': 'running', 'log': str(log)}
        report['phases'].append(row); save()
        with log.open('w') as stream:
            result = subprocess.run(row['command'], stdout=stream, stderr=subprocess.STDOUT)
        row.update(exit_code=result.returncode, status='passed' if result.returncode == 0 else 'failed'); save()
        if result.returncode:
            raise RuntimeError(name + ' failed; inspect ' + str(log))
    def inspect(image):
        value = json.loads(subprocess.check_output(['docker', 'image', 'inspect', image]))[0]
        if value['Architecture'] != arguments.arch:
            raise RuntimeError('image architecture differs: ' + image)
        return value['Id']
    toolchain = 'nex-linux-toolchain:' + arguments.arch
    packager, runtime = 'nex-sdk-packager:' + arguments.arch, 'nex-sdk-runtime:' + arguments.arch
    original_image = inspect(toolchain)
    try:
        if not arguments.skip_image_build:
            for tag, recipe in [(packager, 'Bundle.Dockerfile'), (runtime, 'BundleRuntime.Dockerfile')]:
                run('image-' + recipe.split('.')[0], ['docker', 'build', '--platform', 'linux/' + arguments.arch,
                    '--build-arg', 'TOOLCHAIN_IMAGE=' + toolchain, '-f', source / 'tools/linux' / recipe, '-t', tag, source])
        report['images'] = {name: inspect(name) for name in (toolchain, packager, runtime)}
        if inspect(toolchain) != original_image:
            raise RuntimeError('original compiler image changed')
        frozen = output / 'input-sdk'
        shutil.copytree(sdk, frozen, symlinks=True)
        report['input_compiler_sha256'] = digest(frozen / 'bin/nex')
        shutil.copyfile(source / 'tools/sdk_bundle.py', output / 'assembler.py')
        report['assembler_sha256'] = digest(output / 'assembler.py')
        shutil.copyfile(source / 'tools/sdk_archive.py', output / 'archive-helper.py')
        report['archive_helper_sha256'] = digest(output / 'archive-helper.py')
        notices = {'schema': 'nex.sdk-notices/1', 'components': [{'name': 'z3-official', 'version': '5.3.1',
            'url': 'https://github.com/Z3Prover/z3/releases/tag/z3-5.3.1', 'roots': ['/opt/z3'],
            'license_files': ['/opt/z3/LICENSE.txt']}]}
        (output / 'notices.json').write_text(json.dumps(notices, indent=2) + '\n')
        shutil.copyfile(source / 'tools/linux/bundle_boundaries.py', output / 'boundary-check.py')
        run('metadata-boundaries', ['docker', 'run', '--rm', '--platform', 'linux/' + arguments.arch, '--network', 'none',
            *mount(frozen, '/sdk'), *mount(output, '/work', False), packager,
            'python3', '/work/boundary-check.py', '--sdk', '/sdk', '--assembler', '/work/assembler.py',
            '--output', '/work/boundaries'])
        report['metadata_boundaries'] = json.loads((output / 'boundaries/report.json').read_text())
        run('assemble', ['docker', 'run', '--rm', '--platform', 'linux/' + arguments.arch, '--network', 'none',
            *mount(frozen, '/sdk'), *mount(output, '/work', False), packager,
            'python3', '/work/assembler.py', '--sdk', '/sdk', '--output', '/work/stage',
            '--notices', '/work/notices.json', '--dpkg-notices'])
        moved = output / 'moved SDK, % 🧠'
        (output / 'stage').rename(moved)
        evidence = output / 'clean-acceptance'; evidence.mkdir()
        target = '/relocated SDK, % 🧠'
        run('clean-sdk', ['docker', 'run', '--rm', '--platform', 'linux/' + arguments.arch, '--network', 'none',
            *mount(moved, target), *mount(evidence, '/evidence', False), '--workdir', '/evidence', runtime,
            'python3', target + '/share/nex/tools/linux/bundle.py', '--verify', target, '--output', '/evidence/report'])
        accepted = json.loads((evidence / 'report/verification.json').read_text())
        if not accepted['ok']:
            raise RuntimeError('clean SDK verification failed')
        report['clean_acceptance'] = accepted
        # All tested bytes stay read-only; archive ownership/time are normalized.
        bundle = json.loads((moved / 'share/nex/sdk-bundle.json').read_text())
        name = 'nex-sdk-' + bundle['toolchain'] + '-linux-' + arguments.arch + '-development'
        archive = output / (name + '.tar.gz')
        report['archive'] = sdk_archive.create(moved, archive, name)
        (output / (archive.name + '.sha256')).write_text(report['archive']['sha256'] + '  ' + archive.name + '\n')
        restored = output / 'archive-acceptance'; restored.mkdir()
        extract = '''import importlib.util, pathlib, subprocess
spec=importlib.util.spec_from_file_location('sdk_archive','/archive-helper.py')
archive=importlib.util.module_from_spec(spec);spec.loader.exec_module(archive)
sdk=archive.restore('/archive.tar.gz',pathlib.Path('/evidence/extracted SDK, % 🧠'),'EXPECTED_SHA256')
subprocess.run(['python3',str(sdk/'share/nex/tools/linux/bundle.py'),'--verify',str(sdk),'--output','/evidence/report'],check=True)
'''.replace('EXPECTED_SHA256', report['archive']['sha256'])
        run('restored-archive', ['docker', 'run', '--rm', '--platform', 'linux/' + arguments.arch, '--network', 'none',
            *mount(archive, '/archive.tar.gz'), *mount(output / 'archive-helper.py', '/archive-helper.py'),
            *mount(restored, '/evidence', False), runtime, 'python3', '-c', extract])
        checked_archive = json.loads((restored / 'report/verification.json').read_text())
        if not checked_archive['ok'] or checked_archive['compiler_sha256'] != accepted['compiler_sha256']:
            raise RuntimeError('restored archive differs from the checked SDK')
        report['restored_archive_acceptance'] = checked_archive
        report['ok'] = True
    finally:
        report['seconds'] = round(time.monotonic() - started, 3); save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--sdk', type=Path, help='Unbundled installed Linux SDK (0.28+)')
    choice.add_argument('--verify', type=Path, help='Verify inside the clean runtime container')
    parser.add_argument('--output', type=Path, required=True, help='New/empty evidence directory')
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--arch', choices=('arm64', 'amd64'), default='arm64' if platform.machine() in ('arm64', 'aarch64') else 'amd64')
    parser.add_argument('--skip-image-build', action='store_true')
    arguments = parser.parse_args(); output = arguments.output.resolve()
    sdk = (arguments.sdk or arguments.verify).resolve()
    if output == sdk or sdk in output.parents or output in sdk.parents:
        parser.error('--output must be separate from the input SDK')
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        parser.error('--output must be new or empty; previous evidence is never replaced')
    output.mkdir(parents=True, exist_ok=True)
    report = verify(sdk, output) if arguments.verify else package(arguments, output)
    print(json.dumps({key: report[key] for key in ('ok', 'seconds')}, indent=2))


if __name__ == '__main__':
    main()
