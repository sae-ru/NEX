"""Source file ownership, effects/realms, backends and genuine 0.13 migration."""
import copy
import json
from pathlib import Path
import re
import sqlite3
import unittest
import support as harness


class Resources(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.data=self.root/'data';self.data.mkdir();(self.data/'nested').mkdir()
        self.env={'NEX_FILES_ROOT':str(self.data),'NEX_FILES_WRITE':'1'}

    def agreement(self, expected=None):
        evaluated=self.cli('eval',env=self.env)['stdout']
        if expected is not None:self.assertEqual(evaluated,expected)
        for profile in ['debug','release']:
            self.assertEqual(self.cli('run','--profile',profile,env=self.env,timeout=120)['stdout'],evaluated)
        return evaluated

    def test_streaming_aliases_cursor_modes_unicode_and_eof(self):
        self.source('''module streams;
server fn identity<T>(value:T)->T{return value;}
server fn main()->unit!{fs,io}{
 let file:file=unwrap(file_open_write("nested/Я🧠"));let alias:file=identity(file);
 assert(file_is_open(alias));assert(unwrap(file_write(file,utf8_bytes("Я\\u0000🧠")))==7);
 assert(unwrap(file_size(alias))==7);assert(unwrap(file_flush(file)));
 assert(file_close(alias));assert(!file_close(file));assert(!file_is_open(file));
 assert(error_code(file_read(file,0))=="E_RESOURCE_CLOSED");
 let append:file=unwrap(file_open_append("nested/Я🧠"));assert(unwrap(file_seek(append,0))==0);
 assert(unwrap(file_write(append,unwrap(bytes([255]))))==1);assert(file_close(append));
 let input:file=unwrap(file_open_read("nested/Я🧠"));
 assert(unwrap(file_read(input,2))==utf8_bytes("Я"));
 print(encode_base64(unwrap(file_read(input,100))));
 assert(len(unwrap(file_read(input,1)))==0);assert(unwrap(file_seek(input,0))==0);
 assert(len(unwrap(file_read(input,0)))==0);print(input);
}''')
        self.agreement('APCfp6D/\n<file>\n')
        self.assertEqual((self.data/'nested/Я🧠').read_bytes(),'Я\0🧠'.encode()+b'\xff')
        self.assertEqual(self.cli('emit','--kind','typescript',env=self.env,ok=False)['code'],'E_REALM')

    def test_returned_file_and_aggregate_enum_closure_aliases(self):
        (self.data/'input').write_bytes(b'abcdef')
        self.source('''module owners;
struct Box<T>{value:T;}
enum Maybe<T>{None;Some(value:T);}
server fn open()->file!{fs}{return unwrap(file_open_read("input"));}
server fn keep(value:file)->(server fn()->file){return server fn()->file{return value;};}
server fn select(value:Maybe<file>)->file{match value{Maybe::Some(f)=>{return f;},Maybe::None()=>{assert(false);return select(value);}}}
server fn main()->unit!{fs,io}{
 let f:file=open();let callback:server fn()->file=keep(f);
 let boxed:Box<list<file>>=Box([f,callback()]);let tagged:Maybe<file>=Maybe::Some(boxed.value[1]);
 let selected:file=select(tagged);assert(selected==f);assert(boxed.value[0]==selected);
 assert(unwrap(file_read(f,2))==utf8_bytes("ab"));assert(unwrap(file_read(selected,2))==utf8_bytes("cd"));
 let other:file=open();assert(other!=f);assert(file_close(callback()));
 assert(!file_is_open(boxed.value[0]));assert(!file_is_open(select(tagged)));assert(file_is_open(other));
 print([f,other]);
}''')
        self.agreement('["<file>","<file>"]\n')

    def test_automatic_cleanup_on_blocks_calls_and_early_returns(self):
        (self.data/'input').write_bytes(b'x')
        self.source('''module cleanup;
server fn work(n:i64)->unit!{fs}{
 let f:file=unwrap(file_open_read("input"));if n%2==0{return;}
 var i:i64=0;while i<2{let nested:file=unwrap(file_open_read("input"));
  assert(unwrap(file_size(nested))==1);if i==1{return;}i=i+1;
 }
}
server fn main()->unit!{fs,io}{
 var i:i64=0;while i<150{work(i);let local:file=unwrap(file_open_read("input"));assert(unwrap(file_size(local))==1);i=i+1;}
 print(i);
}''')
        self.agreement('150\n')

    def test_physical_quota_and_explicit_close_with_retained_values(self):
        (self.data/'input').write_bytes(b'x')
        self.source('''module quota;
server fn main()->unit!{fs,io}{
 var owned:list<file>=[];var n:i64=0;
 while n<64{owned=push(owned,unwrap(file_open_read("input")));n=n+1;}
 assert(error_code(file_open_read("input"))=="E_RESOURCE_LIMIT");
 assert(file_close(owned[0]));let next:file=unwrap(file_open_read("input"));assert(next!=owned[0]);
 assert(error_code(file_read(owned[0],0))=="E_RESOURCE_CLOSED");print(len(owned));
}''')
        self.agreement('64\n')

    def test_errors_limits_and_read_only_grants(self):
        (self.data/'input').write_bytes(b'\xff\x00')
        self.source('''module errors;
server fn main()->unit!{fs,io}{
 let f:file=unwrap(file_open_read("input"));
 assert(error_code(file_read(f,-1))=="E_RANGE");assert(error_code(file_read(f,1048577))=="LIMIT");
 assert(error_code(file_seek(f,-1))=="E_RANGE");assert(error_code(file_write(f,utf8_bytes("")))=="CAPABILITY");
 assert(error_code(file_flush(f))=="CAPABILITY");
 assert(error_code(file_open_read("missing"))=="NOT_FOUND");
 assert(error_code(file_open_read("../outside"))=="VALIDATION");
 assert(error_code(file_open_write("alias"))=="VALIDATION");
 print(encode_base64(unwrap(file_read(f,100))));
}''')
        outside=self.root/'outside';outside.write_bytes(b'unchanged');(self.data/'alias').symlink_to(outside)
        self.agreement('/wA=\n');self.assertEqual(outside.read_bytes(),b'unchanged')
        self.source('''module grants;server fn main()->unit!{fs,io}{
 print(error_code(file_open_write("new")));print(error_code(file_open_append("new")));
}''')
        for key in ['', '0','yes']:
            environment={**self.env,'NEX_FILES_WRITE':key}
            self.assertEqual(self.cli('eval',env=environment)['stdout'],'CAPABILITY\nCAPABILITY\n')
            self.assertEqual(self.cli('run',env=environment)['stdout'],'CAPABILITY\nCAPABILITY\n')
        self.assertFalse((self.data/'new').exists())

    def test_large_file_bounded_streams(self):
        (self.data/'large').write_bytes(b'x'*1048576+b'!')
        self.source('''module large;server fn main()->unit!{fs,io}{
 let f:file=unwrap(file_open_read("large"));assert(unwrap(file_size(f))==1048577);
 assert(len(unwrap(file_read(f,1048576)))==1048576);assert(unwrap(file_read(f,100))==utf8_bytes("!"));
 assert(len(unwrap(file_read(f,1)))==0);print(unwrap(file_size(f)));
}''')
        self.agreement('1048577\n')

    def test_left_to_right_once_and_short_circuit(self):
        self.source('''module ordered;
server fn handle()->file!{fs,io}{print("handle");return unwrap(file_open_append("output"));}
server fn content()->bytes!{io}{print("content");return utf8_bytes("x");}
server fn main()->unit!{fs,io}{
 assert(unwrap(file_write(handle(),content()))==1);
 let f:file=unwrap(file_open_read("output"));let a:bool=false&&file_close(f);let b:bool=true||file_close(f);
 assert(file_is_open(f));assert(unwrap(file_read(f,100))==utf8_bytes("x"));
}''')
        # Reset append state between native/reference executions explicitly.
        self.source(self.file.read_text().replace(' assert(unwrap(file_write(handle(),content()))==1);',' assert(unwrap(file_write_text("output","")));assert(unwrap(file_write(handle(),content()))==1);'))
        self.agreement('handle\ncontent\n')

    def test_effect_realm_type_and_reserved_name_rejections(self):
        cases=[
            ('fn f(value:file)->unit{}','E_REALM'),
            ('client fn f(value:list<result<file>>)->unit{}','E_REALM'),
            ('struct Box<T>{value:T;} fn f(value:Box<file>)->unit{}','E_REALM'),
            ('fn f()->unit{let xs:list<file>=[];}','E_REALM'),
            ('server fn f(value:file)->unit{file_close(value);}','E_EFFECT'),
            ('server fn f(value:file)->unit{file_is_open(value);}','E_EFFECT'),
            ('fn f()->unit{file_open_read("x");}','E_REALM'),
            ('server fn f(value:file)->unit!{fs}{file_read(value,true);}','E_TYPE'),
            ('server fn f(value:file)->unit!{fs}{file_write(value,"x");}','E_TYPE'),
            ('server fn f(value:file)->unit!{fs}{file_seek(value);}','E_ARITY'),
            ('server fn f(value:file)->unit{let cb:fn()->str=fn()->str{return str(value);};}','E_REALM'),
            ('server fn f()->unit{let cb:fn(file)->unit=fn(x:file)->unit{};}','E_REALM'),
            ('struct file{value:i64;}','E_DUPLICATE'),
            ('fn file()->i64{return 0;}','E_DUPLICATE'),
            ('fn f<file>(x:file)->file{return x;}','E_DUPLICATE'),
            ('fn file_open_read()->i64{return 0;}','E_DUPLICATE'),
            ('fn identity<T>(x:T)->T{return x;} server fn f(x:file)->file{return identity(x);}','E_REALM'),
            ('server fn f(x:file)->unit{let n:i64=len(x);}','E_TYPE'),
        ]
        for body,code in cases:
            with self.subTest(body=body):
                self.source('module rejected;'+body)
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_no_wire_or_api_file_values_including_phantom_arguments(self):
        for value in ['file','list<file>','result<file>','Box<file>','Phantom<file>']:
            with self.subTest(value=value):
                self.source('module forbidden;struct Box<T>{value:T;}struct Phantom<T>{number:i64;}server fn f(x:'+value+')->str{return encode_json(x);}')
                self.assertEqual(self.cli('check',ok=False)['code'],'E_GENERIC_BOUND')
        self.source('''module api_files;
import "std/api.nex" as api;
pub struct Input{name:str;}pub struct Output{resource:file;}
pub server fn handler(context:api::Context,input:Input)->result<Output>{return err("NO","unsupported");}
endpoint file_api("POST","/api/file")=handler;
''')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_TYPE')

    def test_browser_excludes_unused_server_files_and_allows_contextual_alias(self):
        (self.root/'model.nex').write_text('module model;pub struct Item{value:i64;}')
        self.source('''module browser;
import "./model.nex" as file;
struct Private{resource:file;}
server fn secret()->file!{fs}{return unwrap(file_open_read("SERVER_RESOURCE_SECRET"));}
client fn main()->unit!{io}{let file:fn(i64)->i64=fn(n:i64)->i64{return n+1;};let item:file::Item=file::Item(file(41));print(item.value);}
client test fn browser_test()->unit{let file:fn(i64)->i64=fn(n:i64)->i64{return n+1;};let item:file::Item=file::Item(file(41));assert(item.value==42);}
''')
        emitted=self.cli('emit','--kind','typescript',machine=False).stdout
        self.assertNotIn('SERVER_RESOURCE_SECRET',emitted);self.assertNotIn('file_open_read',emitted)
        self.assertNotIn('resource:file',emitted)
        self.cli('test','--target','web')

    def test_descriptor_and_language_pack(self):
        value=self.cli('describe');self.assertEqual(value['version'],harness.CURRENT_LANGUAGE);self.assertIn('file',value['types'])
        self.assertTrue(value['host_resource_runtime']['source_support'])
        self.assertIn('identity_aliases',value['resource_features'])
        self.assertIn('file_open_read',self.cli('guide','--kind','resources')['text'])

    def test_genuine_013_plain_migration_keeps_history_and_ids(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.13.json').read_text());self.source(fixture['source']);old=self.historical_store('0.13')['revision'];self.file.unlink()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            old_source=db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0]
            ids=db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall()
        self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION');current=self.cli('migrate')
        self.assertEqual(current['language'],harness.CURRENT_LANGUAGE);self.assertNotEqual(current['revision'],old)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],fixture['stdout']);self.cli('test','--revision','HEAD','--target','web')
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0],old_source)
            self.assertEqual(db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall(),ids)
        self.assertEqual({v['language'] for v in self.cli('history')['revisions']},{'0.13',harness.CURRENT_LANGUAGE})

    def repair_fixture(self,suffix):
        fixture=json.loads((harness.REPO/('tests/fixtures/language-'+suffix+'.json')).read_text());self.source(fixture['source']);old=self.historical_store(suffix)['revision'];self.file.unlink()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            original=db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0]
            identities=db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name').fetchall()
        self.assertEqual(self.cli('migrate',ok=False)['code'],'E_DUPLICATE')
        self.assertEqual(self.cli('history')['head'],old)
        bundle=json.loads(original)
        names=['file_open_read','file_open_write','file_open_append','file_read','file_write','file_seek','file_size','file_flush','file_close','file_is_open','file']
        for key,source in bundle['files'].items():
            for name in names:source=re.sub(r'\b'+name+r'\b','LegacyFile' if name=='file' else 'legacy_'+name,source)
            bundle['files'][key]=source
        candidate=self.root/'repair.json';candidate.write_text(json.dumps({'schema':'nex.graph/2','language':'0.13','revision':old,'bundle':bundle}))
        current=self.cli('migrate',candidate);self.assertEqual(current['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],fixture['stdout']);self.cli('test','--revision','HEAD','--target','web')
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            self.assertEqual(db.execute('SELECT source FROM revisions WHERE hash=?',(old,)).fetchone()[0],original)
            after=set(db.execute('SELECT module,name,id FROM node_ids').fetchall());self.assertTrue(set(identities)<=after)

    def test_reserved_resource_name_migration_requires_reviewed_repair(self):
        self.repair_fixture('0.13-resource-names')

    def test_reserved_streaming_and_generic_name_migration_requires_reviewed_repair(self):
        self.repair_fixture('0.13-stream-names')


if __name__=='__main__':unittest.main()
