#!/usr/bin/env python3
"""Prepare pinned, relocatable native module closures for application packaging.

This is an internal preparation stage. It does not build an application or
change its source bindings. The final compiler stage must check the returned
pin projection, compile it, and retain its relationship to the original graph.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
import tempfile

from app_bundle import LinuxApplication, MacApplication, WindowsApplication, notices_for_sdk
from windows_pe import image as pe_image
from sdk_bundle import elf_image, macho, run, sha256


def document(path, maximum=None):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('duplicate JSON key: ' + key)
            result[key] = value
        return result
    if maximum is None:
        text = path.read_text(encoding='utf-8')
    else:
        # Operator catalogues obey the native host's regular-file, no-follow
        # and 1 MiB input contract before Python parses or normalizes anything.
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('operator catalogue must be a regular file')
            if info.st_size > maximum:
                raise ValueError('operator catalogue exceeds its byte limit')
            data = bytearray()
            while True:
                part = os.read(descriptor, min(65536, maximum - len(data) + 1))
                if not part:
                    break
                data.extend(part)
                if len(data) > maximum:
                    raise ValueError('operator catalogue exceeds its byte limit')
            text = data.decode('utf-8')
        finally:
            os.close(descriptor)
    return json.loads(text, object_pairs_hook=unique)


def inspect(nex, host):
    result = subprocess.run([str(nex), 'foreign', str(host), '--json'],
                            capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError('native catalogue verification failed: ' + result.stdout + result.stderr)
    report = json.loads(result.stdout)
    if report.get('schema') != 'nex.foreign-catalogue-report/1' or report.get('module_initialization') is not False:
        raise ValueError('compiler did not return a read-only catalogue report')
    return report


def member(root, relative):
    # Match the runtime's path and no-symlink constraints before filesystem IO.
    if not isinstance(relative, str) or not relative or len(relative.encode()) > 4096 or any(c in relative for c in '\\:\0'):
        raise ValueError('invalid module member path')
    parts = relative.split('/')
    if len(parts) > 128 or any(p in ('', '.', '..') or len(p.encode()) > 255 for p in parts):
        raise ValueError('invalid module member path')
    path = root
    if path.is_symlink():
        raise ValueError('module directory is a symlink')
    for part in parts:
        path /= part
        if path.is_symlink():
            raise ValueError('module member is a symlink: ' + relative)
    return path


class BoundedModule:
    def external(self, source, destination):
        # Runtime ABI 1 caps a member at 64 MiB and the full image at 256 MiB.
        # Bound discovered dependencies as well as the original inventory.
        source = source.resolve(strict=True)
        size = source.stat().st_size
        if size > 64 * 1048576:
            raise ValueError('module closure member exceeds 64 MiB')
        if not destination.exists():
            total = sum(path.stat().st_size for path in self.output.rglob('*') if path.is_file())
            if total + size > 256 * 1048576:
                raise ValueError('module closure exceeds 256 MiB')
        super().external(source, destination)


class MacModule(BoundedModule, MacApplication):
    pass


class LinuxModule(BoundedModule, LinuxApplication):
    pass


class WindowsModule(BoundedModule, WindowsApplication):
    pass


def prepare(nex, host, sdk, output, notices=None, dpkg_notices=False,
            patchelf='patchelf', selection=None):
    """Return exact old/new manifest pins; never initialize a module or run NEX code.

    `selection` maps reachable logical libraries to export names. A caller must
    derive it from the checked native graph. Absent selection retains all grants
    for preparation probes; production packaging must pass its reachable set.
    """
    nex = Path(nex).resolve(strict=True)
    host = Path(os.path.abspath(host))
    sdk = Path(sdk).resolve(strict=True)
    output = Path(os.path.abspath(output))
    if os.path.lexists(output):
        raise ValueError('foreign preparation requires a new output directory')
    if dpkg_notices and platform.system() != 'Linux':
        raise ValueError('--dpkg-notices is Linux-only')
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='.' + output.name + '.foreign-', dir=output.parent)).resolve(strict=True)
    try:
        original = document(host, maximum=1048576)
        libraries = original['libraries']
        if selection is not None:
            if not isinstance(selection, dict) or not selection:
                raise ValueError('reachable foreign selection must be a nonempty object')
            chosen = {}
            for name, exports in selection.items():
                if not isinstance(exports, list) or not exports or any(not isinstance(e, str) for e in exports) or len(set(exports)) != len(exports):
                    raise ValueError('selected exports must be a nonempty unique string list')
                if name not in libraries or not set(exports) <= set(libraries[name]['exports']):
                    raise ValueError('reachable foreign selection exceeds operator authority')
                chosen[name] = {**libraries[name], 'exports': sorted(exports)}
            libraries = chosen
        # Retain the original quota: it counts live module owners, including
        # independent request contexts, rather than the number of library names.
        normalized = {**original, 'libraries': {
            name: {**grant, 'directory': os.path.abspath(host.parent / grant['directory'])}
            for name, grant in libraries.items()}}
        selected_host = stage / '.operator.json'
        selected_host.write_text(json.dumps(normalized), encoding='utf-8')
        reviewed = inspect(nex, selected_host)
        components, sdk_inventory = notices_for_sdk(sdk)
        if notices:
            notices = Path(notices).resolve(strict=True)
            declared = document(notices)
            if declared.get('schema') != 'nex.sdk-notices/1':
                raise ValueError('expected nex.sdk-notices/1')
            for item in declared['components']:
                component = dict(item)
                for key in ('roots', 'license_files'):
                    component[key] = [str((notices.parent / p).resolve(strict=True)) for p in item[key]]
                components.append(component)
        component_selection = stage / '.notices.json'
        component_selection.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': components}))
        result_libraries, prepared = {}, {}
        (stage / 'bundles').mkdir()
        for name, grant in sorted(normalized['libraries'].items()):
            old_pin = grant['manifest_sha256']
            source = Path(grant['directory'])
            raw = member(source, 'manifest.json').read_bytes()
            if hashlib.sha256(raw).hexdigest() != old_pin:
                raise ValueError('module manifest changed after native inspection')
            manifest = json.loads(raw)
            # The compiler validated exact schema, platform, path graph, hashes,
            # signatures and permissions. Each copied byte is checked again.
            identity = (old_pin, str(source))
            if identity not in prepared:
                target = stage / 'bundles' / ('input-' + str(len(prepared)))
                target.mkdir()
                system = platform.system()
                if system == 'Darwin':
                    collector = MacModule(sdk, target, component_selection, dpkg_notices, allow_empty=True)
                    image = macho
                elif system == 'Linux':
                    if ':' in str(stage) or ':' in str(output):
                        raise ValueError('ELF preparation paths cannot contain a search-list colon')
                    collector = LinuxModule(sdk, target, component_selection, dpkg_notices, allow_empty=True)
                    collector.environment = {k: v for k, v in os.environ.items() if k not in ('LD_LIBRARY_PATH', 'LD_PRELOAD')}
                    image = elf_image
                elif system == 'Windows':
                    collector = WindowsModule(sdk, target, component_selection, dpkg_notices, allow_empty=True)
                    collector.pe_directory = (target/manifest['entry']).parent
                    image = pe_image
                else:
                    raise ValueError('native module packaging requires a matching native host')
                collector.sdk_inventory = sdk_inventory
                roots = []
                for record in manifest['files']:
                    path = member(source, record['path'])
                    destination = member(target, record['path'])
                    collector.external(path, destination)
                    if sha256(destination) != record['sha256']:
                        raise ValueError('module member changed after native inspection: ' + record['path'])
                    if image(path):
                        real = path.resolve(strict=True)
                        collector.destinations[real] = destination
                        roots.append((real, destination))
                if not any(destination == target / manifest['entry'] for _, destination in roots):
                    raise ValueError('module entry is not a matching native image')
                for path, destination in roots:
                    if system == 'Darwin':
                        collector.collect(path, destination, source / manifest['entry'])
                    elif system == 'Windows':
                        collector.collect_pe(path,destination)
                    else:
                        collector.collect_elf(path, destination)
                if system == 'Darwin':
                    collector.relocate_macho()
                    details = {'minimum_macos': '.'.join(map(str, collector.minimum_os)), 'signing': 'ad-hoc'}
                elif system == 'Windows':
                    details = {'architecture':collector.images[(source/manifest['entry']).resolve(strict=True)]['machine']}
                else:
                    glibc, glibcxx = collector.relocate_elf(patchelf)
                    details = {'required_glibc_symbols': sorted(glibc), 'required_glibcxx_symbols': sorted(glibcxx)}
                # Distribution notices are captured at catalogue scope. Their
                # component names/paths must not split one original image into
                # separate instances when several logical aliases use it.
                used = collector.copy_notices('licenses/' + name, output=stage)
                # ABI 1 snapshots contain regular files only. A SONAME alias
                # therefore owns a copy of the same relocated image bytes.
                for path in sorted(target.rglob('*')):
                    if path.is_symlink():
                        resolved = path.resolve(strict=True)
                        if target not in resolved.parents or not resolved.is_file():
                            raise ValueError('foreign closure alias escapes the bundle')
                        path.unlink()
                        shutil.copy2(resolved, path)
                for origin in collector.origins.values():
                    origin.pop('source', None)
                # Conversely, canonical relocation must not coalesce distinct
                # original pins (even two differently formatted manifests).
                # Preserve that image identity in a verified ordinary member.
                identity_file = 'SOURCE_MANIFEST_SHA256'
                index = 0
                while (target / identity_file).exists():
                    index += 1
                    identity_file = 'SOURCE_MANIFEST_SHA256.' + str(index)
                (target / identity_file).write_text(old_pin + '\n', encoding='ascii')
                inventory = collector.inventory()
                if not 1 <= len(inventory) <= 128 or any(record['bytes'] > 64 * 1048576 for record in inventory.values()) or sum(record['bytes'] for record in inventory.values()) > 256 * 1048576:
                    raise ValueError('relocated closure exceeds ABI 1 inventory limits')
                notice_paths = manifest['notices']
                final_manifest = {**manifest, 'files': [{'path': path, 'sha256': record['sha256']} for path, record in inventory.items()], 'notices': notice_paths}
                final_bytes = (json.dumps(final_manifest, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode()
                new_pin = hashlib.sha256(final_bytes).hexdigest()
                (target / 'manifest.json').write_bytes(final_bytes)
                final_target = stage / 'bundles' / new_pin
                if final_target.exists():
                    # Equal resulting manifests bind equal member bytes. This
                    # deduplicates aliases only after discovering each closure.
                    if (final_target / 'manifest.json').read_bytes() != final_bytes:
                        raise ValueError('foreign closure hash collision')
                    shutil.rmtree(target)
                else:
                    target.rename(final_target)
                prepared[identity] = {'manifest_sha256': new_pin, 'source_manifest_sha256': old_pin,
                                     'source_identity_file': identity_file,
                                     'components': used, 'system_libraries': sorted(collector.system_libraries),
                                     'files': inventory, **details}
            result_libraries[name] = {**prepared[identity], 'exports': sorted(grant['exports'])}
        final_host = {'schema': 'nex.foreign-host/1',
                     'resource_limit': reviewed['normalized_catalogue']['resource_limit'],
                     'resource_bytes': reviewed['normalized_catalogue']['resource_bytes'],
                     'module_limit': reviewed['normalized_catalogue']['module_limit'], 'libraries': {
            name: {'directory': 'bundles/' + record['manifest_sha256'],
                   'manifest_sha256': record['manifest_sha256'], 'exports': record['exports']}
            for name, record in result_libraries.items()}}
        (stage / 'host.json').write_text(json.dumps(final_host, indent=2) + '\n')
        checked = inspect(nex, stage / 'host.json')
        if checked['normalized_catalogue'] != final_host:
            raise ValueError('prepared catalogue differs from native normalization')
        selected_host.unlink()
        component_selection.unlink()
        report = {'schema': 'nex.foreign-package/1', 'assembly_passed': True, 'execution_verified': False,
                  'module_initialization': False, 'source_catalogue_hash': reviewed['hash'],
                  'catalogue_hash': checked['hash'], 'platform': checked['platform'],
                  'notices_root': 'catalogue',
                  'libraries': result_libraries}
        (stage / 'foreign-package.json').write_text(json.dumps(report, indent=2) + '\n')
        if platform.system()=='Windows':
            stage.rename(output)
        else:
            output.mkdir()
            try:
                stage.rename(output)
            except Exception:
                output.rmdir()
                raise
        return report
    except Exception as error:
        raise RuntimeError(str(error) + '\nForeign preparation retained at ' + str(stage)) from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--nex', required=True, type=Path)
    parser.add_argument('--foreign', required=True, type=Path)
    parser.add_argument('--sdk-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--notices', type=Path)
    parser.add_argument('--selection', type=Path)
    parser.add_argument('--dpkg-notices', action='store_true')
    parser.add_argument('--patchelf', default='patchelf')
    args = parser.parse_args()
    try:
        print(json.dumps(prepare(args.nex, args.foreign, args.sdk_root, args.output,
                                 args.notices, args.dpkg_notices, args.patchelf,
                                 document(args.selection) if args.selection else None)))
        return 0
    except Exception as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
