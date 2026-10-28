"""Real native cross-build artifacts, ABI isolation and explicit toolchain inputs."""
import json
import os
from pathlib import Path
import platform
import re
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

    @unittest.skipUnless(platform.system() == 'Darwin', 'Mach-O run-path selection')
    def test_selected_sqlite_rpath_runs_with_literal_dependency_directory(self):
        directory=self.root/'selected, библиотека % 🧠';directory.mkdir()
        library=directory/'libsqlite.bundle.dylib'
        shutil.copy2(self.doctor['native_sqlite_library'],library)
        subprocess.run(['/usr/bin/install_name_tool','-id','@rpath/'+library.name,str(library)],check=True,capture_output=True)
        subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(library)],check=True,capture_output=True)
        self.configure(sqlite={'include':self.doctor['native_sqlite_include'],'library':str(library)})
        self.source('''module selected_store;
server fn main() -> unit !{db,io} {
  assert(unwrap(store_put("item","persistent 🧠")));
  print(unwrap(store_get("item")));
}
''')
        built=self.cli('build','--toolchain',self.config)
        run=subprocess.run([built['executable']],env={'PATH':'/usr/bin:/bin','NEX_DATABASE':str(self.root/'data.sqlite'),'NEX_STORAGE_OWNER':'alice'},capture_output=True,text=True,timeout=15)
        self.assertEqual((run.returncode,run.stdout),(0,'persistent 🧠\n'),run.stderr)
        commands=subprocess.check_output(['/usr/bin/otool','-l',built['executable']],text=True)
        self.assertIn('path '+str(directory.resolve())+' (offset ',commands)
        self.assertTrue(self.cli('build','--toolchain',self.config)['cached'])

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

    @unittest.skipUnless(platform.system() == 'Linux', 'ELF runtime library selection')
    def test_selected_sqlite_is_actually_loaded_from_literal_elf_directory(self):
        original=self.doctor['native_sqlite_library']
        dynamic=subprocess.check_output(['readelf','-d',original],text=True)
        soname=re.search(r'\(SONAME\).*?\[([^]]+)\]',dynamic).group(1)
        directory=self.root/'selected, библиотека % 🧠';directory.mkdir()
        library=directory/soname;shutil.copy2(original,library)
        # This fixture is a complete selected SDK, including private ICU/C++
        # dependencies whose original ELF RUNPATH is relative to their owner.
        pending=[Path(original).resolve()];seen=set()
        while pending:
            image=pending.pop()
            if image in seen:continue
            seen.add(image)
            listing=subprocess.check_output(['ldd',image],text=True)
            for name,filename in re.findall(r'^\s*(\S+)\s*=>\s*(.*?)\s+\(0x',listing,re.M):
                dependency=Path(filename).resolve()
                if any(Path(root).resolve() in dependency.parents for root in ('/lib','/lib64','/usr/lib','/usr/lib64')):continue
                destination=directory/Path(name).name
                if not destination.exists():shutil.copy2(dependency,destination)
                pending.append(dependency)
        self.configure(sqlite={'include':self.doctor['native_sqlite_include'],'library':str(library)})
        self.source('''module selected_elf_store;
server fn main() -> unit !{db,io} {
  assert(unwrap(store_put("item","persistent 🧠")));
  print(unwrap(store_get("item")));
}
''')
        built=self.cli('build','--toolchain',self.config)
        environment={'PATH':'/usr/bin:/bin','NEX_DATABASE':str(self.root/'data.sqlite'),'NEX_STORAGE_OWNER':'alice'}
        run=subprocess.run([built['executable']],env=environment,capture_output=True,text=True,timeout=15)
        self.assertEqual((run.returncode,run.stdout),(0,'persistent 🧠\n'),run.stderr)
        dependencies=subprocess.check_output(['ldd',built['executable']],env=environment,text=True)
        actual=re.search(r'^\s*'+re.escape(soname)+r'\s*=>\s*(.*?)\s+\(0x',dependencies,re.M)
        self.assertIsNotNone(actual,dependencies)
        self.assertEqual(Path(actual.group(1)).resolve(),library.resolve())
        self.assertTrue(self.cli('build','--toolchain',self.config)['cached'])
        invalid=self.root/'invalid:elf';invalid.mkdir();shutil.copy2(original,invalid/soname)
        self.configure(sqlite={'include':self.doctor['native_sqlite_include'],'library':str(invalid/soname)})
        self.assertEqual(self.cli('build','--toolchain',self.config,ok=False)['code'],'E_TARGET_LIBRARY')

    def test_readonly_manifest_roundtrip_preserves_selected_tool_aliases(self):
        tools=self.root/'physical tools';tools.mkdir()
        alias=self.root/'linked tools';alias.symlink_to(tools,target_is_directory=True)
        fields={}
        for key,doctor_key,name in [('compiler','native_compiler','clang++'),
                                    ('archiver','native_archiver','llvm-ar'),
                                    ('linker','native_linker','ld.lld'),
                                    ('debug_packager','native_debug_packager','dsymutil')]:
            if self.doctor[doctor_key]:
                (tools/name).symlink_to(self.doctor[doctor_key]);fields[key]=str(alias/name)
        self.configure(**fields)
        inspected=self.cli('toolchain',self.config)
        for key,value in fields.items():
            self.assertEqual(inspected['manifest'][key],str(tools.resolve()/Path(value).name))
        captured=self.root/'captured.json';captured.write_text(json.dumps(inspected['manifest']))
        again=self.cli('toolchain',captured)
        self.assertEqual(again['hash'],inspected['hash']);self.assertEqual(again['inputs'],inspected['inputs'])
        self.assertFalse((self.root/'.nex').exists())

    def test_readonly_default_manifest_roundtrip_has_the_same_fingerprint(self):
        self.configure()
        inspected=self.cli('toolchain',self.config)
        self.config.write_text(json.dumps(inspected['manifest']))
        self.assertEqual(self.cli('toolchain',self.config)['hash'],inspected['hash'])
        self.assertFalse((self.root/'.nex').exists())

    def test_invalid_manifests_and_non_native_commands_reject(self):
        for value in ([], {}, {'schema':'bad','target':self.doctor['host']},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'flags':['-O0']},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'sysroot':'missing'},
                      {'schema':'nex.toolchain/1','target':self.doctor['host'],'linker':'missing'},
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

    def test_explicit_linker_runs_is_fingerprinted_and_is_not_an_archiver(self):
        self.configure()
        baseline=self.cli('toolchain',self.config)
        real=baseline['manifest'].get('linker') or '/usr/bin/ld'
        if not Path(real).is_file():self.skipTest('no configured host linker')
        log=self.root/'linker calls.jsonl';driver=self.root/'linker spy'
        driver.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(LOG,'a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')
