"""Callable watches over checked full/partial native snapshots."""
import copy
import json
from pathlib import Path
import sys
import unittest
LIVE = '--live' in sys.argv
if LIVE:
    sys.argv.remove('--live')
import support as harness


SOURCE = '''module callable_debug;
enum Payload { Pick(number:i64,large:list<str>); Empty; }
fn make(payload:Payload,offset:i64)->(fn(bool)->i64){
 return fn(positive:bool)->i64{
  if positive {return match payload {Payload::Pick(n,_)=>n+offset,Payload::Empty()=>offset};}
  return -offset;
 };
}
fn alternate(positive:bool)->i64{if positive{return 42;}return -2;}
fn uncompiled(positive:bool)->i64{if positive{return 999;}return 0;}
fn noisy(positive:bool)->i64!{io}{print(999);return 999;}
server fn remote(positive:bool)->i64{return 777;}
fn generic<T:wire>(value:T)->(fn()->T){
 return fn()->T{
  return unwrap(decode_json<T>(encode_json(value))); // GENERIC_STOP
 };
}
fn wrap(next:fn()->i64)->(fn()->i64){return fn()->i64{return next();};}
fn observe(callback:fn(bool)->i64,alias:fn(bool)->i64,number:i64,thunk:fn()->i64,large:fn(bool)->i64)->unit!{io}{
 print(callback(true)); // WATCH_STOP
 print(alias(false)+number);
 print(thunk());
}
server fn main()->unit!{io}{
 let callback:fn(bool)->i64=make(Payload::Pick(40,["unread"]),2);
 let other:fn(bool)->i64=alternate;
 let loud:fn(bool)->i64!{io}=noisy;
 let distant:server fn(bool)->i64=remote;
 print(other(true));print(loud(true));print(distant(true));
 var bulk:list<str>=["unread"];var i:i64=0;
 while i<15{bulk=bulk+bulk;i=i+1;}
 observe(callback,callback,40,wrap(generic(42)),make(Payload::Pick(40,bulk),2));
}
'''


