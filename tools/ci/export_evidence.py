#!/usr/bin/env python3
"""Export selected CI diagnostics without traversing test projects or probes."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


def export_evidence(source, output):
    source = Path(source).resolve()
    output = Path(output).resolve()
    if not source.is_dir():
        raise ValueError('input must be a CI output directory')
    if output == source or source in output.parents:
        raise ValueError('export must be outside its input directory')
    output.mkdir(exist_ok=False, parents=True)
    output.chmod(0o755)
    selected = set()

    def direct(directory, suffixes=None):
        if not directory.is_dir():
            return
        for path in directory.iterdir():
            if path.is_file() and (suffixes is None or path.suffix in suffixes):
                selected.add(path)

    direct(source, {'.json', '.log'})
    for relative in ('CMakeCache.txt', 'CMakeFiles/CMakeConfigureLog.yaml'):
        path = source / relative
        if path.is_file():
            selected.add(path)
    for tier in ('ci-core', 'ci-full', 'ci-selected'):
        direct(source / tier)
    sdk = source / 'sdk-acceptance'
    if sdk.is_dir():
        for attempt in sdk.iterdir():
            if not re.fullmatch(r'[0-9a-f]{32}', attempt.name):
                continue
            workflow = attempt / 'workflow'
            report = workflow / 'report.json'
            if report.is_file():
                selected.add(report)
            # These are the captured commands, not the projects they execute.
            direct(workflow / 'logs')

    files = []
    for path in sorted(selected):
        relative = path.relative_to(source)
        if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != source):
            raise ValueError('diagnostic paths must be regular owned files: ' + str(relative))
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        for parent in (destination.parent, *destination.parent.parents):
            if parent == output.parent:
                break
            parent.chmod(0o755)
        shutil.copyfile(path, destination)
        destination.chmod(0o644)
        digest = hashlib.sha256()
        with destination.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                digest.update(block)
        files.append({'path':relative.as_posix(), 'bytes':destination.stat().st_size, 'sha256':digest.hexdigest()})
    report = {'schema':'nex.ci-evidence-export/1', 'ok':True, 'input':str(source),
              'output':str(output), 'files':files, 'compiler_tests_executed':False}
    receipt = output / 'evidence-export.json'
    receipt.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    receipt.chmod(0o644)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = export_evidence(args.input, args.output)
    print(json.dumps({'ok':True, 'files':len(report['files']), 'output':report['output']}))
