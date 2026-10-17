"""Real native cross-build artifacts, ABI isolation and explicit toolchain inputs."""
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import unittest

import support as harness


class NativeTargets(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.doctor = self.cli('doctor')
        self.config = self.root / 'toolchain config.json'
        self.source('''module targets;
struct Box<T> { value:T; }
fn identity<T>(value:T) -> T { return value; }
fn main() -> unit !{io} {
  print(encode_json(Box<str>(identity("Архитектуры 🌍"))));
}
test fn semantics() -> unit {
  let value:Box<i64> = unwrap(decode_json<Box<i64>>("{\\"value\\":\\"9223372036854775807\\"}"));
  assert(identity(value.value) == 9223372036854775807);
  assert((false && identity(1) / 0 == 1) == false);
}
''')

    def configure(self, **fields):
        fields = {'schema': 'nex.toolchain/1', 'target': self.doctor['host'], **fields}
        self.config.write_text(json.dumps(fields))
        return fields

    def test_host_manifest_runs_tests_and_archives(self):
        self.configure(compiler=self.doctor['native_compiler'])
        args = ('--toolchain', self.config)
        built = self.cli('build', *args)
        self.assertTrue(built['host_compatible'])
        meta = json.loads(Path(built['metadata']).read_text())
        self.assertEqual((meta['target'], meta['host']), (self.doctor['host'], self.doctor['host']))
        self.assertIn('driver', json.loads(meta['toolchain_inputs']))
        self.assertEqual(self.cli('run', *args)['stdout'], self.cli('eval')['stdout'])
        self.cli('test', *args)
        self.cli('test', '--target', 'web')
        self.assertTrue(self.cli('build', *args)['cached'])
        archive = self.cli('build', '--library', '--entry', 'main', *args)
        self.assertEqual(archive['kind'], 'static_library')
        self.assertGreater(Path(archive['executable']).stat().st_size, 100)

    def test_invalid_manifests_and_non_native_commands_reject(self):
        for value in ([], {}, {'schema':'bad','target':self.doctor['host']},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'flags':['-O0']},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'sysroot':'missing'},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'sqlite':{}},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'openssl':False}):
            with self.subTest(value=value):
                self.config.write_text(json.dumps(value))
                self.assertEqual(self.cli('build', '--toolchain', self.config, ok=False)['code'], 'E_TOOLCHAIN')
        self.configure()
        for command in (('check',), ('eval',), ('build','--target','web'), ('emit','--kind','typescript'), ('test','--interpreter-only')):
            self.assertEqual(self.cli(*command, '--toolchain', self.config, ok=False)['code'], 'E_OPTION')
        for target in ('wasm32-unknown-unknown','aarch64-apple-ios17.0','i386-apple-macosx13.0','aarch64-linux-gnu' if platform.system()=='Darwin' else 'x86_64-apple-macosx13.0'):
            self.assertEqual(self.cli('build', '--target', target, ok=False)['code'], 'E_TARGET')

    def mac_target(self):
        if platform.system() != 'Darwin':
            self.skipTest('macOS SDK cross-build')
        return ('x86_64' if platform.machine() in ('arm64','aarch64') else 'arm64') + '-apple-macosx13.0'

    def architecture(self, path, expected):
        result = subprocess.run(['xcrun','lipo','-archs',str(path)], capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), expected)

    def test_cross_artifacts_caches_profiles_and_archived_sources(self):
        target = self.mac_target()
        arch = target.split('-')[0]
        host = self.cli('build', '--profile', 'release')
        cross = self.cli('build', '--target', target, '--profile', 'release')
        self.assertFalse(cross['host_compatible'])
        self.assertEqual((cross['compiled_modules'], cross['reused_modules']), (1,0))
        self.assertNotEqual(cross['build_key'], host['build_key'])
        self.architecture(cross['executable'], arch)
        meta = json.loads(Path(cross['metadata']).read_text())
        ir = Path(cross['llvm']).read_text()
        self.assertIn('target triple = "' + cross['compiler_target'] + '"', ir)
        self.assertIn('target datalayout = "' + meta['data_layout'] + '"', ir)
        report = json.loads(Path(cross['compilation']).read_text())
        folder = Path(cross['executable']).parent
        for obj in folder.rglob('*.o'):
            self.architecture(obj, arch)
        self.architecture(str(cross['executable']) + '.dSYM/Contents/Resources/DWARF/app', arch)
        self.assertEqual(json.loads(Path(cross['debug_manifest']).read_text())['target'], target)
        warm = self.cli('build', '--target', target, '--profile', 'release')
        self.assertTrue(warm['cached'])
        self.assertTrue(self.cli('build', '--profile', 'release')['cached'])
        archive = self.cli('build', '--target', target, '--profile', 'release', '--library')
        self.architecture(archive['executable'], arch)
        profiled = self.cli('build', '--target', target, '--profile', 'profile', timeout=120)
        self.architecture(profiled['executable'], arch)
        self.assertIn('Tracy', Path(profiled['notices']).read_text())
        self.file.unlink()
        shutil.rmtree(folder)
        restored = self.cli('build', '--revision', cross['revision'], '--target', target, '--profile', 'release')
        self.assertEqual((restored['compiled_modules'], restored['reused_modules']), (0,1))
        self.assertEqual(restored['build_key'], cross['build_key'])
        self.architecture(restored['executable'], arch)
        self.assertEqual(json.loads(Path(restored['compilation']).read_text())['units'][0]['input_key'], report['units'][0]['input_key'])

    def test_foreign_run_test_debug_and_profile_are_not_host_results(self):
        target = self.mac_target()
        self.configure(target=target)
        for command in ('run','test','debug','profile'):
            for args in (('--target',target),('--toolchain',self.config)):
                self.assertEqual(self.cli(command, *args, ok=False)['code'], 'E_TARGET_RUN')
        self.assertEqual(self.cli('build','--target',self.doctor['host'],'--toolchain',self.config,ok=False)['code'], 'E_TOOLCHAIN')

    def test_target_sqlite_uses_explicit_sdk_headers_and_library(self):
        target = self.mac_target()
        sdk = Path(subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()).resolve()
        self.source('''module storage_target;
server fn main() -> unit !{db,io} { print(is_ok(store_keys(""))); }
''')
        self.assertEqual(self.cli('build','--target',target,ok=False)['code'], 'E_TARGET_LIBRARY')
        # Relative paths are anchored at the manifest, not the process cwd.
        (self.root / 'sdk').symlink_to(sdk, target_is_directory=True)
        self.configure(target=target, sysroot='sdk', sqlite={'include':'sdk/usr/include','library':'sdk/usr/lib/libsqlite3.tbd'})
        built = self.cli('build', '--toolchain', self.config)
        self.architecture(built['executable'], target.split('-')[0])
        meta = json.loads(Path(built['metadata']).read_text())
        inputs = json.loads(meta['toolchain_inputs'])
        self.assertEqual(inputs['sqlite_library'], str(sdk / 'usr/lib/libsqlite3.tbd'))
        self.assertIn('--sysroot=' + str(sdk), inputs['driver'])
        self.source('''module server_target;
import "std/http.nex" as http;
server fn handle(request:http::Request) -> http::Response { return http::Response(200,"ok","text/plain"); }
''')
        self.assertEqual(self.cli('build','--target','server','--toolchain',self.config,ok=False)['code'], 'E_TARGET_LIBRARY')

    def test_target_probe_rejects_driver_ignoring_requested_abi(self):
        target = self.mac_target()
        compiler = self.doctor['native_compiler']
        script = self.root / 'driver spy'
        log = self.root / 'driver calls.jsonl'
        script.write_text('''#!/usr/bin/env python3
import json, os, subprocess, sys
with open(LOG,'a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
if '-emit-llvm' in sys.argv:
    args=[x for x in sys.argv[1:] if not x.startswith('--target=')]
    result=subprocess.run([REAL,*args],capture_output=True)
    sys.stdout.buffer.write(result.stdout); sys.stderr.buffer.write(result.stderr)
    sys.exit(result.returncode)
os.execv(REAL,[REAL,*sys.argv[1:]])
'''.replace('LOG',repr(str(log))).replace('REAL',repr(compiler)))
        script.chmod(0o755)
        self.configure(target=target, compiler='driver spy')
        result = self.cli('build', '--toolchain',self.config, ok=False)
        self.assertEqual(result['code'], 'E_TARGET')
        calls = [json.loads(line) for line in log.read_text().splitlines()]
        self.assertIn('--target=' + target, next(c for c in calls if '-emit-llvm' in c))
        self.assertFalse(any('-c' in c for c in calls))


if __name__ == '__main__':
    unittest.main(verbosity=2)
