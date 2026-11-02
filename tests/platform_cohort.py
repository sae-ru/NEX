"""Platform preparation selects actual compiler identities and preserves stores."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

import support as harness

sys.path.insert(0, str(harness.REPO/'tools'))
from compiler_cohort import compiler_cohort, compiler_field, typed_task_abi

spec = importlib.util.spec_from_file_location('windows_acceptance', harness.REPO/'tools/windows/acceptance.py')
windows = importlib.util.module_from_spec(spec)
spec.loader.exec_module(windows)


class PlatformCohort(harness.ToolchainCase):
    def test_current_discovery_and_mixed_identity_refusal(self):
        doctor = self.cli('doctor')
        index = self.cli('describe', '--kind', 'index')
        cohort = compiler_cohort(doctor, index)
        self.assertEqual(cohort['language'], harness.CURRENT_LANGUAGE)
        field = self.cli('describe', '--field', 'source_exceptions.source_providers')
        self.assertEqual(typed_task_abi(cohort, field), 7)
        self.assertEqual(compiler_field(cohort, field, field['field']), field['value'])
        for key, value in [('language','0.27' if cohort['language']=='0.28' else '0.28'),
                           ('version','0.0.0')]:
            changed = {**doctor, key:value}
            with self.subTest(key=key), self.assertRaisesRegex(RuntimeError, 'different compiler versions'):
                compiler_cohort(changed, index)
        for key, value in [('language','0.29'),('compiler_build','invalid'),
                           ('descriptor_hash',None),('kind','field')]:
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                compiler_cohort(doctor, {**index,key:value})
        for key in cohort:
            with self.subTest(field_key=key), self.assertRaisesRegex(RuntimeError, 'identity changed'):
                compiler_field(cohort, {**field,key:'other'}, field['field'])
        for key,value in [('descriptor_abi','0x4e45585400000006'),
                          ('source_languages',cohort['language']+'-malformed')]:
            wrong = copy.deepcopy(field)
            wrong['value'][key] = value
            with self.subTest(provider_key=key),self.assertRaisesRegex(RuntimeError,'ABI7'):
                typed_task_abi(cohort, wrong)

    def test_retained_windows_discovery_keeps_its_own_version(self):
        retained = json.loads((harness.REPO/'docs/evidence/windows-host-2026-10-31.json').read_text())
        doctor, index = retained['compiler']['doctor'], retained['compiler']['index']
        cohort = compiler_cohort(doctor, index)
        self.assertEqual(cohort['language'], '0.27')
        self.assertEqual(cohort['toolchain'], doctor['version'])
        self.assertNotEqual(cohort['compiler_build'], self.cli('describe','--kind','index')['compiler_build'])

    def test_windows_resume_does_not_retag_or_rewrite_checked_history(self):
        language = compiler_cohort(self.cli('doctor'), self.cli('describe','--kind','index'))['language']
        source = 'module resume_project; fn main()->unit !{io}{print("Я🧠42");}\n'
        folder = windows.prepare_project(self.root/'project', source, language)
        self.cli('check', cwd=folder)
        graph = folder/'.nex/graph.db'
        before_graph = harness.database_rows(graph)
        before = {p.name:p.read_bytes() for p in [folder/'nex.json', folder/'main.nex']}
        windows.prepare_project(folder, source, language, resume=True)
        self.assertEqual({name:(folder/name).read_bytes() for name in before},before)
        self.assertEqual(harness.database_rows(graph),before_graph)
        self.assertEqual(self.cli('eval',cwd=folder)['stdout'],'Я🧠42\n')
        for candidate, selected in [(source+'// changed\n', language), (source, '0.27' if language=='0.28' else '0.28')]:
            with self.assertRaisesRegex(RuntimeError,'new output directory'):
                windows.prepare_project(folder,candidate,selected,resume=True)
            self.assertEqual({name:(folder/name).read_bytes() for name in before},before)
            self.assertEqual(harness.database_rows(graph),before_graph)
        # Preserve original physical bytes too, including a Windows CRLF source.
        (folder/'main.nex').write_bytes(source.replace('\n','\r\n').encode())
        crlf = (folder/'main.nex').read_bytes()
        windows.prepare_project(folder,source,language,resume=True)
        self.assertEqual((folder/'main.nex').read_bytes(),crlf)

    def test_cuda_source_preparation_checks_actual_signatures_without_hardware(self):
        out = self.root/'CUDA source % 🧠'
        result = subprocess.run([sys.executable, '-B', str(harness.REPO/'experiments/owned-cuda/prepare.py'),
            '--compiler', harness.NEX, '--source-only', '--output', str(out)],
            env=os.environ, capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        report = json.loads((out/'preparation/report.json').read_text())
        self.assertEqual(report['schema'],'nex.owned-cuda-source-preparation/1')
        self.assertEqual(report['source_language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(report['source_task_ABI'],7)
        self.assertTrue(report['source_only'])
        for flag in ['hardware_executed','driver_initialized','CUDA_from_NEX_accepted']:
            self.assertIs(report[flag],False)
        self.assertFalse((out/'bundle').exists())
        self.assertEqual(len(report['signatures']),7)
        for name, signature in report['signatures'].items():
            digest=hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
            self.assertEqual(report['signature_sha256'][name],digest)
            self.assertIn('#define PIN_'+name.upper()+' "'+digest+'"',(out/'generated/signatures.h').read_text())
        self.assertEqual(json.loads((out/'nex.json').read_text())['language'],harness.CURRENT_LANGUAGE)
        # Source-only checking reaches portable client code without a CUDA module.
        self.assertEqual(self.cli('eval','--entry','client_value',cwd=out)['value'],42)
        refused=self.cli('build','--entry','client_value','--profile','release',cwd=out,ok=False)
        self.assertEqual(refused['code'],'E_REALM')


if __name__ == '__main__': unittest.main()
