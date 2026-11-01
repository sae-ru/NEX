"""Relocated native applications, provenance failures and retained runtime behavior."""
from host_fixture import stop_server, run_native
from host_fixture import python_executable
from host_fixture import deployed_environment
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


APP = 'bin/app.exe' if os.name == 'nt' else 'bin/app'
NEX = 'bin/nex.exe' if os.name == 'nt' else 'bin/nex'

def loader_environment():
    return {k:v for k,v in os.environ.items() if k not in ('LD_LIBRARY_PATH','LD_PRELOAD')}


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
            if os.name=='nt' and path.suffix.lower()=='.dll' and Path(str(path)+'.a').is_file():pending.append(Path(str(path)+'.a'))
            if platform.system() == 'Darwin':
                listing = subprocess.check_output(['/usr/bin/otool', '-L', path], text=True)
                for line in listing.splitlines()[1:]:
                    name = line.strip().split(' (compatibility version ', 1)[0]
                    if name.startswith('/') and not name.startswith(('/usr/lib/', '/System/Library/')):
                        pending.append(name)
            elif os.name=='nt':
                import sys
                sys.path.insert(0,str(harness.REPO/'tools'))
                from windows_pe import inspect,system_directory
                if path.read_bytes().startswith(b'!<arch>\n'):continue
                for name in inspect(path)['imports']:
                    if name.startswith(('api-ms-win-','ext-ms-win-')) or (system_directory()/name).is_file():continue
                    dependency=path.parent/name
                    self.assertTrue(dependency.is_file(),'unresolved PE fixture dependency: '+name)
                    pending.append(dependency)
            else:
                listing = subprocess.check_output(['ldd', path], text=True, env=loader_environment())
                self.assertNotIn('=> not found', listing, 'unresolved ELF fixture dependency: '+str(path))
                pending += re.findall(r'=>\s+(/.*?)\s+\(0x', listing)
        return found

    def copy_elf_fixture_closure(self, original, prefix):
        """Prepare an independently loadable test input, without the packager."""
        original=Path(original).resolve(strict=True)
        listing=subprocess.check_output(['ldd',original],text=True,env=loader_environment())
        self.assertNotIn('=> not found',listing,'unresolved ELF fixture dependency: '+str(original))
        platform_libraries={'libc.so.6','libm.so.6','libpthread.so.0','libdl.so.2',
                            'librt.so.1','libresolv.so.2','libutil.so.1',
                            'ld-linux-aarch64.so.1','ld-linux-x86-64.so.2'}
        aliases={};inputs={original}
        for name,value in re.findall(r'^\s*(\S+)\s*=>\s*(.*?)\s+\(0x',listing,re.M):
            if Path(name).name in platform_libraries:continue
            path=Path(value).resolve(strict=True);inputs.add(path);aliases[name]=path
        self.assertLessEqual(len(inputs),128)
        self.assertLessEqual(sum(p.stat().st_size for p in inputs),256*1024*1024)
        names={};digests={p:hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
        for path in sorted(inputs):
            self.assertNotIn(path.name,names,'ELF fixture basename collision: '+path.name)
            names[path.name]=path;target=prefix/path.name;shutil.copy2(path,target)
            subprocess.run(['patchelf','--set-rpath','$ORIGIN',target],check=True)
            dynamic=subprocess.check_output(['readelf','-d',path],text=True)
            match=re.search(r'\(SONAME\).*?\[([^]]+)\]',dynamic)
            if match:aliases[match[1]]=path
        for name,path in aliases.items():
            self.assertEqual(Path(name).name,name,'ELF fixture SONAME must be a filename')
            self.assertNotIn(name,('','.','..'))
            alias=prefix/name;target=prefix/path.name
            if alias.exists():self.assertEqual(alias.resolve(),target)
            else:alias.symlink_to(target.name)
        for path,digest in digests.items():self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),digest)
        library=prefix/original.name
        captured=subprocess.check_output(['ldd',library],text=True,env=loader_environment())
        self.assertNotIn('=> not found',captured)
        for name,value in re.findall(r'^\s*(\S+)\s*=>\s*(.*?)\s+\(0x',captured,re.M):
            if Path(name).name not in platform_libraries:self.assertIn(prefix.resolve(),Path(value).resolve().parents)
        return library

    def notice(self, roots):
        license_file = self.root / 'fixture-license.txt'
        license_file.write_text('Complete fixture provenance notice for explicitly selected test inputs.\n', newline="\n")
        notices = self.root / 'notices.json'
        notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': [
            {'name': 'test-inputs', 'version': 'fixture', 'url': 'https://sqlite.org',
             'roots': list(map(str, roots)), 'license_files': [str(license_file)]}]}), newline="\n")
        return notices

    def validate_inventory(self, directory):
        report = json.loads((directory / 'application.json').read_text())
        self.assertEqual(report['schema'], 'nex.application-package/1')
        self.assertFalse(report['execution_verified'])
        actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
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
        if platform.system() == 'Darwin':
            shutil.copy2(original, library)
            subprocess.run(['/usr/bin/install_name_tool', '-id', '@rpath/' + library.name, library], check=True)
        elif os.name=='nt':
            # Export the selected genuine SQLite archive as a fixture DLL so
            # native PE closure/provenance is exercised independently of the packager.
            library=prefix/'sqlite3.dll'
            result=run_native([doctor['native_compiler'],'-shared','-Wl,--whole-archive',original,'-Wl,--no-whole-archive','-Wl,--export-all-symbols','-o',library],capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        else:
            library=self.copy_elf_fixture_closure(original,prefix)
        config = self.root / 'toolchain.json'
        config.write_text(json.dumps({**harness.host_toolchain_defaults(doctor),
            'sqlite': {'include': doctor['native_sqlite_include'], 'library': str(library)+('.a' if os.name=='nt' else '')}}), newline="\n")
        return config, library

    @unittest.skipUnless(platform.system()=='Linux','actual private ELF fixture closure')
    def test_fixture_copy_keeps_transitive_libraries_without_ambient_loader_paths(self):
        doctor=self.cli('doctor');compiler=doctor['native_compiler'];original=self.root/'original % 🧠';original.mkdir()
        (original/'leaf.c').write_text('int leaf(void){return 40;}\n', newline="\n")
        (original/'provider.c').write_text('int leaf(void);int answer(void){return leaf()+2;}\n', newline="\n")
        leaf=original/'libnex_fixture_leaf.so.1';provider=original/'libnex_fixture_provider.so.1'
        for argv in ([compiler,'-x','c','-shared','-fPIC',original/'leaf.c','-Wl,-soname,'+leaf.name,'-o',leaf],
                     [compiler,'-x','c','-shared','-fPIC',original/'provider.c','-L'+str(original),'-l:'+leaf.name,
                      '-Wl,-soname,'+provider.name,'-Wl,-rpath,$ORIGIN','-o',provider]):
            subprocess.run(list(map(str,argv)),check=True,env=loader_environment())
        probe=self.root/'probe.c';probe.write_text('#include <dlfcn.h>\n#include <stdio.h>\nint main(int argc,char **argv){if(argc!=2)return 2;void *h=dlopen(argv[1],RTLD_NOW);if(!h){puts(dlerror());return 3;}int(*f)(void)=(int(*)(void))dlsym(h,"answer");if(!f)return 4;printf("%d\\n",f());return dlclose(h)!=0;}\n', newline="\n")
        binary=self.root/'probe';subprocess.run([compiler,'-x','c',str(probe),'-ldl','-o',str(binary)],check=True)
        copied=self.root/'copied % 🧠';copied.mkdir();library=self.copy_elf_fixture_closure(provider,copied)
        self.assertIn(leaf.name,{p.name for p in copied.iterdir()})
        missing=self.root/'missing';missing.mkdir();leaf.unlink()
        with self.assertRaisesRegex(AssertionError,'unresolved ELF fixture dependency'):
            self.copy_elf_fixture_closure(provider,missing)
        shutil.rmtree(original)
        child=subprocess.run([binary,library],capture_output=True,text=True,env=loader_environment())
        self.assertEqual((child.returncode,child.stdout),(0,'42\n'),child.stderr)

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
        child = subprocess.run([moved / APP], env=deployed_environment(), capture_output=True, text=True)
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
        child = subprocess.run([moved / APP], env=deployed_environment(**env), capture_output=True, text=True)
        self.assertEqual((child.returncode, child.stdout), (0, 'Я🧠\n'), child.stderr)

    @unittest.skipUnless(platform.system() == 'Linux', 'ELF private GNU C++ runtime')
    def test_private_cxx_runtime_is_captured_with_notices_and_relocates(self):
        self.source('module private_runtime; fn main()->unit!{io}{print(42);}')
        built=self.cli('build', '--profile', 'release')
        listing=subprocess.check_output(['ldd', built['executable']], text=True)
        selected=dict(re.findall(r'^\s*(libstdc\+\+\.so\.6|libgcc_s\.so\.1)\s*=>\s*(.*?)\s+\(0x',listing,re.M))
        if 'libstdc++.so.6' not in selected:self.skipTest('compiler uses no dynamic GNU C++ runtime')
        private=self.root/'private C++ runtime 🧠';private.mkdir()
        for soname,filename in selected.items():
            origin=Path(filename).resolve();target=private/origin.name;shutil.copy2(origin,target)
            subprocess.run(['patchelf','--set-rpath','$ORIGIN',target],check=True)
            if target.name!=soname:(private/soname).symlink_to(target.name)
        doctor=self.cli('doctor');wrapper=self.root/'private-driver.py'
        wrapper=python_executable(wrapper,'#!/usr/bin/env python3\nimport subprocess,sys\nfrom pathlib import Path\n'
            'args=sys.argv[1:]\nr=subprocess.run(['+repr(doctor['native_compiler'])+ ',*args])\n'
            'if r.returncode==0 and "-o" in args and not any(x in args for x in ["-c","-###","-E","-S"]):\n'
            ' p=Path(args[args.index("-o")+1])\n'
            ' if p.is_file() and p.read_bytes()[:4]==b"\\x7fELF":\n'
            '  r=subprocess.run(["patchelf","--set-rpath",'+repr(str(private))+',str(p)])\n'
            'raise SystemExit(r.returncode)\n',harness.native_fixture_compiler())
        wrapper.chmod(0o755)
        config=self.root/'private-toolchain.json';config.write_text(json.dumps({
            'schema':'nex.toolchain/1','target':doctor['host'],'compiler':str(wrapper)}), newline="\n")
        output=self.root/'private-package'
        failure=self.cli('package','--toolchain',config,'--directory',output,ok=False,timeout=180)
        self.assertEqual(failure['code'],'E_PACKAGE');self.assertIn('provenance',failure['message'])
        self.assertFalse(output.exists())
        self.cli('package','--toolchain',config,'--directory',output,
                 '--notices',self.notice([private]),timeout=180)
        report=self.validate_inventory(output)
        self.assertTrue(any('libstdc++.so.6' in name for name in report['files']))
        self.assertFalse(any(Path(name).name in selected for name in report['system_libraries']))
        self.assertEqual([c['name'] for c in report['components']],['test-inputs'])
        shutil.rmtree(private);shutil.rmtree(self.root/'.nex');self.file.unlink()
        moved=self.root/'moved private application';output.rename(moved)
        child=subprocess.run([moved/APP],env={'PATH':'/usr/bin:/bin','NEX_RESOURCE_DIR':'/absent'},capture_output=True,text=True)
        self.assertEqual((child.returncode,child.stdout),(0,'42\n'),child.stderr)

    def test_existing_output_and_unsupported_modes_are_rejected(self):
        self.source('module rejected; fn main() -> unit {}')
        output = self.root / 'occupied';output.mkdir()
        marker = output / 'keep';marker.write_text('original', newline="\n")
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
        shutil.copy2(harness.NEX, sdk / NEX)
        config, library = self.sqlite_toolchain(sdk / 'libraries')
        notice = sdk / 'notice.txt';notice.write_text('Retained SDK fixture notice.\n', newline="\n")
        resources = sdk / 'share/nex';resources.mkdir(parents=True)
        manifest = {'schema': 'nex.sdk-bundle/1', 'ok': True,
            'files': {p.relative_to(sdk).as_posix(): {'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'component': 'sqlite-fixture'} for p in self.library_inputs([library]) if p.is_relative_to(sdk)},
            'components': [{'name': 'sqlite-fixture', 'version': 'fixture', 'url': 'https://sqlite.org',
                'license_files': [{'path': 'notice.txt', 'sha256': hashlib.sha256(notice.read_bytes()).hexdigest()}]}]}
        (resources / 'sdk-bundle.json').write_text(json.dumps(manifest), newline="\n")
        self.source('module sdk_app; server fn main() -> unit !{db} { store_put("k", "v"); }')
        external = self.library_inputs([library]) - {library}
        extra_notices = ['--notices', self.notice(external)] if external else []
        def attempt(destination, ok=True):
            child = subprocess.run([sdk / NEX, 'package', '--directory', destination, '--toolchain', config, *extra_notices, '--json'],
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
        run_native(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', key, '-out', cert,
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
            process = subprocess.Popen([moved / APP, '--auth', auth, '--database', self.root / 'database.sqlite',
                '--cert', cert, '--key', key, '--port', '0'], env=deployed_environment(),
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
                stop_server(process)
                stdout, stderr = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, stdout + stderr)
                self.assertNotIn('E_INTERNAL_LEAK', stderr)


if __name__ == '__main__':
    unittest.main()
