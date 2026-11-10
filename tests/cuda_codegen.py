"""Public checked-AST CUDA command, graph identity and provider preparation."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import support as harness


class CudaCodegen(harness.ToolchainCase):
    def emit(self, *args, ok=True):
        return self.cli('emit', '--kind', 'cuda', '--entry', 'transform', *args, ok=ok)

    def test_reachable_f64_source_maps_and_saved_revision(self):
        self.source('''module gpu;
fn affine<T:number>(x:T,gain:T,bias:T)->T{return x*gain+bias;}
fn transform(x:f64,gain:f64)->f64{return affine<f64>(x,gain,1.0);}
server fn secret()->str{return "NEX_unreachable_CUDA_secret";}
fn main()->unit{}
''')
        checked = self.cli('check')
        before = harness.database_rows(self.root / '.nex/graph.db')
        value = self.emit('--input-layout', 'columns')
        self.assertEqual(value['schema'], 'nex.cuda-emission/1')
        self.assertEqual(value['revision'], checked['revision'])
        self.assertEqual(value['parameter_types'], ['f64', 'f64'])
        self.assertEqual(value['result_type'], 'f64')
        self.assertEqual(value['kernel'], 'nex_generated_cuda_map')
        self.assertFalse(value['driver_initialized'])
        self.assertFalse(value['device_executed'])
        self.assertNotIn('NEX_unreachable_CUDA_secret', value['source'])
        self.assertEqual(value['shader_sha256'], hashlib.sha256(value['source'].encode()).hexdigest())
        self.assertEqual(value['source_bytes'], len(value['source'].encode()))
        self.assertTrue(value['floating_point']['positive_zero_normalized'])
        self.assertEqual(value['floating_point']['rounding'], 'nearest_ties_even')
        self.assertIn('mul.rn.f64', value['source'])
        self.assertIn('add.rn.f64', value['source'])
        lines = value['source'].splitlines()
        for row in value['function_map']:
            self.assertEqual(row['hash'], value['functions'][row['name']])
            self.assertIn(row['symbol']+'(', lines[row['generated_first_line']-1])
            self.assertEqual(lines[row['generated_last_line']-1], '}')
        index = self.cli('describe', '--kind', 'index')
        for name in ['compiler_build', 'descriptor_hash', 'language', 'toolchain']:
            self.assertEqual(value[name], index[name])
        self.assertEqual(harness.database_rows(self.root / '.nex/graph.db'), before)
        self.file.write_text(self.file.read_text().replace('x,gain,1.0', 'x,gain,2.0'))
        self.cli('check')
        old = self.emit('--revision', checked['revision'], '--input-layout', 'columns')
        self.assertEqual(old, value)

    def test_integer_match_layouts_and_preserved_output_on_rejection(self):
        self.source('module gpu;fn transform(x:i64)->i64{return match x{0=>42,n if n>0=>n+1,_=>0};}fn main()->unit{}')
        self.cli('check')
        rows = self.emit()
        self.assertNotIn('floating_point', rows)
        self.assertIn('const long long *input,', rows['source'])
        output = self.root / 'kernel % 🧠.cu'
        columns = self.emit('--input-layout', 'columns', '-o', output)
        self.assertNotIn('source', columns)
        self.assertEqual(columns['shader_sha256'], hashlib.sha256(output.read_bytes()).hexdigest())
        self.assertIn('const long long *input_0,', output.read_text())
        for source, code in [
                ('fn transform(x:list<i64>)->list<i64>{return x;}', 'E_GPU_TYPE'),
                ('fn transform(x:i64)->i64 !{io}{print(x);return x;}', 'E_GPU_REALM'),
                ('fn transform(x:i64)->i64{return transform(x);}', 'E_GPU_RECURSION'),
                ('fn transform(x:bytes)->bytes{return x;}', 'E_GPU_TYPE')]:
            with self.subTest(code=code):
                self.source('module gpu;'+source+'fn main()->unit{}')
                self.cli('check')
                output.write_bytes(b'preserve shader')
                self.assertEqual(self.emit('-o', output, ok=False)['code'], code)
                self.assertEqual(output.read_bytes(), b'preserve shader')

    def test_preparation_defaults_to_the_public_compiler(self):
        self.source('module gpu;fn transform(x:f64)->f64{return x/2.0;}fn main()->unit{}')
        self.cli('check')
        before = harness.database_rows(self.root / '.nex/graph.db')
        out = self.root / 'prepared % 🧠'
        command = [sys.executable, '-B', harness.REPO / 'experiments/owned-cuda-codegen/prepare.py',
            '--compiler', harness.NEX, '--resources', harness.REPO,
            '--source-project', self.root, '--symbol', 'transform', '--source-only', '--output', out]
        result = subprocess.run(list(map(str, command)), cwd=self.root, capture_output=True,
            text=True, timeout=90, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
        r = json.loads((out / 'preparation/report.json').read_bytes())
        self.assertEqual(r['emitter'], 'public_checked_AST')
        self.assertEqual(r['emission_schema'], 'nex.cuda-emission/1')
        self.assertIsNone(r['frontend_archive_sha256'])
        self.assertTrue(r['all_f64_interface'])
        self.assertEqual(len(r['signature_sha256']), 11)
        generation = next(c for c in r['commands'] if c['label']=='generate')
        self.assertEqual(Path(generation['argv'][0]).resolve(), Path(harness.NEX).resolve())
        self.assertEqual(generation['argv'][1:4], ['emit', '--kind', 'cuda'])
        self.assertFalse(r['native_provider_built'])
        self.assertFalse(r['hardware_executed'])
        self.assertFalse((out / 'bundle').exists())
        self.assertEqual(harness.database_rows(self.root / '.nex/graph.db'), before)

    def test_capability_pack_and_options(self):
        pack = json.loads((harness.REPO / 'llm/language-pack.json').read_bytes())
        value = self.cli('describe', '--field', 'gpu_codegen.cuda')['value']
        self.assertEqual(value, pack['gpu_codegen']['cuda'])
        self.assertTrue((harness.REPO / value['schema_file']).is_file())
        self.assertEqual(self.cli('guide', '--kind', 'gpu')['text'], (harness.REPO / value['guide']).read_text())
        for args in [('--target', 'native'), ('--library',), ('--input-layout', 'invalid'), ('--', 'argument')]:
            self.assertEqual(self.emit(*args, ok=False)['code'], 'E_OPTION')
        self.assertFalse((self.root / '.nex').exists())


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v'])
