"""Actual ABI5 image flags, standalone build metadata and original file grants."""
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument('probe', type=Path)
parser.add_argument('--output', type=Path)
args = parser.parse_args()
probe = args.probe.resolve()
temporary = None
if args.output:
    root = args.output.resolve()
    root.mkdir()
else:
    temporary = tempfile.TemporaryDirectory(prefix='nex stream requirements ')
    root = Path(temporary.name)
started = time.monotonic()
report = {'schema': 'nex.private024-stream-requirements/1', 'ok': False,
          'commands': [], 'operation_cases': [], 'application_cases': [],
          'probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest(),
          'public_language': '0.23', 'private_language': '0.24',
          'public024_published': False, 'full_objective_complete': False}


def save():
    report['seconds'] = round(time.monotonic() - started, 3)
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')


def run(name, argv, env=None, expected=0):
    result = subprocess.run(list(map(str, argv)), cwd=root, env=env or os.environ,
                            text=True, capture_output=True, timeout=240)
    (root / (name + '.stdout')).write_text(result.stdout)
    (root / (name + '.stderr')).write_text(result.stderr)
    report['commands'].append({'name': name, 'argv': list(map(str, argv)),
                               'exit_code': result.returncode})
    save()
    assert result.returncode == expected, (name, result.returncode, result.stdout, result.stderr)
    return result


def invoke(name, mode, source, language='0.24', entry=None):
    argv = [probe, mode, source, root / 'native', language]
    if entry:
        argv.append(entry)
    return json.loads(run(name, argv).stdout)


def image_flags(mlir):
    # Inspect the actual descriptor's requirements member, not inferred source text.
    descriptors = re.findall(r'llvm\.mlir\.global private constant @nex_task_code_\d+\(\).*?\n  }', mlir, re.S)
    assert descriptors
    result = []
    for descriptor in descriptors:
        constants = dict(re.findall(r'(%s\d+) = llvm\.mlir\.constant\((\d+) : i64\)', descriptor))
        member = re.search(r'llvm\.insertvalue (%s\d+), %s\d+\[10\]', descriptor)
        assert member and member[1] in constants
        requirements = int(constants[member[1]])
        result.append((bool(requirements & 16), bool(requirements & 512), bool(requirements & 2048)))
    return result


