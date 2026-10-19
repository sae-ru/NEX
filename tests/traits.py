"""Source traits, associated projections, constructor kinds and static dispatch."""
import json
from pathlib import Path
import sqlite3
import unittest
import support as harness

BOX='''module box;
trait Content {type Item;fn get(value:Self)->Content::Item<Self>;}
struct Box<T> {value:T;}
fn extract<T>(value:Box<T>)->T {return value.value;}
impl boxed<T>:Content for Box<T> {type Item=T;get=extract<T>;}
fn read<T:Content>(value:T)->Content::Item<T> {return Content<T>::get(value);}
fn main()->unit!{io} {print(read(Box<str>("🧠")));}
test fn values()->unit {assert(read(Box<i64>(42))==42);let get:fn(Box<i64>)->i64=Content<Box<i64>>::get;assert(get(Box<i64>(7))==7);}
'''
MAPPER='''module mapper;
trait Mapper<Self<_>> {fn map<A,B>(values:Self<A>,apply:fn(A)->B)->Self<B>;}
fn map_list<A,B>(values:list<A>,apply:fn(A)->B)->list<B> {
 var output:list<B>=[];var index:i64=0;
 while index<len(values){output=push(output,apply(values[index]));index=index+1;}
 return output;
}
impl list_mapper:Mapper for list {map=map_list;}
fn convert<F<_>:Mapper,A,B>(values:F<A>,apply:fn(A)->B)->F<B> {return Mapper<F>::map<A,B>(values,apply);}
fn increase(value:i64)->i64 {return value+1;}
fn main()->unit!{io} {print(convert([1,2],increase));}
test fn values()->unit {
 assert(convert<list,i64,i64>([1,2],increase)==[2,3]);
 assert(Mapper<list>::map([2,3],increase)==[3,4]);
 let apply:fn(list<i64>,fn(i64)->i64)->list<i64>=Mapper<list>::map;
 assert(apply([4],increase)==[5]);
}
'''

