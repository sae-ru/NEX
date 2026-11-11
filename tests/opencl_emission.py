"""Checked scalar OpenCL C source emission."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module opencl_case;
fn twice(x: i64) -> i64 { return x * 2; }
fn transform(x: i64, bias: i64) -> i64 {
  return twice(x) + bias;
}
fn main() -> unit !{io} { print(transform(20, 2)); }
'''
FLOAT='''module opencl_float;
fn transform(x: f64) -> f64 { return x + 1.0; }
fn main() -> unit !{io} { print(transform(1.0)); }
'''


def run(args,cwd):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,timeout=180)

class OpenCL(unittest.TestCase):
    def project(self,root,source):
        (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (root/'main.nex').write_text(source)

    def test_scalar_source_compiles_and_rejects_float(self):
        with tempfile.TemporaryDirectory(prefix='nex opencl ') as temporary:
            root=Path(temporary);self.project(root,SOURCE)
            emitted=run(['emit','--kind','opencl','--entry','transform','--input-layout','rows','--json'],root)
            self.assertEqual(emitted.returncode,0,emitted.stdout+emitted.stderr)
            report=json.loads(emitted.stdout)
            self.assertEqual(report['schema'],'nex.opencl-emission/1')
            self.assertEqual(report['kind'],'opencl')
            self.assertEqual(report['kernel'],'nex_generated_map')
            self.assertFalse(report['device_executed'])
            source=report['source']
            for marker in ('__kernel void nex_generated_map','get_global_id(0)','nex_add(','__global const long *input'):
                self.assertIn(marker,source)
            self.assertNotIn('[[buffer',source)
            self.assertNotIn('metal_stdlib',source)
            clang=shutil.which('clang')
            if clang:
                (root/'kernel.cl').write_text(source)
                checked=subprocess.run([clang,'-x','cl','-cl-std=CL1.2','-fsyntax-only',str(root/'kernel.cl')],
                    capture_output=True,text=True,timeout=120)
                self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            columns=run(['emit','--kind','opencl','--entry','transform','--input-layout','columns','--json'],root)
            self.assertEqual(columns.returncode,0,columns.stdout+columns.stderr)
            column_source=json.loads(columns.stdout)['source']
            self.assertIn('__global const long *input_0',column_source)
            descriptor=json.loads(run(['describe','--field','opencl_codegen','--json'],root).stdout)['value']
            self.assertEqual(descriptor['schema'],'nex.opencl-emission/1')
            self.assertFalse(descriptor['device_execution'])

            (root/'main.nex').write_text(FLOAT)
            rejected=run(['emit','--kind','opencl','--entry','transform','--json'],root)
            self.assertNotEqual(rejected.returncode,0)
            self.assertEqual(json.loads(rejected.stdout)['code'],'E_GPU_TYPE')

if __name__=='__main__':unittest.main()
