"""Actual macOS policy denials and three scoped, unchanged task solutions."""
import errno
import importlib.util
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
NEX = Path(sys.argv.pop(1)).resolve()
BASE = ROOT / 'experiments/quality/llm-campaign-v1'


def load(name, file):
    spec = importlib.util.spec_from_file_location(name, BASE / file)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value); return value


a = load('nex_isolated_acceptance', 'acceptance.py')
i = load('nex_mac_isolation', 'isolation.py')


class Isolation(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex-local-isolation-')
        self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.addCleanup(self.preserve_failure)
        self.work = self.root / 'candidate %, 🧠'; self.work.mkdir()
        self.output = self.root / 'host-only'; self.output.mkdir()
        doctor = json.loads(subprocess.check_output([NEX, 'doctor', '--json'],
                            env=dict(os.environ, NEX_RESOURCE_DIR=str(ROOT))))
        self.cpp = Path(shutil.which(doctor['native_compiler']) or doctor['native_compiler']).absolute()
        self.sandbox = i.MacSandbox(compiler=NEX, cpp=self.cpp, resources=ROOT)

    def preserve_failure(self):
        result = getattr(getattr(self, '_outcome', None), 'result', None)
        failed = any(getattr(test, 'test_case', test) is self
                     for test, _ in [*getattr(result, 'failures', []), *getattr(result, 'errors', [])])
        destination = os.environ.get('NEX_TEST_FAILURE_ROOT')
        if failed and destination:
            target = Path(destination) / (self.id() + '-' + self.root.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(self.root, target)

    def run_python(self, code, name, *, rss=512 * 1024 * 1024):
        args = self.sandbox.wrap([sys.executable, '-I', '-B', '-X', 'utf8', '-c', code],
                                 self.work, self.output, name)
        return a.command(args, self.work, self.sandbox.environment(self.work, compile_phase=False),
                         self.output, name, timeout=20, max_group_rss=rss)

    def test_actual_file_network_fork_and_signal_denials(self):
        marker = self.root / 'host-canary'; marker.write_text('private host control')
        listener = socket.socket(); self.addCleanup(listener.close)
        listener.bind(('127.0.0.1', 0)); listener.listen(2)
        address = listener.getsockname()
        # Establish that the endpoint is live before asking the kernel to deny it.
        peer = socket.create_connection(address, timeout=3); accepted, _ = listener.accept()
        peer.close(); accepted.close()
        code = '''import errno,json,os,socket
def denied(action):
 try: action()
 except OSError as error:
  if error.errno in (errno.EPERM,errno.EACCES): return
  raise
 raise RuntimeError("operation was unexpectedly allowed")
'''
        paths = [marker, BASE / 'fixtures.py', ROOT / 'README.md']
        code += 'for path in ' + repr(list(map(str, paths))) + ':\n denied(lambda: open(path,"rb").close())\n'
        code += 'denied(lambda: open(' + repr(str(self.root / 'forbidden-write')) + ',"w").close())\n'
        code += 'denied(lambda: open(' + repr(str(self.work / 'runtime-write')) + ',"w").close())\n'
        code += 'denied(lambda: socket.create_connection(' + repr(address) + ',timeout=2))\n'
        code += 'denied(lambda: os.kill(' + str(os.getpid()) + ',0))\nos.kill(os.getpid(),0)\n'
        code += '''try:
 child=os.fork()
except OSError as error:
 if error.errno not in (errno.EPERM,errno.EACCES): raise
else:
 if child==0: os._exit(0)
 os.waitpid(child,0)
 raise RuntimeError("fork was unexpectedly allowed")
print(json.dumps({"reads_denied":3,"writes_denied":2,"network_denied":True,"fork_denied":True,"other_signal_denied":True,"self_signal_allowed":True}))
'''
        row = self.run_python(code, 'denials')
        self.assertEqual(row['exit_code'], 0, (self.output / row['stderr']).read_text())
        self.assertIsNone(row['stopped'])
        self.assertEqual(json.loads((self.output / row['stdout']).read_bytes()),
            {'reads_denied': 3, 'writes_denied': 2, 'network_denied': True, 'fork_denied': True,
             'other_signal_denied': True, 'self_signal_allowed': True})
        self.assertEqual(marker.read_text(), 'private host control')
        self.assertFalse((self.root / 'forbidden-write').exists())
        self.assertFalse((self.work / 'runtime-write').exists())

    def test_minimal_environment_and_owned_memory_budget(self):
        env = self.sandbox.environment(self.work, compile_phase=False)
        self.assertFalse(any(k in env for k in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'LM_API_TOKEN', 'HTTP_PROXY']))
        row = self.run_python('import time;time.sleep(10)', 'memory', rss=512 * 1024)
        self.assertEqual(row['stopped'], 'resident_memory_limit')
        self.assertNotEqual(row['exit_code'], 0)

    def test_posix_spawn_does_not_bypass_the_runtime_process_limit(self):
        code = '''import errno,subprocess,sys
try:
 subprocess.run([sys.executable,"-I","-B","-c","pass"],check=True)
except OSError as error:
 if error.errno not in (errno.EPERM,errno.EACCES): raise
else:
 raise RuntimeError("posix_spawn unexpectedly created a runtime child")
print("spawn denied")
'''
        row = self.run_python(code, 'spawn')
        self.assertEqual(row['exit_code'], 0, (self.output / row['stderr']).read_text())
        self.assertEqual((self.output / row['stdout']).read_bytes(), b'spawn denied\n')

    def test_source_oracle_is_not_in_the_candidate_process(self):
        candidate = self.root / 'oracle-lookup'
        a.materialize('bounded-total', 'python', candidate)
        (candidate / 'candidate.py').write_text('def total(n):\n    import sys\n    return sys.modules["__main__"].case.get("expected", -999)\n')
        result = a.check(candidate, 'bounded-total', 'python', self.root / 'oracle-evidence',
                         compiler=NEX, cpp=self.cpp, resources=ROOT, isolate=True)
        self.assertFalse(result['functional_passed']); self.assertFalse(result['accepted'])
        self.assertEqual(result['commands'][-1]['exit_code'], 0)
        observed = result['observations'][0]['values']
        self.assertTrue(all(x['result'] == -999 for x in observed))

    def test_implicit_native_compiler_uses_the_same_selected_toolchain(self):
        implicit = i.MacSandbox(compiler=NEX, resources=ROOT)
        self.assertEqual(implicit.cpp, self.sandbox.cpp)
        self.assertEqual(implicit.linker, self.sandbox.linker)
        self.assertEqual(implicit.roots, self.sandbox.roots)
        self.assertEqual(implicit.compile_roots, self.sandbox.compile_roots)

    def test_three_actual_isolated_solutions(self):
        out = Path(os.environ['NEX_ISOLATION_OUTPUT']) if os.environ.get('NEX_ISOLATION_OUTPUT') else self.root / 'solutions'
        out.mkdir(parents=True, exist_ok=False)
        rows = []
        selected = json.loads(os.environ.get('NEX_ISOLATION_LANGUAGES', '["nex","cpp","python"]'))
        self.assertTrue(selected and set(selected) <= {'nex', 'cpp', 'python'})
        for task, language in [('joined-yielding-child', 'nex'), ('joined-yielding-child', 'cpp'), ('typed-error-finally', 'python')]:
            if language not in selected: continue
            name = task + '-' + language; candidate = out / (name + '-source')
            a.materialize(task, language, candidate, variant='solution')
            with self.subTest(task=task, language=language):
                report = a.check(candidate, task, language, out / name, compiler=NEX, cpp=self.cpp,
                                 resources=ROOT, cache=out / 'native-cache', isolate=True)
                rows.append({'task': task, 'language': language, 'functional_passed': report['functional_passed'],
                             'report': name + '/report.json'})
                a.save(out / 'isolated-controls.json', {'model_calls': 0, 'results': rows})
                self.assertTrue(report['functional_passed'], report['errors'])
                self.assertTrue(report['runner_is_OS_sandbox']); self.assertFalse(report['accepted'])
        if len(rows) == len(selected) and all(row['functional_passed'] for row in rows):
            if (out / 'native-cache').exists(): shutil.rmtree(out / 'native-cache')


if __name__ == '__main__': unittest.main(argv=[__file__, '-v', *sys.argv[1:]])
