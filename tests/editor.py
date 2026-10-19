"""Editor launch preparation, frozen/original source maps and contract cases."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as harness


class Editor(harness.ToolchainCase):
    def node(self):
        node=os.environ.get('NEX_NODE') or shutil.which('node')
        self.assertTrue(node, 'Node is required for the editor integration checks')
        return node

    def test_editor_contracts_reject_untrusted_stale_and_malformed_launches(self):
        process=subprocess.run([self.node(),'--test','test.js'],cwd=harness.REPO/'editor/vscode',capture_output=True,text=True,timeout=30)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)

    def test_actual_compiler_session_maps_only_matching_original_source(self):
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':self.cli('describe')['version'],'entry':'main.nex'}))
        self.source('module editor_case; fn main()->unit!{io} {let value:i64=40;print(value+2);}')
        descriptor=self.cli('debug',self.file,'--kind','nex-dap')
        if not descriptor['nex_adapter']['available']:self.skipTest('matching native LLDB DAP backend unavailable')
        script='''const {prepareSession}=require(process.argv[1]);prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]}).then(value=>process.stdout.write(JSON.stringify(value))).catch(error=>{console.error(error.message);process.exitCode=1;});'''
        command=[self.node(),'-e',script,str(harness.REPO/'editor/vscode/session.js'),json.dumps({'type':'nex','request':'launch','source':str(self.file),'cwd':str(self.root)}),harness.NEX]
        process=subprocess.run(command,cwd=self.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(process.returncode,0,process.stdout+process.stderr)
        prepared=json.loads(process.stdout)
        self.assertEqual(prepared['revision'],descriptor['revision'])
        self.assertEqual(prepared['buildKey'],descriptor['build_key'])
        self.assertTrue(any(pair[1]==str(self.file) for pair in prepared['originalSourceMappings']))
        self.assertEqual(prepared['frozenSourceFallbacks'],[])
        self.assertEqual(prepared['command'],descriptor['adapter_command'])
        self.assertTrue(Path(prepared['launch']['program']).is_file())


if __name__=='__main__':unittest.main(verbosity=2)
