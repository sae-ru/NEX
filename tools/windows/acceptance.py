"""Build with a selected Windows or WSL producer; run PE in native Windows.

Native producer runs accept a local Windows compiler within this corpus;
they do not certify a portable SDK. WSL runs accept only the PE target.
All commands, source projects, IR, failures and outputs remain under --output.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import runpy
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
from compiler_cohort import COHORT_HELPER_SHA256, compiler_cohort, compiler_field, typed_task_abi


def prepare_project(folder, source, language, *, resume=False):
    """Never retag or rewrite an existing project while resuming evidence."""
    folder.mkdir(exist_ok=resume)
    manifest = folder / 'nex.json'
    source_path = folder / 'main.nex'
    expected = {'schema': 'nex.project/1', 'language': language, 'entry': 'main.nex'}
    if manifest.exists():
        if json.loads(manifest.read_text(encoding='utf-8')) != expected:
            raise RuntimeError('project language/configuration changed; use a new output directory')
    elif source_path.exists():
        raise RuntimeError('existing project lacks its manifest; use a new output directory')
    if source_path.exists() and source_path.read_text(encoding='utf-8') != source:
        raise RuntimeError('source changed; use a new output directory')
    if not manifest.exists():
        manifest.write_text(json.dumps(expected) + '\n', encoding='utf-8', newline='\n')
    if not source_path.exists():
        source_path.write_text(source, encoding='utf-8', newline='\n')
    return folder


def linux_path(path):
    value = str(Path(path).resolve()).replace('\\', '/')
    if not re.match(r'^[A-Za-z]:/', value):
        raise ValueError('acceptance outputs must be on a local Windows drive')
    return '/mnt/' + value[0].lower() + value[2:]


def windows_path(path):
    if re.match(r'^[A-Za-z]:[\\/]',path):return Path(path)
    match = re.match(r'^/mnt/([a-z])/(.*)$', path)
    if not match:
        raise ValueError('producer artifact is not on a mounted Windows drive: ' + path)
    return Path(match[1].upper() + ':/' + match[2])


def constant(path, name):
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise ValueError('missing fixture ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--producer', required=True, help='nex path in the selected producer environment')
    parser.add_argument('--producer-environment',choices=('windows','wsl'),default='wsl')
    parser.add_argument('--toolchain-root', required=True, help='LLVM-MinGW root in the selected producer environment')
    parser.add_argument('--sqlite-root', required=True, help='Windows root of target SQLite installation')
    parser.add_argument('--distro', default='Ubuntu-22.04')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--section', choices=('cpu-files', 'storage'), default='cpu-files')
    parser.add_argument('--resume', action='store_true', help='retain prior evidence and reuse passed cases only with identical sources, compiler and artifact hashes')
    args = parser.parse_args()
    native_producer=args.producer_environment=='windows'
    if native_producer:
        args.producer=str(Path(args.producer).resolve())
        args.toolchain_root=Path(args.toolchain_root).resolve().as_posix()
    def producer_path(path):return str(Path(path).resolve()) if native_producer else linux_path(path)
    if args.resume and args.section == 'storage':
        parser.error('storage acceptance requires a fresh database/output directory')
    if platform.system() != 'Windows':
        parser.error('run this driver with native Windows Python')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=args.resume)
    report = {'schema': 'nex.windows-native-acceptance/1', 'ok': False,
              'helper_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'cohort_helper_sha256': COHORT_HELPER_SHA256,
              'section': args.section,
              'producer_environment': 'native Windows' if native_producer else 'WSL '+args.distro, 'execution_environment': 'native Windows',
              'requires_WSL':not native_producer,
              'Windows_hosted_compiler_accepted': False, 'CUDA_NEX_accepted': False,
              'commands': [], 'cases': [], 'source_commit': None}
    previous_index = None
    previous_toolchain = None
    previous_producer_sha256 = None
    previous_seconds = 0
    log_prefix = ''
    if args.resume:
        prior = json.loads((out / 'report.json').read_text(encoding='utf-8'))
        if 'producer_sha256' not in prior:
            parser.error('older receipt lacks the producer binary pin; use a new output directory')
        if any(prior.get(key) != report[key] for key in ('helper_sha256', 'cohort_helper_sha256')):
            parser.error('acceptance helpers changed or lack pins; use a new output directory')
        assert prior.get('section', 'cpu-files') == args.section
        prior.setdefault('section', 'cpu-files')
        resume_count = prior.get('resume_count', 0) + 1
        shutil.copy2(out / 'report.json', out / f'report-before-resume-{resume_count}.json')
        previous_index = prior['index']
        previous_toolchain = prior['toolchain']
        previous_producer_sha256 = prior['producer_sha256']
        previous_seconds = prior['seconds']
        report = prior
        report.update(ok=False, resume_count=resume_count)
        report.pop('failure', None)
        log_prefix = f'resume-{resume_count}-'
    started = time.monotonic()

    def save():
        report['seconds'] = round(previous_seconds + time.monotonic() - started, 3)
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    def command(name, argv, expected=0, env=None, timeout=360, cwd=None):
        name = log_prefix + name
        row = {'name': name, 'argv': list(map(str, argv))}
        if cwd is not None:row['cwd']=str(cwd)
        report['commands'].append(row)
        save()
        result = subprocess.run(row['argv'], capture_output=True, timeout=timeout, env=env,cwd=cwd)
        row.update(exit_code=result.returncode,
                   stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
                   stderr_sha256=hashlib.sha256(result.stderr).hexdigest())
        (out / (name + '.stdout')).write_bytes(result.stdout)
        (out / (name + '.stderr')).write_bytes(result.stderr)
        save()
        if expected is not None and result.returncode != expected:
            raise AssertionError(name + ': ' + str(result.returncode) + '\n' + result.stdout.decode('utf-8', 'replace')[-3000:] + result.stderr.decode('utf-8', 'replace')[-3000:])
        return result

    sequence = 0

    def cli(project, *argv, expected=0, environment=None):
        nonlocal sequence
        sequence += 1
        if native_producer:
            result=command(f'producer-{sequence:04d}',[args.producer,*argv,'--json'],expected,
              env={**os.environ,**(environment or {})},cwd=project)
            return json.loads(result.stdout)
        prefix = ['env', *(key + '=' + value for key, value in environment.items())] if environment else []
        result = command(f'producer-{sequence:04d}', ['wsl.exe', '-d', args.distro, '--cd', linux_path(project), '--', *prefix, args.producer, *argv, '--json'], expected)
        return json.loads(result.stdout)

    def project(name, source):
        return prepare_project(out / name, source, report['cohort']['language'], resume=args.resume)

    def run_case(folder, label, entry='main', stdout='', failure=None, env=None, flags=(), reference=True):
        completed = {row['profile']: row for row in report['cases'] if row.get('name') == label and row.get('status') == 'passed' and 'sha256' in row}
        for row in completed.values():
            assert hashlib.sha256(Path(row['artifact']).read_bytes()).hexdigest() == row['sha256'], 'artifact changed; use a new output directory'
        if all(profile in completed for profile in ('debug', 'release')):
            return
        if reference:
            reference_env = dict(env or {})
            if 'NEX_FILES_ROOT' in reference_env:
                reference_env['NEX_FILES_ROOT'] = producer_path(reference_env['NEX_FILES_ROOT'])
            value = cli(folder, 'eval', '--entry', entry, expected=1 if failure else 0, environment=reference_env)
            if failure:
                assert value['code'] == failure, value
            else:
                assert value['stdout'] == stdout, value
        for profile in ('debug', 'release'):
            if profile in completed:
                continue
            built = cli(folder, 'build', '--entry', entry, '--toolchain', producer_path(toolchain), '--profile', profile)
            exe = windows_path(built['executable'])
            inspect_args=[args.toolchain_root+'/bin/llvm-readobj.exe','--file-headers',built['executable']] if native_producer else ['wsl.exe','-d',args.distro,'--',args.toolchain_root+'/bin/llvm-readobj','--file-headers',built['executable']]
            inspected=command(label+'-'+profile+'-pe',inspect_args)
            assert b'IMAGE_FILE_MACHINE_AMD64' in inspected.stdout
            process = command(label + '-' + profile, [exe, *flags], 70 if failure else 0,
                              {**os.environ, **(env or {})}, timeout=60)
            observed = process.stdout.decode('utf-8')
            assert observed == stdout, (label, observed, stdout)
            if failure:
                assert failure.encode() in process.stderr, process.stderr
                assert b'NEX_SOURCE_EXCEPTION ' not in process.stderr
            else:
                assert not process.stderr, process.stderr
            report['cases'].append({'name': label, 'profile': profile, 'status': 'passed',
                                    'artifact': str(exe), 'sha256': hashlib.sha256(exe.read_bytes()).hexdigest(),
                                    'expected_failure': failure, 'reference_compared': reference})
            save()

    try:
        report['source_commit'] = command('source-head', ['git', '-C', ROOT, 'rev-parse', 'HEAD']).stdout.decode().strip()
        report['producer_sha256'] = hashlib.sha256(Path(args.producer).read_bytes()).hexdigest() if native_producer else command('producer-sha256', ['wsl.exe', '-d', args.distro, '--', 'sha256sum', args.producer]).stdout.decode('ascii').split()[0]
        if previous_producer_sha256:
            assert report['producer_sha256'] == previous_producer_sha256, 'producer binary changed; use a new output directory'
        report['dirty_diff_sha256'] = hashlib.sha256(command('source-diff', ['git', '-C', ROOT, 'diff', '--binary']).stdout).hexdigest()
        report['doctor'] = cli(out, 'doctor')
        assert report['doctor']['llvm'].startswith('22.1.')
        report['index'] = cli(out, 'describe', '--kind', 'index')
        report['cohort'] = compiler_cohort(report['doctor'], report['index'])
        if previous_index:
            assert report['index'] == previous_index, 'producer identity changed; use a new output directory'
        report['features'] = {field: cli(out, 'describe', '--field', field) for field in (
            'source_concurrency', 'structured_tasks_runtime', 'source_exceptions',
            'source_exceptions.source_providers', 'foreign_boundary', 'device', 'compute',
            'runtime_contracts', 'windows_core_target')}
        for field, envelope in report['features'].items():
            compiler_field(report['cohort'], envelope, field)
        report['source_task_ABI'] = typed_task_abi(report['cohort'],
            report['features']['source_exceptions.source_providers'])
        notice = out / 'notices.txt'
        # Read the complete original notices with the producer, preserving bytes.
        if native_producer:
            sdk=Path(args.toolchain_root);notice.write_bytes(b'\n\n'.join(p.read_bytes() for p in [sdk/'LICENSE.TXT',*sorted((sdk/'x86_64-w64-mingw32/share/mingw32').glob('COPYING*'))]))
        else:command('notices', ['wsl.exe', '-d', args.distro, '--', 'python3', '-c',
            'from pathlib import Path;import sys;r=Path(sys.argv[1]);p=[r/"LICENSE.TXT",*sorted((r/"x86_64-w64-mingw32/share/mingw32").glob("COPYING*"))];Path(sys.argv[2]).write_bytes(b"\\n\\n".join(x.read_bytes() for x in p))',
            args.toolchain_root, producer_path(notice)])
        toolchain = out / 'toolchain.json'
        sqlite = Path(args.sqlite_root).resolve()
        toolchain.write_text(json.dumps({'schema': 'nex.toolchain/1', 'target': 'x86_64-w64-windows-gnu',
            'compiler': args.toolchain_root + '/bin/clang++'+('.exe' if native_producer else ''), 'linker': args.toolchain_root + '/bin/ld.lld'+('.exe' if native_producer else ''),
            'archiver': args.toolchain_root + '/bin/llvm-ar'+('.exe' if native_producer else ''), 'sysroot': args.toolchain_root + '/x86_64-w64-mingw32',
            'windows': {'runtime': 'ucrt-static', 'notices': producer_path(notice)},
            'sqlite': {'include': producer_path(sqlite / 'sqlite-amalgamation-3540100'),
                       'library': producer_path(sqlite / 'x86_64/libsqlite3.a')}}), encoding='utf-8')
        report['toolchain'] = cli(out, 'toolchain', producer_path(toolchain))
        if previous_toolchain:
            assert report['toolchain'] == previous_toolchain, 'target toolchain changed; use a new output directory'
        fixtures = runpy.run_path(str(ROOT / 'tests/windows_native_cases.py'))
        if args.section == 'storage':
            storage = project('storage', constant(ROOT / 'tests/windows_runtime.py', 'STORAGE'))
            no_grant = project('no-grant', constant(ROOT / 'tests/windows_runtime.py', 'NO_GRANT'))
            for profile in ('debug', 'release'):
                built = cli(storage, 'build', '--toolchain', producer_path(toolchain), '--profile', profile)
                exe = windows_path(built['executable'])
                database = storage / ('данные 🧠-' + profile + '.sqlite')
                for index, (owner, mode) in enumerate((('alice Я🧠', 'seed'), ('alice Я🧠', 'read'),
                        ('bob', 'seed'), ('bob', 'read'), ('alice Я🧠', 'read'))):
                    label = 'storage-' + profile + '-' + str(index)
                    value = command(label, [exe], env={**os.environ, 'NEX_DATABASE': str(database),
                        'NEX_STORAGE_OWNER': owner, 'NEX065_MODE': mode})
                    assert value.stdout.decode('utf-8').replace('\r\n', '\n') == owner + '\n'
                    assert not value.stderr, value.stderr
                    report['cases'].append({'name': label, 'status': 'passed', 'profile': profile,
                        'owner': owner, 'mode': mode, 'artifact': str(exe),
                        'sha256': hashlib.sha256(exe.read_bytes()).hexdigest()})
                    save()
                missing = cli(no_grant, 'build', '--toolchain', producer_path(toolchain), '--profile', profile)
                environment = dict(os.environ)
                environment.pop('NEX_DATABASE', None)
                environment.pop('NEX_STORAGE_OWNER', None)
                denied = command('storage-no-grant-' + profile, [windows_path(missing['executable'])], env=environment)
                assert json.loads(denied.stdout)['error']['code'] == 'CAPABILITY'
                assert not denied.stderr, denied.stderr
                report['cases'].append({'name': 'storage-no-grant', 'status': 'passed', 'profile': profile})
            report['ok'] = True
            report['Windows_hosted_compiler_accepted']=native_producer
            print(json.dumps({'ok': True, 'cases': len(report['cases']), 'report': str(out / 'report.json')}))
            return
        core = project('core', fixtures['CORE'])
        run_case(core, 'core', stdout='Я\0🧠\n42\n')
        print_bytes=project('print-bytes',r'''module print_bytes;
fn main()->unit!{io}{print("A\r\nB\rC\n\u0000Я🧠");}
''')
        run_case(print_bytes,'print-bytes',stdout='A\r\nB\rC\n\0Я🧠\n')
        for entry, error in [('overflow_add', 'E_OVERFLOW'), ('overflow_sub', 'E_OVERFLOW'),
                             ('overflow_mul', 'E_OVERFLOW'), ('overflow_div', 'E_OVERFLOW'),
                             ('divide_zero', 'E_DIV_ZERO'), ('bad_index', 'E_BOUNDS')]:
            run_case(core, entry, entry=entry, failure=error)
        tasks = project('tasks', constant(ROOT / 'tests/windows_targets.py', 'STRUCTURED_TASK_SOURCE'))
        run_case(tasks, 'tasks', stdout='42\n42\n')
        run_case(tasks, 'task-steps', failure='E_LIMIT', flags=('--nex-task-steps', '1'), reference=False)
        typed = project('typed', fixtures['TYPED_TASKS'])
        run_case(typed, 'typed', stdout='Я\0🧠\nfinished\n')
        run_case(typed, 'cancel', entry='cancel', failure='E_CANCELLED')
        run_case(typed, 'deadline', entry='deadline', failure='E_TIMEOUT',
                 flags=('--nex-task-timeout-ms', '1'), reference=False)
        for name, fixture, stdout in [('files', 'FILES', 'Я\0🧠\n'), ('task-files', 'TASK_FILES', 'task-files-ok\n')]:
            folder = project(name, fixtures[fixture])
            data = folder / 'данные 🧠'
            (data / 'nested').mkdir(parents=True, exist_ok=args.resume)
            file_env = {'NEX_FILES_ROOT': str(data), 'NEX_FILES_WRITE': '1'}
            run_case(folder, name, stdout=stdout, env=file_env)
            if name == 'files':
                run_case(folder, 'read-only', entry='denied', env={'NEX_FILES_ROOT': str(data), 'NEX_FILES_WRITE': '0'}, reference=False)
                assert not (data / 'denied').exists()
            else:
                run_case(folder, 'typed-file', entry='typed', stdout='typed-file-ok\n', env=file_env)
                run_case(folder, 'cancel-file', entry='cancelled', failure='E_CANCELLED', env=file_env)
                assert not (data / 'cancel-finally').exists()
        environment = project('environment', constant(ROOT / 'tests/windows_runtime.py', 'ENVIRONMENT'))
        run_case(environment, 'environment', stdout='значение 🧠\n{"error":{"code":"NOT_FOUND","message":"environment variable is not defined"}}\n',
                 env={'NEX065_Я🧠': 'значение 🧠', 'NEX065_EMPTY': ''}, reference=False)
        for name, source, error in fixtures['REJECTED']:
            folder = project('rejected-' + name, source)
            result = cli(folder, 'check', expected=1)
            assert result['code'] == error, result
            report['cases'].append({'name': name, 'status': 'passed', 'rejected': True, 'diagnostic': error})
        report['ok'] = True
        report['Windows_hosted_compiler_accepted']=native_producer
    except Exception as error:
        report['failure'] = str(error)
        raise
    finally:
        save()
    print(json.dumps({'ok': True, 'cases': len(report['cases']), 'report': str(out / 'report.json')}))


if __name__ == '__main__':
    main()
