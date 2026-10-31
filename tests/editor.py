"""Editor launch preparation, frozen/original source maps and contract cases."""
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


class Editor(harness.ToolchainCase):
    def session_module(self):
        compiler=Path(harness.NEX);installed=compiler.parent.parent/'share/nex/editor/vscode/session.js'
        return installed if compiler.parent.name=='bin' and installed.is_file() else harness.REPO/'editor/vscode/session.js'
    def project_session(self):
        project=self.root/("project 'quoted' % 🧠" if os.name=="nt" else 'project "quoted" \\ % 🧠');shutil.copytree(harness.REPO/'examples/project-tasks',project,ignore=shutil.ignore_patterns('.nex'))
        (project/'task.json').unlink()
        (project/'core/value.nex').write_text('''module project_task::core;
pub fn make(offset:i64)->(fn(i64)->i64){
 let base:i64=offset;
 return fn(value:i64)->i64{return value+base;};
}
pub fn decorate(value:str)->str{return value+" 🧠";}
''', newline="\n")
        before=self.cli('project',project/'nex.build.json','--kind','plan','--component','app','--configuration','debug',cwd=project)
        script='''const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]}).then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});'''
        config={'type':'nex','request':'launch','cwd':str(project),'project':{'manifest':'nex.build.json','component':'app','configuration':'debug'}}
        process=subprocess.run([self.node(),'-e',script,str(self.session_module()),json.dumps(config),harness.NEX],cwd=project,capture_output=True,text=True,timeout=240)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr);prepared=json.loads(process.stdout)
        cache=Path(prepared['launch']['program']).parent.parent
        if cache.name.startswith('nex-debug-'):self.addCleanup(shutil.rmtree,cache)
        self.assertEqual(prepared['project']['planHash'],before['plan_hash']);self.assertEqual(prepared['project']['architectureHash'],before['architecture_hash'])
        compilation=json.loads((Path(prepared['launch']['program']).parent/'compilation.json').read_text())
        self.assertEqual(len(compilation['owned_images']),2);self.assertTrue(all(u['identity'].startswith('project_task::app::') for u in compilation['units']))
        self.assertTrue(any(Path(row[1]).resolve()==(project/'core/value.nex').resolve() for row in prepared['originalSourceMappings']))
        self.assertFalse((project/'.nex/graph.db').exists());return project,prepared

    def test_project_session_keeps_shared_provider_and_frozen_artifact_identity(self):
        self.project_session()

    @unittest.skipUnless(LIVE, 'use --live for actual project editor breakpoints')
    def test_project_original_provider_breakpoint_and_watch(self):
        from debugging import DAP
        project,prepared=self.project_session();source=project/'core/value.nex';client=DAP(prepared['command'],project)
        try:
            client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
            pending=client.send('launch',dict(prepared['launch'],disableASLR=False));client.event('initialized')
            client.request('setBreakpoints',{'source':{'path':str(source)},'breakpoints':[{'line':4}]})
            client.request('configurationDone');client.response(pending);stop=client.event('stopped');self.assertEqual(stop['reason'],'breakpoint')
            placed=client.request('setBreakpoints',{'source':{'path':str(source)},'breakpoints':[{'line':4}]});self.assertTrue(placed['breakpoints'][0]['verified'])
            frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]
            self.assertIn('make',frame['name']);self.assertEqual(Path(frame['source']['path']).resolve(),source.resolve())
            value=client.request('evaluate',{'expression':'base+2','frameId':frame['id'],'context':'watch'});self.assertEqual(value['nex']['value'],'42')
            # The same line also defines the returned closure. This observation
            # is complete; avoid stopping again when that closure is called.
            client.request('setBreakpoints',{'source':{'path':str(source)},'breakpoints':[]})
            client.request('continue',{'threadId':stop['threadId']});self.assertEqual(client.event('exited')['exitCode'],0);client.event('terminated')
            stdout=''.join(m.get('body',{}).get('output','') for m in client.pending if m.get('event')=='output' and m.get('body',{}).get('category')=='stdout')
            self.assertEqual(stdout.replace('\r\n','\n'),'42 🧠\n');self.assertFalse((project/'.nex/graph.db').exists())
        finally:client.close()

    def node(self):
        node=os.environ.get('NEX_NODE') or shutil.which('node')
        self.assertTrue(node, 'Node is required for the editor integration checks')
        return node

    def test_editor_contracts_reject_untrusted_stale_and_malformed_launches(self):
        process=subprocess.run([self.node(),'--test','test.js'],cwd=harness.REPO/'editor/vscode',capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)

    def test_actual_compiler_session_maps_only_matching_original_source(self):
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':self.cli('describe')['version'],'entry':'main.nex'}), newline="\n")
        self.source('module editor_case; fn main()->unit!{io} {let value:i64=40;print(value+2);}')
        descriptor=self.cli('debug',self.file,'--kind','nex-dap')
        if not descriptor['nex_adapter']['available']:self.skipTest('matching native LLDB DAP backend unavailable')
        script='''const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]}).then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});'''
        command=[self.node(),'-e',script,str(self.session_module()),json.dumps({'type':'nex','request':'launch','source':str(self.file),'cwd':str(self.root)}),harness.NEX]
        process=subprocess.run(command,cwd=self.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        prepared=json.loads(process.stdout)
        self.assertEqual(prepared['revision'],descriptor['revision'])
        self.assertEqual(prepared['buildKey'],descriptor['build_key'])
        self.assertTrue(any(pair[1]==str(self.file) for pair in prepared['originalSourceMappings']))
        self.assertEqual(prepared['frozenSourceFallbacks'],[])
        self.assertEqual(prepared['command'],descriptor['adapter_command'])
        self.assertTrue(Path(prepared['launch']['program']).is_file())

    @unittest.skipUnless(LIVE, 'use --live for actual native editor breakpoints')
    def test_original_breakpoint_and_watch_with_quoted_source_path(self):
        from debugging import DAP
        project=self.root/("project 'quoted' % 🧠" if os.name=="nt" else 'project "quoted" \\ % 🧠')
        project.mkdir()
        source=project/'main with spaces.nex'
        source.write_text('module editor_quoted;\nfn main()->unit!{io}{\n let total:i64=40;\n print(total+2);\n}\n', newline="\n")
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':self.cli('describe')['version'],'entry':source.name}), newline="\n")
        descriptor=self.cli('debug',source,'--kind','nex-dap',cwd=project)
        if not descriptor['nex_adapter']['available']:self.skipTest('matching native LLDB DAP backend unavailable')
        script='''const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]}).then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});'''
        process=subprocess.run([self.node(),'-e',script,str(self.session_module()),json.dumps({'type':'nex','request':'launch','source':str(source),'cwd':str(project)}),harness.NEX],cwd=project,capture_output=True,text=True,timeout=60)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        prepared=json.loads(process.stdout)
        self.assertEqual(prepared['revision'],descriptor['revision'])
        self.assertEqual(prepared['buildKey'],descriptor['build_key'])
        client=DAP(prepared['command'],project)
        try:
            client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True})
            pending=client.send('launch',dict(prepared['launch'],disableASLR=False));client.event('initialized')
            placed=client.request('setBreakpoints',{'source':{'path':str(source)},'breakpoints':[{'line':4}]})
            self.assertTrue(placed['breakpoints'][0]['verified'],placed)
            client.request('configurationDone');client.response(pending)
            stop=client.event('stopped');self.assertEqual(stop['reason'],'breakpoint')
            frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]
            self.assertEqual(frame['source']['path'],str(source))
            value=client.request('evaluate',{'expression':'total+2','frameId':frame['id'],'context':'watch'})
            self.assertEqual(value['nex']['value'],'42')
            client.request('continue',{'threadId':stop['threadId']})
            self.assertEqual(client.event('exited')['exitCode'],0)
            client.event('terminated')
            stdout=''.join(m.get('body',{}).get('output','') for m in client.pending if m.get('event')=='output' and m.get('body',{}).get('category')=='stdout')
            self.assertEqual(stdout.replace('\r\n','\n'),'42\n')
        finally:client.close()


if __name__=='__main__':unittest.main(verbosity=2)
