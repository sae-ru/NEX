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
import re

from sdk_bundle import Bundle, LinuxBundle, elf_image, macho, run, sha256


class ApplicationInputs:
    def external(self, source, destination):
        source = source.resolve(strict=True)
        owned = getattr(self, 'owned_inputs', {}).get(source)
        if owned and sha256(source) != owned['sha256']:
            raise ValueError('compiler-owned image changed before collection')
        if not owned and self.sdk_inventory and self.sdk in source.parents:
            relative = str(source.relative_to(self.sdk))
            record = self.sdk_inventory.get(relative)
            if not record or not record.get('component') or record.get('sha256') != sha256(source):
                raise ValueError('SDK library integrity/provenance mismatch: ' + relative)
        super().external(source, destination)
        if owned and sha256(destination) != owned['sha256']:
            raise ValueError('compiler-owned image changed during capture')


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


def copy_foreign(request, stage):
    directory = request.get('foreign_directory')
    if not directory:
        if request.get('foreign_files') or request.get('foreign_projection'):
            raise ValueError('foreign package metadata has no captured directory')
        return None, [], set()
    source = Path(directory)
    if source.is_symlink():
        raise ValueError('foreign capture root is a symlink')
    source = source.resolve(strict=True)
    expected = request['foreign_files']
    actual = {}
    for path in source.rglob('*'):
        if path.is_symlink():
            raise ValueError('symlink in captured foreign inputs')
        if path.is_file():
            actual[str(path.relative_to(source))] = sha256(path)
        elif not path.is_dir():
            raise ValueError('non-regular captured foreign input')
    if not actual or actual != expected:
        raise ValueError('foreign capture changed after compilation')
    target = stage / 'foreign'
    shutil.copytree(source, target)
    if {str(path.relative_to(target)): sha256(path) for path in target.rglob('*') if path.is_file()} != expected:
        raise ValueError('foreign copy changed after compilation')
    projection = request['foreign_projection']
    if projection.get('schema') != 'nex.foreign-projection/1' or projection['packaged_revision'] != request['revision']:
        raise ValueError('foreign source projection differs from the compiled program')
    components, system = [], set()
    for library in projection['preparation']['libraries'].values():
        system.update(library['system_libraries'])
        prefix = Path('foreign') if projection['preparation'].get('notices_root') == 'catalogue' else Path('foreign/bundles') / library['manifest_sha256']
        for item in library['components']:
            component = {**item, 'license_files': [
                {**record, 'path': str(prefix / record['path'])} for record in item['license_files']]}
            if component not in components:
                components.append(component)
    return projection, components, system



def unique_task_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate task provenance JSON field')
        result[key] = value
    return result


