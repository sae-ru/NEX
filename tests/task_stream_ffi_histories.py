"""Preserve genuine SDK023 mixed File/FFI histories through explicit024 migration."""
from host_fixture import run_native, host_cpp
import argparse
import copy
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from collections import Counter
from contextlib import closing
from pathlib import Path
from task_stream_ffi_fixture import DECLARATIONS, build_provider, sha, write

p = argparse.ArgumentParser()
p.add_argument('probe', type=Path)
p.add_argument('compiler', type=Path)
p.add_argument('source_probe', type=Path)
p.add_argument('--output', type=Path)
p.add_argument('--retained-sdk', type=Path)
p.add_argument('--case', action='append', dest='selected')
a = p.parse_args()
probe, compiler, source_probe = (path.resolve() for path in (a.probe, a.compiler, a.source_probe))
temporary = None
if a.output:
    root = a.output.resolve()
    root.mkdir()
else:
    temporary = tempfile.TemporaryDirectory(prefix='nex genuine mixed histories ')
    root = Path(temporary.name).resolve()
if a.retained_sdk:
    a.retained_sdk = a.retained_sdk.resolve(strict=True)
repo = Path(__file__).resolve().parents[1]
started = time.monotonic()
report = {'schema': 'nex.private024-mixed-stream-histories/1', 'ok': False, 'state': 'starting',
          'commands': [], 'cases': [], 'rejections': [], 'providers': {},
          'probe_sha256': sha(probe), 'compiler_sha256': sha(compiler), 'source_probe_sha256': sha(source_probe),
          'public_language': '0.28', 'private_language': '0.24',
          'public025_delivery_accepted': False, 'full_objective_complete': False}


def save():
    report['seconds'] = round(time.monotonic() - started, 3)
    write(root / 'report.json', report)


def run(label, argv, project=None, env=None, expected=0):
    report['state'] = label
    save()
    result = run_native(list(map(str, argv)), cwd=project or root, env=env or os.environ,
                            capture_output=True, text=True, timeout=300)
    (root / (label + '.stdout')).write_text(result.stdout, newline="\n")
    (root / (label + '.stderr')).write_text(result.stderr, newline="\n")
    report['commands'].append({'name': label, 'argv': list(map(str, argv)), 'cwd': str(project or root),
                              'exit_code': result.returncode, 'expected': expected})
    save()
    assert result.returncode == expected, (label, result.returncode, result.stdout[-2500:], result.stderr[-2500:])
    return result


def state(project):
    database = (project / '.nex/graph.db').resolve()
    uri = database.as_uri() + '?mode=ro' + ('&immutable=1' if not Path(str(database) + '-wal').exists() else '')
    with closing(sqlite3.connect(uri, uri=True)) as db:
        tables = [name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {'schema': db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),
                'tables': {name: sorted(db.execute('SELECT * FROM "' + name + '"').fetchall(), key=repr)
                           for name in tables}}


def preserved(before, after):
    assert before['schema'] == after['schema'] and len(before['tables']) == len(after['tables']) == 16
    for table, rows in before['tables'].items():
        if table != 'head':
            assert not (Counter(rows) - Counter(after['tables'][table])), table
    assert before['tables']['metadata'] == after['tables']['metadata']


def restore(name, meta, sql):
    project = root / name
    project.mkdir()
    (project / '.nex').mkdir()
    write(project / 'nex.json', meta['project_manifest'])
    for name, text in meta['revisions'][-1]['physical_files'].items():
        relative = Path(name)
        assert not relative.is_absolute() and '..' not in relative.parts
        path = project / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, newline="\n")
    (project / 'files').mkdir()
    (project / 'files/input').write_bytes(b'abcdef')
    with closing(sqlite3.connect(project / '.nex/graph.db')) as db:
        db.executescript(sql)
    return project


def invoke(label, project, meta, row, extra, env, expected=0):
    request = {'schema': 'nex.private-stream-migration-request/1', 'project': str(project),
               'expected_revision': meta['head'], 'origin_revision': row['revision'],
               'target_language': '0.24', **extra}
    path = root / (label + '.request.json')
    write(path, request)
    return json.loads(run(label, [probe, path, root / (label + '-evidence')], env=env, expected=expected).stdout)


def events(path, allocated):
    text = path.read_text() if path.exists() else ''
    assert text.count('F') == text.count('X') == allocated, (path, text, allocated)
    assert text.count('I') == text.count('D'), (path, text)
    if allocated:
        assert text.startswith('I') and text.endswith('D'), (path, text)
    return text


