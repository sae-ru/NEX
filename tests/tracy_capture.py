"""Optional acceptance check using matching upstream Tracy tools (not CTest)."""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nex', type=Path)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--export', dest='exporter', type=Path, required=True)
    parser.add_argument('--inspect', type=Path)
    parser.add_argument('--runs', type=int, default=3)
    parser.add_argument('--output', type=Path, default=Path('build/tracy-profile-acceptance'))
    options = parser.parse_args()
    if not 1 <= options.runs <= 20:
        parser.error('runs must be 1..20')
    repo = Path(__file__).resolve().parents[1]
    compiler, capture_tool, exporter = options.nex.resolve(), options.capture.resolve(), options.exporter.resolve()
    output = options.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([str(compiler), 'build', str(repo / 'examples/profiling/main.nex'), '--profile', 'profile', '--json'], cwd=repo, text=True, capture_output=True, timeout=180, check=True)
    built = json.loads(result.stdout)
    records = []
    for index in range(options.runs):
        with socket.socket() as reserve:
            reserve.bind(('127.0.0.1', 0))
            port = reserve.getsockname()[1]
        raw, trace = output / f'run-{index}.json', output / f'run-{index}.tracy'
        environment = {**os.environ, 'NEX_TRACY': '1', 'NEX_TRACY_WAIT_MS': '15000', 'TRACY_PORT': str(port), 'NEX_PROFILE_OUTPUT': str(raw)}
        application = subprocess.Popen([built['executable']], env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        collector = None
        try:
            deadline = time.monotonic() + 10
            while True:
                try:
                    with socket.create_connection(('127.0.0.1', port), timeout=.1):
                        break
                except OSError:
                    if application.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError('Tracy application did not open its localhost listener')
                    time.sleep(.01)
            with (output / f'capture-{index}.log').open('w') as log:
                collector = subprocess.Popen([str(capture_tool), '-a', '127.0.0.1', '-p', str(port), '-f', '-o', str(trace)], stdout=log, stderr=subprocess.STDOUT)
                stdout, stderr = application.communicate(timeout=30)
                assert application.returncode == 0 and not stderr, (application.returncode, stdout, stderr)
                assert collector.wait(timeout=30) == 0
            runtime = json.loads(raw.read_text())
            assert runtime['build']['build_key'] == built['build_key']
            assert runtime['build']['revision'] == built['revision']
            exported = subprocess.run([str(exporter), str(trace)], capture_output=True, text=True, timeout=30, check=True)
            (output / f'zones-{index}.csv').write_text(exported.stdout, newline="\n")
            zones = list(csv.DictReader(io.StringIO(exported.stdout)))
            calls = {f['name']: f['calls'] for f in runtime['functions']}
            assert {row['name']: int(row['counts']) for row in zones} == calls
            for row in zones:
                assert Path(row['src_file']).is_file()
                assert float(row['total_ns']) > 0
            record = dict(trace=str(trace), build_key=built['build_key'], revision=built['revision'], stdout=stdout, functions=calls)
            if options.inspect:
                inspected = json.loads(subprocess.check_output([str(options.inspect.resolve()), str(trace)], text=True, timeout=30))
                assert runtime['build'] in inspected['application_info']
                pools = {p['name']: p for p in inspected['pools']}
                for pool in runtime['memory']:
                    actual = pools[pool['pool']]
                    assert actual['allocations'] == pool['allocations'] > 0
                    assert actual['frees'] == pool['frees']
                    assert actual['active'] == actual['usage'] == 0
                record['inspected'] = inspected
            records.append(record)
        finally:
            if application.poll() is None:
                application.kill()
                application.wait(timeout=5)
            if collector is not None and collector.poll() is None:
                collector.terminate()
                collector.wait(timeout=5)
    report = dict(schema='nex.tracy-acceptance/1', startup='application listener ready before capture', runs=records)
    (output / 'acceptance.json').write_text(json.dumps(report, indent=2) + '\n', newline="\n")
    print(json.dumps(dict(output=str(output / 'acceptance.json'), captures=len(records), inspected=bool(options.inspect))))


if __name__ == '__main__':
    main()
