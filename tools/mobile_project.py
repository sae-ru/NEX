#!/usr/bin/env python3
"""Generate an owned Capacitor project from checked NEX browser output.

Native build/sign/install remains an explicit platform step. The generated
project carries pinned JavaScript dependencies, local checksum-checked iOS
frameworks, original browser notices and a bounded provenance report.
"""
import argparse
import hashlib
import html
import ipaddress
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import urllib.request
import urllib.parse
import zipfile

RESOURCES = Path(__file__).resolve().parents[1]
VERSION = '8.5.3'
MAX_NATIVE_DOWNLOAD = 32 * 1024 * 1024
MAX_NATIVE_UNPACKED = 128 * 1024 * 1024
JAVA_KEYWORDS = set('abstract assert boolean break byte case catch char class const continue default do double else enum extends final finally float for goto if implements import instanceof int interface long native new package private protected public return short static strictfp super switch synchronized this throw throws transient try void volatile while true false null'.split())


class Failure(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def api_origin(value):
    """The host selects one canonical HTTPS origin, without credentials or paths."""
    try:
        parsed = urllib.parse.urlsplit(value)
        host = parsed.hostname or ''
        if (len(value) > 300 or not re.fullmatch(r'https://[a-z0-9.-]+(?::[1-9][0-9]{0,4})?', value) or
                len(host) > 253 or not all(re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', part) for part in host.split('.')) or
                parsed.port in (0, 443) or (parsed.port is not None and parsed.port > 65535)):
            raise ValueError()
        # WHATWG URL treats a numeric final label as IPv4, not a DNS name.
        if re.fullmatch(r'(?:[0-9]+|0x[0-9a-f]+)', host.split('.')[-1]):
            if str(ipaddress.IPv4Address(host)) != host:
                raise ValueError()
    except (AttributeError, TypeError, ValueError):
        raise Failure('E_MOBILE_API', 'API origin requires canonical https://HOST[:PORT], without paths or credentials')
    return value


def configure_api(index, origin):
    text = index.read_text()
    if text.count('</head>') != 1 or 'nex-api-origin' in text:
        raise Failure('E_MOBILE_API', 'browser index does not accept a unique API configuration')
    before = sha(index)
    index.write_text(text.replace('</head>', '<meta name="nex-api-origin" content="' + html.escape(api_origin(origin), quote=True) + '"></head>'))
    return {'file': 'index.html', 'original_sha256': before, 'configured_sha256': sha(index)}


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1048576), b''):
            value.update(chunk)
    return value.hexdigest()


def configuration(app_id, name, platform):
    if (not isinstance(app_id, str) or len(app_id) > 128 or
            not re.fullmatch(r'[a-z][a-z0-9]*(?:\.[a-z][a-z0-9]*){1,7}', app_id) or
            any(part in JAVA_KEYWORDS for part in app_id.split('.'))):
        raise Failure('E_MOBILE_ID', 'app ID requires 2..8 lowercase non-keyword dot-separated identifiers, at most128 bytes')
    try:
        raw = name.encode('utf-8')
    except (AttributeError, UnicodeError):
        raise Failure('E_MOBILE_NAME', 'app name must be valid Unicode')
    if not name.strip() or len(raw) > 256 or len(name) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise Failure('E_MOBILE_NAME', 'app name requires1..80 Unicode scalars and at most256 UTF-8 bytes without controls')
    if platform not in ('ios', 'android', 'both'):
        raise Failure('E_MOBILE_PLATFORM', 'platform must be ios, android or both')
    return {'appId': app_id, 'appName': name, 'webDir': 'www'}


def checked_template():
    package = json.loads((RESOURCES / 'mobile/package.json').read_text())
    lock = json.loads((RESOURCES / 'mobile/package-lock.json').read_text())
    expected = {'@capacitor/' + name: VERSION for name in ('core', 'ios', 'android', 'cli')}
    if package.get('dependencies') != expected or lock.get('packages', {}).get('', {}).get('dependencies') != expected:
        raise Failure('E_MOBILE_RESOURCE', 'mobile dependency template does not match the pinned runtime')
    for key, item in lock['packages'].items():
        if key and (not item.get('integrity') or not item.get('resolved', '').startswith('https://registry.npmjs.org/')):
            raise Failure('E_MOBILE_RESOURCE', 'mobile lock requires registry URLs and integrity for every package')
    return package, lock


