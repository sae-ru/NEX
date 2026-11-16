"""Ordinary030 project, graph, migration, task replay and static component flows."""
from pathlib import Path
import argparse
import collections
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler', type=Path)
p.add_argument('--output', type=Path)
p.add_argument('--origin-compiler', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
nex = a.compiler.resolve()
origin = (a.origin_compiler or nex).resolve()
base = (a.output or Path(tempfile.mkdtemp(prefix='nex-030-cli-'))).resolve()
base.mkdir(parents=True, exist_ok=True)
out = Path(tempfile.mkdtemp(prefix='run-', dir=base))
report = {'schema': 'nex.references030-cli-acceptance/1', 'ok': False,
          'compiler_sha256': hashlib.sha256(nex.read_bytes()).hexdigest(),
          'origin_compiler_sha256': hashlib.sha256(origin.read_bytes()).hexdigest(),
          'commands': [], 'gates': []}


def save():
    data=json.dumps(report, ensure_ascii=False, indent=2)+'\n'
    (out/'report.json').write_text(data, encoding='utf-8')
    (base/'report.json').write_text(data, encoding='utf-8')


def run(project, *args, ok=True, compiler=nex):
    result = subprocess.run([str(compiler), *map(str, args), '--json'], cwd=project,
                            capture_output=True, text=True, encoding='utf-8', timeout=300)
    label = str(len(report['commands'])).zfill(3)+'-'+str(args[0])
    (out/(label+'.stdout')).write_text(result.stdout, encoding='utf-8')
    (out/(label+'.stderr')).write_text(result.stderr, encoding='utf-8')
    assert (result.returncode == 0) == ok, (args, result.returncode, result.stdout[-3000:], result.stderr[-3000:])
    value = json.loads(result.stdout)
    report['commands'].append({'args': list(map(str, args)), 'exit': result.returncode,
                               'stdout_sha256': hashlib.sha256(result.stdout.encode()).hexdigest()})
    save()
    return value


def snapshot(project):
    path=project/'.nex/graph.db'
    assert path.is_file()
    with sqlite3.connect(str(path)) as db:
        db.execute('PRAGMA query_only=ON')
        schema = tuple(db.execute('SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name'))
        rows = {name: collections.Counter(tuple(row) for row in db.execute('SELECT * FROM "'+name+'"'))
                for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    return schema, rows


project = out/'project 🧠'
run(out, 'init', project)
manifest = json.loads((project/'nex.json').read_text())
assert manifest['language'] == '0.30'
source = (root/'examples/references/main.nex').read_text()
entry = project/manifest['entry']
entry.write_text(source)
first = run(project, 'check')['revision']
graph = run(project, 'graph')
assert graph['language'] == '0.30' and graph['revision'] == first
assert run(project, 'context', '--symbol', 'answer')['language'] == '0.30'
assert run(project, 'context', '--entity', 'type', '--symbol', 'Counter')['language'] == '0.30'
analysis = run(project, 'analyze', entry, '--details')
assert analysis['language'] == '0.30'
typed = [item for item in analysis['identifiers'] if item.get('detail') == 'type constructor cell<_>']
assert typed and any(item.get('detail', '').startswith('builtin cell_new;') for item in analysis['identifiers'] if item.get('detail'))
run(project, 'operations', '--symbol', 'answer')
assert run(project, 'eval')['stdout'] == '42\n'
for profile in ['debug', 'release']:
    executed = run(project, 'run', '--profile', profile)
    assert executed['stdout'] == '42\n' and executed['exit_code'] == 0
assert run(project, 'test')['ok'] and run(project, 'test', '--target', 'web')['ok']
before = snapshot(project)
formatted = run(project, 'fmt', entry)
assert formatted['language'] == '0.30' and snapshot(project) == before
run(project, 'fmt', entry, '--write')
assert snapshot(project) == before
first = run(project, 'check')['revision']
run(project, 'lock')
assert json.loads((project/'nex.lock.json').read_text())['language'] == '0.30'
run(project, 'emit', '--kind', 'typescript', '--directory', out/'module')
mapping = json.loads((out/'module/nex-map.json').read_text())
assert mapping['language'] == '0.30' and mapping['ordinary_CLI'] and mapping['public_source_enabled']

patch = out/'patch.json'
patch.write_text(json.dumps({'expected_revision': first, 'replacements': [{'name': 'answer',
    'source': 'fn answer()->i64!{state,throw}{return cell_read(cell_new(43));}'}]}))
changed = run(project, 'apply', '--patch', patch)['revision']
assert run(project, 'eval', '--revision', 'HEAD')['stdout'] == '43\n'
run(project, 'restore', '--revision', first, '--expected-revision', changed)
assert run(project, 'eval', '--revision', 'HEAD')['stdout'] == '42\n'
exported = out/'exported'
run(project, 'export', '--directory', exported)
assert json.loads((exported/'nex.json').read_text())['language'] == '0.30'
assert json.loads((exported/'nex.lock.json').read_text())['language'] == '0.30'
assert run(exported, 'check')['revision'] == first
graph = run(project, 'graph')
graph_file = out/'graph.json'
graph_file.write_text(json.dumps(graph))
imported = out/'imported'
imported.mkdir()
(imported/'nex.json').write_text(json.dumps(manifest))
run(imported, 'import', graph_file)
assert run(imported, 'eval', '--revision', 'HEAD')['stdout'] == '42\n'
report['graph_namespace'] = graph['identity_namespace']

run(project, 'task', entry, '--kind', 'init', '-o', project/'task.json')
task_document = json.loads((project/'task.json').read_text())
task_document['checks'].append({'id': 'cell-effects', 'kind': 'effects', 'program': 'app',
    'target': 'source', 'symbols': ['references::answer'], 'allowed_effects': ['state', 'throw']})
task_document['requirements'].append({'id': 'cell-effects', 'text': 'The checked answer declares state and throw',
    'targets': ['source'], 'checks': ['cell-effects'],
    'bindings': [{'kind': 'function', 'program': 'app', 'symbol': 'references::answer'}]})
(project/'task.json').write_text(json.dumps(task_document))
checked_task = run(project, 'task', 'task.json', '--kind', 'check', '--revision', first)
task = run(project, 'task', 'task.json', '--kind', 'run', '--revision', first,
           '--task-hash', checked_task['task_hash'], '--directory', out/'task-run')
assert task['ok']
assert any(check['id'] == 'cell-effects' and check['status'] == 'passed' and not check['violations']
           for check in task['checks'])
languages = json.loads((out/'task-run/inputs/program-languages.json').read_text())
assert languages == {'schema': 'nex.task-program-languages/1', 'programs': {'app': '0.30'}}
entry.rename(entry.with_suffix('.retained'))
try:
    replayed = run(out, 'task', out/'task-run/receipt.json', '--kind', 'replay', '--directory', out/'task-replay')
    assert replayed['ok']
finally:
    entry.with_suffix('.retained').rename(entry)
report['source_deleted_task_replay'] = True

# The ordinary component driver must carry reference signatures into a code-only
# archive and keep all calls in the consuming application's one context.
components = out/'components'
components.mkdir()
(components/'core').mkdir(); (components/'app').mkdir()
(components/'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.30', 'entry': 'app/main.nex'}))
(components/'core/value.nex').write_text('module core;pub fn make()->cell<i64>!{state}{return cell_new(41);}pub fn read(v:cell<i64>)->i64!{state}{return cell_read(v);}pub fn write(v:cell<i64>)->unit!{state}{cell_write(v,42);}')
(components/'app/main.nex').write_text('module app;import "../core/value.nex" as c;fn main()->unit!{state,io}{let v:cell<i64>=c::make();c::write(v);print(c::read(v));}')
(components/'nex.build.json').write_text(json.dumps({'schema': 'nex.project-build/1', 'default_configuration': 'debug',
    'configurations': {'debug': {'profile': 'debug'}, 'release': {'profile': 'release'}}, 'components': {
        'core': {'kind': 'static_library', 'root': 'core', 'entry': 'core/value.nex', 'entry_function': 'make', 'exports': ['read', 'write']},
        'app': {'kind': 'executable', 'root': 'app', 'entry': 'app/main.nex', 'dependencies': {'core': 'static'}}}}))
