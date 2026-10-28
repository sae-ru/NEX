"""Check ordinary owned-device source, realms and actual provider preparation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser();parser.add_argument('compiler',type=Path)
args,remaining=parser.parse_known_args();COMPILER=args.compiler.resolve();sys.argv=[sys.argv[0],*remaining]

class DeviceContract(unittest.TestCase):
 def setUp(self):
  temporary=tempfile.TemporaryDirectory(prefix='nex owned device 🧠 ');self.addCleanup(temporary.cleanup);self.root=Path(temporary.name)
  self.env={**os.environ,'NEX_RESOURCE_DIR':str(ROOT),'PYTHONDONTWRITEBYTECODE':'1'}
  self.descriptor=self.cli('describe')
  (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':self.descriptor['version'],'entry':'main.nex'}))
 def cli(self,*arguments,expected=0):
  result=subprocess.run([str(COMPILER),*map(str,arguments),'--json'],cwd=self.root,env=self.env,capture_output=True,text=True,timeout=180)
  self.assertEqual(result.returncode,expected,(arguments,result.stdout,result.stderr));return json.loads(result.stdout)
 def test_source_metadata_native_reference_typescript_and_replay(self):
  shutil.copyfile(ROOT/'examples/device/main.nex',self.root/'main.nex')
  self.assertEqual(self.cli('eval')['stdout'],'42\n')
  self.cli('test');self.cli('test','--target','web')
  built=self.cli('build','--profile','release');native=self.cli('run','--profile','release')
  self.assertEqual(native['stdout'],'42\n');(self.root/'main.nex').unlink()
  self.assertEqual(self.cli('run','--revision',built['revision'],'--profile','release')['stdout'],'42\n')
 def test_descriptor_guide_and_pinned_preparer_use_actual_sdk(self):
  self.assertEqual(self.descriptor['device'],json.loads((ROOT/'llm/language-pack.json').read_text())['device'])
  self.assertEqual(self.cli('guide','--kind','device')['text'],(ROOT/'docs/device.md').read_text())
  help_result=subprocess.run([sys.executable,'-B',str(ROOT/'experiments/owned-opencl/faults.py'),'--help'],capture_output=True,text=True,timeout=30)
  self.assertEqual(help_result.returncode,0,help_result.stderr)
  self.assertIn('upload_reused_id',help_result.stdout);self.assertIn('execute_fallback_never_masks_protocol',help_result.stdout)
  log_help=subprocess.run([sys.executable,'-B',str(ROOT/'experiments/owned-opencl/logs.py'),'--help'],capture_output=True,text=True,timeout=30)
  self.assertEqual(log_help.returncode,0,log_help.stderr);self.assertIn('--old-limit-red',log_help.stdout)
  sdk=self.root/'SDK';(sdk/'bin').mkdir(parents=True);(sdk/'share').mkdir()
  (sdk/'bin/nex').symlink_to(COMPILER);(sdk/'share/nex').symlink_to(ROOT)
  output=self.root/'prepared'
  result=subprocess.run([sys.executable,'-B',str(ROOT/'experiments/owned-opencl/prepare.py'),'--sdk',str(sdk),'--output',str(output),'--check-sdk'],cwd=self.root,env=self.env,capture_output=True,text=True,timeout=180)
  self.assertEqual(result.returncode,0,(result.stdout,result.stderr));report=json.loads((output/'preparation/report.json').read_text())
  self.assertTrue(report['source_checked']);self.assertFalse(report['hardware_executed']);self.assertFalse(report['driver_initialized']);self.assertFalse(report['native_provider_built'])
  self.assertEqual(report['compiler_sha256'],hashlib.sha256(COMPILER.read_bytes()).hexdigest());self.assertEqual(len(report['signature_sha256']),7)
  self.assertEqual(report['source_language'],self.descriptor['version'])
  self.assertTrue(report['source_input_sha256'])
  for name,value in report['source_input_sha256'].items():self.assertEqual(hashlib.sha256((output/'preparation/inputs'/name).read_bytes()).hexdigest(),value)
 def test_effect_realm_and_wire_boundaries(self):
  prefix='import "std/device.nex" as d;import "std/compute.nex" as c;'
  for body,codes in [
   ('fn bad(value:d::Context)->unit{}',{'E_REALM'}),
   ('server fn bad(ctx:d::Context,value:c::Tensor)->result<d::Tensor> !{ffi}{return d::upload(ctx,value);}',{'E_EFFECT'}),
   ('server fn bad(value:d::Tensor)->str{return encode_json(value);}',{'E_GENERIC_BOUND'})]:
   with self.subTest(body=body):
    (self.root/'main.nex').write_text('module invalid;'+prefix+body+'fn main()->unit{}')
    self.assertIn(self.cli('check',expected=1)['code'],codes)
 def test_browser_emits_only_reachable_client_code(self):
  shutil.copyfile(ROOT/'examples/device/main.nex',self.root/'main.nex');directory=self.root/'web'
  self.cli('emit','--kind','typescript','--entry','client_value','--directory',directory)
  emitted='\n'.join(path.read_text() for path in directory.rglob('*.ts'))
  self.assertIn('client_value',emitted)
  for forbidden in ['std::device::Session','std::device::Buffer','upload_raw','busy_raw','resource_create_with_parents']:self.assertNotIn(forbidden,emitted)

if __name__=='__main__':unittest.main()
