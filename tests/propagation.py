"""Observable result propagation, ownership exits and genuine0.16 migration."""
import json
from pathlib import Path
import unittest
import support as harness


class Propagation(harness.ToolchainCase):
    def test_descriptor_contract_and_sample_agree_in_three_backends(self):
        descriptor=self.cli('describe')
        self.assertEqual(descriptor['version'],'0.18')
        self.assertFalse(descriptor['result_propagation']['checked_traps_caught'])
        self.assertFalse(descriptor['result_propagation']['source_try_catch_throw'])
        self.source((harness.REPO/'examples/propagation.nex').read_text())
        expected=self.cli('eval')['stdout']
        self.assertIn('value=42',expected);self.assertIn('PARTIAL',expected)
        for profile in ['debug','release','profile']:
            self.cli('test','--profile',profile,timeout=180)
            self.assertEqual(self.cli('run','--profile',profile,timeout=180)['stdout'],expected)
        self.cli('test','--target','web',timeout=180)
        measured=self.cli('profile','--scenario','result propagation exits',timeout=180)
        self.assertEqual(measured['stdout'],expected)
        saved=json.loads(Path(measured['output']).read_text())
        for pool in saved['memory']:
            self.assertEqual(pool['live'],0,pool)
            self.assertEqual(pool['allocations'],pool['frees'],pool)
        for function in saved['functions']:
            self.assertEqual(function['calls'],function['completed'],function)
            self.assertEqual(function['aborted'],0,function)

    def test_order_single_evaluation_and_prior_argument_cleanup(self):
        self.source('''module order;
fn first()->str!{io}{print("first");return "temp"+"orary";}
fn stop()->result<str>!{io}{print("stop");return err("STOP","unchanged");}
fn last()->str!{io}{print("last");return "later";}
fn consume(a:str,b:str,c:str)->str{return a+b+c;}
fn work()->result<str>!{io}{return ok(consume(first(),stop()?,last()));}
fn main()->unit!{io}{print(work());}
test fn observable()->unit!{io}{assert(work()==err<str>("STOP","unchanged"));}
''')
        expected=self.cli('eval')['stdout']
        self.assertEqual(expected,'first\nstop\n{"error":{"code":"STOP","message":"unchanged"}}\n')
        self.assertEqual(self.cli('run')['stdout'],expected)
        self.cli('test','--target','web',timeout=180)

    def test_loops_matches_callable_payload_and_all_scalar_shapes(self):
        self.source('''module shapes;
fn plus(v:i64)->i64{return v+1;}
fn callable()->result<i64>{let run:fn(i64)->i64=ok(plus)?;return ok(run(41));}
fn float_value()->result<f64>{return ok(-ok(2.5)?);}
fn bytes_value()->result<bytes>{return ok(ok(utf8_bytes("🦊"))?);}
fn loop(stop:i64)->result<str>{
  var i:i64=0;var text:str="";
  while i<5 {text=text+str(i);if i==stop {let ignored:str=err<str>("LOOP",text)?;}i=i+1;}
  return ok(text);
}
fn guard()->result<str>{return ok(match true {true if err<bool>("GUARD","m")?=>"unused",_=>"fallback"});}
fn main()->unit{}
test fn values()->unit{
  assert(callable()==ok(42));assert(float_value()==ok(-2.5));
  assert(unwrap(decode_utf8(unwrap(bytes_value())))=="🦊");
  assert(loop(3)==err<str>("LOOP","0123"));assert(loop(9)==ok("01234"));
  assert(guard()==err<str>("GUARD","m"));
}
''')
        self.cli('test',timeout=180);self.cli('test','--target','web',timeout=180)

    def test_rejected_programs_and_unused_generic_bodies(self):
        cases=[('fn bad()->i64{return ok(1)?;}','E_RESULT_RETURN'),
               ('fn bad()->result<i64>{return ok(1?);}','E_TYPE'),
               ('fn bad<T>(v:result<T>)->T{return v?;}','E_RESULT_RETURN'),
               ('fn bad<T>(v:T)->result<T>{return ok(v?);}','E_TYPE'),
               ('fn bad()->result<i64>{let run:fn()->i64=fn()->i64{return ok(1)?;};return ok(run());}','E_RESULT_RETURN'),
               ('fn bad()->result<i64>{print("effect");return ok(ok(1)?);}','E_EFFECT'),
               ('fn bad()->result<i64>{return ok(read_env("X")?);}','E_REALM')]
        for source,code in cases:
            with self.subTest(code=code,source=source):
                self.source('module invalid;fn main()->unit{}'+source)
                self.assertEqual(self.cli('check',ok=False)['code'],code)

    def test_checked_traps_are_not_recovered(self):
        self.source('''module trap;
fn work()->result<i64>{let value:i64=ok(1)?;return ok(value/0);}
fn main()->unit{let result:result<i64>=work();}
test fn not_recovered()->unit{let result:result<i64>=work();}
''')
        self.assertEqual(self.cli('eval',ok=False)['code'],'E_DIV_ZERO')
        run=self.cli('run',ok=False);self.assertEqual(run['exit_code'],70);self.assertIn('E_DIV_ZERO',run['stderr'])
        result=self.cli('test','--target','web',ok=False,timeout=180)
        self.assertIn('E_DIV_ZERO',json.dumps(result))

    def test_real_files_cleanup_preserves_caller_and_returned_aliases(self):
        data=self.root/'files';data.mkdir();(data/'input').write_bytes(b'abcdef')
        self.source('''module owned_files;
server fn open()->result<file>!{fs}{return ok(file_open_read("input")?);}
server fn fail()->result<i64>!{fs}{
  let partial:list<file>=[file_open_read("input")?,err<file>("STOP","same")?];
  return ok(len(partial));
}
server fn borrowed(input:file)->result<i64>{
  let partial:list<file>=[input,err<file>("STOP","borrowed")?];return ok(len(partial));
}
server fn main()->unit!{fs,io}{
  let kept:file=unwrap(open());var i:i64=0;
  while i<100 {assert(fail()==err<i64>("STOP","same"));i=i+1;}
  assert(borrowed(kept)==err<i64>("STOP","borrowed"));
  assert(file_is_open(kept));assert(unwrap(file_read(kept,2))==utf8_bytes("ab"));
  assert(file_close(kept));print(i);
}
''')
        env={'NEX_FILES_ROOT':str(data)}
        self.assertEqual(self.cli('eval',env=env)['stdout'],'100\n')
        for profile in ['debug','release']:
            self.assertEqual(self.cli('run','--profile',profile,env=env,timeout=180)['stdout'],'100\n')

    def test_watch_rejects_return_from_stopped_frame_but_allows_helpers(self):
        self.source('''module stopped;
fn helper(value:result<i64>)->result<i64>{return ok(value?+1);}
fn main()->unit{let value:result<i64>=ok(41);let result:result<i64>=helper(value);}
''')
        session=self.cli('debug',timeout=180);manifest=Path(session['manifest'])
        identity=json.loads(manifest.read_text())
        frame={'schema':'nex.debug-frame/1','language':'0.18','revision':identity['revision'],
               'build_key':identity['build_key'],'function':'stopped::main',
               'stop':{'process_id':'1','thread_id':'1','frame_id':0,'stop_id':'1'},
               'bindings':[{'name':'value','type':'result<i64>','value':{'ok':'41'}}],
               'truncated':False}
        path=self.root/'frame.json';path.write_text(json.dumps(frame))
        self.assertEqual(self.cli('inspect',path,'--manifest',manifest,'--expression','value?',ok=False)['code'],'E_DEBUG_RETURN')
        result=self.cli('inspect',path,'--manifest',manifest,'--expression','helper(value)')
        self.assertEqual(result['value'],{'ok':'42'})
        result=self.cli('inspect',path,'--manifest',manifest,'--expression','(fn()->result<i64>{return ok(value?+1);})()')
        self.assertEqual(result['value'],{'ok':'42'})

    def test_genuine016_migration_keeps_every_historical_row_and_local_id(self):
        fixture=json.loads((harness.REPO/'tests/fixtures/language-0.16.json').read_text())
        self.source(fixture['source']);self.historical_store('0.16')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'main.nex'}))
        before=harness.database_rows(self.root/'.nex/graph.db')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.cli('eval','--revision',fixture['revision'],ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)
        self.file.unlink();current=self.cli('migrate','--revision',fixture['revision'])['revision']
        self.assertNotEqual(current,fixture['revision'])
        schema,tables=harness.database_rows(self.root/'.nex/graph.db');self.assertEqual(schema,before[0])
        for name,rows in before[1].items():
            if name!='head':self.assertLessEqual(set(map(repr,rows)),set(map(repr,tables[name])),name)
        self.assertFalse(self.file.exists())
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],fixture['stdout'])
        old=self.root/'old';new=self.root/'new'
        self.cli('export','--revision',fixture['revision'],'--directory',old)
        self.cli('export','--revision','HEAD','--directory',new)
        self.assertEqual(json.loads((old/'nex.json').read_text())['language'],'0.16')
        self.assertEqual(json.loads((new/'nex.json').read_text())['language'],'0.18')
        self.assertEqual((old/'main.nex').read_text(),fixture['source'])
        self.assertEqual(self.cli('run',cwd=new,timeout=180)['stdout'],fixture['stdout'])
        self.cli('test','--target','web',cwd=new,timeout=180)

    def test_graph_expression_repair_preserves_source_and_checked_history(self):
        source='''module repaired;
fn value()->result<str>{return ok(str(ok(41)?));}
fn main()->unit!{io}{print(value());}
test fn wanted()->unit{assert(value()==ok("42"));}
'''
        self.source(source);revision=self.cli('check')['revision']
        context=self.cli('operations','--symbol','value','--limit','100')
        target=next(node for node in context['nodes'] if node['kind']=='expression.propagate_result')
        span=target['source_range'];self.assertTrue(span['editable'])
        self.assertEqual(source.encode()[span['byte_begin']:span['byte_end']],b'ok(41)?')
        patch={'expected_revision':revision,'expected_source_hash':context['source_hash'],
               'replacements':[{'operation_id':target['id'],'source':'42?'}]}
        path=self.root/'patch.json';path.write_text(json.dumps(patch))
        before=harness.database_rows(self.root/'.nex/graph.db')
        self.assertEqual(self.cli('apply','--patch',path,ok=False)['code'],'E_TYPE')
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)
        patch['replacements'][0]['source']='ok(42)?';path.write_text(json.dumps(patch))
        self.cli('apply','--patch',path)
        self.assertEqual(self.file.read_text(),source)
        self.assertEqual(self.cli('eval','--revision',revision)['stdout'],'{"ok":"41"}\n')
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'{"ok":"42"}\n')
        self.assertEqual(self.cli('run','--revision','HEAD',timeout=180)['stdout'],'{"ok":"42"}\n')
        self.cli('test','--revision','HEAD','--target','web',timeout=180)


if __name__=='__main__':unittest.main()
