"""Actual bounded compiled explanations, read-only CLI and checked examples."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as h


class Catalogue(h.ToolchainCase):
    def snapshot(self):
        return {p.relative_to(self.root).as_posix():p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def test_all_indexed_codes_have_bounded_identity_bound_guidance(self):
        index=self.cli('explain','--kind','index')
        discovery=self.cli('describe','--kind','index')
        capability=self.cli('describe','--field','diagnostic_catalogue')['value']
        self.assertEqual(index['schema'],'nex.diagnostic-catalogue-index/1')
        self.assertEqual(index['codes'],sorted(set(index['codes'])))
        self.assertEqual(len(index['codes']),capability['covered_codes'])
        self.assertGreaterEqual(len(index['codes']),100)
        self.assertFalse(index['complete_code_registry'])
        self.assertFalse(capability['complete_code_registry'])
        self.assertEqual(index['catalogue_hash'],capability['catalogue_hash'])
        self.assertEqual(self.cli('explain','--kind','index'),index)
        pairs=0
        for code in index['codes']:
            with self.subTest(code=code):
                self.assertRegex(code,r'^E_[A-Z0-9_]+$')
                value=self.cli('explain',code)
                self.assertEqual(value['schema'],'nex.diagnostic-explanation/1')
                for key in ('compiler_build','descriptor_hash','toolchain','language'):
                    self.assertEqual(value[key],discovery[key])
                self.assertEqual(value['catalogue_hash'],index['catalogue_hash'])
                self.assertEqual(value['code'],code)
                self.assertTrue(value['meaning']);self.assertTrue(value['action'])
                self.assertFalse(value['context_specific']);self.assertFalse(value['automatic_fix'])
                self.assertTrue(value['guide_command'].startswith('nex guide --kind '))
                self.assertLessEqual(len(json.dumps(value,ensure_ascii=False,indent=2).encode()),capability['response_bytes_max'])
                pairs+=len(value['examples'])
        self.assertEqual(pairs,capability['checked_example_pairs'])
        text=self.cli('explain','E_PARSE',machine=False).stdout
        self.assertIn('E_PARSE',text);self.assertIn('n=n+2',text)
        self.assertLessEqual(len(text.encode()),capability['response_bytes_max'])
        self.assertFalse((self.root/'.nex').exists())

    def test_catalogue_operates_without_project_resources_or_python_and_preserves_graph(self):
        (self.root/'nex.json').write_text('{"language":"old","entry":"missing.nex"}')
        (self.root/'.nex').mkdir();(self.root/'.nex/graph.db').write_bytes(b'not a graph\0preserve')
        resources=self.root/'empty-resources';resources.mkdir()
        env=dict(os.environ,NEX_RESOURCE_DIR=str(resources),NEX_PYTHON='deliberately-absent-python')
        before=self.snapshot()
        for arguments in [('E_PARSE',),('--kind','index')]:
            value=self.cli('explain',*arguments,env=env)
            self.assertIn('catalogue_hash',value)
            self.assertEqual(self.snapshot(),before)
        # Only this compiled command is qualified, not a portable DLL closure.
        copied=self.root/'copied compiler'/Path(h.NEX).name;copied.parent.mkdir();shutil.copy2(h.NEX,copied)
        env['PATH']=str(Path(h.NEX).parent)+os.pathsep+env.get('PATH','')
        child=subprocess.run([str(copied),'explain','E_PARSE','--json'],cwd=self.root,env=env,capture_output=True,timeout=20)
        self.assertEqual(child.returncode,0,child.stderr)
        self.assertEqual(json.loads(child.stdout)['code'],'E_PARSE')

    def test_unknown_codes_and_irrelevant_options_do_not_load_a_project(self):
        (self.root/'nex.json').write_text('{');before=self.snapshot()
        cases=[(),('',),('E_NOT_A_COMPILED_DIAGNOSTIC',),('E_',),('e_PARSE',),('E_PARSE\n',),
            ('E_🧠',),('E_'+'A'*127,),('../E_PARSE',),('--kind','other'),
            ('E_PARSE','--kind','index'),('--kind','index','--kind','index'),
            ('E_PARSE','--output','never.json'),('E_PARSE','--profile','release'),
            ('E_PARSE','--interpreter-only'),('E_PARSE','--task-steps','1'),('E_PARSE','--','extra')]
        for arguments in cases:
            with self.subTest(arguments=arguments):
                failed=self.cli('explain',*arguments,ok=False)
                self.assertEqual(failed['code'],'E_OPTION')
                self.assertEqual(self.snapshot(),before)

    def test_every_illustrative_pair_is_rejected_and_corrected_by_the_actual_checker(self):
        index=self.cli('explain','--kind','index');count=0
        for code in index['codes']:
            for example in self.cli('explain',code)['examples']:
                with self.subTest(code=code,pair=count):
                    self.assertEqual(example['rejection_code'],code)
                    self.assertFalse(example['applies_to_user_source'])
                    self.source(example['invalid'])
                    self.assertEqual(self.cli('check',ok=False)['code'],code)
                    self.source(example['corrected']);self.cli('check')
                    count+=1
        self.assertEqual(count,9)


if __name__=='__main__':unittest.main(verbosity=2)