try:
    names = [dialect + '-' + kind for dialect in ('c11', 'cxx20') for kind in ('stream', 'whole-file')]
    if a.selected:
        assert set(a.selected) <= set(names)
        names = [name for name in names if name in a.selected]
    for name in names:
        fixture = repo / 'tests/fixtures' / ('language-0.23-sdk1335-mixed-' + name + '.json')
        meta = json.loads(fixture.read_text())
        sql_path = fixture.with_suffix('.sql')
        assert sha(sql_path) == meta['SQL_sha256'] and len(meta['revisions']) == 3
        assert meta['producer_language'] == '0.23' and meta['all_revisions_produced_by_actual023_SDK']
        assert not meta['retagged_history'] and meta['provider']['reproducible_two_directories']
        if a.retained_sdk:
            assert sha(a.retained_sdk) == meta['producer_compiler_sha256']
        dialect = meta['dialect']
        provider = meta['provider']
        if dialect not in report['providers']:
            original = build_provider(repo, root / (dialect + '-original'), dialect, provider['source'],
                                      provider['signatures'], run, dialect + '-original')
            if os.environ.get('NEX_MIXED_SANITIZER'):
                target = build_provider(repo, root / (dialect + '-target'), dialect, provider['source'],
                                        provider['signatures'], run, dialect + '-target', instrumented=True)
            else:
                target = original
            report['providers'][dialect] = {'original': original, 'target': target}
        original = report['providers'][dialect]['original']
        target = report['providers'][dialect]['target']
        original_available = original['manifest_sha256'] == provider['manifest_sha256']
        for i, row in enumerate(meta['revisions']):
            label = name + '-' + str(i)
            project = restore(label, meta, sql_path.read_text())
            before = state(project)
            physical = {n: (project / n).read_bytes() for n in [*meta['revisions'][-1]['physical_files'], 'nex.json']}
            candidate = copy.deepcopy(row['bundle'])
            projected = target['manifest_sha256'] != provider['manifest_sha256']
            if projected:
                text = candidate['files']['main.nex']
                assert text.count(provider['manifest_sha256']) == len(DECLARATIONS)
                candidate['files']['main.nex'] = text.replace(provider['manifest_sha256'], target['manifest_sha256'])
            candidate_path = root / (label + '-candidate.json')
            write(candidate_path, candidate)
            checked = json.loads(run(label + '-signatures', [source_probe, 'check', candidate_path, project, '-', '0.24']).stdout)
            assert checked['signatures'] == provider['signatures'], '023/024 external signature drift'
            control = {'target_foreign_host': target['host']}
            if projected:
                control['candidate'] = str(candidate_path)
            if original_available:
                control['origin_foreign_host'] = original['host']
            else:
                control.update(evaluate_retained=False, retained_evaluation_unavailable_reason=
                               'Original pinned producer is unavailable on this platform/compiler; origin identity is rechecked, not executed.')
            marker = root / (label + '-migration.events')
            env = {**os.environ, 'NEX_FILES_ROOT': str(project / 'files'), 'NEX_FILES_WRITE': '1',
                   'NEX_TYPED_RESOURCE_MARKER': str(marker)}
            value = invoke(label + '-migrate', project, meta, row, {**control, 'execute': True}, env)
            after = state(project)
            preserved(before, after)
            assert value['origin_verified'] and value['old_identity_rechecked']
            assert value['origin_revision'] == row['revision'] and value['origin_language'] == '0.23'
            assert value['language'] == '0.24' and value['public_default'] == '0.28'
            assert value['target_value'] == row['expected_value'] and value['target_stdout'] == ''
            assert value['target_external_capacity_after_scope'] == 0
            if original_available:
                if row['old_error']:
                    assert value['old_error'] == row['old_error']
                else:
                    assert value['old_value'] == row['old_value'] and value['old_stdout'] == ''
                    assert value['old_external_capacity_after_scope'] == 0
            else:
                assert value['old_evaluation_skipped'] == control['retained_evaluation_unavailable_reason']
            reference_events = events(marker, 1 + int(original_available and not row['old_error']))
            assert len(after['tables']['revisions']) == 4 and after['tables']['head'] == [(1, value['revision'])]
            assert all((project / n).read_bytes() == data for n, data in physical.items())
            idempotent_env = {**env, 'NEX_TYPED_RESOURCE_MARKER': str(root / (label + '-idempotent.events'))}
            invoke(label + '-idempotent', project, meta, row, {**control, 'expected_revision': value['revision']}, idempotent_env)
            assert state(project) == after
            binary = Path(value['executable'])
            path = project / 'main.nex'
            hidden = path.with_name(path.name + '.hidden')
            path.rename(hidden)
            native_marker = root / (label + '-native.events')
            try:
                native = run(label + '-native', [binary, '--nex-foreign', target['host'], '--nex-task-workers', '1'],
                             env={**env, 'PATH': '/usr/bin:/bin', 'NEX_TYPED_RESOURCE_MARKER': str(native_marker)},
                             expected=row['expected_value'])
                assert native.stdout == native.stderr == ''
            finally:
                hidden.rename(path)
            native_events = events(native_marker, 1)
            cli_env = dict(env)
            cli_env.pop('NEX_RESOURCE_DIR', None)
            installed_old_rechecked = False
            if a.retained_sdk and original_available:
                old_marker = root / (label + '-installed-old.events')
                old = json.loads(run(label + '-installed-old', [a.retained_sdk, 'eval', '--revision', row['revision'],
                                     '--foreign', original['host'], '--json'], project,
                                     {**cli_env, 'NEX_TYPED_RESOURCE_MARKER': str(old_marker)},
                                     1 if row['old_error'] else 0).stdout)
                if row['old_error']:
                    assert old['code'] == row['old_error']
                else:
                    assert old['value'] == row['old_value'] and old['stdout'] == ''
                events(old_marker, 0 if row['old_error'] else 1)
                assert state(project) == after
                installed_old_rechecked = True
            refused = json.loads(run(label + '-public-head', [compiler, 'check', '--json'], project, cli_env, 1).stdout)
            assert refused['code'] == 'E_LANGUAGE_VERSION' and state(project) == after
            web = root / (label + '-web')
            run(label + '-web-emission', [source_probe, 'web', candidate_path, project, web, '0.24'])
            text = (web / 'program.ts').read_text()
            assert 'file_open_read' not in text and 'histories::mixed_ffi::main' not in text
            (web / 'package.json').write_text('{"type":"module"}\n', newline="\n")
            (web / 'run.mjs').write_text("import {entry} from './program.ts';process.stdout.write(String(entry())+'\\n');\n", newline="\n")
            client = run(label + '-typescript', [os.environ.get('NEX_NODE', 'node'), '--experimental-strip-types',
                         '--disable-warning=ExperimentalWarning', web / 'run.mjs'])
            assert client.stdout == str(row['expected_value']) + '\n' and client.stderr == ''
            assert (project / 'files/input').read_bytes() == b'abcdef'
            assert not (project / 'files/output').exists()
            report['cases'].append({'name': label, 'origin_revision': row['revision'], 'revision': value['revision'],
                'expected_value': row['expected_value'], 'old_error': row['old_error'], 'old_runtime_executed': original_available,
                'installed_old_SDK_rechecked': installed_old_rechecked, 'native_reference': True, 'pure_client_TypeScript': True,
                'all16_tables_schema_rows_ids_preserved': True, 'physical_sources_manifest_preserved': True,
                'source_absent_native': True, 'idempotent': True, 'physical_manifest_guard': True,
                'reviewed_foreign_pin_projection': projected, 'original_pin': provider['manifest_sha256'],
                'target_pin': target['manifest_sha256'], 'candidate_sha256': sha(candidate_path),
                'fixture_sha256': sha(fixture), 'SQL_sha256': meta['SQL_sha256'],
                'reference_events': reference_events, 'native_events': native_events,
                'executable': str(binary), 'executable_sha256': sha(binary)})
            save()
        for suffix, extra, code in [('disguise', {'declared_language': '0.24'}, 'E_REVISION'),
                                    ('stale', {'expected_revision': '0' * 64}, 'E_CONFLICT'),
                                    ('implicit', {'unversioned_synchronize': True}, 'E_LANGUAGE_VERSION')]:
            label = name + '-' + suffix
            project = restore(label, meta, sql_path.read_text())
            before = state(project)
            rejected = invoke(label, project, meta, meta['revisions'][-1], extra, os.environ, 1)
            assert rejected['code'] == code and state(project) == before
            report['rejections'].append({'name': label, 'code': code, 'store_unchanged': True})
            save()
    report.update(ok=True, state='passed', genuine023_histories=len(names), genuine023_revisions=len(report['cases']),
                  native_reference_pairs=len(report['cases']), pure_client_TypeScript_cases=len(report['cases']),
                  rejected_migrations=len(report['rejections']),
                  retained_runtime_cases=sum(row['old_runtime_executed'] for row in report['cases']),
                  installed_old_SDK_cases=sum(row['installed_old_SDK_rechecked'] for row in report['cases']))
except BaseException as error:
    report.update(state='failed', error=repr(error))
    raise
finally:
    save()
    print(json.dumps({k: report.get(k) for k in ('ok', 'state', 'genuine023_revisions', 'rejected_migrations', 'error')}), flush=True)
