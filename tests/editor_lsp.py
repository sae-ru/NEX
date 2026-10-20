"""Actual Node LSP client plus editor provider/lifecycle contracts."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import support as harness


class EditorLSP(harness.ToolchainCase):
    def node(self):
        node=os.environ.get('NEX_NODE') or shutil.which('node')
        self.assertTrue(node,'Node is required for editor LSP acceptance')
        return node

    def test_provider_and_transport_contracts(self):
        result=subprocess.run([self.node(),'--test','test.js','language.test.js'],cwd=harness.REPO/'editor/vscode',
                              capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_actual_client_and_compiler_preserve_unsaved_sources_and_history(self):
        output=self.root/'client acceptance 🧠'
        result=subprocess.run([self.node(),str(harness.REPO/'editor/vscode/lsp-acceptance.js'),harness.NEX,str(output)],
                              cwd=self.root,capture_output=True,text=True,timeout=60)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report=json.loads(result.stdout)
        self.assertTrue(report['ok']);self.assertTrue(report['source_and_graph_unchanged'])
        self.assertEqual(len(report['checks']),3)


if __name__=='__main__':unittest.main(verbosity=2)
