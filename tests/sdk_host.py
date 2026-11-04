"""Relative host-SDK selection, real native tools and rejected broken bundles."""
from host_fixture import python_executable
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import support as harness


class HostSDK(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve()
        self.file = self.root / 'main.nex'

    def stage(self):
        self.original = self.root / 'before relocation'
        self.prefix = self.original
        (self.prefix / 'bin').mkdir(parents=True)
        shutil.copy2(harness.NEX, self.prefix / 'bin/nex')
        self.descriptor = self.prefix / 'share/nex/sdk-host.json'
        self.descriptor.parent.mkdir(parents=True)
        self.log = self.root / 'tool calls.jsonl'
        doctor = self.cli('doctor')
        tools = {}
        for key, field in [('compiler', 'native_compiler'), ('archiver', 'native_archiver'),
                           ('debug_packager', 'native_debug_packager'), ('linker', 'native_linker')]:
            if not doctor[field]:
                continue
            name = {'compiler': 'clang++', 'linker': 'ld.lld'}.get(key, key)
            relative = Path('tools') / name
            wrapper = self.prefix / relative
            wrapper.parent.mkdir(exist_ok=True)
            wrapper=python_executable(wrapper,'''#!/usr/bin/env python3
import json, os, sys
with open(LOG, 'a') as output: output.write(json.dumps([NAME, sys.argv[0], sys.argv[1:]])+'\\n')
os.execv(REAL, [REAL, *sys.argv[1:]])
'''.replace('LOG', repr(str(self.log))).replace('NAME', repr(key)).replace('REAL', repr(doctor[field])),harness.native_fixture_compiler())
            wrapper.chmod(0o755)
            tools[key] = wrapper.relative_to(self.prefix).as_posix()
        # These tests exercise tool selection with real compiler/archiver/debug
        # subprocesses. The maintained bundle acceptance separately exercises
        # real relocated headers/libraries and dynamic-loader independence.
        (self.prefix / 'deps/include').mkdir(parents=True)
        (self.prefix / 'deps/include/sqlite3.h').write_text('/* fingerprint fixture */\n', newline="\n")
        (self.prefix / 'deps/include/openssl').mkdir()
        (self.prefix / 'deps/include/openssl/ssl.h').write_text('/* fingerprint fixture */\n', newline="\n")
        for name in ['sqlite', 'ssl', 'crypto']:
            (self.prefix / 'deps' / name).write_bytes(b'host SDK selection fixture')
        self.config = {'schema': 'nex.sdk-host/1', 'tools': tools,
                       'sqlite': {'include': 'deps/include', 'library': 'deps/sqlite'},
                       'openssl': {'include': 'deps/include', 'ssl': 'deps/ssl', 'crypto': 'deps/crypto'}}
        if os.name=='nt':
            shutil.copytree(doctor['native_sysroot'],self.prefix/'windows-sysroot',symlinks=False)
            shutil.copy2(doctor['native_windows_notices'],self.prefix/'runtime-notices.txt')
            self.config['windows']={'sysroot':'windows-sysroot','runtime':'ucrt-static','notices':'runtime-notices.txt'}
        self.descriptor.write_text(json.dumps(self.config), newline="\n")

    def staged(self, *args, ok=True, env=None):
        result = subprocess.run([str(self.prefix / 'bin/nex'), *map(str, args), '--json'],
                                cwd=self.root, env={**os.environ, 'NEX_RESOURCE_DIR': str(harness.REPO), **(env or {})},
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def test_moved_sdk_builds_runs_and_archives_with_selected_tools(self):
        self.stage()
        moved = self.root / 'перенесённый SDK % 🧠'
        self.prefix.rename(moved)
        self.prefix = moved
        self.assertFalse(self.original.exists())
        doctor = self.staged('doctor')
        for name, field in [('compiler', 'native_compiler'), ('archiver', 'native_archiver'),
                            ('debug_packager', 'native_debug_packager'), ('linker', 'native_linker')]:
            if name in self.config['tools']:
                self.assertEqual(doctor[field], str(moved / self.config['tools'][name]))
        self.source('module moved; pub fn main() -> unit !{io} { print(42); }')
        self.assertEqual(self.staged('run')['stdout'], '42\n')
        archive = self.staged('build', '--library')
        self.assertGreater(Path(archive['executable']).stat().st_size, 100)
        self.assertTrue(self.staged('build', '--library')['cached'])
        manifest = self.root / 'target.json'
        manifest.write_text(json.dumps(harness.host_toolchain_defaults(doctor)), newline="\n")
        inspected = self.staged('toolchain', manifest)
        archiver = moved / self.config['tools']['archiver']
        self.assertIn(str(archiver), inspected['inputs']['files'])
        archiver.write_bytes(archiver.read_bytes()+b'\n# revised archive tool\n') if os.name=='nt' else archiver.write_text(archiver.read_text() + '\n# revised archive tool\n', newline="\n")
        self.assertNotEqual(inspected['hash'], self.staged('toolchain', manifest)['hash'])
        self.assertFalse(self.staged('build', '--library')['cached'])
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertTrue(any(call[0] == 'archiver' for call in calls))
        self.assertTrue(all(Path(call[1]).is_relative_to(moved) for call in calls))

    def test_moved_direct_C11_and_CPP20_fixtures_use_the_selected_sysroot(self):
        self.stage()
        moved=self.root/'fixture SDK % 🧠';self.prefix.rename(moved);self.prefix=moved
        doctor=self.staged('doctor')
        import importlib.util
        spec=importlib.util.spec_from_file_location('selected_sdk_fixture',harness.REPO/'tools/sdk_host.py')
        helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)
        include=Path(doctor['native_sysroot'])/'include' if os.name=='nt' else self.root/'fixture-include'
        include.mkdir(exist_ok=True)
        # This header is absent from the driver's original installation. A
        # Windows compile that ignores the moved sysroot must fail to find it.
        (include/'nex_selected_fixture.h').write_text('#define NEX_SELECTED_FIXTURE_VALUE 38\n',newline='\n')
        c=self.root/'fixture.c';cpp=self.root/'fixture.cpp';obj=self.root/'fixture.o'
        exe=self.root/('fixture.exe' if os.name=='nt' else 'fixture')
        c.write_text('#include <string.h>\n#include <nex_selected_fixture.h>\nint fixture(void){return NEX_SELECTED_FIXTURE_VALUE+(int)strlen("NEX!");}\n',newline='\n')
        cpp.write_text('#include <array>\n#include <iostream>\nextern "C" int fixture(void);\nint main(){std::array<int,1> value{fixture()};if(value[0]!=42)return 1;std::cout<<value[0]<<"\\n";}\n',newline='\n')
        # The resource producer uses the sibling C driver, while most other
        # fixtures select clang++ with -x c. Exercise both actual driver paths.
        real_c=Path(self.cli('doctor')['native_compiler']).with_name(helper.executable_name('clang'))
        c_driver=python_executable(Path(doctor['native_compiler']).with_name(helper.executable_name('clang')),
            '#!/usr/bin/env python3\nimport os,sys\nos.execv(REAL,[REAL,*sys.argv[1:]])\n'.replace('REAL',repr(str(real_c))),
            harness.native_fixture_compiler())
        includes=[] if os.name=='nt' else ['-I'+str(include)]
        for command in [[c_driver,'-std=c11',*includes,'-c',c,'-o',obj],
                        [doctor['native_compiler'],'-x','c','-std=c11',*includes,'-c',c,'-o',obj],
                        [doctor['native_compiler'],'-std=c++20',cpp,obj,'-o',exe]]:
            result=helper.compile_fixture(command,doctor=doctor,cwd=self.root,capture_output=True,text=True,timeout=180)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        for path in [c,cpp,obj]:path.unlink()
        result=subprocess.run([exe],cwd=self.root,env=helper.deployed_environment(NEX_RESOURCE_DIR=str(self.root/'absent')),capture_output=True,text=True,timeout=30)
        self.assertEqual((result.returncode,result.stdout),(0,'42\n'),result.stderr)

    def test_invalid_descriptor_never_falls_back_to_build_machine_paths(self):
        self.stage()
        self.source('module bad_sdk; fn main() -> i64 { return 0; }')
        outside = self.root / 'outside tool'
        outside.write_text('unused', newline="\n")
        (self.prefix / 'escape').symlink_to(outside)
        variants = []
        for compiler in ['missing', '../outside tool', str(outside), 'escape']:
            config = json.loads(json.dumps(self.config));config['tools']['compiler'] = compiler
            variants.append(config)
        variants += [{**self.config, 'unknown': True}, {**self.config, 'schema': 'bad'},
                     {**self.config, 'sqlite': {}}, {**self.config, 'tools': []}]
        for config in variants:
            with self.subTest(config=config):
                self.descriptor.write_text(json.dumps(config), newline="\n")
                self.assertEqual(self.staged('doctor', ok=False)['code'], 'E_SDK')
                self.assertEqual(self.staged('build', ok=False)['code'], 'E_SDK')
        self.assertFalse(self.log.exists())
        self.descriptor.write_text('{', newline="\n")
        self.assertEqual(self.staged('doctor', ok=False)['code'], 'E_SDK')

    def test_explicit_archive_tool_is_captured_and_used(self):
        self.stage()
        self.source('module archive_selection; pub fn main() -> i64 { return 1; }')
        doctor = self.staged('doctor')
        override = self.root / 'explicit archiver'
        shutil.copy2(self.prefix / self.config['tools']['archiver'], override)
        config = self.root / 'target.json'
        config.write_text(json.dumps({**harness.host_toolchain_defaults(doctor), 'archiver': str(override)}), newline="\n")
        inspected = self.staged('toolchain', config)
        self.assertIn(str(override), inspected['inputs']['files'])
        self.staged('build', '--library', '--toolchain', config)
        calls = [json.loads(line) for line in self.log.read_text().splitlines()]
        self.assertTrue(any(call[0] == 'archiver' and call[1] == str(override) for call in calls))


if __name__ == '__main__':
    unittest.main()
