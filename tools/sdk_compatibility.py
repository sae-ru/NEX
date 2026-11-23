#!/usr/bin/env python3
"""Run the published beta's 0.30 source and graph contracts on a host SDK."""
import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import sdk_archive
from sdk_compat_cli import check_cli
from sdk_compat_examples import check_examples
from sdk_compat_snapshot import check_snapshot
from sdk_compat_stdlib import check_stdlib


def sdk_identity(directory, cwd, environment):
    compiler = directory / 'bin' / ('nex.exe' if os.name == 'nt' else 'nex')
    resources = directory / 'share' / 'nex'
    doctor = json.loads(subprocess.check_output([compiler, 'doctor', '--json'], cwd=cwd, env=environment,
                                                timeout=60))
    discovery = json.loads(subprocess.check_output([compiler, 'describe', '--field', 'project_languages', '--json'],
                                                   cwd=cwd, env=environment, timeout=60))
    if ('0.30' not in discovery['value'] or discovery['toolchain'] != doctor['version']
            or not (resources / 'runtime' / 'runtime.cpp').samefile(doctor['runtime'])):
        raise ValueError('Expected a 0.30-capable compiler using its matching installed runtime')
    return compiler, {'toolchain': doctor['version'], 'host': doctor['host'], 'llvm': doctor['llvm'],
                      'compiler_build': discovery['compiler_build'], 'compiler_sha256': sdk_archive.digest(compiler),
                      'descriptor_hash': discovery['descriptor_hash'], 'source_versions': discovery['value'],
                      'runtime_sha256': sdk_archive.digest(resources / 'runtime' / 'runtime.cpp')}


def host_abi(triple):
    # Darwin's build-host kernel release is present in the LLVM triple. The
    # programs execute together on this host even if the SDKs were built on
    # different macOS releases. Keep the architecture and OS/ABI boundary.
    return re.sub(r'(?<=-darwin)[0-9]+(?:\.[0-9]+)*$', '', triple)


def migration_observations(folder, receipt):
    # Older published reports omit the origin language in the gate summary.
    # Read the real plan output and bind it to its recorded command, in each case.
    runs = [p for p in folder.glob('run-*') if p.is_dir()]
    if len(runs) != 1:
        raise ValueError('expected exactly one CLI suite invocation')
    plans = set()
    for number, cmd in enumerate(receipt['commands']):
        if cmd['args'][0] != 'migrate' or '--kind' not in cmd['args'] or 'plan' not in cmd['args'] or cmd['exit']:
            continue
        path = runs[0] / f'{number:03d}-migrate.stdout'
        text = path.read_text(encoding='utf-8')
        if hashlib.sha256(text.encode()).hexdigest() != cmd['stdout_sha256']:
            raise ValueError('migration plan does not match the recorded command')
        plan = json.loads(text)
        if plan['origin_verified'] is not True or plan['target_language'] != '0.30':
            raise ValueError('expected verified historical origin and target 0.30')
        plans.add((plan['origin_language'], not plan['target_valid']))
    return plans


