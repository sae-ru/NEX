"""Nested patterns, coverage, guard effects, ownership and model/debug workflows."""
import itertools
import json
from pathlib import Path
import random
import shutil
import subprocess
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness


class Matching(harness.ToolchainCase):
    def backends(self):
        expected=self.cli('eval')['stdout']
        for profile in ('debug','release'):
            self.assertEqual(self.cli('run','--profile',profile)['stdout'],expected)
            self.cli('test','--profile',profile)
        self.cli('test','--target','web')

    def test_example_all_backends(self):
        self.source((harness.REPO/'examples/matching.nex').read_text())
        self.assertEqual(self.cli('eval')['stdout'],'42\none:42\n7\n');self.backends()
        self.assertIn('typed_nested_patterns',self.cli('describe')['match_features'])

    def test_scrutinee_guard_order_short_circuit_and_shadowing(self):
        self.source('''module ordered;
enum E {Value(value:i64); Empty;}
fn subject() -> E !{io} {print("subject");return E::Value(42);}
fn guard(label:str,answer:bool) -> bool !{io} {print(label);return answer;}
fn main() -> unit !{io} {
 let n:i64 = -1;
 let result:i64 = match subject() {
  E::Empty() if guard("not called",true) => 0,
  E::Value(n) if guard("first",false) => n,
  E::Value(n) if guard("second",true) && n == 42 => n+1,
  _ => 0,
 };
 print(result);print(n);
 match subject() {
  E::Value(n) if guard("third",false) => {print(0);},
  E::Value(n) => {print(n);}, E::Empty() => {print(0);}
 }
}
test fn guard_short_circuit() -> unit {assert((match true {true if false => 0,_ => 42}) == 42);}
''')
        self.assertEqual(self.cli('eval')['stdout'],'subject\nfirst\nsecond\n43\n-1\nsubject\nthird\n42\n');self.backends()

    def test_literal_record_exact_list_result_and_unit_patterns(self):
        self.source('''module shapes;
struct Pair {a:bool;b:bool;}
fn classify(p:Pair) -> i64 {return match p {Pair(true,_) => 1,Pair(false,true) => 2,Pair(false,false) => 3};}
fn scalar(n:i64) -> str {return match n {-9223372036854775808 => "min",0 => "zero",x if x>0 => "positive",_ => "negative"};}
fn text(s:str) -> bool {return match s {"A\\u0000🌍" => true,_ => false};}
fn classify_list(xs:list<i64>) -> i64 {return match xs {[]=>0,[x]=>x,[1,n]=>n,_=>-1};}
fn effect(value:bool) -> unit !{io} {return match value {true=>print("true"),false=>print("false")};}
fn main() -> unit !{io} {effect(true);match false {true=>print("bad"),false=>print("ok")};}
test fn cases() -> unit {
 assert(classify(Pair(false,false)) == 3);assert(classify(Pair(true,true)) == 1);
 assert(scalar(-9223372036854775808) == "min");assert(scalar(42) == "positive");
 assert(text("A\\u0000🌍"));assert(!text("A"));
 assert(classify_list([])==0);assert(classify_list([42])==42);assert(classify_list([1,42])==42);assert(classify_list([1,2,3]) == -1);
 assert((match err<i64>("E","message") {ok(_) => "ok",err(code,message)=>code+":"+message}) == "E:message");
 assert((match true {true=>[42],false=>[]})[0]==42);
}''')
        self.backends()

    def test_finite_coverage_matches_independent_truth_table(self):
        values=list(itertools.product((False,True),repeat=2));choices=list(itertools.product((None,False,True),repeat=2));rng=random.Random(92022)
        def pattern(pair):return 'Pair('+','.join('_' if p is None else str(p).lower() for p in pair)+')'
        accepted=[]
        for index in range(35):
            rows=[rng.choice(choices) for _ in range(rng.randint(1,6))];covered=set();duplicate=False
            for pair in rows:
                matches={i for i,value in enumerate(values) if all(p is None or p==v for p,v in zip(pair,value))}
                if not matches-covered:duplicate=True
                covered|=matches
            source='module coverage; struct Pair {a:bool;b:bool;} fn choose(p:Pair) -> i64 {return match p {'+','.join(pattern(pair)+'=>'+str(i) for i,pair in enumerate(rows))+'};} fn main() -> unit {}'
            self.source(source)
            if duplicate:self.assertEqual(self.cli('check',ok=False)['code'],'E_MATCH_DUPLICATE')
            elif len(covered)!=4:self.assertEqual(self.cli('check',ok=False)['code'],'E_MATCH_EXHAUSTIVE')
            else:
                self.cli('check');accepted.append((rows,index))
        body='module oracle; struct Pair {a:bool;b:bool;} fn main() -> unit {} '
        for rows,index in accepted:
            body+='fn choose'+str(index)+'(p:Pair) -> i64 {return match p {'+','.join(pattern(pair)+'=>'+str(i) for i,pair in enumerate(rows))+'};}\n'
        body+='test fn truth_table() -> unit {'
        for rows,index in accepted:
            for value in values:
                answer=next(i for i,pair in enumerate(rows) if all(p is None or p==v for p,v in zip(pair,value)))
                body+='assert(choose'+str(index)+'(Pair('+','.join(str(v).lower() for v in value)+')) == '+str(answer)+');'
        self.assertTrue(accepted);self.source(body+'}');self.cli('test');self.cli('test','--target','web')

    def test_rejected_coverage_types_scopes_effects_and_realms(self):
        cases=[
            ('fn main() -> i64 {return match true {true=>1};}','E_MATCH_EXHAUSTIVE'),
            ('fn main() -> i64 {return match true {true if true=>1,false=>0};}','E_MATCH_EXHAUSTIVE'),
            ('fn main() -> i64 {return match 1 {_=>0,1=>1};}','E_MATCH_DUPLICATE'),
            ('fn main() -> i64 {return match true {true=>1,false=>false};}','E_TYPE'),
            ('fn main() -> i64 {return match 1 {true=>1,_=>0};}','E_MATCH_TYPE'),
            ('fn main() -> i64 {return match ok(1) {ok(x,x)=>x,err(_,_)=>0};}','E_ARITY'),
            ('struct Pair {a:i64;b:i64;} fn main() -> i64 {return match Pair(1,2) {Pair(x,x)=>x};}','E_DUPLICATE'),
            ('fn main() -> i64 {return match 1 {x if 1=>x,_=>0};}','E_TYPE'),
            ('fn main() -> unit {match 1 {x=>{x=2;}}}','E_MUTABILITY'),
            ('fn main() -> unit {let n:i64=match 1 {x=>x};print(x);}','E_NAME'),
            ('fn noisy() -> bool !{io} {print(1);return true;} fn main() -> i64 {return match 1 {x if noisy()=>x,_=>0};}','E_EFFECT'),
            ('server fn remote() -> bool {return true;} client fn main() -> i64 {return match 1 {x if remote()=>x,_=>0};}','E_REALM'),
            ('fn main() -> i64 {return match 1 {_=>{return 1;}};}','E_MATCH_TYPE'),
            ('fn main() -> i64 {return match [1] {[x]=>x};}','E_MATCH_EXHAUSTIVE'),
        ]
        for body,code in cases:
            with self.subTest(body=body):self.source('module bad; '+body);self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_heap_cleanup_guard_failure_loops_and_returned_aliases(self):
        self.source('''module ownership;
enum E {Text(text:str,tags:list<str>); Empty;}
fn select(e:E) -> list<str> {
 match e {
  E::Text("skip",_) => {return [];},
  E::Text(text,[first,second]) if text == "bad" => {return [text];},
  E::Text(text,tags) => {let saved:list<str> = match tags {[]=>[text],_=>tags};return saved;},
  E::Empty() => {return [];}
 }
}
fn main() -> unit {}
test fn cleanup() -> unit {
 let original:list<str> = ["A\\u0000🌍","B"];var current:list<str> = original;var n:i64=0;
 while n<200 {let next:list<str> = select(E::Text("keep",current));current=match ok(next) {ok([a,b]) if false=>[a],ok(values)=>values,err(_,_)=>[]};n=n+1;}
 assert(original == ["A\\u0000🌍","B"]);assert(current==original);assert(select(E::Empty())==[]);
 assert(select(E::Text("bad",original))==["bad"]);
}''')
        self.backends()

    def test_contextual_match_name_and_nested_expression_precedence(self):
        self.source('''module contextual;
fn match(value:bool) -> bool {return value;}
fn main() -> unit {}
test fn names() -> unit {
 let match:bool = match(true);if match(false) {assert(false);}if match {assert(true);}
 assert((match match {true=>40,false=>0}) + 2 == 42);
 match match(true) {true=>{assert(true);},false=>{assert(false);}}
 let nested:list<i64> = [40];let matched:i64=match (match true {true=>nested,false=>[]})[0] {n=>n+2};assert(matched==42);
 assert((match (match true {true=>false,false=>true}) {true=>0,false=>42}) == 42);
}''')
        self.backends()
        (self.root/'model.nex').write_text('module namespace_match; pub enum E {A(value:i64);B;}')
        self.source('module namespaced; import "./model.nex" as match; fn main() -> unit {match match::E::A(42) {match::E::A(n)=>{assert(n==42);},match::E::B()=>{assert(false);}}}')
        self.assertEqual(self.cli('run')['exit_code'],0)
        self.source('module indexed; fn main() -> unit {let match:list<i64>=[41];match match[0]+1 {42=>{assert(true);},_=>{assert(false);}}}')
        self.assertEqual(self.cli('run')['exit_code'],0)

    def test_generic_nested_patterns_and_expected_arm_inference(self):
        self.source('''module generic_match;
enum Maybe<T>{None;Some(value:T);}
struct Box<T>{value:T;}
fn take<T:integer>(value:result<Maybe<T>>) -> T {return match value {ok(Maybe::Some(n))=>n,ok(Maybe::None())=>0,err(_,_)=>-1};}
fn unbox<T>(value:Box<T>) -> T {return match value {Box(x)=>x};}
fn main() -> unit {}
test fn cases() -> unit {assert(take(ok(Maybe::Some(42)))==42);assert(take<i64>(ok(Maybe::None()))==0);assert(unbox(Box("NEX"))=="NEX");let xs:list<i64> = match false {true=>[],false=>[42]};assert(xs==[42]);}
''')
        self.backends()

    def test_optimistic_patch_archive_and_operation_binding_edges(self):
        self.source('module graph_match; fn choose(value:result<i64>) -> i64 {return match value {ok(n) if n>0=>n,ok(_)=>0,err(_,_)=>-1};} fn main() -> unit !{io} {print(choose(ok(42)));}')
        before=self.cli('check')['revision'];operations=self.cli('operations','--symbol','choose')['nodes']
        self.assertTrue(any(n['kind']=='expression.match' for n in operations))
        bindings={n['id'] for n in operations if n['kind']=='pattern.binding'}
        self.assertTrue(any(any(r['role']=='binding' and r['id'] in bindings for r in n['references']) for n in operations if n['kind']=='expression.name'))
        patch=self.root/'patch.json';patch.write_text(json.dumps({'expected_revision':before,'replacements':[{'name':'graph_match::choose','source':'fn choose(value:result<i64>) -> i64 {return match value {ok(n) if n>0=>n+1,ok(_)=>0,err(_,_)=>-1};}'}]}))
        after=self.cli('apply','--patch',patch)['revision'];self.file.unlink()
        self.assertEqual(self.cli('run','--revision',before)['stdout'],'42\n');self.assertEqual(self.cli('run','--revision',after)['stdout'],'43\n')
        project=self.root/'export';self.cli('export','--revision',after,'--directory',project);self.assertEqual(self.cli('check',cwd=project)['revision'],after)

    def test_actual_021_migration_preserves_legacy_match_operation_ids(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.8.json').read_text());self.source(fixture['source']);old_binary=harness.REPO/'build/sdk-0.21.0/bin/nex'
        if sys.platform=='darwin' and old_binary.is_file():
            def old_cli(*args):return json.loads(subprocess.check_output([str(old_binary),*args,'--json'],cwd=self.root))
            old=old_cli('check')['revision'];graph=old_cli('graph');nodes=old_cli('operations','--symbol','value')['nodes']
        else:saved=self.historical_store('0.8');old=saved['revision'];graph=saved['graph'];nodes=saved['operations']
        self.file.unlink();self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION');current=self.cli('migrate');self.assertEqual(current['language'],'0.10');self.assertNotEqual(old,current['revision'])
        self.assertEqual({r['language'] for r in self.cli('history')['revisions']},{'0.8','0.10'})
        self.assertEqual({n['name']:n['id'] for n in graph['nodes']},{n['name']:n['id'] for n in self.cli('graph')['nodes']})
        self.assertEqual({n['path']:n['id'] for n in nodes},{n['path']:n['id'] for n in self.cli('operations','--symbol','value')['nodes']})
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')

    def test_lazy_watch_patterns_capture_only_selected_paths(self):
        self.source('''module match_watch;
enum Maybe<T>{None;Some(number:T,large:list<str>);}
fn observe(value:result<Maybe<i64>>) -> unit !{io} {print(1);}
fn main() -> unit !{io} {observe(ok(Maybe::Some(41,["unread"])));}
''')
        session=self.cli('debug');manifest=json.loads(Path(session['manifest']).read_text())
        frame={'schema':'nex.debug-frame/2','language':'0.10','revision':session['revision'],'build_key':manifest['build_key'],'function':'match_watch::observe','stop':{'process_id':'1','thread_id':'2','frame_id':0,'stop_id':'1'},'bindings':[{'name':'value','type':'result<match_watch::Maybe<i64>>','unavailable':'not captured'}],'captures':[],'truncated':False}
        path=self.root/'frame.json';expression='match value {ok(Maybe::Some(n,_)) if n>0 => n+1,_=>0}'
        expected=[([],{'ok':True}),(['ok'],{'case':'Some'}),(['ok','Some::number'],'41')]
        for selected,value in expected:
            path.write_text(json.dumps(frame));demand=self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression,'--kind','demand')['request'];self.assertEqual(demand['path'],selected);frame['captures'].append({**{k:demand[k] for k in ('binding','path','kind')},'value':value})
        path.write_text(json.dumps(frame));value=self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression);self.assertEqual(value['value'],'42');self.assertTrue(all('Some::large' not in row['path'] for row in value['read_paths']))
        plan=self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression,'--kind','plan');self.assertEqual([v['name'] for v in plan['variables']],['value'])
        self.file.unlink();self.assertEqual(self.cli('inspect',path,'--manifest',session['manifest'],'--expression',expression)['value'],'42')

    def test_pattern_resource_bounds_and_trap_semantics(self):
        self.source('module limit; fn main() -> i64 {return match 1 {'+'['*70+'x'+']'*70+'=>1,_=>0};}')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_MATCH_LIMIT')
        self.source('module traps; fn main() -> i64 {return match ok("owned") {ok(text) if len(text)>0=>9223372036854775807+1,_=>0};}')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_OVERFLOW')
        for profile in ('debug','release'):
            result=self.cli('run','--profile',profile,ok=False);self.assertEqual(result['exit_code'],70);self.assertIn('E_OVERFLOW',result['stderr'])

    def test_reviewed_task_repair_and_source_deleted_replay(self):
        self.source('''module match_accept;
pub fn choose(value:result<i64>) -> i64 {return match value {ok(n) if n>0=>0,_=>-1};}
fn main() -> unit !{io} {print(choose(ok(42)));}
test fn cases() -> unit {assert(choose(ok(42))==42);assert(choose(err<i64>("E","error")) == -1);}
''')
        task=self.cli('task',self.file,'--kind','init');native=next(c for c in task['checks'] if c['kind']=='test');web=dict(native,id='web',target='web');task['checks'].append(web)
        task['requirements'].append({'id':'matching','text':'Preserve reviewed match selection in native and browser backends','bindings':[{'program':'app','kind':'function','symbol':'match_accept::choose'}],'targets':['native','web'],'checks':[native['id'],'web']})
        path=self.root/'task.json';path.write_text(json.dumps(task));failed=self.cli('task',path,'--kind','run',ok=False,timeout=180)
        revision=self.cli('check')['revision'];patch=self.root/'patch.json';patch.write_text(json.dumps({'expected_revision':revision,'replacements':[{'name':'match_accept::choose','source':'pub fn choose(value:result<i64>) -> i64 {return match value {ok(n) if n>0=>n,_=>-1};}'}]}))
        fixed=self.cli('apply','--patch',patch)['revision'];passed=self.cli('task',path,'--kind','run','--revision',fixed,'--task-hash',failed['task_hash'],timeout=180)
        self.assertEqual(passed['task_hash'],failed['task_hash']);self.file.unlink();replay=self.cli('task',passed['output'],'--kind','replay',timeout=180);self.assertEqual(replay['status'],'passed')
        self.assertEqual(replay['task_hash'],failed['task_hash'])


