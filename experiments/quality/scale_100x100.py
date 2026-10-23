#!/usr/bin/env python3
"""Opt-in, fixed 100-module/10000-declaration SDK acceptance corpus.

This repeats the historical 094--096 corpus with fresh language/revision pins.
It measures this workload, not universal throughput or model token costs.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import signal
import sqlite3
import stat
import subprocess
import sys
import threading
import time
import traceback


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        name = path.relative_to(directory).as_posix()
        if path.is_symlink():
            raise RuntimeError('resource symlink requires an explicit inventory policy: ' + name)
        if path.is_file():
            result[name] = {'sha256': digest(path), 'mode': stat.S_IMODE(path.stat().st_mode)}
    if not result:
        raise RuntimeError('empty resource directory')
    return result


def generate(project, language):
    modules = project / 'modules'
    modules.mkdir()
    sums = []
    for number in range(100):
        count = 97 if number == 0 else 98
        expected = count * number * 100 + count * (count - 1)
        sums.append(expected)
        lines = ['module large::m%03d;' % number]
        if number == 0:
            lines += ['import "./m%03d.nex" as m%03d;' % (other, other)
                      for other in range(1, 100)]
        lines += ['fn leaf%d(n:i64)->i64{return n+%d;}' % (index, number * 100 + index)
                  for index in range(count)]
        lines += ['pub fn sum()->i64{return ' + '+'.join(
            'leaf%d(%d)' % (index, index) for index in range(count)) + ';}']
        lines += ['test fn module_test()->unit{assert(sum()==%d);}' % expected]
        if number == 0:
            lines += ['fn main()->i64!{io}{print(' + '+'.join(
                ['sum()'] + ['m%03d::sum()' % other for other in range(1, 100)])
                      + ');return 0;}']
        (modules / ('m%03d.nex' % number)).write_text('\n'.join(lines) + '\n')
    (project / 'nex.json').write_text(json.dumps({
        'schema': 'nex.project/1', 'language': language, 'entry': 'modules/m000.nex'
    }) + '\n')
    assert len(list(modules.glob('*.nex'))) == 100
    assert sum(sums) == 49460406
    return sums


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--resources', type=Path,
                        help='default: COMPILER/../../share/nex (installed SDK)')
    parser.add_argument('--output', type=Path, required=True, help='must not exist')
    parser.add_argument('--language', default='0.20', help='must match actual describe')
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    resources = (args.resources or compiler.parent.parent / 'share/nex').resolve(strict=True)
    output = args.output.resolve()
    if output == resources or resources in output.parents:
        parser.error('--output must be outside the immutable resources')
    if output.exists() or output.is_symlink():
        parser.error('--output must be a new directory')
    output.mkdir(parents=True)
    output = output.resolve()
    project = output / 'project'
    project.mkdir()
    start = time.monotonic()
    report = {
        'schema': 'nex.quality-scale/1', 'ok': False, 'state': 'running',
        'modules': 100, 'declarations': 10000, 'reachable_native_functions': 9900,
        'compiler': str(compiler), 'compiler_sha256': digest(compiler),
        'resources': str(resources), 'resource_inventory': inventory(resources),
        'runner_sha256': digest(Path(__file__).resolve()),
        'installed_layout': resources == compiler.parent.parent / 'share/nex',
        'host': {'system': platform.system(), 'release': platform.release(),
                 'machine': platform.machine(), 'python': platform.python_version()},
        'maximum_rss_scope': 'wait4 child rusage as reported by this OS, not process-group peak',
        'limits': {'command_timeout_seconds': 5400, 'output_bytes_per_stream': 33554432,
                   'context_bytes': 32768}, 'commands': [],
        'scope': 'Fixed corpus on this host; driver observer is included in build latency; '
                 'no kernel isolation, cross-platform, C++/Python parity or model-token claim.'
    }
    env = dict(os.environ, NEX_RESOURCE_DIR=str(resources), PYTHONDONTWRITEBYTECODE='1')
    spy = output / 'compiler-observer'
    spylog = output / 'actual-llvm-inputs.log'

    def save():
        report.update(updated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      seconds=round(time.monotonic() - start, 6))
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(output / 'report.json')

    def guard():
        assert digest(compiler) == report['compiler_sha256'], 'compiler changed'
        assert inventory(resources) == report['resource_inventory'], 'resources changed'

    def command(name, arguments, *, timeout=5400, overrides=None, remove_env=()):
        guard()
        report['phase'] = name
        row = {'name': name, 'argv': list(map(str, arguments)), 'cwd': str(project),
               'env_overrides': overrides or {}, 'env_removed': list(remove_env),
               'timeout_seconds': timeout, 'status': 'running'}
        report['commands'].append(row)
        save()
        stdout_path, stderr_path = output / (name + '.stdout'), output / (name + '.stderr')
        command_env = dict(env)
        for key in remove_env:
            command_env.pop(key, None)
        command_env.update(overrides or {})
        row['effective_tool_environment'] = {key: command_env[key] for key in
            ('PATH', 'NEX_RESOURCE_DIR', 'NEX_CLANG', 'NEX_WASM_LD', 'NEX_TOOLCHAIN')
            if key in command_env}
        done = threading.Event()
        termination = []
        began = time.monotonic()
        with stdout_path.open('xb') as stdout, stderr_path.open('xb') as stderr:
            process = subprocess.Popen(row['argv'], cwd=project, env=command_env,
                                       stdout=stdout, stderr=stderr, start_new_session=True)

            def monitor():
                while not done.wait(0.1):
                    reason = None
                    if time.monotonic() - began > timeout:
                        reason = 'timeout'
                    elif any(p.stat().st_size > 33554432 for p in (stdout_path, stderr_path)):
                        reason = 'output_limit'
                    if reason:
                        termination.append(reason)
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        return

            watcher = threading.Thread(target=monitor, daemon=True)
            watcher.start()
            try:
                _, status, usage = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
            except BaseException:
                termination.append('interrupted')
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                _, status, usage = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
            finally:
                done.set()
                watcher.join()
        row.update(exit_code=process.returncode, seconds=round(time.monotonic() - began, 6),
                   user_seconds=usage.ru_utime, system_seconds=usage.ru_stime,
                   maximum_rss_bytes=usage.ru_maxrss * (1 if sys.platform == 'darwin' else 1024),
                   status=termination[0] if termination else
                   ('passed' if process.returncode == 0 else 'failed'))
        for key, path in [('stdout', stdout_path), ('stderr', stderr_path)]:
            row[key] = {'path': path.name, 'sha256': digest(path), 'bytes': path.stat().st_size}
        save()
        guard()
        assert row['status'] == 'passed', (name, row['status'], row['exit_code'])
        return stdout_path.read_text()

    def nex(name, *arguments, **kwargs):
        return json.loads(command(name, [compiler, *arguments, '--json'], **kwargs))

    def query(sql, parameters=()):
        # Existing WAL databases may need sidecar initialization even for
        # SELECTs. Never create a missing DB, then prohibit SQL writes.
        with sqlite3.connect((project / '.nex/graph.db').as_uri() + '?mode=rw', uri=True) as db:
            db.execute('PRAGMA query_only=ON')
            return db.execute(sql, parameters).fetchall()

    def build(name, revision):
        spylog.write_text('')
        value = nex(name, 'build', '--revision', revision, '--profile', 'release')
        calls = spylog.read_text().splitlines()
        assert len(calls) == value['compiled_functions'], (name, len(calls), value)
        (output / (name + '-llvm-inputs.json')).write_text(json.dumps(calls, indent=2) + '\n')
        compilation = Path(value['compilation'])
        if not compilation.is_absolute():
            compilation = project / compilation
        units = json.loads(compilation.read_text())
        assert units['granularity'] == 'function' and len(units['units']) == 9900
        assert len({u['identity'] for u in units['units']}) == 9900
        report.setdefault('compilation_reports', {})[name] = {
            'path': str(compilation), 'sha256': digest(compilation), 'actual_llvm_calls': len(calls)}
        return value, units

    try:
        save()
        actual = nex('describe-version', 'describe', '--field', 'version')
        assert actual['value'] == args.language, actual
        report.update(toolchain=actual['toolchain'], language=actual['value'],
                      compiler_build=actual['compiler_build'])
        sums = generate(project, args.language)
        sources = {p.relative_to(project).as_posix(): digest(p)
                   for p in sorted(project.rglob('*.nex'))}
        report.update(original_sources=sources,
                      source_bytes=sum((project / p).stat().st_size for p in sources))
        original = nex('check-original', 'check')
        old = original['revision']
        assert original['functions'] == 10000
        assert query('SELECT count(*) FROM nodes WHERE revision=?', (old,)) == [(10000,)]
        assert query('SELECT count(*) FROM node_ids') == [(10000,)]
        observed = nex('eval-original', 'eval', '--revision', old, '--steps', '1000000')
        assert (observed['stdout'], observed['value']) == ('49460406\n', 0)
        context = nex('context-original', 'context', '--revision', old,
                      '--symbol', 'large::m042::leaf7')
        assert context['symbol'] == 'large::m042::leaf7'
        assert report['commands'][-1]['stdout']['bytes'] <= 32768
        edited = project / 'modules/m042.nex'
        before = edited.read_text()
        leaf = 'fn leaf7(n:i64)->i64{return n+4207;}'
        test = 'test fn module_test()->unit{assert(sum()==%d);}' % sums[42]
        assert before.count(leaf) == before.count(test) == 1
        edited.write_text(before.replace(leaf, 'fn leaf7(n:i64)->i64{return n+4208;}').replace(
            test, 'test fn module_test()->unit{assert(sum()==%d);}' % (sums[42] + 1)))
        assert [p for p, h in sources.items() if digest(project / p) != h] == ['modules/m042.nex']
        checked = nex('check-edited', 'check')
        new = checked['revision']
        assert old != new and checked['functions'] == 10000
        assert query('SELECT count(*) FROM node_ids') == [(10000,)]
        assert query('SELECT count(*) FROM nodes WHERE revision=?', (new,)) == [(10000,)]
        changes = query('SELECT i.module,i.name FROM nodes a JOIN nodes z ON a.id=z.id '
                        'JOIN node_ids i ON i.id=a.id WHERE a.revision=? AND z.revision=? '
                        'AND a.hash!=z.hash ORDER BY i.name', (old, new))
        assert changes == [('large::m042', 'leaf7'), ('large::m042', 'module_test')]
        assert query('SELECT count(*) FROM nodes a JOIN nodes z ON a.id=z.id '
                     'WHERE a.revision=? AND z.revision=?', (old, new)) == [(10000,)]
        for label, revision, expected in [('edited', new, '49460407\n'), ('history', old, '49460406\n')]:
            result = nex('eval-' + label, 'eval', '--revision', revision, '--steps', '1000000')
            assert (result['stdout'], result['value']) == (expected, 0)
        context = nex('context-edited', 'context', '--revision', new,
                      '--symbol', 'large::m042::leaf7')
        assert context['symbol'] == 'large::m042::leaf7'
        assert report['commands'][-1]['stdout']['bytes'] <= 32768
        doctor = nex('doctor', 'doctor')
        real = Path(doctor['native_compiler'])
        assert real.is_absolute() and real.is_file()
        report['native_compiler'] = {'path': str(real), 'sha256': digest(real)}
        # Retain driver argv[0]; resolving a clang++ symlink can change link behavior.
        spy.write_text('#!/bin/sh\nnex_scale_compile=no\nnex_scale_ir=\nfor nex_scale_arg do\n'
                       ' case "$nex_scale_arg" in\n -c) nex_scale_compile=yes;;\n'
                       ' *.ll) nex_scale_ir=$nex_scale_arg;;\n esac\ndone\n'
                       'if [ "$nex_scale_compile" = yes ] && [ -n "$nex_scale_ir" ]; then\n'
                       ' printf "%s\\n" "$nex_scale_ir" >> ' + shlex.quote(str(spylog)) + '\nfi\n'
                       'exec ' + shlex.quote(str(real)) + ' "$@"\n')
        spy.chmod(0o755)
        env['NEX_CLANG'] = str(spy)
        cold, first = build('cold-original', old)
        assert (cold['compiled_modules'], cold['reused_modules']) == (100, 0)
        assert (cold['compiled_functions'], cold['reused_functions']) == (9900, 0)
        warm, _ = build('warm-original', old)
        assert warm['cached'] and (warm['compiled_functions'], warm['reused_functions']) == (0, 9900)
        assert (warm['compiled_modules'], warm['reused_modules']) == (0, 100)
        changed, second = build('one-function-edit', new)
        assert (changed['compiled_modules'], changed['reused_modules']) == (1, 99)
        assert (changed['compiled_functions'], changed['reused_functions']) == (1, 9899)
        keys = {u['identity']: u['input_key'] for u in first['units']}
        changed_keys = [u['identity'] for u in second['units'] if u['input_key'] != keys[u['identity']]]
        assert changed_keys == ['large::m042::leaf7']
        report.update(original_revision=old, edited_revision=new, all10000_ids_preserved=True,
                      edited_sources={'modules/m042.nex': digest(edited)},
                      changed_native_keys=changed_keys)
        for label, built, expected in [('original', cold, '49460406\n'),
                                       ('edited', changed, '49460407\n')]:
            executable = Path(built['executable'])
            if not executable.is_absolute():
                executable = project / executable
            copied = output / (label + '-standalone')
            shutil.copy2(executable, copied)
            observed = command(label + '-standalone-run', [copied], timeout=60,
                               remove_env=('NEX_RESOURCE_DIR', 'NEX_CLANG'))
            assert observed == expected
            report.setdefault('artifacts', {})[label] = {
                'original': str(executable), 'copy': str(copied), 'sha256': digest(copied)}
        shutil.move(str(project / 'modules'), str(output / 'physical-sources'))
        assert not (project / 'modules').exists()
        for label, revision, expected in [('original', old, '49460406\n'), ('edited', new, '49460407\n')]:
            spylog.write_text('')
            replay = nex(label + '-source-deleted-replay', 'run', '--revision', revision,
                         '--profile', 'release')
            assert replay['stdout'] == expected and not spylog.read_text()
        assert digest(real) == report['native_compiler']['sha256']
        guard()
        report.update(ok=True, state='passed', phase='complete', actual_llvm_calls=[9900, 0, 1],
                      source_deleted_replay=True, database_bytes=(project / '.nex/graph.db').stat().st_size)
    except BaseException as error:
        report.update(state='failed', error=repr(error))
        traceback.print_exc()
    finally:
        save()
        print(json.dumps({k: report.get(k) for k in ('schema', 'ok', 'state', 'phase', 'seconds', 'error')}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