for profile in ['debug', 'release']:
    built = run(components, 'project', '--kind', 'run', '--component', 'app', '--configuration', profile)
    assert built['observation']['exit_code'] == 0 and built['observation']['stdout'] == '42\n'
report['static_components'] = True

# API source projection must select030 for both generated projects and exclude
# server-only source from an emitted client module.
api = out/'api'
api.mkdir()
(api/'nex.json').write_text('{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}')
(api/'main.nex').write_text('''module api_example;
import "std/api.nex" as api;
pub struct Input{value:i64;}pub struct Output{value:i64;}
fn identity<F<_>,T>(v:F<T>)->F<T>{return v;}
server fn double(ctx:api::Context,input:Input)->result<Output>!{state}{let c:cell<Input>=identity<cell,Input>(cell_new(input));cell_write(c,Input(cell_read(c).value*2));return ok(Output(cell_read(c).value));}
server fn marker()->str{return "server-only-marker";}
endpoint double_value("POST","/api/double")=double;
fn main()->unit{}
''')
generated = run(api, 'api', '--directory', api/'generated')
assert generated['language'] == '0.30'
for side in ['server', 'client']:
    selected = api/'generated'/side
    assert json.loads((selected/'nex.json').read_text())['language'] == '0.30'
    run(selected, 'check')
