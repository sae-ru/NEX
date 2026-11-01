"""Memcheck the exact native executables retained by owned-cuda/verify.py."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hardware-report', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--sanitizer', type=Path)
    parser.add_argument('--deadline-ms', type=int, default=2000,
                        help='Instrumented deadline; physical enqueue/drain checks remain mandatory')
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('use native Windows Python')
    if not 1000 <= args.deadline_ms <= 60000:
        parser.error('--deadline-ms must be 1000..60000')
    source = args.hardware_report.resolve(strict=True)
    base = json.loads(source.read_bytes())
    require(base.get('schema') == 'nex.owned-cuda-hardware/1' and
            all(base.get(key) is True for key in ('ok', 'actual_GPU_execution',
                'CUDA_from_NEX_accepted', 'full_hardware_corpus')),
            'use a successful complete owned CUDA hardware report')
    expected = {case['name']: case for case in base['cases']}
    require(len(expected) == len(base['cases']) == 35,
            'expected the complete 35-case CUDA corpus')
    native = {row['label'][:-7]: row for row in base['commands']
              if row['label'].endswith('-native')}
    require(set(native) == set(expected), 'native command inventory differs from the cases')
    contexts = [row for row in base['commands'] if row['label'] == 'trusted-host-context-probe']
    require(len(contexts) == 1, 'expected one physical context probe')
    if args.sanitizer:
        tool = args.sanitizer.resolve(strict=True)
    else:
        selected = shutil.which('compute-sanitizer.exe')
        if not selected:
            selected = str(Path(os.environ.get('CUDA_PATH', '')) /
                           'compute-sanitizer/compute-sanitizer.exe')
        tool = Path(selected).resolve(strict=True)
    version = subprocess.run([tool, '--version'], capture_output=True, timeout=30)
    require(version.returncode == 0, 'Compute Sanitizer --version failed')
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = {'schema': 'nex.cuda-nex-memcheck/1', 'ok': False,
        'requires_WSL': False, 'compiler_sha256': base['compiler_sha256'],
        'hardware_report': str(source), 'hardware_report_sha256': sha(source),
        'module_sha256': base['module_sha256'], 'manifest_sha256': base['manifest_sha256'],
        'sanitizer': str(tool), 'sanitizer_sha256': sha(tool),
        'version': (version.stdout + version.stderr).decode('utf-8', 'replace'),
        'connection_transport': 'windows-named-pipes',
        'verifier_sha256': sha(__file__), 'deadline_timeout_ms': args.deadline_ms,
        'full_windows_regression_accepted': False, 'cases': []}

    def save():
        (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False,
            indent=2) + '\n', encoding='utf-8')

    # Validate every retained executable before the first launch. Only native
    # commands from the reviewed hardware corpus are replayed, never build/eval.
    binaries = {}
    for name, old in native.items():
        case = expected[name]
        require(Path(old['argv'][0]).resolve() == Path(case['executable']).resolve(),
                'native executable differs: ' + name)
        binaries[old['argv'][0]] = case['executable_sha256']
        argv = old['argv']
        require(argv[1:2] == ['--nex-foreign'] and
                argv[3:5] == ['--nex-task-workers', '1'] and len(argv) in (5, 7),
                'unexpected native arguments: ' + name)
        if len(argv) == 7:
            require(argv[5] == '--nex-task-timeout-ms' and argv[6].isdigit(),
                    'unexpected native timeout arguments')
        host = Path(argv[2]).resolve(strict=True)
        catalogue = json.loads(host.read_bytes())
        libraries = list(catalogue['libraries'].values())
        require(len(libraries) == 1, 'expected one CUDA provider')
        bundle = (host.parent / libraries[0]['directory']).resolve(strict=True)
        manifest = bundle / 'manifest.json'
        require(sha(manifest) == base['manifest_sha256'] == libraries[0]['manifest_sha256'],
                'CUDA manifest differs from the hardware receipt')
        entry = json.loads(manifest.read_bytes())['entry']
        require(sha(bundle / entry) == base['module_sha256'], 'CUDA module changed')
    binaries[contexts[0]['argv'][0]] = base['trusted_host_context_probe']['executable_sha256']
    for path, digest in binaries.items():
        require(sha(path) == digest, 'retained executable changed: ' + path)
    save()
    try:
        for old in contexts + list(native.values()):
            name = old['label'].removesuffix('-native')
            argv = list(old['argv'])
            deadline = name == 'deadline_enqueued_GPU'
            pending = name in ('cancel_enqueued_GPU', 'deadline_enqueued_GPU')
            if deadline:
                at = argv.index('--nex-task-timeout-ms') + 1
                baseline_deadline = int(argv[at])
                argv[at] = str(args.deadline_ms)
            log, trace = out / (name + '.memcheck.log'), out / (name + '.trace.jsonl')
            environment = {k: v for k, v in os.environ.items() if not k.startswith('NEX_')}
            environment.update(PYTHONUTF8='1', NEX_OWNED_CUDA_TRACE=str(trace),
                NV_COMPUTE_SANITIZER_LOCAL_CONNECTION_OVERRIDE='named-pipes')
            if pending:
                environment.update(NEX_CUDA_ACCEPTANCE_DELAY_CYCLES='200000000',
                                   NEX_CUDA_ACCEPTANCE_KERNEL_REPEATS='32')
            command = [str(tool), '--tool', 'memcheck', '--leak-check', 'full',
                       '--error-exitcode', '86', '--log-file', str(log), *argv]
            row = {'name': name, 'argv': command, 'executable_sha256': sha(argv[0]),
                   'expected_exit_code': old['exit_code'], 'ok': False}
            if deadline:
                row['baseline_deadline_timeout_ms'] = baseline_deadline
            report['cases'].append(row)
            save()
            began = time.monotonic()
            result = subprocess.run(command, cwd=old['cwd'], env=environment,
                                    capture_output=True, timeout=300)
            row.update(exit_code=result.returncode, seconds=round(time.monotonic() - began, 3))
            (out / (name + '.stdout')).write_bytes(result.stdout)
            (out / (name + '.stderr')).write_bytes(result.stderr)
            require(result.returncode == old['exit_code'], name + ': unexpected exit code')
            text = log.read_text(encoding='utf-8', errors='replace')
            require('ERROR SUMMARY: 0 errors' in text and re.search(
                r'LEAK SUMMARY:\s+0 bytes leaked in 0 allocations', text),
                name + ': Compute Sanitizer did not confirm zero errors/leaks')
            records = [json.loads(line) for line in trace.read_text(encoding='utf-8').splitlines()]
            require(records and records[-1]['event'] == 'module_unloaded' and
                    all(item['event'] != 'unsettled' for item in records),
                    name + ': CUDA module did not settle')
            ledger = records[-1]['ledger']
            require(ledger['live_bytes'] == ledger['cleanup_errors'] == 0,
                    name + ': CUDA resources remain live')
            for allocated, freed in (('allocations', 'frees'), ('contexts', 'context_frees'),
                    ('events', 'event_frees'), ('streams', 'stream_frees'), ('modules', 'module_frees')):
                require(ledger[allocated] == ledger[freed], name + ': allocation/free mismatch')
            if name in expected:
                require(ledger == expected[name]['native']['ledger'],
                        name + ': physical work differs from the hardware corpus')
                if pending:
                    require(expected[name]['expected_error'].encode() in result.stderr,
                            name + ': wrong source error')
                    require(result.stdout == b'', name + ': unexpected source output')
                    require(any(item['event'] == 'kernel_queued' and item['completion_pending']
                                and item['physical_enqueue_verified'] for item in records),
                            name + ': no actual pending GPU work')
                    require(any(item['event'] == 'physical_drain' and
                        item['physical_completion_verified'] and item['event_status'] == 0
                        for item in records), name + ': physical completion was not confirmed')
                else:
                    require(result.stdout == b'42\n', name + ': native result differs')
            else:
                require(json.loads(result.stdout) == base['trusted_host_context_probe']['result'],
                        'physical context probe result differs')
            row.update(ok=True, ledger=ledger, trace_sha256=sha(trace), memcheck_log_sha256=sha(log))
            save()
            print(name + ': MEMCHECK_OK', flush=True)
        for path, digest in binaries.items():
            require(sha(path) == digest, 'retained executable changed during memcheck')
        require(sha(source) == report['hardware_report_sha256'], 'hardware report changed')
        report.update(ok=True, native_cases=len(native), context_probe=True)
    except BaseException as error:
        report['error'] = repr(error)
        raise
    finally:
        save()
        print(json.dumps({'ok': report['ok'], 'report': str(out / 'report.json')}), flush=True)


if __name__ == '__main__':
    main()
