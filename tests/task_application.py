"""Standalone public019 executables use compiled continuations and owned tasks."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

nex = str(Path(sys.argv[1]).resolve())
cases = [
    ('yield', 'fn main()->i64 !{task,io}{print(7);task_yield();return 42;}', 42, '7\n', None),
    ('negative-exit', 'fn main()->i64 !{task}{task_yield();return -1;}', 255, '', None),
    ('unit', 'fn main()->unit !{task}{task_yield();}', 0, '', None),
    ('unused-ffi', 'server fn main()->i64 !{task,ffi,throw}{return with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,throw}{let child:task<i64>=task_spawn(s,server fn()->i64 !{task,ffi}{task_yield();return 42;});return task_wait(child);});}', 42, '', None),
    ('calls', 'fn item(n:i64)->i64 !{task,io}{print(n);task_yield();return n;}fn sum(a:i64,b:i64)->i64 !{task}{task_yield();return a+b;}fn main()->i64 !{task,io}{return sum(item(20),item(22));}', 42, '20\n22\n', None),
    ('short', 'fn bad()->bool !{task,io}{print(99);task_yield();return true;}fn main()->i64 !{task}{if true||false{return 42;}return 0;}', 42, '', None),
    ('short-call', 'fn bad()->bool !{task,io}{print(99);task_yield();return true;}fn main()->i64 !{task,io}{let value:bool=(true||bad())&&(false&&bad());assert(!value);return 42;}', 42, '', None),
    ('snapshot', 'fn main()->i64 !{task}{var base:i64=40;let f:fn(i64)->i64 !{task}=fn(n:i64)->i64 !{task}{task_yield();return base+n;};base=99;return f(2);}', 42, '', None),
    ('heap-return', 'fn text()->list<str> !{task}{let value:list<str>=["A🧠\\u0000"];task_yield();return value;}fn main()->i64 !{task,io}{print(text());return 42;}', 42, '["A🧠\\u0000"]\n', None),
    ('scope', 'fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let a:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 20;});let b:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 22;});return task_wait(a)+task_wait(b);});}', 42, '', None),
    ('internal-task-signatures', 'fn keep_scope(s:task_scope)->task_scope{return s;}fn keep_callback(f:fn()->i64 !{task})->(fn()->i64 !{task}){return f;}fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{assert(keep_scope(s)==s);let callback:fn()->i64 !{task}=keep_callback(fn()->i64 !{task}{task_yield();return 42;});return callback();});}', 42, '', None),
    ('channel', 'fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let q:channel<str>=channel_new<str>(s,0);let writer:task<unit>=task_spawn(s,fn()->unit !{task}{assert(task_send(q,"A🧠\\u0000"));assert(task_close(q));});let value:str=unwrap(task_recv(q));task_wait(writer);assert(!is_ok(task_recv(q)));assert(len(value)==3);return 42;});}', 42, '', None),
    ('cancel', 'fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,fn()->i64 !{task}{let held:list<str>=["retained🧠"];while true{task_yield();}return len(held);});task_yield();assert(task_cancel(t));return 42;});}', 42, '', None),
    ('propagate-cleanup', 'fn work()->result<i64> !{task,throw}{return with_tasks(1,fn(s:task_scope)->result<i64> !{task}{let t:task<str>=task_spawn(s,fn()->str !{task}{let held:str="retained🧠";while true{task_yield();}return held;});task_yield();let bad:result<str>=err<str>("E_STOP","stop");let value:str=bad?;return ok(len(value));});}fn main()->i64 !{task,throw}{return unwrap(work());}', 70, '', 'E_RESULT'),
    ('unobserved', 'fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 1/0;});return 42;});}', 70, '', 'E_DIV_ZERO'),
    ('overflow', 'fn main()->i64 !{task,io}{let held:list<str>=["retained🧠"];print(7);task_yield();let x:i64=9223372036854775807;return x+len(held);}', 70, '7\n', 'E_OVERFLOW'),
    ('owner', 'fn main()->i64 !{task}{let absent:task_scope=current_task_scope();return 42;}', 70, '', 'E_TASK_SCOPE'),
]

def cli(root, *args, success=True):
    p = subprocess.run([nex, *map(str, args), '--json'], cwd=root, capture_output=True, text=True, timeout=180)
    value = json.loads(p.stdout)
    assert (p.returncode == 0) == success, (args, p.returncode, value, p.stderr)
    return value

with tempfile.TemporaryDirectory(prefix='nex task application 🧠 ') as temporary:
    root = Path(temporary)
    (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.27','entry':'yield.nex'}))
    executable_root = root / 'standalone'
    executable_root.mkdir()
    results = []
    for name, body, status, stdout, trap in cases:
        source = root / (name + '.nex')
        source.write_text('module application;\n' + body + '\n')
        for profile in ('debug', 'release'):
            built = cli(root, 'build', source, '--profile', profile)
            metadata = json.loads((Path(built['executable']).parent / 'build.json').read_text())
            assert metadata['runtime_requirements']['tasks'] is True, metadata
            assert 'nex_task_application.cpp' in metadata['runtime_components'], metadata
            llvm = Path(built['llvm']).read_text()
            assert 'nex_task_application_execute' in llvm and '__task_step' in llvm, llvm[:1000]
            # The copied executable runs outside its project and source/cache,
            # with no compiler/resource-path environment or compiler on PATH.
            target = executable_root / (name + '-' + profile)
            shutil.copy2(built['executable'], target)
            hidden = source.with_suffix('.hidden')
            source.rename(hidden)
            try:
                actual = subprocess.run([str(target)], cwd='/', env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=15)
            finally:
                hidden.rename(source)
            assert (actual.returncode, actual.stdout) == (status, stdout), (name, profile, actual.returncode, actual.stdout, actual.stderr)
            if trap:
                assert actual.stderr.startswith(trap + ':'), (name, actual.stderr)
            else:
                assert not actual.stderr, (name, actual.stderr)
            warm = cli(root, 'build', source, '--profile', profile)
            assert warm['cached'] is True and warm['build_key'] == built['build_key'], (name, warm)
            results.append((name, profile))

    task = root / 'task.nex'
    task.write_text('module boundary;fn main()->unit !{task}{task_yield();}')
    profiled = cli(root, 'build', task, '--profile', 'profile')
    dormant = subprocess.run([profiled['executable']], cwd='/', env={'PATH': '/usr/bin:/bin'},
                             capture_output=True, text=True, timeout=15)
    assert (dormant.returncode, dormant.stdout, dormant.stderr) == (0, '', ''), dormant
    assert cli(root, 'build', task, '--library', success=False)['code'] == 'E_TASK_PROVIDER'
    pure = root / 'pure.nex'
    pure.write_text('module pure;fn unused()->unit !{task}{task_yield();}fn main()->i64{return 42;}')
    built = cli(root, 'build', pure)
    metadata = json.loads((Path(built['executable']).parent / 'build.json').read_text())
    assert metadata['runtime_requirements']['tasks'] is False, metadata
    assert 'nex_task_application.cpp' not in metadata['runtime_components'], metadata
    assert '__task_step' not in Path(built['llvm']).read_text()
    assert cli(root, 'build', pure, '--library')['executable'].endswith('libnex.a')
    boundary_types = [
        ('scope', '', 'task_scope'),
        ('future', '', 'task<i64>'),
        ('channel', '', 'channel<str>'),
        ('nested-container', '', 'result<list<task<i64>>>'),
        ('nominal', 'pub struct Box{scope:task_scope;}', 'Box'),
        ('function-result', '', '(fn()->task_scope)'),
        ('function-parameter', '', '(fn(task_scope)->i64)'),
        ('task-effect-callable', '', '(fn()->i64 !{task})'),
        ('nested-task-effect-callable', '', '(fn((fn()->i64 !{task}))->i64)'),
        ('nominal-task-effect-callable', 'pub struct Box{run:fn()->i64 !{task};}', 'result<list<Box>>'),
    ]
    for name, declaration, value_type in boundary_types:
        source = root / ('binary-boundary-' + name + '.nex')
        source.write_text('module boundary;' + declaration + 'pub fn identity(value:' + value_type + ')->' + value_type + '{return value;}fn main()->unit{}')
        rejected = cli(root, 'build', source, '--library', '--entry', 'identity', success=False)
        assert rejected['code'] == 'E_TASK_PROVIDER', (name, rejected)
        rejected = cli(root, 'emit', source, '--kind', 'mlir', '--library', '--entry', 'identity', success=False)
        assert rejected['code'] == 'E_TASK_PROVIDER', (name, rejected)
    # A clean primary entry does not make an additional public ABI export safe.
    exports = root / 'export-project'
    (exports / 'library').mkdir(parents=True)
    (exports / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.27', 'entry': 'library/main.nex'}))
    (exports / 'nex.build.json').write_text(json.dumps({
        'schema': 'nex.project-build/1', 'default_configuration': 'debug',
        'configurations': {'debug': {'profile': 'debug', 'target': 'native'}},
        'components': {'library': {'kind': 'static_library', 'root': 'library', 'entry': 'library/main.nex', 'entry_function': 'answer', 'exports': ['identity']}},
    }))
    (exports / 'library/main.nex').write_text('module exports;pub fn answer()->i64{return 42;}pub struct Box{run:fn()->i64 !{task};}pub fn identity(value:Box)->Box{return value;}')
    rejected = cli(exports, 'project', '--kind', 'build', '--component', 'library', success=False)
    assert rejected['code'] == 'E_TASK_PROVIDER', rejected
    project = root / 'source-project'
    (project / 'app').mkdir(parents=True)
    (project / 'core').mkdir()
    (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.27', 'entry': 'app/main.nex'}))
    (project / 'nex.build.json').write_text(json.dumps({
        'schema': 'nex.project-build/1', 'default_configuration': 'debug',
        'configurations': {'debug': {'profile': 'debug', 'target': 'native'}},
        'components': {
            'core': {'kind': 'source', 'root': 'core', 'entry': 'core/work.nex'},
            'app': {'kind': 'executable', 'root': 'app', 'entry': 'app/main.nex', 'dependencies': {'core': 'source'}},
        },
    }))
    (project / 'core/work.nex').write_text('module core;pub fn work()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let t:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 42;});return task_wait(t);});}')
    (project / 'app/main.nex').write_text('module app;import "../core/work.nex" as core;fn main()->unit !{task,io,throw}{print(core::work());}')
    planned = cli(project, 'project', '--kind', 'build', '--component', 'app')
    app = next(artifact for artifact in planned['artifacts'] if artifact['component'] == 'app')
    metadata = json.loads(Path(app['metadata']).read_text())
    assert metadata['runtime_requirements']['tasks'] is True, metadata
    actual = subprocess.run([app['artifact']], cwd='/', env={'PATH': '/usr/bin:/bin'}, capture_output=True, text=True, timeout=15)
    assert (actual.returncode, actual.stdout, actual.stderr) == (0, '42\n', ''), actual
    observed = cli(project, 'project', '--kind', 'run', '--component', 'app')
    assert observed['observation']['stdout'] == '42\n' and observed['observation']['exit_code'] == 0, observed
    print(json.dumps({'ok': True, 'standalone_profiles': len(results), 'cases': len(cases), 'compiled_continuations': True, 'source_hidden_execution': True, 'warm_cache': True, 'pure_reachability_preserved': True, 'source_component_project': True, 'binary_boundary_signature_cases': len(boundary_types), 'additional_library_export_rejected': True}))
