"""Scalar Wasm f64 ABI, finite checks and Node execution."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

COMPILER=Path(sys.argv.pop(1)).resolve()
SOURCE='''module wasm_float;
pub fn compute(x: f64) -> f64 { return x * 2.0 + 1.0; }
pub fn less(x: f64, y: f64) -> bool { return x < y; }
pub fn bad(x: f64) -> f64 { return x / 0.0; }
fn main() -> unit !{io} { print(compute(20.5)); }
'''


def run(args,cwd,environment=None):
    return subprocess.run(list(map(str,[COMPILER]+args)),cwd=cwd,capture_output=True,text=True,
        timeout=240,env={**os.environ,**(environment or {})})

class WasmF64(unittest.TestCase):
    def test_build_and_node(self):
        doctor=run(['doctor','--json'],Path.cwd())
        if doctor.returncode: raise unittest.SkipTest('doctor failed')
        linker=json.loads(doctor.stdout).get('wasm_linker','')
        if not linker or not Path(linker).is_file(): raise unittest.SkipTest('matching wasm-ld is not installed')
        node=os.environ.get('NEX_NODE','node')
        if not shutil.which(node) and not Path(node).is_file(): raise unittest.SkipTest('Node is not installed')
        with tempfile.TemporaryDirectory(prefix='nex wasm f64 ') as temporary:
            root=Path(temporary)
            (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
            (root/'main.nex').write_text(SOURCE)
            builds={}
            for entry in ('compute','less','bad'):
                result=run(['build','main.nex','--target','wasm','--entry',entry,'--profile','release',
                    '--output',str(root/entry),'--json'],root)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
                builds[entry]=json.loads(result.stdout)
                self.assertTrue(Path(builds[entry]['module']).is_file())
            body='import fs from "node:fs";\n'
            for key in ('compute','less','bad'):
                body+=f'import {{createNexWasm as {key[0].upper()},descriptor as {key[0].upper()}D}} from '+json.dumps(Path(builds[key]['wrapper']).as_uri())+';\n'
            for key in ('compute','less','bad'):
                body+=f'const {key}=await {key[0].upper()}(fs.readFileSync({json.dumps(builds[key]["module"])}));\n'
            body+='''if(compute.call([20.5])!==42||less.call([1.5,2.5])!==true||less.call([2.5,1.5])!==false)throw Error("f64 value");
for(const value of [NaN,Infinity,-Infinity]){let code;try{compute.call([value])}catch(error){code=error.code;}if(code!=="E_WASM_INPUT")throw Error("nonfinite input accepted");}
let code;try{bad.call([1])}catch(error){code=error.code;}if(code!=="E_FLOAT")throw Error("nonfinite result not rejected");
console.log(JSON.stringify({ok:true,params:CD.parameters,result:CD.result,less:LD.result}));
'''
            (root/'driver.mjs').write_text(body)
            result=subprocess.run([node,str(root/'driver.mjs')],cwd=root,capture_output=True,text=True,timeout=120)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            report=json.loads(result.stdout)
            self.assertEqual(report['params'],['f64'])
            self.assertEqual(report['result'],'f64')
            self.assertEqual(report['less'],'bool')

if __name__=='__main__':unittest.main()
