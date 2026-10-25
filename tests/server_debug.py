"""Server descriptors and real stopped worker frames use checked native images."""
import concurrent.futures
import json
import os
from pathlib import Path
import re
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.request

LIVE='--live' in sys.argv
if LIVE:sys.argv.remove('--live')
import support as harness
from debugging import DAP


class ServerDebug(harness.ToolchainCase):
    def setUp(self):
        super().setUp();self.root=self.root.resolve()/'server project % 🧠';self.root.mkdir()
        for name in ('core','service','assets'):(self.root/name).mkdir()
        (self.root/'core/main.nex').write_text('''module debug_core;
pub fn render(body:str)->str{
  let prefix:str="Я🧠:";
  return prefix+body;
}
''')
        (self.root/'service/main.nex').write_text('''module debug_service;
import "std/http.nex" as http;
import "../core/main.nex" as c;
server fn handle(request:http::Request)->http::Response!{db}{
  assert(is_ok(store_put("debug-marker",request.body)));
  let rendered:str=c::render(request.body);
  return http::json_response(200,encode_json(rendered));
}
''')
        (self.root/'assets/index.html').write_text('<h1>Debug server</h1>')
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.23','entry':'service/main.nex'}))
        (self.root/'nex.build.json').write_text(json.dumps({'schema':'nex.project-build/1','default_configuration':'debug',
            'configurations':{'debug':{'profile':'debug'}},'components':{
                'core':{'kind':'shared_library','root':'core','entry':'core/main.nex','entry_function':'render'},
                'service':{'kind':'server','root':'service','entry':'service/main.nex','dependencies':{'core':'dynamic'}}}}))
        self.auth=self.root/'private auth.json';self.database=self.root/'private.sqlite'
        self.arguments=['--auth',str(self.auth),'--database',str(self.database),'--static',str(self.root/'assets'),
            '--port','0','--timeout-ms','60000']

    def descriptor(self,*args,**kwargs):
        process=self.cli('project','--kind','debug','--component','service','--adapter','nex-dap',
            *args,'--json','--',*self.arguments,machine=False,timeout=240,**kwargs)
        return json.loads(process.stdout)

    def test_descriptor_preserves_server_image_and_runtime_arguments_without_starting(self):
        result=self.descriptor();session=result['observation']
        artifact=next(a for a in result['artifacts'] if a['component']=='service')
        self.assertEqual(session['application_kind'],'http_server');self.assertTrue(session['host_compatible'])
        self.assertEqual(session['launch']['program'],artifact['artifact'])
        self.assertEqual(session['launch']['args'],self.arguments)
        self.assertEqual(session['nex_adapter']['launch']['args'],self.arguments)
        self.assertEqual(session['build_key'],artifact['build_key'])
        manifest=json.loads(Path(session['manifest']).read_text())
        self.assertEqual(len(manifest['owned_images']),2)
        self.assertEqual(sum(i['kind']=='runtime' for i in manifest['owned_images']),1)
        self.assertFalse(self.auth.exists());self.assertFalse(self.database.exists())
        self.assertFalse((self.root/'.nex/graph.db').exists())

    def test_source_server_descriptor_and_invalid_debug_options(self):
        session=self.cli('debug','service/main.nex','--target','server','--kind','nex-dap',timeout=180)
        self.assertEqual(session['application_kind'],'http_server');self.assertTrue(session['host_compatible'])
        self.assertFalse(self.auth.exists());self.assertFalse(self.database.exists())
        graph=harness.database_rows(self.root/'.nex/graph.db')
        for args in [('--library',),('--kind','unknown')]:
            rejected=self.cli('debug','service/main.nex',*args,ok=False)
            self.assertEqual(rejected['code'],'E_OPTION')
            self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),graph)

    def test_debug_argument_limits_reject_before_build_cache_or_graph(self):
        for arguments in [['x']*129,['x'*4097],['x'*4096]*17]:
            process=self.cli('project','--kind','debug','--component','service','--json','--',*arguments,machine=False,ok=False)
            self.assertEqual(json.loads(process.stdout)['code'],'E_OPTION')
            self.assertFalse((self.root/'.nex').exists())

    def send_request(self,port,token):
        request=urllib.request.Request('http://127.0.0.1:'+str(port)+'/api/debug',data='payload'.encode(),
            headers={'Authorization':'Bearer '+token,'Content-Type':'text/plain'},method='POST')
        try:response=urllib.request.urlopen(request,timeout=90)
        except urllib.error.HTTPError as error:response=error
        with response:return response.status,json.loads(response.read())

    def start(self,session,breakpoints,source_breakpoint=None):
        client=DAP(session['adapter_command'],self.root)
        try:
            client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,
                'supportsVariableType':True,'supportsVariablePaging':True})
            original=session['nex_adapter']['launch']
            launch=dict(original,disableASLR=False,
                preRunCommands=[*original.get('preRunCommands',[]),'process handle -s false -n false -p true SIGTERM'])
            pending=client.send('launch',launch);client.event('initialized')
            client.request('setFunctionBreakpoints',{'breakpoints':[{'name':name} for name in breakpoints]})
            if source_breakpoint:client.request('setBreakpoints',source_breakpoint)
            client.request('configurationDone');client.response(pending)
            process=client.event('process');pid=process['systemProcessId']
            output=''
            for _ in range(64):
                output+=client.event('output').get('output','')
                match=re.search(r'NEX server http://127\.0\.0\.1:([0-9]+)',output)
                if match:return client,pid,int(match.group(1))
            self.fail('debuggee did not report a bounded loopback listener')
        except BaseException:
            client.close();raise

    def stop_server(self,client,pid):
        os.kill(pid,signal.SIGTERM)
        self.assertEqual(client.event('exited')['exitCode'],0)
        output=''.join(m.get('body',{}).get('output','') for m in client.pending if m.get('event')=='output')
        self.assertNotIn('E_INTERNAL_LEAK',output)

    @unittest.skipUnless(LIVE,'opt-in real HTTP/DAP worker debugging')
    def test_live_worker_request_and_provider_frames_after_original_source_deletion(self):
        token=self.cli('token','--user','debug-user','--auth',self.auth)['token']
        result=self.descriptor();session=result['observation'];manifest=json.loads(Path(session['manifest']).read_text())
        symbols={f['name']:f['native_symbol'] for f in manifest['functions']}
        for name in ('core','service'):shutil.rmtree(self.root/name)
        for name in ('nex.json','nex.build.json'):(self.root/name).unlink()
        client,pid,port=self.start(session,[symbols['debug_service::handle'],symbols['debug_core::render']])
        executor=concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            request=executor.submit(self.send_request,port,token)
            for name,expression,expected in [('debug_service','request.path','/api/debug'),('debug_core','body','payload')]:
                stop=client.event('stopped');self.assertEqual(stop['reason'],'breakpoint')
                frames=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames']
                self.assertIn(name,frames[0]['name'])
                value=client.request('evaluate',{'expression':expression,'frameId':frames[0]['id'],'context':'watch'})
                self.assertEqual(value['nex']['value'],expected)
                client.request('continue',{'threadId':stop['threadId']})
            self.assertEqual(request.result(timeout=80),(200,'Я🧠:payload'))
            self.stop_server(client,pid)
            with sqlite3.connect(self.database) as db:
                self.assertEqual(db.execute('SELECT value FROM nex_kv WHERE owner=? AND key=?',('debug-user','debug-marker')).fetchone(),(b'payload',))
            self.assertFalse((self.root/'.nex/graph.db').exists())
        finally:
            client.close();executor.shutdown(wait=True)

    def editor_session(self,project):
        compiler=Path(harness.NEX);installed=compiler.parent.parent/'share/nex/editor/vscode/session.js'
        module=installed if compiler.parent.name=='bin' and installed.is_file() else harness.REPO/'editor/vscode/session.js'
        node=os.environ.get('NEX_NODE') or shutil.which('node');self.assertTrue(node,'Node is required for editor server checks')
        config={'type':'nex','request':'launch','cwd':str(self.root),'args':self.arguments}
        if project:config['project']={'manifest':'nex.build.json','component':'service','configuration':'debug'}
        else:config.update(source='service/main.nex',target='server')
        code='''const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]})
.then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});'''
        result=subprocess.run([node,'-e',code,str(module),json.dumps(config),harness.NEX],cwd=self.root,capture_output=True,text=True,timeout=240)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);return json.loads(result.stdout)

    def observe_editor(self,project):
        token=self.cli('token','--user','editor-user','--auth',self.auth)['token']
        if not project:(self.root/'nex.build.json').unlink()
        prepared=self.editor_session(project)
        self.assertFalse(self.database.exists())
        source=self.root/'core/main.nex'
        self.assertTrue(any(Path(pair[1]).resolve()==source.resolve() for pair in prepared['originalSourceMappings']))
        session={'adapter_command':prepared['command'],'nex_adapter':{'launch':prepared['launch']}}
        breakpoint={'source':{'path':str(source)},'breakpoints':[{'line':4}]}
        client,pid,port=self.start(session,[],breakpoint);executor=concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            request=executor.submit(self.send_request,port,token)
            stop=client.event('stopped');self.assertEqual(stop['reason'],'breakpoint')
            placed=client.request('setBreakpoints',breakpoint);self.assertTrue(placed['breakpoints'][0]['verified'])
            frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]
            self.assertEqual(Path(frame['source']['path']).resolve(),source.resolve())
            value=client.request('evaluate',{'expression':'prefix+body','frameId':frame['id'],'context':'watch'})
            self.assertEqual(value['nex']['value'],'Я🧠:payload')
            client.request('continue',{'threadId':stop['threadId']})
            self.assertEqual(request.result(timeout=80),(200,'Я🧠:payload'))
            self.stop_server(client,pid)
            if project:self.assertFalse((self.root/'.nex/graph.db').exists())
        finally:
            client.close();executor.shutdown(wait=True)

    @unittest.skipUnless(LIVE,'opt-in actual project editor server launch and source breakpoint')
    def test_live_editor_project_server_original_source_breakpoint(self):
        self.observe_editor(True)

    @unittest.skipUnless(LIVE,'opt-in actual source editor HTTP-target launch and source breakpoint')
    def test_live_editor_source_server_original_source_breakpoint(self):
        self.observe_editor(False)

    @unittest.skipUnless(LIVE,'opt-in real HTTP/DAP deadline preservation')
    def test_live_pause_keeps_request_deadline_and_rolls_back_database_write(self):
        token=self.cli('token','--user','debug-user','--auth',self.auth)['token']
        self.arguments[-1]='5000'
        session=self.descriptor()['observation'];manifest=json.loads(Path(session['manifest']).read_text())
        symbol=next(f['native_symbol'] for f in manifest['functions'] if f['name']=='debug_core::render')
        client,pid,port=self.start(session,[symbol]);executor=concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
            request=executor.submit(self.send_request,port,token)
            stop=client.event('stopped');self.assertEqual(stop['reason'],'breakpoint')
            time.sleep(6)
            client.request('continue',{'threadId':stop['threadId']})
            status,body=request.result(timeout=30)
            self.assertEqual(status,504);self.assertEqual(body['error']['code'],'E_TIMEOUT')
            self.stop_server(client,pid)
            with sqlite3.connect(self.database) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM nex_kv').fetchone()[0],0)
            self.assertFalse((self.root/'.nex/graph.db').exists())
        finally:
            client.close();executor.shutdown(wait=True)


if __name__=='__main__':unittest.main()
