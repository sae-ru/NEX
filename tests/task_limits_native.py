"""Public task limits survive native compilation, caching and standalone use."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

nex = str(Path(sys.argv[1]).resolve())


def cli(root, *arguments, success=True):
    result = subprocess.run([nex, str(arguments[0]), '--json', *map(str, arguments[1:])], cwd=root,
                            capture_output=True, text=True, timeout=240)
    value = json.loads(result.stdout)
    assert (result.returncode == 0) == success, (arguments, result.returncode, value, result.stderr)
    return value


with tempfile.TemporaryDirectory(prefix='nex task limits 🧠 ') as temporary:
    root = Path(temporary)
    source = root / 'application.nex'
    source.write_text('''module limits;
fn plain(n:i64)->i64{var i:i64=0;while i<n{i=i+1;}return i;}
fn main()->unit !{task,io}{let held:list<str>=["retained🧠"];task_yield();print(plain(41)+len(held));}
''')
    defaults = {'steps': 1000000, 'timeout_ms': 5000, 'workers': 16}
    configured = {'steps': 10000, 'timeout_ms': 2000, 'workers': 2}
    default = cli(root, 'build', source)
    default_metadata = json.loads((Path(default['executable']).parent / 'build.json').read_text())
    assert default_metadata['task_limits'] == defaults, default_metadata
    flags = ['--task-steps', '10000', '--task-timeout-ms', '2000', '--task-workers', '2']
    built = cli(root, 'build', source, *flags)
    folder = Path(built['executable']).parent
    metadata = json.loads((folder / 'build.json').read_text())
    assert metadata['task_limits'] == configured and metadata['task_limits_specified'] is True, metadata
    assert built['build_key'] != default['build_key'], (built, default)
    llvm = Path(built['llvm']).read_text()
    assert 'nex_task_application_execute_limits_at' in llvm, llvm[:1000]
    # The actual linked identity must describe the same embedded ceilings.
    identity_source = (folder / 'application-identity.cpp').read_text()
    identity = json.loads(json.loads(identity_source.split('return ', 1)[1].split(';}', 1)[0]))
    assert identity['task_limits'] == configured, identity
    assert metadata['runtime_inputs']['nex_task_limits.h'], metadata
    warm = cli(root, 'build', source, *flags)
    assert warm['cached'] is True and warm['build_key'] == built['build_key'], warm
    standalone = root / 'copied-app'
    shutil.copy2(built['executable'], standalone)
    hidden = source.with_suffix('.hidden')
    source.rename(hidden)
    environment = {'PATH': '/usr/bin:/bin', 'NEX_TASK_STEPS': '1',
                   'NEX_TASK_TIMEOUT_MS': '1', 'NEX_TASK_WORKERS': '1'}

    def app(*arguments):
        return subprocess.run([str(standalone), *arguments], cwd='/', env=environment,
                              capture_output=True, text=True, timeout=10)

    try:
        actual = app()
        assert (actual.returncode, actual.stdout, actual.stderr) == (0, '42\n', ''), actual
        actual = app('--nex-task-steps', '2000', '--nex-task-timeout-ms', '1000', '--nex-task-workers', '1')
        assert (actual.returncode, actual.stdout, actual.stderr) == (0, '42\n', ''), actual
        malformed = [
            ('--nex-task-steps', '10001'), ('--nex-task-timeout-ms', '2001'),
            ('--nex-task-workers', '3'), ('--nex-task-workers', '0'),
            ('--nex-task-steps', '-1'), ('--nex-task-steps', '1x'),
            ('--nex-task-steps',), ('--nex-task-steps', '1', '--nex-task-steps', '1'),
            ('--nex-task-workers=1',), ('--nex-task-unknown', '1'),
        ]
        for arguments in malformed:
            actual = app(*arguments)
            assert actual.returncode == 70 and not actual.stdout and actual.stderr.startswith('E_OPTION:'), (arguments, actual)
        actual = app('--nex-task-steps', '1')
        assert actual.returncode == 70 and actual.stderr.startswith('E_LIMIT:'), actual
    finally:
        hidden.rename(source)
    # Compiler supervision records the same parsed effective limits as the
    # copied launcher's canonical parser; ordinary app arguments stay literal.
    observed = cli(root, 'run', source, *flags, '--', '--nex-task-steps', '2000', '--nex-task-workers', '1')
    execution = observed['task_execution']
    assert execution['configured'] == configured and execution['effective'] == {'steps': 2000, 'timeout_ms': 2000, 'workers': 1}, observed
    assert execution['executor_workers'] == 1 and execution['backend'] == 'native', execution
    pure = root / 'pure.nex'
    pure.write_text('module pure;fn unused()->unit !{task}{task_yield();}fn main()->unit{}')
    assert cli(root, 'build', pure, '--task-steps', '1000000', success=False)['code'] == 'E_OPTION'
    for bad in ['0', '-1', '9007199254740992', '1.5']:
        assert cli(root, 'build', source, '--task-steps', bad, success=False)['code'] == 'E_OPTION'
    # A pure, non-suspending loop still polls the shared native request budget.
    spin = root / 'spin.nex'
    spin.write_text('module spin;fn loop()->unit{let held:list<str>=["retained🧠"];while true{assert(len(held)==1);}}fn main()->unit !{task}{task_yield();loop();}')
    limited = cli(root, 'build', spin, '--task-steps', '1000000000', '--task-timeout-ms', '30', '--task-workers', '1')
    actual = subprocess.run([limited['executable']], cwd='/', env=environment, capture_output=True, text=True, timeout=10)
    assert actual.returncode == 70 and actual.stderr.startswith('E_TIMEOUT:'), actual
    print(json.dumps({'ok': True, 'defaults': defaults, 'configured': configured,
                      'standalone': True, 'no_environment_authority': True,
                      'malformed_launcher_cases': len(malformed), 'cache_identity': True,
                      'native_loop_deadline': True, 'effective_reporting': True}))
