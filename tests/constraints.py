"""Builtin generic capabilities, parametric soundness and versioned authoring."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness


class Constraints(harness.ToolchainCase):
    def test_example_native_reference_typescript_and_discovery(self):
        self.source((harness.REPO/'examples/constraints.nex').read_text())
        self.assertEqual(self.cli('eval')['stdout'],'NEX 🧠\n42\n[1,2,3]\n')
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],'NEX 🧠\n42\n[1,2,3]\n')
            self.cli('test','--profile',profile)
        self.cli('test','--target','web')
        descriptor=self.cli('describe');self.assertEqual(descriptor['version'],'0.18')
        self.assertEqual(descriptor['generic_constraints']['add'],['i64','f64','str','bytes','list<T>'])
        context=self.cli('context','--symbol','combine')
        self.assertEqual(context['type_bounds'],{'constraints::combine::T':['add']})

    def test_invalid_constraints_arguments_and_unused_bodies_are_rejected(self):
        combine='fn combine<T:add>(x:T,y:T) -> T {return x+y;} '
        cases=[
            ('fn bad<T:unknown>(x:T) -> T {return x;}','E_GENERIC_BOUND'),
            ('fn bad<T:add+add>(x:T) -> T {return x;}','E_GENERIC_BOUND'),
            (combine+'fn bad() -> unit {combine(true,false);}','E_GENERIC_BOUND'),
            (combine+'fn bad<T>(x:T) -> T {return combine(x,x);}','E_GENERIC_BOUND'),
            (combine+'fn bad<T:ordered>(x:T) -> T {return combine(x,x);}','E_GENERIC_BOUND'),
            ('fn bad<T:add>(x:T) -> bool {return x<x;}','E_TYPE'),
            ('fn bad<T:ordered>(x:T) -> T {return x+x;}','E_TYPE'),
            ('fn bad<T:add>(x:T) -> T {return -x;}','E_TYPE'),
            ('fn bad<T:add>(x:T) -> T {return x- x;}','E_TYPE'),
            ('fn bad<T:add>() -> T {return 1;}','E_TYPE'),
            ('fn value<T:integer>() -> T {return 1;} fn bad() -> unit {value<str>();}','E_GENERIC_BOUND'),
            ('struct Box<T:add>{value:T;} struct Bad<U>{value:Box<U>;}','E_GENERIC_BOUND'),
            ('enum N<T:integer>{Value(value:T);} fn bad() -> unit {N<str>::Value("x");}','E_GENERIC_BOUND'),
            ('struct Tag<T:ordered>{id:i64;} fn bad() -> unit {let x:Tag<str> = Tag(1);}','E_GENERIC_BOUND'),
            ('fn fixed() -> i64 {return 1;} fn bad<T:integer>() -> T {return fixed();}','E_TYPE'),
            ('fn bad<T:integer,U:integer>(x:T,y:U) -> T {return x+y;}','E_TYPE'),
            ('fn bad<T:integer>(x:T) -> T {return x + true;}','E_TYPE'),
        ]
        for body,code in cases:
            with self.subTest(body=body):
                self.source('module rejected; '+body+' fn main() -> unit {}')
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_forwarded_bounds_recursive_models_and_contextual_integer_literals(self):
        self.source('''module forwarding;
struct Box<T:add>{value:T;}
enum Chain<T:integer>{End; Next(value:T,tail:list<Chain<T>>);}
fn add<T:add>(x:T,y:T) -> T {return x+y;}
fn first<T:ordered>(x:T,y:T) -> T {if x<y {return x;}return y;}
fn number<T:integer>() -> T {return 42;}
fn arithmetic<T:integer>(x:T) -> T {
 assert(0<x);assert(x>0);assert(1+x == x+1);assert((1+2)*x == x*3);
 assert(-(-x) == x);assert(x / 2 == 21);assert(x % 5 == 2);
 return first(add(x,0),number<T>());
}
fn nested<T:integer>(x:T) -> Box<T> {return Box(arithmetic(x));}
fn both<T:add+ordered>(x:T,y:T) -> T {return first(add(x,y),x);}
fn main() -> unit {}
test fn checks() -> unit {
 assert(nested(42).value == 42);assert(both(20,22) == 20);
 let chain:Chain<i64> = Chain::Next(42,[Chain::End()]);
 assert(unwrap(decode_json<Chain<i64>>(encode_json(chain))) == chain);
}''')
        self.cli('test');self.cli('test','--target','web')

    def test_bound_names_are_contextual_and_order_is_semantically_stable(self):
        text='''module names;
struct add {integer:i64; ordered:str;}
fn ordered(integer:i64) -> i64 {return integer;}
fn choose<T:add+ordered>(x:T,y:T) -> T {if x<y {return x+y;}return x;}
fn main() -> unit {let value:add = add(42,"name");assert(ordered(value.integer) == 42);assert(choose(20,22) == 42);}
'''
        self.source(text);before=self.cli('check')['revision']
        self.source(text.replace('T:add+ordered','T:ordered+add'))
        self.assertEqual(self.cli('check')['revision'],before)
        self.assertEqual(self.cli('run')['exit_code'],0)

    def test_heap_arguments_keep_order_aliases_and_cleanup(self):
        self.source('''module heap_bounds;
fn combine<T:add>(x:T,y:T) -> T {return x+y;}
fn left() -> list<str> !{io} {print("left");return ["A\\u0000🌍"];}
fn right() -> list<str> !{io} {print("right");return ["B"];}
fn main() -> unit !{io} {let a:list<str> = combine(left(),right());print(encode_json(a));}
test fn aliases() -> unit {
 let alias:list<str> = ["old"];var current:list<str> = alias;
 var i:i64 = 0;while i<100 {current = combine(current,["new"]);i=i+1;}
 assert(alias == ["old"]);assert(len(current) == 101);
 assert(combine("A\\u0000", "🌍") == "A\\u0000🌍");
}''')
        expected=self.cli('eval')['stdout'];self.assertTrue(expected.startswith('left\nright\n'))
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],expected)
            self.cli('test','--profile',profile)
        self.cli('test','--target','web')

    def test_integer_constraint_retains_checked_arithmetic_traps(self):
        for expression,code in [('x+1','E_OVERFLOW'),('-x','E_OVERFLOW'),('x/0','E_DIV_ZERO')]:
            value='-9223372036854775808' if expression=='-x' else '9223372036854775807'
            self.source('module traps; fn operation<T:integer>(x:T) -> T {return '+expression+';} fn main() -> i64 {return operation('+value+');}')
            self.assertEqual(self.cli('eval',ok=False)['code'],code)
            for profile in ('debug','release'):
                result=self.cli('run','--profile',profile,ok=False);self.assertEqual(result['exit_code'],70);self.assertIn(code,result['stderr'])
            test=self.file.read_text().replace('fn main() -> i64','test fn failure() -> unit').replace('return operation('+value+');','operation('+value+');')+' fn main() -> unit {}'
            self.source(test);result=self.cli('test','--target','web',ok=False);self.assertIn(code,json.dumps(result))

    def test_imported_constraints_atomic_patch_and_source_deleted_archives(self):
        library=self.root/'math.nex';library.write_text('module bound_math; pub fn sum<T:add>(x:T,y:T) -> T {return x+y;}')
        self.source('''module app; import "./math.nex" as math;
fn main() -> unit !{io} {print(math::sum("NEX ","🧠"));}
test fn examples() -> unit {assert(math::sum(20,22) == 42);}
''')
        before=self.cli('check')['revision'];context=self.cli('context','--symbol','bound_math::sum')
        self.assertEqual(context['type_bounds'],{'bound_math::sum::T':['add']})
        patch=self.root/'patch.json';patch.write_text(json.dumps({'expected_revision':before,'replacements':[{'name':'bound_math::sum','source':'pub fn sum<T:integer>(x:T,y:T) -> T {return x+y;}'}]}))
        self.assertEqual(self.cli('apply','--patch',patch,ok=False)['code'],'E_GENERIC_BOUND')
        self.assertEqual(self.cli('history')['head'],before)
        patch.write_text(json.dumps({'expected_revision':before,'replacements':[{'name':'bound_math::sum','source':'pub fn sum<T:add>(x:T,y:T) -> T {return y+x;}'}]}))
        fixed=self.cli('apply','--patch',patch)['revision'];self.assertNotEqual(fixed,before)
        self.file.unlink();library.unlink()
        self.assertEqual(self.cli('run','--revision',before)['stdout'],'NEX 🧠\n')
        self.assertEqual(self.cli('run','--revision',fixed)['stdout'],'🧠NEX \n')
        exported=self.root/'export';self.cli('export','--revision',fixed,'--directory',exported)
        self.assertIn('T:add',(exported/'math.nex').read_text());self.assertEqual(self.cli('check',cwd=exported)['revision'],fixed)

    def test_actual_020_source_migration_preserves_history_and_local_ids(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.7.json').read_text());self.source(fixture['source'])
        old_binary=harness.REPO/'build/sdk-0.20.0/bin/nex'
        if sys.platform=='darwin' and old_binary.is_file():
            def old_cli(*args):return json.loads(subprocess.check_output([str(old_binary),*args,'--json'],cwd=self.root))
            old=old_cli('check')['revision'];graph=old_cli('graph');nodes=old_cli('operations','--symbol','main')['nodes']
        else:
            saved=self.historical_store('0.7');old=saved['revision'];graph=saved['graph'];nodes=saved['operations']
        self.file.unlink();self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION')
        current=self.cli('migrate');self.assertEqual(current['language'],'0.18');self.assertNotEqual(current['revision'],old)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.7','0.18'})
        self.assertEqual({n['name']:n['id'] for n in graph['nodes']},{n['name']:n['id'] for n in self.cli('graph')['nodes']})
        self.assertEqual({n['path']:n['id'] for n in nodes},{n['path']:n['id'] for n in self.cli('operations','--symbol','main')['nodes']})
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')

    def test_generated_api_models_preserve_declared_bounds(self):
        (self.root/'model.nex').write_text('''module bound_model;
pub struct Pair<T:add> {left:T;right:T;}
pub enum Count<T:integer> {Zero;Value(value:T);}
pub struct Payload<T:add,U:integer> {pair:Pair<T>;count:Count<U>;}
''')
        self.source('''module bound_service; import "std/api.nex" as api;import "./model.nex" as model;
server fn echo(c:api::Context,input:model::Payload<str,i64>) -> result<model::Payload<str,i64>> {return ok(input);}
endpoint echo_value("POST","/api/value") = echo;
''')
        generated=self.cli('api','--directory',self.root/'generated')
        model=self.root/'generated/client/models/bound_model.nex';text=model.read_text()
        self.assertIn('Pair<T: add>',text);self.assertIn('Count<T: integer>',text)
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/models/bound_model.nex" as model;
fn main() -> unit {}
test fn models() -> unit {let data:model::Payload<str,i64> = model::Payload(model::Pair("A","🧠"),model::Count::Value(42));assert(unwrap(decode_json<model::Payload<str,i64>>(encode_json(data))) == data);}
''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')
        self.cli('build',generated['server_entry'],'--target','server',timeout=180)
        consumer.write_text(consumer.read_text().replace('model::Payload<str,i64>','model::Payload<bool,i64>'))
        self.assertEqual(self.cli('check',consumer,ok=False)['code'],'E_GENERIC_BOUND')

    def test_constrained_pure_watches_and_concrete_scalar_proof(self):
        self.source('''module bound_watch;
fn increment<T:integer>(x:T) -> T {return x+1;}
fn combine<T:add>(x:T,y:T) -> T {return x+y;}
fn observe<T:integer>(value:T) -> unit !{io} {print(increment(value));}
fn main() -> unit !{io} {observe(41);}
''')
        session=self.cli('debug');manifest=json.loads(Path(session['manifest']).read_text());revision=session['revision']
        frame={'schema':'nex.debug-frame/1','language':'0.18','revision':revision,'build_key':manifest['build_key'],
               'function':'bound_watch::observe<i64>','stop':{'process_id':'1','thread_id':'2','frame_id':0,'stop_id':'1'},
               'bindings':[{'name':'value','type':'i64','value':'41'}],'truncated':False}
        path=self.root/'frame.json';path.write_text(json.dumps(frame))
        for expression,value in [('increment<T>(value)','42'),('combine("A","🌍")','A🌍')]:
            inspected=self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression)
            self.assertEqual(inspected['value'],value);self.assertEqual(inspected['revision'],revision)
        self.assertEqual(self.cli('inspect',path,'--manifest',session['manifest'],'--expression','combine(true,false)',ok=False)['code'],'E_GENERIC_BOUND')
        self.assertEqual(self.cli('graph')['revision'],revision)
        contract=self.root/'contract.json';self.cli('contract','--symbol','bound_watch::increment<i64>','-o',contract)
        proof=json.loads(contract.read_text());proof['functions'][0].update(requires=['x < 9223372036854775807'],ensures=['result == x + 1']);contract.write_text(json.dumps(proof))
        self.assertTrue(self.cli('verify','--contracts',contract)['ok'])
        self.file.unlink();self.assertEqual(self.cli('inspect',path,'--manifest',session['manifest'],'--expression','increment<T>(value)')['value'],'42')

    def test_task_repair_keeps_acceptance_and_replays_constrained_templates(self):
        self.source('''module bound_accept;
pub fn combine<T:add>(x:T,y:T) -> T {return x;}
fn main() -> unit !{io} {print(combine(20,22));}
test fn examples() -> unit {assert(combine(20,22) == 42);assert(combine("NEX ","🧠") == "NEX 🧠");}
''')
        task=self.cli('task',self.file,'--kind','init');test=next(c['id'] for c in task['checks'] if c['kind']=='test')
        task['requirements'].append({'id':'template','text':'Combine bounded types with identical checked operations','bindings':[{'program':'app','kind':'function','symbol':'bound_accept::combine'}],'targets':['native'],'checks':[test]})
        task['checks'].append({'id':'measure','kind':'profile','program':'app','target':'native','entry':'bound_accept::main','scenario':'one bounded integer combine','budget':{'max_calls':{'bound_accept::combine<i64>':'1'}}})
        task['requirements'].append({'id':'measurement','text':'Measure the concrete bounded instance','bindings':[{'program':'app','kind':'function','symbol':'bound_accept::combine<i64>'}],'targets':['native'],'checks':['measure']})
        path=self.root/'task.json';path.write_text(json.dumps(task))
        failed=self.cli('task',path,'--kind','run',ok=False,timeout=180);self.assertEqual(failed['status'],'not_satisfied')
        checked=self.cli('check');patch=self.root/'patch.json';patch.write_text(json.dumps({'expected_revision':checked['revision'],'replacements':[{'name':'bound_accept::combine','source':'pub fn combine<T:add>(x:T,y:T) -> T {return x+y;}'}]}))
        fixed=self.cli('apply','--patch',patch)['revision']
        passed=self.cli('task',path,'--kind','run','--revision',fixed,'--task-hash',failed['task_hash'],timeout=180)
        self.assertEqual(passed['task_hash'],failed['task_hash']);self.file.unlink()
        replay=self.cli('task',passed['output'],'--kind','replay',timeout=180);self.assertEqual(replay['status'],'passed')
        self.assertEqual(replay['task_hash'],failed['task_hash'])


if LIVE:
    class LiveConstraints(harness.ToolchainCase):
        def test_lldb_bounded_parameter_scope_and_uncompiled_string_helper(self):
            self.source('''module live_bounds;
fn combine<T:add>(x:T,y:T) -> T {return x+y;}
fn increment<T:integer>(x:T) -> T {return 1+x;}
fn observe<T:integer>(value:T) -> unit !{io} {print(increment(value));}
fn main() -> unit !{io} {observe(41);}
''')
            self.cli('check');symbol=self.cli('context','--symbol','observe<i64>')['native_symbol']
            session=self.cli('debug');report=self.root/'values.json';script=self.root/'capture.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByName(SYMBOL);process=target.LaunchSimple(None,None,None)
 try:
  assert process.GetState()==lldb.eStateStopped;stop=process.GetStopID()
  def command(text,ok=True):
   result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
   assert result.Succeeded()==ok,result.GetError();return json.loads(result.GetOutput() if ok else result.GetError().removeprefix('error: '))
  output={'integer':command('nex-eval increment<T>(value)'), 'string':command('nex-eval combine("A","🌍")'),'rejected':command('nex-eval combine(true,false)',False)}
  assert process.GetStopID()==stop
  with open(REPORT,'w') as out:json.dump(output,out)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SYMBOL',repr(symbol)).replace('REPORT',repr(str(report))))
            result=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),result.stdout+result.stderr);data=json.loads(report.read_text())
            self.assertEqual(data['integer']['value'],'42');self.assertEqual(data['string']['value'],'A🌍')
            self.assertEqual(data['integer']['revision'],session['revision']);self.assertEqual(data['rejected']['code'],'E_GENERIC_BOUND')


if __name__=='__main__':unittest.main()
