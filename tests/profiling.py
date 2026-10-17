"""Observable native profiling, graph attribution, bounds and request cleanup."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import support as harness


class Profiling(harness.ToolchainCase):
    def program(self):
        self.source('''module measured;
fn recurse(n: i64) -> i64 {
  if n == 0 { return 1; }
  return recurse(n - 1) + 1;
}
fn item(n: i64) -> str { if n == 0 { return "zero"; } return "NEX " + str(n); }
fn unused() -> str { return "unreachable profile sentinel"; }
fn main() -> unit !{io} {
  var i: i64 = 0;
  while i < 20 { print(item(i)); i = i + 1; }
  print(recurse(5));
}
test fn behavior() -> unit { assert(item(0) == "zero"); assert(recurse(3) == 4); }
''')

    def test_graph_timings_memory_and_semantic_agreement(self):
        self.program()
        expected = self.cli('eval')['stdout']
        report = self.cli('profile', '--scenario', 'recursive and string workload', timeout=180)
        self.assertEqual(report['schema'], 'nex.profile-session/1')
        self.assertEqual(report['stdout'], expected)
        self.assertNotIn('traceEvents', report)
        saved = json.loads(Path(report['output']).read_text())
        self.assertEqual(saved['schema'], 'nex.profile/1')
        self.assertEqual(saved['build']['build_key'], report['build_key'])
        self.assertEqual(saved['build']['revision'], report['revision'])
        self.assertEqual(saved['scenario'], 'recursive and string workload')
        self.assertEqual(saved['hardware']['target'], self.cli('doctor')['host'])
        self.assertGreater(saved['duration_ns'], 0)
        graph = self.cli('graph')
        nodes = {node['name']: node for node in graph['nodes']}
        functions = {f['name']: f for f in saved['functions']}
        self.assertEqual(set(functions), {'measured::main', 'measured::item', 'measured::recurse'})
        self.assertEqual(functions['measured::item']['calls'], 20)
        self.assertEqual(functions['measured::recurse']['calls'], 6)
        self.assertEqual(functions['measured::main']['calls'], 1)
        for name, f in functions.items():
            self.assertEqual(f['node_id'], nodes[name]['id'])
            self.assertEqual(f['content_hash'], nodes[name]['hash'])
            self.assertTrue(Path(f['file']).is_file())
            self.assertEqual(f['calls'], f['completed'])
            self.assertEqual(f['aborted'], 0)
            self.assertGreaterEqual(f['inclusive_ns'], f['self_ns'])
            self.assertGreaterEqual(f['inclusive_ns'], f['max_ns'])
        self.assertEqual(len(saved['traceEvents']), 27)
        self.assertEqual(len({e['tid'] for e in saved['traceEvents']}), 1)
        self.assertGreater(sum(f['allocations'] for f in functions.values()), 0)
        for pool in saved['memory']:
            self.assertGreater(pool['allocations'], 0)
            self.assertEqual(pool['allocations'], pool['frees'])
            self.assertEqual(pool['live'], 0)
            self.assertEqual(pool['live_shallow_bytes'], 0)
            self.assertGreater(pool['peak_shallow_bytes'], 0)
        for field in ('dropped_events', 'dropped_functions', 'dropped_frames', 'dropped_allocations', 'untracked_frees'):
            self.assertEqual(saved[field], 0)
        self.assertEqual(self.cli('run', '--profile', 'release')['stdout'], expected)
        self.cli('test', '--profile', 'profile', timeout=180)
        self.cli('test', '--target', 'web')

    def test_traps_preserve_observations_and_close_active_zones(self):
        for expression, code in [('1 / 0', 'E_DIV_ZERO'), ('9223372036854775807 + 1', 'E_OVERFLOW')]:
            self.source('module failing; fn leaf() -> i64 { return ' + expression + '; } fn main() -> unit !{io} { print("before"); print(leaf()); }')
            expected = self.cli('eval', ok=False)
            self.assertEqual(expected['code'], code)
            result = self.cli('profile', ok=False, timeout=180)
            self.assertEqual(result['exit_code'], 70)
            self.assertEqual(result['stdout'], expected['stdout'])
            self.assertIn(code, result['stderr'])
            report = json.loads(Path(result['output']).read_text())
            self.assertEqual(len(report['functions']), 2)
            for f in report['functions']:
                self.assertEqual(f['calls'], 1)
                self.assertEqual(f['aborted'], 1)
                self.assertEqual(f['completed'], 0)
            self.assertTrue(all(e['args']['aborted'] for e in report['traceEvents']))

    def test_bounds_archived_reuse_and_literal_paths(self):
        project = self.root / 'процент % путь'
        project.mkdir()
        original = self.root
        self.root = project
        self.file = project / 'main.nex'
        try:
            self.program()
            first = self.cli('profile', '--events', '2', timeout=180, env={'NEX_TRACY': '1'})
            saved = json.loads(Path(first['output']).read_text())
            self.assertFalse(saved['tracy'])
            self.assertEqual(len(saved['traceEvents']), 2)
            self.assertEqual(saved['dropped_events'], 25)
            built = self.cli('build', '--profile', 'profile')
            self.assertTrue(built['cached'])
            self.assertEqual(built['compiled_modules'], 0)
            self.file.unlink()
            second = self.cli('profile', '--revision', first['revision'], '--events', '0', timeout=180)
            self.assertNotEqual(second['output'], first['output'])
            self.assertEqual(first['stdout'], second['stdout'])
            self.assertEqual(first['revision'], second['revision'])
            detailed = json.loads(Path(second['output']).read_text())
            self.assertEqual(detailed['traceEvents'], [])
            self.assertEqual(detailed['dropped_events'], 27)
            self.assertEqual({f['name']: f['node_id'] for f in saved['functions']}, {f['name']: f['node_id'] for f in detailed['functions']})
            for args in [('--events', '-1'), ('--events', '1000001'), ('--timeout', '0'), ('--timeout', '3601'), ('--profile', 'release'), ('--target', 'web'), ('--target', 'server')]:
                self.assertEqual(self.cli('profile', '--revision', 'HEAD', *args, ok=False)['code'], 'E_OPTION')
        finally:
            self.root = original

    def test_profile_archive_concurrent_request_traps_and_cancellation(self):
        self.source('''module hosted;
fn leaf(n: i64) -> str { let s: str = "NEX " + str(n); if n < 0 { assert(false); } return s; }
pub fn work(n: i64) -> str { return leaf(n); }
''')
        built = self.cli('build', '--library', '--entry', 'work', '--profile', 'profile', timeout=180)
        symbol = self.cli('context', '--symbol', 'work')['native_symbol']
        resources = Path(self.cli('doctor')['runtime']).parent.parent
        host = self.root / 'host.cpp'
        host.write_text('''#include "nex_host.h"
#include <thread>
#include <vector>
#include <atomic>
extern "C" nexrt::Handle *SYMBOL(int64_t);
int main(){
  std::atomic<int> failures{0}; std::vector<std::thread> threads;
  for(int i=0;i<4;++i)threads.emplace_back([&]{
    for(int j=0;j<8;++j){
      try { nexrt::RequestScope scope;auto *value=SYMBOL(j%2?-1:j);nex_release(value);if(j%2)++failures; }
      catch(const nexrt::Trap &e){if(e.code!="E_ASSERT"||j%2==0)++failures;}
    }
    try {nexrt::RequestScope scope(0);SYMBOL(0);++failures;} catch(const nexrt::Trap &e){if(e.code!="E_LIMIT")++failures;}
    try {nexrt::RequestScope scope;scope.cancel();SYMBOL(0);++failures;} catch(const nexrt::Trap &e){if(e.code!="E_CANCELLED")++failures;}
  });
  for(auto &thread:threads)thread.join();nex_runtime_finish();return failures?1:0;
}
'''.replace('SYMBOL', symbol))
        executable = self.root / 'host'
        subprocess.run([self.cli('doctor')['native_compiler'], '-std=c++20', '-DNEX_PROFILE_ENABLED', '-pthread', str(host), '-I', str(resources / 'runtime'), built['executable'], '-o', str(executable)], check=True, capture_output=True)
        output = self.root / 'host-profile.json'
        process = subprocess.run([str(executable)], env={**os.environ, 'NEX_TRACY': '0', 'NEX_PROFILE_OUTPUT': str(output)}, capture_output=True, text=True, timeout=30)
        self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
        measured = json.loads(output.read_text())
        functions = {f['name']: f for f in measured['functions']}
        self.assertEqual(functions['hosted::work']['calls'], 40)
        self.assertEqual(functions['hosted::work']['aborted'], 24)
        self.assertEqual(functions['hosted::leaf']['calls'], 32)
        self.assertEqual(functions['hosted::leaf']['aborted'], 16)
        self.assertEqual(len({e['tid'] for e in measured['traceEvents']}), 4)
        for pool in measured['memory']:
            self.assertEqual(pool['live'], 0)
            self.assertEqual(pool['allocations'], pool['frees'])
        self.assertEqual(measured['untracked_frees'], 0)

    def test_pinned_client_inventory_and_distribution_notices(self):
        vendor = harness.REPO / 'runtime/third_party/tracy'
        inventory = json.loads((vendor / 'manifest.json').read_text())
        self.assertEqual(inventory['version'], '0.14.1')
        for name, digest in inventory['files'].items():
            self.assertEqual(hashlib.sha256((vendor / name).read_bytes()).hexdigest(), digest, name)
        self.program()
        target = self.root / 'distributed-profile'
        built = self.cli('build', '--profile', 'profile', '-o', target, timeout=180)
        notice = Path(built['notices']).read_text()
        for text in ('Bartosz Taudul', 'Yann Collet', 'Cameron Desrochers', 'Erik Rigtorp', 'Mattias Jansson'):
            self.assertIn(text, notice)
        self.assertTrue(Path(str(target) + '.THIRD_PARTY_NOTICES.txt').is_file())
        self.assertEqual(subprocess.check_output([str(target)], text=True), self.cli('eval')['stdout'])
        normal = self.cli('build', '--profile', 'release')
        normal_notice=Path(normal['notices']).read_text()
        expected='Dragonbox 1.1.3\n\n'+(harness.REPO/'runtime/third_party/dragonbox/LICENSE-Boost').read_text()+'\n\n'
        self.assertEqual(normal_notice,expected)
        self.assertNotIn('Tracy',normal_notice)
        self.assertNotIn('nex_profile_enter', Path(normal['llvm']).read_text())
        self.assertIn('nex_profile_enter', Path(built['llvm']).read_text())

    def test_machine_response_is_bounded_and_saved_report_is_complete(self):
        declarations = ['fn f' + str(i) + '() -> i64 { return ' + str(i) + '; }' for i in range(120)]
        calls = ['print(f' + str(i) + '());' for i in range(120)]
        self.source('module many;\n' + '\n'.join(declarations) + '\nfn main() -> unit !{io} {\n' + '\n'.join(calls) + '\n}')
        report = self.cli('profile', '--events', '0', timeout=180)
        saved = json.loads(Path(report['output']).read_text())
        self.assertEqual(report['total_functions'], 121)
        self.assertEqual(len(report['functions']), 100)
        self.assertEqual(len(saved['functions']), 121)
        self.assertEqual(saved['traceEvents'], [])
        times = [f['self_ns'] for f in report['functions']]
        self.assertEqual(times, sorted(times, reverse=True))


if __name__ == '__main__':
    unittest.main()
