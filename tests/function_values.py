"""Observable callable/capture semantics; debugger and migration integration is in progress."""
import hashlib
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest
import support as harness


class FunctionValues(harness.ToolchainCase):
    def test_discovery_and_language_pack_advertise_checked_function_values(self):
        descriptor=self.cli('describe')
        self.assertEqual(descriptor['version'],'0.15')
        self.assertIn('snapshot_closures',descriptor['function_value_features'])
        self.assertEqual(descriptor['function_value_limits']['captures'],1024)
        self.assertEqual(descriptor['function_value_limits']['signature_bytes'],4096)
        self.assertEqual(set(descriptor['generic_constraints']['implications']['integer']),{'number','add','ordered','wire'})
        self.assertEqual(descriptor['generic_constraints']['implications']['ordered'],['wire'])
        self.assertIn('nominal payloads',descriptor['generic_constraints']['wire'])
        for supported in ['function_values','generic_constraints','match_expressions','nested_patterns','pattern_guards','result_patterns']:
            self.assertNotIn(supported,descriptor['not_yet_supported'])
        guide=self.cli('guide','--kind','function')
        self.assertEqual(guide['language'],'0.15')
        self.assertEqual(guide['text'],(harness.REPO/'docs/functions.md').read_text())
        self.assertEqual(len(guide['hash']),64)
        pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(pack['documents']['functions'],descriptor['function_value_guide'])

    def test_actual_022_migration_preserves_history_sources_and_operation_ids(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.9.json').read_text())
        self.source(fixture['source'])
        old_binary=harness.REPO/'build/sdk-0.22.0/bin/nex'
        if sys.platform=='darwin' and old_binary.is_file():
            self.assertEqual(hashlib.sha256(old_binary.read_bytes()).hexdigest(),fixture['compiler_sha256'])
            def old_cli(*args):
                return json.loads(subprocess.check_output([str(old_binary),*map(str,args),'--json'],cwd=self.root))
            old=old_cli('check')['revision'];graph=old_cli('graph')
            nodes=old_cli('operations','--symbol','choose')['nodes']
        else:
            saved=self.historical_store('0.9');old=saved['revision'];graph=saved['graph'];nodes=saved['operations']
        self.assertEqual(old,fixture['revision'])
        self.file.unlink()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.9','entry':'main.nex'}))
        self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION')
        current=self.cli('migrate');self.assertEqual(current['language'],'0.15');self.assertNotEqual(current['revision'],old)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.9','0.15'})
        migrated=self.cli('graph')
        self.assertEqual(migrated['bundle'],graph['bundle'])
        self.assertEqual({n['name']:n['id'] for n in graph['nodes']},{n['name']:n['id'] for n in migrated['nodes']})
        self.assertEqual({n['path']:n['id'] for n in nodes},{n['path']:n['id'] for n in self.cli('operations','--symbol','choose')['nodes']})
        self.assertTrue(all(n['definition']['format']=='nex.function/12' for n in migrated['nodes']))
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')
        old_export=self.root/'old';self.cli('export','--revision',old,'--directory',old_export)
        self.assertEqual(json.loads((old_export/'nex.json').read_text())['language'],'0.9')
        self.assertEqual((old_export/'main.nex').read_text(),fixture['source'])
        exported=self.root/'current';self.cli('export','--revision','HEAD','--directory',exported)
        self.assertEqual(json.loads((exported/'nex.json').read_text())['language'],'0.15')
        self.assertEqual(self.cli('check',cwd=exported)['revision'],current['revision'])

    def test_unchanged_nested_match_operation_ids_survive_other_function_edits(self):
        source='''module stable_arms;enum Maybe{None;Some(value:i64);}
fn choose(value:result<Maybe>)->i64{return match value{ok(Maybe::Some(n)) if n>0=>n,ok(Maybe::None())=>0,_=>-1};}
fn main()->unit!{io}{print(choose(ok(Maybe::Some(42))));}
'''
        self.source(source);self.cli('check')
        before=self.cli('operations','--symbol','choose')['nodes']
        self.source(source.replace('print(choose(ok(Maybe::Some(42))))','print(choose(ok(Maybe::Some(41))))'))
        self.cli('check');after=self.cli('operations','--symbol','choose')['nodes']
        self.assertEqual({n['path']:n['id'] for n in before},{n['path']:n['id'] for n in after})

    def test_portable_022_sql_archive_preserves_recorded_operation_ids(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.9.json').read_text())
        self.source(fixture['source']);saved=self.historical_store('0.9')
        current=self.cli('migrate')
        self.assertEqual(current['language'],'0.15')
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.9','0.15'})
        self.assertEqual({n['name']:n['id'] for n in saved['graph']['nodes']},
                         {n['name']:n['id'] for n in self.cli('graph')['nodes']})
        self.assertEqual({n['path']:n['id'] for n in saved['operations']},
                         {n['path']:n['id'] for n in self.cli('operations','--symbol','choose')['nodes']})
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')

    def test_rejected_legacy_serializer_migration_is_atomic_and_explicitly_repairable(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.9-wire.json').read_text())
        self.source(fixture['source']);old=self.historical_store('0.9-wire')
        self.assertEqual(self.cli('migrate',ok=False)['code'],'E_GENERIC_BOUND')
        history=self.cli('history')
        self.assertEqual(history['head'],old['revision'])
        self.assertEqual(len(history['revisions']),1)
        fixed=fixture['source'].replace('serialize<T>','serialize<T:wire>')
        graph=copy.deepcopy(fixture['graph']);graph['source']=fixed;graph['bundle']['files']['main.nex']=fixed
        repair=self.root/'repair.json';repair.write_text(json.dumps(graph))
        current=self.cli('migrate',repair)
        self.assertEqual(current['language'],'0.15')
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.9','0.15'})
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'"42"\n')
        original=self.root/'original';self.cli('export','--revision',old['revision'],'--directory',original)
        self.assertEqual((original/'main.nex').read_text(),fixture['source'])
        self.assertEqual(self.cli('graph')['bundle']['files']['main.nex'],fixed)

    def backends(self, expected=None):
        observed = self.cli('eval')['stdout']
        if expected is not None:
            self.assertEqual(observed, expected)
        for profile in ('debug', 'release'):
            self.assertEqual(self.cli('run', '--profile', profile)['stdout'], observed)
            self.cli('test', '--profile', profile)
        self.cli('test', '--target', 'web')

    def test_snapshots_nested_returned_fields_lists_and_named_values(self):
        self.source('''module values;
struct Handler {callback:fn(i64)->i64;}
fn increment(value:i64)->i64{return value+1;}
fn twice(callback:fn(i64)->i64,value:i64)->i64{return callback(callback(value));}
fn make(offset:i64)->(fn(i64)->i64){return fn(value:i64)->i64{return value+offset;};}
fn nested(offset:i64)->(fn(i64)->(fn(i64)->i64)){
 return fn(first:i64)->(fn(i64)->i64){return fn(second:i64)->i64{return first+second+offset;};};
}
fn main()->unit!{io}{print(nested(20)(20)(2));}
test fn cases()->unit{
 var offset:i64=40;let captured:fn(i64)->i64=fn(n:i64)->i64{return n+offset;};offset=900;
 assert(captured(2)==42);assert(twice(increment,40)==42);assert(twice(make(1),40)==42);
 let callbacks:list<fn(i64)->i64>=[make(1),increment];assert(callbacks[0](41)==42);
 assert(Handler(make(1)).callback(41)==42);assert(nested(20)(20)(2)==42);
}''')
        self.backends('42\n')

    def test_generic_returned_captures_references_and_higher_order_calls(self):
        self.source('''module generic_functions;
fn identity<T>(value:T)->T{return value;}
fn make<T>(value:T)->(fn()->T){return fn()->T{return value;};}
fn apply<T>(callback:fn(T)->T,value:T)->T{return callback(value);}
fn main()->unit!{io}{print(make("A\\u0000🌍")());}
test fn cases()->unit{
 let inferred:fn(i64)->i64=identity;let explicit:fn(str)->str=identity<str>;
 assert(inferred(42)==42);assert(explicit("NEX")=="NEX");assert(make(42)()==42);
 assert(make(["A\\u0000🌍"])()[0]=="A\\u0000🌍");
 assert(apply(fn(n:i64)->i64{return n+1;},41)==42);
 assert(apply<i64>(identity,42)==42);
}''')
        self.backends('A\0🌍\n')

    def test_imported_named_bridges_and_returned_generic_closures(self):
        (self.root/'model.nex').write_text('''module callback_model;
pub fn increment(value:i64)->i64{return value+1;}
pub fn make<T>(value:T)->(fn()->T){return fn()->T{return value;};}
''')
        self.source('''module imports;import "./model.nex" as model;
fn main()->unit!{io}{let callback:fn(i64)->i64=model::increment;print(callback(41));print(model::make("NEX")());}
test fn cases()->unit{let callback:fn(i64)->i64=model::increment;assert(callback(41)==42);assert(model::make(42)()==42);}
''')
        self.backends('42\nNEX\n')

    def test_introducing_a_cross_module_reference_invalidates_bridge_provider(self):
        model=self.root/'model.nex'
        model.write_text('module bridge_model;pub fn increment(value:i64)->i64{return value+1;}')
        self.source('module bridge_user;import "./model.nex" as model;fn main()->unit!{io}{print(model::increment(41));}')
        self.cli('build');self.assertEqual(self.cli('run')['stdout'],'42\n')
        self.source('module bridge_user;import "./model.nex" as model;fn main()->unit!{io}{let callback:fn(i64)->i64=model::increment;print(callback(41));}')
        built=self.cli('build')
        self.assertEqual(built['compiled_modules'],2)
        self.assertEqual(self.cli('run')['stdout'],'42\n')
        model.write_text('module bridge_model;pub fn increment(value:i64)->i64{return value+2;}')
        updated=self.cli('build');self.assertEqual(updated['compiled_modules'],1);self.assertEqual(updated['reused_modules'],1)
        self.assertEqual(self.cli('run')['stdout'],'43\n');self.assertEqual(self.cli('eval')['stdout'],'43\n')

    def test_callee_argument_order_and_unit_effectful_calls(self):
        self.source('''module order;
fn factory()->(fn(i64,i64)->i64)!{io}{print("callee");return fn(a:i64,b:i64)->i64{return a+b;};}
fn argument(label:str,value:i64)->i64!{io}{print(label);return value;}
fn keep<T>(value:T)->T{return value;}
fn main()->unit!{io}{
 print(factory()(argument("left",40),argument("right",2)));
 let callback:fn(str)->unit!{io}=fn(text:str)->unit!{io}{print(text);};keep<fn(str)->unit!{io}>(callback)("done");
}
test fn cases()->unit{assert((fn(a:i64,b:i64)->i64{return a+b;})(40,2)==42);}
''')
        self.backends('callee\nleft\nright\n42\ndone\n')

    def test_hidden_names_cannot_collide_with_source_functions_or_modules(self):
        (self.root/'model.nex').write_text('module collision::make;pub fn lambda_0(value:i64)->i64{return value+100;}')
        self.source('''module collision;import "./model.nex" as model;
fn make__lambda_0(value:i64)->i64{return value+200;}
fn make(offset:i64)->(fn(i64)->i64){return fn(value:i64)->i64{return value+offset;};}
fn main()->unit!{io}{print(make(1)(41));print(model::lambda_0(1));print(make__lambda_0(1));}
test fn cases()->unit{assert(make(1)(41)==42);assert(model::lambda_0(1)==101);assert(make__lambda_0(1)==201);}
''')
        self.backends('42\n101\n201\n')

    def test_callable_identity_opaque_text_and_owned_reassignment(self):
        self.source('''module identity;
fn make(prefix:str)->(fn(str)->str){let labels:list<str>=["🌍"];return fn(suffix:str)->str{return prefix+labels[0]+suffix;};}
fn main()->unit!{io}{let callback:fn(str)->str=make("NEX");print(str(callback));print(callback("!"));}
test fn cases()->unit{
 let original:fn(str)->str=make("NEX");let alias:fn(str)->str=original;
 assert(original==alias);assert(original!=make("NEX"));assert([original]==[alias]);
 var current:fn(str)->str=original;var i:i64=0;
 while i<80{current=make("next");assert(current("!")=="next🌍!");i=i+1;}
 assert(original("!")=="NEX🌍!");assert(str(original)=="<function>");
 var chain:fn()->i64=fn()->i64{return 12;};var depth:i64=0;
 while depth<30{chain=fn()->i64{return chain()+1;};depth=depth+1;}
 assert(chain()==42);
 let wrapped:result<fn()->i64>=ok(chain);assert(unwrap(wrapped)()==42);
 assert((match wrapped {ok(callback)=>callback(),err(_,_)=>0})==42);
}''')
        self.backends('<function>\nNEX🌍!\n')

    def test_lexical_function_shadowing(self):
        self.source('''module shadow;
fn action(value:i64)->i64{return value+100;}
fn main()->unit!{io}{let action:fn(i64)->i64=fn(n:i64)->i64{return n+1;};print(action(41));}
test fn cases()->unit{let action:fn(i64)->i64=fn(n:i64)->i64{return n+1;};assert(action(41)==42);}
''')
        self.backends('42\n')

    def test_rejected_effects_realms_captures_signatures_and_wire_types(self):
        cases=[
            ('fn main()->unit{let f:fn(i64)->i64=fn(n:bool)->i64{return 0;};}', 'E_TYPE'),
            ('fn main()->unit{let f:fn()->unit=fn()->unit{print(1);};}', 'E_EFFECT'),
            ('fn main()->unit{let f:fn()->unit!{io}=fn()->unit!{io}{print(1);};f();}', 'E_EFFECT'),
            ('server fn remote()->i64{return 1;} fn main()->unit{let f:server fn()->i64=remote;}', 'E_REALM'),
            ('fn main()->unit{var n:i64=0;let f:fn()->unit=fn()->unit{n=1;};}', 'E_MUTABILITY'),
            ('fn main()->unit{let f:fn()->i64=fn()->i64{return missing;};}', 'E_NAME'),
            ('fn main()->unit{let f:fn()->i64=fn()->i64{};}', 'E_RETURN'),
            ('fn main()->unit{let f:fn()->i64=fn()->i64{return 1;};f(1);}', 'E_ARITY'),
            ('fn main()->unit{let f:fn()->i64=fn()->i64{return 1;};encode_json(f);}', 'E_GENERIC_BOUND'),
            ('fn decode<T>(text:str)->result<T>{return decode_json<T>(text);} fn main()->unit{}', 'E_GENERIC_BOUND'),
            ('test fn example()->unit{} fn main()->unit{let f:fn()->unit=example;}', 'E_TEST'),
        ]
        for source,code in cases:
            with self.subTest(source=source):
                self.source('module rejected;'+source)
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_recursive_wire_constraint_and_rejected_callable_fields(self):
        self.source('''module wire_values;
enum Chain<T:wire>{End;Next(value:T,tail:list<Chain<T>>);}
fn roundtrip<T:wire>(value:T)->T{return unwrap(decode_json<T>(encode_json(value)));}
fn encode_integer<T:integer>(value:T)->str{return encode_json(value);}
fn main()->unit{}
test fn cases()->unit{let value:Chain<str>=Chain::Next("A\\u0000🌍",[Chain<str>::End()]);assert(roundtrip(value)==value);assert(decode_json<i64>(encode_integer(42))==ok(42));}
''')
        self.backends('')
        self.source('module rejected_wire;struct Hidden{callback:fn()->i64;}fn main()->unit{encode_json(Hidden(fn()->i64{return 42;}));}')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_GENERIC_BOUND')

    def test_phantom_callback_types_in_function_context_and_task_linkage(self):
        self.source('''module callback_contract;
pub struct Token{id:i64;}
struct Tag<T>{id:i64;}
fn marker()->Tag<fn(Token)->i64>{return Tag(42);}
fn main()->unit{}
test fn cases()->unit{assert(marker().id==42);}
''')
        self.cli('check')
        with self.subTest(kind='function context'):
            context=self.cli('context','--symbol','marker')
            self.assertIn('callback_contract::Token',{s['name'] for s in context['structures']})
        task=self.cli('task',self.file,'--kind','init')
        check=next(c for c in task['checks'] if c['kind']=='test')
        task['requirements'].append({'id':'callback-type','text':'Retain the nominal callback argument contract',
            'bindings':[{'program':'app','kind':'structure','symbol':'callback_contract::Token'}],
            'targets':[check['target']],'checks':[check['id']]})
        taskfile=self.root/'task.json';taskfile.write_text(json.dumps(task))
        with self.subTest(kind='task linkage'):
            self.assertTrue(self.cli('task',taskfile,'--kind','check')['ok'])


if __name__=='__main__':unittest.main()