class Traits(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'main.nex'}))

    def rows(self):
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            names=[name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
            return {name:set(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()) for name in names}

    def agreement(self,source,stdout):
        self.source(source)
        self.assertEqual(self.cli('eval')['stdout'],stdout)
        self.assertEqual(self.cli('run')['stdout'],stdout)
        self.cli('test');self.cli('test','--target','web')

    def test_descriptor_model_pack_and_source_guide_match(self):
        descriptor=self.cli('describe')
        self.assertEqual(descriptor['version'],'0.16')
        self.assertTrue({'user_traits','associated_types','constructor_parameters','static_trait_dispatch'}<=set(descriptor['generic_features']))
        guide=self.cli('guide','--kind','trait')
        self.assertEqual(guide['language'],'0.16');self.assertIn('impl boxed',guide['text'])
        pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(pack['language_version'],'0.16');self.assertEqual(pack['documents']['traits'],'docs/traits.md')
        for path in pack['examples'].values():self.assertTrue((harness.REPO/path).is_file(),path)

    def test_associated_types_generic_impls_and_method_references(self):
        self.agreement(BOX,'🧠\n')

    def test_constructor_parameters_generic_methods_and_inference(self):
        self.agreement(MAPPER,'[2,3]\n')

    def test_higher_kinded_nominal_fields_and_immutable_closures(self):
        self.agreement(MAPPER.replace('fn main()->unit!{io} {print(convert([1,2],increase));}', '''
struct Wrapped<F<_>,T> {values:F<T>;}
fn wrap<F<_>,T>(values:F<T>)->Wrapped<F,T> {return Wrapped<F,T>(values);}
fn main()->unit!{io} {let value:Wrapped<list,i64>=wrap([2,3]);let offset:i64=4;print(convert(value.values,fn(x:i64)->i64{return x+offset;}));}
'''),'[6,7]\n')

    def test_projected_integer_and_nested_wire_bounds(self):
        self.agreement('''module bounds;
trait Number {type Item:integer;fn get(value:Self)->Number::Item<Self>;}
fn number(value:i64)->i64 {return value;}
impl integers:Number for i64 {type Item=i64;get=number;}
fn add<T:Number>(value:T)->Number::Item<T> {return Number<T>::get(value)+1;}
fn encode<T:Number>(value:T)->str {return encode_json([add(value)]);}
fn main()->unit!{io} {print(encode(41));}
test fn values()->unit {assert(add(41)==42);assert(encode(41)=="[\\\"42\\\"]");}
''','["42"]\n')

    def test_evaluation_order_short_circuit_and_checked_native_trap(self):
        source='''module order;
trait Join {fn join(left:Self,right:Self)->Self!{io};}
fn joined(left:str,right:str)->str!{io} {print("body");return left+right;}
impl strings:Join for str {join=joined;}
fn left()->str!{io} {print("left");return "A";}
fn right()->str!{io} {print("right");return "🧠";}
trait Truth {fn truth(value:Self)->bool;}
fn truth(value:bool)->bool {assert(value);return value;}
impl booleans:Truth for bool {truth=truth;}
fn main()->unit!{io} {assert(!(false&&Truth<bool>::truth(false)));print(Join<str>::join(left(),right()));}
test fn values()->unit {assert(!(false&&Truth<bool>::truth(false)));}
'''
        self.agreement(source,'left\nright\nbody\nA🧠\n')
        self.source('''module overflow;
trait Sum {fn add(left:Self,right:Self)->Self;}
fn add(left:i64,right:i64)->i64 {return left+right;}
impl numbers:Sum for i64 {add=add;}
fn main()->i64 {return Sum<i64>::add(9223372036854775807,1);}
''')
        reference=self.cli('eval',ok=False)
        self.assertEqual(reference['code'],'E_OVERFLOW')
        native=self.cli('run',ok=False)
        self.assertEqual(native['exit_code'],70)
        diagnostic=native['native_diagnostics']['diagnostics'][0]
        self.assertEqual(diagnostic['status'],'mapped')
        self.assertEqual(diagnostic['report']['code'],'E_OVERFLOW')
        self.assertEqual(diagnostic['operation_id'],reference['operation_id'])
        self.assertEqual(diagnostic['operation_site'],reference['operation_site'])

    def test_import_visibility_and_orphan_coherence(self):
        (self.root/'model.nex').write_text('''module library;
pub trait Read {type Item;fn read(value:Self)->Read::Item<Self>;}
pub struct Value {number:i64;}
fn hidden(value:Value)->i64 {return value.number;}
impl values:Read for Value {type Item=i64;read=hidden;}
trait Private {fn hidden(value:Self)->i64;}
''')
        self.agreement('''module imported;import "./model.nex" as model;
fn main()->unit!{io} {print(model::Read<model::Value>::read(model::Value(42)));}
test fn values()->unit {assert(model::Read<model::Value>::read(model::Value(42))==42);}
''','42\n')
        self.source('''module orphan;import "./model.nex" as model;
fn other(value:model::Value)->i64 {return value.number;}
impl forbidden:model::Read for model::Value {type Item=i64;read=other;}
fn main()->unit {}
''')
        # The already existing implementation overlaps as well; a nonlocal
        # implementation must fail ownership before dispatch is considered.
        self.assertEqual(self.cli('check',ok=False)['code'],'E_TRAIT_ORPHAN')
        self.source('module private;import "./model.nex" as model;fn bad<T:model::Private>(value:T)->T{return value;}fn main()->unit{}')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_VISIBILITY')

    def test_public_contracts_cannot_expose_private_traits_or_associated_types(self):
        for body in [
            'trait Hidden {} pub fn leak<T:Hidden>(value:T)->T{return value;}',
            'struct Private {} pub trait Visible {type Item;} impl visible:Visible for i64 {type Item=Private;}',
            'struct Private {} pub trait Visible {fn get(value:Self)->Private;}',
        ]:
            with self.subTest(body=body):
                self.source('module privacy;'+body+'fn main()->unit{}')
                self.assertEqual(self.cli('check',ok=False)['code'],'E_VISIBILITY')

    def test_generic_constructor_frame_and_trait_helper_watch_preserve_revision(self):
        source=MAPPER.replace('fn main()->unit!{io} {print(convert([1,2],increase));}', '''
fn identity<T>(value:T)->T{return value;}
fn observe<F<_>:Mapper>(value:F<i64>)->unit!{io}{print(Mapper<F>::map<i64,i64>(value,increase));}
fn main()->unit!{io}{observe<list>([41]);}
''')
        self.source(source);session=self.cli('debug');manifest=json.loads(Path(session['manifest']).read_text())
        frame={'schema':'nex.debug-frame/1','language':'0.16','revision':session['revision'],'build_key':manifest['build_key'],
               'function':'mapper::observe<list>','stop':{'process_id':'1','thread_id':'2','frame_id':0,'stop_id':'1'},
               'bindings':[{'name':'value','type':'list<i64>','value':['41']}],'truncated':False}
        path=self.root/'frame.json';path.write_text(json.dumps(frame))
        for expression,expected in [('identity<F<i64>>(value)',['41']),('Mapper<F>::map<i64,i64>(value,increase)',['42'])]:
            result=self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression)
            self.assertEqual(result['value'],expected);self.assertEqual(result['revision'],session['revision'])

    def test_client_emission_excludes_unreachable_server_implementations(self):
        self.source('''module clients;
struct User {value:i64;}
trait Visible {client fn show(value:Self)->str;}
client fn label(value:User)->str{return "safe";}
impl users:Visible for User {show=label;}
trait Hidden {server fn secret(value:Self)->str;}
server fn secret(value:User)->str{return "SERVER_TRAIT_SECRET_742";}
impl hidden:Hidden for User {secret=secret;}
client fn main()->str{return Visible<User>::show(User(42));}
client test fn values()->unit{assert(main()=="safe");}
''')
        self.cli('test','--target','web')
        emitted=self.cli('emit','--kind','typescript',machine=False).stdout
        self.assertIn('safe',emitted);self.assertNotIn('SERVER_TRAIT_SECRET_742',emitted)
        self.assertNotIn('clients::secret',emitted)

    def test_concrete_associated_api_model_extraction_has_no_server_code(self):
        self.source('''module typed_api;import "std/api.nex" as api;
pub trait Number {type Item:wire;fn get(value:Self)->Number::Item<Self>;}
fn number(value:i64)->i64{return value;}
impl integers:Number for i64 {type Item=i64;get=number;}
pub struct Payload {value:Number::Item<i64>;}
server fn secret()->str{return "SERVER_MODEL_SECRET_981";}
server fn echo(context:api::Context,input:Payload)->result<Payload>{return ok(input);}
endpoint echo("POST","/api/echo")=echo;
fn main()->unit{}
''')
        # Endpoint operation names share the ordinary declaration namespace.
        self.source(self.file.read_text().replace('endpoint echo(', 'endpoint echo_value('))
        generated=self.cli('api','--directory',self.root/'generated')
        client=self.root/'generated/client'
        for path in client.rglob('*.nex'):
            text=path.read_text();self.assertNotIn('SERVER_MODEL_SECRET_981',text)
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/api.nex" as sdk;
import "./generated/client/models/typed_api.nex" as model;
import "std/net.nex" as net;
test fn values()->unit{
 let request:net::Command=sdk::request_echo_value("id","token",model::Payload(42),"done",1000);
 let envelope:net::TypedPayload=unwrap(decode_json<net::TypedPayload>(request.body));
 assert(unwrap(decode_json<model::Payload>(envelope.body)).value==42);
}
fn main()->unit{}
''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')

    def test_api_models_preserve_constructor_kinds_and_nominal_arguments(self):
        self.source('''module constructor_api;import "std/api.nex" as api;
pub struct Box<T> {value:T;}
pub struct Wrapped<F<_>,T> {value:F<T>;}
server fn echo(context:api::Context,input:Wrapped<Box,i64>)->result<Wrapped<Box,i64>>{return ok(input);}
endpoint echo_value("POST","/api/echo")=echo;
fn main()->unit{}
''')
        self.cli('api','--directory',self.root/'generated')
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/api.nex" as sdk;
import "./generated/client/models/constructor_api.nex" as model;
import "std/net.nex" as net;
test fn values()->unit {
 let data:model::Wrapped<model::Box,i64>=model::Wrapped<model::Box,i64>(model::Box(42));
 let request:net::Command=sdk::request_echo_value("id","token",data,"done",1000);
 let envelope:net::TypedPayload=unwrap(decode_json<net::TypedPayload>(request.body));
 let restored:model::Wrapped<model::Box,i64>=unwrap(decode_json<model::Wrapped<model::Box,i64>>(envelope.body));
 assert(restored.value.value==42);
}
fn main()->unit{}
''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')

    def test_api_associated_models_keep_transitive_witnesses_without_server_methods(self):
        (self.root/'contracts.nex').write_text('''module contracts;
pub trait Source {type Item:wire;server fn read(value:Self)->Source::Item<Self>!{io};}
server fn read_integer(value:i64)->str!{io}{print("SERVER_ASSOCIATED_SECRET_293");return str(value);}
impl numbers:Source for i64 {type Item=str;read=read_integer;}
pub struct Box<T> {value:T;}
pub trait Wrapped {type Item:wire;}
impl boxes<T:Source>:Wrapped for Box<T> {type Item=Source::Item<T>;}
pub struct UnusedServerModel {unused:i64;}
''')
        (self.root/'model.nex').write_text('''module model;
import "./contracts.nex" as contract;
pub struct Payload<T:contract::Wrapped> {value:contract::Wrapped::Item<T>;}
''')
        self.source('''module associated_api;
import "std/api.nex" as api;import "./contracts.nex" as contract;import "./model.nex" as model;
server fn echo(context:api::Context,input:model::Payload<contract::Box<i64>>)->result<model::Payload<contract::Box<i64>>>{return ok(input);}
endpoint echo_value("POST","/api/echo")=echo;
fn main()->unit{}
''')
        self.cli('api','--directory',self.root/'generated')
        client=self.root/'generated/client'
        for path in client.rglob('*.nex'):
            source=path.read_text()
            self.assertNotIn('SERVER_ASSOCIATED_SECRET_293',source)
            self.assertNotIn('read_integer',source);self.assertNotIn('UnusedServerModel',source)
        projected=(client/'models/contracts.nex').read_text()
        self.assertIn('trait Source',projected);self.assertIn('impl numbers',projected)
        self.assertIn('impl boxes',projected);self.assertNotIn('fn read',projected)
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/api.nex" as sdk;
import "./generated/client/models/model.nex" as model;
import "./generated/client/models/contracts.nex" as contract;
import "std/net.nex" as net;
test fn values()->unit {
 let value:model::Payload<contract::Box<i64>>=model::Payload<contract::Box<i64>>("Ada🧠");
 let request:net::Command=sdk::request_echo_value("id","token",value,"done",1000);
 let payload:net::TypedPayload=unwrap(decode_json<net::TypedPayload>(request.body));
 assert(unwrap(decode_json<model::Payload<contract::Box<i64>>>(payload.body))==value);
}
fn main()->unit{}
''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')
        consumer.write_text(consumer.read_text().replace('contract::Box<i64>','bool'))
        self.assertEqual(self.cli('check',consumer,ok=False)['code'],'E_GENERIC_BOUND')

    def test_api_constructor_trait_models_keep_kinds_and_reject_missing_witnesses(self):
        self.source(MAPPER.replace('trait Mapper','pub trait Mapper').replace('fn main()->unit!{io} {print(convert([1,2],increase));}', '''
import "std/api.nex" as api;
pub enum Payload<F<_>:Mapper> {Items(values:F<i64>);}
server fn echo(context:api::Context,input:Payload<list>)->result<Payload<list>>{return ok(input);}
endpoint echo_value("POST","/api/echo")=echo;
fn main()->unit{}
'''))
        self.cli('api','--directory',self.root/'generated')
        projected=(self.root/'generated/client/models/mapper.nex').read_text()
        self.assertIn('Self<_>',projected);self.assertIn('F<_>',projected)
        self.assertNotIn('map_list',projected)
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/api.nex" as sdk;
import "./generated/client/models/mapper.nex" as model;
import "std/net.nex" as net;
struct Other<T> {value:T;}
test fn values()->unit {
 let value:model::Payload<list>=model::Payload<list>::Items([41,42]);
 let request:net::Command=sdk::request_echo_value("id","token",value,"done",1000);
 let payload:net::TypedPayload=unwrap(decode_json<net::TypedPayload>(request.body));
 assert(unwrap(decode_json<model::Payload<list>>(payload.body))==value);
}
fn main()->unit{}
''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')
        original=consumer.read_text()
        consumer.write_text(original.replace('Payload<list>','Payload<bool>'))
        self.assertEqual(self.cli('check',consumer,ok=False)['code'],'E_GENERIC_KIND')
        consumer.write_text(original.replace('Payload<list>','Payload<Other>'))
        self.assertEqual(self.cli('check',consumer,ok=False)['code'],'E_GENERIC_BOUND')

    def test_rejected_conformance_kinds_and_unused_bodies_preserve_graph(self):
        tag='trait Tag {fn tag(value:Self)->i64;} fn tag(value:i64)->i64{return value;} '
        any_tag='trait Tag {fn tag(value:Self)->i64;} fn constant<T>(value:T)->i64{return 1;} '
        associated='trait R {type Item:wire;fn get(value:Self)->R::Item<Self>;} '
        cases=[
            (tag+'impl bad:Tag for i64 {}','E_TRAIT_CONFORMANCE'),
            (tag+'fn wrong(value:i64)->bool{return true;}impl bad:Tag for i64 {tag=wrong;}','E_TRAIT_METHOD'),
            (tag+'fn wrong(value:i64)->i64!{io}{print(value);return value;}impl bad:Tag for i64 {tag=wrong;}','E_TRAIT_METHOD'),
            (tag+'server fn wrong(value:i64)->i64{return value;}impl bad:Tag for i64 {tag=wrong;}','E_TRAIT_METHOD'),
            (tag+'fn bad<T>(value:T)->i64{return Tag<T>::tag(value);}','E_GENERIC_BOUND'),
            (tag+'fn bad<T:Tag>(value:T)->T{return 1;}','E_TYPE'),
            (any_tag+'impl all<T>:Tag for T {tag=constant<T>;}impl number:Tag for i64 {tag=constant<i64>;}','E_TRAIT_OVERLAP'),
            (any_tag+'impl a<T:wire>:Tag for T {tag=constant<T>;}impl b<T:ordered>:Tag for T {tag=constant<T>;}','E_TRAIT_OVERLAP'),
            (tag+'impl bad<T>:Tag for i64 {tag=tag;}','E_TRAIT_HEAD'),
            (associated+'fn get(value:i64)->i64{return value;}impl bad:R for i64 {get=get;}','E_TRAIT_CONFORMANCE'),
            (associated+'fn get(value:i64)->i64{return value;}impl bad:R for i64 {type Item=R::Item<i64>;get=get;}','E_TRAIT_CYCLE'),
            (associated+'fn get(value:i64)->(fn()->i64){return fn()->i64{return value;};}impl bad:R for i64 {type Item=fn()->i64;get=get;}','E_GENERIC_BOUND'),
            (any_tag+'impl cycle<T:Tag>:Tag for T {tag=constant<T>;}fn bad()->i64{return Tag<i64>::tag(1);}','E_TRAIT_CYCLE'),
            ('trait M<Self<_>> {} fn bad<T:M>(value:T)->T{return value;}','E_GENERIC_KIND'),
            ('fn bad<F<_>>(value:F)->unit{}','E_GENERIC_KIND'),
            ('fn bad<F<_>>(value:F<i64,str>)->unit{}','E_GENERIC_KIND'),
            ('fn bad<F<_>>(value:F<i64>)->i64{return value[0];}','E_TYPE'),
            ('fn bad<F<_>:wire>()->unit{}','E_GENERIC_KIND'),
        ]
        self.source('module rejected;fn main()->unit{}');self.cli('check');before=self.rows()
        for body,code in cases:
            with self.subTest(body=body):
                self.source('module rejected;'+body+'fn main()->unit{}')
                self.assertEqual(self.cli('check',ok=False)['code'],code)
                self.assertEqual(self.rows(),before)

    def test_trait_impl_context_graph_and_atomic_source_repair(self):
        self.source('''module repair;
trait Tag {fn tag(value:Self)->i64;}
fn number(value:i64)->i64{return value;}
fn text(value:i64)->str{return "n:"+str(value);}
impl numbers:Tag for i64 {tag=number;}
fn main()->unit!{io}{let value:i64=Tag<i64>::tag(21);print(value);}
''')
        revision=self.cli('check')['revision'];before=self.rows()
        trait=self.cli('context','--entity','trait','--symbol','Tag')['node']
        impl=self.cli('context','--entity','impl','--symbol','numbers')['node']
        self.assertTrue(trait['editable']);self.assertTrue(impl['editable'])
        self.assertFalse(self.cli('context','--symbol','repair::Tag::tag')['editable'])
        patch=self.root/'patch.json'
        replacements=[{'kind':'trait','name':'Tag','source':'trait Tag {fn tag(value:Self)->str;}'},
                      {'kind':'impl','name':'numbers','source':'impl numbers:Tag for i64 {tag=text;}'},
                      {'name':'main','source':'fn main()->unit!{io}{let value:str=Tag<i64>::tag(21);print(value);}'}]
        patch.write_text(json.dumps({'expected_revision':revision,'replacements':replacements[:1]}))
        self.cli('apply','--patch',patch,ok=False);self.assertEqual(self.rows(),before)
        patch.write_text(json.dumps({'expected_revision':revision,'replacements':replacements}))
        changed=self.cli('apply','--patch',patch)['revision'];self.assertNotEqual(changed,revision)
        self.file.unlink()
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'n:21\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'n:21\n')
        self.assertEqual(self.cli('eval','--revision',revision)['stdout'],'21\n')
        self.assertEqual(self.cli('apply','--patch',patch,ok=False)['code'],'E_CONFLICT')
        graph=self.cli('subgraph','--entity','impl','--symbol','numbers','--depth','2')
        self.assertIn('repair::Tag',json.dumps(graph));self.assertIn('repair::text',json.dumps(graph))

    def test_genuine015_migration_preserves_history_ids_and_names(self):
        metadata=json.loads((harness.REPO/'tests/fixtures/language-0.15.json').read_text())
        self.source(metadata['source']);fixture=self.historical_store('0.15')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.15','entry':'main.nex'}))
        before=self.rows()
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION');self.assertEqual(self.rows(),before)
        self.assertEqual(self.cli('eval','--revision',fixture['revision'],ok=False)['code'],'E_LANGUAGE_VERSION')
        self.file.unlink();current=self.cli('migrate','--revision',fixture['revision'])['revision']
        self.assertNotEqual(current,fixture['revision']);after=self.rows()
        for table,rows in before.items():
            if table!='head':self.assertLessEqual(rows,after[table],table)
        self.assertFalse(self.file.exists());self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],fixture['stdout'])
        exported=self.root/'exported';self.cli('export','--revision','HEAD','--directory',exported)
        self.assertEqual(json.loads((exported/'nex.json').read_text())['language'],'0.16')
        self.assertEqual(self.cli('eval',cwd=exported)['stdout'],fixture['stdout'])
        self.assertEqual(self.cli('run',cwd=exported)['stdout'],fixture['stdout'])
        self.cli('test','--target','web',cwd=exported)

if __name__=='__main__':unittest.main()
