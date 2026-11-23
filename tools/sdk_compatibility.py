#!/usr/bin/env python3
"""Run the published beta's 0.30 source and graph contracts on a host SDK."""
import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

import agreement
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


def select_archive(record, archive):
    """Select the recorded archive by bytes so a locally renamed download works."""
    size = archive.stat().st_size
    schema = record.get('schema')
    if schema == 'nex.delivery-record/1':
        version = record['toolchain']
        rows = [(None, record)]
    elif schema == 'nex.multi-platform-release/1':
        version = record['version']
        if (record.get('ok') is not True or record.get('tag') != 'v' + version
                or not re.fullmatch(r'[a-f0-9]{40}', record.get('source_commit', ''))):
            raise ValueError('invalid multi-platform release identity or qualification')
        rows = record['targets'].items()
    else:
        raise ValueError('unknown release record schema')
    candidates = [(target, row) for target, row in rows if row['archive']['bytes'] == size]
    if not candidates:
        raise ValueError('SDK archive size differs from the release record')
    checksum = sdk_archive.digest(archive)
    matches = [(target, row) for target, row in candidates if row['archive']['sha256'] == checksum]
    if len(matches) != 1:
        raise ValueError('SDK archive must match exactly one recorded checksum')
    target, row = matches[0]
    if schema == 'nex.multi-platform-release/1':
        if (row.get('target') != target or row.get('source_commit') != record['source_commit']
                or not row.get('compiler_host') or not re.fullmatch('[a-f0-9]{64}', row.get('compiler_sha256', ''))):
            raise ValueError('invalid platform qualification for ' + target)
    return version, target, row


def check_recorded_bundle(version, target, row, manifest, expected_host):
    if manifest['toolchain'] != version:
        raise ValueError('restored SDK differs from its recorded toolchain version')
    if expected_host is not None and host_abi(manifest['host']) != host_abi(expected_host):
        raise ValueError('baseline and candidate host ABIs differ')
    if target is None:
        return
    host = manifest['host']
    arch = host.split('-', 1)[0]
    if arch == 'aarch64':
        arch = 'arm64'
    if arch == 'x86_64' and '-linux-' in host:
        arch = 'amd64'
    system = manifest['platform']
    compiler = 'bin/nex.exe' if system == 'windows' else 'bin/nex'
    if (target != f'{system}-{arch}' or host != row['compiler_host']
            or manifest['files'][compiler]['sha256'] != row['compiler_sha256']
            or len(manifest['files']) != row['archive']['files']):
        raise ValueError('restored SDK differs from its platform qualification')


@dataclass
class RecordedArchive:
    path: Path
    version: str
    target: str | None
    row: dict
    provenance: dict


def archive_input(record_path, archive):
    raw = record_path.read_bytes()
    version, target, row = select_archive(json.loads(raw), archive)
    provenance = {'record_sha256': hashlib.sha256(raw).hexdigest(), 'archive_name': row['archive']['name'],
                  'archive_sha256': row['archive']['sha256']}
    if target is not None:
        provenance.update(target=target, source_commit=row['source_commit'])
    elif 'SDK_source_commit' in row:
        provenance['source_commit'] = row['SDK_source_commit']
    return RecordedArchive(archive, version, target, row, provenance)


def open_archive(selected, destination, environment, expected_host=None):
    sdk = sdk_archive.restore(selected.path, destination, selected.provenance['archive_sha256'])
    manifest = json.loads((sdk / sdk_archive.MANIFEST).read_bytes())
    check_recorded_bundle(selected.version, selected.target, selected.row, manifest, expected_host)
    compiler, identity = sdk_identity(sdk, destination, environment)
    binary = compiler.relative_to(sdk).as_posix()
    if (identity['toolchain'] != selected.version or identity['host'] != manifest['host']
            or identity['compiler_sha256'] != manifest['files'][binary]['sha256']):
        raise ValueError('running compiler differs from the restored SDK')
    return sdk, compiler, identity


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


def agreement_inputs(folder):
    manifest = folder/'cases.json'
    cases = agreement.select_cases(json.loads(manifest.read_bytes()), '0.30', [])
    return {'manifest_sha256': sdk_archive.digest(manifest),
            'sources': {case['name']: sdk_archive.digest(folder/case['source']) for case in cases}}