if LIVE:
    class LiveMatching(harness.ToolchainCase):
        def test_nested_bindings_dwarf_lldb_and_selected_watch_capture(self):
            self.source('''module live_match;
enum E {None;Pair(number:i64,label:str,large:list<str>);}
fn observe(value:result<E>) -> unit !{io} {
 match value {
  ok(E::Pair(number,label,_)) if number>0 => {
   let answer:i64 = match number {0=>0,n=>n+1};
   print(answer); // break: selected
  },
  _ => {print(0);}
 }
}
fn main() -> unit !{io} {observe(ok(E::Pair(41,"A\\u0000🌍",["unread"])));}
''')
            session=self.cli('debug');manifest=json.loads(Path(session['manifest']).read_text());source=manifest['sources'][0]['projection'];line=next(i+1 for i,s in enumerate(self.file.read_text().splitlines()) if '// break: selected' in s)
            report=self.root/'selected.json';script=self.root/'capture.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE);process=target.LaunchSimple(None,None,None)
 try:
  assert process.GetState()==lldb.eStateStopped;stop=process.GetStopID()
  def command(text):
   result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
   assert result.Succeeded(),result.GetError();return json.loads(result.GetOutput())
  expression='match value {ok(E::Pair(n,_,_)) if n>0=>n+1,_=>0}'
  output={'values':command('nex-values'),'bound':command('nex-eval number+1'),'computed':command('nex-eval '+expression),'frame':command('nex-frame '+expression)}
  assert process.GetStopID()==stop
  with open(REPORT,'w') as out:json.dump(output,out)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(source)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            result=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),result.stdout+result.stderr);data=json.loads(report.read_text());values={v['name']:v['value'] for v in data['values']['variables']}
            self.assertEqual(values['number'],'41');self.assertEqual(values['answer'],'42');self.assertIn('\\0🌍',values['label']);self.assertNotIn('n',values)
            self.assertEqual(data['bound']['value'],'42');self.assertEqual(data['computed']['value'],'42');self.assertTrue(all('Pair::large' not in c['path'] for c in data['frame']['captures']))
            from debugging import DAP
            adapter=self.cli('debug','--kind','nex-dap');client=DAP(adapter['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
                pending=client.send('launch',dict(adapter['launch'],disableASLR=False));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[{'line':line}]});client.request('configurationDone');client.response(pending);stop=client.event('stopped')
                frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
                result=client.request('evaluate',{'expression':'match value {ok(E::Pair(n,_,_)) if n>0=>n+1,_=>0}','frameId':frame,'context':'watch'})
                self.assertEqual(result['nex']['value'],'42');self.assertEqual(result['nex']['revision'],session['revision'])
                client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()
            self.file.unlink();snapshot=self.root/'frame.json';snapshot.write_text(json.dumps(data['frame']));self.assertEqual(self.cli('inspect',snapshot,'--manifest',session['manifest'],'--expression','match value {ok(E::Pair(n,_,_))=>n+1,_=>0}')['value'],'42')


if __name__=='__main__':unittest.main()