os.execv(REAL,[REAL,*sys.argv[1:]])
'''.replace('LOG',repr(str(log))).replace('REAL',repr(real)))
        driver.chmod(0o755)
        self.configure(linker=str(driver))
        inspected=self.cli('toolchain',self.config)
        self.assertFalse(log.exists())
        self.assertEqual(inspected['inputs']['schema'],'nex.toolchain-snapshot/2')
        self.assertIn(str(driver.resolve()),inspected['inputs']['files'])
        built=self.cli('build','--toolchain',self.config)
        metadata=json.loads(Path(built['metadata']).read_text())
        self.assertEqual(metadata['linker'],inspected['manifest']['linker'])
        arguments=json.loads(log.read_text().splitlines()[0])
        self.assertEqual(Path(arguments[arguments.index('-o')+1]).name,Path(built['executable']).name)
        run=subprocess.run([built['executable']],capture_output=True,text=True,timeout=15)
        self.assertEqual((run.returncode,run.stdout),(0,self.cli('eval')['stdout']),run.stderr)
        self.assertTrue(self.cli('build','--toolchain',self.config)['cached'])
        self.assertEqual(len(log.read_text().splitlines()),1)
        driver.write_text(driver.read_text()+'\n# reviewed linker revision\n')
        self.assertNotEqual(self.cli('toolchain',self.config)['hash'],inspected['hash'])
        changed=self.cli('build','--toolchain',self.config)
        self.assertNotEqual(changed['build_key'],built['build_key'])
        log.unlink()
        archive=self.cli('build','--toolchain',self.config,'--library')
        self.assertEqual(archive['kind'],'static_library')
        self.assertFalse(log.exists())

    def test_archive_in_literal_unicode_percent_path_links_into_a_native_host(self):
        project=self.root/'архив % 🧠';project.mkdir()
        source=project/'main.nex';source.write_text('module embedded; pub fn answer() -> i64 { return 40 + 2; }')
        built=self.cli('build',source,'--library','--entry','answer',cwd=project)
        context=self.cli('context','--symbol','answer',cwd=project)
        host=project/'host.cpp';host.write_text('#include <iostream>\nextern "C" long long '+context['native_symbol']+'();\nint main(){std::cout << '+context['native_symbol']+'() << "\\n";}\n')
        executable=project/'host-app'
        command=[self.doctor['native_compiler'],'-std=c++20',str(host),built['executable'],'-pthread','-o',str(executable)]
        metadata=json.loads(Path(built['metadata']).read_text())
        # Match NEX's selected linker, retaining its percent-path staging rule.
        # A relative host output avoids LLVM's temporary-file template expansion.
        if metadata.get('linker'):
            command += ['--ld-path='+metadata['linker']]
            command[command.index('-o')+1]=executable.name
        result=subprocess.run(command,cwd=project,capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run([str(executable)],capture_output=True,text=True,timeout=15)
        self.assertEqual((result.returncode,result.stdout),(0,'42\n'),result.stderr)
        self.assertTrue(self.cli('build',source,'--library','--entry','answer',cwd=project)['cached'])

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
