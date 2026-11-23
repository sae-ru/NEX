"""Persistent matching-runtime sessions with real checked030 code-only images."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('compiler', type=Path)
p.add_argument('--host', required=True, type=Path)
p.add_argument('--clang', required=True, type=Path)
p.add_argument('--output', type=Path)
a = p.parse_args()
compiler, host, clang = a.compiler.resolve(), a.host.resolve(), a.clang.absolute()
source = Path(__file__).resolve().parents[1]/'examples/native-host-session'
out = (a.output or Path(tempfile.mkdtemp(prefix='nex-native-sessions-'))).resolve()
out.mkdir(parents=True, exist_ok=True)
assert not (out/'commands.json').exists(), 'use a fresh qualification output'
sha = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
commands = []
env = dict(os.environ)
for key in ('NEX_RESOURCE_DIR', 'NEX_PROFILE_OUTPUT', 'NEX_TRACY'):
    env.pop(key, None)


def run(argv, cwd, extra_env=None):
    result = subprocess.run(list(map(str, argv)), cwd=cwd, env=env | (extra_env or {}),
                            capture_output=True, text=True, encoding='utf-8', timeout=420)
    row = {'command': list(map(str, argv)), 'cwd': str(cwd), 'exit_code': result.returncode,
           'stdout': result.stdout, 'stderr': result.stderr}
    commands.append(row)
    (out/'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2)+'\n')
    assert result.returncode == 0, row
    return result


exports = {
    'core': ('native_session_core', ['make', 'get', 'add', 'fail', 'snapshot', 'cycle', 'spin', 'overflow']),
    'mid': ('native_session_mid', ['twice']),
    'files': ('native_session_files', ['open_file', 'read_file', 'seek_file', 'close_file', 'error_file', 'empty_stash', 'stash', 'use_stash'])}
driver_flags = []
if os.name == 'nt':
    doctor = json.loads(run([compiler, 'doctor', '--json'], out).stdout)
    if doctor.get('sdk_manifest') and clang.samefile(doctor['native_compiler']):
        # The relocated Clang and the packaged UCRT sysroot live in different trees.
        driver_flags = ['--target=' + doctor['host'], '--sysroot=' + doctor['native_sysroot']]
kernel = json.loads(run([host], out).stdout)
assert kernel['ok'] and kernel['cases'] == 14 and kernel['live_delta'] == 0
report = {'schema': 'nex.native-task-sessions/1', 'compiler_sha256': sha(compiler),
          'host_sha256': sha(host), 'harness_sha256': sha(__file__), 'platform': platform.platform(),
          'example_sha256': {f.relative_to(source).as_posix(): sha(f) for f in source.rglob('*') if f.is_file()},
          'kernel': kernel, 'profiles': [], 'portable_SDK': False, 'whole_goal_complete': False}
for profile in ('debug', 'release'):
    folder = out/profile
    shutil.copytree(source, folder)
    reference = json.loads(run([compiler, 'eval', 'app/main.nex', '--json'], folder).stdout)
    assert reference['stdout'] == '42\n'
    built = json.loads(run([compiler, 'project', 'nex.build.json', '--kind', 'build', '--configuration', profile, '--json'], folder).stdout)
    assert built['ok']
    app = json.loads(run([compiler, 'project', 'nex.build.json', '--kind', 'run', '--component', 'app', '--configuration', profile, '--json'], folder).stdout)
    assert app['ok'] and app['observation']['stdout'] == reference['stdout']
    records, images, accessors = {}, {}, []
    for component, (module, names) in exports.items():
        candidates = []
        for path in (folder/'.nex').rglob('task-provider.json'):
            record = json.loads(path.read_text())
            if record.get('artifact_kind') == 'pic-stage' and record.get('component') == component:
                candidates.append((path, record))
        assert len(candidates) == 1, [(str(path), r.get('profile')) for path, r in candidates]
        path, record = candidates[0]
        assert record['schema'] == 'nex.native-task-provider/17' and record['code_only']
        assert record['descriptor_abi'] == int('4e45585400000008', 16)
        assert record['descriptor_size'] == 88 and record['abi_offset'] == 40
        archives = list(path.parent.glob('*.a'))
        assert len(archives) == 1, archives
        archive = archives[0]
        shared = folder/('session-'+component+('.dylib' if platform.system() == 'Darwin' else '.dll' if os.name == 'nt' else '.so'))
        if platform.system() == 'Darwin':
            flags = ['-dynamiclib', '-undefined', 'dynamic_lookup',
                     '-Xlinker', '-force_load', '-Xlinker', str(archive)]
            if component == 'mid':
                flags += [images['core']]
        elif os.name == 'nt':
            flags = ['-shared', '-Wl,--whole-archive', archive, '-Wl,--no-whole-archive',
                     host.parent/('lib'+host.stem+'.dll.a'),
                     '-Xlinker', '--out-implib', '-Xlinker', str(shared)+'.a']
            if component == 'mid':
                flags += [str(images['core'])+'.a']
        else:
            flags = ['-shared', '-fPIC', '-Wl,--whole-archive', archive, '-Wl,--no-whole-archive']
            if component == 'mid':
                flags += ['-Wl,--no-as-needed', images['core']]
        run([clang, *driver_flags, *flags, '-o', shared], folder)
        images[component] = shared
        accessors += [record['exports'][module+'::'+name]['accessor'] for name in names]
        records[component] = {'provider': record, 'archive_sha256': sha(archive), 'image_sha256': sha(shared)}
    data = folder/'data'
    data.mkdir()
    (data/'input.txt').write_bytes('A🌍\0Z'.encode())
    observed = json.loads(run([host, *images.values(), *accessors], folder,
                              {'NEX_FILES_ROOT': str(data), 'NEX_FILES_WRITE': '1', 'NEX_FILES_LIMIT': '256'}).stdout)
    assert observed['ok'] and observed['cases'] == 13 and observed['live_delta'] == 0
    report['profiles'].append({'profile': profile, 'records': records, 'host': observed, 'ordinary_project_stdout': '42\n'})
report['commands'] = len(commands)
(out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'ok': True, 'kernel_cases': 14, 'profiles': len(report['profiles']), 'compiled_cases_per_profile': 13, 'commands': len(commands)}))
