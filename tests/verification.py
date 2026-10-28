"""Proof obligations, actual counterexample replay and conservative proof scope."""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import unittest
import support as harness


class Verification(harness.ToolchainCase):
    def test_bundled_proof_snapshots_and_task_intent_are_current(self):
        language = self.cli('describe')['version']
        for example, filename in [('verification', 'contracts.json'), ('tasks', 'proof.json')]:
            with self.subTest(example=example):
                project = self.root / example
                shutil.copytree(harness.REPO / 'examples' / example, project)
                checked = self.cli('check', cwd=project)
                snapshot = json.loads((project / filename).read_text())
                self.assertEqual(snapshot['language'], language)
                self.assertEqual(snapshot['expected_revision'], checked['revision'])
                verified = self.cli('verify', '--contracts', filename, cwd=project, timeout=90)
                self.assertTrue(verified['ok'])
                self.assertTrue(verified['functions'])
                self.assertTrue(all(item['status'] == 'proven' for item in verified['functions']))
                if example == 'tasks':
                    task = json.loads((project / 'task.json').read_text())
                    self.assertEqual(task['programs'][0]['baseline_revision'], checked['revision'])
                    intent = self.cli('contract', '--kind', 'intent', '--contracts', filename, cwd=project)
                    proof = next(item for item in task['checks'] if item['id'] == 'proof')
                    self.assertEqual(proof['intent_hash'], intent['intent_hash'])
                    self.assertTrue(self.cli('task', 'task.json', '--kind', 'check', cwd=project)['ok'])

    def contract(self, symbol, requires=None, ensures=None):
        value = self.cli('contract', '--symbol', symbol)
        function = value['functions'][0]
        if requires is not None:
            function['requires'] = requires
        if ensures is not None:
            function['ensures'] = ensures
        return value

    def verify(self, contract, *args, ok=True):
        path = self.root / 'contracts.json'
        path.write_text(json.dumps(contract, ensure_ascii=False, indent=2) + '\n')
        return self.cli('verify', '--contracts', path, *args, ok=ok, timeout=90)

    def web(self, entry='main'):
        folder = self.root / 'typescript'
        self.cli('emit', '--kind', 'typescript', '--entry', entry, '--directory', folder)
        (folder / 'package.json').write_text('{"type":"module"}')
        (folder / 'driver.ts').write_text('''import { entry } from './program.ts';
import { str, NexError } from './nex-runtime.ts';
let stdout = '';
console.log = value => { stdout += String(value) + '\\n'; };
let result;
try { const value = entry(); result = {ok: true, value: value === undefined ? null : str(value), stdout}; }
catch(e) { if (!(e instanceof NexError)) throw e; result = {ok: false, code: e.code, stdout}; }
process.stdout.write(JSON.stringify(result));
''')
        process = subprocess.run([os.environ.get('NEX_NODE', 'node'), '--experimental-strip-types', '--no-warnings', str(folder / 'driver.ts')], capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        return json.loads(process.stdout)

    def test_branches_calls_assertions_and_graph_attribution(self):
        self.source('''module checked;
pub fn step(x: i64, up: bool) -> i64 {
  var value: i64 = x;
  if up { value = x + 1; } else { value = x - 1; }
  assert(value != x);
  return value;
}
pub fn twice(x: i64, up: bool) -> i64 { return step(x, up) * 2; }
test fn examples() -> unit { assert(step(3, true) == 4); assert(twice(3, false) == 4); }
''')
        contract = self.contract('twice', ['x >= -100', 'x <= 100'], ['result == (x + 1) * 2 || result == (x - 1) * 2'])
        callee = self.contract('step', ['x > -9223372036854775808', 'x < 9223372036854775807'], ['(up && result == x + 1) || (!up && result == x - 1)'])
        contract['functions'] += callee['functions']
        result = self.verify(contract)
        self.assertEqual(result['schema'], 'nex.verification-session/1')
        self.assertEqual(result['language'], harness.CURRENT_LANGUAGE)
        self.assertTrue(result['solver_version'].startswith('5.') or result['solver_version'].startswith('4.'))
        graph = {n['name']: n for n in self.cli('graph')['nodes']}
        saved = json.loads(Path(result['output']).read_text())
        self.assertEqual(saved['schema'], 'nex.verification/1')
        for function in saved['functions']:
            self.assertEqual(function['status'], 'proven')
            self.assertEqual(function['node_id'], graph[function['symbol']]['id'])
            self.assertEqual(function['content_hash'], graph[function['symbol']]['hash'])
            self.assertEqual(function['checked_obligations'], function['generated_obligations'])
            self.assertGreater(function['checked_obligations'], 3)
            for obligation in function['obligations']:
                self.assertTrue(Path(obligation['query']).is_file())
        self.assertIn('callee_requires', {o['kind'] for f in saved['functions'] for o in f['obligations']})
        self.cli('test')
        self.cli('test', '--target', 'web')

    def test_overflow_counterexample_replays_in_all_backends(self):
        original = 'module overflow; pub fn increment(x: i64) -> i64 { return x + 1; }\n'
        self.source(original)
        result = self.verify(self.contract('increment'), ok=False)
        function = result['functions'][0]
        self.assertEqual(function['status'], 'counterexample')
        failure = next(o for o in function['obligations'] if o['status'] == 'counterexample')
        self.assertEqual(failure['runtime_code'], 'E_OVERFLOW')
        self.assertEqual(failure['counterexample_kind'], 'concrete_input')
        self.assertEqual(failure['inputs']['x'], '9223372036854775807')
        self.source(original + 'fn main() -> i64 { return increment(' + failure['inputs']['x'] + '); }')
        self.assertEqual(self.cli('eval', ok=False)['code'], 'E_OVERFLOW')
        self.assertIn('E_OVERFLOW', self.cli('run', '--profile', 'release', ok=False)['stderr'])
        self.assertEqual(self.web()['code'], 'E_OVERFLOW')

    def test_division_remainder_signs_and_minimum_boundary(self):
        self.source('''module division;
pub fn divide(a: i64, b: i64) -> i64 { return a / b; }
pub fn remainder(a: i64, b: i64) -> i64 { return a % b; }
pub fn guarded(n: i64) -> bool { return n == 0 || 100 / n <= 100; }
''')
        self.verify(self.contract('guarded', ['n >= 0'], ['result']))
        for a, b in [(-7, 3), (-7, -3), (7, -3), (-9223372036854775808, -1)]:
            q = (abs(a) // abs(b)) * (-1 if (a < 0) != (b < 0) else 1)
            remainder = a - q * b
            contract = self.contract('remainder', [f'a == {a}', f'b == {b}'], [f'result == {remainder}'])
            self.verify(contract)
            if q > 9223372036854775807:
                result = self.verify(self.contract('divide', [f'a == {a}', f'b == {b}']), ok=False)
                self.assertEqual(result['functions'][0]['status'], 'counterexample')
            else:
                self.verify(self.contract('divide', [f'a == {a}', f'b == {b}'], [f'result == {q}']))
        zero = self.verify(self.contract('divide', ['b == 0']), ok=False)
        self.assertIn('E_DIV_ZERO', {o['runtime_code'] for o in zero['functions'][0]['obligations']})

    def test_nested_loop_invariants_termination_and_shadowing(self):
        self.source('''module loops;
pub fn count(n: i64) -> i64 {
  var i: i64 = 0; var total: i64 = 0;
  while i < n {
    var j: i64 = 0;
    while j < 2 { total = total + 1; j = j + 1; }
    if true { var i: i64 = 0; i = i + 1; assert(i == 1); }
    i = i + 1;
  }
  return total;
}
test fn examples() -> unit { assert(count(0) == 0); assert(count(8) == 16); }
''')
        contract = self.contract('count', ['n >= 0', 'n <= 1000000'], ['result == n * 2'])
        outer, inner = contract['functions'][0]['loops']
        outer.update(invariants=['i >= 0', 'i <= n', 'total == i * 2'], decreases='n - i')
        inner.update(invariants=['j >= 0', 'j <= 2', 'total == i * 2 + j'], decreases='2 - j')
        result = self.verify(contract)
        full = json.loads(Path(result['output']).read_text())
        kinds = {o['kind'] for o in full['functions'][0]['obligations']}
        self.assertIn('decreases_strict', kinds)
        self.assertIn('invariant_preserved', kinds)
        self.cli('test', '--profile', 'release')
        self.cli('test', '--target', 'web')
        outer['decreases'] = '0'
        failing = self.verify(contract, ok=False)
        self.assertEqual(failing['functions'][0]['status'], 'counterexample')
        failure = next(o for o in failing['functions'][0]['obligations'] if o['kind'] == 'decreases_strict')
        self.assertEqual(failure['counterexample_kind'], 'inductive_state')

    def test_precondition_consistency_definedness_and_call_contracts(self):
        self.source('''module assumptions;
pub fn inc(x: i64) -> i64 { return x + 1; }
pub fn caller(x: i64) -> i64 { return inc(x); }
pub fn safe(x: i64) -> i64 { return x; }
''')
        impossible = self.verify(self.contract('safe', ['x > 0', 'x < 0']), ok=False)
        self.assertEqual(impossible['functions'][0]['status'], 'inconsistent_preconditions')
        undefined = self.verify(self.contract('safe', ['1 / x > 0']), ok=False)
        self.assertEqual(undefined['functions'][0]['status'], 'counterexample')
        self.assertIn('requires_defined/division_nonzero', {o['kind'] for o in undefined['functions'][0]['obligations']})
        contract = self.contract('caller')
        contract['functions'] += self.contract('inc', ['x < 9223372036854775807'])['functions']
        result = self.verify(contract, '--symbol', 'caller', ok=False)
        self.assertIn('callee_requires', {o['kind'] for o in result['functions'][0]['obligations']})

    def test_stale_snapshots_archive_and_independent_graph_identity(self):
        original = 'module frozen; pub fn identity(x: i64) -> i64 { return x; }\n'
        self.source(original)
        contract = self.contract('identity', [], ['result == x'])
        first = self.verify(contract)
        self.file.write_text('// changed locations\n' + original)
        self.assertEqual(self.verify(contract, ok=False)['code'], 'E_CONTRACT_STALE')
        self.file.unlink()
        archived = self.verify(contract, '--revision', first['revision'])
        self.assertEqual(archived['functions'][0]['node_id'], first['functions'][0]['node_id'])
        export = self.root / 'exported'
        self.cli('export', '--revision', first['revision'], '--directory', export)
        path = self.root / 'contracts.json'
        other = self.cli('verify', '--contracts', path, cwd=export)
        self.assertEqual(other['functions'][0]['content_hash'], first['functions'][0]['content_hash'])
        self.assertNotEqual(other['functions'][0]['node_id'], first['functions'][0]['node_id'])

    def test_unsupported_is_never_proven_and_resources_are_explicit(self):
        programs = [
            ('module unverified; pub fn f(x:f64)->f64{return x+x;}', 'f'),
            ('module unverified; pub fn f()->bool{return 1e0<2e0;}', 'f'),
            ('module unverified; pub fn f(x:bytes)->i64{return x[0];}', 'f'),
            ('module unverified; pub fn f()->bool{return len(utf8_bytes("x"))==1;}', 'f'),
            ('module unverified; pub fn f()->bool{return is_ok(decode_base64("AA=="));}', 'f'),
            ('module unverified; pub server fn f()->bool!{fs}{return is_ok(file_read_bytes("x"));}', 'f'),
            ('module unverified; pub fn f(x: str) -> str { return x; }', 'f'),
            ('module unverified; pub fn f(n: i64) -> i64 { if n == 0 { return 0; } return f(n - 1); }', 'f'),
            ('module unverified; pub fn f() -> unit !{io} { print(1); }', 'f'),
            ('module unverified; pub fn f(n: i64) -> i64 { var i: i64 = 0; while i < n { i = i + 1; } return i; }', 'f'),
        ]
        for program, symbol in programs:
            self.source(program)
            result = self.verify(self.contract(symbol), ok=False)
            self.assertEqual(result['functions'][0]['status'], 'unsupported')
        self.source('module limits; pub fn f(x: i64) -> i64 { return x + 1; }')
        result = self.verify(self.contract('f', ['x < 9223372036854775807']), '--resource-limit', '1', ok=False)
        self.assertEqual(result['functions'][0]['status'], 'unknown')
        self.assertTrue(any(o['status'] == 'unknown' for o in result['functions'][0]['obligations']))
        self.assertEqual(result['limits']['solver_resource_limit'], 1)

    def test_contract_input_rejections_and_smt_artifact_replay(self):
        self.source('module schema; pub fn f(x: i64) -> i64 { return x + 1; }')
        original = self.contract('f', ['x < 9223372036854775807'], ['result == x + 1'])
        for key, value, code in [('source_hash', '0' * 64, 'E_CONTRACT_STALE'), ('expected_revision', '0' * 64, 'E_CONTRACT_STALE'), ('schema', 'unknown', 'E_CONTRACT')]:
            contract = copy.deepcopy(original)
            contract[key] = value
            self.assertEqual(self.verify(contract, ok=False)['code'], code)
        for expression, code in [('result == unknown', 'E_CONTRACT_EXPRESSION'), ('result + 1', 'E_CONTRACT_EXPRESSION'), ('true; assert(false);', 'E_PARSE')]:
            contract = copy.deepcopy(original)
            contract['functions'][0]['ensures'] = [expression]
            self.assertEqual(self.verify(contract, ok=False)['code'], code)
        contract = copy.deepcopy(original)
        contract['functions'][0]['unexpected'] = True
        self.assertEqual(self.verify(contract, ok=False)['code'], 'E_CONTRACT')
        result = self.verify(original)
        saved = json.loads(Path(result['output']).read_text())
        query = saved['functions'][0]['obligations'][-1]['query']
        z3 = os.environ.get('NEX_Z3_EXECUTABLE') or shutil.which('z3')
        if z3:
            output = subprocess.check_output([z3, query], text=True, timeout=10)
            self.assertEqual(output.strip(), 'unsat')
        for args in [('--solver-timeout', '0'), ('--resource-limit', '0'), ('--timeout', '301')]:
            self.assertEqual(self.verify(original, *args, ok=False)['code'], 'E_OPTION')

    def test_negative_postcondition_model_replays_actual_result(self):
        original = '''module absolute;
pub fn magnitude(x: i64) -> i64 { if x < 0 { return -x; } return x; }
'''
        self.source(original)
        contract = self.contract('magnitude', ['x > -9223372036854775808'], ['result >= 0'])
        self.verify(contract)
        contract['functions'][0]['ensures'] = ['result == x']
        failed = self.verify(contract, ok=False)
        witness = next(o for o in failed['functions'][0]['obligations'] if o['kind'] == 'ensures')
        x = int(witness['inputs']['x'])
        self.assertLess(x, 0)
        actual = int(witness['locals']['result'])
        self.assertEqual(actual, -x)
        self.assertEqual(witness['counterexample_kind'], 'concrete_input')
        self.source(original + f'fn main() -> unit !{{io}} {{ print(magnitude({x})); }}')
        expected = str(actual) + '\n'
        self.assertEqual(self.cli('eval')['stdout'], expected)
        self.assertEqual(self.cli('run', '--profile', 'release')['stdout'], expected)
        self.assertEqual(self.web()['stdout'], expected)

    def test_argument_evaluation_order_reports_first_reachable_trap(self):
        self.source('''module ordered;
fn first() -> i64 { assert(false); return 1; }
fn second() -> i64 { return 1 / 0; }
fn combine(a: i64, b: i64) -> i64 { return a + b; }
pub fn main() -> i64 { return combine(first(), second()); }
''')
        result = self.verify(self.contract('main'), ok=False)
        failures = result['functions'][0]['obligations']
        self.assertEqual({f['runtime_code'] for f in failures}, {'E_ASSERT'})
        self.assertEqual(self.cli('eval', ok=False)['code'], 'E_ASSERT')
        self.assertIn('E_ASSERT', self.cli('run', '--profile', 'release', ok=False)['stderr'])
        self.assertEqual(self.web()['code'], 'E_ASSERT')


if __name__ == '__main__':
    unittest.main()
