"""Text-file source semantics, native/reference agreement and preserved 0.11 history."""
import copy
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import unittest
import urllib.request
import support as harness


class Files(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.root = self.root.resolve();self.file = self.root / 'main.nex'
        self.data = self.root / 'data';self.data.mkdir();(self.data / 'nested').mkdir()
        self.env = {'NEX_FILES_ROOT': str(self.data), 'NEX_FILES_WRITE': '1'}

    def backends(self, env=None):
        environment = {**self.env, **(env or {})}
        output = self.cli('eval', env=environment)['stdout']
        for profile in ('debug', 'release'):
            self.assertEqual(self.cli('run', '--profile', profile, env=environment, timeout=120)['stdout'], output)
        return output

    def test_unicode_nul_bom_results_and_only_needed_components(self):
        self.source('''module files;
server fn main() -> unit !{fs,io} {
 let value:str = "Я🧠\\u0000text";
 assert(unwrap(file_write_text("nested/Я🧠.txt",value)));
 let saved:result<str> = file_read_text("nested/Я🧠.txt");
 assert(unwrap(saved)==value); print(len(unwrap(saved))); print(unwrap(saved));
 assert(unwrap(file_write_text("bom","\\ufefftext")));
 assert(unwrap(file_read_text("bom"))=="\\ufefftext");
}''')
        self.assertEqual(self.backends(), '7\nЯ🧠\0text\n')
        built = self.cli('build')
        metadata = json.loads((Path(built['executable']).parent / 'build.json').read_text())
        self.assertIn('nex_files.cpp', metadata['runtime_components'])
        self.assertNotIn('nex_store.cpp', metadata['runtime_components'])
        self.assertNotIn('nex_json.cpp', metadata['runtime_components'])
        self.assertEqual((self.data / 'nested/Я🧠.txt').read_bytes(), 'Я🧠\0text'.encode())

    def test_capability_is_explicit_and_read_only_by_default(self):
        (self.data / 'existing').write_text('kept')
        self.source('''module capabilities;
server fn main() -> unit !{fs,io} {
 print(error_code(file_read_text("existing")));
 print(error_code(file_write_text("existing","overwritten")));
}''')
        for root in ('', 'relative-root', str(self.root / 'absent')):
            self.assertEqual(self.backends({'NEX_FILES_ROOT': root}), 'CAPABILITY\nCAPABILITY\n')
        for writable in ('', '0', 'yes'):
            self.assertEqual(self.backends({'NEX_FILES_WRITE': writable}), '\nCAPABILITY\n')
        self.assertEqual((self.data / 'existing').read_text(), 'kept')

    def test_paths_symlinks_invalid_text_and_limits_match(self):
        outside = self.root / 'outside';outside.write_text('private')
        (self.data / 'escape').symlink_to(outside)
        (self.data / 'alias').symlink_to(self.root, target_is_directory=True)
        (self.data / 'invalid').write_bytes(b'\xc3\x28')
        (self.data / 'large').write_bytes(b'x' * 1048577)
        (self.data / 'maximum').write_bytes(b'x' * 1048576)
        self.source('''module boundaries;
server fn main() -> unit !{fs,io} {
 assert(error_code(file_read_text("../outside"))=="VALIDATION");
 assert(error_code(file_write_text("../outside","x"))=="VALIDATION");
 assert(error_code(file_read_text("/absolute"))=="VALIDATION");
 assert(error_code(file_read_text("escape"))=="VALIDATION");
 assert(error_code(file_write_text("escape","x"))=="VALIDATION");
 assert(error_code(file_read_text("alias/outside"))=="VALIDATION");
 assert(error_code(file_read_text("bad\\u0000name"))=="VALIDATION");
 assert(error_code(file_read_text("invalid"))=="E_UTF8");
 assert(error_code(file_read_text("large"))=="LIMIT");
 assert(error_code(file_read_text("missing"))=="NOT_FOUND");
 print(len(unwrap(file_read_text("maximum"))));
}''')
        self.assertEqual(self.backends(), '1048576\n')
        self.assertEqual(outside.read_text(), 'private')

    def test_left_to_right_short_circuit_and_immutable_results(self):
        self.source('''module ordered;
server fn path() -> str !{fs} { assert(unwrap(file_write_text("trace","path"))); return "output"; }
server fn value() -> str !{fs} {
 assert(unwrap(file_read_text("trace"))=="path");
 assert(unwrap(file_write_text("trace","value"))); return "first";
}
server fn main() -> unit !{fs,io} {
 assert(unwrap(file_write_text(path(),value())));
 let first:result<str> = file_read_text("output");
 assert(unwrap(file_write_text("output","second")));
 assert(unwrap(first)=="first");
 let skipped:bool = false && unwrap(file_write_text("skipped","x"));
 let skipped_again:bool = true || unwrap(file_write_text("skipped","x"));
 print([unwrap(first),unwrap(file_read_text("output")),unwrap(file_read_text("trace"))]);
}''')
        self.assertEqual(self.backends(), '["first","second","value"]\n')
        self.assertFalse((self.data / 'skipped').exists())

    def test_generic_wire_helpers_and_snapshot_callable_effects(self):
        self.source('''module file_helpers;
server fn read_json<T:wire>(path:str) -> result<T> !{fs} {
 let loaded:result<str> = file_read_text(path);
 if !is_ok(loaded) { return err(error_code(loaded),error_message(loaded)); }
 return decode_json<T>(unwrap(loaded));
}
server fn reader(prefix:str) -> (server fn(str)->result<str> !{fs}) {
 return server fn(name:str)->result<str> !{fs} { return file_read_text(prefix+name); };
}
server fn main() -> unit !{fs,io} {
 assert(unwrap(file_write_text("nested/value",encode_json([40,2]))));
 var prefix:str = "nested/";
 let load:server fn(str)->result<str> !{fs} = reader(prefix);
 prefix="wrong/";
 assert(unwrap(load("value"))==encode_json([40,2]));
 print(unwrap(read_json<list<i64>>("nested/value")));
}''')
        self.assertEqual(self.backends(), '[40,2]\n')

    def test_effect_realm_arity_and_type_rejections(self):
        cases = [
            ('fn main()->unit!{fs}{}', 'E_REALM'),
            ('client fn main()->unit!{fs}{}', 'E_REALM'),
            ('server fn main()->unit!{io}{file_read_text("x");}', 'E_EFFECT'),
            ('server fn main()->unit!{fs}{file_write_text("x");}', 'E_ARITY'),
            ('server fn main()->unit!{fs}{file_read_text(1);}', 'E_TYPE'),
            ('server fn main()->unit!{fs}{file_write_text("x",false);}', 'E_TYPE'),
            ('server fn main()->unit!{fs}{file_read_text<i64>("x");}', 'E_GENERIC_ARITY'),
            ('fn file_read_text(x:i64)->i64{return x;} fn main()->unit{}', 'E_DUPLICATE'),
            ('fn main()->unit{let bad:fn(str)->result<str>!{fs}=fn(x:str)->result<str>!{fs}{return err("x","x");};}', 'E_REALM'),
            ('server fn read(x:str)->result<str>!{fs}{return file_read_text(x);} server fn main()->unit{let f:server fn(str)->result<str>!{fs}=read;f("x");}', 'E_EFFECT'),
        ]
        for definition, expected in cases:
            with self.subTest(expected=expected, definition=definition):
                self.source('module rejected; ' + definition)
                self.assertEqual(self.cli('check', ok=False)['code'], expected)

    def test_unreachable_server_files_are_absent_from_typescript(self):
        self.source('''module realms;
server fn private_data()->result<str>!{fs}{return file_read_text("FILES_SERVER_SENTINEL");}
fn main()->unit!{io}{print(42);}
test fn client_test()->unit{assert(40+2==42);}
''')
        self.cli('test', '--target', 'web')
        generated = self.cli('emit', '--kind', 'typescript', machine=False).stdout
        for value in ('FILES_SERVER_SENTINEL', 'file_read_text', 'private_data'):
            self.assertNotIn(value, generated)
        self.assertEqual(self.cli('emit', '--kind', 'typescript', '--entry', 'private_data', ok=False)['code'], 'E_REALM')

    def test_genuine_011_migration_preserves_history_and_ids(self):
        fixture = json.loads((harness.REPO / 'tests/fixtures/language-0.11.json').read_text())
        self.source(fixture['source']);metadata = self.historical_store('0.11');self.file.unlink()
        old = metadata['revision']
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            ids_before = db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall()
            source_before = db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0]
        self.assertEqual(self.cli('graph', ok=False)['code'], 'E_LANGUAGE_VERSION')
        migrated = self.cli('migrate')
        self.assertEqual(migrated['language'], '0.12');self.assertNotEqual(migrated['revision'], old)
        self.assertEqual(self.cli('run', '--revision', migrated['revision'])['stdout'], metadata['stdout'])
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(), ids_before)
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0], source_before)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']}, {'0.11', '0.12'})

    def test_reserved_name_migration_fails_without_rewriting_old_history(self):
        fixture = json.loads((harness.REPO / 'tests/fixtures/language-0.11-intrinsic.json').read_text())
        self.source(fixture['source']);metadata = self.historical_store('0.11-intrinsic');self.file.unlink()
        old = metadata['revision']
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            original = db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0]
        self.assertEqual(self.cli('migrate', ok=False)['code'], 'E_DUPLICATE')
        self.assertEqual(self.cli('history')['head'], old)
        bundle = json.loads(original)
        for name, source in bundle['files'].items():
            bundle['files'][name] = source.replace('file_read_text', 'legacy_read').replace('file_write_text', 'legacy_write')
        candidate = self.root / 'reviewed-repair.json'
        candidate.write_text(json.dumps({'schema': 'nex.graph/2', 'language': '0.11', 'revision': old, 'bundle': bundle}))
        migrated = self.cli('migrate', candidate)
        self.assertEqual(self.cli('run', '--revision', migrated['revision'])['stdout'], metadata['stdout'])
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0], original)

    def test_native_http_does_not_inherit_cli_file_capability(self):
        (self.data / 'private').write_text('do not expose')
        self.source('''module http_files;
import "std/http.nex" as http;
server fn handle(request:http::Request)->http::Response!{fs}{
 if request.method=="POST" { return http::json_response(200,encode_json(file_write_text("private","changed"))); }
 return http::json_response(200,encode_json(file_read_text("private")));
}''')
        auth = self.root / 'auth.json';token = self.cli('token', '--user', 'alice', '--auth', auth)['token']
        built = self.cli('build', '--target', 'server', '--profile', 'release', timeout=180)
        process = subprocess.Popen([built['executable'], '--auth', str(auth), '--database', str(self.root / 'data.sqlite'), '--port', '0'],
            env={**os.environ, **self.env}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            lines = queue.Queue();threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
            line = lines.get(timeout=20);match = re.search(r'http://127\.0\.0\.1:([0-9]+)', line)
            if match is None:
                process.terminate();stdout, stderr = process.communicate(timeout=15);self.fail(line + stdout + stderr)
            for method in ('GET', 'POST'):
                request = urllib.request.Request('http://127.0.0.1:' + match.group(1) + '/api/file',
                    data=b'x' if method == 'POST' else None, headers={'Authorization': 'Bearer ' + token}, method=method)
                with urllib.request.urlopen(request, timeout=10) as response:
                    value = json.loads(response.read());self.assertEqual(value['error']['code'], 'CAPABILITY')
        finally:
            if process.poll() is None:process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual(process.returncode, 0, stdout + stderr);self.assertNotIn('E_INTERNAL_LEAK', stderr)
        self.assertEqual((self.data / 'private').read_text(), 'do not expose')

    def test_explicit_host_capability_and_request_cancellation_cleanup(self):
        self.source('''module embedded_files;
server fn main(value:str)->result<bool>!{fs}{return file_write_text("atomic.txt",value);}
''')
        built = self.cli('build', '--library', '--entry', 'main', timeout=120)
        symbol = self.cli('context', '--symbol', 'main')['native_symbol']
        driver = self.root / 'host.cpp'
        driver.write_text(r'''
#include "nex_host.h"
#include "nex_files.h"
#include <filesystem>
#include <fstream>
#include <iostream>
extern "C" nexrt::Handle *SYMBOL(nexrt::Handle*);
void require(bool condition){if(!condition)throw std::runtime_error("host check failed");}
std::string contents(const std::filesystem::path &path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int main(int argc,char **argv){
 try{
  std::filesystem::path root=argv[1];
  {
   nexrt::TextFiles files(root.string(),true);
   {
    nexrt::RequestScope request;
    nexrt::FileScope grant(files);
    auto input=nexrt::makeHandle(nexrt::Value(nexrt::string("accepted")));
    auto output=SYMBOL(input);
    require(nexrt::isSuccess(nexrt::readHandle(output)));
    nex_release(output);nex_release(input);
   }
   require(contents(root/"atomic.txt")=="accepted");
   bool cancelled=false;unsigned polls=0;
   try{
    nexrt::RequestScope request;
    request.setCancellation([&]{return ++polls==5;});
    nexrt::FileScope grant(files);
    auto input=nexrt::makeHandle(nexrt::Value(nexrt::string(std::string(150000,'x'))));
    auto output=SYMBOL(input);
    nex_release(output);nex_release(input);
   }catch(const nexrt::Trap &error){require(error.code=="E_CANCELLED");cancelled=true;}
   require(cancelled && contents(root/"atomic.txt")=="accepted");
   for(const auto &entry:std::filesystem::directory_iterator(root))require(!entry.path().filename().string().starts_with(".nex-write-"));
  }
  nex_runtime_finish();std::cout<<"granted and cancelled cleanly\n";return 0;
 }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
'''.replace('SYMBOL', symbol))
        compiler = self.cli('doctor')['native_compiler']
        executable = self.root / 'host'
        result = subprocess.run([compiler, '-std=c++20', '-pthread', str(driver), built['executable'],
            '-I' + str(harness.REPO / 'runtime'), '-o', str(executable)], capture_output=True, text=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([str(executable), str(self.data)], env={**os.environ, 'NEX_FILES_ROOT': '/not-the-granted-root',
            'NEX_FILES_WRITE': '0'}, capture_output=True, text=True, timeout=30)
        self.assertEqual((result.returncode, result.stdout), (0, 'granted and cancelled cleanly\n'), result.stderr)


if __name__ == '__main__':unittest.main()