def task_package_inputs(request, binary, owned_inputs):
    task = request.get('task_inputs')
    if request['schema'] == 'nex.application-request/1':
        if task is not None:
            raise ValueError('legacy application request cannot contain task provenance')
        return []
    expected_fields = {'schema', 'binary', 'binary_sha256', 'owned_images', 'runtime_notices',
        'runtime_notices_sha256', 'sdk_root', 'toolchain', 'language', 'revision',
        'foreign_directory', 'foreign_files', 'foreign_projection', 'build_key', 'target',
        'compiler_target', 'compiler_build', 'profile', 'kind', 'host_compatible', 'task_inputs'}
    if (set(request) != expected_fields or request['kind'] != 'executable' or request['profile'] == 'profile' or
            request['foreign_directory'] or request['foreign_files'] or request['foreign_projection'] or
            not isinstance(task, dict) or set(task) != {'schema', 'files'} or
            task['schema'] != 'nex.application-task-inputs/1' or
            not isinstance(task['files'], list) or not 4 <= len(task['files']) <= 132):
        raise ValueError('invalid task application provenance envelope')
    libraries = sorted((p for p, row in owned_inputs.items() if row['kind'] == 'library'), key=lambda p: p.name)
    expected = [('application_provider', binary.parent/'task-provider.json', binary)]
    expected += [('owned_provider', Path(str(p)+'.task-provider.json'), p) for p in libraries]
    expected += [(kind, binary.parent/name, None) for kind, name in
                 [('image_inputs', 'image-inputs.json'), ('build', 'build.json'), ('complete', 'complete')]]
    if len(expected) != len(task['files']):
        raise ValueError('task provenance closure differs from owned images')
    result = []
    total = 0
    for row, (kind, source, image) in zip(task['files'], expected):
        if (not isinstance(row, dict) or set(row) != {'kind', 'path', 'hash', 'sha256', 'bytes',
                'component', 'image', 'image_key', 'image_sha256', 'image_uuid'} or
                row['kind'] != kind or row['path'] != str(source) or
                any(not isinstance(row[k], str) or not re.fullmatch('[0-9a-f]{64}', row[k]) for k in ('hash', 'sha256')) or
                type(row['bytes']) is not int or not 1 <= row['bytes'] <= 16*1024**2 or
                source.is_symlink() or source.resolve(strict=True) != source or
                not source.is_file() or source.stat().st_size != row['bytes'] or sha256(source) != row['sha256']):
            raise ValueError('task provenance file identity/path/bytes differ')
        total += row['bytes']
        if total > 32*1024**2:
            raise ValueError('task provenance exceeds aggregate bound')
        if image is None:
            if any(row[k] is not None for k in ('component', 'image', 'image_key', 'image_sha256', 'image_uuid')):
                raise ValueError('nonprovider task input cannot claim image identity')
        else:
            if (row['image'] != str(image) or not isinstance(row['component'], str) or
                    not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,63}', row['component'])):
                raise ValueError('task provider image association differs')
            provider = json.loads(source.read_text(), object_pairs_hook=unique_task_fields)
            provider_fields = {'schema', 'mode', 'descriptor_abi', 'compiler_build', 'descriptor_size',
                'abi_offset', 'code_only', 'task_file_reads', 'component', 'cohort', 'language',
                'definitions', 'exports', 'artifact_kind', 'owner_image', 'definition_owners',
                'component_file_reads', 'image'}
            # The matching compiler validates BLAKE3/cohort/descriptor semantics before
            # this data-only collector; independently preserve and bind raw SHA bytes.
            identity = provider.get('image')
            physical = owned_inputs.get(image)
            if (set(provider) != provider_fields or provider.get('schema') != 'nex.native-task-provider/2' or
                    provider.get('mode') != 'shared-fixed' or provider.get('component') != row['component'] or
                    provider.get('owner_image') != row['component'] or
                    provider.get('artifact_kind') != ('application' if kind == 'application_provider' else 'shared-image') or
                    not isinstance(identity, dict) or set(identity) != {'key', 'hash', 'sha256', 'uuid', 'runtime_key', 'runtime_hash'} or
                    any(identity.get(k) != row[v] for k, v in [('key', 'image_key'), ('sha256', 'image_sha256'), ('uuid', 'image_uuid')]) or
                    identity['sha256'] != sha256(image) or
                    (physical and any(physical[k] != identity[k] for k in ('key', 'sha256', 'uuid'))) or
                    (not physical and (identity['key'] != request['build_key'] or identity['sha256'] != request['binary_sha256']))):
                raise ValueError('raw task provider does not describe its original image')
        result.append((row, source, image))
    return result


