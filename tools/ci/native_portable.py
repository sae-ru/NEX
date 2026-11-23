"""Service-branch runner for the immutable NEX Linux x86-64 release input."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import shutil
import subprocess
import sys
import tarfile
from zipfile import ZipFile

SOURCE = '584715e45d05be53e5a8eb967edcd4d5ab7fc1b5'
SOURCE_RUN = 45134900040
REPOSITORY = 'sae-ru/NEX'
ROOT = Path(__file__).resolve().parents[2]
PIN = ROOT / 'pinned-sdk'
WORK = Path(os.environ.get('RUNNER_TEMP', '/tmp')) / 'native-portable'
DELIVERY = WORK / 'delivery'
EVIDENCE = WORK / 'evidence'
RAW = 'assembled-tree.tar.gz'
IMAGE = 'clean-runtime.docker.tar.gz'
sys.path[:0] = [str(PIN / 'tools'), str(PIN / 'tools/linux')]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')
    path.chmod(0o644)


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def command(*args, **kwargs):
    return subprocess.run([str(arg) for arg in args], check=True, **kwargs)


def text(*args):
    return command(*args, capture_output=True, text=True).stdout.strip()


def api(path):
    return json.loads(text('gh', 'api', 'repos/' + REPOSITORY + '/' + path))


def download_phase(kind, destination):
    run = int(os.environ['GITHUB_RUN_ID'])
    attempt = int(os.environ['GITHUB_RUN_ATTEMPT'])
    prefix = f'native-portable-{kind}-{run}-'
    rows = api(f'actions/runs/{run}/artifacts?per_page=100')['artifacts']
    values = [int(row['name'][len(prefix):]) for row in rows if not row['expired'] and
              row['name'].startswith(prefix) and row['name'][len(prefix):].isdigit()]
    valid = [value for value in values if 0 < value <= attempt]
    require(valid, 'no completed artifact from this run for ' + kind)
    # A failed-job rerun can reuse a successful upstream job from an earlier attempt.
    command('gh', 'run', 'download', run, '-n', prefix + str(max(valid)), '-D', destination)


def copy_zip_file(archive, name, target):
    require(archive.namelist().count(name) == 1, 'missing/duplicate member ' + name)
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(name) as source, target.open('xb') as dest:
        shutil.copyfileobj(source, dest)


def native_host():
    require(platform.machine() == 'x86_64' and text('docker', 'version', '--format', '{{.Server.Arch}}') == 'amd64',
            'qualification requires a native Linux x86-64 runner')
    require(text('git', '-c', 'safe.directory=' + str(PIN), '-C', PIN, 'rev-parse', 'HEAD') == SOURCE, 'SDK checkout changed')
    require(os.environ.get('GITHUB_REPOSITORY', '').lower() == REPOSITORY.lower(), 'different Actions repository')
    return {'platform': platform.platform(), 'machine': platform.machine(), 'native': True,
            'run_id': int(os.environ['GITHUB_RUN_ID']), 'run_attempt': int(os.environ['GITHUB_RUN_ATTEMPT']),
            'workflow_sha': os.environ['GITHUB_SHA'], 'source_sha': SOURCE}


def import_ordinary():
    import ctest_report
    import sdk_acceptance
    run = api(f'actions/runs/{SOURCE_RUN}')
    require(run['head_sha'] == SOURCE and run['path'] == '.github/workflows/full.yml' and
            run['status'] == 'completed' and run['conclusion'] == 'success', 'source run has not passed on the pinned SHA')
    artifacts = api(f'actions/runs/{SOURCE_RUN}/artifacts')['artifacts']
    receipts = WORK / 'source-receipts'
    receipts.mkdir()
    source = f'linux-full-{SOURCE_RUN}-{run["run_attempt"]}'
    installed = f'linux-amd64-installed-{SOURCE}-{run["run_attempt"]}'
    checksums = {}
    for name, kind in [(source, 'diagnostics'), (installed, 'installed')]:
        matches = [row for row in artifacts if row['name'] == name and not row['expired']]
        require(len(matches) == 1, 'expected exactly one source artifact ' + name)
        item = matches[0]
        target = WORK / (kind + '.zip')
        with target.open('xb') as output:
            command('gh', 'api', f'repos/{REPOSITORY}/actions/artifacts/{item["id"]}/zip', stdout=output)
        checksums[name] = sha(target)
        require(item['digest'] == 'sha256:' + checksums[name], 'GitHub artifact digest mismatch: ' + name)
    archive_name = f'nex-linux-amd64-installed-{SOURCE[:12]}.tar.gz'
    with ZipFile(WORK / 'installed.zip') as archive:
        copy_zip_file(archive, 'handoff.json', receipts / 'handoff.json')
        copy_zip_file(archive, archive_name, WORK / archive_name)
    handoff = read(receipts / 'handoff.json')
    with ZipFile(WORK / 'diagnostics.zip') as archive:
        for name in ['verification.json', 'environment.json', 'source-free-sdk.json', 'ci-full/registry.stdout',
                     'ci-full/results.xml', 'ci-full/ctest-receipt.json']:
            copy_zip_file(archive, name, receipts / name)
    require(handoff['schema'] == 'nex.linux-installed-sdk-handoff/1' and
            handoff['source_commit'] == SOURCE and handoff['target_arch'] == 'amd64' and not handoff['emulated'],
            'unexpected source SDK handoff')
    for key in ('environment', 'verification', 'source-free-sdk'):
        require(sha(receipts / (key + '.json')) == handoff['input_report_sha256'][key], 'CI report changed: ' + key)
    env = read(receipts / 'environment.json')
    verify = read(receipts / 'verification.json')
    ordinary = read(receipts / 'source-free-sdk.json')
    sdk_acceptance.validate_completed_report(ordinary)
    rr = receipts / 'ci-full'
    ctest = ctest_report.inspect_files(rr / 'registry.stdout', rr / 'results.xml', ctest_exit_code=0)
    require(env['image_id'] == handoff['toolchain_image_id'] and env['target_arch'] == 'amd64' and not env['emulated']
            and env['tier'] == 'full' and not env['selected_groups'] and verify['ok'] and ctest['ok']
            and ctest == verify['ctest'] == read(rr / 'ctest-receipt.json')
            and len(ctest['observed_groups']) == handoff['passed_source_groups'], 'native source CI evidence differs')
    tar = WORK / archive_name
    require(handoff['archive']['name'] == tar.name and sha(tar) == handoff['archive']['sha256'] and
            tar.stat().st_size == handoff['archive']['bytes'], 'ordinary SDK transport changed')
    with tarfile.open(tar, 'r:gz') as archive:
        seen = set()
        for entry in archive:
            path = PurePosixPath(entry.name)
            require(path.parts and path.parts[0] == 'sdk' and '..' not in path.parts and path not in seen and
                    (entry.isfile() or entry.isdir()), 'invalid ordinary SDK member')
            seen.add(path)
        archive.extractall(WORK, filter='data')
    compiler = sha(WORK / 'sdk/bin/nex')
    require(compiler == handoff['compiler_sha256'] == verify['sdk_compiler_sha256'] == ordinary['compiler_sha256']
            == verify['source_free_sdk']['compiler_sha256'], 'installed SDK is not the accepted native input')
    result = {'ok': True, 'source_commit': SOURCE, 'source_run': SOURCE_RUN, 'source_url': run['html_url'],
              'native_source_compiler_sha256': verify['compiler_sha256'], 'installed_compiler_sha256': compiler,
              'source_groups': len(ctest['observed_groups']), 'ordinary_phases': len(ordinary['phases']),
              'builder_image': env['image_id'], 'native': True, 'github_artifacts': checksums}
    write(DELIVERY / 'native-input-receipt.json', result)
    shutil.copyfile(receipts / 'handoff.json', DELIVERY / 'handoff.json')
    return result, ordinary['doctor']


def run_container(image, mounts, args, log, workdir='/tmp'):
    from nex_docker_mount import mount
    argv = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none']
    for host, guest, readonly in mounts:
        argv.extend(mount(host, guest, readonly))
    argv += ['--workdir', workdir, image, *args]
    write(log.with_suffix('.command.json'), {'argv': list(map(str, argv))})
    with log.open('wb') as output:
        command(*argv, stdout=output, stderr=subprocess.STDOUT)


def image_record(tag):
    raw, = json.loads(text('docker', 'image', 'inspect', tag))
    require(raw['Os'] == 'linux' and raw['Architecture'] == 'amd64', 'incorrect image architecture')
    return {'id': raw['Id'], 'layers': raw['RootFS']['Layers'], 'config': raw['Config']}


def prepare_images():
    from check import prepare_image
    from debugger_packages import prepare
    lock = PIN / 'tools/linux/debugger-packages.json'
    inputs = prepare(read(lock), ROOT / 'build/linux-debugger-packages', 'amd64')
    # Restore the source workflow's exact cache path, then stage only files
    # whose sizes and SHA-256 the immutable SDK lock has verified.
    target = PIN / 'build/linux-debugger-packages/amd64'
    target.mkdir(parents=True, exist_ok=True)
    for package in inputs['packages']:
        source = Path(package['path'])
        shutil.copy2(source, target / source.name)
    builder = 'nex-portable-builder:' + SOURCE[:12]
    clean = 'nex-portable-clean:' + SOURCE[:12]
    common = ['docker', 'build', '--platform', 'linux/amd64', '--progress', 'plain']
    prepare_image([*common, '-f', str(PIN / 'tools/linux/Dockerfile'), '-t', builder, str(PIN)], EVIDENCE / 'builder-image.log')
    prepare_image([*common, '--build-arg', 'TOOLCHAIN_IMAGE=' + builder, '-f', str(PIN / 'tools/linux/BundleRuntime.Dockerfile'),
                   '-t', clean, str(PIN)], EVIDENCE / 'runtime-image.log')
    return builder, clean


def assemble():
    import sdk_archive
    host = native_host()
    DELIVERY.mkdir(parents=True)
    receipt, observed_doctor = import_ordinary()
    builder, clean = prepare_images()
    builder_record, clean_record = image_record(builder), image_record(clean)
    sdk = WORK / 'sdk'
    doctor_log = EVIDENCE / 'doctor.log'
    run_container(builder_record['id'], [(sdk, '/sdk', True)], ['/sdk/bin/nex', 'doctor', '--json'], doctor_log)
    doctor = read(doctor_log)
    require(all(doctor[k] == observed_doctor[k] for k in ('version', 'language', 'host', 'llvm', 'verifier_version')),
            'packaging tools do not match the verified compiler configuration')
    notices = {'schema': 'nex.sdk-notices/1', 'components': [{'name': 'z3-official', 'version': '5.3.1',
        'url': 'https://github.com/Z3Prover/z3/releases/tag/z3-5.3.1', 'roots': ['/opt/z3'],
        'license_files': ['/opt/z3/LICENSE.txt']}]}
    packing = WORK / 'packing'
    write(packing / 'notices.json', notices)
    run_container(builder_record['id'], [(sdk, '/sdk', True), (PIN / 'tools/sdk_bundle.py', '/assembler.py', True),
                  (packing, '/work', False)], ['python3', '-B', '/assembler.py', '--sdk', '/sdk', '--output',
                  '/work/stage', '--notices', '/work/notices.json', '--dpkg-notices'], EVIDENCE / 'assemble.log', '/work')
    assembled = packing / 'assembled'; (packing / 'stage').rename(assembled)
    bundle = read(assembled / 'share/nex/sdk-bundle.json')
    name = 'nex-sdk-' + bundle['toolchain'] + '-linux-amd64-development'
    record = sdk_archive.create(assembled, DELIVERY / (name + '.tar.gz'), name)
    record['name'] = Path(record.pop('path')).name
    require(sha(sdk / 'bin/nex') == receipt['installed_compiler_sha256'], 'ordinary compiler changed during assembly')
    # The moved job receives the assembled tree independently of the normalized release archive.
    command('tar', '-C', packing, '-czf', DELIVERY / RAW, 'assembled')
    with gzip.open(DELIVERY / IMAGE, 'wb', compresslevel=1) as stream:
        process = subprocess.Popen(['docker', 'save', clean], stdout=subprocess.PIPE)
        with process.stdout as source:
            shutil.copyfileobj(source, stream)
        require(process.wait() == 0, 'clean runtime image export failed')
    (DELIVERY / (record['name'] + '.sha256')).write_text(record['sha256'] + '  ' + record['name'] + '\n')
    result = {'schema': 'nex.native-portable-assembly/1', 'ok': True, 'source_commit': SOURCE,
              'toolchain': bundle['toolchain'], 'target': 'linux-amd64', 'hardware': host,
              'input_compiler_sha256': receipt['installed_compiler_sha256'],
              'packaged_compiler_sha256': sha(assembled / 'bin/nex'),
              'portable_manifest_sha256': sha(assembled / 'share/nex/sdk-bundle.json'),
              'assembler_sha256': sha(PIN / 'tools/sdk_bundle.py'), 'archive': record,
              'native_handoff_sha256': sha(DELIVERY / 'handoff.json'),
              'native_input_receipt_sha256': sha(DELIVERY / 'native-input-receipt.json'),
              'raw_transport_sha256': sha(DELIVERY / RAW), 'clean_transport_sha256': sha(DELIVERY / IMAGE),
              'builder_image': builder_record['id'], 'clean_image': clean_record, 'clean_tag': clean}
    write(DELIVERY / 'assembly.json', result)
    for filename in ('assembly.json', 'handoff.json', 'native-input-receipt.json'):
        shutil.copyfile(DELIVERY / filename, EVIDENCE / filename)


def accept(kind, scratch):
    import sdk_archive
    import sdk_acceptance
    host = native_host()
    assembly = read(DELIVERY / 'assembly.json')
    require(assembly['ok'] and assembly['source_commit'] == SOURCE and
            assembly['hardware']['workflow_sha'] == host['workflow_sha'] and
            assembly['hardware']['run_id'] == host['run_id'], 'assembly is from another run or input')
    require(sha(DELIVERY / IMAGE) == assembly['clean_transport_sha256'], 'clean runtime transport changed')
    command('docker', 'load', '-i', DELIVERY / IMAGE)
    actual = image_record(assembly['clean_tag'])
    require(all(actual[k] == assembly['clean_image'][k] for k in ('layers', 'config')), 'clean runtime changed in transit')
    archive = assembly['archive']
    if kind == 'moved':
        require(sha(DELIVERY / RAW) == assembly['raw_transport_sha256'], 'assembled tree transport changed')
        with tarfile.open(DELIVERY / RAW, 'r:gz') as data:
            data.extractall(scratch, filter='data')
        sdk = scratch / 'moved SDK, % 🧠'
        (scratch / 'assembled').rename(sdk)
    else:
        sdk = sdk_archive.restore(DELIVERY / archive['name'], scratch / 'restored SDK, % 🧠', archive['sha256'])
    compiler = sha(sdk / 'bin/nex')
    require(compiler == assembly['packaged_compiler_sha256'] and
            sha(sdk / 'share/nex/sdk-bundle.json') == assembly['portable_manifest_sha256'], 'staged candidate differs')
    target = '/moved SDK, % 🧠' if kind == 'moved' else '/restored SDK, % 🧠'
    scope = 'clean-acceptance' if kind == 'moved' else 'archive-acceptance'
    case = scratch / scope; case.mkdir()
    resultdir = EVIDENCE / scope / 'report'; resultdir.mkdir(parents=True)
    try:
        run_container(actual['id'], [(sdk, target, True), (case, '/evidence', False)], ['python3', '-B',
                target + '/share/nex/tools/linux/bundle.py', '--verify', target, '--output', '/evidence/report'],
                EVIDENCE / (kind + '.log'), '/evidence')
    finally:
        live = case / 'report'
        for relative in ('workflow/report.json','verification.json'):
            if (live/relative).is_file():
                dest = resultdir / relative; dest.parent.mkdir(exist_ok=True)
                shutil.copyfile(live / relative, dest); dest.chmod(0o644)
        progress = live / 'workflow/report.json'
        if progress.is_file():
            for item in read(progress)['commands']:
                if item.get('status') != 'failed':
                    continue
                for stream in ('stdout', 'stderr'):
                    orig = Path(item[stream]).relative_to('/evidence/report')
                    if (live / orig).is_file():
                        copy = resultdir / orig; copy.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(live / orig, copy); copy.chmod(0o644)
    workflow = read(resultdir / 'workflow/report.json'); wrapper = read(resultdir / 'verification.json')
    sdk_acceptance.validate_completed_report(workflow)
    require(wrapper['ok'] and wrapper['compiler_sha256'] == workflow['compiler_sha256'] == compiler and
            wrapper['files_verified'] == archive['files_in_inventory'] and not wrapper['source_checkout_mounted']
            and not wrapper['host_llvm_mlir_z3_present'], 'portable acceptance mismatch')
    proof = {'ok': True, 'source_commit': SOURCE, 'workflow_sha': host['workflow_sha'], 'run_id': host['run_id'],
             'kind': kind, 'compiler_sha256': compiler, 'archive_sha256': archive['sha256'],
             'report_sha256': sha(resultdir / 'workflow/report.json'), 'wrapper_sha256': sha(resultdir / 'verification.json'),
             'phases': len(workflow['phases']), 'commands': len(workflow['commands']),
             'native': True, 'engine_image': actual['id'], 'files_verified': wrapper['files_verified']}
    write(EVIDENCE / (kind + '.json'), proof)


def finalize():
    import sdk_acceptance
    host = native_host()
    assembly = read(WORK / 'assembly/assembly.json')
    receipt = read(WORK / 'assembly/native-input-receipt.json')
    require(assembly['ok'] and receipt['ok'] and assembly['source_commit'] == receipt['source_commit'] == SOURCE
            and assembly['hardware']['workflow_sha'] == host['workflow_sha']
            and assembly['hardware']['run_id'] == host['run_id'], 'assembly and source identities differ')
    results = {}
    for kind, scope in [('moved','clean-acceptance'), ('restored','archive-acceptance')]:
        case = WORK / kind
        proof = read(case / (kind + '.json'))
        path = case / scope / 'report'
        workflow = read(path / 'workflow/report.json')
        wrapper = read(path / 'verification.json')
        sdk_acceptance.validate_completed_report(workflow)
        require(proof['ok'] and proof['native'] and proof['kind'] == kind and proof['source_commit'] == SOURCE
                and proof['workflow_sha'] == host['workflow_sha'] and proof['run_id'] == host['run_id']
                and wrapper['ok'] and not wrapper['source_checkout_mounted'] and not wrapper['host_llvm_mlir_z3_present']
                and proof['phases'] == len(workflow['phases']) and proof['commands'] == len(workflow['commands'])
                and proof['compiler_sha256'] == wrapper['compiler_sha256'] == workflow['compiler_sha256'] == assembly['packaged_compiler_sha256']
                and proof['archive_sha256'] == assembly['archive']['sha256']
                and proof['files_verified'] == assembly['archive']['files_in_inventory']
                and sha(path / 'workflow/report.json') == proof['report_sha256']
                and sha(path / 'verification.json') == proof['wrapper_sha256'], 'portable acceptance differs: ' + kind)
        results[kind] = proof
        shutil.copytree(path, EVIDENCE / scope / 'report')
    for name, key in [('handoff.json', 'native_handoff_sha256'), ('native-input-receipt.json','native_input_receipt_sha256')]:
        require(sha(WORK / 'assembly' / name) == assembly[key], 'source handoff changed')
        shutil.copyfile(WORK / 'assembly' / name, EVIDENCE / name)
    shutil.copyfile(WORK / 'assembly/assembly.json', EVIDENCE / 'assembly.json')
    final = {'ok': True, 'source_commit': SOURCE, 'toolchain': assembly['toolchain'], 'target': 'linux-amd64',
             'native_handoff_sha256': assembly['native_handoff_sha256'],
             'native_input_receipt_sha256': assembly['native_input_receipt_sha256'],
             'input_compiler_sha256': receipt['installed_compiler_sha256'],
             'packaged_compiler_sha256': assembly['packaged_compiler_sha256'],
             'portable_manifest_sha256': assembly['portable_manifest_sha256'],
             'archive': {**assembly['archive'], 'path': assembly['archive']['name']}, **results,
             'execution': {'source_native': True, 'source_run_id': SOURCE_RUN,
                           'source_compiler_sha256': receipt['native_source_compiler_sha256'],
                           'source_groups': receipt['source_groups'], 'ordinary_runtime_phases': receipt['ordinary_phases'],
                           'source_image': receipt['builder_image'], 'portable_native': True, 'emulated': False,
                           'architecture': 'amd64', 'runner': 'ubuntu-24.04', 'packager_image': assembly['builder_image'],
                           'runtime_image': results['restored']['engine_image'], 'portable_run_id': host['run_id'],
                           'workflow_sha': host['workflow_sha'], 'sdk_source_sha': SOURCE}}
    write(EVIDENCE / 'verification.json', final)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['assemble','moved','restored','finalize','download'])
    parser.add_argument('--scratch', type=Path)
    parser.add_argument('--artifact', choices=['assembly','runtime','tree','sdk','moved','restored'])
    parser.add_argument('--into', type=Path)
    options = parser.parse_args()
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    if options.action == 'assemble':
        assemble()
    elif options.action == 'download':
        require(options.artifact and options.into, 'both artifact and destination are required')
        download_phase(options.artifact, options.into)
    elif options.action == 'finalize':
        finalize()
    else:
        require(options.scratch and options.scratch.is_dir(), 'a new scratch volume is required')
        accept(options.action, options.scratch)
