"""Ordinary030 reference ownership across actual static/shared/mixed images."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler', type=Path)
p.add_argument('--output', type=Path)
p.add_argument('--output-parent', type=Path)
a = p.parse_args()
compiler = a.compiler.resolve()
source = Path(__file__).resolve().parents[1]/'examples/reference-task-providers'
out = a.output or Path(tempfile.mkdtemp(prefix='nex-reference-providers-', dir=a.output_parent))
out = out.resolve()
out.mkdir(parents=True, exist_ok=True)
assert not (out/'commands.json').exists(), 'use a fresh output directory'
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
commands = []
env = dict(os.environ)
for key in ('NEX_RESOURCE_DIR', 'NEX_FILES_ROOT', 'NEX_FILES_WRITE', 'NEX_PROFILE_OUTPUT', 'NEX_TRACY'):
    env.pop(key, None)


def run(argv, cwd, *, expected=0, timeout=300):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env, capture_output=True,
                            text=True, encoding='utf-8', timeout=timeout)
    row = {'command': list(map(str, argv)), 'cwd': str(cwd), 'exit_code': result.returncode,
           'stdout': result.stdout, 'stderr': result.stderr}
    commands.append(row)
    (out/'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2)+'\n')
    assert result.returncode == expected, {'command': row['command'], 'exit_code': result.returncode,
                                           'expected': expected, 'stdout_tail': result.stdout[-1200:],
                                           'stderr_tail': result.stderr[-1200:]}
    return result


def cli(root, *args, expected=0, timeout=300):
    args = list(args)
    args.insert(args.index('--') if '--' in args else len(args), '--json')
    return json.loads(run([compiler, *args], root, expected=expected, timeout=timeout).stdout)


def fixture(name, mode):
    root = out/name
    shutil.copytree(source, root)
    data = json.loads((root/'nex.build.json').read_text())
    for name, component in data['components'].items():
        if name != 'app':
            component['kind'] = ('shared_library' if mode == 'shared' or
                                 (mode == 'mixed' and name == 'leaf') else 'static_library')
    for component in data['components'].values():
        for dependency in component.get('dependencies', {}):
            component['dependencies'][dependency] = ('dynamic' if data['components'][dependency]['kind'] == 'shared_library' else 'static')
    (root/'nex.build.json').write_text(json.dumps(data, indent=2)+'\n')
    return root


def project(root, kind, profile='debug', *args, expected=0):
    return cli(root, 'project', '--kind', kind, '--component', 'app',
               '--configuration', profile, *args, expected=expected)


rows = []
for mode in ['static', 'shared', 'mixed']:
    root = fixture(mode, mode)
    reference = cli(root, 'eval', 'app/main.nex', '--limit', '1000000')
    assert reference['ok'] and reference['stdout'] == '42\n'
    for profile in ['debug', 'release']:
        plan = project(root, 'plan', profile)
        expected_schema = ('nex.project-static-task-linkage/6' if mode == 'static' else 'nex.project-task-linkage/17')
        assert all(c['task_linkage']['execution_abi'] == 8 for c in plan['components'])
        assert all(c['task_linkage']['schema'] == expected_schema for c in plan['components'])
        assert all(i['calling_mode'] == 'task-code/8' for c in plan['components'] for i in c['task_linkage']['imports'])
        observed = project(root, 'run', profile)
        assert observed['ok'] and not observed['graph_store_opened']
        actual = observed['observation']
        assert actual['stdout'] == reference['stdout'] and actual['stderr'] == '' and actual['exit_code'] == 0
        assert actual['task_execution']['executor_workers'] == 1
        records = {}
        for artifact in observed['artifacts']:
            folder = Path(artifact['artifact']).parent
            record = json.loads((folder/'task-provider.json').read_text())
            assert record['schema'] == 'nex.native-task-provider/17'
            assert record['descriptor_abi'] == int('4e45585400000008', 16)
            assert record['descriptor_size'] == 88 and record['abi_offset'] == 40
            records[artifact['component']] = {'artifact_sha256': sha(artifact['artifact']), 'record': record}
        # A reference-free provider must participate in the owner's ABI8 cohort.
        assert 'provider_pure::next' in records['pure']['record']['definitions']
        assert all('provider_leaf::bump' not in records[c]['record']['definitions'] for c in ['mid','app'])
        warm = project(root, 'build', profile)
        assert all(artifact['cached'] for artifact in warm['artifacts'])
        rows.append({'mode': mode, 'profile': profile, 'reference': reference,
                     'observation': actual, 'records': records, 'warm_reused': True})
    tested = project(root, 'test')
    assert tested['ok']
    # Both controls fire after constructing a live cell and repeatedly
    # suspending inside library continuations, rather than before entry.
    controlled = fixture(mode+'-controls', mode)
    configuration = json.loads((controlled/'nex.build.json').read_text())
    configuration['configurations']['debug']['task_limits']['steps'] = 9007199254740991
    (controlled/'nex.build.json').write_text(json.dumps(configuration)+'\n')
    (controlled/'app/main.nex').write_text(
        'module provider_app;import "../leaf/value.nex" as leaf;import "../mid/value.nex" as mid;'
        'fn main()->unit!{task,state}{let value:cell<i64>=leaf::make(0);while true{mid::twice(value);}}')
    for code, arguments in [('E_LIMIT', ['--nex-task-steps', '1000']),
                             ('E_TIMEOUT', ['--nex-task-timeout-ms', '25'])]:
        limited = project(controlled, 'run', 'debug', '--', *arguments, expected=70)
        diagnostics = limited['observation']['native_diagnostics']['diagnostics']
        assert not limited['ok'] and len(diagnostics) == 1
        assert diagnostics[0]['status'] == 'mapped' and diagnostics[0]['report']['code'] == code

# Ordinary capture/replay checks the explicit new ABI, source ownership and schemas.
root = out/'mixed'
task = cli(root, 'task', 'nex.build.json', '--kind', 'init', '--component', 'app', '--configuration', 'debug')
task['checks'].append({'id': 'reference-provider-run', 'kind': 'run', 'program': 'app', 'target': 'native',
                       'configuration': 'debug', 'expect': {'stdout': '42\n', 'exit_code': 0}, 'timeout_seconds': 120})
task['requirements'].append({'id': 'reference-provider-run', 'text': 'Preserve cell identity across separately owned providers',
                             'bindings': [{'program': 'app', 'kind': 'function', 'symbol': 'provider_app::main'}],
                             'targets': ['native'], 'checks': ['reference-provider-run']})
(root/'task.json').write_text(json.dumps(task)+'\n')
captured = cli(root, 'task', 'task.json', '--kind', 'run', '--directory', out/'capture', timeout=900)
assert captured['ok']
receipt = Path(captured['output'])
capture = json.loads((receipt.parent/'inputs/projects/app.json').read_text())
assert 'task-code/8' in json.dumps(capture)
for name in ['leaf', 'mid', 'pure', 'app', '.nex']:
    shutil.rmtree(root/name)
for name in ['nex.json', 'nex.build.json', 'task.json']:
    (root/name).unlink()
replayed = cli(out, 'task', receipt, '--kind', 'replay', '--directory', out/'replay', timeout=900)
assert replayed['ok'] and replayed['programs'] == captured['programs']

rejections = []
for name, mutate, code in [
    ('profile', lambda r: None, 'E_CELL_TARGET'),
    ('debugger', lambda r: None, 'E_CELL_TARGET'),
    ('imported-callable', lambda r: (r/'app/main.nex').write_text(
        'module provider_app;import "../leaf/value.nex" as leaf;'
        'fn main()->unit!{task,state}{let value:cell<i64>=leaf::make(1);'
        'let callback:fn(cell<i64>)->cell<i64>!{task,state}=leaf::bump;callback(value);}'), 'E_TASK_PROVIDER'),
]:
    root = fixture('reject-'+name, 'static')
    if name == 'profile':
        data = json.loads((root/'nex.build.json').read_text());data['configurations']['debug']['profile'] = 'profile'
        (root/'nex.build.json').write_text(json.dumps(data)+'\n')
    mutate(root)
    extra = ['--task-debug'] if name == 'debugger' else []
    denied = project(root, 'plan', 'debug', *extra, expected=1)
    assert denied['code'] == code, denied
    rejections.append({'name': name, 'code': code})

report = {'schema': 'nex.reference-task-providers/1', 'ok': True,
          'compiler_sha256': sha(compiler), 'harness_sha256': sha(__file__),
          'example_sha256': {f.relative_to(source).as_posix(): sha(f) for f in source.rglob('*') if f.is_file()},
          'rows': rows, 'capture_replay_without_original_source': True, 'rejections': rejections,
          'command_count': len(commands), 'portable_SDK': False, 'whole_goal_complete': False}
(out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'ok': True, 'native_mode_profiles': len(rows), 'capture_replay': True, 'commands': len(commands)}))
