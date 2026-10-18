"""Real pinned module closures, recursive relocation and independent execution."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sqlite3
import sys
import unittest

import support as harness
import source_ffi
import packaging as packaging_harness
import server_http as http_harness

sys.path.insert(0, str(harness.REPO / 'tools'))
import foreign_bundle

SOURCE = '''module packaged;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server extern fn unused(x:i64)->i64!{ffi}=foreign("test","unused","@PIN@");
server fn main()->unit!{ffi,io}{print(echo(42));}
'''


class ForeignPackaging(harness.ToolchainCase):
    program = source_ffi.SourceFFI.program
    events = source_ffi.SourceFFI.events
    library_inputs = packaging_harness.Packaging.library_inputs

    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.file = self.root / 'main.nex'
        self.marker = self.root / 'events'
        self.env = {'NEX_SOURCE_FFI_MARKER': str(self.marker)}

    def closure(self, inventoried=False):
        bundle = self.program(SOURCE, {'echo': 'echo', 'unused': 'echo'})
        driver = self.cli('doctor')['native_compiler']
        dependencies = bundle / 'deps' if inventoried else self.root / 'original dependencies'
        dependencies.mkdir()
        suffix = '.dylib' if platform.system() == 'Darwin' else '.so'
        leaf, helper = [dependencies / ('lib' + name + suffix) for name in ('leaf', 'helper')]
        leaf_source = self.root / 'leaf.c'
        helper_source = self.root / 'helper.c'
        leaf_source.write_text('long leaf_value(void){return 41;}')
        helper_source.write_text('extern long leaf_value(void); long dependency_value(void){return leaf_value()+1;}')
        def compile(source, output, inputs=()):
            arguments = [driver, '-x', 'c', '-std=c11', '-shared', '-fPIC', str(source), '-x', 'none', *map(str, inputs), '-o', str(output)]
            if platform.system() == 'Darwin':
                arguments += ['-Wl,-install_name,' + str(output)]
            else:
                arguments += ['-Wl,-soname,' + output.name, '-Wl,-rpath,' + str(dependencies)]
            result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        compile(leaf_source, leaf)
        compile(helper_source, helper, [leaf])
        producer = self.root / 'producer.c'
        c = producer.read_text().replace('static nex_ffi_status echo(', 'extern long dependency_value(void);\nstatic nex_ffi_status echo(')
        c = c.replace("mark('C');", "if(dependency_value()!=42)return NEX_FFI_ARGUMENT;mark('C');")
        producer.write_text(c)
        arguments = [driver, '-x', 'c', '-std=c11', '-shared', '-fPIC', '-fvisibility=hidden', '-I' + str(harness.REPO / 'runtime'), str(producer), '-x', 'none', str(helper), '-o', str(bundle / 'module')]
        if platform.system() != 'Darwin':
            arguments += ['-Wl,-rpath,' + str(dependencies)]
        result = subprocess.run(arguments, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads((bundle / 'manifest.json').read_text())
        names = ['module', 'NOTICE'] + ([str(p.relative_to(bundle)) for p in (helper, leaf)] if inventoried else [])
        manifest['files'] = [{'path': name, 'sha256': foreign_bundle.sha256(bundle / name)} for name in names]
        (bundle / 'manifest.json').write_text(json.dumps(manifest))
        self.pin = foreign_bundle.sha256(bundle / 'manifest.json')
        self.catalogue['libraries']['test']['manifest_sha256'] = self.pin
        self.catalogue['module_limit'] = 17
        self.host.write_text(json.dumps(self.catalogue))
        self.source(SOURCE.replace('@PIN@', self.pin))
        license_file = self.root / 'fixture-license.txt'
        license_file.write_text('Complete independent C test fixture license.\n')
        self.notices = self.root / 'notices.json'
        self.notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': [
            {'name': 'fixture', 'version': '1', 'url': 'https://example.invalid/nex-test-fixture',
             'roots': list(map(str, {bundle, dependencies})), 'license_files': [str(license_file)]}]}))
        return bundle, dependencies

    def prepare(self, output, **kwargs):
        # Native catalogue inspection must never call a C module constructor.
        previous = os.environ.get('NEX_SOURCE_FFI_MARKER')
        os.environ['NEX_SOURCE_FFI_MARKER'] = str(self.marker)
        try:
            return foreign_bundle.prepare(harness.NEX, self.host, harness.REPO,
                                          output, self.notices, selection={'test': ['echo']}, **kwargs)
        finally:
            if previous is None:
                os.environ.pop('NEX_SOURCE_FFI_MARKER', None)
            else:
                os.environ['NEX_SOURCE_FFI_MARKER'] = previous

    def exercise(self, inventoried):
        bundle, dependencies = self.closure(inventoried)
        originals = {str(p): foreign_bundle.sha256(p) for p in {*(bundle.rglob('*')), *(dependencies.rglob('*'))} if p.is_file()}
        output = self.root / 'prepared'
        report = self.prepare(output)
        self.assertEqual(self.events(), '')
        self.assertEqual(report['schema'], 'nex.foreign-package/1')
        self.assertFalse(report['execution_verified'])
        library = report['libraries']['test']
        self.assertEqual(library['source_manifest_sha256'], self.pin)
        self.assertNotEqual(library['manifest_sha256'], self.pin)
        self.assertEqual(library['exports'], ['echo'])
        host = json.loads((output / 'host.json').read_text())
        self.assertEqual(host['module_limit'], 17)
        self.assertEqual(host['libraries']['test']['exports'], ['echo'])
        self.assertEqual(len(library['components']), 1)
        for name, digest in originals.items():
            self.assertEqual(foreign_bundle.sha256(Path(name)), digest)
        # Compile the exact derived pin explicitly: production `package` still
        # needs to retain this projection and configure the standalone default.
        self.source(SOURCE.replace('@PIN@', library['manifest_sha256']))
        built = self.cli('build', '--profile', 'release', timeout=120)
        self.file.unlink()
        for name in ('producer.c', 'helper.c', 'leaf.c', 'notices.json', 'fixture-license.txt', 'host.json'):
            (self.root / name).unlink()
        shutil.rmtree(bundle)
        if not inventoried:
            shutil.rmtree(dependencies)
        moved = self.root / 'relocated 🧠 %'
        output.rename(moved)
        result = subprocess.run([built['executable'], '--nex-foreign', str(moved / 'host.json')],
                                cwd='/', capture_output=True, text=True, timeout=20,
                                env={'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': '/absent'})
        self.assertEqual((result.returncode, result.stdout), (0, '42\n'), result.stderr)
        final_bundle = moved / host['libraries']['test']['directory']
        manifest = json.loads((final_bundle / 'manifest.json').read_text())
        self.assertEqual(foreign_bundle.sha256(final_bundle / 'manifest.json'), library['manifest_sha256'])
        for record in manifest['files']:
            self.assertEqual(foreign_bundle.sha256(final_bundle / record['path']), record['sha256'])
        # Integrity still fails before the first module initializer.
        (final_bundle / manifest['entry']).write_bytes(b'corrupted')
        result = subprocess.run([built['executable'], '--nex-foreign', str(moved / 'host.json')], capture_output=True, text=True, timeout=20, env={**os.environ, **self.env})
        self.assertEqual(result.returncode, 70)
        self.assertIn('E_FFI_HASH', result.stderr)
        self.assertEqual(self.events(), '')

    def test_external_transitive_closure_relocates_and_remains_pinned(self):
        self.exercise(False)

    def test_existing_inventory_images_keep_their_relative_paths(self):
        self.exercise(True)

    def test_missing_provenance_and_dependency_reject_without_initialization(self):
        bundle, dependencies = self.closure()
        self.notices.write_text('{"schema":"nex.sdk-notices/1","components":[]}')
        with self.assertRaisesRegex(RuntimeError, 'no component/license provenance'):
            self.prepare(self.root / 'missing-notice')
        self.assertFalse((self.root / 'missing-notice').exists())
        self.assertEqual(self.events(), '')
        # Restore provenance, then remove a required transitive image.
        self.notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': [
            {'name': 'fixture', 'version': '1', 'url': 'https://example.invalid/fixture',
             'roots': [str(bundle), str(dependencies)], 'license_files': [str(bundle / 'NOTICE')]}]}))
        next(dependencies.glob('*leaf*')).unlink()
        with self.assertRaisesRegex(RuntimeError, 'unresolved.*dependency'):
            self.prepare(self.root / 'missing-dependency')
        self.assertFalse((self.root / 'missing-dependency').exists())
        self.assertEqual(self.events(), '')

    def test_reachable_selection_cannot_add_operator_authority(self):
        self.closure()
        output = self.root / 'denied'
        with self.assertRaisesRegex(RuntimeError, 'exceeds operator authority'):
            foreign_bundle.prepare(harness.NEX, self.host, harness.REPO, output,
                                   self.notices, selection={'test': ['not_granted']})
        self.assertFalse(output.exists())
        self.assertEqual(self.events(), '')

    def application_notices(self):
        doctor = self.cli('doctor')
        dependencies = [Path(doctor[key]) for key in ('native_openssl_crypto', 'native_openssl_ssl', 'native_sqlite_library') if doctor.get(key)]
        value = json.loads(self.notices.read_text())
        value['components'][0]['roots'] += list(map(str, self.library_inputs(dependencies)))
        self.notices.write_text(json.dumps(value))

    def test_package_retains_source_history_and_runs_without_inputs_or_sdk(self):
        bundle, dependencies = self.closure()
        self.application_notices()
        # An unreachable catalogue entry must not become a deployment input.
        self.catalogue['libraries']['unreachable'] = {'directory': 'absent', 'manifest_sha256': '0' * 64, 'exports': ['secret']}
        self.host.write_text(json.dumps(self.catalogue))
        original = self.file.read_text()
        checked = self.cli('check')
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            before_source = db.execute('SELECT source FROM revisions WHERE hash=?', (checked['revision'],)).fetchone()[0]
            before_ids = db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall()
        output = self.root / 'application'
        result = self.cli('package', '--foreign', self.host, '--notices', self.notices,
                          '--directory', output, env=self.env, timeout=180)
        self.assertEqual(self.events(), '')
        self.assertEqual(self.file.read_text(), original)
        self.assertEqual(result['source_revision'], checked['revision'])
        self.assertNotEqual(result['revision'], checked['revision'])
        report = packaging_harness.Packaging.validate_inventory(self, output)
        projection = report['foreign_projection']
        self.assertEqual(projection['source_revision'], checked['revision'])
        self.assertEqual(projection['packaged_revision'], result['revision'])
        self.assertEqual([item['function'] for item in projection['changes']], ['packaged::echo'])
        self.assertEqual(set(projection['preparation']['libraries']), {'test'})
        for module in projection['preparation']['libraries'].values():
            if platform.system() == 'Darwin':
                self.assertGreaterEqual(tuple(map(int, report['minimum_macos'].split('.'))),
                                        tuple(map(int, module['minimum_macos'].split('.'))))
            else:
                for key in ('required_glibc_symbols', 'required_glibcxx_symbols'):
                    self.assertGreaterEqual(set(report[key]), set(module[key]))
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?', (checked['revision'],)).fetchone()[0], before_source)
            self.assertEqual(db.execute('SELECT revision FROM head WHERE id=1').fetchone()[0], checked['revision'])
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(), before_ids)
        self.file.unlink()
        # Derived history is independently retrievable with explicit current trust.
        self.assertEqual(self.cli('eval', '--revision', result['revision'], '--foreign', output / 'foreign/host.json')['stdout'], '42\n')
        shutil.rmtree(bundle)
        shutil.rmtree(dependencies)
        shutil.rmtree(self.root / '.nex')
        for name in ('producer.c', 'helper.c', 'leaf.c', 'host.json', 'notices.json', 'fixture-license.txt'):
            (self.root / name).unlink()
        moved = self.root / 'independent 🧠 %'
        output.rename(moved)
        link = self.root / 'entry-link'
        link.symlink_to(moved / 'bin/app')
        executed = subprocess.run([str(link)], cwd='/', capture_output=True, text=True, timeout=20,
                                  env={'PATH': '/usr/bin:/bin', 'NEX_RESOURCE_DIR': '/absent', 'NEX_FOREIGN_CONFIG': '/not-an-authority'})
        self.assertEqual((executed.returncode, executed.stdout), (0, '42\n'), executed.stderr)
        self.assertEqual(self.events(), '')
        # A changed host cannot make the compiled derived pin accept another one.
        host_path = moved / 'foreign/host.json'
        host = json.loads(host_path.read_text())
        host['libraries']['test']['manifest_sha256'] = self.pin
        host_path.write_text(json.dumps(host))
        rejected = subprocess.run([str(link)], cwd='/', capture_output=True, text=True, timeout=20, env={**os.environ, **self.env})
        self.assertEqual(rejected.returncode, 70)
        self.assertIn('E_FFI_HASH', rejected.stderr)
        self.assertEqual(self.events(), '')

    def test_packaged_http_uses_default_catalogue_and_keeps_request_authorization(self):
        bundle, dependencies = self.closure()
        self.application_notices()
        source = '''module packaged;
import "std/http.nex" as http;
server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo","@PIN@");
server fn handle(request:http::Request)->http::Response!{ffi}{return http::json_response(200,encode_json(echo(42)));}
'''
        self.source(source.replace('@PIN@', self.pin))
        output = self.root / 'server'
        self.cli('package', '--target', 'server', '--foreign', self.host, '--notices', self.notices,
                 '--directory', output, env=self.env, timeout=180)
        self.assertEqual(self.events(), '')
        self.file.unlink()
        shutil.rmtree(bundle)
        shutil.rmtree(dependencies)
        shutil.rmtree(self.root / '.nex/build')
        auth = self.root / 'auth.json'
        token = self.cli('token', '--user', 'alice', '--auth', auth)['token']
        (self.root / 'assets').mkdir()
        (self.root / 'assets/index.html').write_text('Built fixture browser assets')
        moved = self.root / 'moved server'
        output.rename(moved)
        process = http_harness.HTTP.launch(self, str(moved / 'bin/app'), auth, env=self.env)
        try:
            self.assertEqual(http_harness.HTTP.request(self, '/api/value')[0], 401)
            self.assertEqual(self.events(), '')
            for _ in range(3):
                self.assertEqual(http_harness.HTTP.request(self, '/api/value', token=token)[:2], (200, '42'))
            before = self.events()
            self.assertEqual(before.count('C'), 3)
            self.assertEqual(http_harness.HTTP.request(self, '/api/value', token='invalid')[0], 401)
            self.assertEqual(self.events(), before)
        finally:
            http_harness.HTTP.stop(self, process)
        self.marker.unlink()
        # Default packaged authority must also be kept outside the static root.
        (moved / 'index.html').write_text('Cannot expose the package as public assets')
        rejected = subprocess.run([str(moved / 'bin/app'), '--auth', str(auth),
                                   '--database', str(self.root / 'private.sqlite'), '--static', str(moved)],
                                  capture_output=True, text=True, timeout=20, env={**os.environ, **self.env})
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('outside the static root', rejected.stderr)
        self.assertEqual(self.events(), '')

    def test_package_rejects_wrong_source_pin_and_wrong_signature_before_initialization(self):
        self.closure()
        self.application_notices()
        for original, replacement, error in [(self.pin, 'f' * 64, 'E_FFI_PACKAGE'),
                                              ('echo(x:i64)->i64', 'echo(x:i64)->f64', 'E_FFI_PACKAGE')]:
            source = SOURCE.replace('@PIN@', self.pin).replace(original, replacement)
            self.source(source)
            # Keep main valid when probing a different external result type.
            output = self.root / ('rejected-' + error)
            result = self.cli('package', '--foreign', self.host, '--notices', self.notices,
                              '--directory', output, env=self.env, ok=False, timeout=180)
            self.assertEqual(result['code'], error, result)
            self.assertFalse(output.exists())
            self.assertEqual(self.events(), '')

    def test_imported_callable_projection_edits_only_the_exact_manifest_token(self):
        self.closure()
        self.application_notices()
        native = self.root / 'native.nex'
        token = '"\\u00' + format(ord(self.pin[0]), '02x') + self.pin[1:] + '"'
        definition = ('module bridge;\n// Preserve this original pin: ' + self.pin + '\n'
                      'pub server extern fn echo(x:i64)->i64!{ffi}=foreign("test","echo",'
                      '// Also preserve this comment: ' + self.pin + '\n' + token + ');\n'
                      'server extern fn unused(x:i64)->i64!{ffi}=foreign("hidden","hidden","' + '0' * 64 + '");\n')
        native.write_text(definition)
        source = ('module callers;import "./native.nex" as native;'
                  'server fn invoke(cb:server fn(i64)->i64!{ffi})->i64!{ffi}{return cb(42);}'
                  'server fn main()->unit!{ffi,io}{assert("' + self.pin + '"=="' + self.pin + '");print(invoke(native::echo));}')
        self.source(source)
        output = self.root / 'callable-package'
        result = self.cli('package', '--foreign', self.host, '--notices', self.notices,
                          '--directory', output, env=self.env, timeout=180)
        self.assertEqual(self.events(), '')
        report = json.loads((output / 'application.json').read_text())
        changes = report['foreign_projection']['changes']
        self.assertEqual([c['function'] for c in changes], ['bridge::echo'])
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            bundle = json.loads(db.execute('SELECT source FROM revisions WHERE hash=?', (result['revision'],)).fetchone()[0])
        self.assertEqual(bundle['files']['native.nex'], definition.replace(token, json.dumps(changes[0]['manifest_sha256'])))
        self.assertEqual(bundle['files']['main.nex'], source)
        self.assertEqual(native.read_text(), definition)
        executed = subprocess.run([str(output / 'bin/app')], capture_output=True, text=True, timeout=20)
        self.assertEqual((executed.returncode, executed.stdout), (0, '42\n'), executed.stderr)


if __name__ == '__main__':
    unittest.main()
