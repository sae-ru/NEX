"""CLI-only installed SDK migration gate for genuine SDK115 language019 stores.

The caller owns command/raw-output recording and the installed compiler choice.
No compiler probe, old SDK execution, network access or mutable source is used.
"""
from collections import Counter
from contextlib import closing
import copy
import hashlib
import json
from pathlib import Path
import sqlite3


_SQL = {
    'history': '37b190db84cb8305b867cee383eb7233e124b1aa692b8f7e69876a8903276de8',
    'tasks': '135e47e4f6de69a9e0035d071a740d58e11d88ae361144e399f04cf334724a98',
    'fs-helper': '4ec772a7c2dbc47496c9ee5b8d2e85bbbd9d6106cef622d92e752def387b7640',
}


def _require(value, message):
    if not value:
        raise AssertionError(message)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _write(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def _state(database):
    # Existing DB only; query_only guards every SQL statement, and closing also
    # releases SQLite readers before the matching CLI opens its transaction.
    with closing(sqlite3.connect(database.resolve().as_uri() + '?mode=rw', uri=True)) as db:
        db.execute('PRAGMA query_only=ON')
        names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {'ddl': db.execute('SELECT * FROM sqlite_master ORDER BY name').fetchall(),
                'user_version': db.execute('PRAGMA user_version').fetchone()[0],
                'application_id': db.execute('PRAGMA application_id').fetchone()[0],
                'tables': {name: sorted(db.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                           for name in names}}


def _retained(before, after, head):
    _require(before['ddl'] == after['ddl'], 'migration changed graph DDL')
    for field in ('user_version', 'application_id'):
        _require(before[field] == after[field], 'migration changed SQLite ' + field)
    _require(before['tables'].keys() == after['tables'].keys(), 'migration changed table inventory')
    for name, rows in before['tables'].items():
        if name != 'head':
            _require(not (Counter(rows) - Counter(after['tables'][name])), 'migration lost historical rows: ' + name)
    _require(after['tables']['head'] == [(1, head)], 'migration selected wrong HEAD')


def check_installed_task_migration(cli, root, resources):
    """Exercise actual CLI archive migration; return bounded evidence.

    cli accepts *arguments, cwd, expected_success and timeout and retains its
    raw requests/responses. The caller's SDK/source-hidden acceptance gate is
    responsible for proving the compiler/resource provenance of this execution.
    """
    root, resources = Path(root), Path(resources)
    out = root/'language-migration019-020'
    out.mkdir(exist_ok=False)
    fixtures = resources/'examples/task-migration'
    current_language=cli('describe')['version'];_require(current_language=='0.23', 'migration gate requires the matching language023 SDK')
    evidence = {'language':current_language, 'origin_language':'0.19', 'fixtures':{}, 'stores':{}}

    def restore(name, label=None):
        metadata_path = fixtures/('language-0.19-sdk115-' + name + '.json')
        raw_metadata = metadata_path.read_bytes(); metadata = json.loads(raw_metadata)
        sql = metadata_path.with_suffix('.sql').read_bytes()
        _require(metadata['language'] == '0.19' and metadata['sdk']['toolchain'] == '0.108.0', 'fixture is not genuine SDK115019')
        _require(metadata['sdk']['acceptance_ok'] and metadata['sdk']['binary_sha256'] ==
                 'a327d02e7f0b668962fdece6709cb7d0b91ef4b4b80abdc5e79802c6e8c2b464', 'fixture SDK provenance differs')
        _require(_sha(sql) == metadata['sql_sha256'] == _SQL[name], 'fixture SQL digest differs')
        _require(len(metadata['tables']) == 16 and metadata['metadata']['schema'] == '4', 'fixture lost graph schema4 tables')
        project = out/(label or name); (project/'.nex').mkdir(parents=True)
        with closing(sqlite3.connect(project/'.nex/graph.db')) as db:
            db.executescript(sql.decode('utf-8'))
        selected = next(r for r in metadata['revisions'] if r['revision'] == metadata['head'])
        for key, text in selected['bundle']['files'].items():
            path = project/key; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(text, encoding='utf-8')
        _write(project/'nex.json', {'schema':'nex.project/1','language':'0.19','entry':selected['bundle']['entry']})
        for key, text in metadata.get('physical_files', {}).items():
            (project/key).write_text(text, encoding='utf-8')
        (project/'original.sql').write_bytes(sql)
        physical = {str(p.relative_to(project)):p.read_bytes() for p in project.rglob('*') if p.is_file() and '.nex' not in p.relative_to(project).parts}
        database = project/'.nex/graph.db'; before = _state(database)
        _require({name:len(rows) for name, rows in before['tables'].items()} == metadata['tables'], 'restored fixture row counts differ')
        _require(before['tables']['head'] == [(1, metadata['head'])], 'restored fixture HEAD differs')
        evidence['fixtures'][name] = {'sql_sha256':_sha(sql), 'metadata_sha256':_sha(raw_metadata),
            'original_sdk_sha256':metadata['sdk']['binary_sha256'], 'revisions':len(metadata['revisions'])}
        return project, database, metadata, selected, before, physical

    def physical_unchanged(project, physical):
        for key, raw in physical.items():
            _require((project/key).read_bytes() == raw, 'migration changed physical projection: ' + key)

    for name in ('history', 'tasks'):
        project, database, metadata, selected, before, physical = restore(name)
        rejected = cli('check', cwd=project, expected_success=False)
        _require(rejected['code'] == 'E_LANGUAGE_VERSION' and _state(database) == before, 'physical019 version guard mutated store')
        # A current physical manifest must not make ordinary source checking
        # migrate an older graph HEAD. Exercise the actual CLI, then restore
        # the exact physical bytes before the explicit migration below.
        manifest = project/'nex.json'
        original_manifest = manifest.read_bytes()
        current_manifest = json.loads(original_manifest)
        current_manifest['language'] = evidence['language']
        try:
            _write(manifest, current_manifest)
            rejected = cli('check', cwd=project, expected_success=False)
            _require(rejected['code'] == 'E_LANGUAGE_VERSION' and _state(database) == before,
                     'current physical language silently changed retained HEAD or graph rows')
        finally:
            manifest.write_bytes(original_manifest)
        physical_unchanged(project, physical)
        migrated = cli('migrate', '--expected-revision', metadata['head'], cwd=project)
        current_revision = migrated['revision']
        _require(migrated['language'] == current_language and migrated['origin_language'] == '0.19' and
                 migrated['origin_verified'] and not migrated['materialized'] and current_revision != metadata['head'], 'migration did not verify genuine019 identity')
        after = _state(database); _retained(before, after, current_revision)
        namespace = dict(before['tables']['metadata'])['identity_namespace']
        _require(dict(after['tables']['metadata'])['identity_namespace'] == namespace, 'migration changed namespace')
        graph = cli('graph', '--revision', current_revision, cwd=project)
        for envelope in (graph, graph['operation_graph'], graph['declaration_graph']):
            _require(envelope['language'] == current_language and envelope['revision'] == current_revision, 'new graph envelope language/revision differs')
        _require(graph['bundle'] == selected['bundle'], '019-to020 migration changed source without review')
        _require(cli('eval', '--revision', current_revision, cwd=project)['stdout'] == '42\n', 'migrated selected source changed observation')
        if name == 'tasks':
            _require(cli('run', '--revision', current_revision, cwd=project, timeout=300)['stdout'] == '42\n', 'installed native task archive differs')
        rejected = cli('eval', '--revision', metadata['head'], cwd=project, expected_success=False)
        _require(rejected['code'] == 'E_LANGUAGE_VERSION', 'old019 execution silently acquired020 semantics')
        cli('migrate', '--revision', current_revision, cwd=project)
        _require(_state(database) == after, 'idempotent current migration changed rows')
        rejected = cli('migrate', '--revision', metadata['head'], '--expected-revision', metadata['head'], cwd=project, expected_success=False)
        _require(rejected['code'] == 'E_CONFLICT' and _state(database) == after, 'HEAD conflict did not preserve all rows')
        old_export, new_export = out/(name+'-019-export'), out/(name+'-020-export')
        cli('export', '--revision', metadata['head'], '--directory', old_export, cwd=project)
        cli('export', '--revision', current_revision, '--directory', new_export, cwd=project)
        _require(json.loads((old_export/'nex.json').read_text())['language'] == '0.19', 'old source export was retagged')
        _require(json.loads((new_export/'nex.json').read_text())['language'] == current_language and
                 json.loads((new_export/'nex.lock.json').read_text())['language'] == current_language, 'new export/lock language differs')
        _require(cli('check', cwd=new_export)['revision'] == current_revision, 'new exported source lost revision')
        changes = cli('changes', cwd=project)
        _require(changes['changes'][0]['language'] == current_language and changes['changes'][0]['previous_revision'] == metadata['head'], 'migration journal language/origin differs')
        _require(_state(database) == after, 'selected archive reads changed history')
        physical_unchanged(project, physical)
        evidence['stores'][name] = {'old_head':metadata['head'], 'revision':current_revision, 'namespace':namespace,
            'tables':16, 'old_rows_ids_ddl_retained':True, 'physical_projection_unchanged':True,
            'canonical_origin_verified':True, 'idempotent':True, 'conflict_rollback':True,
            'implicit_HEAD_language_change_rejected':True,
            'native_task_archive':name == 'tasks'}

    for language in ('0.1', '0.18', '0.17', '0.20', '0.21', '0.22', '0.23', 'unknown'):
        project, database, metadata, _, _, _ = restore('history', 'corrupt-language-' + language)
        with closing(sqlite3.connect(database)) as db:
            db.execute('UPDATE revisions SET language=? WHERE hash=?', (language, metadata['head'])); db.commit()
        before = _state(database)
        rejected = cli('migrate', cwd=project, expected_success=False)
        _require(rejected['code'] == ('E_LANGUAGE_VERSION' if language == 'unknown' else 'E_REVISION') and
                 _state(database) == before, 'corrupted stored language was relabeled or mutated')

    project, database, metadata, selected, before, physical = restore('fs-helper')
    rejected = cli('migrate', cwd=project, expected_success=False)
    _require(rejected['code'] == 'E_EFFECT' and _state(database) == before, '020 silently promoted genuine019 fs-only helper')
    graph = {'schema':'nex.graph/2','language':'0.19','revision':metadata['head'],'bundle':selected['bundle'],
             'source':selected['bundle']['files']['main.nex']}
    for name, candidate, code in (
        ('unknown', {**graph, 'language':'unknown'}, 'E_LANGUAGE_VERSION'),
        ('corrupt', {**graph, 'revision':'0'*64}, 'E_REVISION'),
        ('target', graph, 'E_EFFECT')):
        destination = out/('fresh-' + name); destination.mkdir()
        _write(destination/'nex.json', {'schema':'nex.project/1','language':current_language,'entry':'missing.nex'})
        path = out/(name+'.graph.json'); _write(path, candidate)
        rejected = cli('migrate', path, cwd=destination, expected_success=False)
        _require(rejected['code'] == code and not (destination/'.nex').exists(), 'failed migration created a graph destination')
    repaired = copy.deepcopy(graph)
    text = graph['source'].replace('legacy()->result<str> !{fs}', 'legacy()->result<str> !{task,fs}')
    _require(text != graph['source'], 'reviewed helper repair did not change its declared effect')
    repaired['source'] = text; repaired['bundle']['files']['main.nex'] = text
    path = out/'reviewed-helper.graph.json'; _write(path, repaired)
    migrated = cli('migrate', path, cwd=project)
    _require(migrated['origin_verified'] and migrated['origin_language'] == '0.19' and migrated['language'] == current_language, 'reviewed repair lost verified retained origin')
    _retained(before, _state(database), migrated['revision']); physical_unchanged(project, physical)
    evidence.update(ok=True, genuine019=True, history_preserved=True,
                    corrupt_stored_languages_rejected=8, fresh_preflight_failures_without_store=3,
                    reviewed_helper_effect_repair=True, reserved_name_repair=False,
                    historical_source_language_relabelled=False)
    evidence['head_language_guard'] = {'schema':'nex.head-language-guard/1',
        'actual_cli':True, 'compiler_language':evidence['language'], 'origin_language':'0.19',
        'fixtures':['history','tasks'], 'command':'check', 'code':'E_LANGUAGE_VERSION',
        'all16_tables_schema_rows_ids_preserved':True, 'physical_projection_restored':True}
    _write(out/'migration-evidence.json', evidence)
    return evidence