def check_migrations(baseline, candidate, resources, root, environment, published):
    suite = resources / 'tests' / 'references030_cli.py'
    replay_env = dict(environment)
    replay_env.pop('PYTHONOPTIMIZE', None)
    folder = root / ('beta-migration' if published else 'candidate-migration')
    folder.mkdir()
    with (folder / 'suite.log').open('wb') as log:
        run = subprocess.run([sys.executable, '-B', suite, candidate, '--origin-compiler', baseline,
                              '--output', folder], env=replay_env, cwd=root, stdout=log,
                             stderr=subprocess.STDOUT, timeout=1200)
    if run.returncode:
        raise ValueError('CLI/migration suite failed; see ' + str(folder/'suite.log'))
    raw = folder / 'report.json'
    receipt = json.loads(raw.read_bytes())
    expected = {('0.29', False), ('0.29', True)}
    if not published:
        expected.add(('0.28', False))
    plans = migration_observations(folder, receipt)
    if (receipt['schema'] != 'nex.references030-cli-acceptance/1' or receipt['ok'] is not True
            or receipt['origin_compiler_sha256'] != sdk_archive.digest(baseline)
            or receipt['compiler_sha256'] != sdk_archive.digest(candidate)
            or not expected.issubset(plans) or len(plans) != len(receipt['gates'])
            or sorted(v for _, v in plans) != sorted(g['migration_collision'] for g in receipt['gates'])
            or not all(g['old_rows_preserved'] is True and g['namespace_preserved'] is True for g in receipt['gates'])
            or (not published and not all(g.get('same_version_retry') is True for g in receipt['gates']))
            or not all(receipt[k] is True for k in ('static_components', 'api_projection', 'source_deleted_task_replay'))):
        raise ValueError('incomplete or mismatched migration evidence')
    return {'ok': True, 'suite_sha256': sdk_archive.digest(suite), 'report_sha256': sdk_archive.digest(raw),
            'commands': len(receipt['commands']), 'gates': receipt['gates'],
            'observed_plans': [{'from': lang, 'collision': clash} for lang, clash in sorted(plans)],
            'static_components': True, 'api_projection': True, 'source_deleted_task_replay': True}


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-record', type=Path, required=True, help='committed beta delivery record')
    parser.add_argument('--baseline-archive', type=Path, required=True, help='unaltered published host archive')
    parser.add_argument('--candidate-sdk', type=Path, required=True, help='installed candidate prefix')
    parser.add_argument('--output', type=Path, required=True, help='new directory for receipts and diagnostics')
    args = parser.parse_args()
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    record = json.loads(args.release_record.read_bytes())
    archive = args.baseline_archive.resolve(strict=True)
    if record.get('schema') != 'nex.delivery-record/1' or archive.stat().st_size != record['archive']['bytes']:
        raise ValueError('incorrect baseline release record or archive size')
    # Run helpers with SDK resource discovery even when the calling shell uses a source checkout.
    os.environ.pop('NEX_RESOURCE_DIR', None)
    if sys.platform == 'darwin' and not os.environ.get('SDKROOT'):
        sdkroot = subprocess.check_output(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'],
                                          text=True, timeout=30).strip()
        if not Path(sdkroot).is_absolute() or not Path(sdkroot).is_dir():
            raise ValueError('select the installed macOS SDK with SDKROOT or xcode-select')
        os.environ['SDKROOT'] = sdkroot
    environment = os.environ.copy()
    result = {'schema': 'nex.sdk-source-compatibility/1', 'ok': False,
              'platform': platform.system() + '-' + platform.machine(), 'language': '0.30',
              'release_record_sha256': sdk_archive.digest(args.release_record),
              'baseline_archive_sha256': record['archive']['sha256'],
              'baseline_archive_name': record['archive']['name'], 'checks': {}}
    report = root / 'report.json'
    save(report, result)
    with tempfile.TemporaryDirectory(prefix='beta-sdk-', dir=root) as temp:
        beta_sdk = sdk_archive.restore(archive, Path(temp) / 'restore', record['archive']['sha256'])
        old, result['baseline'] = sdk_identity(beta_sdk, root, environment)
        new, result['candidate'] = sdk_identity(args.candidate_sdk.resolve(strict=True), root, environment)
        if (result['baseline']['toolchain'] != record['toolchain']
                or host_abi(result['baseline']['host']) != host_abi(result['candidate']['host'])):
            raise ValueError('baseline and candidate must match the recorded version and host respectively')
        if old.samefile(new):
            raise ValueError('pass separate baseline and candidate SDKs')
        save(report, result)
        resources = beta_sdk / 'share' / 'nex'
        for name, check, params in (
                ('consumer_cli', check_cli, (old, new, root)),
                ('public_stdlib', check_stdlib, (old, new, root)),
                ('graph_snapshot', check_snapshot, (old, new, root)),
                ('published_examples', check_examples, (old, new, resources/'examples', root)),
                ('published_migration_suite', check_migrations, (old, new, resources, root, environment, True)),
                ('candidate_migration_suite', check_migrations,
                 (old, new, args.candidate_sdk.resolve()/'share'/'nex', root, environment, False))):
            print(name, flush=True)
            data = check(*params)
            if data.get('ok') is not True:
                raise ValueError(name + ' returned an incomplete result')
            result['checks'][name] = data
            save(report, result)
    result['ok'] = True
    save(report, result)
    print(report)


if __name__ == '__main__':
    main()
