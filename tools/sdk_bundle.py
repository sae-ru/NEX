#!/usr/bin/env python3
"""Assemble a relocatable macOS development SDK from an installed NEX SDK.

Only copies are rewritten/signed. Apple SDK, system C++ runtime/linker/debugger,
Python and Node/npm remain host prerequisites. See docs/sdk.md for acceptance.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess


def run(arguments, **options):
    result = subprocess.run(list(map(str, arguments)), capture_output=True, text=True, **options)
    if result.returncode:
        raise RuntimeError('command failed: ' + repr(list(map(str, arguments))) + '\n' + result.stdout + result.stderr)
    return result.stdout


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def system_path(path):
    return str(path).startswith(('/usr/lib/', '/System/Library/'))


def macho(path):
    with path.open('rb') as source:
        magic = source.read(4)
    if magic not in (b'\xfe\xed\xfa\xce', b'\xce\xfa\xed\xfe', b'\xfe\xed\xfa\xcf',
                     b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf'):
        return False
    # Universal static archives also use FAT_MAGIC. Their OBJECT members are
    # not loadable images and must never be passed to codesign/install_name_tool.
    return bool(re.search(r'\b(EXECUTE|DYLIB|BUNDLE|DYLINKER)\b', run(['/usr/bin/otool', '-hv', path])))


class Bundle:
    def __init__(self, sdk, output, notices):
        self.sdk, self.output = sdk, output
        self.origins, self.images, self.destinations, self.dependencies = {}, {}, {}, {}
        self.minimum_os = (0,)
        self.system_libraries = set()
        self.components = json.loads(notices.read_text())
        if self.components.get('schema') != 'nex.sdk-notices/1' or not self.components.get('components'):
            raise ValueError('expected nex.sdk-notices/1 with nonempty components')
        names = set()
        for component in self.components['components']:
            name = component['name']
            if not re.fullmatch('[a-zA-Z0-9_.-]{1,80}', name) or name in names:
                raise ValueError('invalid/duplicate notice component name')
            names.add(name)
            if not component.get('version') or not component.get('url') or not component.get('roots') or not component.get('license_files'):
                raise ValueError('component needs version, url, roots and license_files: ' + name)
            component['roots'] = [str((notices.parent / root).resolve(strict=True)) for root in component['roots']]
            component['license_files'] = [str((notices.parent / file).resolve(strict=True)) for file in component['license_files']]

    def component(self, source):
        matches = [(len(root), component['name']) for component in self.components['components']
                   for root in component['roots'] if source == Path(root) or Path(root) in source.parents]
        if not matches:
            raise ValueError('no component/license provenance for external file: ' + str(source))
        return max(matches)[1]

    def external(self, source, destination):
        source = source.resolve(strict=True)
        relative = str(destination.relative_to(self.output))
        provenance = {'source': str(source), 'source_sha256': sha256(source), 'component': self.component(source)}
        if destination.exists():
            if self.origins.get(relative) != provenance:
                raise ValueError('bundle destination collision: ' + relative)
            return
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        self.origins[relative] = provenance

    def external_tree(self, source, destination):
        visited = set()
        def copy(directory, target):
            real = directory.resolve(strict=True)
            if real in visited:
                raise ValueError('cycle/duplicate directory in external component: ' + str(directory))
            visited.add(real)
            target.mkdir(parents=True, exist_ok=True)
            for entry in sorted(directory.iterdir()):
                if entry.is_dir():
                    copy(entry, target / entry.name)
                elif entry.is_file():
                    self.external(entry, target / entry.name)
                else:
                    raise ValueError('unsupported external input: ' + str(entry))
            visited.remove(real)
        copy(source, destination)

    def image_info(self, source):
        commands = run(['/usr/bin/otool', '-l', source]).splitlines()
        rpaths, identifier = [], None
        command = ''
        for line in commands:
            line = line.strip()
            if line.startswith('cmd '):
                command = line[4:]
            if command == 'LC_RPATH' and line.startswith('path '):
                rpaths.append(line[5:].rsplit(' (offset ', 1)[0])
            if command == 'LC_ID_DYLIB' and line.startswith('name '):
                identifier = line[5:].rsplit(' (offset ', 1)[0]
            if command == 'LC_BUILD_VERSION' and line.startswith('minos '):
                self.minimum_os = max(self.minimum_os, tuple(map(int, line.split()[1].split('.'))))
            if command == 'LC_VERSION_MIN_MACOSX' and line.startswith('version '):
                self.minimum_os = max(self.minimum_os, tuple(map(int, line.split()[1].split('.'))))
        dependencies = []
        for line in run(['/usr/bin/otool', '-L', source]).splitlines()[1:]:
            if line.startswith('\t') and ' (compatibility version ' in line:
                dependency = line.strip().split(' (compatibility version ', 1)[0]
                if dependency != identifier and dependency not in dependencies:
                    dependencies.append(dependency)
        return dependencies, list(dict.fromkeys(rpaths)), identifier

    def collect(self, source, destination, executable, inherited=()):
        source = source.resolve(strict=True)
        if source in self.images:
            if self.images[source]['destination'] != destination:
                raise ValueError('duplicate executable/library identity: ' + str(source))
            return
        dependencies, rpaths, identifier = self.image_info(source)
        def expand(value):
            return value.replace('@loader_path', str(source.parent)).replace('@executable_path', str(executable.parent))
        search = [Path(expand(path)) for path in rpaths] + list(inherited)
        image = {'destination': destination, 'rpaths': rpaths, 'id': identifier, 'dependencies': {}}
        self.images[source] = image
        for dependency in dependencies:
            if system_path(dependency):
                self.system_libraries.add(dependency)
                continue
            if dependency.startswith('@rpath/'):
                candidates = [path / dependency[len('@rpath/'):] for path in search]
            else:
                candidates = [Path(expand(dependency))]
            resolved = next((path.resolve() for path in candidates if path.is_file()), None)
            if resolved is None:
                raise ValueError('unresolved dependency ' + dependency + ' of ' + str(source))
            target = self.output / 'lib/nex/host' / resolved.name
            self.external(resolved, target)
            image['dependencies'][dependency] = target
            self.destinations[resolved] = target
            self.collect(resolved, target, executable, search)

    def assemble(self):
        environment = dict(os.environ, NEX_RESOURCE_DIR=str(self.sdk / 'share/nex'))
        environment.pop('NEX_CLANG', None)
        doctor = json.loads(run([self.sdk / 'bin/nex', 'doctor', '--json'], env=environment))
        if doctor.get('sdk_manifest') or not doctor.get('native_archiver'):
            raise ValueError('input must be an unbundled installed SDK with host-tool discovery (0.27+)')
        shutil.copytree(self.sdk, self.output, symlinks=True)
        if any(path.is_symlink() for path in self.output.rglob('*')):
            raise ValueError('input SDK contains symlinks; install a plain development SDK first')
        llvm = Path(doctor['native_compiler']).resolve().parent.parent
        tools = {'compiler': 'clang++', 'archiver': 'llvm-ar', 'debug_packager': 'dsymutil'}
        configuration = {'schema': 'nex.sdk-host/1', 'tools': {}}
        for key, name in tools.items():
            target = self.output / 'libexec/nex/llvm/bin' / name
            original = Path(doctor[{'compiler': 'native_compiler', 'archiver': 'native_archiver', 'debug_packager': 'native_debug_packager'}[key]])
            self.external(original, target)
            configuration['tools'][key] = str(target.relative_to(self.output))
        # clang++ may invoke clang by name; preserve C++ dispatch through argv[0].
        (self.output / 'libexec/nex/llvm/bin/clang').symlink_to('clang++')
        resource = Path(run([doctor['native_compiler'], '-print-resource-dir'], env=environment).strip())
        self.external_tree(resource, self.output / 'libexec/nex/llvm/lib/clang' / resource.name)
        self.external_tree(llvm / 'include/c++/v1', self.output / 'libexec/nex/llvm/include/c++/v1')
        # Darwin Clang passes this path to Apple's linker, including ordinary
        # non-LTO links. Retain it when supplied by the selected LLVM package.
        lto = llvm / 'lib/libLTO.dylib'
        if lto.is_file():
            self.external(lto, self.output / 'libexec/nex/llvm/lib/libLTO.dylib')
        includes = self.output / 'lib/nex/deps/include'
        for name in ['sqlite3.h', 'sqlite3ext.h']:
            self.external(Path(doctor['native_sqlite_include']) / name, includes / name)
        self.external_tree(Path(doctor['native_openssl_include']) / 'openssl', includes / 'openssl')
        # All copied runtime dylibs join the closure, even if not needed by NEX's
        # default compile flags. Static compiler-rt archives remain unmodified.
        initial = [(self.sdk / 'bin/nex', self.output / 'bin/nex')]
        for relative, origin in list(self.origins.items()):
            if macho(self.output / relative):
                initial.append((Path(origin['source']), self.output / relative))
        for source, destination in initial:
            self.collect(source, destination, source)
        for key in ['native_sqlite_library', 'native_openssl_ssl', 'native_openssl_crypto']:
            source = Path(doctor[key]).resolve()
            target = self.output / 'lib/nex/host' / source.name
            self.external(source, target)
            self.destinations[source] = target
            self.collect(source, target, source)
        configuration['sqlite'] = {'include': str(includes.relative_to(self.output)),
                                   'library': str(self.destinations[Path(doctor['native_sqlite_library']).resolve()].relative_to(self.output))}
        configuration['openssl'] = {'include': str(includes.relative_to(self.output)),
                                    **{name: str(self.destinations[Path(doctor[field]).resolve()].relative_to(self.output))
                                       for name, field in [('ssl', 'native_openssl_ssl'), ('crypto', 'native_openssl_crypto')]}}
        for source, image in self.images.items():
            destination = image['destination']
            arguments = ['/usr/bin/install_name_tool']
            for old, dependency in image['dependencies'].items():
                relative = os.path.relpath(dependency, destination.parent)
                arguments += ['-change', old, '@loader_path/' + relative]
            for old in image['rpaths']:
                arguments += ['-delete_rpath', old]
            if image['id']:
                arguments += ['-id', '@rpath/' + destination.name]
            if len(arguments) > 1:
                run([*arguments, destination])
            run(['/usr/bin/codesign', '--force', '--sign', '-', destination])
            run(['/usr/bin/codesign', '--verify', destination])
            actual, rpaths, _ = self.image_info(destination)
            if rpaths:
                raise ValueError('unexpected remaining rpaths: ' + str(destination))
            for dependency in actual:
                if system_path(dependency):
                    continue
                resolved = Path(dependency.replace('@loader_path', str(destination.parent))).resolve()
                if not dependency.startswith('@loader_path/') or self.output not in resolved.parents or not resolved.is_file():
                    raise ValueError('external dependency remains: ' + dependency)
        installed_components = []
        used = {item['component'] for item in self.origins.values()}
        for component in self.components['components']:
            if component['name'] not in used:
                continue
            notice = {key: component[key] for key in ['name', 'version', 'url']}
            notice['license_files'] = []
            for index, filename in enumerate(component['license_files']):
                source = Path(filename)
                source.read_text()  # Require complete UTF-8 notice text.
                target = self.output / 'share/nex/licenses/sdk' / component['name'] / (str(index) + '-' + source.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                notice['license_files'].append({'path': str(target.relative_to(self.output)), 'sha256': sha256(target)})
            installed_components.append(notice)
        (self.output / 'share/nex/sdk-host.json').write_text(json.dumps(configuration, indent=2) + '\n')
        files = {}
        for path in sorted(self.output.rglob('*')):
            relative = str(path.relative_to(self.output))
            if path.is_symlink():
                if self.output not in path.resolve(strict=True).parents:
                    raise ValueError('escaping bundle symlink: ' + relative)
                files[relative] = {'symlink': str(path.readlink())}
            elif path.is_file():
                files[relative] = {'sha256': sha256(path), 'bytes': path.stat().st_size,
                                   'executable': bool(path.stat().st_mode & 0o111), **self.origins.get(relative, {})}
        report = {'schema': 'nex.sdk-bundle/1', 'ok': True, 'toolchain': doctor['version'], 'language': doctor['language'],
                  'host': doctor['host'], 'minimum_macos': '.'.join(map(str, self.minimum_os)),
                  'system_libraries': sorted(self.system_libraries), 'components': installed_components,
                  'external_prerequisites': ['Apple command line tools/SDK and system C++ runtime/linker',
                                             'Python 3.9+', 'Node.js/npm for browser builds', 'host LLDB/lldb-dap for live debugging'],
                  'modifications': 'Non-system Mach-O loads rewritten to bundle-relative loader paths; ad hoc signatures refreshed. Source installations unchanged.',
                  'acceptance_passed': False, 'files': files}
        (self.output / 'share/nex/sdk-bundle.json').write_text(json.dumps(report, indent=2) + '\n')
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--notices', type=Path, required=True,
                        help='nex.sdk-notices/1 provenance and full local license text paths')
    arguments = parser.parse_args()
    if platform.system() != 'Darwin':
        parser.error('Mach-O bundling currently requires macOS; Linux/Windows packaging is pending')
    sdk, output = arguments.sdk.resolve(strict=True), arguments.output.resolve()
    if output.exists() or sdk in output.parents or output in sdk.parents:
        parser.error('--output must be new and separate from the input SDK')
    report = Bundle(sdk, output, arguments.notices.resolve(strict=True)).assemble()
    print(json.dumps({key: report[key] for key in ['ok', 'toolchain', 'language', 'host', 'minimum_macos', 'acceptance_passed']}))


if __name__ == '__main__':
    main()
