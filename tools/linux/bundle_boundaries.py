#!/usr/bin/env python3
"""Check relocated multicall ELF images and reject hostile packaging metadata."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys



def check_elf_aliases(module, sdk, root, compiler):
    original = root / 'original alias inputs'; original.mkdir()
    library_source = original / 'helper.c'
    library_source.write_text('int alias_value(void){return 42;}\n')
    library = original / 'libalias_fixture.so'
    subprocess.run([compiler, '-x', 'c', '-shared', '-fPIC', str(library_source), '-Wl,-soname,libalias_fixture.so', '-o', str(library)], check=True)
    executable_source = original / 'dispatcher.c'
    executable_source.write_text('#include <stdio.h>\n#include <string.h>\nextern int alias_value(void);\nint main(int argc,char **argv){const char *base=strrchr(argv[0],47);printf("%s:%d\\n",base?base+1:argv[0],alias_value());return 0;}\n')
    executable = original / 'dispatcher'
    subprocess.run([compiler, '-x', 'c', str(executable_source), '-L'+str(original), '-lalias_fixture', '-Xlinker', '-rpath', '-Xlinker', str(original), '-o', str(executable)], check=True)
    notice = root / 'alias-notices.json'; license_file = root / 'alias-fixture-NOTICE.txt'
    license_file.write_text('Locally generated ELF relocation test fixture.\n')
    notice.write_text(json.dumps({'schema':'nex.sdk-notices/1','components':[{'name':'alias-fixture','version':'test','url':'https://example.invalid/nex-local-fixture','roots':[str(root)],'license_files':[str(license_file)]}]}))
    output = root / 'alias SDK % 🧠'
    collector = module.LinuxBundle(sdk, output, notice)
    collector.environment = dict(os.environ)
    for key in ('LD_LIBRARY_PATH','LD_PRELOAD'):
        collector.environment.pop(key, None)
    destinations = [output/'libexec/bin/ld.lld', output/'libexec/deeper/bin/wasm-ld']
    for alias, destination in zip(('ld.lld','wasm-ld'), destinations):
        path = original/alias; path.symlink_to(executable.name)
        collector.external(path, destination); collector.collect_elf(path, destination)
        collector.collect_elf(path, destination)  # repeated traversal is idempotent
    collector.relocate_elf(shutil.which('patchelf'))
    retained = root/'retained-alias-inputs'; original.rename(retained)
    results = []
    for destination in destinations:
        value = subprocess.check_output([str(destination)], env=collector.environment, text=True)
        if value != destination.name+':42\n':
            raise RuntimeError('multicall argv[0] or relocated dependency failed: '+repr(value))
        results.append({'name':destination.name,'stdout':value})
    other = retained/'different-dispatcher'; shutil.copy2(retained/'dispatcher', other)
    with other.open('ab') as stream: stream.write(b'different source')
    before = module.sha256(destinations[0])
    for action, expected in [(lambda: collector.external(other,destinations[0]),'bundle destination collision'),
                             (lambda: collector.collect_elf(other,destinations[0]),'duplicate ELF image destination')]:
        try: action()
        except ValueError as error:
            if expected not in str(error): raise
        else: raise RuntimeError('different ELF source was accepted at an occupied destination')
    if module.sha256(destinations[0]) != before:
        raise RuntimeError('rejected ELF collision changed the original destination')
    return {'ok':True,'two_aliases_same_source':True,'different_destination_depths':True,
            'all_dependency_copies_relocated':True,'original_dependency_directory_absent':not original.exists(),
            'different_source_collisions_rejected':True,'rejected_destinations_unchanged':True,'executions':results}


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
    aliases = check_elf_aliases(module, args.sdk, root, doctor['native_compiler'])
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
    report = {'ok': True, 'elf_aliases': aliases, 'unsafe_absolute_soname_rejected': True, 'no_outside_write': True,
              'parent_component_names_rejected': True}
    (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