class CallableFrame(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.source(SOURCE)
        self.session = self.cli('debug')
        self.manifest = Path(self.session['manifest'])
        self.identity = json.loads(self.manifest.read_text())
        self.frame = {
            'schema': 'nex.debug-frame/1', 'language': self.identity['language'],
            'revision': self.identity['revision'], 'build_key': self.identity['build_key'],
            'function': 'callable_debug::observe',
            'stop': {'process_id': '100', 'thread_id': '101', 'frame_id': 0, 'stop_id': '1'},
            'bindings': [
                {'name': n, 'type': t, 'unavailable': 'not captured'} for n, t in
                [('callback', 'fn(bool)->i64'), ('alias', 'fn(bool)->i64'),
                 ('number', 'i64'), ('thunk', 'fn()->i64')]], 'truncated': False}
        self.framefile = self.root/'frame.json'
        self.schema = self.inspect('callback', kind='plan')['variables'][0]['wire_schema']
        self.target = next(n for n, t in self.schema['targets'].items()
                           if {c['name'] for c in t['captures']} == {'payload', 'offset'})
        self.shape = {'function': self.target, 'identity': '10001'}
        self.value = dict(self.shape, captures={
            'payload': {'case': 'Pick', 'fields': {'number': '40', 'large': ['unread']}},
            'offset': '2'})

    def inspect(self, expression, frame=None, kind=None, steps=None, **kwargs):
        self.framefile.write_text(json.dumps(frame if frame is not None else self.frame), newline="\n")
        extra = ['--kind', kind] if kind else []
        if steps is not None:
            extra += ['--steps', str(steps)]
        return self.cli('inspect', self.framefile, '--manifest', self.manifest,
                        '--expression', expression, *extra, **kwargs)

    def full(self, callback=None, alias=None):
        frame = copy.deepcopy(self.frame)
        for b in frame['bindings']:
            if b['name'] in ('callback', 'alias'):
                b.pop('unavailable')
                b['value'] = copy.deepcopy(callback if b['name'] == 'callback' else alias)
                if b['value'] is None:
                    b['value'] = copy.deepcopy(self.value)
            elif b['name'] == 'number':
                b.pop('unavailable'); b['value'] = '40'
        return frame

    def partial(self):
        frame = copy.deepcopy(self.frame)
        frame['schema'] = 'nex.debug-frame/2'; frame['captures'] = []
        return frame

    def supply(self, request):
        path, kind = request['path'], request['kind']
        if path == [] and kind == 'shape':
            return copy.deepcopy(self.shape)
        if path == [] and kind == 'value':
            return copy.deepcopy(self.value)
        if path == ['offset']:
            return '2'
        if path == ['payload']:
            return {'case': 'Pick'} if kind == 'shape' else self.value['captures']['payload']
        if path == ['payload', 'Pick::number']:
            return '40'
        self.fail('Unexpected read: ' + str(request))

    def demand(self, expression, frame=None, supply=None):
        frame = frame if frame is not None else self.partial()
        requests = []
        for _ in range(30):
            result = self.inspect(expression, frame, kind='demand')
            if result['schema'] == 'nex.expression/1':
                return result, requests, frame
            self.assertEqual(result['schema'], 'nex.expression-demand/1')
            request = result['request']; requests.append(request)
            frame['captures'].append(dict(
                {k: request[k] for k in ('binding', 'path', 'kind')},
                value=(supply or self.supply)(request)))
        self.fail('Callable watch demands did not converge')


class FunctionDebug(CallableFrame):
    def test_schema_and_full_values_are_checked_separately_from_application_json(self):
        self.assertEqual(self.schema['schema'], 'nex.debug-wire/1')
        self.assertTrue(self.schema['targets'][self.target]['compiled'])
        self.assertFalse(self.schema['targets']['callable_debug::uncompiled']['compiled'])
        result = self.inspect('callback(true)', self.full())
        self.assertEqual(result['value'], '42')
        result = self.inspect('callback', self.full())
        self.assertEqual(result['value'], self.value)
        self.assertEqual(result['wire_schema']['schema'], 'nex.debug-wire/1')
        self.assertEqual(self.inspect('encode_json(callback)', self.full(), ok=False)['code'], 'E_GENERIC_BOUND')

    def test_lazy_calls_read_only_selected_captures_and_payload_fields(self):
        result, requests, _ = self.demand('callback(false)')
        self.assertEqual(result['value'], '-2')
        self.assertEqual([(r['path'], r['kind']) for r in requests], [([], 'shape'), (['offset'], 'value')])
        result, requests, frame = self.demand('callback(true)')
        self.assertEqual(result['value'], '42')
        self.assertEqual([(r['path'], r['kind']) for r in requests],
                         [([], 'shape'), (['payload'], 'shape'),
                          (['payload', 'Pick::number'], 'value'), (['offset'], 'value')])
        self.assertEqual(self.inspect('callback', frame, ok=False)['code'], 'E_DEBUG_UNAVAILABLE')
        result, requests, _ = self.demand('callback', frame)
        self.assertEqual(result['value'], self.value)
        self.assertTrue(requests)

    def test_alias_identity_equality_requires_no_environment(self):
        result, requests, _ = self.demand('callback == alias')
        self.assertTrue(result['value'])
        self.assertEqual([(r['binding'], r['path'], r['kind']) for r in requests],
                         [('callback', [], 'shape'), ('alias', [], 'shape')])
        result, _, _ = self.demand('callback == alias', supply=lambda r:
            dict(self.shape, identity='10002' if r['binding'] == 'alias' else '10001'))
        self.assertFalse(result['value'])
        self.assertTrue(self.inspect('[callback] == [alias]', self.full())['value'])

    def test_conflicting_alias_targets_and_used_capture_values_are_rejected(self):
        other = dict(self.value, function='callable_debug::alternate', captures={})
        self.assertEqual(self.inspect('callback == alias', self.full(alias=other), ok=False)['code'], 'E_DEBUG_VALUE')
        other = copy.deepcopy(self.value); other['captures']['offset'] = '3'
        self.assertEqual(self.inspect('callback(false) == alias(false)', self.full(alias=other), ok=False)['code'], 'E_DEBUG_VALUE')
        frame = self.partial()
        frame['captures'] = [
            {'binding': n, 'path': [], 'kind': 'shape', 'value': dict(self.shape)} for n in ('callback', 'alias')]
        frame['captures'] += [
            {'binding': n, 'path': ['offset'], 'kind': 'value', 'value': v} for n, v in [('callback', '2'), ('alias', '3')]]
        self.assertEqual(self.inspect('callback(false) == alias(false)', frame, ok=False)['code'], 'E_DEBUG_VALUE')

    def test_forged_target_effect_realm_identity_and_capture_layouts_are_rejected(self):
        for name in ['callable_debug::noisy', 'callable_debug::remote',
                     'callable_debug::uncompiled', 'callable_debug::missing']:
            with self.subTest(target=name):
                bad = dict(self.value, function=name)
                result = self.inspect('callback(true)', self.full(callback=bad), ok=False)
                self.assertEqual(result['code'], 'E_DEBUG_VALUE')
        for identity in ['', '0', '01', '-1', '1.0', '18446744073709551616', 'computed:1']:
            with self.subTest(identity=identity):
                bad = dict(self.value, identity=identity)
                self.assertEqual(self.inspect('callback(true)', self.full(callback=bad), ok=False)['code'], 'E_DEBUG_VALUE')
        for captures in [{}, {'offset': '2'}, dict(self.value['captures'], extra='9')]:
            with self.subTest(captures=captures):
                bad = dict(self.value, captures=captures)
                self.assertEqual(self.inspect('callback(true)', self.full(callback=bad), ok=False)['code'], 'E_DEBUG_VALUE')

    def test_watch_created_closures_capture_frames_without_revision_writes(self):
        revision = self.cli('graph')['revision']
        expression = '(fn(extra:i64)->i64{return callback(true)+number+extra;})(2)'
        self.assertEqual(self.inspect(expression, self.full())['value'], '84')
        result = self.inspect('fn(extra:i64)->i64{return number+extra;}', self.full())
        self.assertEqual(result['value']['captures'], {'number': '40'})
        self.assertTrue(result['value']['identity'].startswith('computed:'))
        self.assertFalse(result['wire_schema']['targets'][result['value']['function']]['compiled'])
        self.assertEqual(self.inspect('(fn(x:i64)->(fn()->i64){return fn()->i64{return x+number;};})(2)()', self.full())['value'], '42')
        self.assertEqual(self.cli('graph')['revision'], revision)
        self.file.unlink()
        self.assertEqual(self.inspect('callback(true)', self.full())['value'], '42')
        self.assertEqual(self.cli('graph')['revision'], revision)

    def test_nested_callable_containers_and_full_partial_alias_agreement(self):
        result = self.inspect('[ok(callback),ok(alias)]', self.full())
        self.assertEqual(result['value'], [{'ok': self.value}, {'ok': self.value}])
        frame = self.full(); frame['schema'] = 'nex.debug-frame/2'; frame['captures'] = []
        alias = next(b for b in frame['bindings'] if b['name'] == 'alias')
        alias.pop('value'); alias['unavailable'] = 'not captured'
        result, requests, _ = self.demand('callback(false)==alias(false)', frame)
        self.assertTrue(result['value'])
        frame['captures'][-1]['value'] = '3'
        self.assertEqual(self.inspect('callback(false)==alias(false)', frame, ok=False)['code'], 'E_DEBUG_VALUE')

    def test_watch_lambda_body_depth_and_invocation_step_limits(self):
        expression = '(fn()->i64{' + 'if true {'*140 + 'return 42;' + '}'*140 + 'return 0;})()'
        self.assertEqual(self.inspect(expression, ok=False)['code'], 'E_DEBUG_LIMIT')
        self.assertEqual(self.inspect('(fn()->i64{while true {}return 0;})()',
                                     self.full(), steps=50, ok=False)['code'], 'E_LIMIT')

    def test_full_and_partial_callable_cycles_and_large_results_fail_explicitly(self):
        plan = self.inspect('thunk', kind='plan')['variables'][0]['wire_schema']
        target = next(n for n, t in plan['targets'].items()
                      if [c['name'] for c in t['captures']] == ['next'])
        shape = {'function': target, 'identity': '20001'}
        frame = copy.deepcopy(self.frame)
        thunk = next(b for b in frame['bindings'] if b['name'] == 'thunk')
        thunk.pop('unavailable')
        thunk['value'] = dict(shape, captures={'next': dict(shape, captures={'next': None})})
        self.assertEqual(self.inspect('thunk()', frame, ok=False)['code'], 'E_DEBUG_VALUE')
        frame = self.partial()
        frame['captures'] = [
            {'binding': 'thunk', 'path': path, 'kind': 'shape', 'value': dict(shape)}
            for path in [[], ['next']]]
        self.assertEqual(self.inspect('thunk()', frame, ok=False)['code'], 'E_DEBUG_VALUE')
        expression = '(fn()->str{var text:str="x";var i:i64=0;while i<20{text=text+text;i=i+1;}return text;})()'
        self.assertEqual(self.inspect(expression, ok=False)['code'], 'E_DEBUG_LIMIT')

    def test_alias_observation_budget_includes_repeated_long_path_keys(self):
        field = 'children_'+'x'*1015
        self.source('module watchbudget;struct Node{'+field+':list<Node>;n:i64;}'
            'fn make(node:Node)->(fn()->i64){return fn()->i64{return node.n;};}'
            'fn observe(thunk:fn()->i64)->unit!{io}{print(thunk());}'
            'fn main()->unit!{io}{observe(make(Node([],42)));}')
        session = self.cli('debug')
        self.manifest = Path(session['manifest'])
        manifest = json.loads(self.manifest.read_text())
        node = {field: [{field: [], 'n': '42'} for _ in range(500)], 'n': '42'}
        for _ in range(20):
            node = {field: [node], 'n': '42'}
        frame = copy.deepcopy(self.frame)
        frame.update(function='watchbudget::observe', revision=manifest['revision'], build_key=manifest['build_key'])
        frame['bindings'] = [{'name': 'thunk', 'type': 'fn()->i64', 'value': {
            'function': 'watchbudget::make::$lambda_0', 'identity': '30001', 'captures': {'node': node}}}]
        result = self.inspect('thunk()', frame, ok=False)
        self.assertEqual(result['code'], 'E_DEBUG_LIMIT')
        self.assertIn('alias observations', result['message'])


if LIVE:
    class LiveFunctionDebug(CallableFrame):

        def test_native_lldb_dap_lazy_captures_generic_frames_and_offline_replay(self):
            session = self.cli('debug', '--kind', 'nex-dap')
            projected = self.identity['sources'][0]['projection']
            line = next(i+1 for i, s in enumerate(SOURCE.splitlines()) if '// WATCH_STOP' in s)
            generic = next(i+1 for i, s in enumerate(SOURCE.splitlines()) if '// GENERIC_STOP' in s)
            report, script = self.root/'callable-watch.json', self.root/'callable_watch.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();observer=target.BreakpointCreateByLocation(SOURCE,LINE)
 target.BreakpointCreateByLocation(SOURCE,GENERIC)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID()
  handle=frame.FindVariable('callback').GetValueAsUnsigned()
  result={'positive':command('nex-eval callback(true)'), 'negative':command('nex-eval callback(false)'),
          'alias':command('nex-eval callback == alias'), 'nested':command('nex-eval thunk()'),
          'snapshot':command('nex-frame callback(true)'), 'whole':command('nex-eval callback'),
          'large':command('nex-eval large(true)'), 'large_snapshot':command('nex-frame large(true)')}
  assert process.GetStopID()==stop and frame.FindVariable('callback').GetValueAsUnsigned()==handle
  target.BreakpointDelete(observer.GetID());process.Continue()
  assert process.GetState()==lldb.eStateStopped
  result['generic']=command('nex-eval unwrap(decode_json<T>(encode_json(value)))')
  result['generic_lambda']=command('nex-eval (fn()->T{return value;})()')
  with open(REPORT,'w') as output:json.dump(result,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE', repr(projected)).replace('LINE', str(line))
                .replace('GENERIC', str(generic)).replace('REPORT', repr(str(report))), newline="\n")
            output = self.cli('debug', '--', '--no-lldbinit', '--batch', '-o',
                              'command script import '+json.dumps(str(script)), machine=False)
            self.assertTrue(report.is_file(), output.stdout+output.stderr)
            result = json.loads(report.read_text())
            for key in ('positive', 'nested', 'generic', 'generic_lambda', 'large'):
                self.assertEqual(result[key]['value'], '42', key)
            self.assertEqual(result['negative']['value'], '-2')
            self.assertTrue(result['alias']['value'])
            self.assertEqual({tuple(r['path']) for r in result['negative']['read_paths']}, {(), ('offset',)})
            self.assertEqual(result['whole']['value']['function'], self.target)
            self.assertEqual(result['whole']['value']['captures']['offset'], '2')
            self.assertFalse(any('large' in c['path'] for c in result['snapshot']['captures']))
            self.assertEqual([c['path'] for c in result['large_snapshot']['captures']],
                             [[], ['payload'], ['payload', 'Pick::number'], ['offset']])
            self.file.unlink()
            snapshot = self.root/'snapshot.json'; snapshot.write_text(json.dumps(result['snapshot']), newline="\n")
            self.assertEqual(self.cli('inspect', snapshot, '--manifest', self.manifest,
                                     '--expression', 'callback(true)')['value'], '42')
            from debugging import DAP
            client = DAP(session['adapter_command'], self.root)
            try:
                client.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path',
                    'linesStartAt1': True, 'supportsVariablePaging': True})
                pending = client.send('launch', dict(session['launch'], disableASLR=False))
                client.event('initialized')
                client.request('setBreakpoints', {'source': {'path': projected}, 'breakpoints': [{'line': line}]})
                client.request('configurationDone'); client.response(pending)
                stopped = client.event('stopped')
                frame = client.request('stackTrace', {'threadId': stopped['threadId']})['stackFrames'][0]['id']
                def evaluate(expression):
                    return client.request('evaluate', {'expression': expression, 'frameId': frame, 'context': 'watch'})
                self.assertEqual(evaluate('callback(true)')['nex']['value'], '42')
                self.assertEqual(evaluate('thunk()')['nex']['value'], '42')
                self.assertEqual(evaluate('large(true)')['nex']['value'], '42')
                value = evaluate('callback')
                self.assertEqual(value['namedVariables'], 3)
                fields = self.schema['targets'][self.target]['captures']
                index = next(i+1 for i, f in enumerate(fields) if f['name'] == 'offset')
                children = client.request('variables', {'variablesReference': value['variablesReference'],
                    'start': index, 'count': 1})['variables']
                self.assertEqual([(v['name'], v['value']) for v in children], [('offset', '2')])
                target = client.request('variables', {'variablesReference': value['variablesReference'],
                    'start': 0, 'count': 1})['variables'][0]
                self.assertEqual(target['name'], '<target>')
                self.assertEqual(json.loads(target['value']), self.target)
                client.request('continue', {'threadId': stopped['threadId']})
                self.assertEqual(client.event('exited')['exitCode'], 0)
                with self.assertRaisesRegex(RuntimeError, 'expired|unknown'):
                    client.request('variables', {'variablesReference': value['variablesReference']})
            finally:
                client.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
