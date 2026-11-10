"""Actual checked-AST Metal emission, source identities and rejected programs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
import support as harness


class MetalCodegen(harness.ToolchainCase):
    def emit(self, *args, ok=True):
        return self.cli('emit', '--kind', 'metal', '--entry', 'transform', *args, ok=ok)

    def prepare_owned(self, name, ok=True):
        sdk = self.root / ('SDK ' + name)
        (sdk / 'bin').mkdir(parents=True)
        (sdk / 'share').mkdir()
        (sdk / 'bin' / ('nex.exe' if os.name == 'nt' else 'nex')).symlink_to(harness.NEX)
        (sdk / 'share/nex').symlink_to(harness.REPO, target_is_directory=True)
        output = self.root / ('prepared % 🧠 ' + name)
        # Source-only preparation must need neither Apple's SDK nor C++/GPU.
        command = [sys.executable, '-B', harness.REPO / 'experiments/owned-metal-codegen/prepare.py',
            '--sdk', sdk, '--source-project', self.root, '--symbol', 'transform',
            '--output', output, '--check-sdk', '--cxx', self.root / 'unavailable compiler']
        result = subprocess.run(list(map(str, command)), cwd=self.root, capture_output=True,
            text=True, encoding='utf-8', timeout=180,
            env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'SDKROOT': str(self.root / 'unavailable SDK')})
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return output, result

    def test_owned_preparation_uses_public_emission_and_exact_source_identity(self):
        self.source('''module gpu;
fn identity<T>(x:T)->T{return x;}
fn transform(x:i64,add:bool)->i64 requires(x>=0) ensures(r=>r>=x){
 if add{return identity<i64>(x)+1;}return x;
}
server fn unused()->str{return "unreachable provider secret";}
fn main()->unit{}
''')
        checked = self.cli('check')
        before = harness.database_rows(self.root / '.nex/graph.db')
        expected = self.emit('--input-layout', 'columns')
        output, _ = self.prepare_owned('public')
        report = json.loads((output / 'preparation/report.json').read_bytes())
        emission = json.loads((output / 'generation/report.json').read_bytes())
        self.assertEqual(report['emitter'], 'public_checked_AST')
        self.assertEqual(report['emission_schema'], 'nex.metal-emission/1')
        self.assertEqual(report['source_revision'], checked['revision'])
        self.assertEqual(report['root'], expected['entry'])
        self.assertEqual(report['root_hash'], expected['functions'][expected['entry']])
        for name in ['functions', 'function_map', 'compiler_build', 'descriptor_hash', 'toolchain']:
            self.assertEqual(report[name], expected[name])
        self.assertEqual(emission['shader_sha256'], expected['shader_sha256'])
        self.assertEqual(report['emission_sha256'], hashlib.sha256((output / 'generation/report.json').read_bytes()).hexdigest())
        self.assertEqual(report['compiler_sha256'], hashlib.sha256(Path(harness.NEX).read_bytes()).hexdigest())
        self.assertEqual(len(report['signature_sha256']), 9)
        self.assertTrue(report['source_checked'])
        for name in ['driver_initialized', 'hardware_executed', 'native_provider_built']:
            self.assertFalse(report[name])
        generation = next(row for row in report['commands'] if row['label'] == 'generate')
        self.assertEqual(Path(generation['argv'][0]).resolve(), Path(harness.NEX))
        self.assertEqual(generation['argv'][1:4], ['emit', '--kind', 'metal'])
        self.assertEqual(Path(generation['cwd']), self.root.resolve())
        shader = (output / 'generation/kernel.metal').read_bytes()
        header = (output / 'preparation/inputs/generated_kernel.h').read_text(encoding='utf-8')
        embedded = next(line[len('#define GENERATED_MSL '):] for line in header.splitlines() if line.startswith('#define GENERATED_MSL '))
        self.assertEqual(json.loads(embedded).encode('utf-8'), shader)
        self.assertEqual(report['kernel_sha256'], hashlib.sha256(shader).hexdigest())
        self.assertNotIn(b'unreachable provider secret', shader)
        self.assertIn(report['root_hash'], (output / 'main.nex').read_text())
        for name, digest in report['source_input_pins'].items():
            self.assertEqual(hashlib.sha256((output / 'preparation/inputs' / name).read_bytes()).hexdigest(), digest)
        self.assertEqual(harness.database_rows(self.root / '.nex/graph.db'), before)

    def test_owned_preparation_keeps_zero_unit_and_eight_argument_contracts(self):
        for i, (source, count, result) in enumerate([
                ('fn transform()->unit{assert(true);}', 0, 'unit'),
                ('fn transform(a:i64,b:bool,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64)->bool{return b&&a==h;}', 8, 'bool')]):
            with self.subTest(parameters=count):
                self.source('module gpu;' + source + 'fn main()->unit{}')
                output, _ = self.prepare_owned(str(i))
                report = json.loads((output / 'preparation/report.json').read_bytes())
                self.assertEqual(len(report['parameter_types']), count)
                self.assertEqual(report['result_type'], result)
                self.assertIn('#define GENERATED_ARGUMENTS ' + str(count) + '\n',
                    (output / 'preparation/inputs/generated_kernel.h').read_text())
                self.assertFalse((output / 'bundle').exists())

    def test_owned_preparation_preserves_gpu_rejection_without_fallback(self):
        self.source('module gpu;fn transform(x:f64)->f64{return x;}fn main()->unit{}')
        self.cli('check')
        before = harness.database_rows(self.root / '.nex/graph.db')
        output, result = self.prepare_owned('rejected', ok=False)
        self.assertIn('E_GPU_TYPE', result.stderr)
        self.assertFalse((output / 'generation/kernel.metal').exists())
        self.assertFalse((output / 'preparation/report.json').exists())
        self.assertFalse((output / 'bundle').exists())
        self.assertEqual(harness.database_rows(self.root / '.nex/graph.db'), before)

    def test_reachable_source_hashes_mapping_and_saved_revision(self):
        self.source('''module gpu;
fn unused()->str{return "NEX_unreachable_device_secret";}
server fn unused_server()->unit !{io}{print("NEX_unreachable_server_secret");}
fn helper(x:i64)->i64{return x*2;}
fn transform(x:i64,bias:i64)->i64{return helper(x)+bias;}
fn main()->unit !{io}{print(transform(20,2));}
test fn answer()->unit{assert(transform(20,2)==42);}
''')
        checked = self.cli('check')
        graph = self.cli('graph')
        before = harness.database_rows(self.root / '.nex/graph.db')
        value = self.emit()
        self.assertEqual(value['schema'], 'nex.metal-emission/1')
        self.assertEqual(value['revision'], checked['revision'])
        self.assertEqual(value['entry'], 'gpu::transform')
        self.assertEqual(value['parameter_types'], ['i64', 'i64'])
        self.assertEqual(value['result_type'], 'i64')
        self.assertFalse(value['driver_initialized'])
        self.assertFalse(value['device_executed'])
        source = value['source']
        self.assertEqual(value['source_bytes'], len(source.encode('utf-8')))
        self.assertEqual(value['shader_sha256'], hashlib.sha256(source.encode()).hexdigest())
        self.assertNotIn('NEX_unreachable_', source)
        self.assertEqual(set(value['functions']), {'gpu::helper', 'gpu::transform'})
        nodes = {node['name']: node for node in graph['nodes']}
        lines = source.splitlines()
        for row in value['function_map']:
            self.assertEqual(row['hash'], nodes[row['name']]['hash'])
            self.assertEqual(value['functions'][row['name']], row['hash'])
            self.assertIn(row['symbol'] + '(', lines[row['generated_first_line'] - 1])
            self.assertEqual(lines[row['generated_last_line'] - 1], '}')
            self.assertEqual(Path(row['source_file']), self.file.relative_to(self.root))
            self.assertGreater(row['source_line'], 1)
        index = self.cli('describe', '--kind', 'index')
        for name in ['compiler_build', 'descriptor_hash', 'language', 'toolchain']:
            self.assertEqual(value[name], index[name])
        self.assertEqual(harness.database_rows(self.root / '.nex/graph.db'), before)
        # Source emission cannot change the checked function's existing paths.
        self.assertEqual(self.cli('eval')['stdout'], '42\n')
        self.assertEqual(len(self.cli('test')['tests']), 1)
        original = value
        self.file.write_text(self.file.read_text().replace('helper(x)+bias', 'helper(x)+bias+1'))
        newer = self.cli('check')
        self.assertNotEqual(newer['revision'], checked['revision'])
        before = harness.database_rows(self.root / '.nex/graph.db')
        # An explicit saved revision does not parse or overwrite live source.
        self.file.write_text('invalid current physical source')
        saved = self.emit('--revision', checked['revision'])
        for name in ['revision', 'functions', 'shader_sha256', 'source']:
            self.assertEqual(saved[name], original[name])
        self.assertEqual(harness.database_rows(self.root / '.nex/graph.db'), before)
        self.assertEqual(self.file.read_text(), 'invalid current physical source')

    def test_layouts_generic_contracts_and_binary_file_hash(self):
        self.source('''module gpu;
fn identity<T>(x:T)->T{return x;}
fn transform(x:i64,bias:i64)->i64 requires(x>=0) ensures(r=>r>=x){
 var i:i64=0;var answer:i64=identity<i64>(x);
 while i<bias invariant(i>=0) decreases(bias-i){answer=answer+1;i=i+1;}
 return answer;
}
fn main()->unit{}
''')
        target = self.root / 'shader % 🧠.metal'
        for layout in ['rows', 'columns']:
            value = self.emit('--input-layout', layout, '-o', target)
            self.assertNotIn('source', value)
            self.assertEqual(Path(value['path']), target)
            self.assertEqual(value['input_layout'], layout)
            data = target.read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), value['shader_sha256'])
            self.assertNotIn(b'\r', data)
            text = data.decode('utf-8')
            if layout == 'columns':
                self.assertIn('input_0 [[buffer(0)]]', text)
                self.assertIn('output [[buffer(8)]]', text)
            else:
                self.assertIn('input[lane * 2u + 0u]', text)
            self.assertTrue(any('<i64>' in name for name in value['functions']))

    def test_unit_boolean_zero_and_eight_arguments(self):
        cases = [
            ('fn transform()->i64{return 42;}', [], 'i64'),
            ('fn transform(x:bool,y:bool)->bool{return x&&(y||!x);}', ['bool', 'bool'], 'bool'),
            ('fn transform(x:i64)->unit{assert(x>0);}', ['i64'], 'unit'),
            ('fn transform(a:i64,b:i64,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64)->i64{return a+h;}', ['i64'] * 8, 'i64')]
        for source, types, result in cases:
            with self.subTest(source=source):
                self.source('module gpu;' + source + 'fn main()->unit{}')
                value = self.emit('--input-layout', 'columns')
                self.assertEqual(value['parameter_types'], types)
                self.assertEqual(value['result_type'], result)

    def test_accepted_NEX_outside_scalar_backend_is_rejected_at_source(self):
        cases = [
            ('fn transform(x:f64)->f64{return x;}', 'E_GPU_TYPE'),
            ('fn transform(x:str)->str{return x;}', 'E_GPU_TYPE'),
            ('fn transform(x:list<i64>)->i64{return x[0];}', 'E_GPU_TYPE'),
            ('fn transform(x:i64)->result<i64>{return ok(x);}', 'E_GPU_TYPE'),
            ('client fn transform(x:i64)->i64{return x;}', 'E_GPU_REALM'),
            ('server fn transform(x:i64)->i64{return x;}', 'E_GPU_REALM'),
            ('fn transform(x:i64)->i64 !{io}{print(x);return x;}', 'E_GPU_REALM'),
            ('fn transform(x:i64)->i64{return match x{0=>1,_=>x};}', 'E_GPU_UNSUPPORTED'),
            ('fn transform(x:i64)->i64{try{return x;}finally{assert(true);}}', 'E_GPU_UNSUPPORTED'),
            ('fn transform(x:i64)->i64{let f:fn(i64)->i64=fn(y:i64)->i64{return y;};return f(x);}', 'E_GPU_TYPE'),
            ('fn transform()->i64{return len("abc");}', 'E_GPU_UNSUPPORTED'),
            ('fn transform(x:i64)->i64{if x==0{return 0;}return transform(x-1);}', 'E_GPU_RECURSION'),
            ('fn other(x:i64)->i64{return transform(x);}fn transform(x:i64)->i64{return other(x);}', 'E_GPU_RECURSION'),
            ('fn transform(a:i64,b:i64,c:i64,d:i64,e:i64,f:i64,g:i64,h:i64,i:i64)->i64{return a;}', 'E_GPU_LIMIT')]
        artifact = self.root / 'preserved.metal'
        for source, code in cases:
            with self.subTest(code=code, source=source):
                self.source('module gpu;\n' + source + '\nfn main()->unit{}')
                self.cli('check')
                artifact.write_bytes(b'preserve existing shader\n')
                value = self.emit('-o', artifact, ok=False)
                self.assertEqual(value['code'], code)
                self.assertEqual(artifact.read_bytes(), b'preserve existing shader\n')

    def test_public_limits_reject_depth_and_width_but_allow128_functions(self):
        body = ''.join('fn h'+str(i)+'()->unit{}' for i in range(127))
        calls = ''.join('h'+str(i)+'();' for i in range(127))
        self.source('module gpu;' + body + 'fn transform()->unit{' + calls + '}fn main()->unit{}')
        self.assertEqual(len(self.emit()['functions']), 128)
        self.source('module gpu;' + body + 'fn extra()->unit{}fn transform()->unit{' + calls + 'extra();}fn main()->unit{}')
        self.assertEqual(self.emit(ok=False)['code'], 'E_GPU_LIMIT')
        chain = ''.join('fn h'+str(i)+'()->unit{h'+str(i+1)+'();}' for i in range(128))
        self.source('module gpu;' + chain + 'fn h128()->unit{}fn transform()->unit{h0();}fn main()->unit{}')
        self.assertEqual(self.emit(ok=False)['code'], 'E_GPU_LIMIT')

    def test_discovery_manifest_guide_and_invalid_options(self):
        full = self.cli('describe')
        pack = json.loads((harness.REPO / 'llm/language-pack.json').read_bytes())
        self.assertEqual(full['gpu_codegen'], pack['gpu_codegen'])
        guide = self.cli('guide', '--kind', 'gpu')
        self.assertEqual(guide['text'], (harness.REPO / 'docs/gpu-codegen.md').read_text())
        self.assertTrue((harness.REPO / full['gpu_codegen']['schema_file']).is_file())
        for args in [('--input-layout', 'unknown'), ('--target', 'native'), ('--library',),
                     ('--profile', 'release'), ('--directory', 'unused'), ('--', 'argument')]:
            with self.subTest(args=args):
                self.assertEqual(self.emit(*args, ok=False)['code'], 'E_OPTION')
        self.assertEqual(self.cli('check', '--input-layout', 'rows', ok=False)['code'], 'E_OPTION')
        self.assertFalse((self.root / '.nex').exists())


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v'])
