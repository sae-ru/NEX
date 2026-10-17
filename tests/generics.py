"""Parametric checking, specialization, graph source identity and backend agreement."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness


class Generics(harness.ToolchainCase):
    def example(self):
        for name in ['main.nex','model.nex']:shutil.copyfile(harness.REPO/'examples/generics'/name,self.root/name)

    def test_generic_recursive_models_and_functions_across_backends(self):
        self.example();expected='🧠\n42\n[2,40]\n'
        self.assertEqual(self.cli('eval')['stdout'],expected)
        for profile in ['debug','release']:
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],expected)
            self.cli('test','--profile',profile)
        self.cli('test','--target','web')

    def test_unused_templates_are_checked_parametrically(self):
        cases=[
            ('fn wrong<T>(x:T) -> T {return 1;}', 'E_TYPE'),
            ('fn wrong<T>(x:T) -> i64 {return x + 1;}', 'E_TYPE'),
            ('fn wrong<T>(x:T) -> i64 {return len(x);}', 'E_TYPE'),
            ('fn wrong<T,U>(x:T,y:U) -> T {return y;}', 'E_TYPE'),
            ('fn wrong<T>(x:T) -> unit {print(x);}', 'E_EFFECT'),
            ('server fn remote() -> unit {} client fn wrong<T>(x:T) -> unit {remote();}', 'E_REALM'),
            ('fn wrong<T,T>(x:T) -> T {return x;}', 'E_DUPLICATE'),
            ('struct result<T> {value:T;}', 'E_GENERIC_NAME'),
            ('enum result<T> {Some(value:T);}', 'E_GENERIC_NAME'),
            ('test fn wrong<T>() -> unit {}', 'E_TEST'),
            ('struct Box<T> {v:T;} fn wrong() -> unit {let b:Box = Box(1);}', 'E_GENERIC_ARITY'),
            ('struct Box<T> {v:T;} fn wrong() -> unit {Box<unit>(print(1));}', 'E_TYPE'),
            ('struct Box<T> {v:T;} fn wrong() -> unit {Box<i64,str>(1);}', 'E_GENERIC_ARITY'),
            ('fn id<T>(x:T) -> T {return x;} fn wrong() -> unit {id<i64>(true);}', 'E_TYPE'),
            ('fn id<T>(x:T) -> T {return x;} fn wrong() -> unit {id<i64,str>(1);}', 'E_GENERIC_ARITY'),
            ('fn id<T>(x:T) -> T {return x;} fn wrong() -> unit {id();}', 'E_ARITY'),
            ('struct Tag<T> {id:i64;} fn wrong() -> unit {Tag(1);}', 'E_GENERIC_INFER'),
            ('struct Row {id:i64;} fn wrong() -> unit {Row<i64>(1);}', 'E_GENERIC_ARITY'),
            ('fn id(x:i64) -> i64 {return x;} fn wrong() -> unit {id<i64>(1);}', 'E_GENERIC_ARITY'),
            ('fn wrong() -> unit {len<i64>([]);}', 'E_GENERIC_ARITY'),
            ('pub struct Box<T> {value:T;} struct Private {} pub fn wrong() -> Box<Private> {return Box(Private());}', 'E_VISIBILITY'),
        ]
        for body,code in cases:
            with self.subTest(body=body):
                self.source('module rejected; '+body+' fn main() -> unit {}')
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_inference_context_phantom_types_aliases_and_evaluation_order(self):
        self.source('''module inference;
pub struct Pair<T,U> {left:T; right:U;}
pub struct Tag<T> {id:i64;}
struct Private {value:str;}
enum Maybe<T> {None; Some(value:T);}
pub fn id<T>(x:T) -> T {return x;}
fn append<T>(xs:list<T>,v:T) -> list<T> {return push(xs,v);}
fn empty<T>() -> Maybe<T> {return Maybe<T>::None();}
fn left() -> str !{io} {print("left"); return "🧠";}
fn right() -> i64 !{io} {print("right"); return 42;}
fn main() -> unit !{io} {let pair:Pair<str,i64> = Pair(left(),right()); print(pair.left); print(pair.right);}
test fn context_and_aliases() -> unit {
 let xs:list<i64> = append([],42);assert(xs == [42]);
 let none:Maybe<str> = empty();assert(none == Maybe<str>::None());
 let tag:Tag<str> = Tag(42);assert(tag == Tag<str>(42));
 let secret:Private = id(Private("local"));assert(secret.value == "local");
 let before:Pair<str,i64> = Pair("old",1);var current:Pair<str,i64> = before;
 current = Pair("new",2);assert(before.left == "old");assert(current.right == 2);
}''')
        self.assertEqual(self.cli('eval')['stdout'],'left\nright\n🧠\n42\n')
        self.assertEqual(self.cli('run')['stdout'],'left\nright\n🧠\n42\n')
        self.cli('test');self.cli('test','--target','web')
        source=self.file.read_text();self.source(source.replace('assert(tag == Tag<str>(42))','assert(tag == Tag<i64>(42))'))
        self.assertEqual(self.cli('check',ok=False)['code'],'E_TYPE')

    def test_operator_result_types_and_intrinsic_contexts_do_not_conflict(self):
        self.source('''module contexts;
enum Maybe<T> {None; Some(value:T);}
fn id<T>(x:T) -> T {return x;}
fn same<T>(x:T,y:T) -> bool {return id(x) == id(y);}
fn parse<T:wire>(text:str) -> result<T> {return decode_json<T>(text);}
fn take<T:wire>(text:str) -> T {return unwrap(parse(text));}
fn main() -> unit {}
test fn contexts() -> unit {
 let same:bool = id(42) == 42;assert(same);
 assert(same("equal","equal"));assert(!same("left","right"));
 let inferred:bool = take(INTEGER_JSON) == 42;assert(inferred);
 let cases:bool = Maybe::None() == Maybe::Some(42);assert(!cases);
 let lists:bool = [] == [1];assert(!lists);
 let number:i64 = unwrap(parse(INTEGER_JSON));assert(number == 42);
 let negative:i64 = -take(INTEGER_JSON);assert(negative == -42);
 if take("true") {assert(true);} else {assert(false);}
 var n:i64 = 0;while take("false") {n = n + 1;}assert(n == 0);
 assert(take("true"));assert(!take("false") && take("true"));
 assert(push([1],take(INTEGER_JSON)) == [1,42]);
 let xs:list<i64> = set([1,2],take(INDEX_JSON),take(INTEGER_JSON));assert(xs == [1,42]);
 assert(xs[take(INDEX_JSON)] == 42);
 assert(slice(take(TEXT_JSON),take(ZERO_JSON),take(INDEX_JSON)) == "🧠");
}'''.replace('INTEGER_JSON',json.dumps(json.dumps('42'))).replace('INDEX_JSON',json.dumps(json.dumps('1'))).replace('ZERO_JSON',json.dumps(json.dumps('0'))).replace('TEXT_JSON',json.dumps(json.dumps('🧠a'))))
        self.cli('test');self.cli('test','--target','web')

    def test_template_patch_updates_derived_instances_and_archives(self):
        self.source('''module repair;
fn first<T>(xs:list<T>) -> T {return xs[0];}
fn main() -> unit !{io} {print(first([41,42])); print(first(["before","after"]));}
''')
        old=self.cli('check')['revision'];context=self.cli('context','--symbol','repair::first<i64>')
        self.assertEqual(context['template'],'repair::first');self.assertFalse(context['editable'])
        self.assertEqual(context['type_arguments'],['i64'])
        patch=self.root/'patch.json';patch.write_text(json.dumps({'expected_revision':old,'replacements':[{'name':'repair::first<i64>','source':'fn first<T>(xs:list<T>) -> T {return xs[1];}'}]}))
        self.assertEqual(self.cli('apply','--patch',patch,ok=False)['code'],'E_PATCH_SPECIALIZATION')
        patch.write_text(json.dumps({'expected_revision':old,'replacements':[{'name':'repair::first','source':'fn first<T>(xs:list<T>) -> T {return xs[1];}'}]}))
        fixed=self.cli('apply','--patch',patch)['revision'];self.assertNotEqual(old,fixed)
        self.file.unlink();self.assertEqual(self.cli('run','--revision',fixed)['stdout'],'42\nafter\n')
        self.assertEqual(self.cli('run','--revision',old)['stdout'],'41\nbefore\n')
        exported=self.root/'project';self.cli('export','--revision',fixed,'--directory',exported)
        self.assertEqual(self.cli('check',cwd=exported)['revision'],fixed)

    def test_actual_016_source_migration_preserves_history(self):
        old_binary=harness.REPO/'build/sdk-0.16.0/bin/nex'
        self.source('module legacy; enum E {A(value:i64); B;} fn value(e:E) -> i64 {match e {E::A(n) => {return n;} E::B() => {return 0;}}} fn main() -> unit {assert(value(E::A(42)) == 42);}')
        if sys.platform=='darwin' and old_binary.exists():
            def old_cli(*args):return json.loads(subprocess.check_output([str(old_binary),*args,'--json'],cwd=self.root))
            old=old_cli('check')['revision'];old_graph=old_cli('graph');old_nodes=old_cli('operations','--symbol','value')['nodes']
        else:
            fixture=self.historical_store('0.6');old=fixture['revision'];old_graph=fixture['graph'];old_nodes=fixture['operations']
        self.file.unlink();self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION')
        current=self.cli('migrate');self.assertEqual(current['language'],'0.9');self.assertNotEqual(current['revision'],old)
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.6','0.9'})
        graph=self.cli('graph');nodes=self.cli('operations','--symbol','value')['nodes']
        self.assertEqual({n['name']:n['id'] for n in graph['nodes']},{n['name']:n['id'] for n in old_graph['nodes']})
        self.assertEqual({n['path']:n['id'] for n in nodes},{n['path']:n['id'] for n in old_nodes})
        self.assertEqual(self.cli('run','--revision','HEAD')['exit_code'],0)

    def test_expansion_limits_are_diagnostics(self):
        for body in ['fn grow<T>(x:T) -> unit {grow([x]);}',
                     'struct Box<T> {v:T;} struct Grow<T> {next:Grow<Box<T>>;}']:
            self.source('module limit; '+body+' fn main() -> unit {}')
            self.assertEqual(self.cli('check',ok=False,timeout=20)['code'],'E_GENERIC_LIMIT')
        self.source('module limit; struct S {value:'+'list<'*200+'i64'+'>'*200+';} fn main() -> unit {}')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_GENERIC_LIMIT')

    def test_abstract_instances_cannot_be_executable_entries(self):
        self.source('module entries; fn constant<T>() -> i64 {return 42;} fn other<T>() -> i64 {return constant<T>();} fn main() -> unit {}')
        self.cli('check');graph=self.cli('graph')
        abstract=next(n['name'] for n in graph['nodes'] if n['definition']['template']=='entries::constant')
        for command in [('eval',),('build',),('emit','--kind','typescript','--directory',self.root/'ts')]:
            with self.subTest(command=command):
                self.assertEqual(self.cli(*command,'--entry',abstract,ok=False)['code'],'E_GENERIC_ENTRY')

    def test_local_instance_names_can_contain_qualified_type_arguments(self):
        (self.root/'model.nex').write_text('module domain::model; pub struct Value {number:i64;}')
        self.source('''module app; import "./model.nex" as model;
struct Box<T> {value:T;}
fn identity<T>(x:T) -> T {return x;}
fn main() -> unit {let value:Box<model::Value> = identity(Box(model::Value(42)));assert(value.value.number == 42);}
''')
        self.cli('check')
        context=self.cli('context','--symbol','identity<app::Box<domain::model::Value>>')
        self.assertEqual(context['symbol'],'app::identity<app::Box<domain::model::Value>>')
        self.assertEqual(context['template'],'app::identity')

    def test_generic_api_models_are_extracted_once_with_phantom_arguments(self):
        (self.root/'domain.nex').write_text('''module domain;
pub struct Value {number:i64;}
pub enum Maybe<T> {None; Some(value:T);}
pub struct Tag<T> {count:i64;}
pub struct Response<T> {items:list<Maybe<T>>; marker:Tag<T>;}
fn hidden() -> str {return "GENERIC_SERVER_ONLY_SENTINEL";}
''')
        self.source('''module service; import "std/api.nex" as api; import "./domain.nex" as model;
server fn echo(c:api::Context,input:model::Response<model::Value>) -> result<model::Response<model::Value>> {return ok(input);}
endpoint echo_value("POST","/api/value") = echo;
''')
        generated=self.cli('api',self.file,'--directory',self.root/'generated')
        model=self.root/'generated/client/models/domain.nex';text=model.read_text()
        self.assertEqual(text.count('pub enum Maybe<T>'),1);self.assertEqual(text.count('pub struct Response<T>'),1)
        self.assertIn('pub struct Value',text);self.assertNotIn('GENERIC_SERVER_ONLY_SENTINEL',text)
        consumer=self.root/'consumer.nex';consumer.write_text('''module consumer;
import "./generated/client/api.nex" as sdk; import "./generated/client/models/domain.nex" as model;
import "std/net.nex" as net; import "std/web.nex" as web;
fn main() -> unit {}
test fn models() -> unit {
 let value:model::Value = model::Value(42);
 let data:model::Response<model::Value> = model::Response([model::Maybe::Some(value)],model::Tag(1));
 let request:net::Command = sdk::request_echo_value("1","token",data,"received",1000);
 let body:net::TypedPayload = unwrap(decode_json<net::TypedPayload>(request.body));
 assert(unwrap(decode_json<model::Response<model::Value>>(body.body)) == data);
 let response:net::Response = net::Response("1",200,ok(encode_json(ok(data))));
 assert(unwrap(sdk::response_echo_value(web::Event("received",encode_json(response),"/"))) == data);
}''')
        self.cli('test',consumer);self.cli('test',consumer,'--target','web')
        self.cli('build',generated['server_entry'],'--target','server','--profile','release',timeout=180)

    def test_generic_watch_instantiations_preserve_revision_and_resolve_frame_parameters(self):
        self.source('''module watches;
struct Box<T> {value:T;}
fn identity<T>(value:T) -> T {return value;}
fn observe<T>(box:Box<T>) -> unit !{io} {print(box.value);}
fn main() -> unit !{io} {observe(Box(41));}
''')
        session=self.cli('debug');manifest=json.loads(Path(session['manifest']).read_text());revision=session['revision']
        frame={'schema':'nex.debug-frame/1','language':'0.9','revision':revision,'build_key':manifest['build_key'],
               'function':'watches::observe<i64>','stop':{'process_id':'1','thread_id':'2','frame_id':0,'stop_id':'1'},
               'bindings':[{'name':'box','type':'watches::Box<i64>','value':{'value':'41'}}],'truncated':False}
        path=self.root/'frame.json';path.write_text(json.dumps(frame))
        for expression,expected in [('identity<T>(box.value)','41'),('identity<Box<i64>>(box)',{'value':'41'}),('identity<str>("uncompiled")','uncompiled')]:
            result=self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression)
            self.assertEqual(result['value'],expected);self.assertEqual(result['revision'],revision)
        partial=dict(frame,schema='nex.debug-frame/2',bindings=[{'name':'box','type':'watches::Box<i64>','unavailable':'not captured'}],captures=[])
        for expected in [{'record':'watches::Box<i64>'},'41']:
            path.write_text(json.dumps(partial))
            demand=self.cli('inspect',path,'--manifest',session['manifest'],'--expression','identity(box).value','--kind','demand')
            request=demand['request'];partial['captures'].append({**{k:request[k] for k in ['binding','path','kind']},'value':expected})
        path.write_text(json.dumps(partial));result=self.cli('inspect',path,'--manifest',session['manifest'],'--expression','identity(box).value')
        self.assertEqual(result['value'],'41');self.assertEqual(result['revision'],revision)

    def test_scalar_specialization_can_be_verified_without_proving_template(self):
        self.source('module scalar; fn id<T>(x:T) -> T {return x;} fn main() -> i64 {return id(42);}')
        contract=self.root/'contract.json';self.cli('contract','--symbol','scalar::id<i64>','-o',contract)
        data=json.loads(contract.read_text());data['functions'][0]['ensures']=['result == x'];contract.write_text(json.dumps(data))
        result=self.cli('verify','--contracts',contract);self.assertTrue(result['ok'])
        self.cli('contract','--symbol','id','-o',contract)
        result=self.cli('verify','--contracts',contract,ok=False)
        self.assertEqual(result['functions'][0]['status'],'unsupported')

    def test_generic_body_edits_recompile_provider_and_reuse_callers(self):
        model=self.root/'model.nex';model.write_text('module model; pub fn first<T>(values:list<T>) -> T {return values[0];}')
        (self.root/'left.nex').write_text('module left; import "./model.nex" as m; pub fn value() -> i64 {return m::first([41,42]);}')
        (self.root/'right.nex').write_text('module right; pub fn value() -> i64 {return 100;}')
        self.source('module app; import "./left.nex" as l; import "./right.nex" as r; fn main() -> unit !{io} {print(l::value());print(r::value());}')
        first=self.cli('build');self.assertEqual((first['compiled_modules'],first['reused_modules']),(4,0))
        self.assertEqual(subprocess.check_output([first['executable']],text=True),'41\n100\n')
        warm=self.cli('build');self.assertEqual((warm['compiled_modules'],warm['reused_modules']),(0,4))
        model.write_text(model.read_text().replace('values[0]','values[1]'))
        changed=self.cli('build');self.assertEqual((changed['compiled_modules'],changed['reused_modules']),(1,3))
        self.assertEqual(subprocess.check_output([changed['executable']],text=True),'42\n100\n')
        self.assertEqual(self.cli('eval')['stdout'],'42\n100\n')
        clean=self.root/'clean';clean.mkdir()
        for name in ['main.nex','model.nex','left.nex','right.nex']:shutil.copyfile(self.root/name,clean/name)
        fresh=self.cli('build',cwd=clean);self.assertEqual(fresh['compiled_modules'],4)
        self.assertEqual(subprocess.check_output([fresh['executable']],text=True),'42\n100\n')

    def test_task_requirements_link_templates_and_profile_concrete_instances(self):
        self.source('''module acceptance_generic;
pub struct Box<T> {value:T;}
pub fn id<T>(value:T) -> T {return value;}
fn main() -> unit !{io} {print(id(42));}
test fn cases() -> unit {assert(id(42) == 42);assert(Box("value").value == "value");}
''')
        task=self.cli('task',self.file,'--kind','init');test=next(c['id'] for c in task['checks'] if c['kind']=='test')
        task.update(id='generic-acceptance',title='Generic source acceptance',goal='Check reusable identity and Box through concrete tests and a measured scalar instance.')
        task['requirements'].append({'id':'templates','text':'Exercise the reviewed generic declarations through concrete tests','bindings':[{'program':'app','kind':'function','symbol':'acceptance_generic::id'},{'program':'app','kind':'structure','symbol':'acceptance_generic::Box'}],'targets':['native'],'checks':[test]})
        task['checks'].append({'id':'profile-instance','kind':'profile','program':'app','target':'native','entry':'acceptance_generic::main','scenario':'one identity call','budget':{'max_calls':{'acceptance_generic::id<i64>':'1'}}})
        task['requirements'].append({'id':'measured','text':'The concrete integer instance is called once in this workload','bindings':[{'program':'app','kind':'function','symbol':'acceptance_generic::id<i64>'}],'targets':['native'],'checks':['profile-instance']})
        path=self.root/'task.json';path.write_text(json.dumps(task));checked=self.cli('task',path,'--kind','check');self.assertTrue(checked['ok'])
        result=self.cli('task',path,'--kind','run','--task-hash',checked['task_hash'],timeout=180);self.assertTrue(result['ok'])
        self.assertTrue(self.cli('task',result['output'],'--kind','replay',timeout=180)['ok'])


if LIVE:
    class LiveGenerics(harness.ToolchainCase):
        def test_real_lldb_and_dap_generic_scopes_and_uncompiled_helpers(self):
            self.source('''module live_generic;
struct Box<T> {value:T;}
fn identity<U>(value:U) -> U {return value;}
fn observe<T>(box:Box<T>) -> unit !{io} {
 let value:T = box.value;
 print(value); // break: generic
}
fn main() -> unit !{io} {observe(Box(41));}
''')
            session=self.cli('debug','--kind','nex-dap');manifest=json.loads(Path(session['manifest']).read_text())
            source=manifest['sources'][0]['projection'];line=next(i+1 for i,s in enumerate(self.file.read_text().splitlines()) if '// break: generic' in s)
            report=self.root/'generic-watch.json';script=self.root/'capture.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE);process=target.LaunchSimple(None,None,None)
 try:
  assert process.GetState()==lldb.eStateStopped;frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID();handle=frame.FindVariable('box').GetValueAsUnsigned()
  def command(text):
   result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
   assert result.Succeeded(),result.GetError();return json.loads(result.GetOutput())
  output={'value':command('nex-eval identity<T>(value)'), 'snapshot':command('nex-frame identity(box).value'), 'new':command('nex-eval identity<str>("uncompiled")')}
  assert process.GetStopID()==stop and frame.FindVariable('box').GetValueAsUnsigned()==handle
  with open(REPORT,'w') as out:json.dump(output,out)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(source)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            result=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.exists(),result.stdout+result.stderr);captured=json.loads(report.read_text())
            self.assertEqual(captured['value']['value'],'41');self.assertEqual(captured['new']['value'],'uncompiled')
            self.assertEqual(captured['value']['revision'],session['revision']);self.assertEqual(captured['new']['revision'],session['revision'])
            self.assertEqual([c['path'] for c in captured['snapshot']['captures']],[[],['value']])
            from debugging import DAP
            client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[{'line':line}]})
                client.request('configurationDone');client.response(pending);stop=client.event('stopped')
                frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
                def evaluate(expression):return client.request('evaluate',{'expression':expression,'frameId':frame,'context':'watch'})
                self.assertEqual(evaluate('identity<T>(value)')['nex']['value'],'41')
                value=evaluate('identity<Box<i64>>(box)');self.assertEqual(value['nex']['revision'],session['revision'])
                fields=client.request('variables',{'variablesReference':value['variablesReference'],'start':0,'count':1})['variables']
                self.assertEqual([(v['name'],v['value']) for v in fields],[('value','41')])
                client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()
            self.file.unlink();path=self.root/'frame.json';path.write_text(json.dumps(captured['snapshot']))
            self.assertEqual(self.cli('inspect',path,'--manifest',session['manifest'],'--expression','identity(box).value')['value'],'41')


if __name__=='__main__':unittest.main()
