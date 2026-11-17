"""Run an explicit CTest tier and retain a fixture-complete, checked receipt.

The caller configures/builds first. This command never installs dependencies,
invokes a model, retries a failed group or treats a skipped group as accepted.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import time

TOOLS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nex_ci_tiers', TOOLS / 'ctest_tiers.py')
tiers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tiers)


def run(build, output, *, tier='core', selected=None, jobs=1, ctest='ctest', policy=None):
    build = Path(build).resolve(strict=True)
    output = Path(output).resolve()
    if tier not in ('core', 'full', 'selected') or type(jobs) is not int or not 1 <= jobs <= 8:
        raise ValueError('select core/full/selected and 1..8 jobs')
    if tier == 'selected':
        if (not isinstance(selected, (list, tuple)) or not selected
            or any(not isinstance(name, str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', name)
                   for name in selected) or len(set(selected)) != len(selected)):
            raise ValueError('selected requires distinct explicit registered group names')
        selected = list(selected)
    elif selected is not None:
        raise ValueError('--select requires --tier selected')
    if not (build / 'CMakeCache.txt').is_file():
        raise ValueError('configure and build the selected directory first')
    # A previous JUnit file or receipt must never satisfy a new invocation.
    output.mkdir(parents=True, exist_ok=False)
    started = time.monotonic()
    report = {'schema': 'nex.ci-ctest/1', 'ok': False, 'tier': tier,
              'build': str(build), 'requested_groups': selected or [],
              'phases': [], 'release_qualification': False}

    def save():
        (output / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')

    def command(name, argv):
        row = {'name': name, 'command': argv, 'status': 'running'}
        report['phases'].append(row)
        save()
        with (output / (name + '.stdout')).open('wb') as stdout, \
             (output / (name + '.stderr')).open('wb') as stderr:
            result = subprocess.run(argv, stdout=stdout, stderr=stderr)
        row.update(exit_code=result.returncode, status='passed' if result.returncode == 0 else 'failed')
        save()
        return result.returncode

    try:
        policy_path = Path(policy) if policy else TOOLS.parent / 'cmake/test-tiers.json'
        raw_policy = policy_path.read_bytes()
        declared = tiers.policy(raw_policy)
        report['policy_sha256'] = hashlib.sha256(raw_policy).hexdigest()
        if command('registry', [str(ctest), '--test-dir', str(build), '--show-only=json-v1']):
            raise ValueError('cannot obtain actual CTest registry')
        registry = output / 'registry.stdout'
        inventory = tiers.inspect(declared, tiers.decode(registry.read_bytes()))
        (output / 'tiers.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
        if tier == 'core':
            selected = inventory['tiers']['core']['selected_groups']
        elif tier == 'selected':
            # Resolve against the complete actual registry before executing.
            # CTest will add the selected groups' real fixture setup/cleanup.
            tiers.fixtures.fixture_closure(tiers.decode(registry.read_bytes()), selected)
        argv = [str(ctest), '--test-dir', str(build), '--output-on-failure',
                '--no-tests=error', '-j', str(jobs), '--output-log', str(output / 'ctest.log'),
                '--output-junit', str(output / 'results.xml')]
        if tier == 'core':
            argv += ['-L', '^core$']
        elif tier == 'selected':
            argv += ['-R', '^(' + '|'.join(re.escape(name) for name in selected) + ')$']
        code = command('ctest', argv)
        receipt = tiers.fixtures.inspect_files(registry, output / 'results.xml',
                                               ctest_exit_code=code, selected=selected)
        (output / 'ctest-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        report['ctest'] = receipt
        report['ok'] = receipt['ok']
    except (OSError, ValueError, TypeError, KeyError) as error:
        report['error'] = str(error)
    finally:
        direct_log = output / 'ctest.log'
        if direct_log.is_file():
            report['direct_log_sha256'] = hashlib.sha256(direct_log.read_bytes()).hexdigest()
        # LastTest.log is shared mutable CTest state. Even a nested inventory
        # query can replace it; retain it only as supplementary diagnostics.
        log = build / 'Testing/Temporary/LastTest.log'
        if any(p['name'] == 'ctest' and 'exit_code' in p for p in report['phases']) and log.is_file():
            shutil.copyfile(log, output / 'LastTest.log')
        report['seconds'] = round(time.monotonic() - started, 3)
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--tier', choices=('core', 'full', 'selected'), default='core')
    parser.add_argument('--select', action='append', help='Exact registered group; repeat with --tier selected')
    parser.add_argument('--jobs', type=int, choices=range(1, 9), default=1)
    parser.add_argument('--ctest', default='ctest')
    args = parser.parse_args()
    try:
        result = run(args.build, args.output, tier=args.tier, selected=args.select,
                     jobs=args.jobs, ctest=args.ctest)
    except (OSError, ValueError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}))
        return 2
    print(json.dumps({'ok': result['ok'], 'tier': result['tier'], 'seconds': result['seconds'],
                      'report': str(args.output / 'report.json')}))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
