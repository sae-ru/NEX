#!/usr/bin/env python3
"""Prepare bounded candidates and check actual behavior; never call a model.

Private drivers/controls are host resources, excluded from the model's file API.
Behavioral success is distinct from independent review of source-level rules.
"""
import argparse
import contextlib
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
RESOURCES = HERE.parents[2]
LIMIT = 2 * 1024 * 1024


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fixtures = module('nex_campaign_fixtures', HERE / 'fixtures.py')
drivers = module('nex_campaign_drivers', HERE / 'drivers.py')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def decode(raw):
    if len(raw) > LIMIT:
        raise ValueError('JSON exceeds its byte budget')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result: raise ValueError('duplicate JSON key')
            result[key] = value
        return result
    def invalid(value): raise ValueError('nonfinite JSON: ' + value)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def catalogue():
    result = decode((HERE / 'tasks.json').read_bytes())
    if result['schema'] != 'nex.llm-campaign-tasks/1' or result['language'] != '0.28':
        raise ValueError('unknown task catalogue')
    items = {}
    for item in result['tasks']:
        contract = (json.dumps(item['contract'], ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
        if item['id'] in items or sha(contract) != item['contract_sha256']:
            raise ValueError('duplicate task or changed contract')
        if set(fixtures.TASKS[item['id']]) != {'nex', 'cpp', 'python'}:
            raise ValueError('incomplete language matrix')
        items[item['id']] = item
    if len(items) != 10: raise ValueError('expected all ten tasks')
    return items


def inventory(files):
    return {name: sha(raw) for name, raw in sorted(files.items())}


def source_digest(files):
    return sha(json.dumps(inventory(files), sort_keys=True, separators=(',', ':')).encode())


def materialize(task, language, directory, *, variant='start'):
    item = catalogue()[task]
    values = fixtures.files(task, language, variant)
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False)
    for name, raw in values.items(): (directory / name).write_bytes(raw)
    # Only this contract and this language's starting files go to a model.
    save(directory / 'task.json', {'id': task, 'language': language,
         'contract': item['contract'], 'contract_sha256': item['contract_sha256'],
         'editable_files': sorted(values), 'starting_source_pins': inventory(values)})
    return {'directory': str(directory), 'files': inventory(values), 'source_digest': source_digest(values)}


def read_candidate(directory, task, language):
    allowed = set(fixtures.files(task, language))
    values = {}
    for path in directory.iterdir():
        if path.name == 'task.json':
            if path.is_symlink() or not path.is_file(): raise ValueError('invalid task metadata')
            continue
        if path.name not in allowed or path.is_symlink() or not path.is_file():
            raise ValueError('candidate contains an unexpected path: ' + path.name)
        if path.stat().st_size > LIMIT: raise ValueError('candidate file exceeds its byte budget')
        raw = path.read_bytes()
        if len(raw) > LIMIT: raise ValueError('candidate file grew beyond its byte budget')
        raw.decode('utf-8')
        values[path.name] = raw
    if set(values) != allowed or sum(map(len, values.values())) > 4 * LIMIT:
        raise ValueError('candidate is incomplete or oversized')
    return values


def same(a, b):
    if type(a) is not type(b): return False
    if isinstance(a, dict): return a.keys() == b.keys() and all(same(a[k], b[k]) for k in a)
    if isinstance(a, list): return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def source_review(review, candidate, digest, item):
    if review is None: return None
    review = Path(review).resolve(strict=True)
    if review.is_relative_to(candidate): raise ValueError('source review must be host evidence outside candidate files')
    if not review.is_file() or review.stat().st_size > LIMIT: raise ValueError('invalid source review file')
    raw = review.read_bytes(); value = decode(raw)
    valid = (value.get('schema') == 'nex.llm-source-review/1' and value.get('candidate_digest') == digest
        and value.get('contract_sha256') == item['contract_sha256'] and value.get('passed') is True
        and value.get('rules') == item['contract']['acceptance_rules']
        and isinstance(value.get('reviewer'), str) and 0 < len(value['reviewer']) <= 512)
    if not valid: raise ValueError('source review does not bind every rule to this candidate/contract')
    return raw


def command(argv, cwd, env, output, name, *, timeout=120, windows_observer=None, max_group_rss=None):
    argv = list(map(str, argv)); began = time.monotonic(); reason = None
    stdout, stderr = output / (name + '.stdout'), output / (name + '.stderr')
    if os.name == 'nt':
        if not windows_observer: raise ValueError('Windows execution requires the existing private-job observer')
        observer = module('nex_campaign_windows_job', RESOURCES / 'tools/windows/job_observer.py')
        observed = observer.observe(argv, output / (name + '-job'), env,
                                    observer=windows_observer, directory=cwd, timeout=timeout)
        job = output / (name + '-job')
        stdout.write_bytes((job / 'stdout').read_bytes()); stderr.write_bytes((job / 'stderr').read_bytes())
        status = observed['parent_exit_code']; reason = 'timeout' if observed['timed_out'] else None
    else:
        with stdout.open('xb') as out, stderr.open('xb') as err:
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                     stdout=out, stderr=err, start_new_session=True)
            started = {'pid': child.pid, 'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       'argv': argv, 'cwd': str(cwd), 'owned_new_session': True}
            save(output / (name + '.owner.json'), started)
            def interrupt(signum, frame): raise InterruptedError('campaign command interrupted')
            previous = signal.signal(signal.SIGTERM, interrupt)
            last_rss_sample = 0
            try:
                while child.poll() is None:
                    if time.monotonic() - began > timeout: reason = 'timeout'; break
                    if any(p.stat().st_size > LIMIT for p in (stdout, stderr)): reason = 'output_limit'; break
                    if max_group_rss is not None and time.monotonic() - last_rss_sample >= 0.1:
                        # Query only the new owned session's kernel process group,
                        # never a process-name or unrelated PID tree. RSS is an
                        # aggregate upper bound, not a heap/peak memory metric.
                        sample = subprocess.run(['/bin/ps', '-o', 'rss=', '-g', str(child.pid)],
                                                capture_output=True, timeout=5)
                        if sample.returncode and child.poll() is None: raise ValueError('cannot observe owned process-group memory')
                        values = sample.stdout.split()
                        if any(not item.isdigit() for item in values): raise ValueError('invalid owned RSS observation')
                        if sum(map(int, values)) * 1024 > max_group_rss:
                            reason = 'resident_memory_limit'; break
                        last_rss_sample = time.monotonic()
                    time.sleep(0.02)
            finally:
                # Retire the newly owned group even when its root already exited.
                # No PID scan, process-name match or unrelated process is used.
                with contextlib.suppress(ProcessLookupError): os.killpg(child.pid, signal.SIGKILL)
                child.wait(timeout=10)
                signal.signal(signal.SIGTERM, previous)
            status = child.returncode
    if any(p.stat().st_size > LIMIT for p in (stdout, stderr)): reason = 'output_limit'
    row = {'name': name, 'argv': argv, 'cwd': str(cwd), 'exit_code': status,
           'seconds': round(time.monotonic() - began, 6), 'stopped': reason,
           'stdout': stdout.name, 'stderr': stderr.name,
           'stdout_sha256': sha(stdout.read_bytes()), 'stderr_sha256': sha(stderr.read_bytes())}
    save(output / (name + '.json'), row)
    return row


def check(candidate, task, language, output, *, compiler=None, cpp=None,
          resources=RESOURCES, cache=None, trial_id='offline-control', review=None,
          cpp_args=(), windows_observer=None, visible_only=False, isolate=False, deadline=None):
    item = catalogue()[task]; candidate = Path(candidate).resolve(strict=True)
    files = read_candidate(candidate, task, language); digest = source_digest(files)
    review_raw = source_review(review, candidate, digest, item)
    sandbox = None
    if isolate:
        isolation = module('nex_campaign_isolation', HERE / 'isolation.py')
        sandbox = isolation.MacSandbox(compiler=compiler, cpp=cpp, resources=resources)
    cases = item['contract']['visible_cases'] + ([] if visible_only else fixtures.held_out(task))
    expected = drivers.expected(task, cases); output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'; inputs.mkdir()
    for name, raw in files.items(): (inputs / name).write_bytes(raw)
    workspace = Path(tempfile.mkdtemp(prefix='nex-llm-acceptance-'))
    if any((p / 'nex.json').exists() for p in workspace.parents):
        workspace.rmdir(); raise ValueError('temporary execution root is inside an existing NEX project')
    commands, observations, errors = [], [], []
    env = {k: v for k, v in os.environ.items() if not k.startswith(('NEX_', 'PYTHON', 'LD_', 'DYLD_'))}
    env.update(NEX_RESOURCE_DIR=str(Path(resources).resolve()), PYTHONDONTWRITEBYTECODE='1')
    tool_pins = {'python': {'executable': sys.executable, 'version': sys.version, 'sha256': sha(Path(sys.executable).read_bytes())}}
    def run(name, args, timeout=120, *, compile_phase=False):
        if deadline is not None:
            timeout=min(timeout,max(0.01,deadline-time.monotonic()))
        selected_env, limit = env, None
        if sandbox:
            selected_env = sandbox.environment(workspace, compile_phase=compile_phase)
            args = sandbox.wrap(args, workspace, output, name, compile_phase=compile_phase,
                                writable_cache=cache if compile_phase and language == 'nex' else None)
            limit = (2048 if compile_phase else 512) * 1024 * 1024
        row = command(args, workspace, selected_env, output, name, timeout=timeout,
                      windows_observer=windows_observer, max_group_rss=limit)
        commands.append(row)
        return row
    def observe(row, nex=False):
        if row['exit_code'] != 0 or row['stopped']:
            errors.append({'step': row['name'], 'reason': 'process failed or exceeded its budget'}); return
        raw = (output / row['stdout']).read_bytes()
        if nex:
            packet = decode(raw)
            if packet.get('ok') is not True or packet.get('exit_code', 0) != 0:
                errors.append({'step': row['name'], 'reason': 'NEX did not complete'}); return
            raw = packet['stdout'].encode('utf-8')
        actual = [decode(line) for line in raw.splitlines()]
        observations.append({'step': row['name'], 'values': actual})
        if not same(actual, expected):
            errors.append({'step': row['name'], 'reason': 'observable outputs differ'})
    try:
        for name, raw in files.items(): (workspace / name).write_bytes(raw)
        if language == 'nex':
            if not compiler: raise ValueError('selected NEX compiler is required')
            compiler = Path(compiler).resolve(strict=True); pin = sha(compiler.read_bytes())
            tool_pins['nex'] = {'path': str(compiler), 'sha256': pin}
            discovery = run('discovery', [compiler, 'describe', '--kind', 'index', '--json'], compile_phase=True)
            if discovery['exit_code'] != 0: raise ValueError('NEX discovery failed')
            descriptor = decode((output / discovery['stdout']).read_bytes())
            if descriptor.get('language') != '0.28': raise ValueError('campaign requires current language0.28')
            tool_pins['nex']['index'] = descriptor
            cache = Path(cache).resolve() if cache else output / 'native-cache'
            marker = {'schema': 'nex.llm-acceptance-cache/1', 'compiler_sha256': pin}
            if cache.exists():
                if decode((cache / 'owner.json').read_bytes()) != marker: raise ValueError('cache is not owned by this compiler cohort')
            else: cache.mkdir(parents=True); save(cache / 'owner.json', marker)
            body = files['candidate.nex'].decode() + '\n' + drivers.nex_driver(task, cases)
            (workspace / 'main.nex').write_text(body, encoding='utf-8')
            (output / 'driver.nex').write_text(body, encoding='utf-8')
            save(workspace / 'nex.json', {'schema': 'nex.project/1', 'language': '0.28', 'entry': 'main.nex'})
            checked = run('source-check', [compiler, 'check', '--json'], compile_phase=True)
            if checked['exit_code'] == 0 and not checked['stopped']:
                observe(run('reference', [compiler, 'eval', '--json'], compile_phase=True), nex=True)
                if sandbox:
                    info = run('toolchain-info', [compiler, 'doctor', '--json'], compile_phase=True)
                    if info['exit_code'] != 0: raise ValueError('cannot capture the selected native toolchain')
                    doctor = decode((output / info['stdout']).read_bytes())
                    toolchain = {'schema': 'nex.toolchain/1', 'target': doctor['host'],
                        'compiler': doctor['native_compiler'], 'archiver': doctor['native_archiver'],
                        'debug_packager': doctor['native_debug_packager'], 'linker': str(sandbox.linker)}
                    if doctor['native_sysroot']: toolchain['sysroot'] = doctor['native_sysroot']
                    if doctor['native_sqlite_include'] and doctor['native_sqlite_library']:
                        toolchain['sqlite'] = {'include': doctor['native_sqlite_include'], 'library': doctor['native_sqlite_library']}
                    if doctor['native_openssl_include']:
                        toolchain['openssl'] = {'include': doctor['native_openssl_include'],
                            'ssl': doctor['native_openssl_ssl'], 'crypto': doctor['native_openssl_crypto']}
                    save(workspace / 'toolchain.json', toolchain); save(output / 'toolchain.json', toolchain)
                    tool_pins['nex']['explicit_linker'] = str(sandbox.linker)
                    built = run('native-build', [compiler, 'build', '--profile', 'release', '--build-directory', cache,
                                '--toolchain', workspace / 'toolchain.json', '--json'], compile_phase=True)
                    if built['exit_code'] == 0 and not built['stopped']:
                        executable = Path(decode((output / built['stdout']).read_bytes())['executable']).resolve(strict=True)
                        if not executable.is_relative_to(cache): raise ValueError('native image escaped the owned cache')
                        observe(run('native', [executable], 30))
                    else: errors.append({'step': 'native-build', 'reason': 'native compilation failed'})
                else:
                    observe(run('native', [compiler, 'run', '--profile', 'release', '--build-directory', cache, '--json']), nex=True)
            else: errors.append({'step': 'source-check', 'reason': 'candidate rejected'})
            if sha(compiler.read_bytes()) != pin: raise ValueError('compiler changed during acceptance')
        elif language == 'cpp':
            if not cpp: raise ValueError('selected C++ compiler is required')
            # clang++ may be a symlink to clang-N. Preserve argv[0]: resolving
            # that symlink changes driver mode and can omit the C++ libraries.
            cpp = Path(cpp).absolute()
            tool_pins['cpp'] = {'path': str(cpp), 'image': str(cpp.resolve(strict=True)),
                               'sha256': sha(cpp.read_bytes()), 'options': list(cpp_args)}
            (workspace / 'driver.cpp').write_text(drivers.cpp_driver(task, cases), encoding='utf-8')
            shutil.copyfile(workspace / 'driver.cpp', output / 'driver.cpp')
            binary = workspace / ('application.exe' if os.name == 'nt' else 'application')
            sources = [workspace / 'driver.cpp'] + ([workspace / 'operations.cpp'] if task == 'module-interface-change' else [])
            selected_linker = ['--ld-path=' + str(sandbox.linker)] if sandbox else []
            if sandbox: tool_pins['cpp']['explicit_linker'] = str(sandbox.linker)
            built = run('compile', [cpp, '-std=c++20', '-O2', '-pthread', *cpp_args, *selected_linker, *sources, '-o', binary], compile_phase=True)
            if built['exit_code'] == 0 and not built['stopped']: observe(run('execute', [binary], 30))
            else: errors.append({'step': 'compile', 'reason': 'candidate rejected'})
            if sha(cpp.read_bytes()) != tool_pins['cpp']['sha256']: raise ValueError('C++ compiler changed')
        elif language == 'python':
            (workspace / 'driver.py').write_text(drivers.python_driver(task, cases), encoding='utf-8')
            shutil.copyfile(workspace / 'driver.py', output / 'driver.py')
            observe(run('execute', [sys.executable, '-I', '-B', '-X', 'utf8', workspace / 'driver.py'], 30))
        else: raise ValueError('unknown language')
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        errors.append({'step': 'infrastructure', 'reason': str(error)})
    finally:
        # Retain only bounded source/driver/log evidence, not repeated binaries.
        shutil.rmtree(workspace)
    if read_candidate(candidate, task, language) != files:
        errors.append({'step': 'source-pins', 'reason': 'candidate changed during acceptance'})
    functional = not errors and bool(observations)
    reviewed = review_raw is not None
    if reviewed: (output / 'source-review.json').write_bytes(review_raw)
    accepted = functional and reviewed and not visible_only
    receipt = {'schema': 'nex.llm-acceptance/1', 'trial_id': trial_id,
               'contract_sha256': item['contract_sha256'], 'passed': accepted,
               'checks': [{'name': 'functional-visible-and-held-out', 'exit_code': 0 if functional and not visible_only else 1},
                          {'name': 'independent-source-contract-review', 'exit_code': 0 if reviewed else 1}]}
    report = {'schema': 'nex.llm-functional-check/1', 'functional_passed': functional, 'accepted': accepted,
              'task': task, 'language': language, 'candidate_digest': digest, 'source_pins': inventory(files),
              'contract_sha256': item['contract_sha256'], 'visible_cases': len(item['contract']['visible_cases']),
              'held_out_cases': 0 if visible_only else len(fixtures.held_out(task)),
              'source_contract_reviewed': reviewed, 'tool_pins': tool_pins,
              'commands': commands, 'observations': observations, 'errors': errors,
              'successful_workspace_removed': True, 'model_calls': 0,
              'runner_is_OS_sandbox': sandbox is not None,
              'isolation_backend': 'darwin-seatbelt/1' if sandbox else None,
              'candidate_source_not_modified': True}
    save(output / 'acceptance.json', receipt); save(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    for name in ['prepare', 'check']:
        p = sub.add_parser(name); p.add_argument('--task', required=True, choices=sorted(catalogue()))
        p.add_argument('--language', required=True, choices=['nex', 'cpp', 'python'])
        if name == 'prepare': p.add_argument('--directory', type=Path, required=True)
        else:
            p.add_argument('--candidate', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
            p.add_argument('--compiler', type=Path); p.add_argument('--cpp-compiler', type=Path); p.add_argument('--cache', type=Path)
            p.add_argument('--resources', type=Path, default=RESOURCES); p.add_argument('--trial-id', default='offline-control')
            p.add_argument('--source-review', type=Path); p.add_argument('--functional-only', action='store_true')
            p.add_argument('--isolate', action='store_true')
            p.add_argument('--cpp-arg', action='append', default=[]); p.add_argument('--windows-observer', type=Path)
    args = parser.parse_args()
    try:
        if sys.version_info < (3, 10): raise ValueError('Python3.10+ required')
        if args.action == 'prepare':
            print(json.dumps(materialize(args.task, args.language, args.directory))); return 0
        result = check(args.candidate, args.task, args.language, args.output, compiler=args.compiler,
                       cpp=args.cpp_compiler, resources=args.resources, cache=args.cache, trial_id=args.trial_id,
                       review=args.source_review, cpp_args=args.cpp_arg, windows_observer=args.windows_observer,
                       isolate=args.isolate)
        print(json.dumps({k: result[k] for k in ['task', 'language', 'functional_passed', 'accepted', 'candidate_digest']}))
        return 0 if result['functional_passed' if args.functional_only else 'accepted'] else 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({'schema': 'nex.llm-functional-check/1', 'valid': False, 'error': str(error)})); return 2


if __name__ == '__main__':
    raise SystemExit(main())
