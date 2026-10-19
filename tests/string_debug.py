"""Unicode scalar windows in offline snapshots and actual LLDB/DAP stops."""
import copy
import json
from pathlib import Path
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness

SOURCE=(harness.REPO/'examples/debugging/strings.nex').read_text()


class StringFrames(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.source(SOURCE);self.session=self.cli('debug');self.manifest=Path(self.session['manifest']);self.identity=json.loads(self.manifest.read_text());self.framefile=self.root/'frame.json'
        self.frame={'schema':'nex.debug-frame/2','language':self.identity['language'],'revision':self.identity['revision'],'build_key':self.identity['build_key'],'function':'string_debug::observe','stop':{'process_id':'100','thread_id':'101','frame_id':0,'stop_id':'1'},'bindings':[{'name':n,'type':t,'unavailable':'not captured'} for n,t in [('text','str'),('box','string_debug::Box'),('reply','result<str>'),('failure','result<i64>'),('callback','fn(i64,i64)->str'),('alias','fn(i64,i64)->str')]],'truncated':False,'captures':[]}
        self.shape={'function':'string_debug::make::$lambda_0','identity':'12345'};self.size=1000000000

    def inspect(self,expression,frame=None,kind=None,**kw):
        self.framefile.write_text(json.dumps(frame if frame is not None else self.frame))
        return self.cli('inspect',self.framefile,'--manifest',self.manifest,'--expression',expression,*(['--kind',kind] if kind else []),**kw)

    def supply(self,request):
        binding,path,kind=request['binding'],request['path'],request['kind']
        if kind=='shape':
            if not path and binding in ('callback','alias'):return dict(self.shape)
            if not path and binding=='box':return {'record':'string_debug::Box'}
            if not path and binding in ('reply','failure'):return {'ok':binding=='reply'}
        text={('box',('label',)):'box 🌍\0',('reply',('ok',)):'ok🌍\0',('failure',('code',)):'E🌍',('failure',('message',)):'failure 🌍\0'}.get((binding,tuple(path)))
        length=len(text) if text is not None else self.size
        if kind=='shape':return {'length':str(length)}
        self.assertEqual(kind,'text_range','a partial string was materialized whole')
        start,count=int(request['start']),int(request['count'])
        return text[start:start+count] if text is not None else ''.join('A🌍\0λ'[(start+i)%4] for i in range(count))

    def demand(self,expression,supply=None,frame=None):
        frame=copy.deepcopy(self.frame if frame is None else frame);requests=[]
        for _ in range(32):
            response=self.inspect(expression,frame,kind='demand')
            if response['schema']=='nex.expression/1':return response,requests,frame
            self.assertEqual(response['schema'],'nex.expression-demand/1');request=response['request'];requests.append(request)
            capture={k:request[k] for k in ('binding','path','kind','start','count') if k in request};capture['value']=(supply or self.supply)(request);frame['captures'].append(capture)
        self.fail('string demands did not converge')

    def shaped(self,size=None):
        frame=copy.deepcopy(self.frame);frame['captures']=[{'binding':'text','path':[],'kind':'shape','value':{'length':str(self.size if size is None else size)}}];return frame

    def window(self,start,count,value,binding='text',path=None):
        return {'binding':binding,'path':path or [],'kind':'text_range','start':str(start),'count':str(count),'value':value}

    def test_length_uses_only_scalar_shape_for_a_large_string(self):
        value,requests,_=self.demand('len(text)');self.assertEqual(value['value'],'1000000000')
        self.assertEqual([(r['path'],r['kind']) for r in requests],[([], 'shape')])

    def test_dynamic_index_and_pure_call_slice_are_exact_scalar_windows(self):
        value,requests,_=self.demand('text[len(text)-1]');self.assertEqual(value['value'],'λ')
        self.assertEqual([(r['kind'],r.get('start'),r.get('count')) for r in requests],[('shape',None,None),('text_range','999999999','1')])
        value,requests,_=self.demand('callback(len(text)-3,3)');self.assertEqual(value['value'],'🌍\0λ')
        self.assertTrue(any(r['binding']=='callback' and r['path']==['text'] and r['kind']=='text_range' for r in requests))
        self.assertFalse(any(r['kind']=='value' for r in requests))

    def test_nested_record_result_and_result_code_strings(self):
        for expression,expected in [('slice(box.label,4,2)','🌍\0'),('slice(unwrap(reply),2,2)','🌍\0'),('len(error_message(failure))','10'),('error_code(failure)[1]','🌍')]:
            with self.subTest(expression=expression):
                result,requests,_=self.demand(expression);self.assertEqual(result['value'],expected)
                self.assertTrue(all(r['kind'] in ('shape','text_range') for r in requests))

    def test_empty_slice_checks_bounds_without_payload_and_short_circuit_skips_reads(self):
        result,requests,_=self.demand('slice(text,len(text),0)');self.assertEqual(result['value'],'');self.assertEqual(len(requests),1)
        result,requests,_=self.demand('false && text[999999999999]=="x"');self.assertFalse(result['value']);self.assertFalse(requests)

    def test_bounds_and_range_budget_fail_without_whole_capture(self):
        frame=self.shaped()
        for expression in ['text[-1]','text[1000000000]','slice(text,-1,1)','slice(text,0,-1)','slice(text,1000000000,1)']:
            with self.subTest(expression=expression):self.assertEqual(self.inspect(expression,frame,ok=False)['code'],'E_BOUNDS')
        self.assertEqual(self.inspect('slice(text,0,4097)',frame,ok=False)['code'],'E_DEBUG_LIMIT')
        result,requests,_=self.demand('slice(text,0,4096)',lambda r:{'length':'4096'} if r['kind']=='shape' else '🌍'*4096)
        self.assertEqual(result['value'],'🌍'*4096);self.assertTrue(result['display_truncated']);self.assertEqual(len(requests),2)

    def test_saved_window_supplies_contained_and_overlapping_future_selections(self):
        frame=self.shaped(6);frame['captures'] += [self.window(0,4,'A🌍\0λ'),self.window(3,3,'λBC')]
        self.assertEqual(self.inspect('text[2]',frame)['value'],'\0')
        self.assertEqual(self.inspect('slice(text,1,5)',frame)['value'],'🌍\0λBC')
        self.assertEqual(self.inspect('text[0]',frame)['read_paths'][-1]['kind'],'text_range')
        bad=copy.deepcopy(frame);bad['captures'][-1]['value']='QBC'
        self.assertEqual(self.inspect('slice(text,1,5)',bad,ok=False)['code'],'E_DEBUG_VALUE')

    def test_missing_or_unavailable_ranges_never_become_empty_values(self):
        frame=self.shaped(6);frame['captures'].append(self.window(0,2,'A🌍'))
        self.assertEqual(self.inspect('text[5]',frame,ok=False)['code'],'E_DEBUG_UNAVAILABLE')
        request=self.inspect('slice(text,0,4)',frame,kind='demand')['request'];self.assertEqual((request['start'],request['count']),('0','4'))
        unavailable=self.window(5,1,'x');unavailable.pop('value');unavailable['unavailable']='memory inaccessible';frame['captures'].append(unavailable)
        self.assertIn('memory inaccessible',self.inspect('text[5]',frame,ok=False)['message'])

    def test_whole_string_frames_keep_original_operations_and_wire(self):
        frame=copy.deepcopy(self.frame);frame['schema']='nex.debug-frame/1';frame.pop('captures')
        text=frame['bindings'][0];text.pop('unavailable');text['value']='A🌍\0λ'
        for expression,expected in [('len(text)','4'),('text[1]','🌍'),('slice(text,1,2)','🌍\0'),('text=="A🌍\\u0000λ"',True)]:
            self.assertEqual(self.inspect(expression,frame)['value'],expected)

    def test_malformed_range_metadata_paths_and_duplicates_are_rejected(self):
        for field,values in [('start',[-1,1,'','-1','00','+1','1.0','١','9223372036854775808']),('count',[1,'-1','00','4097','9223372036854775807'])]:
            for value in values:
                with self.subTest(field=field,value=value):
                    frame=self.shaped(8);c=self.window(0,1,'A');c[field]=value;frame['captures'].append(c)
                    self.assertEqual(self.inspect('len(text)',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=self.shaped();frame['captures'] += [self.window(0,1,'A'),self.window(0,1,'A')]
        self.assertEqual(self.inspect('len(text)',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=self.shaped();frame['captures'][0]['start']='0';frame['captures'][0]['count']='1'
        self.assertEqual(self.inspect('len(text)',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=self.shaped();frame['captures'].append(self.window(0,1,'A',binding='callback'))
        self.assertEqual(self.inspect('len(text)',frame,ok=False)['code'],'E_DEBUG_FRAME')
        frame=self.shaped();frame['captures'].append(self.window(9223372036854775807,1,'A'))
        self.assertEqual(self.inspect('len(text)',frame,ok=False)['code'],'E_DEBUG_FRAME')

    def test_range_values_must_match_declared_scalar_count(self):
        for value in ['','AA',1,{'text':'A'}]:
            frame=self.shaped(8);frame['captures'].append(self.window(0,1,value))
            self.assertEqual(self.inspect('text[0]',frame,ok=False)['code'],'E_DEBUG_VALUE')
        surrogate=self.shaped(8);surrogate['captures'].append(self.window(0,1,'\ud800'))
        self.assertEqual(self.inspect('text[0]',surrogate,ok=False)['code'],'E_DEBUG_FRAME')
        for length in ['00','-1','9223372036854775808',5]:
            frame=self.shaped();frame['captures'][0]['value']['length']=length
            self.assertEqual(self.inspect('len(text)',frame,ok=False)['code'],'E_DEBUG_VALUE')

    def test_alias_ranges_and_whole_capture_agree_in_both_evaluation_orders(self):
        frame=copy.deepcopy(self.frame)
        for binding in frame['bindings']:
            if binding['name']=='callback':binding.pop('unavailable');binding['value']=dict(self.shape,captures={'text':'A🌍\0λ'})
        frame['captures']=[{'binding':'alias','path':[],'kind':'shape','value':dict(self.shape)}, {'binding':'alias','path':['text'],'kind':'shape','value':{'length':'4'}},self.window(1,2,'🌍\0',binding='alias',path=['text'])]
        for expression in ['callback(1,2)==alias(1,2)','alias(1,2)==callback(1,2)']:
            self.assertTrue(self.inspect(expression,frame)['value'])
            bad=copy.deepcopy(frame);bad['captures'][-1]['value']='Q\0'
            self.assertEqual(self.inspect(expression,bad,ok=False)['code'],'E_DEBUG_VALUE')

    def test_partial_alias_views_agree_and_overlaps_are_checked(self):
        frame=copy.deepcopy(self.frame)
        for binding in ('callback','alias'):
            frame['captures'] += [{'binding':binding,'path':[],'kind':'shape','value':dict(self.shape)}, {'binding':binding,'path':['text'],'kind':'shape','value':{'length':'4'}}]
        frame['captures'] += [self.window(0,3,'A🌍\0',binding='callback',path=['text']),self.window(1,3,'🌍\0λ',binding='alias',path=['text'])]
        self.assertEqual(self.inspect('callback(0,3)+alias(1,3)',frame)['value'],'A🌍\0🌍\0λ')
        bad=copy.deepcopy(frame);bad['captures'][-1]['value']='Q\0λ'
        self.assertEqual(self.inspect('callback(0,3)+alias(1,3)',bad,ok=False)['code'],'E_DEBUG_VALUE')

    def test_selected_scalar_observation_budget_is_explicit(self):
        count=26*4096;frame=self.shaped(count)
        frame['captures'] += [self.window(i*4096,4096,'A'*4096) for i in range(26)]
        expression='(fn(value:str)->i64{var i:i64=0;var total:i64=0;while i<26{total=total+len(slice(value,i*4096,4096));i=i+1;}return total;})(text)'
        self.assertEqual(self.inspect(expression,frame,ok=False)['code'],'E_DEBUG_LIMIT')
        whole=copy.deepcopy(self.frame);whole['bindings'][0].pop('unavailable');whole['bindings'][0]['value']='A'*count
        self.assertEqual(self.inspect(expression,whole)['value'],str(count))

    def test_snapshot_replay_after_source_deletion_preserves_stop_and_graph(self):
        result,_,frame=self.demand('slice(text,len(text)-4,4)');head=self.cli('history')['head'];self.file.unlink()
        replay=self.inspect('text[len(text)-1]',frame)
        self.assertEqual(replay['value'],'λ');self.assertEqual(replay['stop'],result['stop']);self.assertEqual(self.cli('history')['head'],head)

    def test_descriptor_guide_and_model_pack(self):
        desc=self.cli('describe');pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(desc['string_debug_capture_kind'],'text_range');self.assertEqual(desc['string_debug_limits']['range_scalars'],4096)
        self.assertEqual(desc['string_debug_schema'],pack['documents']['text_range_schema'])
        self.assertEqual(self.cli('guide','--kind','string-debug')['text'],(harness.REPO/'docs/string-debug.md').read_text())


if LIVE:
    class LiveStringDebug(StringFrames):
        def test_lldb_dap_large_utf8_ranges_snapshots_and_unchanged_stop(self):
            session=self.cli('debug','--kind','nex-dap');projected=self.identity['sources'][0]['projection'];line=next(i+1 for i,text in enumerate(SOURCE.splitlines()) if '// STRING_STOP' in text)
            report,script=self.root/'string-watch.json',self.root/'string_watch.py'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text,success=True):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded()==success,(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput() if success else result.GetError().removeprefix('error: '))
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID();handle=frame.FindVariable('text').GetValueAsUnsigned()
  result={'length':command('nex-eval len(text)'), 'last':command('nex-eval text[len(text)-1]'),
   'range':command('nex-eval slice(text,len(text)-4,4)'), 'callback':command('nex-eval callback(len(text)-4,4)'),
   'alias':command('nex-eval alias(1,2)'), 'code':command('nex-eval error_code(failure)[1]'),
   'snapshot':command('nex-frame slice(text,len(text)-4,4)'), 'whole':command('nex-eval text',False)}
  assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
  assert frame.FindVariable('text').GetValueAsUnsigned()==handle
  with open(REPORT,'w') as output:json.dump(result,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('REPORT',repr(str(report))))
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),machine=False,timeout=180)
            self.assertTrue(report.is_file(),output.stdout+output.stderr);values=json.loads(report.read_text())
            self.assertEqual(values['length']['value'],'2097152');self.assertEqual(values['last']['value'],'λ')
            self.assertEqual(values['range']['value'],'A🌍\0λ');self.assertEqual(values['callback']['value'],'A🌍\0λ');self.assertEqual(values['alias']['value'],'🌍\0');self.assertEqual(values['code']['value'],'🌍')
            self.assertEqual(values['whole']['code'],'E_DEBUG_UNAVAILABLE')
            self.assertEqual([(c['kind'],c.get('start'),c.get('count')) for c in values['snapshot']['captures']],[('shape',None,None),('text_range','2097148','4')]);self.assertLess(len(json.dumps(values['snapshot'])),8192)
            self.file.unlink();self.assertEqual(self.inspect('text[len(text)-1]',values['snapshot'])['value'],'λ')
            from debugging import DAP
            client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized');client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]});client.request('configurationDone');client.response(pending)
                stopped=client.event('stopped');frame=client.request('stackTrace',{'threadId':stopped['threadId']})['stackFrames'][0]['id']
                def evaluate(expression):return client.request('evaluate',{'expression':expression,'frameId':frame,'context':'watch'})
                self.assertEqual(evaluate('len(text)')['nex']['value'],'2097152')
                self.assertEqual(evaluate('text[len(text)-1]')['nex']['value'],'λ')
                self.assertEqual(evaluate('slice(text,len(text)-4,4)')['nex']['value'],'A🌍\0λ')
                client.request('continue',{'threadId':stopped['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()


if __name__=='__main__':unittest.main()
