"""Explicit 018/019 rechecks against genuine history and real task programs.

The probe accepts structured requests; this driver never relabels old source or
imports a synthetic database in place of the retained 0.97 SDK fixture.
"""
import argparse
from collections import Counter
from contextlib import closing
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import time

REPO = Path(__file__).resolve().parents[1]
OLD_LANGUAGE = '0.18'
TASK_LANGUAGE = '0.19'
RESERVED_FUNCTIONS = (
    'with_tasks', 'task_spawn', 'task_wait', 'task_send', 'task_recv',
    'task_close', 'task_cancel', 'task_yield', 'channel_new', 'current_task_scope',
)
RESERVED_TYPES = ('task', 'channel', 'task_scope')
ORDINARY_NAMES = ('async', 'await', 'spawn', 'send', 'recv', 'cancel', 'close', 'yield')
RENAMES = {name: 'legacy_' + name for name in RESERVED_TYPES + RESERVED_FUNCTIONS}
# NEX has // comments and JSON-style string escapes. Keeping both as whole
# tokens prevents a spelling repair from changing comments, literals or substrings.
TOKENS = re.compile(r'//[^\n]*|"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z0-9_]*')


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def bundle(source, **files):
    return {'schema': 'nex.sources/1', 'entry': 'main.nex',
            'files': {'main.nex': source, **files}}


