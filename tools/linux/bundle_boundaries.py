#!/usr/bin/env python3
"""Reject hostile packaging metadata using an owned ELF/SDK fixture."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--assembler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); root = args.output.resolve(); args.sdk = args.sdk.resolve()
    if root == args.sdk or args.sdk in root.parents or root in args.sdk.parents:
        parser.error('--output must be separate from the input SDK')
    if root.exists():
        parser.error('--output must be new')
    if any(path.is_symlink() for path in args.sdk.rglob('*')):
        parser.error('unbundled SDK input cannot contain symlinks')
    root.mkdir(parents=True)
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('sdk_assembler', args.assembler)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    doctor = json.loads(subprocess.check_output([str(args.sdk / 'bin/nex'), 'doctor', '--json'], text=True))
    malformed = root / 'malformed-sqlite.so'
    shutil.copy2(doctor['native_sqlite_library'], malformed)
    outside = root / 'must-not-be-created.so'
    subprocess.run(['patchelf', '--set-soname', str(outside), str(malformed)], check=True)
    sdk = root / 'input-sdk'; shutil.copytree(args.sdk, sdk, symlinks=True)
    doctor['native_sqlite_library'] = str(malformed)
    # A real ELF fixture returns the chosen SDK's metadata with one malformed
    # library. It is solely a packaging test, never language/compiler evidence.
    source = root / 'doctor.cpp'
    source.write_text('#include <iostream>\nint main(){std::cout << ' + json.dumps(json.dumps(doctor)) + ';}\n')
    subprocess.run([doctor['native_compiler'], str(source), '-o', str(sdk / 'bin/nex')], check=True)
    component = {'name': 'sqlite-fixture', 'version': 'test', 'url': 'https://sqlite.org/',
                 'roots': [str(malformed)], 'license_files': ['/usr/share/doc/libsqlite3-0/copyright']}
    notices = root / 'notices.json'
    notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': [component]}))
    try:
        module.LinuxBundle(sdk, root / 'output-sdk', notices, True).assemble(shutil.which('patchelf'))
    except ValueError as error:
        if 'SONAME must be a filename' not in str(error):
            raise
    else:
        raise RuntimeError('unsafe absolute SONAME was accepted')
    if outside.exists() or outside.is_symlink():
        raise RuntimeError('packager wrote outside its output SDK')
    for name in ('.', '..'):
        invalid = root / ('invalid-' + str(len(name)) + '.json')
        invalid.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': [{**component, 'name': name}]}))
        try:
            module.Bundle(sdk, root / 'unused', invalid)
        except ValueError as error:
            if 'component name' not in str(error):
                raise
        else:
            raise RuntimeError('unsafe component name was accepted')
    report = {'ok': True, 'unsafe_absolute_soname_rejected': True, 'no_outside_write': True,
              'parent_component_names_rejected': True}
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
