"""Opaque file identities, pure watches and actual stopped native file values."""
import copy
import json
from pathlib import Path
import sys
import unittest

LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness

SOURCE='''module resource_debug;
server fn make(first:file)->(server fn(file)->bool){return server fn(value:file)->bool{return value==first;};}
server fn observe(first:file,alias:file,other:file,callback:server fn(file)->bool)->unit!{io}{
 print(first); // RESOURCE_STOP
 print(alias==first);print(callback(other));
}
server fn main()->unit!{fs,io}{
 let first:file=unwrap(file_open_read("input"));let other:file=unwrap(file_open_read("input"));
 observe(first,first,other,make(first));
}
'''


class ResourceFrame(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.source(SOURCE);self.data=self.root/'data';self.data.mkdir();(self.data/'input').write_bytes(b'data')
        self.env={'NEX_FILES_ROOT':str(self.data)}
        self.session=self.cli('debug');self.manifest=Path(self.session['manifest']);self.identity=json.loads(self.manifest.read_text());self.framefile=self.root/'frame.json'
        self.frame={'schema':'nex.debug-frame/1','language':self.identity['language'],'revision':self.identity['revision'],'build_key':self.identity['build_key'],
            'function':'resource_debug::observe','stop':{'process_id':'100','thread_id':'101','frame_id':0,'stop_id':'1'},
            'bindings':[{'name':name,'type':kind,'value':value} for name,kind,value in [
                ('first','file',{'file':'17'}),('alias','file',{'file':'17'}),('other','file',{'file':'18'}),
                ('callback','server fn(file)->bool',{'function':'resource_debug::make::$lambda_0','identity':'9001','captures':{'first':{'file':'17'}}})]],'truncated':False}

    def inspect(self,expression,frame=None,kind=None,**kw):
        self.framefile.write_text(json.dumps(self.frame if frame is None else frame), newline="\n");args=['inspect',self.framefile,'--manifest',self.manifest,'--expression',expression]
        if kind:args+=['--kind',kind]
        return self.cli(*args,**kw)

    def test_identity_aliases_formatting_and_nested_computed_values(self):
        self.assertTrue(self.inspect('first==alias')['value']);self.assertFalse(self.inspect('first==other')['value'])
        self.assertEqual(self.inspect('first')['value'],{'file':'17'});self.assertEqual(self.inspect('str(first)')['value'],'<file>')
        self.assertEqual(self.inspect('[first,alias,other]')['value'],[{'file':'17'},{'file':'17'},{'file':'18'}])
        self.assertEqual(self.inspect('ok(first)')['value'],{'ok':{'file':'17'}})

    def test_pure_server_closure_keeps_opaque_capture_identity(self):
        self.assertTrue(self.inspect('callback(alias)')['value']);self.assertFalse(self.inspect('callback(other)')['value'])
        result=self.inspect('callback')['value'];self.assertEqual(result['captures'],{'first':{'file':'17'}})

    def test_no_filesystem_effect_is_allowed_in_watch(self):
        for expression in ['file_close(first)','file_is_open(first)','file_read(first,1)','file_size(first)','file_open_read("input")','file_write(first,utf8_bytes("x"))']:
            with self.subTest(expression=expression):self.assertEqual(self.inspect(expression,ok=False)['code'],'E_EFFECT')
        self.assertEqual(self.inspect('encode_json(first)',ok=False)['code'],'E_GENERIC_BOUND')

    def test_strict_opaque_input_and_no_descriptor_fields(self):
        for value in [{'file':'0'},{'file':'01'},{'file':'-1'},{'file':'1\n'},{'file':'18446744073709551616'},{'file':17},{'file':'17','fd':3},{}]:
            frame=copy.deepcopy(self.frame);frame['bindings'][0]['value']=value
            with self.subTest(value=value):self.assertEqual(self.inspect('first',frame,ok=False)['code'],'E_DEBUG_VALUE')

    def test_partial_reads_are_bounded_identity_values(self):
        frame=copy.deepcopy(self.frame);frame['schema']='nex.debug-frame/2';frame['captures']=[]
        for binding in frame['bindings']:binding.pop('value');binding['unavailable']='not captured'
        request=self.inspect('first==alias',frame,kind='demand')['request'];self.assertEqual(request['binding'],'first');self.assertEqual(request['kind'],'value');self.assertEqual(request['wire_schema']['root'],'file')
        frame['captures'].append({'binding':'first','path':[],'kind':'value','value':{'file':'17'}})
        request=self.inspect('first==alias',frame,kind='demand')['request'];self.assertEqual(request['binding'],'alias')
        frame['captures'].append({'binding':'alias','path':[],'kind':'value','value':{'file':'17'}})
        self.assertTrue(self.inspect('first==alias',frame)['value'])
        frame['captures']=[];self.assertFalse(self.inspect('false&&first==alias',frame,kind='demand')['value'])


if LIVE:
    class LiveResourceDebug(ResourceFrame):
        def test_lldb_dap_identity_capture_and_archived_replay(self):
            session=self.cli('debug','--kind','nex-dap');projected=self.identity['sources'][0]['projection'];line=next(i+1 for i,t in enumerate(SOURCE.splitlines()) if '// RESOURCE_STOP' in t)
            script=self.root/'file_watch.py';report=self.root/'file-watch.json'
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
  stop=process.GetStopID()
  result={'first':command('nex-eval first'),'equal':command('nex-eval first==alias'),'other':command('nex-eval first==other'),
          'capture':command('nex-eval callback(alias)'),'snapshot':command('nex-frame first==alias'),'previews':command('nex-values')}
  assert process.GetStopID()==stop
  with open(REPORT,'w') as output:json.dump(result,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('REPORT',repr(str(report))), newline="\n")
            output=self.cli('debug','--','--no-lldbinit','--batch','-o','command script import '+json.dumps(str(script)),env=self.env,machine=False,timeout=120)
            self.assertTrue(report.is_file(),output.stdout+output.stderr);result=json.loads(report.read_text())
            self.assertTrue(result['equal']['value']);self.assertFalse(result['other']['value']);self.assertTrue(result['capture']['value'])
            self.assertRegex(result['first']['value']['file'],r'^[1-9][0-9]*$');self.assertIn('<file ',json.dumps(result['previews']))
            self.file.unlink();snapshot=self.root/'snapshot.json';snapshot.write_text(json.dumps(result['snapshot']), newline="\n")
            self.assertTrue(self.cli('inspect',snapshot,'--manifest',self.manifest,'--expression','first==alias')['value'])
            from debugging import DAP
            client=DAP(session['adapter_command'],self.root)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False,env=self.env));client.event('initialized')
                client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]});client.request('configurationDone');client.response(pending)
                stopped=client.event('stopped');frame=client.request('stackTrace',{'threadId':stopped['threadId']})['stackFrames'][0]['id']
                value=client.request('evaluate',{'expression':'first','frameId':frame,'context':'watch'});self.assertEqual(value['type'],'file');self.assertEqual(value['variablesReference'],0);self.assertIn('<file ',value['result'])
                result=client.request('evaluate',{'expression':'[first,alias]','frameId':frame,'context':'watch'})
                children=client.request('variables',{'variablesReference':result['variablesReference'],'filter':'indexed','start':0,'count':2})['variables'];self.assertEqual(children[0]['value'],children[1]['value'])
                client.request('continue',{'threadId':stopped['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            finally:client.close()


if __name__=='__main__':unittest.main(verbosity=2)
