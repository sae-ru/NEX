#!/usr/bin/env python3
"""Check HTTP foreign authority, browser isolation and source-deleted delivery."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

from fixtures import Fixtures

HERE = Path(__file__).resolve().parent


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--http-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--package-notices', type=Path)
    args = parser.parse_args()
    temporary = args.output is None
    out = args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nex-http-delivery-'))
    if not temporary:
        out.mkdir(parents=True)
    shutil.copy2(__file__, out / 'verify-input.py')
    started = time.monotonic()
    report = {'schema': 'nex.http-provider-delivery/1', 'ok': False,
              'verification_source_sha256': sha(__file__), 'commands': [],
              'rejections': [], 'full_objective_complete': False}
    peer = None

    def save():
        report['seconds'] = round(time.monotonic() - started, 3)
        write(out / 'report.json', report)

    def run(label, argv, *, cwd=None, env=None, expected=0, parsed=True):
        argv = list(map(str, argv))
        row = {'label': label, 'argv': argv, 'state': 'running'}
        report['commands'].append(row)
        report['state'] = label
        save()
        result = subprocess.run(argv, cwd=cwd or out, env=env,
                                capture_output=True, text=True, timeout=240)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        row.update(exit_code=result.returncode, state='passed' if result.returncode == expected else 'failed')
        save()
        assert result.returncode == expected, (label, result.stdout[-3500:], result.stderr[-2000:])
        return json.loads(result.stdout) if parsed else result

    try:
        if args.sdk:
            sdk = args.sdk.resolve(strict=True)
        else:
            if not args.compiler or not args.resources:
                parser.error('use --sdk, or both --compiler and --resources')
            sdk = out / 'source-projection'
            (sdk / 'bin').mkdir(parents=True)
            (sdk / 'share').mkdir()
            shutil.copy2(args.compiler.resolve(strict=True), sdk / 'bin/nex')
            (sdk / 'share/nex').symlink_to(args.resources.resolve(strict=True), target_is_directory=True)
        compiler = sdk / 'bin/nex'
        env = {**os.environ, 'NEX_RESOURCE_DIR': str(sdk / 'share/nex'), 'PYTHONDONTWRITEBYTECODE': '1'}
        env.pop('NEX_FOREIGN_CONFIG', None)
        checked = run('operator-inputs', [sys.executable, '-B', HERE / 'check_inputs.py',
            '--http-prefix', args.http_prefix.resolve(strict=True), '--output', out / 'operator-inputs'], env=env)
        assert checked['ok'] and checked['target_rejections'] == 57
        report['target_rejections'] = checked['target_rejections']
        doctor = run('doctor', [compiler, 'doctor', '--json'], env=env)
        peer = Fixtures(out, doctor)
        target = out / 'targets.json'
        write(target, peer.config())
        project = out / 'original project % 🧠'
        run('prepare', [sys.executable, '-B', HERE / 'prepare.py', '--sdk', sdk,
                       '--targets', target, '--http-prefix', args.http_prefix.resolve(strict=True),
                       '--output', project, '--diagnostics'], env=env, parsed=False)
        prepared = json.loads((project / 'evidence/report.json').read_text())
        assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized']
        assert peer.dns.count() == 0 and not peer.events
        shutil.copytree(project / 'evidence', out / 'prepared-evidence')
        shutil.copytree(project / 'generated', out / 'prepared-configuration')
        shutil.copy2(project / 'bundle/manifest.json', out / 'original-provider-manifest.json')
        report.update(compiler_sha256=sha(compiler), language=prepared['language'], toolchain=prepared['toolchain'],
                      provider_module_sha256=prepared['module_sha256'])
        source = project / 'main.nex'
        prefix = source.read_text().split('server fn main()->unit', 1)[0]
        body = 'assert(len(statistics_raw())==8);'
        for scheme, port, protocol in [('http', peer.http_port, '1.1'), ('https', peer.https_port, '2')]:
            url = json.dumps(scheme + '://api.example.test:' + str(port) + '/ok')
            body += ('let r' + str(port) + ':httpc::Response=unwrap(httpc::get(make_client(),"backend",' + url + ',1000));'
                     'assert(r' + str(port) + '.status==200);assert(r' + str(port) + '.body==utf8_bytes("42"));'
                     'assert(r' + str(port) + '.protocol==' + json.dumps(protocol) + ');')
        program = prefix + 'server fn main()->unit !{task,ffi,io}{' + body + 'print(42);}\n'
        source.write_text(program)
        host = project / 'foreign.json'
        catalogue = json.loads(host.read_text())
        module, policy = project / 'bundle/module.so', project / 'bundle/targets.json'
        module_bytes, policy_bytes = module.read_bytes(), policy.read_bytes()
        for kind, code in [('no-grant', 'E_FFI_GRANT'), ('no-export', 'E_FFI_GRANT'),
                           ('wrong-pin', 'E_FFI_HASH'), ('wrong-signature', 'E_FFI_SIGNATURE'),
                           ('changed-module', 'E_FFI_HASH'), ('changed-target-file', 'E_FFI_HASH')]:
            source.write_text(program)
            write(host, catalogue)
            module.write_bytes(module_bytes)
            policy.write_bytes(policy_bytes)
            selected = copy.deepcopy(catalogue)
            if kind == 'no-export':
                selected['libraries']['http']['exports'] = []
                write(host, selected)
            if kind == 'wrong-pin':
                source.write_text(program.replace(prepared['manifest_sha256'], 'f' * 64))
            if kind == 'wrong-signature':
                source.write_text(program.replace('statistics_raw()->list<i64>', 'statistics_raw()->list<bool>'))
            if kind == 'changed-module':
                module.write_bytes(module_bytes + b'\0')
            if kind == 'changed-target-file':
                policy.write_bytes(policy_bytes + b' ')
            for mode in ('eval', 'debug', 'release'):
                before = peer.dns.count(), len(peer.events)
                argv = [compiler, 'eval' if mode == 'eval' else 'run', '--task-workers', '1', '--json']
                if kind != 'no-grant':
                    argv += ['--foreign', host]
                if mode != 'eval':
                    argv += ['--profile', mode]
                observed = run(kind + '-' + mode, argv, cwd=project,
                               env={**env, 'NEX_FOREIGN_CONFIG': str(host)}, expected=1 if mode == 'eval' else 70)
                if mode == 'eval':
                    assert observed.get('code') == code, observed
                else:
                    diagnostics = observed.get('native_diagnostics', {}).get('diagnostics', [])
                    assert len(diagnostics) == 1 and diagnostics[0]['status'] == 'mapped' and diagnostics[0]['report']['code'] == code, observed
                assert (peer.dns.count(), len(peer.events)) == before
                report['rejections'].append({'case': kind, 'mode': mode, 'code': code, 'DNS_packets': 0, 'HTTP1_requests': 0})
                save()
        source.write_text(program)
        write(host, catalogue)
        module.write_bytes(module_bytes)
        policy.write_bytes(policy_bytes)
        run('client-emission', [compiler, 'emit', '--kind', 'typescript', '--entry', 'client_value',
                               '--directory', out / 'client', '--json'], cwd=project, env=env)
        for path in (out / 'client').rglob('*'):
            if path.is_file():
                text = path.read_text()
                assert not any(value in text for value in ('send_raw', 'statistics_raw', 'make_client',
                    prepared['manifest_sha256'], 'example.test', '127.0.0.1', 'module.so', 'BEGIN CERTIFICATE')), path
        source.write_text(prefix + 'client fn forbidden()->result<httpc::Response> !{task,ffi}{return send_raw(httpc::request("backend","GET","http://api.example.test/",utf8_bytes(""),1000));}\n')
        rejected = run('client-realm-rejection', [compiler, 'check', '--json'], cwd=project, env=env, expected=1)
        assert rejected['code'] == 'E_REALM', rejected
        source.write_text(program)
        notice_names = ['NOTICE', 'SOURCE.json', 'curl-LICENSE.txt', 'nghttp2-LICENSE.txt', 'c-ares-LICENSE.txt']
        components = [{'name': 'nex-http-provider', 'version': prepared['toolchain'],
            'url': 'https://github.com/sae-ru/NEX', 'roots': [str(project / 'bundle')],
            'license_files': [str(project / 'bundle' / name) for name in notice_names]}]
        if args.package_notices:
            external = args.package_notices.resolve(strict=True)
            selected = json.loads(external.read_text())
            assert selected['schema'] == 'nex.sdk-notices/1'
            for row in selected['components']:
                item = dict(row)
                for field in ('roots', 'license_files'):
                    item[field] = [str((external.parent / path).resolve(strict=True)) for path in row[field]]
                components.append(item)
        elif sys.platform == 'darwin' and not (sdk / 'share/nex/sdk-bundle.json').is_file():
            crypto = Path(doctor['native_openssl_crypto']).resolve(strict=True)
            license = crypto.parent.parent / 'LICENSE.txt'
            if not license.is_file():
                raise RuntimeError('unbundled OpenSSL requires --package-notices with its actual license')
            components.append({'name': 'openssl', 'version': crypto.parent.parent.name,
                'url': 'https://www.openssl.org/', 'roots': [str(crypto.parent)], 'license_files': [str(license)]})
        notices = out / 'notices.json'
        write(notices, {'schema': 'nex.sdk-notices/1', 'components': components})
        before = peer.dns.count()
        package = out / 'package'
        argv = [compiler, 'package', '--foreign', host, '--notices', notices, '--directory', package, '--json']
        if sys.platform.startswith('linux'):
            argv += ['--dpkg-notices']
        run('package', argv, cwd=project, env=env)
        assert peer.dns.count() == before and json.loads((package / 'application.json').read_text())['execution_verified'] is False
        moved = out / 'moved package % 🧠'
        package.rename(moved)
        shutil.rmtree(project)
        # The peer has already loaded its server key/certificate. Removing the
        # operator root proves the application uses its captured CA bytes.
        (peer.cert / 'root.pem').unlink()
        observed = run('source-deleted-package', [moved / 'bin/app'], cwd=peer.files,
            env={'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': str(out / 'absent-sdk'),
                 'NEX_FOREIGN_CONFIG': str(out / 'absent-host.json'), 'SSL_CERT_FILE': str(out / 'absent-ca.pem')}, parsed=False)
        assert observed.stdout == '42\n' and peer.dns.count() >= before + 4, (observed.stdout, observed.stderr)
        original_source = json.loads((out / 'prepared-evidence/inputs/SOURCE.json').read_text())
        records = list(moved.rglob('SOURCE.json'))
        assert records and all(json.loads(path.read_text()) == original_source for path in records)
        for name in ('curl-LICENSE.txt', 'nghttp2-LICENSE.txt', 'c-ares-LICENSE.txt'):
            files = list(moved.rglob(name))
            assert files and all(sha(path) == sha(out / 'prepared-evidence/inputs/licenses' / name) for path in files)
        write(out / 'moved-inventory.json', {path.relative_to(moved).as_posix():
            {'sha256': sha(path), 'bytes': path.stat().st_size} for path in moved.rglob('*') if path.is_file()})
        report.update(ok=True, state='passed', authority_rejections=len(report['rejections']),
                      client_server_pruning=True, source_deleted_package=True, relocated_package=True,
                      captured_CA_used=True, static_dependency_licenses_preserved=True)
    except BaseException as error:
        report.update(state='failed', error=repr(error))
        raise
    finally:
        if peer:
            report['DNS_events'], report['HTTP1_events'] = peer.dns.events, peer.events
            peer.close()
        save()
    print(json.dumps({key: report.get(key) for key in ('ok', 'state', 'authority_rejections', 'source_deleted_package', 'seconds')}))
    if temporary and report['ok']:
        shutil.rmtree(out)


if __name__ == '__main__':
    main()
