"""Optional, observed profiling overhead for one fixed workload; no speed gate."""
import argparse
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import tempfile
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('nex', type=Path)
    parser.add_argument('--runs', type=int, default=9)
    parser.add_argument('--iterations', type=int, default=50000)
    parser.add_argument('--output', type=Path, default=Path('build/profile-benchmark.json'))
    options = parser.parse_args()
    if not 3 <= options.runs <= 100 or not 1 <= options.iterations <= 5000000:
        parser.error('runs must be 3..100; iterations 1..5000000')
    compiler = options.nex.resolve()
    with tempfile.TemporaryDirectory(prefix='nex-profile-overhead-') as temp:
        root = Path(temp)
        source = root / 'main.nex'
        source.write_text('''module benchmark;
fn add(x: i64) -> i64 { return x + 1; }
fn main() -> unit !{io} {
  var total: i64 = 0; var i: i64 = 0;
  while i < ITERATIONS { total = total + add(i); i = i + 1; }
  print(total);
}
'''.replace('ITERATIONS', str(options.iterations)))

        def cli(*args):
            result = subprocess.run([str(compiler), *map(str, args), '--json'], cwd=root, capture_output=True, text=True, timeout=180, check=True)
            return json.loads(result.stdout)

        builds = {mode: cli('build', '--profile', mode) for mode in ('release', 'profile')}
        context = cli('profile', '--scenario', 'checked add in fixed loop', '--events', '0')
        expected = str(options.iterations * (options.iterations + 1) // 2) + '\n'
        environment = {k: v for k, v in os.environ.items() if k not in ('NEX_PROFILE_OUTPUT', 'NEX_TRACY', 'NEX_PROFILE_EVENTS')}
        environment['NEX_TRACY'] = '0'
        durations = {mode: [] for mode in ('release', 'instrumented_dormant', 'local_aggregate')}
        # Rotate order between rounds to reduce systematic warm-cache/order bias.
        modes = list(durations)
        for round_index in range(options.runs + 1):
            for mode in modes[round_index % len(modes):] + modes[:round_index % len(modes)]:
                env = dict(environment)
                if mode == 'local_aggregate':
                    env.update(NEX_PROFILE_OUTPUT=str(root / 'runtime.json'), NEX_PROFILE_EVENTS='0')
                executable = builds['release' if mode == 'release' else 'profile']['executable']
                start = time.perf_counter_ns()
                process = subprocess.run([executable], capture_output=True, text=True, env=env, timeout=30, check=True)
                elapsed = time.perf_counter_ns() - start
                assert process.stdout == expected and not process.stderr
                if round_index:
                    durations[mode].append(elapsed)
        measured = json.loads((root / 'runtime.json').read_text())
        counts = {f['name']: f['calls'] for f in measured['functions']}
        assert counts == {'benchmark::add': options.iterations, 'benchmark::main': 1}
        assert measured['dropped_events'] == options.iterations + 1
        observed = {mode: dict(process_wall_ns=values, median_ns=int(statistics.median(values))) for mode, values in durations.items()}
        baseline = observed['release']['median_ns']
        for result in observed.values():
            result['ratio_to_release_process_median'] = result['median_ns'] / baseline
        report = dict(schema='nex.profile-overhead/1', toolchain=context['toolchain'], language=context['language'], hardware=context['hardware'], os=platform.platform(),
                      revision=context['revision'], builds={mode: b['build_key'] for mode, b in builds.items()}, iterations=options.iterations, runs=options.runs,
                      scenario='checked add in fixed loop', observation='whole-process elapsed time including launch and local report flush; one host/workload; no performance guarantee', results=observed)
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(dict(output=str(options.output.resolve()), medians_ms={mode: value['median_ns'] / 1000000 for mode, value in observed.items()})))


if __name__ == '__main__':
    main()
