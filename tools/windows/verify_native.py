"""Verify one frozen NEX cohort in an ordinary native Windows session."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from local_smoke import context

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from ctest_report import fixture_closure, inspect_files


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b''):
            digest.update(block)
    return digest.hexdigest()


def document(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def cohort_pins(cohort):
    record = json.loads((cohort / 'cohort.json').read_bytes())
    for name, digest in record['sha256'].items():
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('invalid cohort pin: ' + name)
        if sha(cohort / relative) != digest:
            raise ValueError('cohort input changed: ' + name)
    if sha(cohort / 'nex.exe') != record['compiler_sha256']:
        raise ValueError('cohort compiler differs')
    return record


def harness_pins():
    names = subprocess.check_output(['git', 'ls-files', '-z', '--cached', '--others',
        '--exclude-standard', '--', 'tests', 'tools', 'runtime', 'debug', 'lib', 'llm', 'web', 'editor', 'examples', 'experiments/owned-cuda'], cwd=ROOT)
    return {name: sha(ROOT / name) for name in sorted(set(names.decode('utf-8').split('\0')))
            if name and (ROOT / name).is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cohort', required=True, type=Path)
    parser.add_argument('--debugger-prefix', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--mode', choices=('full', 'focused'), default='full')
    parser.add_argument('--jobs', choices=(1, 2, 3, 4), type=int, default=2)
    parser.add_argument('--cuda', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('this gate requires native Windows')
    cohort = args.cohort.resolve(strict=True)
    debugger = args.debugger_prefix.resolve(strict=True)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    token = context()
    report = {'schema': 'nex.windows-native-verification/1', 'ok': False,
        'requires_WSL': False, 'state': 'running', 'context': token, 'mode': args.mode, 'jobs': args.jobs,
        'full_windows_regression_accepted': False, 'cuda_requested':args.cuda, 'commands': []}

    def save():
        document(output / 'report.json', report)

    save()
    if token['is_app_container'] or token['is_elevated']:
        raise RuntimeError('run this gate from an ordinary unelevated Windows terminal')
    pinned = cohort_pins(cohort)
    initial_harness = harness_pins()
    document(output / 'harness-pins.json', initial_harness)
    report.update(compiler_sha256=pinned['compiler_sha256'],
        cohort_manifest_sha256=sha(cohort / 'cohort.json'),
        harness_pins_sha256=sha(output / 'harness-pins.json'))
    environment = {**os.environ, 'PYTHONUTF8': '1', 'NEX_PYTHON': sys.executable,
        'NEX_RESOURCE_DIR': str(cohort / 'resources'),
        'NEX_LLDB': str(debugger / 'bin/lldb.exe'),
        'NEX_LLDB_DAP': str(debugger / 'bin/lldb-dap.exe'),
        'NEX_TSC': str(ROOT / 'web/node_modules/typescript/bin/tsc'),
        'NEX_TEST_FAILURE_ROOT': str(output / 'failed-fixtures')}
    environment['PATH'] = str(debugger / 'bin') + os.pathsep + str(
        ROOT / 'build/deps/windows-host/clang64/bin') + os.pathsep + environment.get('PATH', '')
    report['debugger'] = {name: sha(debugger / 'bin' / name)
        for name in ('lldb.exe', 'lldb-dap.exe', 'lldb-server.exe', 'liblldb.dll')}

    def run(label, argv):
        report['phase'] = label
        save()
        path = output / (label + '.log')
        with path.open('wb') as log, subprocess.Popen(list(map(str, argv)), cwd=ROOT,
                env=environment, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as child:
            for line in child.stdout:
                log.write(line)
                log.flush()
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
            code = child.wait()
        report['commands'].append({'name': label, 'argv': list(map(str, argv)),
            'exit_code': code, 'log': str(path), 'log_sha256': sha(path)})
        save()
        return code

    try:
        ctest = shutil.which('ctest.exe') or 'C:/Program Files/CMake/bin/ctest.exe'
        command = [ctest, '--test-dir', cohort, '--output-on-failure', '-j', args.jobs,
                   '--output-junit', output / 'ctest.xml']
        if args.mode == 'focused':
            command += ['-R', '^(project_foreign_packaging|foreign_packaging|project_package_tasks|'
                'task_provider_debug_lifetime_native|server_workload|task_workloads|task_foreign|'
                'task_toolchains|tasks|task_stream_project|typed_error_projects|source_exception_projects|'
                'public_task_write_observability|task_file_stream_ffi_histories|'
                'public_task_stream_histories|source_exception_modules|native_images|'
                'task_shared_provider_native|task_provider_debugging_native|task_provider_profile_native|'
                'typed_error_debugging|source_finally_foundation|source_task_finally|'
                'source_exceptions_projects|source_exceptions_projects_debug)$']
        registry_path = output / 'ctest-registry.json'
        registry_path.write_bytes(subprocess.check_output(
            [str(ctest), '--test-dir', str(cohort), '--show-only=json-v1'], cwd=ROOT, env=environment))
        declared = json.loads(registry_path.read_bytes())
        expected_names={test['name'] for test in declared['tests']}
        if not expected_names:raise RuntimeError('the cohort declares no tests')
        selected = ([name for name in expected_names if re.search(command[-1], name)]
                    if args.mode == 'focused' else None)
        roots, closure = fixture_closure(declared, selected)
        report['declared_test_count']=len(expected_names)
        report['selected_test_names'] = sorted(roots)
        report['required_fixture_test_names'] = sorted(closure - roots)
        code = run('ctest', command)
        if not (output / 'ctest.xml').is_file():
            raise RuntimeError('CTest did not publish a completed JUnit report; full regression is not accepted')
        verification = inspect_files(registry_path, output / 'ctest.xml',
                                     ctest_exit_code=code, selected=selected)
        rows = verification['results']
        report['ctest'] = rows
        report['ctest_verification'] = verification
        report['ctest_xml_sha256'] = sha(output / 'ctest.xml')
        cuda_ok = True
        if args.cuda:
            project = output / 'cuda-project'
            cuda_ok = run('cuda-prepare', [sys.executable, '-X', 'utf8',
                ROOT / 'experiments/owned-cuda/prepare.py', '--compiler', cohort / 'nex.exe',
                '--output', project]) == 0
            if cuda_ok:
                cuda_ok = run('cuda-hardware', [sys.executable, '-X', 'utf8',
                    ROOT / 'experiments/owned-cuda/verify.py', '--compiler', cohort / 'nex.exe',
                    '--project', project, '--output', output / 'cuda-hardware']) == 0
                if cuda_ok:
                    receipt = output / 'cuda-hardware/report.json'
                    hardware = json.loads(receipt.read_bytes())
                    cuda_ok = (hardware.get('ok') is True and hardware.get('full_hardware_corpus') is True
                        and hardware.get('compiler_sha256') == pinned['compiler_sha256'])
                    report['cuda'] = {'ok': cuda_ok, 'report': str(receipt), 'sha256': sha(receipt)}
        cohort_pins(cohort)
        if harness_pins() != initial_harness:
            raise RuntimeError('test harness/resources changed during this run')
        report['inputs_unchanged'] = True
        report['ok'] = verification['ok'] and cuda_ok
        report['full_windows_regression_accepted'] = report['ok'] and args.mode == 'full'
        report['state'] = 'complete'
    except BaseException as error:
        report['state'] = 'error'
        report['error'] = repr(error)
        save()
        raise
    save()
    print(json.dumps({'ok': report['ok'], 'report': str(output / 'report.json')}, ensure_ascii=False))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
