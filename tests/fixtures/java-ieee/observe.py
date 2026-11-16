"""Capture an actual JDK's handwritten IEEE observations; no project converter."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--jdk', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True, help='New evidence directory')
args = parser.parse_args()
root = Path(__file__).resolve().parent
generator = root.parents[1] / 'ieee_numeric_cases.py'
spec = importlib.util.spec_from_file_location('ieee_cases', generator)
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
commands = []
def run(argv, stdin=None):
    argv = list(map(str, argv))
    result = subprocess.run(argv, input=stdin, text=True, capture_output=True, timeout=120)
    index = len(commands)
    (out / f'{index}.stdout').write_text(result.stdout)
    (out / f'{index}.stderr').write_text(result.stderr)
    commands.append({'argv': argv, 'exit_code': result.returncode})
    (out / 'commands.json').write_text(json.dumps(commands, indent=2) + '\n')
    if result.returncode:
        raise RuntimeError(f'JDK command failed: {index}')
    return result.stdout, result.stderr
java, javac = args.jdk / 'bin/java', args.jdk / 'bin/javac'
_, version = run([java, '-version'])
run([javac, '-d', out, root / 'Oracle.java'])
cases = model.cases()
stdin = ''.join(' '.join(map(str, c)) + '\n' for c in cases)
stdout, _ = run([java, '-cp', out, 'Oracle'], stdin)
results = stdout.splitlines()
assert len(results) == len(cases)
for case, observed in zip(cases, results, strict=True):
    expected = model.expected(case)
    if expected != observed:
        raise AssertionError(f'{case}: JDK={observed} model={expected}')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
fixture = {'schema': 'nex.java-ieee-oracle/1', 'JDK': version.strip(),
           'java_sha256': sha(root / 'Oracle.java'), 'generator_sha256': sha(generator),
           'input_sha256': hashlib.sha256(stdin.encode()).hexdigest(),
           'stdout_sha256': hashlib.sha256(stdout.encode()).hexdigest(),
           'case_count': len(cases), 'exact_rational_model_agrees': True, 'results': results}
(out / 'oracle.json').write_text(json.dumps(fixture, indent=2) + '\n')
print(json.dumps({'ok': True, 'cases': len(cases), 'oracle': str(out / 'oracle.json')}))
