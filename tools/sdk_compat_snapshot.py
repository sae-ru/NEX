"""Verify source 0.30 snapshot interoperability between two installed NEX SDKs."""
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
from contextlib import closing

MAIN = '''module compatibility::app;
import "./score.nex" as score;
fn main() -> unit !{io,state} { print(score::value()); }
'''
SCORE = '''module compatibility::score;
pub fn value() -> i64 !{state} {
  let value: cell<i64> = cell_new(40);
  cell_write(value, cell_read(value) + INCREMENT);
  return cell_read(value);
}
'''


def require(condition, message):
    if not condition:
        raise ValueError("snapshot compatibility: " + message)


def cli(nex, cwd, *args):
    # Let each SDK resolve its own installed resources and ignore an inherited
    # override that would silently mix the candidate with another toolchain.
    environment = os.environ.copy()
    environment.pop('NEX_RESOURCE_DIR', None)
    completed = subprocess.run([nex, *args, '--json'], cwd=cwd, env=environment,
                               capture_output=True, timeout=180)
    if completed.returncode:
        detail = (completed.stderr or completed.stdout).decode('utf-8', errors='replace')[:1000]
        raise ValueError(f"snapshot compatibility: {args[0]} exited {completed.returncode}: {detail}")
    return json.loads(completed.stdout)


def digest(value):
    return hashlib.sha256(value).hexdigest()


def object_digest(value):
    return digest(json.dumps(value, sort_keys=True, separators=(',', ':')).encode())


def row_digest(project):
    """Compare logical rows. SQLite checkpointing can change database file bytes."""
    database = project / '.nex' / 'graph.db'
    # All NEX subprocesses have exited. Confirm there are no uncheckpointed
    # pages before an immutable inspection, which cannot create WAL sidecars.
    require(all(not p.exists() or p.stat().st_size == 0 for p in
                (Path(str(database) + '-wal'), Path(str(database) + '-journal'))), 'graph still has an active journal')
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro&immutable=1', uri=True)) as db:
        schema = db.execute("SELECT name, sql FROM sqlite_schema WHERE type='table' ORDER BY name").fetchall()
        tables = []
        for name, sql in schema:
            quoted = '"' + name.replace('"', '""') + '"'
            rows = sorted(repr(row) for row in db.execute('SELECT * FROM ' + quoted))
            tables.append((name, sql, rows))
        return object_digest(tables)


def identities(nex, project, revision):
    records = {}
    for kind in ('function', 'operation'):
        page = cli(nex, project, 'identities', '--entity', kind, '--revision', revision, '--limit', '1000')
        require(page['revision'] == revision and page['language'] == '0.30' and page['truncated'] is False,
                'wrong or incomplete identity page')
        nodes = sorted((r['symbol'], r['path'], r['id'], r['hash']) for r in page['nodes'] if r['kind'] == kind)
        require(len(nodes) == len(page['nodes']) and {n[0] for n in nodes} ==
                {'compatibility::score::value', 'compatibility::app::main'}, 'missing function or operation IDs')
        require(all(re.fullmatch('[a-f0-9]{32}', n[2]) and re.fullmatch('[a-f0-9]{64}', n[3]) for n in nodes),
                'invalid local identity or content hash')
        records[kind] = {'count': len(nodes), 'sha256': object_digest(nodes),
                         'local_ids_sha256': object_digest([node[:3] for node in nodes]),
                         'namespace': page['namespace']}
    return records