def database_state(path):
    """All tables, all rows, all DDL and the actual SQLite schema versions."""
    # WAL readers may need writable sidecars. Open only an existing database,
    # prohibit SQL writes, and close it promptly after the complete snapshot.
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        schema = db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall()
        names = [name for name, in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {name: sorted(db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                for name in names}
        return {'schema': schema, 'user_version': db.execute('PRAGMA user_version').fetchone()[0],
                'application_id': db.execute('PRAGMA application_id').fetchone()[0], 'tables': rows}


def retained_rows(before, after, head):
    assert before['schema'] == after['schema'], 'migration changed existing DDL'
    assert before['user_version'] == after['user_version']
    assert before['application_id'] == after['application_id']
    assert before['tables'].keys() == after['tables'].keys(), 'migration changed the table inventory'
    for name, rows in before['tables'].items():
        if name != 'head':
            assert not (Counter(rows) - Counter(after['tables'][name])), ('lost historical rows', name)
    assert after['tables']['head'] == [(1, head)]


def read_revision(path, revision):
    with closing(sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        row = db.execute('SELECT source,language FROM revisions WHERE hash=?', (revision,)).fetchone()
    assert row, ('missing retained revision', revision)
    return json.loads(row[0]), row[1]


def repaired_source(source):
    occurrences = []

    def replace(match):
        name = match.group()
        if name not in RENAMES:
            return name
        occurrences.append({'old': name, 'new': RENAMES[name],
                            'begin_byte': len(source[:match.start()].encode('utf-8')),
                            'end_byte': len(source[:match.end()].encode('utf-8'))})
        return RENAMES[name]

    repaired = TOKENS.sub(replace, source)
    assert {item['old'] for item in occurrences} == set(RENAMES)
    for name in ORDINARY_NAMES:
        assert len(re.findall(r'\b' + name + r'\b', source)) == len(re.findall(r'\b' + name + r'\b', repaired))
        assert 'fn ' + name + '(' in repaired
    assert all(token.group() not in RENAMES for token in TOKENS.finditer(repaired))
    return repaired, occurrences


TASK_BUNDLE = bundle('''module migrated_tasks;
import "./worker.nex" as worker;
fn main()->i64 !{task}{return worker::solve();}
''', **{'worker.nex': '''module migrated_worker;
pub struct Box<T>{value:T;}
fn delayed<T>(value:T)->T !{task}{task_yield();return value;}
pub fn solve()->i64 !{task}{
 return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
  assert(current_task_scope()==scope);
  let queue:channel<Box<i64>>=channel_new<Box<i64>>(scope,0);
  let offset:i64=20;
  let writer:task<i64>=task_spawn(scope,fn()->i64 !{task}{
   assert(task_send(queue,delayed(Box(offset))));
   assert(task_send(queue,delayed(Box(offset+2))));
   assert(task_close(queue));return 2;
  });
  let first:Box<i64>=unwrap(task_recv(queue));
  let second:Box<i64>=unwrap(task_recv(queue));
  assert(!is_ok(task_recv(queue)));
  assert(task_wait(writer)==2);
  return first.value+second.value;
 });
}
'''})
TASK_CONTROLS = bundle('''module migrated_controls;
fn main()->i64 !{task}{return with_tasks(1,fn(outer:task_scope)->i64 !{task}{
 let borrowed:task_scope=with_tasks(1,fn(inner:task_scope)->task_scope !{task}{return outer;});
 assert(borrowed==outer);
 let pending:task<i64>=task_spawn(outer,fn()->i64 !{task}{while true{task_yield();}return 0;});
 task_yield();assert(task_cancel(pending));return 42;
});}
''')


class MigrationChecks:
    def __init__(self, probe, compiler, output):
        self.probe_binary = Path(probe).resolve()
        self.compiler = Path(compiler).resolve()
        self.output = output
        self.raw = output / 'requests'
        self.raw.mkdir()
        self.sequence = 0
        self.records = []
        self.checks = []

    def execute(self, name, command, cwd=None, ok=True, timeout=30):
        self.sequence += 1
        stem = self.raw / ('%03d-%s' % (self.sequence, name))
        write_json(stem.with_suffix('.command.json'), {'argv': list(map(str, command)), 'cwd': str(cwd or self.output)})
        started = time.monotonic()
        try:
            process = subprocess.run(list(map(str, command)), cwd=cwd or self.output,
                                     text=True, encoding='utf-8', capture_output=True, timeout=timeout,
                                     env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        except subprocess.TimeoutExpired as error:
            for suffix, captured in (('.stdout.json', error.stdout), ('.stderr.txt', error.stderr)):
                text = captured.decode('utf-8', errors='replace') if isinstance(captured, bytes) else captured or ''
                stem.with_suffix(suffix).write_text(text, encoding='utf-8')
            write_json(stem.with_suffix('.process.json'), {'timeout': timeout})
            raise AssertionError((name, 'exceeded timeout', timeout)) from error
        stem.with_suffix('.stdout.json').write_text(process.stdout, encoding='utf-8')
        stem.with_suffix('.stderr.txt').write_text(process.stderr, encoding='utf-8')
        write_json(stem.with_suffix('.process.json'), {'exit_code': process.returncode,
                   'seconds': time.monotonic() - started})
        assert process.returncode == (0 if ok else 1), (name, process.returncode, process.stdout, process.stderr)
        try:
            result = json.loads(process.stdout)
        except json.JSONDecodeError as error:
            raise AssertionError((name, 'invalid JSON response', process.stdout, process.stderr)) from error
        self.records.append({'name': name, 'exit_code': process.returncode,
                             'schema': result.get('schema'), 'code': result.get('code'),
                             'revision': result.get('revision')})
        if ok and 'ok' in result:
            assert result['ok'] is True, (name, result)
        if not ok:
            assert result['ok'] is False and result.get('code'), (name, result)
        return result

    def probe(self, name, sources, language=TASK_LANGUAGE, mode='inspect', ok=True, **fields):
        request = {'schema': 'nex.private-task-migration-request/1', 'mode': mode,
                   'language': language, 'sources': sources, **fields}
        path = self.raw / ('%03d-%s.request.json' % (self.sequence + 1, name))
        write_json(path, request)
        result = self.execute(name, [self.probe_binary, path], ok=ok)
        if ok:
            assert result['schema'] == 'nex.private-task-migration/1', result
            assert result['language'] == language and result['roundtrip'] is True, result
            assert result['lock']['language'] == language, result
        return result

    def cli(self, name, *arguments, cwd=None, ok=True):
        return self.execute(name, [self.compiler, *arguments, '--json'], cwd=cwd, ok=ok, timeout=60)

    def envelopes(self, data, language, revision):
        graph = data['graph']
        assert graph['schema'] == 'nex.graph/2'
        for envelope in (graph, graph['operation_graph'], graph['declaration_graph'], data['identities']):
            assert envelope['language'] == language and envelope['revision'] == revision, envelope
        assert graph['bundle']['schema'] == 'nex.sources/1'
        change = data['changes']['changes'][0]
        assert change['revision'] == revision and change['language'] == language, change
        assert change['source_hash'] == data['source_hash']
        assert change['action'] == 'migrate'
        assert data['changes']['head'] == revision and data['materialized'] is False
        assert data['identities']['namespace'] == graph['identity_namespace']

    def run(self):
        descriptor = self.cli('describe', 'describe')
        self.installed_language = descriptor['version']
        metadata_path = REPO / 'tests/fixtures/language-0.18-task-names.json'
        sql_path = metadata_path.with_suffix('.sql')
        metadata_bytes, sql_bytes = metadata_path.read_bytes(), sql_path.read_bytes()
        metadata = json.loads(metadata_bytes)
        assert metadata['language'] == OLD_LANGUAGE and metadata['toolchain'] == '0.97.0'
        assert sha256(sql_bytes) == metadata['sql_sha256']
        assert sha256(metadata['source'].encode()) == metadata['source_sha256']
        assert [item['value'] for item in metadata['revisions']] == [42, 43]
        assert len(metadata['tables']) == 16
        for item in metadata['revisions']:
            assert sha256(item['source'].encode()) == item['source_sha256']
        self.fixture = {'metadata_sha256': sha256(metadata_bytes), 'sql_sha256': sha256(sql_bytes),
                        'revisions': [item['revision'] for item in metadata['revisions']], 'tables': 16}

        project = self.output / 'legacy-project'
        store = project / '.nex'
        store.mkdir(parents=True)
        database = store / 'graph.db'
        with sqlite3.connect(database) as db:
            db.executescript(sql_bytes.decode())
        (project / 'main.nex').write_text(metadata['source'], encoding='utf-8')
        write_json(project / 'nex.json', {'schema': 'nex.project/1', 'language': OLD_LANGUAGE, 'entry': 'main.nex'})
        shutil.copyfile(sql_path, project / 'original.sql')
        physical = {name: (project / name).read_bytes() for name in ('main.nex', 'nex.json', 'original.sql')}
        before = database_state(database)
        assert before['user_version'] == metadata['user_version']
        assert {name: len(rows) for name, rows in before['tables'].items()} == metadata['tables']
        assert before['tables']['head'] == [(1, metadata['revision'])]

        for index, old in enumerate(metadata['revisions']):
            archived, language = read_revision(database, old['revision'])
            assert language == OLD_LANGUAGE and archived == bundle(old['source'])
            inspected = self.probe('genuine018-recheck-%d' % index, archived, OLD_LANGUAGE)
            assert inspected['revision'] == old['revision'], inspected
            observed = self.probe('genuine018-execute-%d' % index, archived, OLD_LANGUAGE,
                                  mode='run-reference', entry='answer')
            assert observed['value'] == old['value'] and observed['stdout'] == '', observed
            error = self.probe('genuine018-conflict-%d' % index, archived, mode='migrate', ok=False,
                               store_directory=str(store), expected_head=metadata['revision'],
                               original_revision=old['revision'])
            assert error['code'] == 'E_DUPLICATE', error
            assert database_state(database) == before
        original_graph = self.probe('genuine018-idempotent-graph-read', bundle(metadata['source']),
                                    OLD_LANGUAGE, mode='migrate', store_directory=str(store),
                                    expected_head=metadata['revision'])['graph']
        assert original_graph['revision'] == metadata['revision'] and original_graph['language'] == OLD_LANGUAGE
        assert database_state(database) == before
        self.checks.append('genuine018_hashes_rechecks_and_two_historical_observations')

        # Each declaration is independently rejected, so a diagnostic on the
        # first nominal in the genuine fixture cannot mask an unreserved name.
        declarations = [('function-' + name, 'fn ' + name + '(value:i64)->i64{return value+1;}')
                        for name in RESERVED_FUNCTIONS]
        declarations += [('type-' + name, 'struct ' + name + '{value:i64;}') for name in RESERVED_TYPES]
        declarations += [('generic-' + name, 'fn id<' + name + '>(value:' + name + ')->' + name + '{return value;}')
                         for name in RESERVED_TYPES]
        for name, declaration in declarations:
            source = bundle('module reserved_name;\n' + declaration + '\nfn main()->unit{}')
            rejected = self.probe('reserved-' + name, source, mode='migrate', ok=False,
                                  store_directory=str(store), expected_head=metadata['revision'])
            assert rejected['code'] == 'E_DUPLICATE', (name, rejected)
            assert database_state(database) == before
        self.checks.append('all_reserved_declarations_reject_without_any_table_or_ddl_changes')

        repaired, occurrences = repaired_source(metadata['source'])
        candidate = bundle(repaired)
        write_json(self.output / 'reviewed-candidate.sources.json', candidate)
        write_json(self.output / 'reviewed-renames.json', {
            'schema': 'nex.task-migration-test-renames/1', 'original_revision': metadata['revision'],
            'original_source_sha256': metadata['source_sha256'], 'candidate_source_sha256': sha256(repaired.encode()),
            'file': 'main.nex', 'identifiers': RENAMES, 'occurrences': occurrences,
            'preserved_ordinary_identifiers': ORDINARY_NAMES})
        old_repaired = self.probe('repaired018-recheck', candidate, OLD_LANGUAGE)
        new_repaired = self.probe('repaired019-recheck', candidate)
        assert old_repaired['revision'] != new_repaired['revision'], 'language was omitted from semantic revision'
        assert old_repaired['revision'] not in self.fixture['revisions']
        assert new_repaired['revision'] not in self.fixture['revisions']
        old_behavior = self.probe('repaired018-observation', candidate, OLD_LANGUAGE,
                                  mode='run-reference', entry='answer')
        new_behavior = self.probe('repaired019-observation', candidate, mode='run-reference', entry='answer')
        assert old_behavior['value'] == 43 and new_behavior['representation'] == '43'
        assert old_behavior['stdout'] == new_behavior['stdout'] == ''
        assert database_state(database) == before

        exported = self.output / 'exported019'
        migrated = self.probe('migrate-reviewed019', candidate, mode='migrate',
                              store_directory=str(store), expected_head=metadata['revision'],
                              original_revision=metadata['revision'], export_directory=str(exported))
        revision = migrated['revision']
        assert revision == new_repaired['revision']
        assert migrated['original_revision'] == metadata['revision']
        self.envelopes(migrated, TASK_LANGUAGE, revision)
        assert migrated['graph']['bundle'] == candidate
        assert migrated['changes']['changes'][0]['previous_revision'] == metadata['revision']
        assert migrated['changes']['total'] == len(before['tables']['change_journal']) + 1
        names = {node['local_name'] for node in migrated['graph']['nodes']}
        assert set(ORDINARY_NAMES) <= names and not (set(RESERVED_FUNCTIONS) & names)
        after = database_state(database)
        retained_rows(before, after, revision)
        assert {row[-1] for row in after['tables']['revisions']} == {OLD_LANGUAGE, TASK_LANGUAGE}
        assert len(after['tables']['revisions']) == 3
        for old in metadata['revisions']:
            assert read_revision(database, old['revision']) == (bundle(old['source']), OLD_LANGUAGE)
        assert json.loads((exported / 'nex.json').read_text())['language'] == TASK_LANGUAGE
        assert (exported / 'main.nex').read_text() == repaired
        archived, language = read_revision(database, revision)
        assert language == TASK_LANGUAGE and archived == candidate
        replay = self.probe('replay-selected019-archive', archived, language, mode='run-reference', entry='answer')
        assert replay['revision'] == revision and replay['representation'] == '43'
        roundtrip = self.probe('read-selected019-archive', archived, language)
        assert roundtrip['revision'] == revision
        assert database_state(database) == after
        repeated = self.probe('idempotent019-recheck', archived, language, mode='migrate',
                             store_directory=str(store), expected_head=revision,
                             original_revision=metadata['revision'])
        assert repeated['revision'] == revision and database_state(database) == after
        self.checks.append('reviewed_token_rename_migration_preserves_history_ids_schema_and_physical_source')
        self.checks.append('language019_envelopes_lock_journal_archive_export_and_idempotence')

        conflicting = bundle(repaired.replace('checked(5)', 'checked(6)'))
        assert conflicting != candidate
        conflict_export = self.output / 'conflict-must-not-export'
        for expected in ('EMPTY', '0' * 64):
            rejected = self.probe('expected-head-conflict-' + expected[:5], conflicting,
                                  mode='migrate', ok=False, store_directory=str(store), expected_head=expected,
                                  original_revision=metadata['revision'], export_directory=str(conflict_export))
            assert rejected['code'] == 'E_CONFLICT', rejected
            assert database_state(database) == after
            assert not conflict_export.exists()
        self.checks.append('expected_head_conflicts_roll_back_all_rows')

        corrupt = self.output / 'corrupt-language' / '.nex'
        corrupt.mkdir(parents=True)
        with sqlite3.connect(database) as source, sqlite3.connect(corrupt / 'graph.db') as target:
            source.backup(target)
        with sqlite3.connect(corrupt / 'graph.db') as db:
            db.execute('UPDATE revisions SET language=? WHERE hash=?', (OLD_LANGUAGE, revision))
        corrupt_before = database_state(corrupt / 'graph.db')
        rejected = self.probe('corrupt-revision-language', archived, mode='migrate', ok=False,
                              store_directory=str(corrupt), expected_head=revision)
        assert rejected['code'] == 'E_REVISION', rejected
        assert database_state(corrupt / 'graph.db') == corrupt_before
        self.checks.append('corrupted_revision_language_rejected_without_relabel_or_mutation')

        # Negative preflight cases get entirely absent graph destinations.
        plain = bundle('module preflight;fn main()->unit{}')
        for index, language in enumerate(['', 'unknown', '0.99', '0.18\0', None, 19, True]):
            destination = self.output / ('invalid-language-%d' % index) / '.nex'
            rejected = self.probe('invalid-language-%d' % index, plain, language, mode='migrate', ok=False,
                                  store_directory=str(destination), expected_head='EMPTY')
            assert rejected['code'] == ('E_OPTION' if not isinstance(language, str) else 'E_LANGUAGE_VERSION'), rejected
            assert not destination.parent.exists(), 'language failure created a graph directory'
        for name, source, code in [
            ('invalid-type', 'module preflight;fn main()->i64{return true;}', 'E_TYPE'),
            ('invalid-syntax', 'module preflight;fn main()->unit{', 'E_PARSE'),
        ]:
            destination = self.output / name / '.nex'
            rejected = self.probe(name, bundle(source), mode='migrate', ok=False,
                                  store_directory=str(destination), expected_head='EMPTY')
            assert rejected['code'] == code, rejected
            assert not destination.parent.exists(), 'frontend failure created a graph directory'
        lifetimes = json.loads((REPO / 'tests/fixtures/task-lifetimes.json').read_text())
        selected = {'scope-lifetime-own-generic', 'scope-lifetime-own-factory', 'scope-lifetime-own-result-list'}
        found = set()
        for case in lifetimes['cases']:
            if case['name'] not in selected:
                continue
            found.add(case['name'])
            assert case['analysis'] == 'E_TASK_LIFETIME'
            destination = self.output / case['name'] / '.nex'
            rejected = self.probe(case['name'], bundle('module migration_escape;\n' + case['source']),
                                  mode='migrate', ok=False, store_directory=str(destination), expected_head='EMPTY')
            assert rejected['code'] == 'E_TASK_LIFETIME' and rejected['line'] > 0, rejected
            assert rejected['file'].endswith('main.nex'), rejected
            assert not destination.parent.exists(), 'lifetime failure created a graph directory'
        assert found == selected
        self.checks.append('language_frontend_and_known_lifetime_errors_precede_graph_creation')

        for name, sources in [('modular-task-channel', TASK_BUNDLE), ('task-cancel-ancestor', TASK_CONTROLS)]:
            destination = self.output / name / '.nex'
            target = self.output / (name + '-exported')
            task = self.probe(name + '-store', sources, mode='migrate',
                              store_directory=str(destination), expected_head='EMPTY', export_directory=str(target))
            self.envelopes(task, TASK_LANGUAGE, task['revision'])
            task_before = database_state(destination / 'graph.db')
            assert len(task_before['tables']['revisions']) == len(task_before['tables']['change_journal']) == 1
            saved, language = read_revision(destination / 'graph.db', task['revision'])
            assert saved == sources and language == TASK_LANGUAGE
            actual = self.probe(name + '-reference', saved, language, mode='run-reference')
            assert actual['representation'] == '42' and actual['stdout'] == '', actual
            assert actual['revision'] == task['revision']
            checked = self.probe(name + '-roundtrip', saved, language)
            assert checked['revision'] == task['revision']
            repeated = self.probe(name + '-idempotent', saved, language, mode='migrate',
                                  store_directory=str(destination), expected_head=task['revision'])
            assert repeated['revision'] == task['revision']
            assert database_state(destination / 'graph.db') == task_before
            assert json.loads((target / 'nex.json').read_text())['language'] == language
            for path, text in sources['files'].items():
                assert (target / path).read_text() == text
        self.checks.append('real019_tasks_modules_generics_captures_scopes_futures_channels_cancel_roundtrip')

        # Public routes must honor the selected archive rather than stale live
        # metadata/source. Query describe for the installed version; do not pin a
        # public toolchain number or old private execution-guard flag here.
        if self.installed_language != OLD_LANGUAGE:
            rejected = self.cli('stale018-physical-check', 'check', cwd=project, ok=False)
            assert rejected['code'] == 'E_LANGUAGE_VERSION', rejected
        graph = self.cli('public-selected019-graph', 'graph', '--revision', revision, cwd=project)
        assert graph['language'] == TASK_LANGUAGE and graph['revision'] == revision
        context = self.cli('public-selected019-context', 'context', '--symbol', 'legacy_task_names::answer',
                           '--revision', revision, cwd=project)
        assert context['language'] == TASK_LANGUAGE and context['revision'] == revision
        history = self.cli('public-history-languages', 'history', cwd=project)
        assert {row['language'] for row in history['revisions']} == {OLD_LANGUAGE, TASK_LANGUAGE}
        selected_export = self.output / 'public-selected019-export'
        self.cli('public-selected019-export', 'export', '--revision', revision, '--directory', selected_export, cwd=project)
        assert json.loads((selected_export / 'nex.json').read_text())['language'] == TASK_LANGUAGE
        assert (selected_export / 'main.nex').read_text() == repaired
        evaluated = self.cli('public-selected019-eval', 'eval', '--revision', revision, cwd=project)
        assert evaluated['stdout'] == '43\n', evaluated
        assert self.cli('public-exported019-check', 'check', cwd=exported)['revision'] == revision
        self.cli('public-exported019-tests', 'test', cwd=exported)
        task_export = self.output / 'modular-task-channel-exported'
        task_observation = self.cli('public-exported019-task-eval', 'eval', cwd=task_export)
        assert task_observation['value'] == 42 and task_observation['stdout'] == '', task_observation
        assert database_state(database) == after
        for name, content in physical.items():
            assert (project / name).read_bytes() == content, ('changed physical historical file', name)
        assert metadata_path.read_bytes() == metadata_bytes and sql_path.read_bytes() == sql_bytes
        self.checks.append('public_archived_graph_eval_exported_check_test_and_task_reference')

        # Exercise public migrate against another complete genuine SQL store.
        public = self.output / 'public-migration'
        public_store = public / '.nex'
        public_store.mkdir(parents=True)
        with sqlite3.connect(public_store / 'graph.db') as db:
            db.executescript(sql_bytes.decode())
        (public / 'main.nex').write_bytes(physical['main.nex'])
        (public / 'nex.json').write_bytes(physical['nex.json'])
        public_before = database_state(public_store / 'graph.db')
        graph_candidate = copy.deepcopy(original_graph)
        graph_candidate['source'] = repaired
        graph_candidate['bundle'] = candidate
        # This is an explicitly separate reviewed source candidate, not a claim
        # that the repaired source has the old semantic hash.
        candidate_file = self.output / 'reviewed-public-migration.graph.json'
        write_json(candidate_file, graph_candidate)
        changed = self.cli('public-reviewed018-migrate', 'migrate', candidate_file, cwd=public)
        assert changed['revision'] == revision and changed['language'] == TASK_LANGUAGE
        assert changed['materialized'] is False
        retained_rows(public_before, database_state(public_store / 'graph.db'), revision)
        public_stable = database_state(public_store / 'graph.db')
        self.cli('public-idempotent019-migrate', 'migrate', '--revision', revision, cwd=public)
        assert database_state(public_store / 'graph.db') == public_stable
        assert (public / 'main.nex').read_bytes() == physical['main.nex']
        assert (public / 'nex.json').read_bytes() == physical['nex.json']
        assert metadata_path.read_bytes() == metadata_bytes and sql_path.read_bytes() == sql_bytes
        self.checks.append('public_migrate_reviewed_candidate_keeps_genuine018_history')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe')
    parser.add_argument('compiler')
    arguments = parser.parse_args()
    if not __debug__:
        raise RuntimeError('task migration checks require active Python assertions')
    destination = os.environ.get('NEX_TASK_MIGRATION_OUTPUT')
    temporary = None
    if destination:
        output = Path(destination).resolve()
        output.mkdir(parents=True, exist_ok=False)
    else:
        temporary = tempfile.TemporaryDirectory(prefix='nex-task-migration-')
        output = Path(temporary.name)
    checks = MigrationChecks(arguments.probe, arguments.compiler, output)
    started = time.monotonic()
    report = {'schema': 'nex.task-migration-tests/1', 'ok': False}
    try:
        checks.run()
        report.update(ok=True, installed_language=checks.installed_language,
                      old_language=OLD_LANGUAGE, target_language=TASK_LANGUAGE,
                      fixture=checks.fixture, checks=checks.checks,
                      requests=checks.sequence, seconds=time.monotonic() - started)
    except BaseException as error:
        report.update(error=repr(error), checks=checks.checks,
                      requests=checks.sequence, seconds=time.monotonic() - started)
        raise
    finally:
        report['observations'] = checks.records
        write_json(output / 'report.json', report)
        print(json.dumps({key: value for key, value in report.items()
                          if key not in ('observations', 'fixture')}, ensure_ascii=False), flush=True)
        if temporary:
            temporary.cleanup()


if __name__ == '__main__':
    main()
