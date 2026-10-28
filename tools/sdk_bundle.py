#!/usr/bin/env python3
"""Assemble a relocatable macOS/Linux development SDK from an installed SDK.

Only copies are rewritten. Platform C/C++ SDK/runtime, Python, Node/npm and
host debugger remain prerequisites. See docs/sdk.md for acceptance.
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


def selected_wasm_linker(doctor, environment):
    """Package the explicit linker used by Wasm builds, even with no CMake default."""
    if 'NEX_WASM_LD' not in environment:
        return doctor
    selected = shutil.which(environment['NEX_WASM_LD'], path=environment.get('PATH'))
    if not selected:
        raise ValueError('NEX_WASM_LD must select an executable LLVM 22.1 wasm-ld')
    # Keep the selected filename for multicall LLVM tools' argv[0] dispatch.
    if 'LLD 22.1.' not in run([selected, '--version'], env=environment):
        raise ValueError('NEX_WASM_LD requires wasm-ld from LLVM 22.1.x')
    return {**doctor, 'wasm_linker': str(Path(selected).absolute())}


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


class DebianNotices:
    """Ownership metadata only; never runs package-supplied maintainer scripts."""
    def __init__(self, components):
        self.components, self.owners, self.packages = components, {}, {}
        for listing in Path('/var/lib/dpkg/info').glob('*.list'):
            for name in listing.read_text().splitlines():
                if name.startswith('/'):
                    self.owners.setdefault(name, listing.name[:-5])

    def component(self, source):
        owner = self.owners.get(str(source))
        if owner is None:
            raise ValueError('unmanaged external file needs explicit component/notice: ' + str(source))
        if owner not in self.packages:
            fields = run(['dpkg-query', '-W', '-f=${Version}\n${source:Package}\n${source:Version}\n${Homepage}', owner]).splitlines()
            copyright_file = Path('/usr/share/doc') / owner.split(':')[0] / 'copyright'
            if not copyright_file.is_file():
                raise ValueError('missing installed copyright metadata for ' + owner)
            text = copyright_file.read_text()
            licenses = [str(copyright_file.resolve())]
            for name in sorted(set(re.findall(r'/usr/share/common-licenses/([A-Za-z0-9_.+-]+)', text))):
                path = Path('/usr/share/common-licenses') / name
                if path.is_file():
                    licenses.append(str(path.resolve()))
            component = {'name': 'deb-' + owner.replace(':', '_'), 'version': fields[0],
                         'url': fields[3] if len(fields) > 3 and fields[3] else 'https://packages.ubuntu.com/noble/' + owner.split(':')[0],
                         'package': owner, 'source_package': fields[1], 'source_version': fields[2],
                         'roots': [], 'license_files': list(dict.fromkeys(licenses))}
            if any(item['name'] == component['name'] for item in self.components):
                raise ValueError('automatic notice component name collision: ' + component['name'])
            self.components.append(component)
            self.packages[owner] = component
        component = self.packages[owner]
        component['roots'].append(str(source))
        return component['name']


class Bundle:
    def __init__(self, sdk, output, notices, dpkg_notices=False, allow_empty=False):
        self.sdk, self.output = sdk, output
        self.origins, self.images, self.destinations, self.dependencies = {}, {}, {}, {}
        self.minimum_os = (0,)
        self.system_libraries = set()
        self.components = json.loads(notices.read_text())
        if self.components.get('schema') != 'nex.sdk-notices/1' or not isinstance(self.components.get('components'), list) or (not self.components['components'] and not dpkg_notices and not allow_empty):
            raise ValueError('expected nex.sdk-notices/1 with nonempty components')
        names = set()
        for component in self.components['components']:
            name = component['name']
            if not re.fullmatch('[a-zA-Z0-9_.-]{1,80}', name) or name in ('.', '..') or name in names:
                raise ValueError('invalid/duplicate notice component name')
            names.add(name)
            if not component.get('version') or not component.get('url') or not component.get('roots') or not component.get('license_files'):
                raise ValueError('component needs version, url, roots and license_files: ' + name)
            component['roots'] = [str((notices.parent / root).resolve(strict=True)) for root in component['roots']]
            component['license_files'] = [str((notices.parent / file).resolve(strict=True)) for file in component['license_files']]
        self.debian = DebianNotices(self.components['components']) if dpkg_notices else None
        self.component_cache = {}

    def component(self, source):
        if source in self.component_cache:
            return self.component_cache[source]
        matches = [(len(root), component['name']) for component in self.components['components']
                   for root in component['roots'] if source == Path(root) or Path(root) in source.parents]
        if not matches:
            if not self.debian:
                raise ValueError('no component/license provenance for external file: ' + str(source))
            name = self.debian.component(source)
        else:
            name = max(matches)[1]
        self.component_cache[source] = name
        return name

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

    def dependency_target(self, source):
        # Application module bundles can already inventory an image at a fixed
        # relative path. Reuse that destination rather than copying it twice.
        return self.destinations.get(source, self.output / 'lib/nex/host' / source.name)

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
            target = self.dependency_target(resolved)
            self.external(resolved, target)
            image['dependencies'][dependency] = target
            self.destinations[resolved] = target
            self.collect(resolved, target, executable, search)

    def assemble(self):
        environment = dict(os.environ, NEX_RESOURCE_DIR=str(self.sdk / 'share/nex'))
        environment.pop('NEX_CLANG', None)
        doctor = json.loads(run([self.sdk / 'bin/nex', 'doctor', '--json'], env=environment))
        doctor = selected_wasm_linker(doctor, environment)
        if doctor.get('sdk_manifest') or not doctor.get('native_archiver'):
            raise ValueError('input must be an unbundled installed SDK with host-tool discovery (0.27+)')
        shutil.copytree(self.sdk, self.output, symlinks=True)
        if any(path.is_symlink() for path in self.output.rglob('*')):
            raise ValueError('input SDK contains symlinks; install a plain development SDK first')
        llvm = Path(doctor['native_compiler']).resolve().parent.parent
        tools = {'compiler': 'clang++', 'archiver': 'llvm-ar', 'debug_packager': 'dsymutil'}
        if doctor.get('wasm_linker'):
            tools['wasm_linker'] = 'wasm-ld'
        configuration = {'schema': 'nex.sdk-host/1', 'tools': {}}
        for key, name in tools.items():
            target = self.output / 'libexec/nex/llvm/bin' / name
            original = Path(doctor[{'compiler': 'native_compiler', 'archiver': 'native_archiver', 'debug_packager': 'native_debug_packager', 'wasm_linker': 'wasm_linker'}[key]])
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
        self.relocate_macho()
        return self.finish(configuration, doctor, {
            'platform': 'macos', 'minimum_macos': '.'.join(map(str, self.minimum_os)),
            'external_prerequisites': ['Apple command line tools/SDK and system C++ runtime/linker',
                                       'Python 3.9+', 'Node.js/npm for browser builds', 'host LLDB/lldb-dap for live debugging'],
            'modifications': 'Non-system Mach-O loads rewritten to bundle-relative loader paths; ad hoc signatures refreshed. Source installations unchanged.'})

    def relocate_macho(self):
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

    def copy_notices(self, directory="share/nex/licenses/sdk", *, output=None):
        output = self.output if output is None else output
        installed_components = []
        used = {item['component'] for item in self.origins.values()}
        for component in self.components['components']:
            if component['name'] not in used:
                continue
            notice = {key: component[key] for key in ['name', 'version', 'url', 'package', 'source_package', 'source_version'] if key in component}
            notice['license_files'] = []
            for index, filename in enumerate(component['license_files']):
                source = Path(filename)
                source.read_text()  # Require complete UTF-8 notice text.
                target = output / directory / component['name'] / (str(index) + '-' + source.name)
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or (target.exists() and (not target.is_file() or sha256(target) != sha256(source))):
                    raise ValueError('bundle notice destination collision: ' + str(target.relative_to(output)))
                shutil.copy2(source, target)
                notice['license_files'].append({'path': str(target.relative_to(output)), 'sha256': sha256(target)})
            installed_components.append(notice)
        return installed_components

    def inventory(self):
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
        return files

    def finish(self, configuration, doctor, details):
        installed_components = self.copy_notices()
        (self.output / 'share/nex/sdk-host.json').write_text(json.dumps(configuration, indent=2) + '\n')
        files = self.inventory()
        report = {'schema': 'nex.sdk-bundle/1', 'ok': True, 'toolchain': doctor['version'], 'language': doctor['language'],
                  'host': doctor['host'], 'system_libraries': sorted(self.system_libraries),
                  'components': installed_components, **details,
                  'acceptance_passed': False, 'files': files}
        (self.output / 'share/nex/sdk-bundle.json').write_text(json.dumps(report, indent=2) + '\n')
        return report


def elf_image(path):
    with path.open('rb') as source:
        header = source.read(20)
    return (len(header) == 20 and header[:4] == b'\x7fELF' and header[5] in (1, 2)
            and int.from_bytes(header[16:18], 'little' if header[5] == 1 else 'big') in (2, 3))


class LinuxBundle(Bundle):
    # Known runtime SONAMEs also serve the core capsule's matching-host guard.
    # Collection resolves C++ libraries below before classifying private copies.
    HOST_LIBRARIES = {'libc.so.6', 'libm.so.6', 'libpthread.so.0', 'libdl.so.2', 'librt.so.1',
                      'libresolv.so.2', 'libutil.so.1', 'libstdc++.so.6', 'libgcc_s.so.1',
                      'ld-linux-aarch64.so.1', 'ld-linux-x86-64.so.2'}
    CXX_LIBRARIES = {'libstdc++.so.6', 'libgcc_s.so.1'}

    def elf_loader_context(self, source):
        # Resolve once from the actual load root. Running ldd on each child
        # discards an executable's inherited DT_RPATH and can choose different
        # providers from the ones its loader actually selected.
        resolved = {}
        for line in run(['ldd', source], env=self.environment).splitlines():
            match = re.match(r'\s*(\S+)\s+=>\s+(.*?)\s+\(0x', line)
            if match:
                name, path = match.group(1), Path(match.group(2)).resolve(strict=True)
                if not path.is_file():
                    raise ValueError('ELF loader selected a non-file: ' + str(path))
                if name in resolved and resolved[name] != path:
                    raise ValueError('ELF image has inconsistent loader contexts: ' + name)
                resolved[name] = path
        return resolved

    def collect_elf(self, source, destination, loader_context=None, visited=None):
        source = source.resolve(strict=True)
        if loader_context is None:
            loader_context = self.elf_loader_context(source)
        if visited is None:
            visited = set()
        def selected(name):
            original = Path(name).resolve() if Path(name).is_absolute() else loader_context.get(name)
            if original is None or not original.is_file():
                raise ValueError('unresolved ELF dependency ' + name + ' of ' + str(source))
            return original
        # LLVM installs multicall tools such as ld.lld and wasm-ld as
        # aliases of one ELF file. Each copied destination needs its own
        # origin-relative dependency rewrite while preserving its argv[0].
        key = (source, destination)
        if key in visited:
            return
        visited.add(key)
        if key in self.images:
            image = self.images[key]
            for name, original in image['loader_bindings'].items():
                if selected(name) != original:
                    raise ValueError('ELF image has inconsistent loader contexts: ' + name + ' of ' + str(source))
            # A shared intermediary can have identical immediate dependencies
            # while a deeper provider differs between two application roots.
            for name, original in image['dependency_sources'].items():
                self.collect_elf(original, image['dependency_targets'][image['dependencies'][name]].resolve(),
                                 loader_context, visited)
            return
        if any(image['destination'] == destination for image in self.images.values()):
            raise ValueError('duplicate ELF image destination: ' + str(destination))
        dynamic = run(['readelf', '-d', source])
        needed = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', dynamic)
        image = {'destination': destination, 'dependencies': {}, 'dependency_targets': {},
                 'loader_bindings': {}, 'dependency_sources': {}}
        self.images[key] = image
        for name in needed:
            if Path(name).name in self.HOST_LIBRARIES - self.CXX_LIBRARIES:
                self.system_libraries.add(name)
                continue
            original = selected(name)
            image['loader_bindings'][name] = original
            if (Path(name).name in self.CXX_LIBRARIES and
                    any(Path(root).resolve() in original.parents for root in ('/lib', '/lib64', '/usr/lib', '/usr/lib64'))):
                self.system_libraries.add(name)
                continue
            target = self.dependency_target(original)
            self.external(original, target)
            alias = name if '/' not in name else original.name
            alias_path = target.parent / alias
            if alias_path != target:
                if alias_path.exists() and alias_path.resolve() != target.resolve():
                    raise ValueError('ELF SONAME collision: ' + alias)
                if not alias_path.exists():
                    alias_path.symlink_to(target.name)
            image['dependencies'][name] = alias
            image['dependency_targets'][alias] = alias_path
            image['dependency_sources'][name] = original
            self.destinations[original] = target
            self.collect_elf(original, target, loader_context, visited)

    def assemble(self, patchelf):
        environment = dict(os.environ, NEX_RESOURCE_DIR=str(self.sdk / 'share/nex'))
        for name in ('NEX_CLANG', 'LD_LIBRARY_PATH', 'LD_PRELOAD'):
            environment.pop(name, None)
        self.environment = environment
        doctor = json.loads(run([self.sdk / 'bin/nex', 'doctor', '--json'], env=environment))
        doctor = selected_wasm_linker(doctor, environment)
        if doctor.get('sdk_manifest') or not doctor.get('native_linker'):
            raise ValueError('input must be an unbundled installed Linux SDK with LLVM LLD')
        if tuple(map(int, doctor['version'].split('.')[:2])) < (0, 28):
            raise ValueError('Linux application dependency selection requires NEX toolchain 0.28+')
        shutil.copytree(self.sdk, self.output, symlinks=True)
        if any(path.is_symlink() for path in self.output.rglob('*')):
            raise ValueError('input SDK contains symlinks; install a plain development SDK first')
        configuration = {'schema': 'nex.sdk-host/1', 'tools': {}}
        tools = [('clang++', 'native_compiler'), ('llvm-ar', 'native_archiver'), ('ld.lld', 'native_linker')]
        if doctor.get('wasm_linker'):
            tools.append(('wasm-ld', 'wasm_linker'))
        for name, field in tools:
            target = self.output / 'libexec/nex/llvm/bin' / name
            self.external(Path(doctor[field]), target)
            key = {'clang++': 'compiler', 'llvm-ar': 'archiver', 'ld.lld': 'linker', 'wasm-ld': 'wasm_linker'}[name]
            configuration['tools'][key] = str(target.relative_to(self.output))
        (self.output / 'libexec/nex/llvm/bin/clang').symlink_to('clang++')
        resource = Path(run([doctor['native_compiler'], '-print-resource-dir'], env=environment).strip())
        self.external_tree(resource, self.output / 'libexec/nex/llvm/lib/clang' / resource.name)
        includes = self.output / 'lib/nex/deps/include'
        for name in ('sqlite3.h', 'sqlite3ext.h'):
            self.external(Path(doctor['native_sqlite_include']) / name, includes / name)
        openssl_include = Path(doctor['native_openssl_include'])
        self.external_tree(openssl_include / 'openssl', includes / 'openssl')
        multiarch = run(['g++', '-print-multiarch']).strip()
        architecture_headers = openssl_include / multiarch / 'openssl'
        if architecture_headers.is_dir():
            self.external_tree(architecture_headers, includes / 'openssl')
        initial = [(self.sdk / 'bin/nex', self.output / 'bin/nex')]
        for relative, origin in list(self.origins.items()):
            if elf_image(self.output / relative):
                initial.append((Path(origin['source']), self.output / relative))
        for source, destination in initial:
            self.collect_elf(source, destination)
        for key in ('native_sqlite_library', 'native_openssl_ssl', 'native_openssl_crypto'):
            original = Path(doctor[key]).resolve()
            target = self.output / 'lib/nex/host' / original.name
            self.external(original, target)
            self.destinations[original] = target
            self.collect_elf(original, target)
            dynamic = run(['readelf', '-d', original])
            soname = re.search(r'\(SONAME\).*?\[([^]]+)\]', dynamic)
            if soname and soname[1] != target.name:
                if '/' in soname[1] or soname[1] in ('.', '..'):
                    raise ValueError('ELF SONAME must be a filename inside the bundle: ' + soname[1])
                alias = target.parent / soname[1]
                if not alias.exists():
                    alias.symlink_to(target.name)
        configuration['sqlite'] = {'include': str(includes.relative_to(self.output)),
                                   'library': str(self.destinations[Path(doctor['native_sqlite_library']).resolve()].relative_to(self.output))}
        configuration['openssl'] = {'include': str(includes.relative_to(self.output)),
                                    **{key: str(self.destinations[Path(doctor[field]).resolve()].relative_to(self.output))
                                       for key, field in [('ssl', 'native_openssl_ssl'), ('crypto', 'native_openssl_crypto')]}}
        required_glibc, required_glibcxx = self.relocate_elf(patchelf)
        return self.finish(configuration, doctor, {
            'platform': 'linux', 'tested_build_distribution': Path('/etc/os-release').read_text(),
            'host_glibc': run(['getconf', 'GNU_LIBC_VERSION']).strip(),
            'required_glibc_symbols': sorted(required_glibc), 'required_glibcxx_symbols': sorted(required_glibcxx),
            'host_cxx_sdk': run(['g++', '--version']).splitlines()[0],
            'packager_patchelf': run([patchelf, '--version']).strip(),
            'external_prerequisites': ['matching glibc loader/runtime and GCC C/C++ development SDK (headers/CRT); system C++/GCC runtimes listed in system_libraries',
                                       'Python 3.9+', 'openssl CLI for HTTPS acceptance', 'Node.js/npm for browser builds',
                                       'host LLDB/lldb-dap for live debugging'],
            'modifications': 'Copied ELF images use origin-relative RUNPATH; absolute DT_NEEDED paths normalized. Private C++/GCC runtimes are captured; GNU platform runtime remains external. Source installations unchanged.'})

    def relocate_elf(self, patchelf):
        required_glibc, required_glibcxx = set(), set()
        for image in self.images.values():
            target = image['destination']
            for old, new in image['dependencies'].items():
                if old != new:
                    run([patchelf, '--replace-needed', old, new, target])
            directories = list(dict.fromkeys(path.parent for path in image['dependency_targets'].values()))
            if not directories:
                directories = [self.output / 'lib/nex/host']
            relative = [os.path.relpath(path, target.parent) for path in directories]
            rpath = ':'.join('$ORIGIN' if path == '.' else '$ORIGIN/' + path for path in relative)
            run([patchelf, '--set-rpath', rpath, target])
            if run([patchelf, '--print-rpath', target]).strip() != rpath:
                raise ValueError('ELF runtime path was not retained: ' + str(target))
            versions = run(['readelf', '--version-info', target], env={**self.environment, 'LC_ALL': 'C'})
            needs = versions.split('Version needs section', 1)[1] if 'Version needs section' in versions else ''
            required_glibc.update(re.findall(r'\bGLIBC_[A-Za-z0-9_.]+', needs))
            required_glibcxx.update(re.findall(r'\bGLIBCXX_[0-9.]+', needs))
            # ldd uses the new origin paths, with no loader environment override.
            dependencies = run(['ldd', target], env=self.environment)
            for old, alias in image['dependencies'].items():
                match = re.search(r'^\s*' + re.escape(alias) + r'\s*=>\s*(.*?)\s+\(0x', dependencies, re.M)
                expected = image['dependency_targets'][alias].resolve(strict=True)
                if match is None or Path(match[1]).resolve() != expected:
                    raise ValueError('ELF dependency escaped the bundle: ' + alias + ' in ' + dependencies)
        return required_glibc, required_glibcxx


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--notices', type=Path, required=True,
                        help='nex.sdk-notices/1 provenance and full local license text paths')
    parser.add_argument('--dpkg-notices', action='store_true', help='Supplement explicit notices from installed Debian/Ubuntu package metadata')
    parser.add_argument('--patchelf', default='patchelf', help='ELF rewriting tool for Linux packaging only')
    arguments = parser.parse_args()
    system = platform.system()
    if system not in ('Darwin', 'Linux'):
        parser.error('SDK bundling currently supports macOS/Linux; Windows packaging is pending')
    sdk, output = arguments.sdk.resolve(strict=True), arguments.output.resolve()
    if output.exists() or sdk in output.parents or output in sdk.parents:
        parser.error('--output must be new and separate from the input SDK')
    if system == 'Linux':
        patchelf = shutil.which(arguments.patchelf)
        if not patchelf:
            parser.error('Linux packaging requires patchelf; it is not needed to use the assembled SDK')
        report = LinuxBundle(sdk, output, arguments.notices.resolve(strict=True), arguments.dpkg_notices).assemble(patchelf)
    else:
        if arguments.dpkg_notices:
            parser.error('--dpkg-notices is Linux-only')
        report = Bundle(sdk, output, arguments.notices.resolve(strict=True)).assemble()
    print(json.dumps({key: report[key] for key in ['ok', 'platform', 'toolchain', 'language', 'host', 'acceptance_passed']}))


if __name__ == '__main__':
    main()