def copy_task_provenance(inputs, stage, application, collector):
    if not inputs:
        return None
    records = []
    for index, (row, source, image) in enumerate(inputs):
        relative = Path('provenance/task')/('%03d-' % index + source.name)
        target = stage/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if (source.stat().st_size != row['bytes'] or sha256(source) != row['sha256'] or
                target.stat().st_size != row['bytes'] or sha256(target) != row['sha256']):
            raise ValueError('task provenance changed during collection')
        output = None if image is None else application if row['kind'] == 'application_provider' else collector.destinations.get(image)
        if image is not None and (output is None or not output.is_file() or stage not in output.parents):
            raise ValueError('task provider image was not retained by collector')
        records.append({'kind': row['kind'], 'path': relative.as_posix(),
            'input_hash': row['hash'], 'input_sha256': row['sha256'], 'bytes': row['bytes'],
            'component': row['component'], 'input_image_key': row['image_key'],
            'input_image_sha256': row['image_sha256'], 'input_uuid': row['image_uuid'],
            'output_image': None if output is None else output.relative_to(stage).as_posix(),
            'output_image_sha256': None if output is None else sha256(output)})
    return {'schema': 'nex.application-task-provenance/1', 'metadata_rewritten': False,
            'hash_algorithm': 'BLAKE3', 'files': records}

