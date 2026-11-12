"""Execute emitted scalar OpenCL kernels through the owned ctypes runner."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
RUNNER=Path(__file__).resolve().parent.parent/'tools/owned-opencl/run.py'
SOURCE='''module opencl_dispatch;
pub fn multiply(x:i64,y:i64)->i64{return x*y+1;}
pub fn scale(x:f64)->f64{return x*2.0;}
pub fn divide(x:i64)->i64{return 100/x;}
fn main()->unit !{io}{print(multiply(20,2));}
'''

def invoke(args,cwd):
    return subprocess.run([sys.executable,'-B',str(RUNNER),*args],cwd=cwd,capture_output=True,text=True,timeout=180)

class OpenCLDispatch(unittest.TestCase):
    def project(self):
        temporary=tempfile.TemporaryDirectory(prefix='nex opencl dispatch ')
        root=Path(temporary.name)
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(SOURCE)
        return temporary,root

    def test_scalar_i64_and_division_error(self):
        temporary,root=self.project()
        with temporary:
            base=['--compiler',str(COMPILER),'--project',str(root)]
            first=invoke([*base,'--entry','multiply','--args','20,2'],root)
            if first.returncode and ('no OpenCL platform' in first.stderr or 'no OpenCL GPU' in first.stderr):
                self.skipTest('OpenCL GPU is not available')
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            multiply=json.loads(first.stdout);self.assertTrue(multiply['ok']);self.assertEqual(multiply['result'],41);self.assertFalse(multiply['cpu_fallback'])
            failed=invoke([*base,'--entry','divide','--args','0'],root)
            self.assertEqual(failed.returncode,0,failed.stdout+failed.stderr)
            divide=json.loads(failed.stdout);self.assertFalse(divide['ok']);self.assertEqual(divide['error'],2)

    def test_f64_if_supported(self):
        temporary,root=self.project()
        with temporary:
            base=['--compiler',str(COMPILER),'--project',str(root)]
            first=invoke([*base,'--entry','scale','--args','20.5'],root)
            if first.returncode and ('no OpenCL platform' in first.stderr or 'no OpenCL GPU' in first.stderr or 'enqueue failed' in first.stderr):
                self.skipTest('this OpenCL device cannot enqueue f64 kernels')
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            scale=json.loads(first.stdout);self.assertTrue(scale['ok']);self.assertAlmostEqual(scale['result'],41.0)

if __name__=='__main__':unittest.main()