run(api/'generated/client', 'emit', '--kind', 'typescript', '--entry', 'request_double_value', '--directory', api/'typescript')
assert 'server-only-marker' not in (api/'typescript/program.ts').read_text()+(api/'typescript/nex-map.json').read_text()
report['api_projection'] = True

for conflict in [False, True]:
    folder = out/('collision' if conflict else 'migration')
    folder.mkdir()
    old_manifest = {'schema': 'nex.project/1', 'language': '0.29', 'entry': 'main.nex'}
    (folder/'nex.json').write_text(json.dumps(old_manifest))
    original = 'module origin;'+('struct cell<T>{value:T;}' if conflict else '')+'fn main()->unit!{io}{print(42);}'
    (folder/'main.nex').write_text(original)
    head = run(folder, 'check', compiler=origin)['revision']
    before = snapshot(folder)
    plan = run(folder, 'migrate', '--language-version', '0.30', '--kind', 'plan')
    assert plan['origin_verified'] and plan['target_language'] == '0.30' and snapshot(folder) == before
    assert plan['target_valid'] != conflict
    args = []
    if conflict:
        candidate = plan['candidate']
        candidate['sources']['files']['main.nex'] = original.replace('struct cell<T>', 'struct LegacyCell<T>')
        candidate_file = folder/'candidate.json'
        candidate_file.write_text(json.dumps(candidate))
        args = ['--candidate', candidate_file]
    applied = run(folder, 'migrate', '--language-version', '0.30', '--expected-revision', head, *args)
    assert applied['language'] == '0.30' and applied['identity_namespace'] == plan['identity_namespace']
    after = snapshot(folder)
    assert after[0] == before[0]
    for table, rows in before[1].items():
        # HEAD is the only overwritten graph metadata; immutable rows/local IDs
        # remain present. Migration appends its revision and change record.
        if table != 'head':
            assert not (rows-after[1][table]), (table, rows-after[1][table])
    bad = run(folder, 'check', ok=False)
    assert bad['code'] == 'E_LANGUAGE_VERSION' and snapshot(folder) == after
    (folder/'nex.json').write_text(json.dumps({**old_manifest, 'language': '0.30'}))
    assert run(folder, 'eval', '--revision', 'HEAD')['stdout'] == '42\n'
    target = folder/'materialized'
    run(folder, 'export', '--directory', target)
    assert run(target, 'check')['revision'] == applied['revision']
    report['gates'].append({'migration_collision': conflict, 'old_rows_preserved': True, 'namespace_preserved': True})

report['ok'] = True
save()
print(json.dumps({'ok': True, 'commands': len(report['commands']), 'report': str(out/'report.json')}))