def assemble(request, output, notices=None, dpkg_notices=False, patchelf='patchelf'):
    if dpkg_notices and platform.system() != 'Linux':
        raise ValueError('--dpkg-notices is Linux-only')
    if request.get('schema') not in ('nex.application-request/1', 'nex.application-request/2'):
        raise ValueError('expected nex.application-request/1 or /2')
    binary = Path(request['binary']).resolve(strict=True)
    if sha256(binary) != request['binary_sha256']:
        raise ValueError('application binary changed after compilation')
    owned_inputs = {}
    owned = request.get('owned_images', [])
    if not isinstance(owned, list) or len(owned) > 129:
        raise ValueError('invalid compiler-owned image inventory')
    for image in owned:
        if not isinstance(image, dict) or set(image) != {'path', 'sha256', 'key', 'abi', 'kind', 'uuid'}:
            raise ValueError('invalid compiler-owned image fields')
        source = Path(image['path'])
        if (source.is_symlink() or source.resolve(strict=True).parent != (binary.parent/'images').resolve(strict=True) or
                not re.fullmatch(r'libnex_[A-Za-z_][A-Za-z_0-9]{0,63}_'+re.escape(image['key'])+r'\.(so|dylib)', source.name) or
                image['kind'] not in ('runtime', 'library') or
                any(not isinstance(image[k], str) or not re.fullmatch('[0-9a-f]{64}', image[k]) for k in ('sha256', 'key', 'abi')) or
                not isinstance(image['uuid'], str) or not re.fullmatch('[0-9a-f]{16,128}', image['uuid']) or
                sha256(source) != image['sha256']):
            raise ValueError('compiler-owned image path/identity/bytes differ')
        source = source.resolve(strict=True)
        if source in owned_inputs:
            raise ValueError('duplicate compiler-owned image')
        owned_inputs[source] = image
    if owned_inputs and sum(i['kind'] == 'runtime' for i in owned_inputs.values()) != 1:
        raise ValueError('compiler-owned image closure requires exactly one runtime')
    task_inputs = task_package_inputs(request, binary, owned_inputs)
    runtime_notices = Path(request['runtime_notices'])
    if ('runtime_notices_sha256' in request and sha256(runtime_notices) != request['runtime_notices_sha256']):
        raise ValueError('captured runtime notices changed')
    if owned_inputs and 'runtime_notices_sha256' not in request:
        raise ValueError('owned image provenance requires captured runtime notices')
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
        if owned_inputs:
            components.append({'name': 'nex-generated-project-images', 'version': request['toolchain'],
                'url': 'https://github.com/sae-ru/NEX', 'roots': [str(p) for p in owned_inputs],
                'license_files': [str(runtime_notices.resolve(strict=True))]})
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
        collector.owned_inputs = owned_inputs
        application = stage / 'bin/app'
        application.parent.mkdir()
        shutil.copy2(binary, application)
        if sha256(application) != request['binary_sha256']:
            raise ValueError('application bytes changed during capture')
        if system == 'Darwin':
            collector.collect(binary, application, binary)
            for source in owned_inputs:
                target = collector.dependency_target(source)
                collector.external(source, target); collector.destinations[source] = target
                collector.collect(source, target, binary)
            collector.relocate_macho()
            details = {'platform': 'macos', 'minimum_macos': '.'.join(map(str, collector.minimum_os)),
                       'external_prerequisites': ['compatible macOS system libraries'],
                       'signing': 'ad-hoc; Developer ID signing/notarization not performed'}
        else:
            collector.collect_elf(binary, application)
            for source in owned_inputs:
                target = collector.dependency_target(source)
                collector.external(source, target); collector.destinations[source] = target
                collector.collect_elf(source, target)
            glibc, glibcxx = collector.relocate_elf(patchelf)
            details = {'platform': 'linux', 'host_glibc': run(['getconf', 'GNU_LIBC_VERSION']).strip(),
                       'required_glibc_symbols': sorted(glibc), 'required_glibcxx_symbols': sorted(glibcxx),
                       'external_prerequisites': ['matching GNU loader/glibc runtime; system C++/GCC runtimes listed in system_libraries'],
                       'packager_patchelf': run([patchelf, '--version']).strip()}
        task_provenance = copy_task_provenance(task_inputs, stage, application, collector)
        used_components = collector.copy_notices('licenses')
        foreign, foreign_components, foreign_system = copy_foreign(request, stage)
        used_components += foreign_components
        if foreign:
            modules = foreign['preparation']['libraries'].values()
            if system == 'Darwin':
                minimum = max([tuple(map(int, details['minimum_macos'].split('.')))] +
                              [tuple(map(int, module['minimum_macos'].split('.'))) for module in modules])
                details['minimum_macos'] = '.'.join(map(str, minimum))
            else:
                for key in ('required_glibc_symbols', 'required_glibcxx_symbols'):
                    details[key] = sorted(set(details[key]).union(*(module[key] for module in modules)))
        runtime_notices.read_text()  # Preserve complete UTF-8 runtime notices.
        shutil.copy2(runtime_notices, stage / 'THIRD_PARTY_NOTICES.txt')
        selection.unlink()
        # The package records input hashes, not local SDK/source installation paths.
        for origin in collector.origins.values():
            owned = owned_inputs.get(Path(origin['source']))
            if owned:
                origin.update(owned_image_kind=owned['kind'], owned_image_key=owned['key'],
                              owned_image_abi=owned['abi'], input_uuid=owned['uuid'])
            origin.pop('source', None)
        report = {'schema': 'nex.application-package/1', 'assembly_passed': True,
                  'execution_verified': False, 'entry': 'bin/app',
                  **{key: request[key] for key in ('toolchain', 'language', 'revision', 'build_key',
                      'compiler_build', 'profile', 'kind', 'compiler_target', 'host_compatible', 'binary_sha256')},
                  'components': used_components, 'system_libraries': sorted(collector.system_libraries | foreign_system),
                  **details, 'files': collector.inventory()}
        if task_provenance:
            report['task_provenance'] = task_provenance
        if foreign:
            report['foreign_projection'] = foreign
        (stage / 'application.json').write_text(json.dumps(report, indent=2) + '\n')
        # Claim the destination without replacing an existing file/directory, then
        # publish the fully assembled tree over our own empty reservation.
        output.mkdir()
        try:
            stage.rename(output)
        except Exception:
            output.rmdir()
            raise
        result = {'schema': 'nex.package/1', 'ok': True, 'directory': str(output),
                'executable': str(output / 'bin/app'), 'manifest': str(output / 'application.json'),
                'build_key': request['build_key'], 'revision': request['revision'],
                'execution_verified': False, 'files': len(report['files'])}
        if foreign:
            result['source_revision'] = foreign['source_revision']
            result['foreign_catalogue'] = str(output / 'foreign/host.json')
        return result
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
