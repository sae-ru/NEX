"""Actual Windows environment/SQLite code generation; no emulator is launched."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import support as harness

TOOLS = Path(os.environ['NEX_WINDOWS_TOOLCHAIN_ROOT']).resolve() if os.environ.get('NEX_WINDOWS_TOOLCHAIN_ROOT') else None
SQLITE = Path(os.environ['NEX_WINDOWS_SQLITE_ROOT']).resolve() if os.environ.get('NEX_WINDOWS_SQLITE_ROOT') else None
ENVIRONMENT = '''module windows_environment;
server fn main()->unit!{io} {
 assert(unwrap(read_env("NEX065_Я🧠"))=="значение 🧠");
 assert(unwrap(read_env("NEX065_EMPTY"))=="");
 assert(!is_ok(read_env("NEX065_MISSING")));
 assert(!is_ok(read_env("a=b")) && !is_ok(read_env("")));
 print(unwrap(read_env("NEX065_Я🧠")));
 print(read_env("NEX065_MISSING"));
}
'''
STORAGE = '''module windows_storage;
pub server fn persist()->i64!{db} {
 assert(is_ok(store_put("library", "retained")));
 return 42;
}
server fn main()->unit!{db,io} {
 let owner:str=unwrap(read_env("NEX_STORAGE_OWNER"));
 let mode:str=unwrap(read_env("NEX065_MODE"));
 if mode=="seed" {
  assert(!is_ok(store_get("key")));
  assert(is_ok(store_put("key",owner)));
 } else {
  assert(unwrap(store_get("key"))==owner);
 }
 assert(len(unwrap(store_keys("key")))==1);
 assert(persist()==42);
 print(unwrap(store_get("key")));
}
'''
NO_GRANT = '''module windows_without_grant;
server fn main()->unit!{db,io} {print(store_get("key"));}
'''


class WindowsRuntimeDescriptor(harness.ToolchainCase):
    def test_capabilities_and_language_semantics(self):
        value=self.cli('describe')['windows_core_target']
        self.assertTrue(value['environment_access'] and value['database'] and value['explicit_target_sqlite'])
        self.assertEqual(value['environment_encoding'],'strict_utf8_utf16')
        self.assertFalse(value['files'] or value['source_foreign_loading'] or value['host_execution'])
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}))
        self.source('module boundary;client fn main()->result<str>!{io}{return read_env("x");}')
        self.cli('check',ok=False)
        self.source('module boundary;server fn main()->result<str>{return read_env("x");}')
        self.cli('check',ok=False)


@unittest.skipUnless(TOOLS,'set NEX_WINDOWS_TOOLCHAIN_ROOT for real Windows runtime cross-builds')
class WindowsRuntimeBuilds(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}))
        self.config=self.root/'toolchain.json';self.notices=self.root/'notices.txt'
        licenses=[TOOLS/'LICENSE.TXT',*sorted((TOOLS/'x86_64-w64-mingw32/share/mingw32').glob('COPYING*'))]
        self.notices.write_text('\n\n'.join(str(p.relative_to(TOOLS))+'\n'+p.read_text() for p in licenses))

    def configure(self,arch,sqlite=False):
        value={'schema':'nex.toolchain/1','target':arch+'-w64-windows-gnu','compiler':str(TOOLS/'bin/clang++'),
               'linker':str(TOOLS/'bin/ld.lld'),'archiver':str(TOOLS/'bin/llvm-ar'),
               'sysroot':str(TOOLS/(arch+'-w64-mingw32')),'windows':{'runtime':'ucrt-static','notices':str(self.notices)}}
        if sqlite:
            self.assertIsNotNone(SQLITE)
            value['sqlite']={'include':str(SQLITE/'sqlite-amalgamation-3540100'),'library':str(SQLITE/arch/'libsqlite3.a')}
        self.config.write_text(json.dumps(value));return value

    def command(self,args):
        result=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);return result.stdout

    def retain(self,built,name):
        if not os.environ.get('NEX_WINDOWS_RUNTIME_OUTPUT'):return
        dest=Path(os.environ['NEX_WINDOWS_RUNTIME_OUTPUT'])/name;dest.mkdir(parents=True,exist_ok=False)
        for key in ('executable','llvm','metadata','debug_manifest','notices'):
            path=Path(built[key]);shutil.copy2(path,dest/path.name)
        (dest/'result.json').write_text(json.dumps(built,indent=2)+'\n')

    def build_cases(self,source,name,sqlite=False):
        self.source(source);previous=set()
        for arch,machine in (('x86_64','IMAGE_FILE_MACHINE_AMD64'),('aarch64','IMAGE_FILE_MACHINE_ARM64')):
            config=self.configure(arch,sqlite);snapshot=self.cli('toolchain',self.config)
            if sqlite:
                for path in (Path(config['sqlite']['include'])/'sqlite3.h',Path(config['sqlite']['library'])):
                    self.assertIn(str(path.resolve()),snapshot['inputs']['files'])
            for profile in ('debug','release'):
                built=self.cli('build','--toolchain',self.config,'--profile',profile,timeout=240)
                self.assertNotIn(built['build_key'],previous);previous.add(built['build_key'])
                self.assertTrue(self.cli('build','--toolchain',self.config,'--profile',profile,timeout=120)['cached'])
                self.assertIn(machine,self.command([TOOLS/'bin/llvm-readobj','--file-headers',built['executable']]))
                imports=self.command([TOOLS/'bin/llvm-readobj','--coff-imports',built['executable']])
                for line in imports.splitlines():
                    if line.strip().startswith('Name:'):
                        dll=line.split(':',1)[1].strip().lower()
                        self.assertTrue(dll=='kernel32.dll' or dll.startswith('api-ms-win-crt-'),dll)
                metadata=json.loads((Path(built['executable']).parent/'build.json').read_text())
                projection=Path(metadata['runtime_source_projection'])
                self.assertEqual((projection/'nex_platform.h').read_bytes(),(harness.REPO/'runtime/nex_platform.h').read_bytes())
                self.assertFalse((projection/'nex_files_windows.h').exists())
                self.retain(built,name+'-'+arch+'-'+profile)
        return built

    def test_unicode_environment_executables(self):
        self.build_cases(ENVIRONMENT,'environment')

    @unittest.skipUnless(SQLITE,'set NEX_WINDOWS_SQLITE_ROOT for matching target SQLite3.54.1 libraries')
    def test_unicode_storage_executables_archive_and_source_replay(self):
        last=self.build_cases(STORAGE,'storage',True)
        symbol=self.cli('context','--symbol','persist')['native_symbol']
        bridge=self.root/'bridge.cpp';bridge.write_text('extern "C" long long '+symbol+'();\nint main(){return '+symbol+'()==42?0:1;}\n')
        for arch in ('x86_64','aarch64'):
            config=self.configure(arch,True)
            archive=self.cli('build','--toolchain',self.config,'--library','--entry','persist','--profile','release',timeout=240)
            self.command([TOOLS/'bin/clang++','--target='+config['target'],'--sysroot='+config['sysroot'],'-static',bridge,archive['executable'],config['sqlite']['library'],'-o',self.root/(arch+'-library.exe')])
        self.file.unlink();shutil.rmtree(Path(last['executable']).parent)
        rebuilt=self.cli('build','--revision',last['revision'],'--toolchain',self.config,'--profile','release',timeout=240)
        self.assertEqual(rebuilt['build_key'],last['build_key']);self.assertGreater(rebuilt['reused_functions'],0)
        self.source(NO_GRANT);self.configure('x86_64',True)
        self.retain(self.cli('build','--toolchain',self.config,'--profile','release',timeout=240),'storage-no-grant-x86_64-release')


if __name__=='__main__':unittest.main()
