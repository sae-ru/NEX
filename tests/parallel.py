"""Source CPU map semantics, actual native threads and genuine017 migration."""
import copy,json,sys
from pathlib import Path
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness

class Parallel(harness.ToolchainCase):
    def agreement(self):
        self.cli('check');self.cli('test',timeout=240);self.cli('test','--target','web',timeout=240)

    def test_ordered_mapping_uses_actual_native_worker_threads_and_cleans_profile(self):
        self.source('''module cpu_workers;
fn work(n:i64)->i64{var i:i64=0;var total:i64=0;while i<2000{total=total+n+i;i=i+1;}return total;}
fn values()->list<i64>{return parallel_map([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],work,4);}
fn main()->unit!{io}{print(values()[15]);}
test fn ordered()->unit{let got:list<i64>=values();assert(len(got)==16);assert(got[0]==1999000);assert(got[15]==2029000);}
''')
        self.agreement();self.assertEqual(self.cli('eval')['stdout'],'2029000\n')
        measured=self.cli('profile','--scenario','actual ordered CPU workers',timeout=240)
        self.assertEqual(measured['stdout'],'2029000\n');saved=json.loads(Path(measured['output']).read_text())
        events=[e for e in saved['traceEvents'] if e.get('name')=='cpu_workers::work']
        self.assertEqual(len(events),16);self.assertGreaterEqual(len({e['tid'] for e in events}),2)
        self.assertTrue(any(a['tid']!=b['tid'] and max(a['ts'],b['ts'])<min(a['ts']+a['dur'],b['ts']+b['dur']) for a in events for b in events))
        for pool in saved['memory']:self.assertEqual(pool['live'],0);self.assertEqual(pool['allocations'],pool['frees'])
        for f in saved['functions']:self.assertEqual(f['calls'],f['completed'],f);self.assertEqual(f['aborted'],0,f)

    def test_generic_callbacks_empty_lists_scalar_tags_heap_and_callable_results(self):
        self.source('''module cpu_shapes;
struct Box<T>{value:T;}
fn identity<T>(value:T)->T{return value;}
fn mapped<T,U>(values:list<T>,callback:fn(T)->U)->list<U>{return parallel_map(values,callback,3);}
fn main()->unit{}
test fn shapes()->unit{
 let offset:i64=40;
 assert(parallel_map([1,2],fn(n:i64)->i64{return n+offset;},2)==[41,42]);
 assert(parallel_map([],fn(n:i64)->str{return str(n);},2)==[]);
 assert(parallel_map([1.5,-2e0],fn(n:f64)->f64{return n+0.5;},2)==[2e0,-1.5]);
 assert(parallel_map([true,false],fn(n:bool)->bool{return !n;},2)==[false,true]);
 assert(parallel_map([Box("Я"),Box("🧠")],identity,2)==[Box("Я"),Box("🧠")]);
 assert(mapped([utf8_bytes("a"),utf8_bytes("🦊")],identity<bytes>)==[utf8_bytes("a"),utf8_bytes("🦊")]);
 let functions:list<fn(i64)->i64>=parallel_map([1,2],fn(n:i64)->(fn(i64)->i64){return fn(x:i64)->i64{return n+x;};},2);
 assert(functions[0](40)==41);assert(functions[1](40)==42);
 let results:list<result<str>>=parallel_map([0,1,2],fn(n:i64)->result<str>{let held:list<str>=["owned","temp"];
  assert(len(held)==2);if n==1{return ok("unnamed"+err<str>("EXPECTED","ошибка 🧠")?);}return ok(str(n));},2);
 assert(results==[ok("0"),err<str>("EXPECTED","ошибка 🧠"),ok("2")]);
}
''');self.agreement()

    def test_nested_groups_preserve_order_and_snapshot_captures(self):
        self.source('''module nested_cpu;
fn main()->unit{}
test fn nesting()->unit{
 var base:i64=40;let callback:fn(i64)->list<i64>=fn(n:i64)->list<i64>{return parallel_map([1,2],fn(x:i64)->i64{return base+n+x;},16);};
 base=100;assert(parallel_map([0,10],callback,2)==[[41,42],[51,52]]);
}
''');self.agreement()

    def test_lowest_index_checked_failure_and_global_limit_precedence(self):
        self.source('''module cpu_failure;
fn work(n:i64)->i64{let held:list<str>=["owned",str(n)];if n==0{return 1/0;}assert(false);return len(held);}
fn main()->unit{let values:list<i64>=parallel_map([0,1],work,2);}
test fn failure()->unit{main();}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_DIV_ZERO')
        native=self.cli('run',ok=False,timeout=180);self.assertEqual(native['exit_code'],70);self.assertIn('E_DIV_ZERO',native['stderr'])
        web=self.cli('test','--target','web',ok=False,timeout=180);self.assertIn('E_DIV_ZERO',json.dumps(web))
        self.source('''module cpu_limit;
fn recurse(n:i64)->i64{return recurse(n+1);}
fn main()->unit{let values:list<i64>=parallel_map([0],recurse,1);}
test fn limit()->unit{main();}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_LIMIT')
        native=self.cli('run',ok=False,timeout=180);self.assertEqual(native['exit_code'],70);self.assertIn('E_LIMIT',native['stderr'])
        web=self.cli('test','--target','web',ok=False,timeout=180);self.assertIn('E_LIMIT',json.dumps(web))
        self.source('''module cpu_global_limit;
fn recurse(n:i64)->i64{return recurse(n+1);}
fn work(n:i64)->i64{if n==0{return 1/0;}return recurse(n);}
fn main()->unit{let values:list<i64>=parallel_map([0,1],work,2);}
test fn limit()->unit{main();}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_LIMIT')
        native=self.cli('run',ok=False,timeout=180);self.assertEqual(native['exit_code'],70);self.assertIn('E_LIMIT',native['stderr'])
        web=self.cli('test','--target','web',ok=False,timeout=180);self.assertIn('E_LIMIT',json.dumps(web))

    def test_worker_and_item_limits_are_checked_before_callbacks(self):
        for workers in [0,17]:
            self.source('module range_cpu;fn main()->unit{let values:list<i64>=parallel_map([],fn(n:i64)->i64{return 1/0;},'+str(workers)+');}test fn bounds()->unit{main();}')
            self.assertEqual(self.cli('eval',ok=False)['code'],'E_RANGE')
            native=self.cli('run',ok=False,timeout=180);self.assertIn('E_RANGE',native['stderr']);self.assertNotIn('E_DIV_ZERO:',native['stderr'])
            web=self.cli('test','--target','web',ok=False,timeout=180);self.assertIn('E_RANGE',json.dumps(web))
        self.source('''module items_cpu;
fn main()->unit{var values:list<i64>=[1];var i:i64=0;while i<16{values=values+values;i=i+1;}
 let output:list<i64>=parallel_map(push(values,1),fn(n:i64)->i64{return 1/0;},2);}
test fn bounds()->unit{main();}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_LIMIT')
        native=self.cli('run',ok=False,timeout=180);self.assertIn('E_LIMIT',native['stderr']);self.assertNotIn('E_DIV_ZERO:',native['stderr'])
        web=self.cli('test','--target','web',ok=False,timeout=180);self.assertIn('E_LIMIT',json.dumps(web))

    def test_argument_evaluation_is_once_and_left_to_right(self):
        self.source('''module cpu_order;
fn items()->list<i64>!{io}{print("items");return [1,2];}
fn callback()->(fn(i64)->i64)!{io}{print("callback");return fn(x:i64)->i64{return x+40;};}
fn workers()->i64!{io}{print("workers");return 2;}
fn main()->unit!{io}{print(parallel_map(items(),callback(),workers()));}
''')
        expected='items\ncallback\nworkers\n[41,42]\n';self.assertEqual(self.cli('eval')['stdout'],expected);self.assertEqual(self.cli('run',timeout=180)['stdout'],expected)

    def test_invalid_types_effects_realms_and_unused_generics_are_rejected(self):
        self.source('module baseline;fn main()->unit{}');self.cli('check');before=harness.database_rows(self.root/'.nex/graph.db')
        cases=[('fn bad()->list<i64>{return parallel_map(1,fn(x:i64)->i64{return x;},2);}','E_TYPE'),
        ('fn bad()->list<i64>{return parallel_map([1],fn(x:i64)->i64!{io}{print(x);return x;},2);}','E_EFFECT'),
        ('fn bad()->list<i64>{return parallel_map([1],fn(x:i64)->unit{},2);}','E_PARALLEL_TYPE'),
        ('fn bad<T>(v:list<T>)->list<i64>{return parallel_map(v,fn(x:i64)->i64{return x;},2);}','E_TYPE'),
        ('fn bad()->list<i64>{return parallel_map([1],fn(x:i64)->i64{return x;},true);}','E_TYPE'),
        ('fn bad()->list<i64>{return parallel_map([1],server fn(x:i64)->i64{return x;},2);}','E_REALM'),
        ('server fn bad(v:list<file>,f:server fn(file)->i64)->list<i64>{return parallel_map(v,f,2);}','E_PARALLEL_TYPE')]
        for body,code in cases:
            with self.subTest(body=body):
                self.source('module rejected;'+body+'fn main()->unit{}');self.assertEqual(self.cli('check',ok=False)['code'],code)
                self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)

    def test_runtime_capture_guard_finds_files_hidden_behind_function_signatures(self):
        self.source('''module hidden_cpu;
server fn main()->unit!{fs}{
 let f:file=unwrap(file_open_read("input"));
 let hidden:server fn()->bool=server fn()->bool{return f==f;};
 let callback:fn(i64)->str=fn(n:i64)->str{return str(hidden)+str(n);};
 let result:list<str>=parallel_map([1,2],callback,2);
}
''')
        data=self.root/'data';data.mkdir();(data/'input').write_text('owned');env={'NEX_FILES_ROOT':str(data)}
        self.cli('check');self.assertEqual(self.cli('eval',env=env,ok=False)['code'],'E_PARALLEL_VALUE')
        native=self.cli('run',env=env,ok=False,timeout=180);self.assertEqual(native['exit_code'],70);self.assertIn('E_PARALLEL_VALUE',native['stderr'])

    def test_genuine017_migration_and_reserved_name_failure_preserve_all_history(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.17.json').read_text());self.source(fixture['source']);self.historical_store('0.17')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.17','entry':'main.nex'}))
        database=self.root/'.nex/graph.db';before=harness.database_rows(database)
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.cli('eval','--revision',fixture['revision'],ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.cli('migrate','--revision',fixture['reserved_revision'],ok=False)['code'],'E_DUPLICATE')
        self.assertEqual(harness.database_rows(database),before)
        current=self.cli('migrate','--revision',fixture['revision'])['revision'];after=harness.database_rows(database)
        self.assertNotEqual(current,fixture['revision']);self.assertEqual(after[0],before[0])
        for name,rows in before[1].items():
            if name!='head':self.assertLessEqual(set(map(repr,rows)),set(map(repr,after[1][name])),name)
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],fixture['stdout']);self.cli('test','--revision','HEAD',timeout=180);self.cli('test','--revision','HEAD','--target','web',timeout=180)
        old=self.root/'old';new=self.root/'new';self.cli('export','--revision',fixture['revision'],'--directory',old);self.cli('export','--directory',new)
        self.assertEqual(json.loads((old/'nex.json').read_text())['language'],'0.17');self.assertEqual(json.loads((new/'nex.json').read_text())['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual((old/'main.nex').read_text(),(new/'main.nex').read_text())
        self.assertEqual(self.cli('graph','--revision',fixture['reserved_revision'],ok=False)['code'],'E_LANGUAGE_VERSION')
        repaired=copy.deepcopy(fixture['reserved_graph'])
        source=fixture['reserved_source'].replace('parallel_map','legacy_map')
        repaired['source']=source;repaired['bundle']['files']['main.nex']=source
        patch=self.root/'repair.json';patch.write_text(json.dumps(repaired));stable=harness.database_rows(database)
        self.cli('migrate',patch);after=harness.database_rows(database)
        for name,rows in stable[1].items():
            if name!='head':self.assertLessEqual(set(map(repr,rows)),set(map(repr,after[1][name])),name)
        self.assertEqual(self.cli('eval','--revision','HEAD')['value'],42)
        self.assertEqual(json.loads((self.root/'nex.json').read_text())['language'],'0.17')

    def test_binary_providers_propagate_parallel_runtime_and_opaque_callbacks(self):
        (self.root/'core').mkdir();(self.root/'app').mkdir()
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'app/main.nex'}))
        (self.root/'core/value.nex').write_text('''module cpu_provider;
pub fn ordinary(x:i64)->i64{return x+1;}
pub fn mapped(callback:fn(i64)->i64)->list<i64>{return parallel_map([1,2],callback,2);}
''')
        (self.root/'app/main.nex').write_text('''module cpu_consumer;import "../core/value.nex" as c;
fn plus(x:i64)->i64{return x+40;}
fn main()->unit!{io}{print(c::mapped(plus));print(c::ordinary(41));}
test fn values()->unit{assert(c::mapped(plus)==[41,42]);}
''')
        manifest={'schema':'nex.project-build/1','default_configuration':'debug','configurations':{'debug':{'profile':'debug'}},'components':{
            'core':{'kind':'static_library','root':'core','entry':'core/value.nex','entry_function':'ordinary','exports':['mapped']},
            'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'static'}}}}
        for linkage in ['static','dynamic']:
            with self.subTest(linkage=linkage):
                manifest['components']['core']['kind']='static_library' if linkage=='static' else 'shared_library'
                manifest['components']['app']['dependencies']['core']=linkage
                (self.root/'nex.build.json').write_text(json.dumps(manifest))
                result=self.cli('project','nex.build.json','--kind','run','--component','app',timeout=300)
                self.assertEqual(result['observation']['stdout'],'[41,42]\n42\n')
                self.cli('project','nex.build.json','--kind','test','--component','app',timeout=300)
        # The separately compiled provider has no map of its own. Its exported
        # callback must still participate in the consuming group's depth bound.
        (self.root/'core/value.nex').write_text('module cpu_provider;pub fn ordinary(x:i64)->i64{return x+1;}pub fn recurse(x:i64)->i64{return recurse(x+1);}')
        (self.root/'app/main.nex').write_text('module cpu_consumer;import "../core/value.nex" as c;fn main()->unit{let out:list<i64>=parallel_map([0],c::recurse,1);}')
        manifest['components']['core']['exports']=['recurse'];(self.root/'nex.build.json').write_text(json.dumps(manifest))
        failed=self.cli('project','nex.build.json','--kind','run','--component','app',ok=False,timeout=300)
        self.assertIn('E_LIMIT',failed['observation']['stderr'])

    @unittest.skipUnless(LIVE,'use --live for actual CPU worker breakpoints and watches')
    def test_live_worker_breakpoint_watch_and_resume_after_source_deletion(self):
        from debugging import DAP
        self.source('''module cpu_debug;
fn work(n:i64)->str{
 let base:i64=n+40;
 let text:str="worker="+str(base);
 return text;
}
fn main()->unit!{io}{print(parallel_map([1,2,3,4],work,2));}
''')
        session=self.cli('debug','--kind','nex-dap',timeout=180)
        if not session['nex_adapter']['available']:self.skipTest('matching lldb-dap unavailable')
        manifest=json.loads(Path(session['manifest']).read_text())
        source=next(s['projection'] for s in manifest['sources'] if Path(s['original']).name=='main.nex')
        self.file.unlink();client=DAP(session['adapter_command'],self.root)
        try:
            client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
            launch=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
            placed=client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[{'line':4}]});self.assertTrue(placed['breakpoints'][0]['verified'])
            client.request('configurationDone');client.response(launch);stop=client.event('stopped');self.assertEqual(stop['reason'],'breakpoint')
            threads=client.request('threads')['threads']
            frames=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames']
            evidence={'stop':stop,'threads':threads,'frames':frames}
            self.assertGreaterEqual(len(threads),3,json.dumps(evidence,ensure_ascii=False))
            frame=frames[0];self.assertIn('work',frame['name'],json.dumps(evidence,ensure_ascii=False))
            value=client.request('evaluate',{'expression':'base+1','frameId':frame['id'],'context':'watch'})
            self.assertIn(value['nex']['value'],['42','43','44','45'])
            client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[]});client.request('continue',{'threadId':stop['threadId']})
            self.assertEqual(client.event('exited')['exitCode'],0);client.event('terminated')
            self.assertFalse(self.file.exists())
        finally:client.close()

if __name__=='__main__':unittest.main()
