#!/usr/bin/env python3
"""Assemble an immutable, versioned SDK release from a verified bundle archive."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys

def digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()

def load(path):
    try:return json.loads(Path(path).read_text(encoding='utf-8'))
    except Exception as error:raise SystemExit('invalid JSON: '+str(path)+': '+str(error))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle',required=True,type=Path)
    parser.add_argument('--archive',required=True,type=Path)
    parser.add_argument('--acceptance-report',required=True,type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--notices',required=True,type=Path)
    arguments=parser.parse_args()
    bundle,archive,output=arguments.bundle.resolve(),arguments.archive.resolve(),arguments.output
    manifest=load(bundle/'share/nex/sdk-bundle.json')
    acceptance=load(arguments.acceptance_report)
    notices=arguments.notices.resolve()
    if manifest.get('schema')!='nex.sdk-bundle/1' or manifest.get('ok') is not True:raise SystemExit('bundle manifest is not a successful nex.sdk-bundle/1')
    if acceptance.get('schema')!='nex.sdk-acceptance/1' or acceptance.get('ok') is not True:raise SystemExit('acceptance report is not successful')
    if acceptance.get('version')!=manifest.get('toolchain') or acceptance.get('language')!=manifest.get('language'):raise SystemExit('acceptance identity differs from bundle')
    if not archive.is_file() or not notices.is_file():raise SystemExit('archive or notices missing')
    if output.exists():raise SystemExit('release output must be new')
    version=manifest.get('toolchain');platform=manifest.get('platform') or manifest.get('host') or 'unknown'
    name='nex-'+version+'-'+platform
    output.mkdir(parents=True)
    release=output/name
    release.mkdir()
    shutil.copyfile(archive,release/archive.name)
    shutil.copyfile(notices,release/'THIRD_PARTY_NOTICES.json')
    acceptance_copy=release/'acceptance.json'
    shutil.copyfile(arguments.acceptance_report,acceptance_copy)
    report={'schema':'nex.sdk-release/1','ok':True,'immutable':True,'name':name,
        'version':version,'language':manifest.get('language'),'platform':platform,
        'bundle_manifest_sha256':digest(bundle/'share/nex/sdk-bundle.json'),
        'archive':archive.name,'archive_sha256':digest(release/archive.name),
        'archive_bytes':(release/archive.name).stat().st_size,
        'notices_sha256':digest(release/'THIRD_PARTY_NOTICES.json'),
        'acceptance_sha256':digest(acceptance_copy),
        'acceptance_phases':len(acceptance.get('phases',[])),
        'browser_build':acceptance.get('browser_build') if acceptance.get('browser_build') is not None else bool(acceptance.get('evidence',{}).get('browser_build')),
        'live_debugger':acceptance.get('live_debugger') if acceptance.get('live_debugger') is not None else bool(acceptance.get('evidence',{}).get('live_debugger'))}
    (release/'release.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    (release/'SHA256SUMS').write_text(''.join(digest(release/name)+'  '+name+'\n' for name in ('release.json','acceptance.json','THIRD_PARTY_NOTICES.json',archive.name)),encoding='utf-8')
    for path in release.iterdir():os.chmod(path,0o444)
    os.chmod(release,0o555);os.chmod(output,0o555)
    print(json.dumps(report,sort_keys=True))
    return 0

if __name__=='__main__':sys.exit(main())
