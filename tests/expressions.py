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
            model.write('''\nfn hidden() -> i64 { return 9; }
pub fn at(items: list<i64>, index: i64) -> i64 { return items[index]; }
pub fn name(person: Person) -> str { return person.name; }
pub fn first_two(items: list<i64>) -> i64 { var index: i64 = 0; var total: i64 = 0; while index < 2 { total = total + items[index]; index = index + 1; } return total; }
pub enum Selection { Empty; Chosen(id:i64, ignored:i64, samples:list<str>); }
pub fn selected(value:Selection) -> i64 { match value { Selection::Empty() => {return 0;} Selection::Chosen(id,ignored,samples) => {return id + len(samples);} } }
''')
        self.file.write_text(self.file.read_text().replace('  let empty:', '  let selection: model::Selection = model::Selection::Chosen(40,999,["selected"]);\n  let empty:'))
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
                'empty':('list<str>',[]),
                'selection':('debugging::model::Selection',{'case':'Chosen','fields':{'id':'40','ignored':'999','samples':['selected']}})}
        self.frame={'schema':'nex.debug-frame/1','language':'0.19','revision':identity['revision'],
                    'build_key':identity['build_key'],'function':'debugging::app::inspect',
                    'stop':{'process_id':'100','thread_id':'101','frame_id':0,'stop_id':'1'},
                    'bindings':[{'name':n,'type':t,'value':v} for n,(t,v) in values.items()], 'truncated':False}
        self.framefile=self.root/'frame.json'

    def inspect(self, expression, frame=None, **kwargs):
        self.framefile.write_text(json.dumps(frame or self.frame))
        kind=kwargs.pop('extra_kind',None)
        extra=['--kind',kind] if kind else []
        return self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression',expression,*extra,**kwargs)

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

    def partial(self):
        frame=copy.deepcopy(self.frame);frame['schema']='nex.debug-frame/2';frame['captures']=[]
        for binding in frame['bindings']:
            binding.pop('value',None);binding['unavailable']='not captured'
        return frame

    def demand(self, expression, supply, frame=None):
        frame=frame or self.partial();requests=[]
        for _ in range(30):
            response=self.inspect(expression,frame,extra_kind='demand')
            if response['schema']=='nex.expression/1':return response,requests,frame
            self.assertEqual(response['schema'],'nex.expression-demand/1')
            request=response['request'];requests.append(request)
            capture={k:request[k] for k in ('binding','path','kind')}
            capture['value']=supply(request)
            frame['captures'].append(capture)
        self.fail('demand did not converge')

    def test_partial_large_lengths_and_dynamic_indices_inside_pure_calls(self):
        result,requests,frame=self.demand('model::at(items, len(items) - 1)',
            lambda r:{'length':'1000000000'} if r['kind']=='shape' else '73')
        self.assertEqual(result['value'],'73')
        self.assertEqual([(r['binding'],r['path'],r['kind']) for r in requests],
                         [('items',[],'shape'),('items',[999999999],'value')])
        self.assertEqual(self.inspect('len(items)',frame)['value'],'1000000000')
        self.assertEqual(self.inspect('items',frame,ok=False)['code'],'E_DEBUG_UNAVAILABLE')
        self.assertEqual(self.inspect('items[1000000000]',frame,ok=False)['code'],'E_BOUNDS')
        self.assertEqual(self.inspect('items[-1]',frame,ok=False)['code'],'E_BOUNDS')

    def test_partial_record_fields_and_nested_list_paths(self):
        def supply(r):
            if r['path']==[]:return {'record':'debugging::model::Person'}
            if r['path']==['tags']:return {'length':'500000'}
            if r['path']==['tags',1]:return 'chosen'
            if r['path']==['name']:return 'exact\x00\U0001f30d'
            self.fail(str(r))
        result,requests,_=self.demand('person.tags[1]',supply)
        self.assertEqual(result['value'],'chosen')
        self.assertEqual([r['path'] for r in requests],[[],['tags'],['tags',1]])
        result,requests,_=self.demand('model::name(person)',supply)
        self.assertEqual(result['value'],'exact\x00\U0001f30d')
        self.assertEqual([r['path'] for r in requests],[[],['name']])

    def test_partial_results_do_not_require_unused_payloads(self):
        result,requests,_=self.demand('is_ok(reply)',lambda r:{'ok':True})
        self.assertTrue(result['value']);self.assertEqual(len(requests),1)
        result,requests,_=self.demand('unwrap(reply)',lambda r:{'ok':True} if r['kind']=='shape' else 'hello\x00')
        self.assertEqual(result['value'],'hello\x00');self.assertEqual(requests[-1]['path'],['ok'])
        result,requests,_=self.demand('error_code(failure)',lambda r:{'ok':False} if r['kind']=='shape' else 'BIG')
        self.assertEqual(result['value'],'BIG');self.assertEqual(requests[-1]['path'],['code'])
        self.assertFalse(any(r['path']==['message'] for r in requests))
        frame=self.partial();frame['captures']=[{'binding':'failure','path':[],'kind':'shape','value':{'ok':False}},
            {'binding':'failure','path':['code'],'kind':'value','value':'E'},
            {'binding':'failure','path':['message'],'kind':'value','value':'message'}]
        self.assertEqual(self.inspect('unwrap(failure)',frame,ok=False)['code'],'E_RESULT')

    def test_enum_match_helpers_demand_only_selected_payloads(self):
        self.assertEqual(self.inspect('model::selected(selection)')['value'],'41')
        def supply(request):
            if request['path'] == []: return {'case':'Chosen'}
            if request['path'] == ['Chosen::id']: return '40'
            if request['path'] == ['Chosen::samples']: return {'length':'2'}
            self.fail('unused enum field requested: '+str(request))
        result,requests,frame=self.demand('model::selected(selection)',supply)
        self.assertEqual(result['value'],'42')
        self.assertEqual([r['path'] for r in requests],[[],['Chosen::id'],['Chosen::samples']])
        self.assertEqual(self.inspect('selection',frame,ok=False)['code'],'E_DEBUG_UNAVAILABLE')
        result,requests,_=self.demand('model::selected(selection)',lambda r:{'case':'Empty'})
        self.assertEqual(result['value'],'0');self.assertEqual(len(requests),1)
        bad=self.partial();bad['captures']=[{'binding':'selection','path':[],'kind':'shape','value':{'case':'Unknown'}}]
        self.assertEqual(self.inspect('model::selected(selection)',bad,ok=False)['code'],'E_DEBUG_VALUE')

    def test_partial_pure_loops_constructors_aliases_and_short_circuit(self):
        result,requests,_=self.demand('model::first_two(items)',lambda r:{'length':'999999'} if r['kind']=='shape' else str(20+r['path'][0]))
        self.assertEqual(result['value'],'41');self.assertEqual([r['path'] for r in requests],[[],[0],[1]])
        result,requests,_=self.demand('len([person, person])',lambda r:self.fail(str(r)))
        self.assertEqual(result['value'],'2');self.assertEqual(requests,[])
        result,requests,_=self.demand('false && person.id == 7',lambda r:self.fail(str(r)))
        self.assertFalse(result['value']);self.assertEqual(requests,[])
        result,requests,_=self.demand('unwrap(ok(person)).id',lambda r:{'record':'debugging::model::Person'} if r['kind']=='shape' else '7')
        self.assertEqual(result['value'],'7');self.assertEqual([r['path'] for r in requests],[[],['id']])

    def test_partial_frame_rejects_bad_paths_conflicts_duplicates_and_shapes(self):
        frame=self.partial();capture={'binding':'items','path':[],'kind':'shape','value':{'length':'2'}}
        for change in [{'binding':'absent'},{'path':[-1]},{'path':['no']},{'path':[0,0]},{'kind':'other'}]:
            bad=copy.deepcopy(frame);bad['captures']=[dict(capture,**change)]
            self.assertEqual(self.inspect('len(items)',bad,ok=False)['code'],'E_DEBUG_FRAME')
        bad=copy.deepcopy(frame);bad['captures']=[capture,capture]
        self.assertEqual(self.inspect('len(items)',bad,ok=False)['code'],'E_DEBUG_FRAME')
        bad=copy.deepcopy(frame);bad['bindings'][0]={'name':'n','type':'i64','value':'40'}
        bad['captures']=[{'binding':'n','path':[],'kind':'value','value':'41'}]
        self.assertEqual(self.inspect('n',bad,ok=False)['code'],'E_DEBUG_FRAME')
        for value in [{'length':2},{'length':'02'},{'length':'-1'},{'length':'9223372036854775808'},{'length':'2','other':0}]:
            bad=copy.deepcopy(frame);bad['captures']=[dict(capture,value=value)]
            self.assertEqual(self.inspect('len(items)',bad,ok=False)['code'],'E_DEBUG_VALUE')
        bad=copy.deepcopy(frame);bad['captures']=[{'binding':'person','path':[],'kind':'shape','value':{'record':'wrong'}}]
        self.assertEqual(self.inspect('person.id',bad,ok=False)['code'],'E_DEBUG_VALUE')

    def test_partial_unavailable_reads_and_exact_materialization(self):
        frame=self.partial();frame['captures']=[{'binding':'items','path':[],'kind':'shape','value':{'length':'3'}},
            {'binding':'items','path':[0],'kind':'value','unavailable':'unreadable selected child'}]
        self.assertEqual(self.inspect('items[0]',frame,ok=False)['code'],'E_DEBUG_UNAVAILABLE')
        self.assertEqual(self.inspect('false && items[0] == 0',frame)['value'],False)
        frame['captures'][1]={'binding':'items','path':[0],'kind':'value','value':3}
        self.assertEqual(self.inspect('items[0]',frame,ok=False)['code'],'E_DEBUG_VALUE')
        result,requests,_=self.demand('encode_json(push(items, 9))',lambda r:['1','2'])
        self.assertEqual(result['value'],'["1","2","9"]');self.assertEqual(len(requests),1)
        self.assertEqual(requests[0]['kind'],'value');self.assertEqual(requests[0]['path'],[])

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

    def test_large_fixture_projection_agrees_in_native_typescript_and_interpreter(self):
        source=(harness.REPO/'examples/debugging/large.nex').read_text()
        source=source.replace('print(report.id); // break: large',
            'print(report.id); print(len(samples)); print(last(report.samples)); print(error_code(failure)); print(len(unwrap(reply).samples));')
        self.file.write_text(source)
        interpreted=self.cli('eval')['stdout']
        self.assertEqual(interpreted,'7\n32768\nleaf\x00\U0001f30d\nBULK\n32768\n')
        self.assertEqual(self.cli('run')['stdout'],interpreted)
        folder=self.root/'large-ts';self.cli('emit','--kind','typescript','--directory',folder)
        (folder/'package.json').write_text('{"type":"module"}')
        (folder/'watch.ts').write_text("import {entry} from './program.ts';entry();")
        actual=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(folder/'watch.ts')],capture_output=True,text=True,timeout=30)
        self.assertEqual(actual.returncode,0,actual.stderr);self.assertEqual(actual.stdout,interpreted)


