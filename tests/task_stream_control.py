"""Real compiled NEX/independent AST file cancellation, deadlines and exits."""
from host_fixture import run_native
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('compiler', type=Path)
parser.add_argument('probe', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
compiler, probe = args.compiler.resolve(), args.probe.resolve()
source_root = Path(__file__).resolve().parents[1]
temporary = None
if args.output:
    root = args.output.resolve()
    root.mkdir()
else:
    temporary = tempfile.TemporaryDirectory(prefix='nex stream control ')
    root = Path(temporary.name)
started = time.monotonic()
report = {'schema': 'nex.private024-stream-control/1', 'ok': False,
          'commands': [], 'cases': [], 'images': {}, 'runtime_objects': {},
          'compiler_sha256': hashlib.sha256(compiler.read_bytes()).hexdigest(),
          'probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest(),
          'public024_published': False, 'full_objective_complete': False}


def save():
    report['seconds'] = round(time.monotonic() - started, 3)
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n', newline="\n")


def run(name, argv, env=None, input=None):
    result = run_native(list(map(str, argv)), cwd=root, env=env or os.environ,
                            input=input, text=True, capture_output=True, timeout=180)
    (root / (name + '.stdout')).write_text(result.stdout, newline="\n")
    (root / (name + '.stderr')).write_text(result.stderr, newline="\n")
    report['commands'].append({'name': name, 'argv': list(map(str, argv)),
                              'exit_code': result.returncode})
    save()
    assert result.returncode == 0, (name, result.returncode, result.stdout, result.stderr)
    return result.stdout


body = '''let f:file=unwrap(file_open_write("output"));
assert(unwrap(file_write(f,utf8_bytes("first")))==5);task_yield();
assert(unwrap(file_write(f,utf8_bytes("second")))==6);
assert(unwrap(file_flush(f)));assert(file_close(f));return 42;'''
programs = {
    'flow': 'module controlled;server fn main()->i64 !{task,fs}{' + body + '}',
    'modules': {'schema': 'nex.sources/1', 'entry': 'main.nex', 'files': {
        'main.nex': 'module app;import "./writer.nex" as writer;server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_write("output"));assert(writer::write_chunk(f,"first")==5);assert(writer::write_chunk(f,"second")==6);assert(unwrap(file_flush(f)));file_close(f);return 42;}',
        'writer.nex': 'module writer;pub server fn write_chunk(f:file,text:str)->i64 !{task,fs}{task_yield();return unwrap(file_write(f,utf8_bytes(text)));}'}},
    'overflow': 'module controlled;server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_write("output"));assert(unwrap(file_write(f,utf8_bytes("first")))==5);let n:i64=9223372036854775807;return n+1;}',
    'assertion': 'module controlled;server fn main()->i64 !{task,fs}{let f:file=unwrap(file_open_write("output"));assert(false);return 42;}',
    'source_cancel': '''module controlled;server fn main()->i64 !{task,fs}{
return with_tasks(1,server fn(s:task_scope)->i64 !{task,fs}{
let ready:channel<i64>=channel_new<i64>(s,0);let parked:channel<i64>=channel_new<i64>(s,0);
let writer:task<unit>=task_spawn(s,server fn()->unit !{task,fs}{
let f:file=unwrap(file_open_write("output"));assert(unwrap(file_write(f,utf8_bytes("first")))==5);
assert(task_send(ready,1));task_recv(parked);file_write(f,utf8_bytes("must-not-write"));});
task_recv(ready);assert(task_cancel(writer));task_wait(writer);return 42;});}''',
    'propagation': '''module controlled;
server fn attempt()->result<i64> !{task,fs}{let f:file=unwrap(file_open_write("output"));
assert(unwrap(file_write(f,utf8_bytes("first")))==5);let missing:file=file_open_read("missing")?;return ok(1);}
server fn main()->i64 !{task,fs}{var i:i64=0;while i<70{
let outcome:result<i64>=with_tasks(1,server fn(s:task_scope)->result<i64> !{task,fs}{return attempt();});
assert(error_code(outcome)=="NOT_FOUND");i=i+1;}return 42;}''',
}
cases = [
    ('cancel_before_open', 'flow', 'cancel', 'file_open_write', 1, 'E_CANCELLED', b'original'),
    ('cancel_after_open', 'flow', 'cancel', 'file_write', 1, 'E_CANCELLED', b''),
    ('cancel_after_first_chunk', 'flow', 'cancel', 'file_write', 2, 'E_CANCELLED', b'first'),
    ('cancel_before_close', 'flow', 'cancel', 'file_close', 1, 'E_CANCELLED', b'firstsecond'),
    ('deadline_after_first_chunk', 'flow', 'deadline', 'file_write', 2, 'E_TIMEOUT', b'first'),
    ('revoke_after_open', 'flow', 'revoke', 'file_write', 1, 'E_RESOURCE_SCOPE', b''),
    ('module_cancel_after_first_chunk', 'modules', 'cancel', 'file_write', 2, 'E_CANCELLED', b'first'),
    ('module_revoke_after_open', 'modules', 'revoke', 'file_write', 1, 'E_RESOURCE_SCOPE', b''),
    ('overflow_after_first_chunk', 'overflow', 'none', 'none', 0, 'E_OVERFLOW', b'first'),
    ('assertion_after_open', 'assertion', 'none', 'none', 0, 'E_ASSERT', b''),
    ('source_task_cancel_owns_open_file', 'source_cancel', 'none', 'none', 0, 'E_CANCELLED', b'first'),
    ('propagated_error_reuses_quota', 'propagation', 'none', 'none', 0, '', b'first'),
]

try:
    doctor = json.loads(run('doctor', [compiler, 'doctor', '--json']))
    clang = doctor['native_compiler']
    target = run('target', [clang, '-S', '-emit-llvm', '-x', 'c++', '-', '-o', '-'], input='')
    triple = re.search(r'target triple = "([^"]+)"', target)[1]
    layout = re.search(r'target datalayout = "([^"]+)"', target)[1]
    runtime = source_root / 'runtime'
    flags = ['-std=c++20', '-g', '-O0', '-pthread', '-DNEX_STRUCTURED_WORKERS', '-DNEX_ASYNC_TASKS', '-I', runtime]
    objects = []
    report['native_host_source_sha256'] = hashlib.sha256((source_root / 'tests/task_stream_control_native.cpp').read_bytes()).hexdigest()
    for name in ['runtime.cpp', 'nex_files.cpp', 'nex_task_external.cpp', 'nex_task_frame.cpp',
                 'nex_resource_region.cpp', 'nex_external_resource.cpp', 'nex_resource_executor.cpp']:
        output = root / (name + '.o')
        run('runtime-' + name, [clang, *flags, '-c', runtime / name, '-o', output])
        objects.append(output)
        report['runtime_objects'][name] = {'object': str(output), 'sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
                                          'source_sha256': hashlib.sha256((runtime / name).read_bytes()).hexdigest()}
    sources = {}
    for name, source in programs.items():
        path = root / (name + ('.json' if isinstance(source, dict) else '.nex'))
        path.write_text(json.dumps(source) if isinstance(source, dict) else source, newline="\n")
        sources[name] = path
        staged = json.loads(run(name + '-stage', [probe, 'stage', path, root / (name + '-staged'), '0.24', triple, layout]))
        binary = root / (name + '-native')
        run(name + '-link', [clang, *flags, '-DNEX_TEST_DESCRIPTOR=' + staged['descriptor'],
                            source_root / 'tests/task_stream_control_native.cpp', staged['llvm'],
                            *objects, *([] if sys.platform == 'darwin' else ['-ldl']), '-o', binary])
        report['images'][name] = {'executable': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
                                 'revision': staged['revision'], 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'llvm': staged['llvm'], 'llvm_sha256': hashlib.sha256(Path(staged['llvm']).read_bytes()).hexdigest(),
                                 'mlir': staged['mlir'], 'mlir_sha256': hashlib.sha256(Path(staged['mlir']).read_bytes()).hexdigest()}
        save()
    for name, program, mode, operation, occurrence, expected_error, expected_bytes in cases:
        outcomes = {}
        for backend in ['reference', 'native']:
            files = root / (name + '-' + backend)
            files.mkdir()
            (files / 'output').write_bytes(b'original')
            env = {**os.environ, 'NEX_FILES_ROOT': str(files), 'NEX_FILES_WRITE': '1'}
            source = sources[program]
            if backend == 'reference':
                argv = [probe, 'eval-control', source, root / 'unused', '0.24', mode, operation + ':' + str(occurrence)]
                result = json.loads(run(name + '-reference', argv, env))
                assert result['revision'] == report['images'][program]['revision']
            else:
                hidden = source.with_suffix('.hidden')
                source.rename(hidden)
                try:
                    argv = [report['images'][program]['executable'], mode, operation, occurrence, files]
                    result = json.loads(run(name + '-native', argv, {'PATH': '/usr/bin:/bin', **{k: v for k, v in os.environ.items() if k.endswith('SAN_OPTIONS')}}))
                finally:
                    hidden.rename(source)
            assert result['ok'] and result['control_error'] == expected_error, (name, backend, result)
            assert not (root / (name + '-' + backend + '.stderr')).read_text()
            assert result['control_fired'] == (mode != 'none'), (name, backend, result)
            assert result['physical_file_settlement'] and result['live_objects_restored']
            if not expected_error:
                assert result['value'] == 42
            assert (files / 'output').read_bytes() == expected_bytes, (name, backend)
            assert not (files / 'missing').exists()
            outcomes[backend] = result
        report['cases'].append({'name': name, 'program': program, 'mode': mode,
                                'operation': operation, 'occurrence': occurrence,
                                'expected_error': expected_error, 'expected_bytes_hex': expected_bytes.hex(),
                                'native_reference': True, 'outcomes': outcomes})
        save()
    report.update(ok=True, native_reference_pairs=len(cases), compiled_images=len(programs),
                  real_group_and_stop_token_cancellation=True, real_deadline=True,
                  coordinator_file_scope_revocation=True, physical_settlement_before_return=True,
                  source_absent_native_execution=True, no_post_IO_rollback_claim=True)
except BaseException as error:
    report['error'] = repr(error)
    raise
finally:
    save()
    print(json.dumps({k: report.get(k) for k in ['ok', 'native_reference_pairs', 'compiled_images', 'error']}), flush=True)
