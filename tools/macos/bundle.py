#!/usr/bin/env python3
"""Assemble, relocate, archive and kernel-isolate a macOS development SDK."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import sdk_archive
import sdk_acceptance


def inside(path, root):
    return path == root or root in path.parents


def profile(roots, sdk):
    filters = ' '.join('(subpath '+json.dumps(str(root), ensure_ascii=False)+')' for root in roots)
    return '(version 1)\n(allow default)\n(deny file-read* '+filters+')\n' + \
           '(deny file-write* (subpath '+json.dumps(str(sdk), ensure_ascii=False)+'))\n'


def read_probes(sdk, notices, roots, extra=()):
    candidates = [sdk/'bin/nex']
    for path in extra:
        probe = Path(path).resolve(strict=True)
        if not probe.is_file() or not any(inside(probe, root) for root in roots):
            raise ValueError('--deny-probe must name a readable file inside a denied root')
        candidates.append(probe)
    for component in json.loads(notices.read_text())['components']:
        candidates.extend((notices.parent/filename).resolve(strict=True) for filename in component['license_files'])
    probes = []
    for root in roots:
        probe = next((path for path in candidates if inside(path.resolve(), root) and path.is_file()), None)
        if probe is None:
            raise ValueError('no bounded negative-control input for denied root: '+str(root))
        with probe.open('rb') as stream:
            stream.read(1)
        probes.append(probe.resolve())
    return probes


def package(args):
    sdk, output, notices = args.sdk.resolve(strict=True), args.output.resolve(), args.notices.resolve(strict=True)
    roots = list(dict.fromkeys(path.resolve() for path in args.deny_read))
    if not roots or any(root == Path('/') for root in roots):
        raise ValueError('explicit non-root --deny-read paths are required')
    if inside(output, sdk) or inside(sdk, output) or (output.exists() and any(output.iterdir())):
        raise ValueError('--output must be new/empty and separate from the input SDK')
    if not (sdk/'bin/nex').is_file() or any(p.is_symlink() for p in sdk.rglob('*')):
        raise ValueError('input must be a plain unbundled installed SDK')
    node, npm, python = [Path(path).resolve(strict=True) for path in (args.node, args.npm, args.python)]
    if any(inside(tool, root) for tool in (node, npm, python) for root in roots):
        raise ValueError('Python and Node/npm prerequisites must be outside --deny-read roots')
    output.mkdir(parents=True, exist_ok=True); (output/'logs').mkdir()
    case = Path(tempfile.mkdtemp(prefix='NEX SDK distribution, % 🧠 ', dir=args.work_directory)).resolve()
    report = {'schema': 'nex.sdk-distribution/2', 'ok': False, 'sdk_input': str(sdk),
              'work_directory': str(case), 'denied_read_roots': list(map(str, roots)),
              'live_debugger': args.live, 'browser_build': True, 'npm_offline': True,
              'external_network_blocked': False, 'commands': []}
    started = time.monotonic()
    def save():
        (output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    def run(label, arguments, environment=None, expected=0, timeout=900):
        row = {'label': label, 'arguments': list(map(str, arguments)), 'status': 'running',
               'expected_exit_code': expected}
        report['commands'].append(row); save()
        try:
            result = subprocess.run(row['arguments'], cwd=case, env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout)
        except BaseException as error:
            row.update(status='failed', error=type(error).__name__+': '+str(error)); save()
            raise
        index = str(len(report['commands'])).zfill(3)
        for name in ('stdout', 'stderr'):
            path = output/'logs'/(index+'-'+label+'.'+name)
            path.write_text(getattr(result, name)); row[name] = str(path)
        row.update(exit_code=result.returncode, status='passed' if result.returncode == expected else 'failed'); save()
        if result.returncode != expected:
            raise RuntimeError(label+' failed; inspect '+row['stderr'])
        return result.stdout
    try:
        if any(inside(case, root) for root in roots):
            raise ValueError('temporary work directory must be outside --deny-read roots')
        cache = args.npm_cache.resolve(strict=True)
        if not cache.is_dir():
            raise ValueError('--npm-cache must contain the locked browser dependencies')
        shutil.copytree(cache, case/'npm-cache', symlinks=True)
        environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1',
            PATH=str(node.parent)+':/usr/bin:/bin:/usr/sbin:/sbin', NEX_NODE=str(node), NEX_NPM=str(npm),
            NEX_PYTHON=str(python), NEX_NPM_CACHE=str(case/'npm-cache'), npm_config_offline='true',
            npm_config_audit='false', npm_config_fund='false', npm_config_update_notifier='false')
        for key in ('NEX_CLANG', 'NEX_RESOURCE_DIR', 'NEX_LLDB_DAP', 'DYLD_LIBRARY_PATH',
                    'DYLD_FALLBACK_LIBRARY_PATH', 'LD_LIBRARY_PATH'):
            environment.pop(key, None)
        environment['SDKROOT'] = run('apple-sdk', ['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path']).strip()
        assembler = Path(__file__).resolve().parents[1]/'sdk_bundle.py'
        report.update(input_compiler_sha256=sdk_archive.digest(sdk/'bin/nex'),
                      assembler_sha256=sdk_archive.digest(assembler),
                      archive_helper_sha256=sdk_archive.digest(Path(sdk_archive.__file__)))
        run('assemble', [python, assembler, '--sdk', sdk, '--output', case/'stage', '--notices', notices], environment)
        # Assembly captures the explicitly selected linker into sdk-host.json.
        # Relocated checks must use that relative selection, not the old prefix.
        environment.pop('NEX_WASM_LD', None)
        moved = case/'moved SDK, % 🧠'; (case/'stage').rename(moved)
        manifest, _, _ = sdk_archive.inventory(moved)
        original_paths = [sdk] + [Path(item['source']).resolve() for item in manifest['files'].values() if 'source' in item]
        if any(not any(inside(path, root) for root in roots) for path in original_paths):
            raise ValueError('--deny-read must cover the input SDK and all copied host-component sources')
        report.update(toolchain=manifest['toolchain'], language=manifest['language'], host=manifest['host'],
                      minimum_macos=manifest['minimum_macos'], external_prerequisites=manifest['external_prerequisites'])
        probes = read_probes(sdk, notices, roots, getattr(args, 'deny_probe', []))
        report['negative_control_inputs'] = list(map(str, probes))
        deny_read = '''import json,sys
try:
 with open(sys.argv[1],'rb') as source:source.read(1)
except PermissionError as error:
 print(json.dumps({'denied':True,'errno':error.errno}));sys.exit(77)
raise RuntimeError('forbidden file remained readable')
'''
        deny_write = '''import json,sys
try:
 with open(sys.argv[1],'xb'):pass
except PermissionError as error:
 print(json.dumps({'denied':True,'errno':error.errno}));sys.exit(77)
raise RuntimeError('SDK remained writable')
'''
        def verify(prefix, label):
            policy = case/(label+'.sb'); policy.write_text(profile(roots, prefix))
            base = ['/usr/bin/sandbox-exec', '-f', policy]
            for index, probe in enumerate(probes):
                denied = json.loads(run(label+'-deny-read-'+str(index), [*base, python, '-I', '-c', deny_read, probe], environment, expected=77))
                if denied.get('denied') is not True:
                    raise RuntimeError('read isolation negative control failed')
            control = prefix/'nex-readonly-control'
            if control.exists():
                raise RuntimeError('unexpected SDK write-control path')
            denied = json.loads(run(label+'-deny-write', [*base, python, '-I', '-c', deny_write, control], environment, expected=77))
            if denied.get('denied') is not True:
                raise RuntimeError('write isolation negative control failed')
            target = case/(label+'-workflow')
            command = [*base, python, prefix/'share/nex/tools/sdk_acceptance.py', prefix,
                       '--output', target, '--browser']
            if args.live:
                command.append('--live')
            run(label+'-workflow', command, environment, timeout=18000)
            accepted = json.loads((target/'report.json').read_text())
            sdk_acceptance.validate_completed_report(accepted)
            if accepted['compiler_sha256'] != sdk_archive.digest(prefix/'bin/nex'):
                raise RuntimeError('maintained SDK acceptance differs from the inventoried compiler')
            for field in ('native_compiler', 'native_archiver', 'native_debug_packager', 'sdk_manifest',
                          'native_sqlite_library', 'native_openssl_ssl', 'native_openssl_crypto', 'runtime'):
                if not inside(Path(accepted['doctor'][field]).resolve(), prefix):
                    raise RuntimeError('selected tool/resource escaped SDK: '+field)
            sdk_archive.inventory(prefix, allow_python_cache=False)
            copied = output/(label+'-acceptance.json'); shutil.copyfile(target/'report.json', copied)
            return {'ok': True, 'report': str(copied), 'working_report': str(target/'report.json'),
                    'phases': len(accepted['phases']), 'seconds': accepted['seconds'], 'live_debugger': args.live,
                    'browser_build': True, 'compiler_sha256': accepted['compiler_sha256'],
                    'configured_read_roots_denied': True, 'sdk_write_denied': True,
                    'negative_read_controls': len(probes)}
        report['moved_sdk'] = verify(moved, 'moved')
        arch = manifest['host'].split('-')[0]
        if arch not in ('arm64', 'aarch64', 'x86_64'):
            raise ValueError('unsupported macOS SDK host architecture')
        arch = 'arm64' if arch == 'aarch64' else arch
        name = 'nex-sdk-'+manifest['toolchain']+'-macos-'+arch+'-development'
        report['archive'] = sdk_archive.create(moved, output/(name+'.tar.gz'), name)
        restored = sdk_archive.restore(report['archive']['path'], case/'extracted SDK, % 🧠', report['archive']['sha256'])
        report['restored_sdk'] = verify(restored, 'restored')
        if report['moved_sdk']['compiler_sha256'] != report['restored_sdk']['compiler_sha256']:
            raise RuntimeError('restored SDK compiler differs')
        report['ok'] = True
        Path(report['archive']['path']+'.sha256').write_text(report['archive']['sha256']+'  '+Path(report['archive']['path']).name+'\n')
    except BaseException as error:
        report['error'] = type(error).__name__+': '+str(error)
        raise
    finally:
        report['seconds'] = round(time.monotonic()-started, 3); save()
    Path(report['archive']['path']+'.manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--notices', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--npm-cache', type=Path, required=True)
    parser.add_argument('--deny-read', type=Path, action='append', required=True,
                        help='Block this source/host-dependency tree with a tested kernel policy; repeat as needed')
    parser.add_argument('--deny-probe', type=Path, action='append', default=[],
                        help='Explicit readable control file in a denied source/build root; repeat as needed')
    parser.add_argument('--node', default=shutil.which('node'))
    parser.add_argument('--npm', default=shutil.which('npm'))
    parser.add_argument('--python', default=sys.executable)
    parser.add_argument('--work-directory', type=Path)
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('this distribution workflow requires macOS and sandbox-exec')
    if not args.node or not args.npm:
        parser.error('Node/npm are required external prerequisites')
    report = package(args)
    print(json.dumps({key: report[key] for key in ('ok', 'archive', 'seconds')}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
