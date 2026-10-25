"""Actual provider template/signature checks; native tests stop at a declared compiler boundary."""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('compiler',type=Path);args,remaining=parser.parse_known_args()
COMPILER=args.compiler.resolve();sys.argv=[sys.argv[0],*remaining]
EVIDENCE=Path(os.environ['NEX_PROVIDER_PREPARATION_EVIDENCE']) if os.environ.get('NEX_PROVIDER_PREPARATION_EVIDENCE') else None
if EVIDENCE:EVIDENCE.mkdir(parents=True,exist_ok=True)
spec=importlib.util.spec_from_file_location('provider_sdk_test',ROOT/'tools/provider_sdk.py')
helper=importlib.util.module_from_spec(spec);spec.loader.exec_module(helper)


class ProviderPreparation(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='nex provider 🧠 ')
        self.addCleanup(self.temporary.cleanup);self.root=Path(self.temporary.name)
        self.sdk=self.root/'SDK';(self.sdk/'bin').mkdir(parents=True);(self.sdk/'share').mkdir()
        (self.sdk/'bin/nex').symlink_to(COMPILER);(self.sdk/'share/nex').symlink_to(ROOT)
        self.env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1','NEX_RESOURCE_DIR':str(ROOT)}
        result=subprocess.run([str(COMPILER),'describe','--json'],cwd=self.root,env=self.env,capture_output=True,text=True,check=True)
        self.descriptor=json.loads(result.stdout)

    def execute(self,script,*arguments,success=True):
        result=subprocess.run([sys.executable,str(script),'--sdk',str(self.sdk),*map(str,arguments)],
            cwd=self.root,env=self.env,capture_output=True,text=True,timeout=120)
        self.assertEqual(result.returncode==0,success,(result.stdout,result.stderr))
        return result

    def test_current_compiler_checks_real_model_GPU_and_NPU_templates(self):
        cases=[('models',[]),('rk3588',['--backend','gpu']),('rk3588',['--backend','gpu','--api','compute']),('rk3588',['--backend','npu'])]
        for provider,arguments in cases:
            with self.subTest(provider=provider,arguments=arguments):
                result=self.execute(ROOT/'experiments'/provider/'prepare.py',*arguments,'--check-sdk')
                report=json.loads(result.stdout)
                self.assertEqual(report['schema'],'nex.provider-sdk-check/1')
                self.assertIs(report['ok'],True);self.assertIs(report['source_checked'],True)
                self.assertEqual(report['source_language'],self.descriptor['version'])
                self.assertEqual(report['compiler_sha256'],hashlib.sha256(COMPILER.read_bytes()).hexdigest())
                self.assertIs(report['native_worker_built'],False);self.assertIs(report['hardware_executed'],False)
                self.assertIs(report['temporary_project_removed'],True)
                self.assertEqual(len(report['signature_sha256']),1)
                for symbol,signature in report['signatures'].items():
                    self.assertEqual(signature['schema'],'nex.foreign-signature/1')
                    self.assertEqual(report['signature_sha256'][symbol],hashlib.sha256(json.dumps(signature,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest())
                self.assertEqual(report['source_sha256'],hashlib.sha256(report['probe_source'].encode()).hexdigest())
                self.assertEqual([row['exit_code'] for row in report['commands']],[0,0,0])
                self.assertEqual(len(report['checked_revision']),64)
                if EVIDENCE:(EVIDENCE/(provider+'-'+('-'.join(arguments) if arguments else 'default')+'.json')).write_text(json.dumps(report,indent=2)+'\n')

    def test_native_model_and_compute_paths_use_the_current_source_checker(self):
        # Only platform selection is simulated. NEX checks the real generated
        # sources/signature; a deliberate compiler exit prevents native code,
        # runtime initialization or inference from being mistaken for proof.
        compiler=self.root/'stop at native compiler';capture=self.root/'native-compiler.json'
        compiler.write_text('#!'+sys.executable+'\nimport json,sys\nfrom pathlib import Path\nPath('+repr(str(capture))+').write_text(json.dumps(sys.argv))\nsys.stderr.write("NEX_TEST_NATIVE_BOUNDARY\\n")\nsys.exit(73)\n');compiler.chmod(0o755)
        model=self.root/'model.onnx';model.write_bytes(b'not an inference artifact: source preparation fixture')
        library=self.root/'runtime.so';library.write_bytes(b'not loaded: source preparation fixture')
        headers=self.root/'headers';headers.mkdir();specification=self.root/'spec.json'
        specification.write_text(json.dumps({'schema':'nex.model-artifact/1','id':'source-check',
            'sha256':hashlib.sha256(model.read_bytes()).hexdigest(),
            'inputs':[{'name':'X','dtype':'u8','shape':[1]}],'outputs':[{'name':'Y','dtype':'u8','shape':[1]}]}))
        for provider,arguments in [('models',['--model',model,'--spec',specification,'--ort-library',library,'--include',headers]),
                                   ('rk3588',['--backend','gpu','--api','compute','--opencl-library',library])]:
            with self.subTest(provider=provider):
                if capture.exists():capture.unlink()
                output=self.root/provider
                runner='import importlib.util,sys;spec=importlib.util.spec_from_file_location("provider",sys.argv[1]);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.platform.system=lambda:"Linux";module.platform.machine=lambda:"aarch64";sys.argv=sys.argv[1:];module.main()'
                result=subprocess.run([sys.executable,'-c',runner,str(ROOT/'experiments'/provider/'prepare.py'),
                    '--sdk',str(self.sdk),'--output',str(output),'--cxx',str(compiler),*map(str,arguments)],
                    cwd=self.root,env=self.env,capture_output=True,text=True,timeout=120)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('NEX_TEST_NATIVE_BOUNDARY',result.stderr)
                self.assertTrue(capture.is_file(),'provider rejected current source before reaching native preparation')
                self.assertEqual(json.loads((output/'nex.json').read_text())['language'],self.descriptor['version'])
                self.assertTrue((output/'main.nex').is_file())
                signature=json.loads((output/'prepare-1.stdout').read_text())
                self.assertEqual(signature['schema'],'nex.foreign-signature/1')
                self.assertTrue(signature['types'])
                self.assertTrue(any(str(argument).endswith('-worker.cpp') for argument in json.loads(capture.read_text())))
                if EVIDENCE:
                    directory=EVIDENCE/('native-boundary-'+provider);directory.mkdir()
                    for path in [*output.glob('prepare-*.stdout'),*output.glob('prepare-*.stderr'),output/'main.nex',output/'nex.json',capture]:
                        (directory/path.name).write_bytes(path.read_bytes())
                    (directory/'boundary.stderr').write_text(result.stderr)
                    (directory/'scope.json').write_text(json.dumps({'platform_selection_simulated':'Linux ARM64','actual_NEX_source_and_signature_check':True,'compiler_sha256':hashlib.sha256(COMPILER.read_bytes()).hexdigest(),'native_compiler_deliberately_stopped':True,'native_worker_built':False,'hardware_executed':False})+'\n')

    def test_versions_require_capabilities_and_supported_contracts(self):
        for language in ['0.20','0.21','0.23','0.23']:
            value=copy.deepcopy(self.descriptor);value['version']=language
            self.assertEqual(helper.source_language(value,'model'),language)
        for language in ['0.19','0.022','1.0','0.22.1','0.٢٢','']:
            value=copy.deepcopy(self.descriptor);value['version']=language
            with self.subTest(language=language),self.assertRaises(RuntimeError):helper.source_language(value)
        for value in [False,None,1,'true']:
            descriptor=copy.deepcopy(self.descriptor);descriptor['foreign_boundary']['source_support']=value
            with self.subTest(source_support=value),self.assertRaises(RuntimeError):helper.source_language(descriptor)
        for field,value in [('contract_version',2),('contract_version',True),('source_support',False),('import','wrong.nex')]:
            descriptor=copy.deepcopy(self.descriptor);descriptor['model'][field]=value
            with self.subTest(field=field,value=value),self.assertRaises(RuntimeError):helper.source_language(descriptor,'model')

    def test_source_check_refuses_ambiguous_native_inputs(self):
        self.execute(ROOT/'experiments/models/prepare.py','--check-sdk','--output',self.root/'ignored',success=False)
        self.execute(ROOT/'experiments/rk3588/prepare.py','--check-sdk','--backend','gpu','--opencl-library',self.root/'ignored',success=False)
        self.execute(ROOT/'experiments/rk3588/prepare.py','--check-sdk','--backend','npu','--api','compute',success=False)


if __name__=='__main__':unittest.main(verbosity=2)