def run(command, cwd, logs, env, label, commands, machine=False, timeout=900):
    log_id = '%03d-%s' % (len(commands), label)
    stdout, stderr = logs / (log_id + '.stdout'), logs / (log_id + '.stderr')
    entry = {'command': list(map(str, command)), 'cwd': str(cwd), 'stdout': str(stdout), 'stderr': str(stderr)}
    commands.append(entry)
    with stdout.open('wb') as out, stderr.open('wb') as err:
        try:
            result = subprocess.run(list(map(str, command)), cwd=cwd, env=env,
                                    stdin=subprocess.DEVNULL, stdout=out, stderr=err, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise Failure('E_MOBILE_TOOL', label + ' failed: ' + str(error))
    entry['exit_code'] = result.returncode
    if result.returncode:
        raise Failure('E_MOBILE_TOOL', label + ' failed; see retained logs: ' + str(logs))
    if machine:
        try:
            value = json.loads(stdout.read_text())
        except (UnicodeError, ValueError):
            raise Failure('E_MOBILE_PROTOCOL', label + ' returned invalid JSON; see retained logs')
        if value.get('ok') is not True:
            raise Failure('E_MOBILE_PROTOCOL', label + ' did not report success')
        return value


def ios_artifacts(project, cache, offline):
    manifest = json.loads((RESOURCES / 'mobile/ios-artifacts.json').read_text())
    if manifest.get('schema') != 'nex.mobile-native/1' or manifest.get('version') != VERSION:
        raise Failure('E_MOBILE_RESOURCE', 'incorrect iOS artifact manifest')
    folder = project / 'native-dependencies/capacitor-ios'
    folder.mkdir(parents=True)
    receipt = []
    for item in manifest['artifacts']:
        if (item['name'] not in ('Capacitor', 'Cordova') or not re.fullmatch('[0-9a-f]{64}', item['sha256']) or
                item['url'] != 'https://github.com/ionic-team/capacitor-swift-pm/releases/download/' + VERSION + '/' + item['name'] + '.xcframework.zip' or
                not 0 < item['bytes'] <= MAX_NATIVE_DOWNLOAD):
            raise Failure('E_MOBILE_RESOURCE', 'invalid pinned iOS artifact')
        archive_path = cache / (item['sha256'] + '.zip')
        if not archive_path.is_file() or sha(archive_path) != item['sha256']:
            if offline:
                raise Failure('E_MOBILE_CACHE', 'offline iOS artifact missing or changed: ' + item['name'])
            cache.mkdir(parents=True, exist_ok=True)
            # Temporary file belongs to this invocation; never execute downloaded code.
            import tempfile
            fd, name = tempfile.mkstemp(prefix='nex-mobile-', suffix='.zip', dir=cache)
            temp = Path(name)
            try:
                with os.fdopen(fd, 'wb') as target, urllib.request.urlopen(item['url'], timeout=60) as source:
                    size = 0
                    for chunk in iter(lambda: source.read(1048576), b''):
                        size += len(chunk)
                        if size > item['bytes']:
                            raise Failure('E_MOBILE_INTEGRITY', 'oversized iOS artifact')
                        target.write(chunk)
                if size != item['bytes'] or sha(temp) != item['sha256']:
                    raise Failure('E_MOBILE_INTEGRITY', 'iOS artifact checksum/size mismatch')
                os.replace(temp, archive_path)
            finally:
                temp.unlink(missing_ok=True)
        if archive_path.stat().st_size != item['bytes']:
            raise Failure('E_MOBILE_INTEGRITY', 'cached iOS artifact size mismatch')
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            if len(members) > 10000 or sum(m.file_size for m in members) > MAX_NATIVE_UNPACKED:
                raise Failure('E_MOBILE_INTEGRITY', 'iOS artifact inventory exceeds limits')
            names = set()
            for member in members:
                path = PurePosixPath(member.filename)
                if (not path.parts or path.is_absolute() or '..' in path.parts or '\\' in member.filename or
                        ':' in member.filename or path.parts[0] != item['name'] + '.xcframework' or
                        member.filename in names or (member.external_attr >> 16) & 0o170000 == 0o120000):
                    raise Failure('E_MOBILE_INTEGRITY', 'unsafe or duplicate iOS archive member')
                names.add(member.filename)
            archive.extractall(folder)
        receipt.append({key: item[key] for key in ('name', 'url', 'sha256', 'bytes')})
    if {x['name'] for x in receipt} != {'Capacitor', 'Cordova'} or len(receipt) != 2:
        raise Failure('E_MOBILE_RESOURCE', 'both iOS frameworks must be pinned once')
    (folder / 'Package.swift').write_text('''// swift-tools-version:5.9
import PackageDescription
let package = Package(name: "capacitor-swift-pm", products: [
.library(name: "Capacitor", targets: ["Capacitor"]),
.library(name: "Cordova", targets: ["Cordova"])], targets: [
.binaryTarget(name: "Capacitor", path: "Capacitor.xcframework"),
.binaryTarget(name: "Cordova", path: "Cordova.xcframework")])
''')
    shutil.copyfile(RESOURCES / 'mobile/CAPACITOR-LICENSE.txt', folder / 'LICENSE.txt')
    package = project / 'ios/App/CapApp-SPM/Package.swift'
    old = '.package(url: "https://github.com/ionic-team/capacitor-swift-pm.git", exact: "' + VERSION + '")'
    text = package.read_text()
    if text.count(old) != 1:
        raise Failure('E_MOBILE_RESOURCE', 'generated Swift package does not match pinned template')
    package.write_text(text.replace(old, '.package(name: "capacitor-swift-pm", path: "../../../native-dependencies/capacitor-ios")'))
    return receipt


def generate(args):
    config = configuration(args.app_id, args.name, args.platform)
    package, lock = checked_template()
    output = Path(os.path.abspath(args.directory))
    if os.path.lexists(output):
        raise Failure('E_EXISTS', 'mobile generation requires a new directory')
    origin = getattr(args, 'api_origin', None)
    if origin is not None:
        origin = api_origin(origin)
    if not output.parent.is_dir():
        raise Failure('E_MOBILE_DIRECTORY', 'output parent directory must exist')
    nex = Path(args.nex).resolve()
    source = Path(args.source).resolve()
    if not nex.is_file() or not source.is_file():
        raise Failure('E_MOBILE_INPUT', 'an actual NEX compiler and source file are required')
    npm = shutil.which(os.environ.get('NEX_NPM', 'npm'))
    node = shutil.which(os.environ.get('NEX_NODE', 'node'))
    if not npm or not node:
        raise Failure('E_MOBILE_TOOL', 'Node22+ and npm are required')
    output.mkdir(mode=0o700)
    logs = output / 'logs'; logs.mkdir()
    commands = []
    report = {'schema': 'nex.mobile-project/1', 'ok': False, 'directory': str(output), 'platform': args.platform,
              'app_id': args.app_id, 'name': args.name, 'capacitor_version': VERSION, 'commands': commands,
              'compiler_sha256': sha(nex), 'native_application_built': False, 'target_executed': False,
              'source_backend': 'typescript-react', 'native_archive_target': False}
    report['api_origin'] = origin
    try:
        env = dict(os.environ)
        if args.offline:
            env['npm_config_offline'] = 'true'
        (output / 'package.json').write_text(json.dumps(package, indent=2) + '\n')
        (output / 'package-lock.json').write_text(json.dumps(lock, indent=2) + '\n')
        (output / 'capacitor.config.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n')
        build = run([nex, 'build', source, '--target', 'web', '--profile', args.profile, '-o', output / 'www', '--json'],
                    source.parent, logs, env, 'nex-web', commands, machine=True)
        if build.get('schema') != 'nex.web-build/1':
            raise Failure('E_MOBILE_PROTOCOL', 'compiler did not produce a browser build')
        report['nex_web_build'] = build
        if origin is not None:
            report['host_configuration'] = configure_api(output / 'www/index.html', origin)
        install = [npm, 'ci', '--ignore-scripts', '--no-audit', '--no-fund']
        if os.environ.get('NEX_NPM_CACHE'):
            install.extend(['--cache', os.environ['NEX_NPM_CACHE']])
        run(install, output, logs, env, 'locked-mobile-dependencies', commands)
        cap = output / 'node_modules/@capacitor/cli/bin/capacitor'
        platforms = ['ios', 'android'] if args.platform == 'both' else [args.platform]
        for platform in platforms:
            command = [node, cap, 'add', platform]
            if platform == 'ios':
                command += ['--packagemanager', 'SPM']
            run(command, output, logs, env, 'generate-' + platform, commands)
        if 'android' in platforms:
            # Capacitor may infer an unrelated host SDK while generating.
            # Keep SDK selection explicit at build time rather than baking it in.
            (output / 'android/local.properties').unlink(missing_ok=True)
        if 'ios' in platforms:
            report['ios_artifacts'] = ios_artifacts(output, Path(args.artifact_cache).resolve(), args.offline)
        # Runtime notices are copied inside the eventual app's web resources.
        notice = output / 'www/NEX_MOBILE_NOTICES.txt'
        notice.write_text('Capacitor ' + VERSION + '\n\n' + '\n\n'.join((RESOURCES / 'mobile' / name).read_text() for name in ('CAPACITOR-LICENSE.txt', 'CAPACITOR-SOURCE-LICENSE.txt', 'CORDOVA-ANDROID-NOTICE.txt', 'CORDOVA-IOS-NOTICE.txt', 'APACHE-2.0.txt')))
        run([node, cap, 'copy'], output, logs, env, 'copy-final-assets', commands)
        if sha(nex) != report['compiler_sha256']:
            raise Failure('E_MOBILE_INPUT', 'compiler changed during generation')
        assets = {p.relative_to(output / 'www').as_posix(): sha(p) for p in (output / 'www').rglob('*') if p.is_file()}
        native_assets = {'ios': output / 'ios/App/App/public', 'android': output / 'android/app/src/main/assets/public'}
        for platform in platforms:
            for name, digest in assets.items():
                if sha(native_assets[platform] / name) != digest:
                    raise Failure('E_MOBILE_INTEGRITY', 'native assets differ from checked browser output')
        report.update(ok=True, platforms=platforms, web_assets=assets,
                      project_files={'ios': 'ios/App/App.xcodeproj', 'android': 'android'} if len(platforms) == 2 else
                                    {platforms[0]: 'ios/App/App.xcodeproj' if platforms[0] == 'ios' else 'android'},
                      npm_lock_sha256=sha(output / 'package-lock.json'))
    except Exception as error:
        report['error'] = {'code': error.code if isinstance(error, Failure) else 'E_MOBILE_TOOL', 'message': str(error)}
    (output / 'nex-mobile-project.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    if not report['ok']:
        raise Failure(report['error']['code'], report['error']['message'] + '; project and logs retained at ' + str(output))
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('--nex', required=True)
    parser.add_argument('--directory', required=True)
    parser.add_argument('--platform', required=True, choices=['ios', 'android', 'both'])
    parser.add_argument('--app-id', required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--profile', choices=['debug', 'release'], default='release')
    parser.add_argument('--artifact-cache', required=True)
    parser.add_argument('--offline', action='store_true')
    parser.add_argument('--api-origin', help='explicit canonical HTTPS API origin, without paths or credentials')
    args = parser.parse_args()
    try:
        report = generate(args)
        print(json.dumps(report, ensure_ascii=False))
        return 0
    except Failure as error:
        print(json.dumps({'ok': False, 'code': error.code, 'message': str(error)}, ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
