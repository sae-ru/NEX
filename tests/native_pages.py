"""Opt-in actual DAP indexed pages, without whole-root watch capture."""
import json
from pathlib import Path
import sys
import unittest
LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness
from debugging import DAP

SOURCE=(harness.REPO/'examples/debugging/pages.nex').read_text()

class NativePages(harness.ToolchainCase):
    @unittest.skipUnless(LIVE, 'use --live for actual native indexed pages')
    def test_native_root_pages_reach_large_indices_remain_bounded_and_expire(self):
        self.source(SOURCE);session=self.cli('debug','--kind','nex-dap')
        if not session['nex_adapter']['available']:self.skipTest('matching lldb-dap unavailable')
        manifest=json.loads(Path(session['manifest']).read_text());projected=manifest['sources'][0]['projection']
        line=next(i+1 for i,s in enumerate(SOURCE.splitlines()) if 'NATIVE_PAGE_STOP' in s)
        client=DAP(session['adapter_command'],self.root)
        try:
            client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True,'supportsVariableType':True})
            pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
            placed=client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
            self.assertTrue(placed['breakpoints'][0]['verified']);client.request('configurationDone');client.response(pending)
            stop=client.event('stopped');frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
            scopes=client.request('scopes',{'frameId':frame})['scopes'];variables=[]
            for scope in scopes:
                if not scope.get('expensive'):variables.extend(client.request('variables',{'variablesReference':scope['variablesReference']})['variables'])
            roots={v['name']:v for v in variables};print(json.dumps({'native_roots':roots},ensure_ascii=False),flush=True)
            before=client.request('evaluate',{'expression':'len(items)+len(data)','frameId':frame,'context':'watch'})
            self.assertEqual(before['nex']['value'],'4227072')
            references={}
            for name,total,expected in [('items',32768,['40','42']),('data',4194304,['120','255'])]:
                root=roots[name];self.assertEqual(root['indexedVariables'],total)
                reference=root['variablesReference'];references[name]=reference
                page=client.request('variables',{'variablesReference':reference,'start':total-2,'count':2})
                self.assertEqual([(v['name'],v['value']) for v in page['variables']],[(f'[{total-2}]',expected[0]),(f'[{total-1}]',expected[1])])
                self.assertEqual(page['nex']['native_page']['returned_count'],2)
                indexed=client.request('variables',{'variablesReference':reference,'filter':'indexed','start':total-2,'count':2})
                self.assertEqual([(v['name'],v['value']) for v in indexed['variables']],[(f'[{total-2}]',expected[0]),(f'[{total-1}]',expected[1])])
                named=client.request('variables',{'variablesReference':reference,'filter':'named','start':0,'count':2})
                self.assertEqual(named['variables'],[])
                default=client.request('variables',{'variablesReference':reference})
                self.assertEqual(len(default['variables']),1000)
                huge=client.request('variables',{'variablesReference':reference,'start':1000,'count':1000000})
                self.assertEqual(len(huge['variables']),1000);self.assertEqual(huge['variables'][0]['name'],'[1000]')
                end=client.request('variables',{'variablesReference':reference,'start':total,'count':2})
                self.assertEqual(end['variables'],[])
                for args in [{'start':-1},{'count':True}]:
                    with self.assertRaises(RuntimeError):client.request('variables',{'variablesReference':reference,**args})
            first=client.request('evaluate',{'expression':'items[len(items)-1]+data[len(data)-1]','frameId':frame,'context':'watch'})
            self.assertEqual(first['nex']['value'],'297')
            self.assertEqual(first['nex']['stop'],before['nex']['stop'])
            second=client.request('evaluate',{'expression':'len(data)','frameId':frame,'context':'watch'})
            self.assertEqual(second['nex']['stop'],first['nex']['stop'])
            client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0)
            for reference in references.values():
                with self.assertRaises(RuntimeError):client.request('variables',{'variablesReference':reference,'start':0,'count':1})
        finally:client.close()

if __name__=='__main__':unittest.main(verbosity=2)
