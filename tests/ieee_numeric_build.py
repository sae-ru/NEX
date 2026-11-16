"""Compile/observe the internal IEEE kernel from one source or installed tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

parser = argparse.ArgumentParser()
parser.add_argument('--compiler', action='append', required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
resources = Path(__file__).resolve().parents[1]
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=False)
env = dict(os.environ, NEX_RESOURCE_DIR=str(out / 'absent-nex-resources'), PYTHONDONTWRITEBYTECODE='1')
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
report = {'schema': 'nex.ieee-kernel-build/1', 'ok': False, 'resources': str(resources),
          'platform': platform.platform(), 'machine': platform.machine(), 'commands': [],
          'compilers': [], 'kernel_only': True, 'portable_SDK': False,
          'public_source_support': False}
def save():
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
def run(argv):
    argv = list(map(str, argv))
    index = len(report['commands'])
    started = time.monotonic()
    result = subprocess.run(argv, cwd=out, env=env, capture_output=True, timeout=120)
    stdout, stderr = out / f'{index}.stdout', out / f'{index}.stderr'
    stdout.write_bytes(result.stdout)
    stderr.write_bytes(result.stderr)
    report['commands'].append({'argv': argv, 'cwd': str(out), 'exit_code': result.returncode,
        'seconds': time.monotonic() - started, 'stdout_sha256': sha(stdout), 'stderr_sha256': sha(stderr)})
    save()
    if result.returncode:
        raise RuntimeError(f'command {index} failed; inspect {stderr}')
    return result.stdout.decode()
try:
    runtime = resources / 'runtime'
    report['input_sha256'] = {name: sha(resources / name) for name in (
        'runtime/nex_ieee.h', 'runtime/nex_float.h', 'runtime/nex_error.h',
        'tests/ieee_numeric.cpp', 'tests/ieee_numeric.py', 'tests/ieee_numeric_cases.py',
        'tests/fixtures/java-ieee/Oracle.java', 'tests/fixtures/java-ieee/oracle.json')}
    fixture = json.loads((resources / 'tests/fixtures/java-ieee/oracle.json').read_text())
    report['cases_per_build'] = fixture['case_count']
    for index, compiler in enumerate(args.compiler):
        version = run([compiler, '--version'])
        report['compilers'].append({'path': compiler, 'version': version})
        for profile, optimization in (('debug', '-O0'), ('release', '-O2')):
            executable = out / f'kernel-{index}-{profile}{".exe" if os.name == "nt" else ""}'
            run([compiler, '-std=c++20', optimization, '-ffp-contract=off', '-frounding-math', '-pthread',
                 '-I' + str(runtime), resources / 'tests/ieee_numeric.cpp', '-o', executable])
            run([sys.executable, '-B', resources / 'tests/ieee_numeric.py', executable,
                 '--fixtures', resources / 'tests/fixtures/java-ieee'])
    report.update(ok=True, compiled_profiles=['debug', 'release'],
                  caller_environment_checked=True, exact_model_and_JDK_fixture_agree=True)
finally:
    save()
print(json.dumps({'ok': report['ok'], 'cases_per_build': report.get('cases_per_build'),
                  'compilers': len(report['compilers']), 'report': str(out / 'report.json')}))
