#!/usr/bin/env python3
"""Qualify and archive an installed native Windows SDK on Windows."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import sdk_acceptance
from sdk_archive import create, digest, inventory, restore


def process_environments(system, openssl_prefix, wasm_linker, host_runtime_bin=None):
    clean = {k: v for k, v in os.environ.items()
             if k.upper() != 'PATH' and not k.upper().startswith(('NEX_', 'PYTHON', 'NPM_CONFIG_'))}
    system_path = (str(system/'System32'), str(system))
    clean.update(PATH=os.pathsep.join(system_path), PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')
    # The ordinary NEX executable has not yet had its PE dependencies collected.
    # On the standard layout its host LLVM DLLs sit beside the selected Wasm linker.
    host_bin = host_runtime_bin if host_runtime_bin is not None else wasm_linker.parent
    host_bin = host_bin.resolve(strict=True)
    if not host_bin.is_dir():
        raise ValueError('select an existing directory of host compiler runtime DLLs')
    assembly_path = (str(openssl_prefix/'bin'), str(host_bin), *system_path)
    assembly = {**clean, 'PATH': os.pathsep.join(assembly_path), 'NEX_WASM_LD': str(wasm_linker)}
    return clean, assembly


def browser_environment(environment, node, output):
    # npm scripts and their tsc/vite shims start "node" by name. Expose only
    # the selected executable, including when it lives alongside host tools.
    node_bin = output/'browser-tools'
    node_bin.mkdir()
    shutil.copy2(node, node_bin/'node.exe')
    return {**environment, 'PATH': os.pathsep.join((str(node_bin), environment['PATH'])),
            'NEX_NODE': str(node)}


def qualify(args):
    sdk = args.sdk.resolve(strict=True)
    output = args.output.resolve()
    if output.is_relative_to(sdk) or sdk.is_relative_to(output):
        raise ValueError('output must be separate from the installed SDK')
    if not (sdk/'bin/nex.exe').is_file() or (sdk/'share/nex/sdk-bundle.json').exists():
        raise ValueError('input must be an ordinary native Windows SDK installation')
    paths = {name: getattr(args, name).resolve(strict=True) for name in
             ('notices', 'openssl_prefix', 'wasm_linker', 'npm_cache', 'node', 'npm')}
    for name in ('lldb', 'lldb_dap', 'package_notices'):
        if getattr(args, name) is not None:
            paths[name] = getattr(args, name).resolve(strict=True)
    if not paths['npm_cache'].is_dir() or not (paths['openssl_prefix']/'bin').is_dir():
        raise ValueError('select populated npm cache and native OpenSSL prefix directories')
    for name, path in paths.items():
        if name not in ('npm_cache', 'openssl_prefix') and not path.is_file():
            raise ValueError('selected input must be a file: '+name)
    forbidden = [path.resolve() for path in args.forbid_source]
    if any(path.exists() for path in forbidden):
        raise ValueError('a forbidden source path is present on this Windows host')

    output.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'nex.sdk-windows-distribution/1', 'ok': False,
              'network_profile': args.network_profile, 'input_compiler_sha256': digest(sdk/'bin/nex.exe'),
              'forbidden_source_paths': list(map(str, forbidden)), 'commands': []}
    system = Path(os.environ['SystemRoot']).resolve(strict=True)
    environment, assembly_env = process_environments(system, paths['openssl_prefix'], paths['wasm_linker'],
                                                      args.host_runtime_bin)

    def save():
        temporary = output/'verification.tmp'
        temporary.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
        temporary.replace(output/'verification.json')

    def run(label, command, env):
        command = [str(value) for value in command]
        row = {'phase': label, 'command': command, 'status': 'running'}
        report['commands'].append(row)
        save()
        try:
            with (output/(label+'.stdout')).open('xb') as stdout, (output/(label+'.stderr')).open('xb') as stderr:
                result = subprocess.run(command, cwd=output, env=env, stdout=stdout, stderr=stderr, timeout=18000)
            row.update(exit_code=result.returncode, status='passed' if result.returncode == 0 else 'failed')
            if result.returncode:
                raise RuntimeError(label+' failed; inspect '+str(output/(label+'.stderr')))
        except Exception:
            row['status'] = 'failed'
            raise
        finally:
            save()

    def accepted(prefix, manifest, label, env):
        manifest_path = prefix/'share/nex/sdk-bundle.json'
        manifest_pin = digest(manifest_path)
        acceptance = output/(label+'-acceptance')
        command = [sys.executable, '-B', prefix/'share/nex/tools/sdk_acceptance.py', prefix,
                   '--output', acceptance, '--browser', '--network-profile', args.network_profile]
        if args.live:
            command.append('--live')
        if 'package_notices' in paths:
            command.extend(('--package-notices', paths['package_notices']))
        for path in forbidden:
            command.extend(('--forbid-source', path))
        run(label, command, env)
        receipt = acceptance/'report.json'
        verified = json.loads(receipt.read_text(encoding='utf-8'))
        sdk_acceptance.validate_completed_report(verified, expected_network_profile=args.network_profile)
        if (verified['compiler_sha256'] != report['input_compiler_sha256'] or
                verified['version'] != manifest['toolchain'] or verified['language'] != manifest['language'] or
                Path(verified['sdk']).resolve(strict=True) != prefix):
            raise ValueError('acceptance belongs to a different SDK')
        doctor = verified['doctor']
        if Path(doctor['sdk_manifest']).resolve(strict=True) != prefix/'share/nex/sdk-host.json':
            raise ValueError('acceptance did not select the moved Windows toolchain manifest')
        for name in ('native_compiler', 'native_archiver', 'native_linker', 'native_sysroot',
                     'native_sqlite_include', 'native_sqlite_library', 'native_openssl_include',
                     'native_openssl_ssl', 'native_openssl_crypto', 'native_windows_notices',
                     'wasm_compiler', 'wasm_linker', 'runtime'):
            if not Path(doctor[name]).resolve(strict=True).is_relative_to(prefix):
                raise ValueError('relocated SDK selected an external tool/resource: '+name)
        inventory(prefix, allow_python_cache=False)
        if digest(manifest_path) != manifest_pin:
            raise ValueError('SDK manifest changed during acceptance')
        return {'report': str(receipt), 'report_sha256': digest(receipt), 'phases': len(verified['phases']),
                'manifest_sha256': manifest_pin, 'compiler_sha256': verified['compiler_sha256']}

    try:
        stage = output/'assembled'
        run('assemble', [sys.executable, '-B', TOOLS/'sdk_bundle.py', '--sdk', sdk, '--output', stage,
                         '--notices', paths['notices'], '--windows-openssl-prefix', paths['openssl_prefix']], assembly_env)
        moved = stage.rename(output/'Moved SDK %, λ')
        manifest, _, _ = inventory(moved, allow_python_cache=False)
        if manifest.get('platform') != 'windows' or manifest.get('architecture') != 'x86_64':
            raise ValueError('expected an assembled native Windows x86-64 SDK')
        cache = output/'npm-cache'
        shutil.copytree(paths['npm_cache'], cache)
        validation_env = {**browser_environment(environment, paths['node'], output), 'NEX_NPM': str(paths['npm']),
                          'NEX_PYTHON': sys.executable, 'NEX_NPM_CACHE': str(cache),
                          'npm_config_offline': 'true', 'npm_config_audit': 'false', 'npm_config_fund': 'false'}
        for name in ('lldb', 'lldb_dap'):
            if name in paths:
                validation_env['NEX_'+name.upper()] = str(paths[name])
        report['moved_sdk'] = accepted(moved, manifest, 'moved', validation_env)
        name = 'nex-sdk-'+manifest['toolchain']+'-windows-x86_64-development'
        archive = output/(name+'.tar.gz')
        report['archive'] = create(moved, archive, name)
        restored = restore(archive, output/'Restored SDK %, λ', report['archive']['sha256'])
        report['restored_sdk'] = accepted(restored, manifest, 'restored', validation_env)
        if report['moved_sdk']['manifest_sha256'] != report['restored_sdk']['manifest_sha256']:
            raise ValueError('archive restoration changed the accepted SDK manifest')
        archive.with_suffix(archive.suffix+'.sha256').write_text(
            report['archive']['sha256']+'  '+archive.name+'\n', encoding='utf-8')
        report['ok'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('sdk', 'output', 'notices', 'openssl-prefix', 'wasm-linker', 'npm-cache', 'node', 'npm'):
        parser.add_argument('--'+name, type=Path, required=True)
    for name in ('lldb', 'lldb-dap', 'package-notices', 'host-runtime-bin'):
        parser.add_argument('--'+name, type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--forbid-source', type=Path, action='append', default=[])
    parser.add_argument('--network-profile', choices=sdk_acceptance.NETWORK_PROFILES, default='full')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('run the distribution workflow on native Windows')
    if args.live and (args.lldb is None or args.lldb_dap is None):
        parser.error('--live requires explicit --lldb and --lldb-dap')
    report = qualify(args)
    print(json.dumps({'ok': True, 'archive': report['archive'], 'network_profile': report['network_profile']}))


if __name__ == '__main__':
    main()
