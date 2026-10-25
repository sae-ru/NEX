"""Current compiled whole-file reads agree with the independent AST scheduler."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('nex')
parser.add_argument('--output', type=Path)
args = parser.parse_args()
nex = str(Path(args.nex).resolve())
receipts = []

cases = [
    ('text-bytes', '''server fn file_helper()->i64{return 42;}
server fn read(path:str)->result<str> !{task,fs}{task_yield();return file_read_text(path);}
server fn main()->i64 !{task,fs}{assert(len(unwrap(read("text")))==4);let data:bytes=unwrap(file_read_bytes("data"));assert(len(data)==3);return file_helper();}''', '', True),
    ('scope-indirect', '''server fn read(path:str)->result<str> !{task,fs}{task_yield();return file_read_text(path);}
server fn keep(f:server fn(str)->result<str> !{task,fs})->(server fn(str)->result<str> !{task,fs}){return f;}
server fn main()->i64 !{task,fs}{let f:server fn(str)->result<str> !{task,fs}=keep(read);return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{let first:task<result<str>>=task_spawn(s,server fn()->result<str> !{task,fs}{return f("text");});let second:task<result<str>>=task_spawn(s,server fn()->result<str> !{task,fs}{return f("text");});assert(task_wait(first)==task_wait(second));return 42;});}''', '', True),
    ('generic-record-callable', '''struct Reader<T>{run:server fn(T)->result<str> !{task,fs};}
server fn identity<T>(value:T)->T{return value;}
server fn invoke<T>(f:server fn(T)->result<str> !{task,fs},value:T)->result<str> !{task,fs}{return f(value);}
server fn read(path:str)->result<str> !{task,fs}{task_yield();return file_read_text(path);}
server fn main()->i64 !{task,fs}{let reader:Reader<str>=Reader(identity(read));return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{let t:task<result<str>>=task_spawn(s,server fn()->result<str> !{task,fs}{return invoke(reader.run,"text");});assert(len(unwrap(task_wait(t)))==4);return 42;});}''', '', True),
    ('order-short-circuit', '''server fn path(n:i64)->str !{task,io}{print(n);task_yield();return "data";}
server fn main()->i64 !{task,fs,io}{let first:bytes=unwrap(file_read_bytes(path(1)));let second:bytes=unwrap(file_read_bytes(path(2)));assert(first==second);assert(true||is_ok(file_read_text("missing")));assert(!(false&&is_ok(file_read_text("missing"))));return 42;}''', '1\n2\n', True),
    ('propagate-abort', '''server fn work()->result<i64> !{task,fs}{return with_tasks(1,server fn(s:task_scope)->result<i64> !{task,fs}{let other:task<result<bytes>>=task_spawn(s,server fn()->result<bytes> !{task,fs}{return file_read_bytes("data");});let absent:str=file_read_text("missing")?;task_wait(other);return ok(len(absent));});}
server fn main()->i64 !{task,fs}{let failure:result<i64>=work();assert(error_code(failure)=="NOT_FOUND");return 42;}''', '', True),
    ('ordinary-errors', '''server fn main()->i64 !{task,fs}{assert(error_code(file_read_text("data"))=="E_UTF8");assert(error_code(file_read_text("missing"))=="NOT_FOUND");assert(error_code(file_read_bytes("../escape"))=="VALIDATION");assert(error_code(file_read_text("large"))=="LIMIT");assert(len(unwrap(file_read_bytes("maximum")))==1048576);return 42;}''', '', True),
    ('unavailable-grant', '''server fn main()->i64 !{task,fs}{assert(error_code(file_read_text("text"))=="CAPABILITY");return 42;}''', '', False),
    ('skipped-unavailable', '''server fn main()->i64 !{task,fs}{if false{file_read_text("text");}return 42;}''', '', False),
    ('sync-fs', '''server fn main()->i64 !{fs}{assert(len(unwrap(file_read_bytes("data")))==3);return 42;}''', '', True),
]


def run(root, command, env, expected=0):
    completed = subprocess.run(list(map(str, command)), cwd=root, env=env, capture_output=True, text=True, timeout=240)
    receipt = dict(command=list(map(str, command)), exit=completed.returncode, stdout=completed.stdout, stderr=completed.stderr)
    receipts.append(receipt)
    if args.output:
        (args.output / 'commands.json').write_text(json.dumps(receipts, ensure_ascii=False, indent=2) + '\n')
    assert completed.returncode == expected, receipt
    return completed


def cli(root, env, *arguments, success=True):
    result = run(root, [nex, *arguments, '--json'], env, 0 if success else 1)
    return json.loads(result.stdout)


if args.output:
    args.output.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix='nex native task file reads 🧠 ') as directory:
    root = Path(directory)
    files = root / 'grant'
    files.mkdir()
    (files / 'text').write_bytes('A🧠\0B'.encode())
    (files / 'data').write_bytes(b'A\0\xff')
    (files / 'maximum').write_bytes(b'x' * 1048576)
    (files / 'large').write_bytes(b'x' * 1048577)
    configured = {**os.environ, 'NEX_FILES_ROOT': str(files)}
    configured.pop('NEX_RESOURCE_DIR', None)
    configured.pop('NEX_FILES_WRITE', None)
    absent = {key: value for key, value in configured.items() if key != 'NEX_FILES_ROOT'}
    for name, body, stdout, grant in cases:
        source = root / (name + '.nex')
        source.write_text('module native_reads;\n' + body + '\n')
        env = configured if grant else absent
        actual = cli(root, env, 'eval', source)
        assert actual['value'] == 42 and actual['stdout'] == stdout, (name, actual)
        for profile in (('debug', 'release') if name in ('text-bytes', 'scope-indirect') else ('debug',)):
            built = cli(root, env, 'build', source, '--profile', profile)
            folder = Path(built['executable']).parent
            metadata = json.loads((folder / 'build.json').read_text())
            tasks = name != 'sync-fs'
            assert metadata['runtime_requirements']['tasks'] is tasks, metadata
            assert metadata['runtime_requirements']['task_file_reads'] is tasks, metadata
            assert metadata['runtime_components'].count('nex_files.cpp') == 1, metadata
            if tasks:
                assert 'nex_task_file_read.h' in metadata['runtime_inputs'], metadata
                assert '__task_step' in Path(built['llvm']).read_text()
            standalone = root / (name + '-' + profile)
            shutil.copy2(built['executable'], standalone)
            source.rename(source.with_suffix('.hidden'))
            try:
                detached = {'PATH': '/usr/bin:/bin'}
                if grant:
                    detached['NEX_FILES_ROOT'] = str(files)
                observed = run('/', [standalone], detached, 42)
                assert observed.stdout == stdout and not observed.stderr, (name, observed)
            finally:
                source.with_suffix('.hidden').rename(source)
    boundary = root / 'unsupported.nex'
    boundary.write_text('module boundary;server fn main()->i64 !{task,fs}{assert(error_code(file_write_text("created","forbidden"))=="CAPABILITY");return 42;}')
    readonly = {**configured, 'NEX_FILES_WRITE':'0'}
    built = cli(root, readonly, 'build', boundary)
    assert cli(root, readonly, 'eval', boundary)['value'] == 42
    run(root, [built['executable']], readonly, 42)
    assert not (files / 'created').exists()
    boundary.write_text('module boundary;server fn main()->i64 !{task,fs}{assert(unwrap(file_write_text("created","complete")));assert(unwrap(file_read_text("created"))=="complete");return 42;}')
    writable = {**configured, 'NEX_FILES_WRITE':'1'}
    built = cli(root, writable, 'build', boundary)
    assert cli(root, writable, 'eval', boundary)['value'] == 42
    run(root, [built['executable']], writable, 42)
    assert (files / 'created').read_text() == 'complete'
    for body in [
        'server fn read()->result<str> !{fs}{return file_read_text("text");}server fn main()->i64 !{task,fs}{return len(unwrap(read()));}',
        'server fn main()->i64 !{task,fs}{let f:server fn()->result<str> !{fs}=server fn()->result<str> !{fs}{return file_read_text("text");};return len(unwrap(f()));}',
    ]:
        boundary.write_text('module boundary;' + body)
        assert cli(root, configured, 'check', boundary, success=False)['code'] == 'E_EFFECT'
    boundary.write_text('module boundary;server fn main()->i64 !{task,fs}{return len(unwrap(file_read_text("text")));}')
    for options, code in [(['--library'], 'E_TASK_PROVIDER'), (['--target', 'server', '--entry', 'main'], 'E_HTTP_SIGNATURE')]:
        assert cli(root, configured, 'build', boundary, *options, success=False)['code'] == code
    profiled = cli(root, configured, 'build', boundary, '--profile', 'profile')
    raw_path = root/'file-read-profile.json'
    observation = run('/', [profiled['executable']], {**configured,
        'NEX_PROFILE_OUTPUT':str(raw_path), 'NEX_PROFILE_EVENTS':'0', 'NEX_TRACY':'0'}, 4)
    assert not observation.stdout and not observation.stderr, observation
    measured = json.loads(raw_path.read_text())
    assert measured['schema'] == 'nex.profile-runtime/2', measured
    assert measured['completeness']['aggregates'] and measured['completeness']['memory'], measured
    assert all(pool['live'] == 0 and pool['allocations'] == pool['frees'] for pool in measured['memory']), measured
    assert cli(root, configured, 'emit', boundary, '--kind', 'typescript', success=False)['code'] == 'E_REALM'
    checked_test = root / 'checked-test.nex'
    checked_test.write_text('module checked_test;server test fn read_ok()->unit !{task,fs}{assert(len(unwrap(file_read_bytes("data")))==3);}')
    tested = cli(root, configured, 'test', checked_test)
    assert tested['ok'] is True, tested
    project = root / 'source-project'
    (project / 'core').mkdir(parents=True)
    (project / 'app').mkdir()
    (project / 'nex.json').write_text(json.dumps(dict(schema='nex.project/1', language='0.24', entry='app/main.nex')))
    (project / 'nex.build.json').write_text(json.dumps({
        'schema': 'nex.project-build/1', 'default_configuration': 'debug',
        'configurations': {'debug': {'profile': 'debug', 'target': 'native'}},
        'components': {
            'core': {'kind': 'source', 'root': 'core', 'entry': 'core/read.nex'},
            'app': {'kind': 'executable', 'root': 'app', 'entry': 'app/main.nex', 'dependencies': {'core': 'source'}},
        },
    }))
    (project / 'core/read.nex').write_text('module core;pub server fn read()->i64 !{task,fs}{return len(unwrap(file_read_bytes("data")));}')
    (project / 'app/main.nex').write_text('module app;import "../core/read.nex" as core;server fn main()->unit !{task,fs,io}{assert(core::read()==3);print(42);}')
    built_project = cli(project, configured, 'project', '--kind', 'build', '--component', 'app')
    artifact = next(item for item in built_project['artifacts'] if item['component'] == 'app')
    metadata = json.loads(Path(artifact['metadata']).read_text())
    assert metadata['runtime_requirements']['task_file_reads'] is True, metadata
    standalone = run('/', [artifact['artifact']], {'PATH': '/usr/bin:/bin', 'NEX_FILES_ROOT': str(files)})
    assert standalone.stdout == '42\n' and not standalone.stderr, standalone
    observed = cli(project, configured, 'project', '--kind', 'run', '--component', 'app')
    assert observed['observation']['stdout'] == '42\n' and observed['observation']['exit_code'] == 0, observed
    print(json.dumps(dict(ok=True, cases=len(cases), commands=len(receipts), native_reference_agreement=True, standalone_without_compiler=True, source_component_project=True)))
