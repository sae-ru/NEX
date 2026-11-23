"""Retain the exact ordinary Linux installation for subsequent SDK packaging."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sdk_archive import digest


def export_install(source, destination, commit):
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('expected the full source checkout SHA')
    if destination.exists() or destination == source or source in destination.parents:
        raise ValueError('choose a new output outside the CI build directory')
    paths = {key: source / (key + '.json') for key in ('verification', 'environment', 'source-free-sdk')}
    reports = {key: json.loads(path.read_bytes()) for key, path in paths.items()}
    verified = reports['verification']
    environment = reports['environment']
    installed = reports['source-free-sdk']
    ctest = verified['ctest']
    groups = set(ctest['expected_groups'])
    if (verified.get('ok') is not True or verified['tier'] != 'full'
            or ctest.get('ok') is not True or ctest['ctest_exit_code'] != 0 or not groups
            or groups != set(ctest['observed_groups']) or groups != set(ctest['results']['passed'])
            or ctest['results']['failed'] or ctest['results']['skipped']
            or environment['tier'] != 'full' or environment['selected_groups']):
        raise ValueError('a completed full source qualification is required')
    input_sdk = source / 'sdk'
    if input_sdk.is_symlink() or any(p.is_symlink() or not (p.is_dir() or p.is_file())
                                    for p in input_sdk.rglob('*')):
        raise ValueError('the ordinary Linux SDK must contain regular files and directories')
    compiler = input_sdk / 'bin' / 'nex'
    compiler_sha = digest(compiler)
    isolated = verified['source_free_sdk']
    if (isolated.get('ok') is not True or isolated.get('source_checkout_mounted') is not False
            or installed.get('ok') is not True or installed.get('schema') != 'nex.sdk-acceptance/1'
            or any(h != compiler_sha for h in
                   (verified['sdk_compiler_sha256'], isolated['compiler_sha256'], installed['compiler_sha256']))):
        raise ValueError('the installed compiler must match the completed source-free SDK acceptance')
    arch = environment['target_arch']
    if arch not in ('amd64', 'arm64') or not re.fullmatch(r'sha256:[0-9a-f]{64}', environment['image_id']):
        raise ValueError('missing target architecture or toolchain image identity')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        stage = Path(temporary) / 'artifact'
        stage.mkdir()
        stage.chmod(0o755)
        archive = stage / f'nex-linux-{arch}-installed-{commit[:12]}.tar.gz'
        subprocess.run(['tar', '-C', str(source), '-czf', str(archive), 'sdk'], check=True)
        receipt = {'schema': 'nex.linux-installed-sdk-handoff/1', 'source_commit': commit,
                   'target_arch': arch, 'toolchain_image_id': environment['image_id'],
                   'emulated': environment['emulated'], 'passed_source_groups': len(groups),
                   'version': installed['version'], 'compiler_sha256': compiler_sha,
                   'input_report_sha256': {key: digest(path) for key, path in paths.items()},
                   'archive': {'name': archive.name, 'bytes': archive.stat().st_size, 'sha256': digest(archive)}}
        report = stage / 'handoff.json'
        report.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
        for path in (report, archive):
            path.chmod(0o644)
        stage.rename(destination)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--commit', required=True)
    args = parser.parse_args()
    print(json.dumps(export_install(args.input, args.output, args.commit)))
