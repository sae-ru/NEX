"""Compiler-derived C value contracts and explicit language-0.14 migration."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
import support as harness
PROBE=str(Path(sys.argv.pop(1)).resolve())

MODEL='''module interop;
pub struct Packet<T>{data:T;text:str;}
pub enum Reply<T>{Ready(packet:Packet<T>);Error(code:str);}
pub fn contract<T>(data:T)->result<Reply<T>>{return ok(Reply::Ready(Packet(data,"Я\\u0000🧠")));}
fn main()->unit!{io}{print(encode_json(contract(unwrap(bytes([0,255,128,1])))));}
test fn model_test()->unit{assert(is_ok(contract(utf8_bytes("data"))));}
'''
MODEL += '\ntest fn wire_model()->unit{assert(encode_json(contract(unwrap(bytes([0,255,128,1]))))=="{\\"ok\\":{\\"case\\":\\"Ready\\",\\"fields\\":{\\"packet\\":{\\"data\\":\\"AP+AAQ==\\",\\"text\\":\\"Я\\\\u0000🧠\\"}}}}");}\n'

class ForeignTypes(harness.ToolchainCase):
    def test_compiler_contract_c_producer_and_backend_results_agree(self):
        self.source(MODEL)
        expected=self.cli('eval')['stdout']
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],expected)
        self.cli('test','--target','web')
        contract=self.cli('ffi','--symbol','interop::contract<bytes>')
        self.assertEqual(contract['schema'],'nex.foreign-signature/1')
        names={x['name'] for x in contract['types'] if 'name' in x}
        self.assertEqual(names,{'interop::Packet<bytes>','interop::Reply<bytes>'})
        path=self.root/'signature.json';path.write_text(json.dumps(contract))
        result=subprocess.run([PROBE,'--signature',str(path)],capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(result.stdout,expected)
        before=self.cli('history')['head'];self.file.unlink()
        self.assertEqual(self.cli('ffi','--revision','HEAD','--symbol','interop::contract<bytes>'),contract)
        self.assertEqual(self.cli('history')['head'],before)

    def test_recursive_nominals_use_flat_bounded_type_indices(self):
        self.source('''module recursive;
pub enum Chain{End;Next(value:i64,rest:list<Chain>);}
fn contract(value:Chain)->Chain{return value;}
fn main()->unit{}
''')
        value=self.cli('ffi','--symbol','contract')
        self.assertEqual(len(value['types']),3)
        index=value['parameters'][0];self.assertEqual(value['result'],index)
        self.assertEqual(value['types'][index]['kind'],'enum')
        listed=next(t for t in value['types'] if t['kind']=='list')
        self.assertEqual(listed['item'],index)

    def test_function_keys_and_server_file_shapes_are_explicit(self):
        self.source('''module opaque;
server fn contract(value:list<file>,callback:server fn(file)->file)->(server fn(file)->file){return callback;}
fn main()->unit{}
''')
        value=self.cli('ffi','--symbol','contract')
        self.assertEqual({t['kind'] for t in value['types']},{'list','file','function'})
        callable=value['types'][value['result']]
        self.assertEqual(callable,{'kind':'function','name':'server fn(file)->file'})
        self.assertEqual(value['parameters'][1],value['result'])

    def test_generic_templates_tests_and_hidden_captures_are_rejected(self):
        self.source('''module selected;
fn identity<T>(value:T)->T{return value;}
fn capture(value:i64)->(fn()->i64){return fn()->i64{return value;};}
fn main()->unit{identity(42);capture(1);}
test fn check_model()->unit{}
''')
        for name in ('identity','check_model','selected::capture::$lambda_0'):
            with self.subTest(name=name):
                self.assertEqual(self.cli('ffi','--symbol',name,ok=False)['code'],'E_FFI_SIGNATURE')
        value=self.cli('ffi','--symbol','selected::identity<i64>')
        self.assertEqual(value['types'],[{'kind':'i64'}])

    def test_signature_export_requires_a_selected_existing_symbol(self):
        self.source('module option;fn main()->unit{}')
        self.assertEqual(self.cli('ffi',ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('ffi','--symbol','missing',ok=False)['code'],'E_NAME')
        self.assertEqual(self.cli('ffi','--symbol','main')['types'],[{'kind':'unit'}])

    def test_transport_limits_do_not_silently_accept_larger_source_layouts(self):
        fields=''.join('field'+str(i)+':i64;' for i in range(1025))
        self.source('module bounds;struct Big{'+fields+'}fn contract(value:Big)->unit{}fn main()->unit{}')
        self.cli('check')
        self.assertEqual(self.cli('ffi','--symbol','contract',ok=False)['code'],'E_FFI_SIGNATURE')

    def test_genuine_014_snapshot_migrates_without_retagging_history(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.14.json').read_text())
        self.source(fixture['source']);old=self.historical_store('0.14')['revision'];self.file.unlink()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            source=db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0]
            ids=db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall()
        self.assertEqual(self.cli('ffi','--revision','HEAD','--symbol','legacy_foreign_names::resource_callback',ok=False)['code'],'E_LANGUAGE_VERSION')
        current=self.cli('migrate');self.assertEqual(current['language'],harness.CURRENT_LANGUAGE);self.assertNotEqual(current['revision'],old)
        contract=self.cli('ffi','--revision','HEAD','--symbol','legacy_foreign_names::resource_callback')
        self.assertEqual(contract['types'],[{'kind':'function','name':'server fn(file)->file'}])
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],fixture['stdout'])
        self.cli('test','--revision','HEAD','--target','web')
        self.assertEqual(self.cli('history')['head'],current['revision'])
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0],source)
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(),ids)
        sql=(harness.REPO/'tests/fixtures/language-0.14.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),fixture['sql_sha256'])

    def test_discovery_and_model_independent_pack_describe_source_ffi(self):
        self.source('module discovery;fn main()->unit{}')
        desc=self.cli('describe')['foreign_boundary']
        self.assertTrue(desc['source_support'])
        self.assertEqual(desc['signature_schema'],'nex.foreign-signature/1')
        self.assertIn('typed_return_validation',desc['features'])
        self.assertIn('nex ffi',self.cli('guide','--kind','ffi')['text'])
        pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertIn('foreign_signature_schema',pack['documents'])

if __name__=='__main__':unittest.main()
