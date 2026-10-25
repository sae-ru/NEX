"""Checked source bytes across interpreters, code generators, files and history."""
import base64
import json
from pathlib import Path
import re
import random
import shutil
import sqlite3
import unittest
import support as harness
from support import ToolchainCase


class BinaryPrograms(ToolchainCase):
    def agree(self, expected, env=None):
        self.assertEqual(self.cli('eval', env=env)['stdout'], expected)
        for profile in ('debug', 'release'):
            self.assertEqual(self.cli('run', '--profile', profile, env=env)['stdout'], expected)

    def test_browser_state_preserves_native_typescript_and_reference_semantics(self):
        self.source((harness.REPO/'examples/bytes-web.nex').read_text())
        self.agree('AP+AQQA=\n')
        self.cli('test')
        if shutil.which('node'):
            self.cli('test', '--target', 'web')
        directory = self.root/'browser'
        self.cli('web', '--directory', directory)
        for path in (directory/'src').rglob('*.ts'):
            source = path.read_text()
            self.assertNotIn('BINARY_WEB_SERVER_ONLY_SENTINEL', source)
            self.assertNotIn('file_read_bytes', source)

    def test_seeded_updates_and_retained_aliases_match_independent_octet_oracle(self):
        rng = random.Random(0x4E4558)
        value = bytes(range(256))
        encode = lambda data: base64.b64encode(data).decode('ascii')
        lines = ['module binary_oracle;', 'fn exercise()->bytes{',
                 'var value:bytes=unwrap(decode_base64('+json.dumps(encode(value))+'));']
        snapshots = []
        for i in range(48):
            snapshots.append(encode(value))
            lines.append('let saved_'+str(i)+':bytes=value;')
            operation = rng.choice(['push', 'set', 'slice', 'concat'])
            if operation == 'set' and not value:
                operation = 'push'
            if operation == 'push':
                octet = rng.randrange(256)
                expression = 'push(value,'+str(octet)+')'; value += bytes([octet])
            elif operation == 'set':
                index, octet = rng.randrange(len(value)), rng.randrange(256)
                expression = 'set(value,'+str(index)+','+str(octet)+')'
                value = value[:index]+bytes([octet])+value[index+1:]
            elif operation == 'slice':
                start = rng.randrange(len(value)+1); count = rng.randrange(len(value)-start+1)
                expression = 'slice(value,'+str(start)+','+str(count)+')'; value = value[start:start+count]
            else:
                extra = bytes(rng.randrange(256) for _ in range(rng.randrange(17)))
                expression = 'value+unwrap(decode_base64('+json.dumps(encode(extra))+'))'; value += extra
            lines += ['value='+expression+';',
                      'assert(encode_base64(value)=='+json.dumps(encode(value))+');']
        for i, saved in enumerate(snapshots):
            lines.append('assert(encode_base64(saved_'+str(i)+')=='+json.dumps(saved)+');')
        lines += ['return value;}', 'fn main()->unit!{io}{print(encode_base64(exercise()));}',
                  'test fn oracle()->unit{assert(encode_base64(exercise())=='+json.dumps(encode(value))+');}']
        self.source('\n'.join(lines))
        self.agree(encode(value)+'\n')
        self.cli('test')
        if shutil.which('node'):
            self.cli('test', '--target', 'web')

    def test_examples_generics_callbacks_and_immutable_owners(self):
        self.source((harness.REPO / 'examples/bytes.nex').read_text())
        self.agree('AP+AQQ==\nE_UTF8\n{"name":"raw","data":"AP+AQQ=="}\n')
        self.cli('test')
        self.cli('test', '--profile', 'release')
        if shutil.which('node'):
            self.cli('test', '--target', 'web')
        descriptor = self.cli('describe')
        self.assertEqual(descriptor['version'], '0.23')
        self.assertIn('bytes', descriptor['types'])
        self.assertIn('bytes', descriptor['generic_constraints']['add'])
        self.assertNotIn('bytes', descriptor['generic_constraints']['ordered'])
        self.assertIn('immutable_contiguous_octets', descriptor['binary_features'])
        self.assertIn('0..255', self.cli('guide', '--kind', 'bytes')['text'])
        context = self.cli('context', '--symbol', 'binary_data::combine<bytes>')
        self.assertEqual(context['type_arguments'], ['bytes'])
        self.assertFalse(context['editable'])

    def test_unicode_and_independent_all_octet_codec_vectors(self):
        values = bytes(range(256))
        encoded = base64.b64encode(values).decode('ascii')
        self.source(r'''module octets;
fn main()->unit !{io} {
  let value:bytes = unwrap(decode_base64("ENCODED"));
  assert(len(value)==256);
  var i:i64 = 0;
  while i<256 { assert(value[i]==i); i=i+1; }
  assert(encode_base64(value)=="ENCODED");
  assert(error_code(decode_utf8(value))=="E_UTF8");
  print(encode_base64(value));
  print(unwrap(decode_utf8(utf8_bytes("\ufeffЯ\u0000🧠"))));
}
test fn malformed()->unit {
  assert(error_code(decode_utf8(unwrap(bytes([192,128]))))=="E_UTF8");
  assert(error_code(decode_utf8(unwrap(bytes([237,160,128]))))=="E_UTF8");
  assert(error_code(decode_utf8(unwrap(bytes([244,144,128,128]))))=="E_UTF8");
  assert(error_code(decode_base64("Zh=="))=="E_BASE64");
  assert(error_code(decode_base64("Zm9="))=="E_BASE64");
  assert(error_code(decode_base64("AA-_"))=="E_BASE64");
  assert(error_code(decode_base64("AA==\n"))=="E_BASE64");
  assert(error_code(decode_json<bytes>("\"Zh==\""))=="E_JSON");
}
'''.replace('ENCODED', encoded))
        self.agree(encoded + '\n\ufeffЯ\0🧠\n')
        self.cli('test')
        if shutil.which('node'):
            self.cli('test', '--target', 'web')

    def test_rejected_programs_and_no_implicit_conversions(self):
        cases = [
            ('fn main()->unit{let x:bytes=[];}', 'E_INFER'),
            ('fn main()->unit{bytes([1e0]);}', 'E_TYPE'),
            ('fn main()->unit{decode_utf8("x");}', 'E_TYPE'),
            ('fn main()->unit{utf8_bytes(unwrap(bytes([])));}', 'E_TYPE'),
            ('fn main()->unit{let x:bytes=unwrap(bytes([]))+[1];}', 'E_TYPE'),
            ('fn main()->unit{let x:bool=utf8_bytes("a")<utf8_bytes("b");}', 'E_TYPE'),
            ('fn main()->unit{set(utf8_bytes("a"),0,true);}', 'E_TYPE'),
            ('fn main()->unit{push(utf8_bytes("a"),1e0);}', 'E_TYPE'),
            ('fn main()->unit{let x:bytes=slice(utf8_bytes("a"),true,1);}', 'E_TYPE'),
            ('fn main()->unit{let x:fn(str)->bytes=utf8_bytes;}', 'E_NAME'),
            ('fn bytes(x:i64)->i64{return x;}', 'E_DUPLICATE'),
            ('struct bytes{value:i64;} fn main()->unit{}', 'E_DUPLICATE'),
            ('fn f<bytes>(x:bytes)->bytes{return x;} fn main()->unit{}', 'E_DUPLICATE'),
            ('fn main()->unit{file_read_bytes("x");}', 'E_REALM'),
            ('server fn main()->unit!{io}{file_read_bytes("x");}', 'E_EFFECT'),
            ('server fn main()->unit!{fs}{file_write_bytes("x","text");}', 'E_TYPE'),
        ]
        for body, expected in cases:
            with self.subTest(body=body):
                self.source('module rejected;\n' + body)
                self.assertEqual(self.cli('check', ok=False)['code'], expected)

    def test_traps_match_evaluation_and_native_error_order(self):
        for expression, expected in [
            ('set(utf8_bytes("a"),-1,256)', 'E_BOUNDS'),
            ('set(utf8_bytes("a"),1,256)', 'E_BOUNDS'),
            ('set(utf8_bytes("a"),0,256)', 'E_RANGE'),
            ('push(utf8_bytes("a"),-1)', 'E_RANGE'),
            ('slice(utf8_bytes("a"),1,9223372036854775807)', 'E_BOUNDS'),
            ('utf8_bytes("a")[9223372036854775807]', 'E_BOUNDS'),
        ]:
            with self.subTest(expression=expression):
                self.source('module traps;\nfn main()->unit!{io}{\n print(' + expression + ');\n}\n')
                error = self.cli('eval', ok=False)
                self.assertEqual(error['code'], expected)
                self.assertEqual(error['line'], 3)
                self.assertEqual(error['stdout'], '')
                native = self.cli('run', ok=False)
                self.assertEqual(native['exit_code'], 70)
                self.assertIn(expected + ':', native['stderr'])
                self.assertIn('source line 3', native['stderr'])
                self.assertEqual(native['stdout'], '')

    def test_contextual_names_and_qualified_import_alias(self):
        (self.root / 'model.nex').write_text('module model; pub struct Item { value:bytes; }\n')
        self.source('''module aliases;
import "./model.nex" as bytes;
fn main()->unit!{io}{
 let item:bytes::Item=bytes::Item(utf8_bytes("x"));
 let bytes:fn(i64)->i64=fn(n:i64)->i64{return n+1;};
 assert(bytes(41)==42);
 print(encode_base64(item.value));
}
''')
        self.agree('eA==\n')

    def test_binary_files_and_selective_native_components(self):
        data = self.root / 'data'
        data.mkdir()
        raw = bytes(range(256))
        (data / 'input').write_bytes(raw)
        env = {'NEX_FILES_ROOT': str(data), 'NEX_FILES_WRITE': '1'}
        self.source('''module binary_files;
server fn main()->unit!{fs,io}{
 let data:bytes=unwrap(file_read_bytes("input"));
 assert(unwrap(file_write_bytes("copy",data)));
 assert(error_code(file_read_text("copy"))=="E_UTF8");
 assert(unwrap(file_read_bytes("copy"))==data);
 print(encode_base64(data));
}
''')
        self.agree(base64.b64encode(raw).decode('ascii') + '\n', env)
        self.assertEqual((data / 'copy').read_bytes(), raw)
        built = self.cli('build')
        metadata = json.loads((Path(built['executable']).parent / 'build.json').read_text())
        components = set(metadata['runtime_components'])
        self.assertTrue({'nex_files.cpp', 'files_runtime.cpp'}.issubset(components))
        self.assertNotIn('nex_json.cpp', components)
        self.assertNotIn('nex_store.cpp', components)
        self.assertEqual(self.cli('eval', env={**env, 'NEX_FILES_WRITE': ''}, ok=False)['code'], 'E_RESULT')
        self.assertEqual((data / 'copy').read_bytes(), raw)

    def test_binary_file_evaluation_order_and_short_circuit(self):
        data = self.root / 'data'
        data.mkdir()
        env = {'NEX_FILES_ROOT': str(data), 'NEX_FILES_WRITE': '1'}
        self.source('''module ordered_bytes;
server fn path()->str!{fs}{assert(unwrap(file_write_bytes("trace",utf8_bytes("path"))));return "value";}
server fn value()->bytes!{fs}{
 assert(unwrap(file_read_bytes("trace"))==utf8_bytes("path"));
 assert(unwrap(file_write_bytes("trace",utf8_bytes("value"))));return unwrap(bytes([0,255]));
}
server fn main()->unit!{fs,io}{
 assert(unwrap(file_write_bytes(path(),value())));
 let skip:bool=false&&unwrap(file_write_bytes("skipped",utf8_bytes("x")));
 let skip2:bool=true||unwrap(file_write_bytes("skipped","bad"));
 print(encode_base64(unwrap(file_read_bytes("value"))));
 print(unwrap(file_read_text("trace")));
}
'''.replace('file_write_bytes("skipped","bad")', 'file_write_bytes("skipped",utf8_bytes("bad"))'))
        self.agree('AP8=\nvalue\n', env)
        self.assertFalse((data / 'skipped').exists())

    def test_byte_early_returns_and_retained_snapshot_cleanup(self):
        self.source('''module exits;
fn choose(flag:bool,data:bytes)->bytes{
 if flag { let f:fn()->bytes=fn()->bytes{return slice(data,1,1);};return f(); }
 var n:i64=0;
 while n<2 {let copy:bytes=data+data;if n==1{return slice(copy,2,2);}n=n+1;}
 return data;
}
fn main()->unit!{io}{
 let data:bytes=unwrap(bytes([0,255,128]));
 print(encode_base64(choose(true,data)));
 print(encode_base64(choose(false,data)));
}
''')
        self.agree('/w==\ngAA=\n')

    def test_real_language_012_migration_retains_history_and_ids(self):
        fixture = json.loads((harness.REPO / 'tests/fixtures/language-0.12.json').read_text())
        self.source(fixture['source'])
        metadata = self.historical_store('0.12')
        self.file.unlink()
        old = metadata['revision']
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            source = db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0]
            identities = db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall()
        self.assertEqual(self.cli('graph', ok=False)['code'], 'E_LANGUAGE_VERSION')
        migrated = self.cli('migrate')
        self.assertEqual(migrated['language'], '0.23')
        self.assertNotEqual(migrated['revision'], old)
        self.assertEqual(self.cli('run', '--revision', migrated['revision'])['stdout'], metadata['stdout'])
        self.cli('test', '--revision', migrated['revision'], '--target', 'web')
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(), identities)
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0], source)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']}, {'0.12', '0.23'})

    def test_real_nominal_codec_conflicts_reject_before_primitive_reinterpretation(self):
        fixture = json.loads((harness.REPO / 'tests/fixtures/language-0.12-byte-names.json').read_text())
        self.source(fixture['source'])
        metadata = self.historical_store('0.12-byte-names')
        self.file.unlink()
        old = metadata['revision']
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            original = db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0]
        self.assertEqual(self.cli('migrate', ok=False)['code'], 'E_DUPLICATE')
        self.assertEqual(self.cli('history')['head'], old)
        bundle = json.loads(original)
        for name, source in bundle['files'].items():
            for intrinsic in ('utf8_bytes', 'decode_utf8', 'encode_base64', 'decode_base64'):
                source = source.replace(intrinsic, 'legacy_' + intrinsic)
            bundle['files'][name] = source
        candidate = self.root / 'reviewed-repair.json'
        candidate.write_text(json.dumps({'schema': 'nex.graph/2', 'language': '0.12', 'revision': old, 'bundle': bundle}))
        # Repairing function names must not silently change the old nominal bytes.
        self.assertEqual(self.cli('migrate', candidate, ok=False)['code'], 'E_DUPLICATE')
        self.assertEqual(self.cli('history')['head'], old)
        for name, source in bundle['files'].items():
            bundle['files'][name] = re.sub(r'\bbytes\b', 'LegacyBytes', source)
        candidate.write_text(json.dumps({'schema': 'nex.graph/2', 'language': '0.12', 'revision': old, 'bundle': bundle}))
        migrated = self.cli('migrate', candidate)
        self.assertEqual(self.cli('run', '--revision', migrated['revision'])['stdout'], metadata['stdout'])
        self.cli('test', '--revision', migrated['revision'], '--target', 'web')
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?', (old,)).fetchone()[0], original)


if __name__ == '__main__':
    unittest.main()