try:
    # Expected operation classes are explicit ABI conformance expectations.
    operations = [
        ('open_read', 'file_open_read("input");', (True, False, True)),
        ('open_write', 'file_open_write("output");', (False, True, True)),
        ('open_append', 'file_open_append("output");', (False, True, True)),
        ('read', 'file_read(f,1);', (True, False, True)),
        ('write', 'file_write(f,utf8_bytes("x"));', (False, True, True)),
        ('seek', 'file_seek(f,0);', (False, False, True)),
        ('size', 'file_size(f);', (False, False, True)),
        ('flush', 'file_flush(f);', (False, True, True)),
        ('close', 'file_close(f);', (False, False, True)),
        ('is_open', 'file_is_open(f);', (False, False, True)),
        ('whole_read', 'file_read_bytes("input");', (True, False, False)),
        ('whole_write', 'file_write_bytes("output",utf8_bytes("x"));', (False, True, False)),
        ('no_file_operation', 'task_yield();', (False, False, False)),
    ]
    for name, body, expected in operations:
        source = root / (name + '.nex')
        source.write_text('module requirements;server fn target(f:file)->unit !{task,fs}{' + body + '}\n')
        flags = image_flags(invoke(name, 'emit', source, entry='target')['mlir'])
        assert flags == [expected], (name, flags, expected)
        report['operation_cases'].append({'name': name, 'flags': flags})
        save()

    applications = [
        ('read_only', 'let f:file=unwrap(file_open_read("input"));assert(unwrap(file_read(f,3))==utf8_bytes("abc"));assert(unwrap(file_size(f))==3);assert(unwrap(file_seek(f,0))==0);assert(file_is_open(f));assert(file_close(f));', (True, False, True), False),
        ('write_only', 'let f:file=unwrap(file_open_write("output"));assert(unwrap(file_write(f,utf8_bytes("x")))==1);assert(unwrap(file_flush(f)));assert(file_close(f));', (False, True, True), True),
        ('append_only', 'let f:file=unwrap(file_open_append("output"));assert(unwrap(file_write(f,utf8_bytes("x")))==1);assert(file_close(f));', (False, True, True), True),
        ('mixed', 'let f:file=unwrap(file_open_read("input"));let g:file=unwrap(file_open_write("output"));assert(unwrap(file_write(g,unwrap(file_read(f,3))))==3);assert(file_close(f));assert(file_close(g));', (True, True, True), True),
        ('no_file', 'task_yield();', (False, False, False), False),
        ('read_grant_not_upgraded', 'assert(error_code(file_open_write("output"))=="CAPABILITY");let f:file=unwrap(file_open_read("input"));assert(error_code(file_write(f,utf8_bytes("bad")))=="CAPABILITY");assert(file_close(f));', (True, True, True), False),
    ]
    for name, body, expected, writable in applications:
        source = root / (name + '-main.nex')
        source.write_text('module app;server fn unreachable()->unit !{task,fs}{file_open_write("UNREACHABLE_WRITE");}server fn main()->i64 !{task,fs}{' + body + 'return 42;}\n')
        emitted = invoke(name + '-emit', 'emit', source)['mlir']
        assert image_flags(emitted) == [expected]
        assert 'UNREACHABLE_WRITE' not in emitted
        result = invoke(name + '-build', 'build', source)
        binary = Path(result['executable'])
        metadata = json.loads((binary.parent / 'build.json').read_text())
        for record in [metadata, metadata['runtime_requirements']]:
            actual = tuple(record[k] for k in ['task_file_reads', 'task_file_writes', 'task_file_streams'])
            assert actual == expected, (name, actual, expected)
            assert record['task_execution_abi'] == 0x4e45585400000005
        directory = root / (name + '-files')
        directory.mkdir()
        (directory / 'input').write_bytes(b'abc')
        runtime = {'PATH': '/usr/bin:/bin'}
        if name != 'no_file':
            runtime['NEX_FILES_ROOT'] = str(directory)
        if writable:
            runtime['NEX_FILES_WRITE'] = '1'
        source.rename(source.with_suffix('.hidden'))
        try:
            raw = run(name + '-execute', [binary], runtime, 42)
            assert not raw.stdout and not raw.stderr
        finally:
            source.with_suffix('.hidden').rename(source)
        assert (directory / 'input').read_bytes() == b'abc'
        assert not (directory / 'UNREACHABLE_WRITE').exists()
        if name in ['write_only', 'append_only']:
            assert (directory / 'output').read_bytes() == b'x'
        elif name == 'mixed':
            assert (directory / 'output').read_bytes() == b'abc'
        else:
            assert not (directory / 'output').exists()
        report['application_cases'].append({'name': name, 'flags': expected,
            'executable': str(binary), 'sha256': hashlib.sha256(binary.read_bytes()).hexdigest()})
        save()

    # Published023 retains its ABI4 descriptor and rejects stream execution.
    source = root / 'retained023.nex'
    source.write_text('module retained;server fn main()->i64 !{task,fs}{assert(unwrap(file_write_bytes("output",utf8_bytes("x"))));return 42;}\n')
    old = invoke('retained023-build', 'build', source, '0.23')
    metadata = json.loads((Path(old['executable']).parent / 'build.json').read_text())
    assert metadata['task_execution_abi'] == 0x4e45585400000004
    assert metadata['task_file_reads'] is True and metadata['task_file_writes'] is True
    assert 'task_file_streams' not in metadata and 'task_file_streams' not in metadata['runtime_requirements']
    assert image_flags(invoke('retained023-emit', 'emit', source, '0.23')['mlir']) == [(False, True, False)]
    report.update(ok=True, operation_checks=len(operations), standalone_applications=len(applications),
                  retained023_metadata_unchanged=True, source_absent_execution=True,
                  read_grant_not_upgraded=True, unreachable_write_pruned=True)
except BaseException as error:
    report['error'] = repr(error)
    raise
finally:
    save()
    print(json.dumps({k: report.get(k) for k in ['ok', 'operation_checks', 'standalone_applications', 'error']}), flush=True)
