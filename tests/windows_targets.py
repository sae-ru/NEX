"""Real GNU/UCRT PE and archive builds; target execution is separately optional."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest

import support as harness

TOOLS = Path(os.environ['NEX_WINDOWS_TOOLCHAIN_ROOT']).resolve() if os.environ.get('NEX_WINDOWS_TOOLCHAIN_ROOT') else None


class WindowsConfiguration(harness.ToolchainCase):
    def test_unconfigured_and_unsupported_abis_reject(self):
        self.source('module windows; fn main()->i64 {return 0;}')
        for target in ('x86_64-w64-windows-gnu', 'aarch64-w64-windows-gnu',
                       'i686-w64-windows-gnu', 'arm64ec-w64-windows-gnu', 'x86_64-pc-windows-msvc'):
            self.assertEqual(self.cli('build', '--target', target, ok=False)['code'], 'E_TARGET')
        config = self.root / 'toolchain.json'
        config.write_text(json.dumps({'schema':'nex.toolchain/1', 'target':'x86_64-w64-windows-gnu',
                                     'windows':{'runtime':'ucrt-static'}}))
        self.assertEqual(self.cli('toolchain', config, ok=False)['code'], 'E_TOOLCHAIN')


@unittest.skipUnless(TOOLS, 'set NEX_WINDOWS_TOOLCHAIN_ROOT to an LLVM-MinGW UCRT installation')
class WindowsTargets(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'main.nex'}))
        self.config = self.root/'toolchain.json'
        self.notices = self.root/'runtime-notices.txt'
        files = [TOOLS/'LICENSE.TXT', *sorted((TOOLS/'x86_64-w64-mingw32/share/mingw32').glob('COPYING*'))]
        self.notices.write_text('\n\n'.join(str(p.relative_to(TOOLS))+'\n'+p.read_text() for p in files))
        self.source('''module windows_core;
trait Read {type Item; fn get(value:Self)->Read::Item<Self>;}
struct Box<T> {value:T;}
fn extract<T>(value:Box<T>)->T {return value.value;}
impl boxes<T>:Read for Box<T> {type Item=T;get=extract<T>;}
fn read<T:Read>(value:T)->Read::Item<T> {return Read<T>::get(value);}
pub fn answer()->i64 {
 let original:list<str>=["Я🧠2","tail"];
 let changed:list<str>=push(original,"extra");
 let captured:i64=read(Box<i64>(40));
 let add:fn(i64)->i64=fn(value:i64)->i64{return captured+value;};
 assert(len(original)==2 && len(changed)==3 && len(original[0])==3);
 assert(unwrap(decode_json<Box<str>>(encode_json(Box<str>(original[0])))).value=="Я🧠2");
 assert((false && 1/0==0)==false);
 assert(5e-324+0e0==5e-324);
 return add(2);
}
fn main()->unit!{io} {print(answer());print("Я🧠\\u0000tail");}
test fn semantics()->unit {assert(answer()==42);}
''')

    def configure(self, arch='x86_64', **fields):
        value={'schema':'nex.toolchain/1','target':arch+'-w64-windows-gnu',
               'compiler':str(TOOLS/'bin/clang++'),
               'linker':str(TOOLS/'bin/ld.lld'),'archiver':str(TOOLS/'bin/llvm-ar'),
               'sysroot':str(TOOLS/(arch+'-w64-mingw32')),
               'windows':{'runtime':'ucrt-static','notices':str(self.notices)}, **fields}
        self.config.write_text(json.dumps(value));return value

    def command(self, args, timeout=90):
        result=subprocess.run(list(map(str,args)),capture_output=True,text=True,timeout=timeout)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);return result.stdout

    def retain(self, built, name):
        if not os.environ.get('NEX_WINDOWS_TEST_OUTPUT'):return
        dest=Path(os.environ['NEX_WINDOWS_TEST_OUTPUT'])/name;dest.mkdir(parents=True,exist_ok=False)
        for key in ('executable','llvm','metadata','debug_manifest','notices'):
            path=Path(built[key]);shutil.copy2(path,dest/path.name)
        (dest/'result.json').write_text(json.dumps(built,indent=2))

    def test_real_pe_archives_abi_cache_and_archived_source(self):
        self.cli('test',timeout=120);self.cli('test','--target','web',timeout=120)
        host=self.cli('build','--profile','release');keys={host['build_key']}
        symbol=self.cli('context','--symbol','answer')['native_symbol']
        bridge=self.root/'bridge.cpp';bridge.write_text('extern "C" long long '+symbol+'();\nint main(){return '+symbol+'()==42?0:1;}\n')
        for arch,machine in (('x86_64','IMAGE_FILE_MACHINE_AMD64'),('aarch64','IMAGE_FILE_MACHINE_ARM64')):
            self.configure(arch);inspected=self.cli('toolchain',self.config)
            self.assertFalse(inspected['host_compatible']);self.assertEqual(inspected['manifest']['windows']['runtime'],'ucrt-static')
            self.assertIn(str(self.notices.resolve()),inspected['inputs']['files'])
            for profile in ('debug','release'):
                built=self.cli('build','--toolchain',self.config,'--profile',profile,timeout=180)
                self.assertFalse(built['host_compatible']);self.assertEqual(Path(built['executable']).name,'app.exe')
                self.assertNotIn(built['build_key'],keys);keys.add(built['build_key'])
                self.assertTrue(self.cli('build','--toolchain',self.config,'--profile',profile)['cached'])
                metadata=json.loads(Path(built['metadata']).read_text());inputs=json.loads(metadata['toolchain_inputs'])
                self.assertEqual((inputs['sqlite_library'],inputs['openssl_ssl'],inputs['debug_packager']),('','',''))
                ir=Path(built['llvm']).read_text();self.assertIn('target triple = "'+built['compiler_target']+'"',ir)
                self.assertIn('target datalayout = "'+metadata['data_layout']+'"',ir)
                for path in [Path(built['executable']),*Path(built['executable']).parent.rglob('*.o')]:
                    self.assertIn(machine,self.command([TOOLS/'bin/llvm-readobj','--file-headers',path]))
                imports=self.command([TOOLS/'bin/llvm-readobj','--coff-imports',built['executable']])
                for line in imports.splitlines():
                    if line.strip().startswith('Name:'):
                        name=line.split(':',1)[1].strip().lower()
                        self.assertTrue(name=='kernel32.dll' or name.startswith('api-ms-win-crt-'),name)
                self.assertIn(self.notices.read_text(),Path(built['notices']).read_text())
                self.retain(built,arch+'-'+profile)
            archive=self.cli('build','--toolchain',self.config,'--library','--entry','answer','--profile','release',timeout=180)
            self.assertIn(machine,self.command([TOOLS/'bin/llvm-readobj','--file-headers',archive['executable']]))
            image=self.root/(arch+'-archive.exe')
            self.command([TOOLS/('bin/'+arch+'-w64-mingw32-clang++'),'--target='+arch+'-w64-windows-gnu',
                          '--sysroot='+str(TOOLS/(arch+'-w64-mingw32')),'-static',bridge,archive['executable'],'-o',image])
            self.assertIn(machine,self.command([TOOLS/'bin/llvm-readobj','--file-headers',image]))
        self.file.unlink();shutil.rmtree(Path(built['executable']).parent)
        restored=self.cli('build','--revision',built['revision'],'--toolchain',self.config,'--profile','release',timeout=180)
        self.assertEqual(restored['build_key'],built['build_key']);self.assertGreater(restored['reused_functions'],0)

    def test_foreign_execution_and_unported_runtime_boundaries_reject(self):
        self.configure()
        for command in ('run','test','debug','profile'):
            self.assertEqual(self.cli(command,'--toolchain',self.config,ok=False)['code'],'E_TARGET_RUN')
        self.assertEqual(self.cli('build','--toolchain',self.config,'--profile','profile',ok=False)['code'],'E_TARGET')
        self.source('module storage;server fn main()->unit!{db} {assert(is_ok(store_keys("")));}')
        self.assertEqual(self.cli('build','--toolchain',self.config,ok=False)['code'],'E_TARGET_LIBRARY')
        for source in (
            'server fn main()->unit!{fs} {assert(is_ok(file_read_text("input")));}',
            'server extern fn opaque()->i64!{ffi}=foreign("x","y","'+'0'*64+'"); server fn main()->i64!{ffi} {return opaque();}'
        ):
            self.source('module unavailable;'+source)
            self.assertEqual(self.cli('build','--toolchain',self.config,ok=False)['code'],'E_TARGET')
        self.source('module arithmetic;fn main()->i64{return 0;}')
        self.assertEqual(self.cli('package','--toolchain',self.config,'--directory',self.root/'package',ok=False)['code'],'E_TARGET')
        self.assertFalse((self.root/'package').exists())

    def test_required_inputs_wrong_driver_and_notice_identity(self):
        for field in ('compiler','linker','archiver','sysroot'):
            value=self.configure();del value[field];self.config.write_text(json.dumps(value))
            self.assertEqual(self.cli('build','--toolchain',self.config,ok=False)['code'],'E_TOOLCHAIN')
        self.configure(windows={'runtime':'msvcrt','notices':str(self.notices)})
        self.assertEqual(self.cli('build','--toolchain',self.config,ok=False)['code'],'E_TARGET')
        real=self.cli('doctor')['native_compiler'];driver=self.root/'wrong driver'
        driver.write_text('#!/usr/bin/env python3\nimport os,sys\nreal='+repr(real)+'\nargs=[x for x in sys.argv[1:] if not x.startswith(("--target=","--sysroot="))]\nos.execv(real,[real,*args])\n')
        driver.chmod(0o755);self.configure(compiler=str(driver))
        self.assertEqual(self.cli('build','--toolchain',self.config,ok=False)['code'],'E_TARGET')
        self.configure();before=self.cli('toolchain',self.config);a=self.cli('build','--toolchain',self.config,timeout=180)
        self.notices.write_text(self.notices.read_text()+'\nAdditional reviewed runtime notice.\n')
        after=self.cli('toolchain',self.config);self.assertNotEqual(before['hash'],after['hash'])
        b=self.cli('build','--toolchain',self.config,timeout=180);self.assertNotEqual(a['build_key'],b['build_key'])
        self.assertIn('Additional reviewed runtime notice.',Path(b['notices']).read_text())


if __name__ == '__main__':
    unittest.main()
