#!/usr/bin/env python3
"""Package a compiler-produced native application; never execute its entry point."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

from sdk_bundle import Bundle, LinuxBundle, elf_image, macho, run, sha256


class ApplicationInputs:
    def external(self, source, destination):
        source = source.resolve(strict=True)
        if self.sdk_inventory and self.sdk in source.parents:
            relative = str(source.relative_to(self.sdk))
            record = self.sdk_inventory.get(relative)
            if not record or not record.get('component') or record.get('sha256') != sha256(source):
                raise ValueError('SDK library integrity/provenance mismatch: ' + relative)
        super().external(source, destination)


class MacApplication(ApplicationInputs, Bundle):
    pass


class LinuxApplication(ApplicationInputs, LinuxBundle):
    pass


def notices_for_sdk(sdk):
    path = sdk / 'share/nex/sdk-bundle.json'
    if not path.exists():
        return [], {}
    report = json.loads(path.read_text())
    if report.get('schema') != 'nex.sdk-bundle/1' or report.get('ok') is not True:
        raise ValueError('invalid SDK bundle manifest')
    inventory = report['files']
    components = []
    for component in report['components']:
        roots = []
        for relative, record in inventory.items():
            if record.get('component') != component['name']:
                continue
            candidate = (sdk / relative).resolve(strict=True)
            if sdk not in candidate.parents:
                raise ValueError('SDK component path escapes its prefix')
            roots.append(str(candidate))
        if not roots:
            continue
        licenses = []
        for record in component['license_files']:
            source = (sdk / record['path']).resolve(strict=True)
            if sdk not in source.parents or sha256(source) != record['sha256']:
                raise ValueError('SDK notice integrity mismatch')
            licenses.append(str(source))
        components.append({'name': component['name'], 'version': component['version'],
                           'url': component['url'], 'roots': roots, 'license_files': licenses})
    return components, inventory


def assemble(request, output, notices=None, dpkg_notices=False, patchelf='patchelf'):
    if dpkg_notices and platform.system() != 'Linux':
        raise ValueError('--dpkg-notices is Linux-only')
    if request.get('schema') != 'nex.application-request/1':
        raise ValueError('expected nex.application-request/1')
    binary = Path(request['binary']).resolve(strict=True)
    if sha256(binary) != request['binary_sha256']:
        raise ValueError('application binary changed after compilation')
    sdk = Path(request['sdk_root']).resolve(strict=True)
    output = Path(os.path.abspath(output))
    if os.path.lexists(output):
        raise ValueError('application output must be a new directory')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '.stage-', dir=output.parent)).resolve(strict=True)
    try:
        components, sdk_inventory = notices_for_sdk(sdk)
        if notices:
            declared = json.loads(notices.read_text())
            if declared.get('schema') != 'nex.sdk-notices/1':
                raise ValueError('expected nex.sdk-notices/1')
            for component in declared['components']:
                item = dict(component)
                for key in ('roots', 'license_files'):
                    item[key] = [str((notices.parent / name).resolve(strict=True)) for name in component[key]]
                components.append(item)
        selection = stage / '.notices.json'
        selection.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': components}))
        system = platform.system()
        if system == 'Darwin' and macho(binary):
            collector = MacApplication(sdk, stage, selection, dpkg_notices, allow_empty=True)
        elif system == 'Linux' and elf_image(binary):
            if ':' in str(output) or ':' in str(stage):
                raise ValueError('ELF package paths cannot contain a runtime search-list colon')
            collector = LinuxApplication(sdk, stage, selection, dpkg_notices, allow_empty=True)
            collector.environment = dict(os.environ)
            for name in ('LD_LIBRARY_PATH', 'LD_PRELOAD'):
                collector.environment.pop(name, None)
        else:
            raise ValueError('application packaging requires a matching macOS Mach-O or Linux ELF host')
        collector.sdk_inventory = sdk_inventory
        application = stage / 'bin/app'
        application.parent.mkdir()
        shutil.copy2(binary, application)
        if system == 'Darwin':
            collector.collect(binary, application, binary)
            collector.relocate_macho()
            details = {'platform': 'macos', 'minimum_macos': '.'.join(map(str, collector.minimum_os)),
                       'external_prerequisites': ['compatible macOS system libraries'],
                       'signing': 'ad-hoc; Developer ID signing/notarization not performed'}
        else:
            collector.collect_elf(binary, application)
            glibc, glibcxx = collector.relocate_elf(patchelf)
            details = {'platform': 'linux', 'host_glibc': run(['getconf', 'GNU_LIBC_VERSION']).strip(),
                       'required_glibc_symbols': sorted(glibc), 'required_glibcxx_symbols': sorted(glibcxx),
                       'external_prerequisites': ['matching GNU loader/glibc/libstdc++/libgcc runtime'],
                       'packager_patchelf': run([patchelf, '--version']).strip()}
        used_components = collector.copy_notices('licenses')
        runtime_notices = Path(request['runtime_notices'])
        runtime_notices.read_text()  # Preserve complete UTF-8 runtime notices.
        shutil.copy2(runtime_notices, stage / 'THIRD_PARTY_NOTICES.txt')
        selection.unlink()
        # The package records input hashes, not local SDK/source installation paths.
        for origin in collector.origins.values():
            origin.pop('source', None)
        report = {'schema': 'nex.application-package/1', 'assembly_passed': True,
                  'execution_verified': False, 'entry': 'bin/app',
                  **{key: request[key] for key in ('toolchain', 'language', 'revision', 'build_key',
                      'compiler_build', 'profile', 'kind', 'compiler_target', 'host_compatible', 'binary_sha256')},
                  'components': used_components, 'system_libraries': sorted(collector.system_libraries),
                  **details, 'files': collector.inventory()}
        (stage / 'application.json').write_text(json.dumps(report, indent=2) + '\n')
        # Claim the destination without replacing an existing file/directory, then
        # publish the fully assembled tree over our own empty reservation.
        output.mkdir()
        try:
            stage.rename(output)
        except Exception:
            output.rmdir()
            raise
        return {'schema': 'nex.package/1', 'ok': True, 'directory': str(output),
                'executable': str(output / 'bin/app'), 'manifest': str(output / 'application.json'),
                'build_key': request['build_key'], 'revision': request['revision'],
                'execution_verified': False, 'files': len(report['files'])}
    except Exception as error:
        raise RuntimeError(str(error) + '\nPartial package retained at ' + str(stage)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--request', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--notices', type=Path)
    parser.add_argument('--dpkg-notices', action='store_true')
    parser.add_argument('--patchelf', default='patchelf')
    args = parser.parse_args()
    try:
        report = assemble(json.loads(args.request.read_text()), args.output, args.notices, args.dpkg_notices, args.patchelf)
        print(json.dumps(report))
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
