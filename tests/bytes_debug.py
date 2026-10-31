"""Exact binary watches, selected octet reads, and real LLDB/DAP stops."""
import base64
import copy
import json
from pathlib import Path
import sys
import unittest

LIVE = '--live' in sys.argv
if LIVE:
    sys.argv.remove('--live')
import support as harness


SOURCE = '''module binary_debug;
fn make(data:bytes)->(fn(i64)->i64){return fn(index:i64)->i64{return data[index];};}
fn observe(data:bytes,small:bytes,callback:fn(i64)->i64,alias:fn(i64)->i64)->unit!{io}{
 print(len(data)); // BINARY_STOP
 print(small[1]);print(callback(1));print(alias(2));
}
fn main()->unit!{io}{
 let owner:bytes=unwrap(bytes([7,0,255,128,65,9]));
 let small:bytes=slice(owner,1,4);
 let callback:fn(i64)->i64=make(small);
 var data:bytes=utf8_bytes("x");var i:i64=0;
 while i<22{data=data+data;i=i+1;}
 observe(set(data,len(data)-1,255),small,callback,callback);
}
'''


def encoded(value):
    return base64.b64encode(bytes(value)).decode('ascii')


class BinaryFrame(harness.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.source(SOURCE)
        self.session = self.cli('debug')
        self.manifest = Path(self.session['manifest'])
        self.identity = json.loads(self.manifest.read_text())
        self.framefile = self.root/'frame.json'
        self.frame = {
            'schema': 'nex.debug-frame/1', 'language': self.identity['language'],
            'revision': self.identity['revision'], 'build_key': self.identity['build_key'],
            'function': 'binary_debug::observe',
            'stop': {'process_id': '100', 'thread_id': '101', 'frame_id': 0, 'stop_id': '1'},
            'bindings': [{'name': name, 'type': kind, 'unavailable': 'not captured'}
                         for name, kind in [('data', 'bytes'), ('small', 'bytes'),
                                            ('callback', 'fn(i64)->i64'), ('alias', 'fn(i64)->i64')]],
            'truncated': False}
        self.shape = {'function': 'binary_debug::make::$lambda_0', 'identity': '10001'}
        self.binary = encoded([0, 255, 128, 65])

    def inspect(self, expression, frame=None, kind=None, **kwargs):
        self.framefile.write_text(json.dumps(frame if frame is not None else self.frame), newline="\n")
        return self.cli('inspect', self.framefile, '--manifest', self.manifest,
                        '--expression', expression, *(['--kind', kind] if kind else []), **kwargs)

    def full(self):
        frame = copy.deepcopy(self.frame)
        for binding in frame['bindings']:
            binding.pop('unavailable')
            binding['value'] = (self.binary if binding['type'] == 'bytes' else
                                dict(self.shape, captures={'data': self.binary}))
        return frame

    def partial(self):
        return dict(copy.deepcopy(self.frame), schema='nex.debug-frame/2', captures=[])

    def demand(self, expression, supply, frame=None):
        frame = self.partial() if frame is None else frame
        requests = []
        for _ in range(30):
            result = self.inspect(expression, frame, kind='demand')
            if result['schema'] == 'nex.expression/1':
                return result, requests, frame
            self.assertEqual(result['schema'], 'nex.expression-demand/1')
            request = result['request']; requests.append(request)
            frame['captures'].append(dict(
                {key: request[key] for key in ('binding', 'path', 'kind')}, value=supply(request)))
        self.fail('Binary demands did not converge')


class BinaryDebug(BinaryFrame):
    def test_exact_wire_operations_and_nested_values(self):
        frame = self.full()
        cases = [('len(small)', '4'), ('small[1]', '255'),
                 ('slice(small,1,2)', encoded([255, 128])),
                 ('set(small,0,17)', encoded([17, 255, 128, 65])),
                 ('push(small,9)', encoded([0, 255, 128, 65, 9])),
                 ('small+small', encoded([0, 255, 128, 65]*2)),
                 ('[ok(small)]', [{'ok': self.binary}]),
                 ('unwrap(decode_json<bytes>(encode_json(small)))', self.binary),
                 ('error_code(decode_utf8(small))', 'E_UTF8'),
                 ('callback(1)', '255'), ('callback == alias', True)]
        for expression, value in cases:
            with self.subTest(expression=expression):
                result = self.inspect(expression, frame)
                self.assertEqual(result['value'], value)
                self.assertEqual(result['stop'], self.frame['stop'])
        self.assertEqual(self.inspect('small', frame)['wire_schema']['root'], 'bytes')
        self.assertEqual(json.loads(self.framefile.read_text()), frame)

    def test_noncanonical_wire_values_are_rejected(self):
        for value in ['AA', 'AB==', '_w==', 'AA===', 'AA==\n', 42, [], {'bytes': 'AA=='}]:
            with self.subTest(value=value):
                frame = self.full(); frame['bindings'][1]['value'] = value
                self.assertEqual(self.inspect('small', frame, ok=False)['code'], 'E_DEBUG_VALUE')
        frame = self.full(); frame['bindings'][1]['value'] = ''
        self.assertEqual(self.inspect('len(small)', frame)['value'], '0')

    def test_large_length_index_and_slice_need_only_selected_octets(self):
        size = 4194304
        def supply(request):
            if request['kind'] == 'shape':
                return {'length': str(size)}
            return '255' if request['path'] == [size-1] else '120'
        value, requests, frame = self.demand('data[len(data)-1]', supply)
        self.assertEqual(value['value'], '255')
        self.assertEqual([(r['path'], r['kind']) for r in requests],
                         [([], 'shape'), ([size-1], 'value')])
        self.assertEqual(self.inspect('data', frame, ok=False)['code'], 'E_DEBUG_UNAVAILABLE')
        value, requests, _ = self.demand('slice(data,len(data)-3,3)', supply)
        self.assertEqual(value['value'], encoded([120, 120, 255]))
        self.assertEqual([r['path'] for r in requests], [[], [size-3], [size-2], [size-1]])
        value, requests, _ = self.demand('slice(data,len(data),0)', supply)
        self.assertEqual(value['value'], '')
        self.assertEqual([r['path'] for r in requests], [[]])
        value, requests, _ = self.demand('false && data[0]==0', self.fail)
        self.assertFalse(value['value']); self.assertEqual(requests, [])

    def test_slice_capture_budget_and_bounded_whole_capture(self):
        frame = self.partial()
        frame['captures'] = [{'binding': 'data', 'path': [], 'kind': 'shape',
                              'value': {'length': '1000'}}]
        frame['captures'] += [{'binding': 'data', 'path': [i], 'kind': 'value', 'value': str(i)}
                              for i in range(255)]
        self.assertEqual(self.inspect('slice(data,0,255)', frame)['value'], encoded(range(255)))
        frame['captures'] = frame['captures'][:1]
        self.assertEqual(self.inspect('slice(data,0,256)', frame, ok=False)['code'], 'E_DEBUG_LIMIT')
        frame = self.full(); frame['bindings'][0]['value'] = encoded([42]*300)
        self.assertEqual(self.inspect('slice(data,0,300)', frame)['value'], encoded([42]*300))

    def test_partial_ranges_octets_and_paths_are_checked(self):
        frame = self.partial()
        frame['captures'] = [{'binding': 'data', 'path': [], 'kind': 'shape', 'value': {'length': '4'}}]
        for expression in ['data[-1]', 'data[4]', 'slice(data,3,2)', 'slice(data,0,-1)']:
            self.assertEqual(self.inspect(expression, frame, ok=False)['code'], 'E_BOUNDS')
        for value in ['-1', '256', True, 255]:
            with self.subTest(value=value):
                candidate = copy.deepcopy(frame)
                candidate['captures'].append({'binding': 'data', 'path': [1], 'kind': 'value', 'value': value})
                self.assertEqual(self.inspect('data[1]', candidate, ok=False)['code'], 'E_DEBUG_VALUE')
        for length in ['-1', '01', '9223372036854775808', 4]:
            candidate = copy.deepcopy(frame); candidate['captures'][0]['value']['length'] = length
            self.assertEqual(self.inspect('len(data)', candidate, ok=False)['code'], 'E_DEBUG_VALUE')
        candidate = copy.deepcopy(frame)
        candidate['captures'].append({'binding': 'data', 'path': ['1'], 'kind': 'value', 'value': '255'})
        self.assertEqual(self.inspect('data[1]', candidate, ok=False)['code'], 'E_DEBUG_FRAME')

    def test_aliased_callable_whole_and_selected_binary_captures_must_agree(self):
        frame = self.full(); frame['schema'] = 'nex.debug-frame/2'
        alias = frame['bindings'][-1]; alias.pop('value'); alias['unavailable'] = 'not captured'
        frame['captures'] = [
            {'binding': 'alias', 'path': [], 'kind': 'shape', 'value': dict(self.shape)},
            {'binding': 'alias', 'path': ['data'], 'kind': 'shape', 'value': {'length': '4'}},
            {'binding': 'alias', 'path': ['data', 1], 'kind': 'value', 'value': '255'}]
        for expression in ['callback(1)==alias(1)', 'alias(1)==callback(1)']:
            self.assertTrue(self.inspect(expression, frame)['value'])
            bad = copy.deepcopy(frame); bad['captures'][-1]['value'] = '254'
            self.assertEqual(self.inspect(expression, bad, ok=False)['code'], 'E_DEBUG_VALUE')

    def test_snapshot_replay_uses_archived_sources_and_preserves_graph(self):
        revision = self.cli('graph')['revision']
        self.file.unlink()
        self.assertEqual(self.inspect('callback(1)', self.full())['value'], '255')
        self.assertEqual(self.cli('graph')['revision'], revision)


if LIVE:
    class LiveBinaryDebug(BinaryFrame):
        def test_lldb_dap_bounded_reads_readonly_pages_and_source_deleted_replay(self):
            session = self.cli('debug', '--kind', 'nex-dap')
            projected = self.identity['sources'][0]['projection']
            line = next(i+1 for i, text in enumerate(SOURCE.splitlines()) if '// BINARY_STOP' in text)
            report, script = self.root/'binary-watch.json', self.root/'binary_watch.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID()
  handle=frame.FindVariable('data').GetValueAsUnsigned()
  result={'index':command('nex-eval data[len(data)-1]'),
          'slice':command('nex-eval slice(data,len(data)-3,3)'),
          'snapshot':command('nex-frame data[len(data)-1]'),
          'small':command('nex-eval small'),
          'callback':command('nex-eval callback(1)'),
          'alias':command('nex-eval alias(2)'),
          'whole_snapshot':command('nex-frame data'),
          'previews':command('nex-values')}
  small=frame.FindVariable('small').GetSyntheticValue()
  result['children']=[small.GetChildAtIndex(i).GetValueAsSigned() for i in range(small.GetNumChildren())]
  assert process.GetStopID()==stop and frame.FindVariable('data').GetValueAsUnsigned()==handle
  with open(REPORT,'w') as output:json.dump(result,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE', repr(projected)).replace('LINE', str(line)).replace('REPORT', repr(str(report))), newline="\n")
            output = self.cli('debug', '--', '--no-lldbinit', '--batch', '-o',
                              'command script import '+json.dumps(str(script)), machine=False, timeout=120)
            self.assertTrue(report.is_file(), output.stdout+output.stderr)
            result = json.loads(report.read_text())
            self.assertEqual(result['index']['value'], '255')
            self.assertEqual(result['slice']['value'], encoded([120, 120, 255]))
            self.assertEqual(result['small']['value'], self.binary)
            self.assertEqual(result['callback']['value'], '255')
            self.assertEqual(result['alias']['value'], '128')
            self.assertEqual(result['children'], [0, 255, 128, 65])
            self.assertEqual([c['path'] for c in result['snapshot']['captures']], [[], [4194303]])
            whole = result['whole_snapshot']['captures']
            self.assertEqual(len(whole), 1)
            self.assertIn('encoded byte budget', whole[0]['unavailable'])
            self.assertIn('bytes[4194304]', json.dumps(result['previews']))
            self.file.unlink()
            snapshot = self.root/'snapshot.json'; snapshot.write_text(json.dumps(result['snapshot']), newline="\n")
            self.assertEqual(self.cli('inspect', snapshot, '--manifest', self.manifest,
                                     '--expression', 'data[len(data)-1]')['value'], '255')
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
                self.assertEqual(evaluate('data[len(data)-1]')['nex']['value'], '255')
                value = evaluate('slice(data,len(data)-3,3)')
                self.assertEqual(value['type'], 'bytes'); self.assertEqual(value['indexedVariables'], 3)
                reference = value['variablesReference']
                children = client.request('variables', {'variablesReference': reference,
                    'filter': 'indexed', 'start': 1, 'count': 2})['variables']
                self.assertEqual([(v['name'], v['value'], v['type']) for v in children],
                                 [('[1]', '120', 'i64'), ('[2]', '255', 'i64')])
                self.assertTrue(all('readOnly' in v['presentationHint']['attributes'] for v in children))
                self.assertEqual(client.request('variables', {'variablesReference': reference,
                    'filter': 'named'})['variables'], [])
                with self.assertRaises(RuntimeError):
                    client.request('setVariable', {'variablesReference': reference, 'name': '[1]', 'value': '0'})
                client.request('continue', {'threadId': stopped['threadId']})
                self.assertEqual(client.event('exited')['exitCode'], 0)
                with self.assertRaisesRegex(RuntimeError, 'expired|unknown'):
                    client.request('variables', {'variablesReference': reference})
            finally:
                client.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
