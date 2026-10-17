"""NEX expression semantics in captured frames and actual read-only LLDB stops."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness


class Expressions(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        for name in ['main.nex','model.nex']:
            shutil.copyfile(harness.REPO/'examples/debugging'/name,self.root/name)
        with (self.root/'model.nex').open('a') as model:
            model.write('\nfn hidden() -> i64 { return 9; }\n')
        with self.file.open('a') as output:
            output.write('''\nfn spin() -> i64 { var n: i64 = 0; while true { n = n + 1; } return n; }
server fn server_value() -> i64 { return 3; }
fn noisy() -> i64 !{io} { print(9); return 9; }
fn expand() -> list<str> { var items: list<str> = ["x"]; var n: i64 = 0; while n < 30 { items = items + items; n = n + 1; } return items; }
''')
        self.session=self.cli('debug')
        self.manifest=Path(self.session['manifest'])
        identity=json.loads(self.manifest.read_text())
        label='\u0410\u0434\u0430\x00\U0001f30d'
        values={'n':('i64','40'),'enabled':('bool',True),'label':('str',label),
                'person':('debugging::model::Person',{'id':'7','name':label,'tags':['nex','debug']}),
                'total':('i64','42'),'items':('list<i64>',['40','41']),
                'reply':('result<str>',{'ok':label}),
                'failure':('result<i64>',{'error':{'code':'EXAMPLE','message':'recoverable error'}}),
                'empty':('list<str>',[])}
        self.frame={'schema':'nex.debug-frame/1','language':'0.5','revision':identity['revision'],
                    'build_key':identity['build_key'],'function':'debugging::app::inspect',
                    'stop':{'process_id':'100','thread_id':'101','frame_id':0,'stop_id':'1'},
                    'bindings':[{'name':n,'type':t,'value':v} for n,(t,v) in values.items()], 'truncated':False}
        self.framefile=self.root/'frame.json'

    def inspect(self, expression, frame=None, **kwargs):
        self.framefile.write_text(json.dumps(frame or self.frame))
        return self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression',expression,**kwargs)

    def test_scalars_collections_nominal_types_results_and_generic_json(self):
        for expr,expected in [('model::increment(total) + items[1]','84'),
                ('len(label)','5'),('label[3]','\x00'),('slice(person.name, 4, 1)','\U0001f30d'),
                ('push(items, 99)',['40','41','99']),('set(items, 1, 7)',['40','7']),
                ('error_code(failure)','EXAMPLE'),('is_ok(reply)',True),
                ('unwrap(decode_json<model::Person>(encode_json(person))).tags',['nex','debug']),
                ('model::Person(9, "x", []).id','9'),('assert(enabled)',None)]:
            with self.subTest(expr=expr):
                result=self.inspect(expr)
                self.assertEqual(result['schema'],'nex.expression/1')
                self.assertEqual(result['value'],expected)
                self.assertEqual(result['stop'],self.frame['stop'])
                self.assertEqual(json.loads(self.framefile.read_text()),self.frame)

    def test_short_circuit_unavailable_and_rejected_wire_data(self):
        frame=copy.deepcopy(self.frame)
        item=next(b for b in frame['bindings'] if b['name']=='items');item.pop('value');item['unavailable']='collection capture budget exhausted'
        result=self.inspect('false && items[0] == 0',frame)
        self.assertFalse(result['value']);self.assertEqual(result['read_bindings'],[])
        self.assertEqual(self.inspect('items[0]',frame,ok=False)['code'],'E_DEBUG_UNAVAILABLE')
        frame=copy.deepcopy(self.frame);frame['bindings'][0]['value']=40
        self.assertEqual(self.inspect('n',frame,ok=False)['code'],'E_DEBUG_VALUE')
        frame['bindings'][0]['value']='9223372036854775808'
        self.assertEqual(self.inspect('n',frame,ok=False)['code'],'E_DEBUG_VALUE')

    def test_checked_arithmetic_bounds_and_inference(self):
        for expr,code in [('9223372036854775807 + 1','E_OVERFLOW'),('-9223372036854775808 / -1','E_OVERFLOW'),
                          ('1 / 0','E_DIV_ZERO'),('items[-1]','E_BOUNDS'),('unwrap(failure)','E_RESULT'),
                          ('[]','E_INFER'),('1 + true','E_TYPE'),('total = 8','E_PARSE')]:
            with self.subTest(expr=expr):self.assertEqual(self.inspect(expr,ok=False)['code'],code)
        self.assertEqual(self.inspect('-9223372036854775808 % -1')['value'],'0')
        self.assertEqual(self.inspect('-7 / 3')['value'],'-2')
        self.assertEqual(self.inspect('-7 % 3')['value'],'-1')

    def test_effects_realms_visibility_and_frame_identity_are_checked(self):
        self.assertEqual(self.inspect('print(total)',ok=False)['code'],'E_EFFECT')
        self.assertEqual(self.inspect('read_env("HOME")',ok=False)['code'],'E_REALM')
        self.assertEqual(self.inspect('server_value()',ok=False)['code'],'E_REALM')
        self.assertEqual(self.inspect('noisy()',ok=False)['code'],'E_EFFECT')
        self.assertEqual(self.inspect('model::hidden()',ok=False)['code'],'E_VISIBILITY')
        frame=copy.deepcopy(self.frame);frame['build_key']='0'*64
        self.assertEqual(self.inspect('total',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=copy.deepcopy(self.frame);frame['bindings'].append(dict(frame['bindings'][0]))
        self.assertEqual(self.inspect('total',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=copy.deepcopy(self.frame);frame['bindings'][0]['type']='str'
        self.assertEqual(self.inspect('n',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=copy.deepcopy(self.frame);frame['function']='debugging::app::model_test'
        self.assertEqual(self.inspect('1',frame,ok=False)['code'],'E_DEBUG_FRAME')
        helper=copy.deepcopy(self.frame);helper['function']='debugging::model::increment'
        helper['bindings']=[{'name':'value','type':'i64','value':'40'},{'name':'next','type':'i64','value':'41'}]
        self.assertEqual(self.inspect('increment(value) + next',helper)['value'],'82')
        self.assertEqual(self.inspect('hidden()',helper)['value'],'9')

    def test_plan_needs_only_referenced_inputs_and_does_not_execute(self):
        frame=copy.deepcopy(self.frame)
        for b in frame['bindings']:b.pop('value',None);b['unavailable']='not yet read'
        result=self.cli_plan(frame)
        self.assertEqual({v['name'] for v in result['variables']},{'total','person'})
        person=next(v for v in result['variables'] if v['name']=='person')
        self.assertEqual(person['wire_schema']['root'],{'record':'debugging::model::Person'})
        self.assertNotIn('value',result)
        result=self.inspect('assert(false) || false',ok=False)
        self.assertEqual(result['code'],'E_TYPE')

    def cli_plan(self,frame):
        self.framefile.write_text(json.dumps(frame))
        return self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression','model::increment(total) + person.id','--kind','plan')

    def test_pure_call_step_allocation_and_expression_limits(self):
        self.framefile.write_text(json.dumps(self.frame))
        result=self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression','spin()','--steps','50',ok=False)
        self.assertEqual(result['code'],'E_LIMIT')
        self.assertEqual(self.inspect('expand()',ok=False)['code'],'E_DEBUG_LIMIT')
        self.assertEqual(self.inspect('!'*2000+'true',ok=False)['code'],'E_DEBUG_LIMIT')
        self.assertEqual(self.inspect('"'+('x'*5000)+'"')['display_truncated'],True)
        self.assertEqual(self.inspect('"'+('x'*5000)+'"')['value'],'x'*5000)

    def test_archived_source_integrity_and_no_graph_writes(self):
        revision=self.cli('graph')['revision']
        self.file.unlink();(self.root/'model.nex').unlink()
        self.assertEqual(self.inspect('model::increment(total)')['value'],'43')
        self.assertEqual(self.cli('graph')['revision'],revision)
        bundle=self.manifest.parent/'source-bundle.json';original=bundle.read_bytes();value=json.loads(original)
        value['files']['main.nex']+='\n// changed exact source\n';bundle.write_text(json.dumps(value))
        self.assertEqual(self.inspect('total',ok=False)['code'],'E_DEBUG_SNAPSHOT')
        bundle.write_bytes(original)

    def test_raw_frame_rejects_duplicates_escaped_duplicates_and_malformed_utf8(self):
        raw=json.dumps(self.frame,ensure_ascii=False)
        self.assertIn('"id": "7"',raw)
        for replacement in ['"id": "9", "id": "7"','"i\\u0064": "9", "id": "7"']:
            self.framefile.write_text(raw.replace('"id": "7"',replacement,1))
            result=self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression','person.id',ok=False)
            self.assertEqual(result['code'],'E_DEBUG_FRAME')
        self.framefile.write_bytes(b'\xef\xbb\xbf'+raw.encode('utf-8'))
        self.assertEqual(self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression','person.id')['value'],'7')
        self.framefile.write_bytes(raw.encode('utf-8')[:-1]+b',"extra":"\xff"}')
        self.assertEqual(self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression','person.id',ok=False)['code'],'E_DEBUG_FRAME')

    def test_reference_native_and_typescript_agree_with_watch_values(self):
        expr='model::increment(total) + items[1]'
        expected=self.inspect(expr)['value']
        with self.file.open('a') as output:
            output.write('''\nfn projection() -> unit !{io} { let total: i64 = 42; let items: list<i64> = [40, 41]; print(encode_json('''+expr+''')); }\n''')
        interpreted=self.cli('eval','--entry','projection')['stdout']
        self.assertEqual(json.loads(interpreted),expected)
        native=self.cli('run','--entry','projection')
        self.assertEqual(native['stdout'],interpreted)
        folder=self.root/'ts'
        self.cli('emit','--kind','typescript','--entry','projection','--directory',folder)
        (folder/'package.json').write_text('{"type":"module"}')
        (folder/'watch.ts').write_text("import {entry} from './program.ts';entry();")
        actual=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(folder/'watch.ts')],capture_output=True,text=True,timeout=30)
        self.assertEqual(actual.returncode,0,actual.stderr);self.assertEqual(actual.stdout,interpreted)


if LIVE:
    class LiveExpressions(harness.ToolchainCase):
        def test_actual_frame_exact_values_shadowing_pure_calls_and_stops(self):
            for name in ['main.nex','model.nex']:shutil.copyfile(harness.REPO/'examples/debugging'/name,self.root/name)
            session=self.cli('debug')
            manifest=json.loads(Path(session['manifest']).read_text())
            projected=next(s['projection'] for s in manifest['sources'] if Path(s['original']).name=='main.nex')
            script=self.root/'watch_live.py';report=self.root/'watch.json'
            script.write_text('''import json,lldb

def __lldb_init_module(debugger, _):
    debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
    target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,12);target.BreakpointCreateByLocation(SOURCE,14)
    process=target.LaunchSimple(None,None,None);out=[]
    def command(expression,success=True):
        r=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand('nex-eval '+expression,r)
        assert r.Succeeded()==success,(expression,r.GetOutput(),r.GetError())
        return json.loads(r.GetOutput() if success else r.GetError().removeprefix('error: '))
    try:
        assert process.GetState()==lldb.eStateStopped
        stop=process.GetStopID()
        for expression in ['total','model::increment(total) + items[1]','person.name','len(label)','label[3]','push(items, 99)','unwrap(reply)','error_message(failure)','person.tags']:
            out.append(command(expression))
        assert command('print(total)',False)['code']=='E_EFFECT'
        assert process.GetStopID()==stop and process.GetState()==lldb.eStateStopped
        assert process.GetSelectedThread().GetSelectedFrame().FindVariable('total').GetValueAsSigned()==42
        process.Continue();out.append(command('total'))
        process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
        with open(REPORT,'w') as output:json.dump(out,output)
    finally:
        if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('REPORT',repr(str(report))))
            self.file.unlink();(self.root/'model.nex').unlink()
            self.cli('debug','--revision','HEAD','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file())
            results=json.loads(report.read_text())
            self.assertEqual([v['value'] for v in results],['42','84','\u0410\u0434\u0430\x00\U0001f30d','5','\x00',['40','41','99'],'\u0410\u0434\u0430\x00\U0001f30d','recoverable error',['nex','debug'],'40'])
            self.assertNotEqual(results[0]['stop']['stop_id'],results[-1]['stop']['stop_id'])


        def test_real_dap_watch_children_nonselected_frame_and_stale_references(self):
            from debugging import DAP
            for name in ['main.nex','model.nex']:shutil.copyfile(harness.REPO/'examples/debugging'/name,self.root/name)
            session=self.cli('debug','--kind','nex-dap')
            self.assertEqual(session['adapter'],'nex-dap');self.assertTrue(session['nex_adapter']['available'])
            manifest=json.loads(Path(session['manifest']).read_text())
            source=next(s['projection'] for s in manifest['sources'] if Path(s['original']).name=='main.nex')
            client=DAP(session['adapter_command'],self.root)
            try:
                capabilities=client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'columnsStartAt1':True,'supportsVariableType':True,'supportsVariablePaging':True})
                self.assertFalse(capabilities['supportsSetExpression'])
                pending=client.send('launch',dict(session['launch'],disableASLR=False))
                client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[{'line':12},{'line':14}]})
                client.request('configurationDone');client.response(pending)
                stop=client.event('stopped')
                stack=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames']
                scopes=client.request('scopes',{'frameId':stack[0]['id']})['scopes']
                physical=next(s['variablesReference'] for s in scopes if not s.get('expensive'))
                before=client.request('variables',{'variablesReference':physical})['variables']
                def evaluate(expression,frame=0):return client.request('evaluate',{'expression':expression,'frameId':stack[frame]['id'],'context':'watch'})
                value=evaluate('model::increment(total) + items[1]')
                self.assertEqual(value['result'],'84');self.assertEqual(value['type'],'i64')
                initial_stop=value['nex']['stop']['stop_id']
                values=evaluate('push(items, 99)')
                reference=values['variablesReference'];self.assertGreater(reference,0)
                children=client.request('variables',{'variablesReference':reference,'start':1,'count':1})['variables']
                self.assertEqual([(v['name'],v['value'],v['type']) for v in children],[('[1]','41','i64')])
                person=evaluate('person')
                fields=client.request('variables',{'variablesReference':person['variablesReference']})['variables']
                self.assertEqual([v['name'] for v in fields],['id','name','tags'])
                self.assertEqual(fields[0]['value'],'7')
                tags=client.request('variables',{'variablesReference':fields[2]['variablesReference']})['variables']
                self.assertEqual([v['value'] for v in tags],['"nex"','"debug"'])
                self.assertEqual(evaluate('person.id',1)['nex']['function'],'debugging::app::main')
                self.assertEqual(evaluate('total\n+\n2')['result'],'44')
                self.assertEqual(evaluate('total')['nex']['stop']['stop_id'],initial_stop)
                bad=client.send('evaluate',{'expression':'print(total)','frameId':stack[0]['id'],'context':'watch'})
                failure=client.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==bad)
                self.assertFalse(failure['success']);self.assertIn('E_EFFECT',str(failure))
                bad=client.send('evaluate',{'expression':'0\n`continue','frameId':stack[0]['id'],'context':'watch'})
                failure=client.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==bad)
                self.assertFalse(failure['success'])
                self.assertEqual(evaluate('total')['result'],'42')
                after=client.request('variables',{'variablesReference':physical})['variables']
                self.assertEqual([(v['name'],v['value']) for v in before],[(v['name'],v['value']) for v in after])
                client.request('continue',{'threadId':stop['threadId']});stop=client.event('stopped')
                bad=client.send('variables',{'variablesReference':reference})
                failure=client.wait(lambda m:m.get('type')=='response' and m.get('request_seq')==bad)
                self.assertFalse(failure['success']);self.assertIn('stale',failure['message'])
                stack=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames']
                self.assertEqual(evaluate('total')['result'],'40')
                client.request('continue',{'threadId':stop['threadId']})
                self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()

        def test_exact_long_string_and_bounded_shared_dag_capture(self):
            for name in ['main.nex','model.nex']:shutil.copyfile(harness.REPO/'examples/debugging'/name,self.root/name)
            source=self.file.read_text();long_text='\u03b1'*300+'\x00\U0001f98a'
            source=source.replace('"\u0410\u0434\u0430\\u0000\U0001f30d"',json.dumps(long_text,ensure_ascii=False))
            declarations='';kind='str'
            for index in range(15):
                kind='list<'+kind+'>'
                expression='["x"]' if index==0 else '[huge'+str(index-1)+', huge'+str(index-1)+']'
                declarations+='  let huge'+str(index)+': '+kind+' = '+expression+';\n'
            source=source.replace('  if enabled {',declarations+'  if enabled {');self.file.write_text(source)
            session=self.cli('debug');manifest=json.loads(Path(session['manifest']).read_text())
            projected=next(s['projection'] for s in manifest['sources'] if Path(s['original']).name=='main.nex')
            line=next(i+1 for i,s in enumerate(source.splitlines()) if '// break: inner' in s)
            report=self.root/'long-watch.json';script=self.root/'long_watch.py'
            script.write_text('''import json,lldb

def __lldb_init_module(debugger, _):
    debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
    target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
    process=target.LaunchSimple(None,None,None)
    def command(text):
        r=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,r)
        assert r.Succeeded(),r.GetError()
        return json.loads(r.GetOutput())
    try:
        assert process.GetState()==lldb.eStateStopped
        result={'length':command('nex-eval len(label)'), 'zero':command('nex-eval label[300]'), 'person':command('nex-frame person'),
                'bounded':command('nex-frame huge14'), 'short':command('nex-eval false && len(huge14) > 0'), 'scalar':command('nex-eval n + 1')}
        with open(REPORT,'w') as output:json.dump(result,output)
        process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
    finally:
        if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),output.stdout+output.stderr);result=json.loads(report.read_text())
            self.assertEqual(result['length']['value'],'302');self.assertEqual(result['zero']['value'],'\x00')
            person=next(b['value'] for b in result['person']['bindings'] if b['name']=='person')
            self.assertEqual(person['name'],long_text)
            bounded=next(b for b in result['bounded']['bindings'] if b['name']=='huge14')
            self.assertIn('unavailable',bounded);self.assertNotIn('value',bounded)
            self.assertFalse(result['short']['value']);self.assertEqual(result['short']['read_bindings'],[])
            self.assertEqual(result['scalar']['value'],'41')


if __name__=='__main__':unittest.main(verbosity=2)