def check_release_agreement(candidate, baseline_resources, candidate_resources, root, environment):
    runner = Path(agreement.__file__).resolve()
    compiler_sha = sdk_archive.digest(candidate)
    result = {'ok': False, 'compiler_sha256': compiler_sha, 'runner_sha256': sdk_archive.digest(runner),
              'corpora': {}, 'runs': {}}
    corpora = {'baseline': baseline_resources/'tests/agreement', 'candidate': candidate_resources/'tests/agreement'}
    # Historical SDKs shipped before the agreement corpus was installed.
    if not (corpora['candidate']/'cases.json').is_file():
        if (corpora['baseline']/'cases.json').is_file():
            raise ValueError('candidate SDK is missing the agreement corpus shipped by the baseline')
        corpora['maintained'] = runner.parents[1]/'tests/agreement'
    for role, folder in corpora.items():
        if not (folder/'cases.json').is_file():
            if role == 'maintained':
                raise ValueError('compatibility tool has no maintained agreement corpus')
            result['corpora'][role] = {'shipped': False}
            continue
        inputs = agreement_inputs(folder)
        prior = next((name for name, run in result['runs'].items() if run['inputs'] == inputs), None)
        result['corpora'][role] = {'run': prior or role}
        if prior:
            continue
        output = root/('agreement-' + role)
        output.mkdir()
        with (output/'driver.log').open('wb') as log:
            executed = subprocess.run([sys.executable, '-B', runner, '--compiler', candidate, '--root', folder,
                                       '--language-version', '0.30', '--require-complete', '--output', output],
                                      cwd=root, env=environment, stdout=log, stderr=subprocess.STDOUT)
        if executed.returncode:
            raise ValueError('candidate failed the ' + role + ' corpus; see ' + str(output/'driver.log'))
        raw = output/'report.json'
        receipt = json.loads(raw.read_bytes())
        observed = {case['name']: case['source_sha256'] for case in receipt['cases']}
        if (not receipt['ok'] or not receipt['complete'] or receipt['compiler_sha256'] != compiler_sha
                or receipt['requested_language'] != '0.30' or receipt['manifest_sha256'] != inputs['manifest_sha256']
                or observed != inputs['sources'] or len(receipt['cases']) != len(observed)):
            raise ValueError('incomplete or mismatched agreement report for ' + role)
        result['runs'][role] = {'inputs': inputs, 'coverage': receipt['coverage'],
                                'report_sha256': sdk_archive.digest(raw)}
    result['ok'] = True
    return result


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    tmp.replace(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-record', type=Path, required=True, help='beta delivery record or qualification.json')
    parser.add_argument('--baseline-archive', type=Path, required=True, help='unaltered published host archive')
    candidate = parser.add_mutually_exclusive_group(required=True)
    candidate.add_argument('--candidate-sdk', type=Path, help='installed candidate prefix for development')
    candidate.add_argument('--candidate-archive', type=Path, help='candidate archive for release qualification')
    parser.add_argument('--candidate-release-record', type=Path, help='release record for the candidate archive')
    parser.add_argument('--output', type=Path, required=True, help='new directory for receipts and diagnostics')
    args = parser.parse_args()
    if bool(args.candidate_archive) != bool(args.candidate_release_record):
        parser.error('--candidate-archive and --candidate-release-record must be supplied together')
    baseline = archive_input(args.release_record, args.baseline_archive)
    proposal = None
    if args.candidate_archive:
        proposal = archive_input(args.candidate_release_record, args.candidate_archive)
        if proposal.provenance['archive_sha256'] == baseline.provenance['archive_sha256']:
            parser.error('the baseline and candidate archives contain identical bytes')
        if not os.environ.get('NEX_TSC') or os.environ.get('NEX_SKIP_TYPESCRIPT'):
            parser.error('archive comparison requires NEX_TSC with TypeScript execution enabled')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
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
              'release_record_sha256': baseline.provenance['record_sha256'],
              'baseline_archive_sha256': baseline.provenance['archive_sha256'],
              'baseline_archive_name': baseline.provenance['archive_name'], 'checks': {}}
    if baseline.target is not None:
        result['baseline_target'] = baseline.target
    if 'source_commit' in baseline.provenance:
        result['baseline_source_commit'] = baseline.provenance['source_commit']
    if proposal:
        result['candidate_archive'] = proposal.provenance
    report = root / 'report.json'
    save(report, result)
    with tempfile.TemporaryDirectory(prefix='compat-sdk-', dir=root) as temp:
        if proposal:
            candidate_sdk, new, result['candidate'] = open_archive(
                proposal, Path(temp)/'candidate', environment)
        else:
            candidate_sdk = args.candidate_sdk.resolve(strict=True)
            new, result['candidate'] = sdk_identity(candidate_sdk, root, environment)
        beta_sdk, old, result['baseline'] = open_archive(
            baseline, Path(temp)/'baseline', environment, result['candidate']['host'])
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
                 (old, new, candidate_sdk/'share'/'nex', root, environment, False))):
            print(name, flush=True)
            data = check(*params)
            if data.get('ok') is not True:
                raise ValueError(name + ' returned an incomplete result')
            result['checks'][name] = data
            save(report, result)
        if proposal:
            print('backend_agreement', flush=True)
            result['checks']['backend_agreement'] = check_release_agreement(
                new, resources, candidate_sdk/'share'/'nex', root, environment)
    # check_examples creates these native build products in this new run directory.
    # Keep them on failures so intermediate code remains available for diagnosis.
    examples_build = root/'build'
    if examples_build.is_dir():
        try:
            shutil.rmtree(examples_build)
        except OSError as error:
            result['retained_example_build'] = str(error)
    result['ok'] = True
    save(report, result)
    print(report)


if __name__ == '__main__':
    main()