if LIVE:
    class LiveExpressions(harness.ToolchainCase):
        def test_live_enum_patterns_partial_reads_and_dap_children(self):
            self.source('''module live_enum;
enum Selection { Empty; Chosen(id:i64, unused:i64, samples:list<str>); }
fn selected(value:Selection) -> i64 { match value { Selection::Empty() => {return 0;} Selection::Chosen(n,unused,samples) => {return n + len(samples);} } }
fn observe(selection:Selection) -> unit !{io} {
 match selection {
  Selection::Empty() => {},
  Selection::Chosen(n,_,samples) => {
   print(n); // break: enum
   print(len(samples));
  }
 }
}
fn main() -> unit !{io} { var samples:list<str> = ["leaf"]; var i:i64 = 0; while i < 15 {samples = samples + samples; i = i + 1;} observe(Selection::Chosen(40,999,samples)); }
''')
            session=self.cli('debug','--kind','nex-dap');manifest=json.loads(Path(session['manifest']).read_text())
            projected=manifest['sources'][0]['projection'];line=next(i+1 for i,s in enumerate(self.file.read_text().splitlines()) if '// break: enum' in s)
            report=self.root/'enum-watch.json';script=self.root/'enum_watch.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE);process=target.LaunchSimple(None,None,None)
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID();handle=frame.FindVariable('selection').GetValueAsUnsigned()
  def command(text):
   result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
   assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
   return json.loads(result.GetOutput())
  result={'value':command('nex-eval selected(selection)'), 'pattern':command('nex-eval n'), 'snapshot':command('nex-frame selected(selection)')}
  assert process.GetStopID()==stop and frame.FindVariable('selection').GetValueAsUnsigned()==handle
  with open(REPORT,'w') as output:json.dump(result,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),output.stdout+output.stderr);result=json.loads(report.read_text())
            self.assertEqual(result['value']['value'],'32808');self.assertEqual(result['pattern']['value'],'40')
            self.assertEqual([c['path'] for c in result['snapshot']['captures']],[[],['Chosen::id'],['Chosen::samples']])
            framefile=self.root/'snapshot.json';framefile.write_text(json.dumps(result['snapshot']))
            self.assertEqual(self.cli('inspect',framefile,'--manifest',session['manifest'],'--expression','selected(selection)')['value'],'32808')
            from debugging import DAP
            client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
                client.request('configurationDone');client.response(pending);stop=client.event('stopped')
                frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
                def evaluate(expression):return client.request('evaluate',{'expression':expression,'frameId':frame,'context':'watch'})
                self.assertEqual(evaluate('selected(selection)')['nex']['value'],'32808')
                value=evaluate('Selection::Chosen(n,0,[])');self.assertEqual(value['namedVariables'],4)
                children=client.request('variables',{'variablesReference':value['variablesReference'],'start':0,'count':2})['variables']
                self.assertEqual([(v['name'],v['value']) for v in children],[('<case>','"Chosen"'),('id','40')])
                client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()

        def large(self):
            shutil.copyfile(harness.REPO/'examples/debugging/large.nex',self.file)
            session=self.cli('debug','--kind','nex-dap');manifest=json.loads(Path(session['manifest']).read_text())
            source=manifest['sources'][0]['projection']
            line=next(i+1 for i,s in enumerate(self.file.read_text().splitlines()) if '// break: large' in s)
            return session,source,line

        def test_large_live_paths_skip_siblings_and_preserve_offline_snapshot(self):
            session,source,line=self.large();report=self.root/'large-watch.json';script=self.root/'large_watch.py'
            script.write_text('''import json,lldb

def __lldb_init_module(debugger, _):
    debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
    target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
    process=target.LaunchSimple(None,None,None)
    def command(text,success=True):
        r=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,r)
        assert r.Succeeded()==success,(text,r.GetOutput(),r.GetError())
        return json.loads(r.GetOutput() if success else r.GetError().removeprefix('error: '))
    try:
        assert process.GetState()==lldb.eStateStopped
        stop=process.GetStopID();frame=process.GetSelectedThread().GetSelectedFrame()
        handle=frame.FindVariable('samples').GetValueAsUnsigned()
        import lldb_nex
        data=lldb_nex._data(frame.FindVariable('samples'))
        unreadable=data.CreateValueFromAddress('unreadable',1,data.GetType())
        try:lldb_nex._ExactVector(unreadable)
        except ValueError:pass
        else:raise AssertionError('unreadable vector became an empty list')
        result={expression:command('nex-eval '+expression) for expression in
            ['len(samples)','report.id','last(report.samples)','is_ok(reply)','len(unwrap(reply).samples)','error_code(failure)']}
        result['snapshot']=command('nex-frame last(report.samples)')
        result['whole_list']=command('nex-eval samples',False)
        result['whole_message']=command('nex-eval error_message(failure)',False)
        assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
        assert frame.FindVariable('samples').GetValueAsUnsigned()==handle
        with open(REPORT,'w') as output:json.dump(result,output)
        process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
    finally:
        if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(source)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False)
            self.assertTrue(report.is_file(),output.stdout+output.stderr);result=json.loads(report.read_text())
            self.assertEqual([result[e]['value'] for e in ['len(samples)','report.id','last(report.samples)','is_ok(reply)','len(unwrap(reply).samples)','error_code(failure)']],
                             ['32768','7','leaf\x00\U0001f30d',True,'32768','BULK'])
            self.assertEqual(result['whole_list']['code'],'E_DEBUG_UNAVAILABLE')
            self.assertEqual(result['whole_message']['code'],'E_DEBUG_UNAVAILABLE')
            snapshot=result['snapshot'];self.assertEqual(snapshot['schema'],'nex.debug-frame/2')
            self.assertEqual([(c['binding'],c['path'],c['kind']) for c in snapshot['captures']],
                [('report',[],'shape'),('report',['samples'],'shape'),('report',['samples',32767],'value')])
            self.assertLess(len(json.dumps(snapshot)),8192)
            self.file.unlink();framefile=self.root/'partial.json';framefile.write_text(json.dumps(snapshot))
            offline=self.cli('inspect',framefile,'--manifest',session['manifest'],'--expression','last(report.samples)')
            self.assertEqual(offline['value'],'leaf\x00\U0001f30d')
            self.assertEqual(offline['stop'],result['last(report.samples)']['stop'])

        def test_large_actual_dap_watches_and_small_computed_pages(self):
            from debugging import DAP
            session,source,line=self.large();client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':source},'breakpoints':[{'line':line}]})
                client.request('configurationDone');client.response(pending);stop=client.event('stopped')
                stack=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames']
                def evaluate(expression):return client.request('evaluate',{'expression':expression,'frameId':stack[0]['id'],'context':'watch'})
                last=evaluate('last(report.samples)');self.assertEqual(last['nex']['value'],'leaf\x00\U0001f30d')
                self.assertEqual(len(last['nex']['read_paths']),3)
                sizes=evaluate('[len(samples), len(unwrap(reply).samples)]')
                self.assertEqual(sizes['nex']['value'],['32768','32768'])
                page=client.request('variables',{'variablesReference':sizes['variablesReference'],'start':1,'count':1})['variables']
                self.assertEqual([(v['name'],v['value'],v['type']) for v in page],[('[1]','32768','i64')])
                self.assertEqual(evaluate('error_code(failure)')['nex']['value'],'BULK')
                self.assertEqual(evaluate('report.id')['nex']['stop'],last['nex']['stop'])
                client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()

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
