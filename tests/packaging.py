"""Relocated native applications, provenance failures and retained runtime behavior."""
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
import unittest
import urllib.error
import urllib.request

import support as harness


class Packaging(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.file = self.root / 'main.nex'

    def library_inputs(self, inputs):
        """Declare the local test fixture's actual vendor-library closure."""
        pending = list(inputs);found = set()
        while pending:
            path = Path(pending.pop()).resolve()
            if path in found:continue
            found.add(path)
            if platform.system() == 'Darwin':
                listing = subprocess.check_output(['/usr/bin/otool', '-L', path], text=True)
                for line in listing.splitlines()[1:]:
                    name = line.strip().split(' (compatibility version ', 1)[0]
                    if name.startswith('/') and not name.startswith(('/usr/lib/', '/System/Library/')):
                        pending.append(name)
            else:
                listing = subprocess.check_output(['ldd', path], text=True)
                pending += re.findall(r'=>\s+(/.*?)\s+\(0x', listing)
        return found

    def notice(self, roots):
        license_file = self.root / 'fixture-license.txt'
        license_file.write_text('Complete fixture provenance notice for explicitly selected test inputs.\n')
        notices = self.root / 'notices.json'
        notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': [
            {'name': 'test-inputs', 'version': 'fixture', 'url': 'https://sqlite.org',
             'roots': list(map(str, roots)), 'license_files': [str(license_file)]}]}))
        return notices

    def validate_inventory(self, directory):
        report = json.loads((directory / 'application.json').read_text())
        self.assertEqual(report['schema'], 'nex.application-package/1')
        self.assertFalse(report['execution_verified'])
        actual = {str(p.relative_to(directory)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
        self.assertEqual(actual, set(report['files']) | {'application.json'})
        for relative, record in report['files'].items():
            path = directory / relative
            if path.is_symlink():
                self.assertEqual(str(path.readlink()), record['symlink'])
                self.assertIn(directory, path.resolve().parents)
            else:
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), record['sha256'])
                self.assertEqual(path.stat().st_size, record['bytes'])
            self.assertNotIn('source', record)
        for component in report['components']:
            for record in component['license_files']:
                self.assertEqual(hashlib.sha256((directory / record['path']).read_bytes()).hexdigest(), record['sha256'])
        self.assertFalse(any('llvm' in name.lower() or 'clang' in name.lower() for name in actual))
        return report

    def sqlite_toolchain(self, prefix):
        doctor = self.cli('doctor')
        original = Path(doctor['native_sqlite_library']).resolve()
        prefix.mkdir(parents=True)
        library = prefix / original.name
        shutil.copy2(original, library)
        if platform.system() == 'Darwin':
            subprocess.run(['/usr/bin/install_name_tool', '-id', '@rpath/' + library.name, library], check=True)
        else:
            dynamic = subprocess.check_output(['readelf', '-d', library], text=True)
            soname = re.search(r'\(SONAME\).*?\[([^]]+)\]', dynamic).group(1)
            if soname != library.name:
                (prefix / soname).symlink_to(library.name)
        config = self.root / 'toolchain.json'
        config.write_text(json.dumps({'schema': 'nex.toolchain/1', 'target': doctor['host'],
            'sqlite': {'include': doctor['native_sqlite_include'], 'library': str(library)}}))
        return config, library

    def test_pure_archived_revision_relocates_without_sources_or_build(self):
        self.source('module packed; fn main() -> i64 !{io} { print("Я🧠"); return 7; }')
        revision = self.cli('check')['revision']
        self.file.unlink()
        output = self.root / 'before'
        result = self.cli('package', '--revision', revision, '--directory', output, timeout=120)
        self.assertFalse(result['execution_verified'])
        moved = self.root / 'moved, % 🧠'
        output.rename(moved)
        report = self.validate_inventory(moved)
        self.assertEqual(report['profile'], 'release')
        self.assertEqual(report['revision'], revision)
        self.assertEqual(report['components'], [])
        shutil.rmtree(self.root / '.nex')
        child = subprocess.run([moved / 'bin/app'], env={'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': '/absent'}, capture_output=True, text=True)
        self.assertEqual((child.returncode, child.stdout), (7, 'Я🧠\n'), child.stderr)

    def test_storage_needs_provenance_and_survives_original_library_removal(self):
        config, library = self.sqlite_toolchain(self.root / 'selected library, % 🧠')
        original_hash = hashlib.sha256(library.read_bytes()).hexdigest()
        self.source('''module saved;
server fn main() -> unit !{db,io} {
  assert(is_ok(store_put("key", "Я🧠")));
  print(unwrap(store_get("key")));
}''')
        output = self.root / 'package'
        database = self.root / 'private.sqlite'
        env = {'NEX_DATABASE': str(database), 'NEX_STORAGE_OWNER': 'alice'}
        error = self.cli('package', '--directory', output, '--toolchain', config, ok=False, env=env, timeout=120)
        self.assertEqual(error['code'], 'E_PACKAGE')
        self.assertFalse(output.exists())
        self.assertIn('provenance', error['message'])
        self.cli('package', '--directory', output, '--toolchain', config,
                 '--notices', self.notice(self.library_inputs([library])), env=env, timeout=120)
        self.assertFalse(database.exists(), 'packaging executed the application')
        self.assertEqual(hashlib.sha256(library.read_bytes()).hexdigest(), original_hash)
        report = self.validate_inventory(output)
        self.assertEqual(len(report['components']), 1)
        self.assertTrue(any('sqlite' in p for p in report['files']))
        shutil.rmtree(library.parent)
        self.file.unlink()
        shutil.rmtree(self.root / '.nex')
        moved = self.root / 'deployed, % 🧠'
        output.rename(moved)
        child = subprocess.run([moved / 'bin/app'], env={'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': '/absent', **env}, capture_output=True, text=True)
        self.assertEqual((child.returncode, child.stdout), (0, 'Я🧠\n'), child.stderr)

    def test_existing_output_and_unsupported_modes_are_rejected(self):
        self.source('module rejected; fn main() -> unit {}')
        output = self.root / 'occupied';output.mkdir()
        marker = output / 'keep';marker.write_text('original')
        self.assertEqual(self.cli('package', '--directory', output, ok=False)['code'], 'E_EXISTS')
        self.assertEqual(marker.read_text(), 'original')
        dangling = self.root / 'dangling';dangling.symlink_to(self.root / 'missing')
        self.assertEqual(self.cli('package', '--directory', dangling, ok=False)['code'], 'E_EXISTS')
        for arguments in [('--target', 'web'), ('--library',), ('--interpreter-only',), ('--output', 'other'), ('--kind', 'llvm'), ('--', '--port', '0')]:
            with self.subTest(arguments=arguments):
                self.assertEqual(self.cli('package', '--directory', self.root / 'new', *arguments, ok=False)['code'], 'E_OPTION')
        self.assertEqual(self.cli('build', '--dpkg-notices', ok=False)['code'], 'E_OPTION')

    def test_sdk_notice_reuse_and_modified_sdk_library_rejection(self):
        # A small SDK-inventory fixture exercises the real compiler/helper and
        # selected real SQLite image, not the full SDK distribution workflow.
        sdk = self.root / 'sdk';(sdk / 'bin').mkdir(parents=True)
        shutil.copy2(harness.NEX, sdk / 'bin/nex')
        config, library = self.sqlite_toolchain(sdk / 'libraries')
        notice = sdk / 'notice.txt';notice.write_text('Retained SDK fixture notice.\n')
        resources = sdk / 'share/nex';resources.mkdir(parents=True)
        manifest = {'schema': 'nex.sdk-bundle/1', 'ok': True,
            'files': {str(library.relative_to(sdk)): {'sha256': hashlib.sha256(library.read_bytes()).hexdigest(), 'component': 'sqlite-fixture'}},
            'components': [{'name': 'sqlite-fixture', 'version': 'fixture', 'url': 'https://sqlite.org',
                'license_files': [{'path': 'notice.txt', 'sha256': hashlib.sha256(notice.read_bytes()).hexdigest()}]}]}
        (resources / 'sdk-bundle.json').write_text(json.dumps(manifest))
        self.source('module sdk_app; server fn main() -> unit !{db} { store_put("k", "v"); }')
        external = self.library_inputs([library]) - {library}
        extra_notices = ['--notices', self.notice(external)] if external else []
        def attempt(destination, ok=True):
            child = subprocess.run([sdk / 'bin/nex', 'package', '--directory', destination, '--toolchain', config, *extra_notices, '--json'],
                cwd=self.root, env={**os.environ, 'NEX_RESOURCE_DIR': str(harness.REPO)}, capture_output=True, text=True, timeout=120)
            self.assertEqual(child.returncode == 0, ok, child.stdout + child.stderr)
            return json.loads(child.stdout)
        attempt(self.root / 'valid')
        report = self.validate_inventory(self.root / 'valid')
        self.assertEqual(report['components'][0]['name'], 'sqlite-fixture')
        with library.open('ab') as stream:stream.write(b'\0')
        error = attempt(self.root / 'changed', ok=False)
        self.assertEqual(error['code'], 'E_PACKAGE')
        self.assertIn('integrity/provenance mismatch', error['message'])
        self.assertFalse((self.root / 'changed').exists())

    def test_relocated_https_server_auth_storage_and_restart(self):
        self.source('''module deployed;
import "std/http.nex" as http;
server fn handle(request: http::Request) -> http::Response !{db} {
  if request.method == "POST" { assert(is_ok(store_put("value", request.body))); }
  let saved: result<str> = store_get("value");
  if is_ok(saved) { return http::json_response(200, encode_json(unwrap(saved))); }
  return http::json_response(200, encode_json("empty"));
}''')
        doctor = self.cli('doctor')
        roots = self.library_inputs([Path(doctor[key]).resolve() for key in ('native_sqlite_library', 'native_openssl_ssl', 'native_openssl_crypto')])
        auth = self.root / 'secret-auth.json'
        tokens = [self.cli('token', '--user', user, '--auth', auth)['token'] for user in ('alice', 'bob')]
        cert, key = self.root / 'cert.pem', self.root / 'secret-key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert,
                        '-days', '1', '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1'],
                       capture_output=True, check=True)
        output = self.root / 'server'
        self.cli('package', '--target', 'server', '--directory', output, '--notices', self.notice(roots), timeout=180)
        report = self.validate_inventory(output)
        self.assertEqual(report['kind'], 'http_server')
        self.assertFalse(any('secret' in p or p.endswith('.sqlite') for p in report['files']))
        for token in tokens:self.assertNotIn(token, (output / 'application.json').read_text())
        moved = self.root / 'server moved, % 🧠';output.rename(moved)
        self.file.unlink();shutil.rmtree(self.root / '.nex')
        def launch():
            process = subprocess.Popen([moved / 'bin/app', '--auth', auth, '--database', self.root / 'database.sqlite',
                '--cert', cert, '--key', key, '--port', '0'], env={'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': '/absent'},
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            lines = queue.Queue()
            threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            try:
                line = lines.get(timeout=15)
                match = re.search(r'https://127\.0\.0\.1:([0-9]+)', line)
                if match is None:
                    process.terminate()
                    stdout, stderr = process.communicate(timeout=15)
                    self.fail(line + stdout + stderr)
                return process, 'https://127.0.0.1:' + match.group(1)
            except BaseException:
                process.terminate();process.communicate(timeout=15);raise
        context = ssl.create_default_context(cafile=str(cert))
        def request(base, token=None, body=None):
            headers = {} if token is None else {'Authorization': 'Bearer ' + token}
            req = urllib.request.Request(base + '/api/value', data=None if body is None else body.encode(), headers=headers)
            try:response = urllib.request.urlopen(req, context=context, timeout=10)
            except urllib.error.HTTPError as error:response = error
            with response:return response.status, json.loads(response.read())
        for restart in (False, True):
            process, base = launch()
            try:
                self.assertEqual(request(base)[0], 401)
                if not restart:self.assertEqual(request(base, tokens[0], 'Я🧠'), (200, 'Я🧠'))
                self.assertEqual(request(base, tokens[0]), (200, 'Я🧠'))
                self.assertEqual(request(base, tokens[1]), (200, 'empty'))
            finally:
                process.send_signal(signal.SIGTERM)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertNotIn('E_INTERNAL_LEAK', stderr)


if __name__ == '__main__':
    unittest.main()
