"""Genuine SDK115 language019 archives migrate explicitly to language020."""
import argparse
import copy
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from task_migration import (MigrationChecks, REPO, bundle, database_state,
                            read_revision, repaired_source, retained_rows,
                            sha256, write_json)

SQL_PINS = {
    'history': '37b190db84cb8305b867cee383eb7233e124b1aa692b8f7e69876a8903276de8',
    'tasks': '135e47e4f6de69a9e0035d071a740d58e11d88ae361144e399f04cf334724a98',
    'fs-helper': '4ec772a7c2dbc47496c9ee5b8d2e85bbbd9d6106cef622d92e752def387b7640',
}
TARGET = '0.23'


class FileMigrationChecks(MigrationChecks):
    def fixture(self, name):
        path = REPO/'tests/fixtures'/('language-0.19-sdk115-' + name + '.json')
        metadata = json.loads(path.read_text())
        raw = path.with_suffix('.sql').read_bytes()
        assert metadata['schema'] == 'nex.language-019-migration-fixture/1'
        assert metadata['language'] == '0.19' and metadata['sdk']['toolchain'] == '0.108.0'
        assert metadata['sdk']['acceptance_ok'] is True
        assert metadata['sdk']['binary_sha256'] == 'a327d02e7f0b668962fdece6709cb7d0b91ef4b4b80abdc5e79802c6e8c2b464'
        assert sha256(raw) == metadata['sql_sha256'] == SQL_PINS[name]
        assert len(metadata['tables']) == 16 and metadata['metadata']['schema'] == '4'
        assert all(row['language'] == '0.19' for row in metadata['revisions'])
        self.fixtures[name] = {'metadata_sha256':sha256(path.read_bytes()), 'sql_sha256':sha256(raw),
                               'head':metadata['head'], 'revisions':len(metadata['revisions'])}
        return metadata, raw

    def restore(self, label, metadata, sql):
        project = self.output/label
        directory = project/'.nex'; directory.mkdir(parents=True)
        with sqlite3.connect(directory/'graph.db') as db: db.executescript(sql.decode())
        head = next(row for row in metadata['revisions'] if row['revision'] == metadata['head'])
        for key, text in head['bundle']['files'].items():
            path = project/key; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text)
        write_json(project/'nex.json', {'schema':'nex.project/1','language':'0.19','entry':head['bundle']['entry']})
        for key, text in metadata.get('physical_files', {}).items(): (project/key).write_text(text)
        (project/'original.sql').write_bytes(sql)
        before = database_state(directory/'graph.db')
        assert {name:len(rows) for name, rows in before['tables'].items()} == metadata['tables']
        assert before['tables']['head'] == [(1, metadata['head'])]
        physical = {key:path.read_bytes() for key, path in
                    [(name, project/name) for name in [*head['bundle']['files'], 'nex.json', 'original.sql']]}
        return project, directory/'graph.db', before, physical

    def unmodified(self, project, physical):
        for name, raw in physical.items(): assert (project/name).read_bytes() == raw, name

    def run(self):
        self.fixtures = {}
        self.installed_language = self.cli('describe', 'describe')['version']
        assert self.installed_language == TARGET
        for name in ('history', 'tasks'):
            metadata, sql = self.fixture(name)
            project, database, before, physical = self.restore(name, metadata, sql)
            selected = {}
            for index, row in enumerate(metadata['revisions']):
                old = self.probe(name+'-genuine019-'+str(index), row['bundle'], '0.19')
                assert old['revision'] == row['revision'] and old['public_source_tasks']
                assert old['supports_task_file_reads'] is False
                new = self.probe(name+'-explicit020-'+str(index), row['bundle'], TARGET)
                assert new['revision'] != old['revision'] and new['source_hash'] == old['source_hash']
                assert new['public_source_tasks'] and new['supports_task_file_reads']
                selected[row['revision']] = new['revision']
                saved, language = read_revision(database, row['revision'])
                assert saved == row['bundle'] and language == '0.19'
                if name == 'tasks':
                    for version in ('0.19', TARGET):
                        run = self.probe(name+'-reference-'+version, saved, version, mode='run-reference', entry='solve')
                        assert run['representation'] == '42' and run['stdout'] == ''
            assert database_state(database) == before
            for operation in ('check', 'eval', 'run', 'test', 'build'):
                rejected = self.cli(name+'-physical019-'+operation, operation, cwd=project, ok=False)
                assert rejected['code'] == 'E_LANGUAGE_VERSION'
                assert database_state(database) == before
            changed = self.cli(name+'-public-migrate', 'migrate', '--expected-revision', metadata['head'], cwd=project)
            current = selected[metadata['head']]
            assert changed['revision'] == current and changed['language'] == TARGET
            assert changed['origin_language'] == '0.19' and changed['origin_verified'] is True
            assert changed['previous_revision'] == metadata['head'] and changed['materialized'] is False
            after = database_state(database); retained_rows(before, after, current)
            old_namespace = dict(before['tables']['metadata'])['identity_namespace']
            assert dict(after['tables']['metadata'])['identity_namespace'] == old_namespace
            graph = self.cli(name+'-selected020-graph', 'graph', '--revision', current, cwd=project)
            for envelope in (graph, graph['operation_graph'], graph['declaration_graph']):
                assert envelope['language'] == TARGET and envelope['revision'] == current
            assert graph['identity_namespace'] == old_namespace
            archived, language = read_revision(database, current)
            old_bundle, _ = read_revision(database, metadata['head'])
            assert archived == old_bundle and language == TARGET
            journal = self.cli(name+'-journal', 'changes', cwd=project)
            event = journal['changes'][0]
            assert event['language'] == TARGET and event['previous_revision'] == metadata['head']
            assert all(json.loads(row[3])['language'] == '0.19' for row in before['tables']['change_journal'])
            self.cli(name+'-idempotent-current', 'migrate', '--revision', current, cwd=project)
            assert database_state(database) == after
            conflict = self.cli(name+'-head-conflict', 'migrate', '--revision', metadata['head'],
                                '--expected-revision', metadata['head'], cwd=project, ok=False)
            assert conflict['code'] == 'E_CONFLICT' and database_state(database) == after
            old_export = self.output/(name+'-old-export')
            self.cli(name+'-export019', 'export', '--revision', metadata['head'], '--directory', old_export, cwd=project)
            assert json.loads((old_export/'nex.json').read_text())['language'] == '0.19'
            rejected = self.cli(name+'-old-export-check', 'check', cwd=old_export, ok=False)
            assert rejected['code'] == 'E_LANGUAGE_VERSION' and not (old_export/'.nex').exists()
            new_export = self.output/(name+'-new-export')
            self.cli(name+'-export020', 'export', '--revision', current, '--directory', new_export, cwd=project)
            assert json.loads((new_export/'nex.json').read_text())['language'] == TARGET
            assert json.loads((new_export/'nex.lock.json').read_text())['language'] == TARGET
            assert self.cli(name+'-export020-check', 'check', cwd=new_export)['revision'] == current
            task = self.cli(name+'-current-task-init', 'task', new_export/'main.nex', '--kind', 'init', cwd=new_export)
            task_path = project/'reviewed020.task.json'; write_json(task_path, task)
            rejected = self.cli(name+'-task-old-candidate', 'task', task_path, '--kind', 'check',
                                '--revision', metadata['head'], cwd=project, ok=False)
            assert rejected['code'] == 'E_LANGUAGE_VERSION' and database_state(database) == after
            evaluated = self.cli(name+'-selected020-eval', 'eval', '--revision', current, cwd=project)
            assert evaluated['stdout'] == '42\n'
            rejected = self.cli(name+'-selected019-execution', 'eval', '--revision', metadata['head'], cwd=project, ok=False)
            assert rejected['code'] == 'E_LANGUAGE_VERSION'
            assert database_state(database) == after
            self.unmodified(project, physical)
            self.checks.append(name+'_genuine019_identity_migration_history_ids_envelopes_export_replay_idempotence')
            if name == 'history':
                self.corruption(metadata, sql)
                # Select the first archived source explicitly, despite stale
                # physical source and a newer020 HEAD.
                first = metadata['revisions'][0]
                replay = self.cli('history-migrate-earlier019', 'migrate', '--revision', first['revision'], cwd=project)
                assert replay['revision'] == selected[first['revision']]
                assert self.cli('history-earlier020-eval', 'eval', '--revision', replay['revision'], cwd=project)['stdout'] == '41\n'
                retained_rows(after, database_state(database), replay['revision'])
                self.unmodified(project, physical)
        self.callback_versions()
        self.preflight_and_reviewed_helper()
        self.explicit018_paths()

    def corruption(self, metadata, sql):
        for language in ('0.1', '0.18', '0.17', TARGET, 'unknown'):
            project, database, _, physical = self.restore('corrupt-'+language, metadata, sql)
            with sqlite3.connect(database) as db:
                db.execute('UPDATE revisions SET language=? WHERE hash=?', (language, metadata['head']))
            before = database_state(database)
            rejected = self.cli('corrupt-origin-'+language, 'migrate', cwd=project, ok=False)
            assert rejected['code'] == ('E_LANGUAGE_VERSION' if language == 'unknown' else 'E_REVISION')
            assert database_state(database) == before
            self.unmodified(project, physical)
        project, database, _, _ = self.restore('corrupt-source', metadata, sql)
        with sqlite3.connect(database) as db:
            raw = db.execute('SELECT source FROM revisions WHERE hash=?', (metadata['head'],)).fetchone()[0]
            db.execute('UPDATE revisions SET source=? WHERE hash=?', (raw.replace('return 42', 'return 43'), metadata['head']))
        before = database_state(database)
        rejected = self.cli('corrupt-origin-source', 'migrate', cwd=project, ok=False)
        assert rejected['code'] == 'E_REVISION' and database_state(database) == before
        self.checks.append('corrupt_known_origin_language_hash_and_unknown_language_fail_without_mutation')

    def callback_versions(self):
        source = bundle('''module versioned_callbacks;
server fn main()->result<str> !{task,fs}{
 return with_tasks(1,server fn(scope:task_scope)->result<str> !{task,fs}{
  let reader:task<result<str>>=task_spawn(scope,server fn()->result<str> !{task,fs}{return file_read_text("input.txt");});
  return task_wait(reader);
 });
}''')
        rejected = self.probe('019-callback-rule-retained', source, '0.19', ok=False)
        assert rejected['code'] == 'E_EFFECT'
        accepted = self.probe('020-callback-read-recheck', source, TARGET)
        assert accepted['supports_task_file_reads']
        self.checks.append('genuine019_callback_effect_rule_distinct_from020_without_reserved_name_repair')

    def preflight_and_reviewed_helper(self):
        metadata, sql = self.fixture('fs-helper')
        project, database, before, physical = self.restore('sync-fs-helper', metadata, sql)
        old = metadata['revisions'][0]
        assert self.probe('genuine019-fs-helper-recheck', old['bundle'], '0.19')['revision'] == old['revision']
        rejected = self.cli('020-helper-no-auto-effect-repair', 'migrate', cwd=project, ok=False)
        assert rejected['code'] == 'E_EFFECT' and database_state(database) == before
        graph = {'schema':'nex.graph/2','language':'0.19','revision':old['revision'],
                 'bundle':old['bundle'], 'source':old['bundle']['files']['main.nex']}
        for name, candidate, code in (
            ('unknown-language', {**graph, 'language':'unknown'}, 'E_LANGUAGE_VERSION'),
            ('corrupt-hash', {**graph, 'revision':'0'*64}, 'E_REVISION'),
            ('target-helper-error', graph, 'E_EFFECT')):
            destination = self.output/('fresh-'+name); destination.mkdir()
            write_json(destination/'nex.json', {'schema':'nex.project/1','language':TARGET,'entry':'missing.nex'})
            path = self.output/(name+'.graph.json'); write_json(path, candidate)
            rejected = self.cli('fresh-'+name, 'migrate', path, cwd=destination, ok=False)
            assert rejected['code'] == code and not (destination/'.nex').exists()
        repaired = copy.deepcopy(graph)
        text = graph['source'].replace('legacy()->result<str> !{fs}', 'legacy()->result<str> !{task,fs}')
        assert text != graph['source']
        repaired['source'] = text; repaired['bundle'] = bundle(text)
        path = self.output/'reviewed-helper-effect.graph.json'; write_json(path, repaired)
        accepted = self.cli('reviewed-explicit-helper-effect-migrate', 'migrate', path, cwd=project)
        assert accepted['origin_verified'] and accepted['origin_language'] == '0.19'
        assert accepted['revision'] == self.probe('reviewed-helper020', repaired['bundle'], TARGET)['revision']
        retained_rows(before, database_state(database), accepted['revision'])
        self.unmodified(project, physical)
        self.checks.append('target_preflight_before_destination_creation_and_explicit_reviewed_helper_effect_repair')

    def explicit018_paths(self):
        path = REPO/'tests/fixtures/language-0.18-task-names.json'
        meta = json.loads(path.read_text()); sql = path.with_suffix('.sql').read_bytes()
        assert sha256(sql) == meta['sql_sha256']
        source, _ = repaired_source(meta['source']); candidate = bundle(source)
        revisions = {}
        for language in ('0.19', TARGET):
            directory = self.output/('from018-'+language)/'.nex'; directory.mkdir(parents=True)
            with sqlite3.connect(directory/'graph.db') as db: db.executescript(sql.decode())
            before = database_state(directory/'graph.db')
            result = self.probe('explicit018-to-'+language, candidate, language, mode='migrate',
                                store_directory=str(directory), expected_head=meta['revision'], original_revision=meta['revision'])
            self.envelopes(result, language, result['revision'])
            retained_rows(before, database_state(directory/'graph.db'), result['revision'])
            revisions[language] = result['revision']
        assert revisions['0.19'] != revisions[TARGET]
        directory = self.output/'from018-0.19/.nex'; before = database_state(directory/'graph.db')
        result = self.probe('explicit018-019-020-chain', candidate, TARGET, mode='migrate',
                            store_directory=str(directory), expected_head=revisions['0.19'], original_revision=revisions['0.19'])
        assert result['revision'] == revisions[TARGET]
        retained_rows(before, database_state(directory/'graph.db'), result['revision'])
        self.checks.append('explicit018_019_and018_020_targets_and_sequential_history_preserved')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('probe'); parser.add_argument('compiler'); args = parser.parse_args()
    if not __debug__: raise RuntimeError('migration checks require active Python assertions')
    temporary = None
    if os.environ.get('NEX_TASK_FILE_MIGRATION_OUTPUT'):
        output = Path(os.environ['NEX_TASK_FILE_MIGRATION_OUTPUT']).resolve(); output.mkdir(parents=True, exist_ok=False)
    else:
        temporary = tempfile.TemporaryDirectory(prefix='nex-task-file-migration-'); output = Path(temporary.name)
    checks = FileMigrationChecks(args.probe, args.compiler, output)
    started = time.monotonic(); report = {'schema':'nex.task-file-migration-tests/1','ok':False,
        'compiler_sha256':sha256(checks.compiler.read_bytes()), 'probe_sha256':sha256(checks.probe_binary.read_bytes())}
    try:
        checks.run(); report.update(ok=True, language=TARGET, fixtures=checks.fixtures)
    except BaseException as error:
        report['error'] = repr(error); raise
    finally:
        report.update(checks=checks.checks, requests=checks.sequence, observations=checks.records, seconds=time.monotonic()-started)
        write_json(output/'report.json', report)
        print(json.dumps({key:value for key,value in report.items() if key not in ('observations','fixtures')}), flush=True)
        if temporary: temporary.cleanup()


if __name__ == '__main__': main()