def check_snapshot(baseline_nex: Path, candidate_nex: Path, root: Path) -> dict:
    """Create a baseline snapshot; recover, replay and materialize it with the candidate."""
    baseline_nex, candidate_nex = (Path(p).resolve(strict=True) for p in (baseline_nex, candidate_nex))
    work = Path(root).resolve() / 'snapshot-compatibility'
    work.mkdir(parents=True, exist_ok=False)
    original, archive, recovered = (work / name for name in ('baseline-project', 'snapshot', 'recovered'))
    original.mkdir()
    (original / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.30',
                                                   'entry': 'main.nex'}), encoding='utf-8')
    (original / 'main.nex').write_bytes(MAIN.encode())
    revisions = []
    for increment in (1, 2):
        (original / 'score.nex').write_bytes(SCORE.replace('INCREMENT', str(increment)).encode())
        revision = cli(baseline_nex, original, 'check')['revision']
        require(re.fullmatch('[0-9a-f]{64}', revision) and revision not in revisions, 'invalid or repeated revision')
        revisions.append(revision)
    head = revisions[-1]
    history = cli(baseline_nex, original, 'history')
    require(history['head'] == head and len(history['revisions']) == 2 and
            {(r['revision'], r['language']) for r in history['revisions']} == {(r, '0.30') for r in revisions},
            'baseline history did not retain both source versions')
    nodes = [identities(baseline_nex, original, r) for r in revisions]
    for kind in ('function', 'operation'):
        require(nodes[0][kind]['local_ids_sha256'] == nodes[1][kind]['local_ids_sha256']
                and nodes[0][kind]['sha256'] != nodes[1][kind]['sha256'],
                'fixture must preserve local IDs while changing content')
    delta = cli(baseline_nex, original, 'changes')
    namespace = delta['namespace']
    baseline_rows = row_digest(original)
    captured = cli(baseline_nex, original, 'snapshot', '--directory', archive)
    require(captured['source_unchanged'] and captured['head'] == head and
            captured['namespace'] == namespace and row_digest(original) == baseline_rows,
            'snapshot changed the baseline or captured the wrong graph')
    def archive_hashes():
        return {p.name: digest(p.read_bytes()) for p in archive.iterdir() if p.is_file()}
    archive_before = archive_hashes()
    manifest = json.loads((archive / 'snapshot.json').read_bytes())
    require(archive_before['graph.db'] == captured['database_sha256'] == manifest['database']['sha256'],
            'snapshot does not match the recorded database')
    restored = cli(candidate_nex, work, 'recover', archive, '--directory', recovered)
    require(restored['materialized'] is False and restored['head'] == head and restored['namespace'] == namespace
            and restored['database_sha256'] == archive_before['graph.db'] and row_digest(recovered) == baseline_rows,
            'candidate changed the recovered graph')
    require(cli(candidate_nex, recovered, 'history') == history and cli(candidate_nex, recovered, 'changes') == delta,
            'candidate changed revision history or journal')
    evidence = []
    for index, revision in enumerate(revisions, 1):
        expected = f'{40+index}\n'
        require(identities(candidate_nex, recovered, revision) == nodes[index-1], 'stored identities changed')
        args = ('--revision', revision)
        require(cli(candidate_nex, recovered, 'check', *args)['revision'] == revision,
                'candidate checked a different revision')
        run = cli(candidate_nex, recovered, 'run', *args)
        require(run['exit_code'] == 0 and run['stdout'] == expected and
                cli(candidate_nex, recovered, 'eval', *args)['stdout'] == expected, 'archived execution disagrees')
        physical = work / f'export-{index}'
        exported = cli(candidate_nex, recovered, 'export', *args, '--directory', physical)
        require(exported['revision'] == revision and json.loads((physical/'nex.json').read_bytes())['language'] == '0.30'
                and (physical/'main.nex').read_bytes() == MAIN.encode()
                and (physical/'score.nex').read_bytes() == SCORE.replace('INCREMENT', str(index)).encode(),
                'exported source differs from baseline')
        require(cli(candidate_nex, physical, 'check')['revision'] == revision and
                cli(candidate_nex, physical, 'eval')['stdout'] == expected, 'physical export disagrees')
        evidence.append({'revision': revision, 'language': '0.30', 'stdout': expected,
                         'identities': nodes[index-1], 'archived_check': True, 'native': True,
                         'reference': True, 'physical_export_checked_and_evaluated': True})
    require(archive_hashes() == archive_before and row_digest(original) == row_digest(recovered) == baseline_rows
            and not any(p.is_file() for p in recovered.glob('*.nex')), 'replay or export mutated graph history, snapshot or source projection')
    return {'schema': 'nex.sdk-snapshot-compatibility/1', 'ok': True, 'head': head, 'namespace': namespace,
            'snapshot_database_sha256': archive_before['graph.db'], 'snapshot_manifest_sha256': archive_before['snapshot.json'],
            'baseline_rows_sha256': baseline_rows, 'history_sha256': object_digest(history),
            'change_journal_sha256': object_digest(delta), 'revisions': evidence}
