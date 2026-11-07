"""Selected runtime bindings over real LLVM-produced ELF images; no input dlopen."""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

PROBE, CLANG, LLD, AR = map(Path, sys.argv[1:5])
LOADER = '--loader' in sys.argv[5:]
sys.argv[1:] = []
TARGETS = ('x86_64-unknown-linux-gnu', 'i386-unknown-linux-gnu',
           'powerpc-unknown-linux-gnu', 'powerpc64-unknown-linux-gnu')


class RuntimePaths(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex-runtime-paths-')
        self.root = Path(self.temp.name).resolve()
        self.counter = 0

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, arguments, *, expected=0):
        env = {k: v for k, v in os.environ.items() if not k.startswith('LD_')}
        result = subprocess.run(list(map(str, arguments)), capture_output=True,
                                text=True, timeout=30, env=env)
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        return result

    def dso(self, directory, role, value=1, *, target=TARGETS[0], soname=True):
        directory = self.root / directory
        directory.mkdir(parents=True, exist_ok=True)
        self.counter += 1
        source = self.root / ('input-%d.c' % self.counter)
        source.write_text('int %s_value(void){return %d;}\n' % (role, value))
        image = directory / ('lib%s-%d.so.1' % (role, self.counter))
        # Keep the producer independent of its output-path handling (some
        # macOS ELF LLD builds cannot create Unicode output paths). The planner
        # still reads the real ELF bytes from the exact requested directory.
        produced = self.root / ('produced-%d.so' % self.counter)
        name = 'lib%s.so.1' % role
        command = [CLANG, '--target=' + target, '--ld-path=' + str(LLD),
                   '-nostdlib', '-fPIC', '-shared', source, '-o', produced]
        if soname:
            command += ['-Xlinker', '-soname', '-Xlinker', name]
        self.run_tool(command)
        shutil.move(produced, image)
        if soname:
            (directory / name).symlink_to(image.name)
        return image

    def paths(self, sqlite='', ssl='', crypto='', *, target=TARGETS[0],
              storage=True, foreign=False, server=True, ok=True):
        result = self.run_tool([PROBE, target, sqlite, ssl, crypto,
                                str(int(storage)), str(int(foreign)), str(int(server))],
                               expected=0 if ok else 1)
        value = json.loads(result.stdout)
        self.assertEqual(value['ok'], ok)
        if not ok:
            self.assertEqual(value['code'], 'E_TARGET_LIBRARY')
        return value.get('paths', value.get('message'))

    def cohort(self, *, target=TARGETS[0], suffix=''):
        return (self.dso('a-sqlite'+suffix, 'sqlite', 20, target=target),
                self.dso('z-openssl'+suffix, 'ssl', 22, target=target),
                self.dso('z-openssl'+suffix, 'crypto', 0, target=target))

    def test_selected_SONAME_precedes_a_byte_identical_copy_in_another_selected_directory(self):
        for i, target in enumerate(TARGETS):
            with self.subTest(target=target):
                sqlite, ssl, crypto = self.cohort(target=target, suffix=str(i))
                shutil.copy2(ssl, sqlite.parent / 'libssl.so.1')
                paths = self.paths(sqlite, ssl, crypto, target=target)
                self.assertEqual(paths, [str(ssl.parent), str(sqlite.parent)])

    def test_conflicting_selected_SONAMEs_are_rejected_instead_of_silently_switching_a_dependency(self):
        sqlite, ssl, crypto = self.cohort()
        shutil.copy2(ssl, sqlite.parent / 'libssl.so.1')
        shutil.copy2(sqlite, ssl.parent / 'libsqlite.so.1')
        message = self.paths(sqlite, ssl, crypto, ok=False)
        self.assertIn('conflicting SONAME search requirements', message)
        self.assertIn(str(sqlite.parent), message)
        self.assertIn(str(ssl.parent), message)

    def test_a_selected_alias_must_name_the_selected_image(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                sqlite, ssl, crypto = self.cohort(suffix=str(missing))
                alias = ssl.parent / 'libssl.so.1'
                alias.unlink()
                if not missing:
                    wrong = self.dso('wrong'+str(missing), 'wrong', 7)
                    alias.symlink_to(wrong)
                self.assertIn('SONAME alias', self.paths(sqlite, ssl, crypto, ok=False))

    def test_archive_restored_regular_file_aliases_keep_the_selected_image(self):
        sqlite, ssl, crypto = self.cohort()
        for image in (sqlite,ssl,crypto):
            alias=image.parent/('lib%s.so.1'%image.name.split('-')[0][3:])
            alias.unlink();shutil.copy2(image,alias)
            self.assertFalse(alias.is_symlink())
        self.assertEqual(self.paths(sqlite,ssl,crypto),sorted([str(sqlite.parent),str(ssl.parent)]))

    def test_unused_libraries_and_other_native_targets_do_not_gain_new_requirements(self):
        self.assertEqual(self.paths(storage=False, server=False), [])
        self.assertEqual(self.paths('absent.a', 'absent.so', 'absent-crypto.so',
                                    target='x86_64-w64-windows-gnu'), [])
        self.assertEqual(self.paths('/a/libsqlite.dylib', '/z/libssl.dylib', '/z/libcrypto.dylib',
                                    target='arm64-apple-darwin'), ['/a', '/z'])

    def test_static_archive_directories_do_not_shadow_dynamic_inputs(self):
        source = self.root / 'archive.c';source.write_text('int archive_value(void){return 0;}\n')
        obj = self.root / 'archive.o'
        self.run_tool([CLANG, '--target='+TARGETS[0], '-c', source, '-o', obj])
        folder = self.root / 'a-static';folder.mkdir()
        archive = folder / 'libsqlite.a';self.run_tool([AR, 'rcs', archive, obj])
        ssl = self.dso('z-dynamic', 'ssl');crypto = self.dso('z-dynamic', 'crypto')
        shutil.copy2(ssl, folder/'libssl.so.1')
        self.assertEqual(self.paths(archive, ssl, crypto), [str(ssl.parent)])

    def test_order_is_deterministic_when_directories_do_not_overlap(self):
        sqlite, ssl, crypto = self.cohort()
        expected = sorted([str(sqlite.parent), str(ssl.parent)])
        self.assertEqual(self.paths(sqlite, ssl, crypto), expected)
        self.assertEqual(self.paths(sqlite, ssl, crypto), expected)

    def test_selected_directory_preserves_unicode_commas_quotes_and_percent(self):
        folder = 'runtime, % " 🧠'
        sqlite = self.dso(folder, 'sqlite');ssl = self.dso(folder, 'ssl');crypto = self.dso(folder, 'crypto')
        self.assertEqual(self.paths(sqlite, ssl, crypto), [str(sqlite.parent)])

    def test_missing_SONAME_remains_an_absolute_linker_input(self):
        image = self.dso('direct', 'sqlite', soname=False)
        self.assertEqual(self.paths(image, storage=True, server=False), [str(image.parent)])

    def test_corrupt_dynamic_string_table_is_rejected_for_each_ELF_class_and_byte_order(self):
        for i, target in enumerate(TARGETS):
            with self.subTest(target=target):
                image = self.dso('corrupt'+str(i), 'sqlite', target=target)
                raw = bytearray(image.read_bytes())
                endian = '<' if raw[5] == 1 else '>'
                wide = raw[4] == 2
                word = 'Q' if wide else 'I';width=8 if wide else 4
                phoff = struct.unpack_from(endian+word, raw, 32 if wide else 28)[0]
                phsize, count = struct.unpack_from(endian+'HH', raw, 54 if wide else 42)
                changed=False
                for index in range(count):
                    ph=phoff+index*phsize
                    if struct.unpack_from(endian+'I',raw,ph)[0]!=2:continue
                    start=struct.unpack_from(endian+word,raw,ph+(8 if wide else 4))[0]
                    size=struct.unpack_from(endian+word,raw,ph+(32 if wide else 16))[0]
                    for offset in range(start,start+size,2*width):
                        if struct.unpack_from(endian+word,raw,offset)[0]==10:
                            struct.pack_into(endian+word,raw,offset+width,(1<<(width*8))-1);changed=True;break
                self.assertTrue(changed)
                image.write_bytes(raw)
                self.assertIn('string table',self.paths(image,storage=True,server=False,ok=False))


class NativeLoader(RuntimePaths):
    def test_the_actual_loader_uses_each_selected_library_and_the_old_alphabetic_order_fails(self):
        target=self.run_tool([CLANG,'-dumpmachine']).stdout.strip()
        sqlite,ssl,crypto=self.cohort(target=target)
        shadow=self.dso('unselected','ssl',300,target=target)
        shutil.copy2(shadow,sqlite.parent/'libssl.so.1')
        paths=self.paths(sqlite,ssl,crypto,target=target)
        source=self.root/'main.c'
        source.write_text('int sqlite_value(void);int ssl_value(void);int crypto_value(void);\n'
                          'int main(void){return sqlite_value()+ssl_value()+crypto_value()==42?0:1;}\n')
        for label,order,expected in [('selected',paths,0),('old-alphabetic',sorted(paths),1)]:
            image=self.root/label
            args=[CLANG,'--ld-path='+str(LLD),source,sqlite,ssl,crypto,'-o',image]
            for directory in order:args+=['-Xlinker','-rpath','-Xlinker',directory]
            self.run_tool(args)
            self.run_tool([image],expected=expected)


if __name__=='__main__':
    if not LLD.is_file():
        raise RuntimeError('ELF fixtures require LLVM22.1 ld.lld; configure -DNEX_ELF_TEST_LD=/absolute/path/to/ld.lld')
    versions={str(tool):subprocess.check_output([str(tool),'--version'],text=True,timeout=30)
              for tool in (CLANG,LLD,AR)}
    if any(not re.search(r'(?:clang version|LLD|LLVM version) 22\.1\.\d+',version)for version in versions.values()):
        raise RuntimeError('ELF fixture producers must all use LLVM/LLD22.1.x: '+repr(versions))
    print('ELF fixture producers: '+json.dumps(versions),flush=True)
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(NativeLoader if LOADER else RuntimePaths)
    # The loader case adds execution to the separately maintained parser/order
    # corpus; neither a host name nor successful ELF generation claims execution.
    if LOADER:
        suite=unittest.TestSuite([NativeLoader('test_the_actual_loader_uses_each_selected_library_and_the_old_alphabetic_order_fails')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(0 if result.wasSuccessful()else 1)
