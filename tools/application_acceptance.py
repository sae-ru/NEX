#!/usr/bin/env python3
"""Prepare native package fixtures, or probe only deployed packages without SDK access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import queue
import re
import shutil
import signal
import ssl
import subprocess
import threading
import urllib.error
import urllib.request


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(arguments, **options):
    result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True, timeout=180, **options)
    require(result.returncode == 0, repr(list(map(str, arguments))) + '\n' + result.stdout + result.stderr)
    return result.stdout


def prepare(sdk, output, notices=None, dpkg=False):
    require(not os.path.lexists(output), '--output must be a new directory')
    sdk = sdk.resolve(strict=True)
    compiler = sdk / 'bin/nex'
    environment = dict(os.environ, NEX_RESOURCE_DIR=str(sdk / 'share/nex'))
    descriptor = json.loads(command([compiler, 'describe', '--json'], env=environment))
    require('application_package_command' in descriptor, 'SDK does not advertise native application packaging')
    output.mkdir(parents=True)
    fixtures = output / 'fixtures';fixtures.mkdir()
    sources = {
        'pure': 'module pure; fn main() -> unit !{io} { print(1.25+1.25); }',
        'storage': '''module storage;
server fn main() -> unit !{db,io} {
  assert(is_ok(store_put("key", "Я🧠"))); print(unwrap(store_get("key")));
}''',
        'server': '''module deployment_server;
import "std/http.nex" as http;
server fn handle(request:http::Request) -> http::Response !{db} {
  if request.method == "POST" { assert(is_ok(store_put("value", request.body))); }
  let saved:result<str> = store_get("value");
  if is_ok(saved) { return http::json_response(200, encode_json(unwrap(saved))); }
  return http::json_response(200, encode_json("empty"));
}'''}
    report = {'schema': 'nex.application-acceptance/1', 'ok': False, 'execution_verified': False,
              'sdk_compiler_sha256': digest(compiler), 'packages': {}}
    def save(): (output / 'preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    save()
    for name, source in sources.items():
        project = output / 'build-inputs' / name;project.mkdir(parents=True)
        (project / 'main.nex').write_text(source + '\n')
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': descriptor['version'], 'entry': 'main.nex'}))
        arguments = [compiler, 'package', '--directory', output / 'packages' / name, '--json']
        if name == 'server':arguments += ['--target', 'server']
        if notices:arguments += ['--notices', notices.resolve(strict=True)]
        if dpkg:arguments += ['--dpkg-notices']
        result = json.loads(command(arguments, cwd=project, env=environment))
        require(result['ok'] and not result['execution_verified'], 'assembly incorrectly claims execution verification')
        report['packages'][name] = result
        save()
    auth = fixtures / 'auth.json'
    tokens = [json.loads(command([compiler, 'token', '--user', user, '--auth', auth, '--json'], env=environment))['token']
              for user in ('alice', 'bob')]
    (fixtures / 'tokens.json').write_text(json.dumps(tokens))
    (fixtures / 'tokens.json').chmod(0o600)
    command(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', fixtures / 'key.pem',
             '-out', fixtures / 'cert.pem', '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'])
    report['ok'] = True
    save()
    return report


def probe(directory, report_path, runtime_only=False):
    directory = directory.resolve(strict=True)
    require(not os.path.lexists(report_path), '--report must be a new file')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    work = report_path.parent / (report_path.stem + '-data');work.mkdir()
    report = {'schema': 'nex.application-execution/1', 'ok': False, 'execution_verified': False,
              'system': platform.system(), 'architecture': platform.machine(), 'runtime_only_requested': runtime_only,
              'available_development_tools': {name: shutil.which(name) for name in ('nex', 'clang++', 'g++', 'cmake', 'node', 'npm')},
              'packages': {}}
    def save(): report_path.write_text(json.dumps(report, indent=2) + '\n')
    save()
    try:
        if runtime_only:
            require(not any(report['available_development_tools'].values()), 'development tools remain in deployment environment')
        host_libraries = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2', 'librt.so.1',
                          'libresolv.so.2', 'libutil.so.1', 'libstdc++.so.6', 'libgcc_s.so.1',
                          'ld-linux-aarch64.so.1', 'ld-linux-x86-64.so.2'}
        for name in ('pure', 'storage', 'server'):
            package = directory / 'packages' / name
            manifest = json.loads((package / 'application.json').read_text())
            require(manifest['schema'] == 'nex.application-package/1' and manifest['execution_verified'] is False,
                    'invalid assembly manifest')
            files = {str(p.relative_to(package)) for p in package.rglob('*') if p.is_file() or p.is_symlink()}
            require(files == set(manifest['files']) | {'application.json'}, 'deployed inventory differs')
            images = {}
            for relative, record in manifest['files'].items():
                path = package / relative
                if 'symlink' in record:
                    require(path.is_symlink() and str(path.readlink()) == record['symlink'] and package in path.resolve(strict=True).parents,
                            'invalid deployed alias')
                else:
                    require(digest(path) == record['sha256'] and path.stat().st_size == record['bytes'] and
                            bool(path.stat().st_mode & 0o111) == record['executable'], 'deployed bytes/mode differ: ' + relative)
                    if platform.system() == 'Linux' and path.read_bytes()[:4] == b'\x7fELF':
                        listing = command(['ldd', path])
                        require('not found' not in listing, 'deployed dependency is missing')
                        for library, resolved in re.findall(r'^\s*(\S+)\s+=>\s+(.*?)\s+\(0x', listing, re.M):
                            require(library in host_libraries or package in Path(resolved).resolve().parents,
                                    'non-platform dependency escaped package: ' + listing)
                        images[relative] = listing
            report['packages'][name] = {'files_verified': len(files), 'manifest_sha256': digest(package / 'application.json'),
                                         'library_resolutions': images}
        environment = {'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': '/absent-nex-resources'}
        require(command([directory / 'packages/pure/bin/app'], env=environment) == '2.5e0\n', 'numeric output differs')
        require(command([directory / 'packages/storage/bin/app'], env={**environment,
            'NEX_DATABASE': str(work / 'storage.sqlite'), 'NEX_STORAGE_OWNER': 'alice'}) == 'Я🧠\n', 'storage output differs')
        fixtures = directory / 'fixtures'
        tokens = json.loads((fixtures / 'tokens.json').read_text())
        context = ssl.create_default_context(cafile=str(fixtures / 'cert.pem'))
        for restart in (False, True):
            process = subprocess.Popen(list(map(str, [directory / 'packages/server/bin/app', '--auth', fixtures / 'auth.json',
                '--database', work / 'server.sqlite', '--cert', fixtures / 'cert.pem', '--key', fixtures / 'key.pem', '--port', '0'])),
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                lines = queue.Queue()
                threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
                line = lines.get(timeout=15)
                match = re.search(r'https://127\.0\.0\.1:([0-9]+)', line)
                require(match is not None, 'server did not announce a port: ' + line)
                base = 'https://127.0.0.1:' + match.group(1)
                def request(token=None, body=None):
                    headers = {} if token is None else {'Authorization': 'Bearer ' + token}
                    req = urllib.request.Request(base + '/api/value', data=None if body is None else body.encode(), headers=headers)
                    try:response = urllib.request.urlopen(req, context=context, timeout=10)
                    except urllib.error.HTTPError as error:response = error
                    with response:return response.status, json.loads(response.read())
                require(request()[0] == 401, 'unauthenticated request accepted')
                if not restart:require(request(tokens[0], 'Я🧠') == (200, 'Я🧠'), 'write failed')
                require(request(tokens[0]) == (200, 'Я🧠'), 'stored Unicode/restart value differs')
                require(request(tokens[1]) == (200, 'empty'), 'principal data isolation failed')
            finally:
                if process.poll() is None:process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=15)
                (work / ('server-restarted.log' if restart else 'server.log')).write_text(stdout + stderr)
                require(process.returncode == 0 and 'E_INTERNAL_LEAK' not in stderr, 'server exit failed: ' + stderr)
        report.update(ok=True, execution_verified=True, numeric=True, storage=True, https=True,
                      authentication=True, principal_isolation=True, restart_persistence=True)
    except BaseException as error:
        report['error'] = str(error)
        raise
    finally:
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--notices', type=Path)
    parser.add_argument('--dpkg-notices', action='store_true')
    parser.add_argument('--probe', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--require-runtime-only', action='store_true')
    args = parser.parse_args()
    if args.probe:
        if not args.report or args.sdk or args.output:parser.error('--probe requires --report and no --sdk/--output')
        result = probe(args.probe, args.report, args.require_runtime_only)
    else:
        if not args.sdk or not args.output or args.report or args.require_runtime_only:parser.error('preparation requires --sdk and --output')
        result = prepare(args.sdk, Path(os.path.abspath(args.output)), args.notices, args.dpkg_notices)
    print(json.dumps(result))


if __name__ == '__main__':main()
