"""Bounded source sheet, actual examples, rejects and backend agreement."""
import json
import copy
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest
import support as h

spec=importlib.util.spec_from_file_location('quick_sdk_acceptance',h.REPO/'tools/sdk_acceptance.py')
sdk=importlib.util.module_from_spec(spec);spec.loader.exec_module(sdk)


class QuickReference(h.ToolchainCase):
    def test_bounded_sheet_and_embedded_program_are_current_and_checked(self):
        value=self.cli('guide','--kind','quick')
        cap=self.cli('describe','--field','llm_entry')['value']
        text=(h.REPO/cap['guide']).read_text()
        self.assertEqual(value['text'],text)
        self.assertEqual(value['language'],h.CURRENT_LANGUAGE)
        self.assertLessEqual(len(text.encode()),cap['guide_utf8_bytes_max'])
        self.assertFalse(cap['token_savings_demonstrated'])
        programs=re.findall(r'```nex\n(.*?)```',text,re.S)
        self.assertEqual(len(programs),1)
        self.source(programs[0]);self.cli('check')
        observed=self.cli('eval');self.assertEqual(observed['stdout'],'4\n')
        self.assertIn('slice(text,start,count)',text)
        self.assertIn('add throw',self.cli('explain','E_EFFECT')['action'])

    def test_quick_resource_limit_and_UTF8_are_enforced_before_any_project_lookup(self):
        (self.root/'nex.json').write_text('{')
        resources=self.root/'resources';(resources/'llm').mkdir(parents=True)
        file=resources/'llm/QUICK_REFERENCE.md'
        env=dict(os.environ,NEX_RESOURCE_DIR=str(resources))
        file.write_bytes(b'x'*6145)
        self.assertEqual(self.cli('guide','--kind','quick',env=env,ok=False)['code'],'E_RESOURCE')
        file.write_bytes(b'\xff')
        self.assertEqual(self.cli('guide','--kind','quick',env=env,ok=False)['code'],'E_JSON')
        self.assertFalse((self.root/'.nex').exists())

    def test_multi_module_sample_reference_native_profiles_and_typescript_agree(self):
        node=os.environ.get('NEX_NODE','node')
        def run(command):
            child=subprocess.run(list(map(str,command)),capture_output=True,text=True,timeout=60)
            self.assertEqual(child.returncode,0,child.stdout+child.stderr)
            return child.stdout
        proof=sdk.exercise_bounded_language_entry(cli=self.cli,run=run,compiler=Path(h.NEX),
            resources=h.REPO,root=self.root,browser=True)
        resources={name:hashlib.sha256((h.REPO/name).read_bytes()).hexdigest() for name in
            ['llm/QUICK_REFERENCE.md',*['examples/llm-quick/'+name for name in proof['source_sha256']]]}
        report={'compiler_sha256':proof['compiler_sha256'],'version':proof['toolchain'],'language':h.CURRENT_LANGUAGE,
            'resource_hashes':resources,'evidence':{'browser_build':True,'bounded_language_entry':proof}}
        sdk.validate_bounded_language_entry_evidence(report)
        for key,value in [('compiler_sha256','0'*64),('guide_bytes',6145),('sheet_checked',False),
                          ('reference_stdout','wrong'),('native',{}),('typescript',{'requested':True,'executed':False}),
                          ('model_token_savings_measured',True),('source_sha256',{})]:
            changed=copy.deepcopy(report);changed['evidence']['bounded_language_entry'][key]=value
            with self.subTest(rejected=key),self.assertRaises(RuntimeError):
                sdk.validate_bounded_language_entry_evidence(changed)
        changed=copy.deepcopy(report);changed['resource_hashes']['llm/QUICK_REFERENCE.md']='0'*64
        with self.assertRaises(RuntimeError):sdk.validate_bounded_language_entry_evidence(changed)
        changed=copy.deepcopy(report);del changed['evidence']['bounded_language_entry']
        with self.assertRaises(RuntimeError):sdk.validate_bounded_language_entry_evidence(changed)
        # Non-browser scope must be declared explicitly; it never claims TS execution.
        changed=copy.deepcopy(report);changed['evidence']['browser_build']=False
        changed['evidence']['bounded_language_entry']['typescript']={'requested':False,'executed':False}
        sdk.validate_bounded_language_entry_evidence(changed)
        folder=self.root/'bounded-entry-typescript'
        tsc=os.environ.get('NEX_TSC')
        if not tsc:
            self.assertTrue(os.environ.get('NEX_NPM_CACHE'),
                'Set NEX_TSC to the pinned compiler or NEX_NPM_CACHE to its populated offline package cache')
            tool=self.root/'typecheck-tool';tool.mkdir()
            for name in ('package.json','package-lock.json'):shutil.copy2(h.REPO/'web'/name,tool/name)
            run([os.environ.get('NEX_NPM','npm'),'ci','--ignore-scripts','--offline','--prefix',tool,
                '--cache',os.environ['NEX_NPM_CACHE']])
            tsc=tool/'node_modules/typescript/bin/tsc'
        selected=Path(tsc).resolve(strict=True)
        pinned=json.loads((h.REPO/'web/package.json').read_text())['devDependencies']['typescript']
        self.assertEqual(json.loads((selected.parent.parent/'package.json').read_text())['version'],pinned)
        checked=subprocess.run([node,str(selected),'--noEmit','--strict','--target','ES2022','--module','ESNext',
            '--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',str(folder/'program.ts')],
            capture_output=True,text=True,timeout=180)
        self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
        print(json.dumps({'bounded_entry_subworkflow':proof,'strict_TypeScript':pinned,
            'SDK_receipt_rejection_controls':10,'complete_SDK_workflow_executed':False}))


if __name__=='__main__':unittest.main(verbosity=2)
