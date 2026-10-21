"""Data-only core capsule copying/projection, called by a matching NEX compiler.

This module never executes a bundled program, compiler, formatter or script.
The C++ caller validates the retained build and native core before publication.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import resource
import stat
import subprocess
import sys
import tempfile
import time

CORE_LIMIT = 32 * 1024**3
TOTAL_LIMIT = 33 * 1024**3
FILE_LIMIT = 512 * 1024**2
MAX_FILES = 4096
IDENTITY = ('toolchain', 'language', 'compiler_build', 'runtime_view',
            'expression_protocol', 'build_key', 'revision', 'source_hash')
BUILD_FILES = ('app', 'program.mlir', 'program.ll', 'compilation.json',
               'build.json', 'source-bundle.json', 'complete')


def completion_inputs(build):
    if 'completion_schema' not in build and 'completion_inputs' not in build:
        return []
    inputs = build.get('completion_inputs')
    if build.get('completion_schema') == 'nex.native-completion/3':
        if not isinstance(inputs, list) or not 4 <= len(inputs) <= 1024:
            raise ValueError('invalid retained native image completion limit')
        result = []
        position = 0

        def take(kind, path):
            nonlocal position
            if inputs[position] != {'kind': kind, 'path': path}:
                raise ValueError('invalid retained native image completion path/kind/order')
            result.append(path)
            position += 1

        def kind():
            value = inputs[position]
            return value.get('kind') if isinstance(value, dict) else None

        take('abi', 'library-abi.json')
        take('link_inputs', 'image-inputs.json')
        take('objects', 'objects.a')
        archives = 0
        while position < len(inputs) and kind() == 'static_library':
            if archives >= 128:
                raise ValueError('too many retained static libraries')
            take('static_library', 'libraries/%d.a' % archives)
            archives += 1
        image = re.compile(r'images/libnex_[A-Za-z_][A-Za-z_0-9]{0,63}_[0-9a-f]{64}\.(so|dylib)')
        images = []
        while position < len(inputs) and kind() == 'owned_image':
            path = inputs[position].get('path')
            if (not isinstance(path, str) or not image.fullmatch(path) or
                    (images and path <= images[-1]) or len(images) >= 129):
                raise ValueError('invalid retained owned image')
            images.append(path)
            take('owned_image', path)
        if not images:
            raise ValueError('retained image build requires its runtime')
        previous = ''
        while position < len(inputs):
            value = inputs[position]
            path = value.get('path') if isinstance(value, dict) else None
            if not isinstance(path, str) or path <= previous:
                raise ValueError('invalid retained symbol order')
            allowed = False
            for owned in images:
                if not owned.endswith('.dylib'):
                    continue
                prefix = owned + '.dSYM/Contents/'
                basename = PurePosixPath(owned).name
                allowed |= path in (prefix+'Info.plist', prefix+'Resources/DWARF/'+basename)
                allowed |= bool(re.fullmatch(re.escape(prefix)+r'Resources/Relocations/[A-Za-z_0-9]+/'+re.escape(basename)+r'\.yml', path))
            if not allowed:
                raise ValueError('invalid retained owned symbols')
            previous = path
            take('owned_symbols', path)
        return result
    if (build.get('completion_schema') != 'nex.native-completion/2' or
            not isinstance(inputs, list) or not 1 <= len(inputs) <= 129 or
            inputs != ['library-abi.json'] + ['libraries/%d.a' % i for i in range(len(inputs)-1)]):
        raise ValueError('invalid retained native completion inputs')
    return inputs


def host():
    machine = platform.machine().lower()
    machine = {'aarch64': 'arm64', 'amd64': 'x86_64'}.get(machine, machine)
    if sys.platform not in ('darwin', 'linux') or machine not in ('arm64', 'x86_64'):
        raise ValueError('core capsules currently require macOS/Linux ARM64 or x86-64')
    return {'os': sys.platform, 'machine': machine}


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate capsule JSON field')
        result[key] = value
    return result


def relative(name):
    if (not isinstance(name, str) or not name or len(name.encode('utf-8')) > 4096 or
            '\\' in name or '\0' in name or name.startswith('/') or
            len(name.split('/')) > 32 or
            any(part in ('', '.', '..') or len(part.encode('utf-8')) > 255 for part in name.split('/'))):
        raise ValueError('invalid relative capsule path')
    return PurePosixPath(name)


class Files:
    def __init__(self):
        self.deadline = time.monotonic() + 900
        self.total = 0
        self.count = 0

    def checked(self, path, limit, destination=None):
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC)
        target = None
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or not 0 <= info.st_size <= limit:
                raise ValueError('capsule input must be a bounded regular non-symlink file')
            self.count += 1
            self.total += info.st_size
            if self.count > MAX_FILES + 8 or self.total > TOTAL_LIMIT:
                raise ValueError('capsule input count/total size exceeds limit')
            if destination is not None:
                destination.parent.mkdir(parents=True, exist_ok=True)
                target = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
            digest = hashlib.sha256()
            contents = bytearray() if destination is None and limit <= 16*1024**2 else None
            count = 0
            while True:
                if time.monotonic() > self.deadline:
                    raise ValueError('capsule copy/hash deadline exceeded')
                block = os.read(fd, 1024**2)
                if not block:
                    break
                count += len(block)
                if count > info.st_size:
                    raise ValueError('capsule input grew during inspection')
                digest.update(block)
                if contents is not None:
                    contents.extend(block)
                if target is not None:
                    remaining = memoryview(block)
                    while remaining:
                        written = os.write(target, remaining)
                        if written <= 0:
                            raise ValueError('cannot write capsule copy')
                        remaining = remaining[written:]
            after = os.fstat(fd)
            current = os.lstat(path)
            if (count != info.st_size or after.st_size != info.st_size or
                    (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino) or
                    after.st_mtime_ns != info.st_mtime_ns or after.st_ctime_ns != info.st_ctime_ns):
                raise ValueError('capsule input changed during inspection')
            return {'sha256': digest.hexdigest(), 'bytes': count}, contents
        finally:
            os.close(fd)
            if target is not None:
                os.close(target)

    def json(self, path, limit=8*1024**2):
        return self.json_record(path, limit)[0]

    def json_record(self, path, limit=8*1024**2):
        record, data = self.checked(path, limit)
        return json.loads(bytes(data).decode('utf-8', 'strict'), object_pairs_hook=unique), record


def write_json(path, value):
    data = (json.dumps(value, ensure_ascii=True, indent=2) + '\n').encode()
    if len(data) > 8*1024**2:
        raise ValueError('capsule manifest exceeds limit')
    with path.open('xb') as stream:
        stream.write(data)


def system_dependencies(program):
    # Read native headers without using ldd or launching the image's loader.
    if sys.platform == 'darwin':
        args = ['/usr/bin/otool', '-L', str(program)]
    elif sys.platform == 'linux':
        args = ['readelf', '-d', str(program)]
    else:
        raise ValueError('core capsules currently require macOS or Linux')
    def bound_output():
        resource.setrlimit(resource.RLIMIT_FSIZE, (1024**2, 1024**2))
    with tempfile.TemporaryFile() as output:
        subprocess.run(args, stdout=output, stderr=output, timeout=30,
                       check=True, preexec_fn=bound_output)
        output.seek(0)
        text = output.read(1024**2 + 1).decode('utf-8', 'strict')
    if len(text.encode('utf-8')) > 1024**2:
        raise ValueError('native dependency listing exceeds limit')
    if sys.platform == 'darwin':
        libraries = [line.strip().split(' (compatibility version ', 1)[0]
                     for line in text.splitlines()[1:] if line.startswith('\t')]
        if not libraries or any(not p.startswith(('/usr/lib/', '/System/Library/')) for p in libraries):
            raise ValueError('capsules with non-system native dependencies are not yet supported')
    else:
        from sdk_bundle import LinuxBundle
        libraries = re.findall(r'\(NEEDED\).*?\[([^]]+)\]', text)
        if any('/' in name or name not in LinuxBundle.HOST_LIBRARIES for name in libraries):
            raise ValueError('capsules with non-system native dependencies are not yet supported')
    return sorted(set(libraries))


def identity(manifest):
    result = {key: manifest[key] for key in IDENTITY}
    for key, value in result.items():
        if not isinstance(value, str) or not value or len(value) > 256:
            raise ValueError('invalid capsule build identity')
    if not re.fullmatch('[0-9a-f]{64}', result['build_key']):
        raise ValueError('invalid capsule build key')
    program = Path(manifest['program'])
    if not program.is_absolute() or program.name != 'app' or program.parent.name != result['build_key']:
        raise ValueError('capsule requires its original content-addressed executable path')
    return result


def export(request):
    files = Files()
    work = Path(request['work'])
    if not work.is_dir() or any(work.iterdir()):
        raise ValueError('capsule staging directory must be empty')
    original = Path(request['manifest'])
    manifest, original_record = files.json_record(original)
    bound = identity(manifest)
    recorded_program = str(Path(manifest['program']).resolve(strict=True))
    if Path(recorded_program).parent.name != bound['build_key'] or Path(recorded_program).name != 'app':
        raise ValueError('original executable alias does not resolve to its retained build key')
    if any(bound[key] != request['identity'][key] for key in ('compiler_build', 'toolchain', 'language')):
        raise ValueError('capsule export requires the matching compiler')
    prefix = 'build/' + bound['build_key']
    inventory = {}

    def copy(source, name, limit=FILE_LIMIT):
        relative(name)
        if name in inventory or len(inventory) >= MAX_FILES:
            raise ValueError('duplicate capsule file')
        inventory[name], _ = files.checked(source, limit, work/name)

    copy(original, 'original-debug.json', 8*1024**2)
    if inventory['original-debug.json'] != original_record:
        raise ValueError('debug manifest changed during export')
    for name in BUILD_FILES:
        copy(original.parent/name, prefix+'/'+name)
    build, build_record = files.json_record(original.parent/'build.json')
    if inventory[prefix+'/build.json'] != build_record:
        raise ValueError('build metadata changed during export')
    for name in completion_inputs(build):
        copy(original.parent/name, prefix+'/'+name)
    symbols = original.parent/'app.dSYM'
    if sys.platform == 'darwin':
        if symbols.is_symlink() or not symbols.is_dir():
            raise ValueError('capsule requires retained native symbols')
        copy(original.parent/'debug-symbols.complete', prefix+'/debug-symbols.complete', 1024)
        for directory, dirs, names in os.walk(symbols, followlinks=False):
            for name in dirs:
                if (Path(directory)/name).is_symlink():
                    raise ValueError('symlink in capsule symbol tree')
            for name in sorted(names):
                source = Path(directory)/name
                copy(source, prefix+'/'+source.relative_to(original.parent).as_posix())
    if not isinstance(manifest['sources'], list) or len(manifest['sources']) > 1024:
        raise ValueError('capsule frozen source count exceeds limit')
    for index, source in enumerate(manifest['sources']):
        copy(Path(source['projection']), prefix+'/capsule-sources/%04d/source.nex' % index, 16*1024**2)
    copy(Path(request['core']), 'process.core', CORE_LIMIT)
    if inventory['process.core']['sha256'] != request['core_sha256']:
        raise ValueError('core changed after retained-build inspection')
    dependencies = system_dependencies(work/prefix/'app')
    receipt = {'schema': 'nex.core-capsule/1', 'identity': bound, 'host': host(),
               'recorded_program': recorded_program, 'original_program': manifest['program'], 'build_directory': prefix,
               'core': 'process.core', 'original_manifest': 'original-debug.json',
               'native_dependencies': dependencies, 'dependency_scope': 'matching_host_system_only',
               'application_execution': False, 'files': inventory}
    write_json(work/'capsule.json', receipt)
    return {'ok': True, 'files': len(inventory), 'bytes': sum(x['bytes'] for x in inventory.values())}


def prepare(request):
    files = Files()
    root = Path(request['capsule'])
    if root.is_symlink() or not root.is_dir():
        raise ValueError('capsule root must be a regular directory')
    work = Path(request['work'])
    if not work.is_dir() or any(work.iterdir()):
        raise ValueError('capsule read workspace must be empty')
    receipt, receipt_record = files.json_record(root/'capsule.json')
    required = {'schema', 'identity', 'host', 'recorded_program', 'original_program', 'build_directory', 'core',
                'original_manifest', 'native_dependencies', 'dependency_scope', 'application_execution', 'files'}
    if (not isinstance(receipt, dict) or set(receipt) != required or receipt['schema'] != 'nex.core-capsule/1' or
            receipt['host'] != host() or receipt['dependency_scope'] != 'matching_host_system_only' or
            receipt['application_execution'] is not False):
        raise ValueError('unsupported capsule format/host/dependency scope')
    inventory = receipt['files']
    if not isinstance(inventory, dict) or not 1 <= len(inventory) <= MAX_FILES:
        raise ValueError('capsule file count exceeds limit')
    manifest, original_record = files.json_record(root/'original-debug.json')
    if inventory.get('original-debug.json') != original_record:
        raise ValueError('capsule original debug manifest integrity differs')
    bound = identity(manifest)
    prefix = receipt['build_directory']
    recorded = receipt['recorded_program']
    if (not isinstance(recorded, str) or not recorded or len(recorded.encode('utf-8')) > 16384 or '\0' in recorded or
            not Path(recorded).is_absolute() or os.path.normpath(recorded) != recorded or
            Path(recorded).parent.name != bound['build_key'] or Path(recorded).name != 'app' or
            receipt['identity'] != bound or receipt['original_program'] != manifest['program'] or
            prefix != 'build/'+bound['build_key'] or receipt['core'] != 'process.core' or
            receipt['original_manifest'] != 'original-debug.json' or
            any(bound[key] != request['identity'][key] for key in ('compiler_build', 'toolchain', 'language'))):
        raise ValueError('capsule original/physical/compiler identities differ')
    sources = manifest['sources']
    if not isinstance(sources, list) or len(sources) > 1024:
        raise ValueError('capsule frozen source count exceeds limit')
    expected = {'original-debug.json', 'process.core'} | {prefix+'/'+name for name in BUILD_FILES}
    build, build_record = files.json_record(root/prefix/'build.json')
    if inventory.get(prefix+'/build.json') != build_record:
        raise ValueError('capsule native build metadata differs')
    expected |= {prefix+'/'+name for name in completion_inputs(build)}
    expected |= {prefix+'/capsule-sources/%04d/source.nex' % index for index in range(len(sources))}
    if sys.platform == 'darwin':
        expected |= {prefix+'/debug-symbols.complete', prefix+'/app.dSYM/Contents/Info.plist',
                     prefix+'/app.dSYM/Contents/Resources/DWARF/app'}
    optional_symbol = re.compile(re.escape(prefix)+r'/app\.dSYM/Contents/Resources/Relocations/[^/]+/[^/]+\.yml')
    if not expected <= set(inventory) or any(name not in expected and
            not (sys.platform == 'darwin' and optional_symbol.fullmatch(name)) for name in inventory):
        raise ValueError('capsule has missing or unexpected retained build inputs')
    dirs = set()
    for name in inventory:
        path = relative(name)
        dirs.update(p.as_posix() for p in path.parents if p.as_posix() != '.')
        if len(dirs) > MAX_FILES:
            raise ValueError('capsule directory count exceeds limit')
    actual = set()
    for directory, children, names in os.walk(root, followlinks=False):
        for name in children:
            path = Path(directory)/name
            if path.is_symlink() or path.relative_to(root).as_posix() not in dirs:
                raise ValueError('unexpected/symlink capsule directory')
        for name in names:
            path = Path(directory)/name
            relative_name = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file() or relative_name not in {*inventory, 'capsule.json'}:
                raise ValueError('unexpected/symlink/special capsule file')
            actual.add(relative_name)
    if actual != {*inventory, 'capsule.json'}:
        raise ValueError('capsule inventory is incomplete')
    for name, record in inventory.items():
        if (not isinstance(record, dict) or set(record) != {'bytes', 'sha256'} or
                type(record['bytes']) is not int or record['bytes'] < 0 or
                not isinstance(record['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', record['sha256'])):
            raise ValueError('invalid capsule file record')
        limit = CORE_LIMIT if name == 'process.core' else 8*1024**2 if name == 'original-debug.json' else 16*1024**2 if name.endswith('/source-bundle.json') or '/capsule-sources/' in name else FILE_LIMIT
        destination = work/name if name.startswith(prefix+'/') else None
        observed, _ = files.checked(root/name, limit, destination)
        if observed != record:
            raise ValueError('capsule file integrity mismatch: '+name)
    folder = work/prefix
    if system_dependencies(folder/'app') != receipt['native_dependencies']:
        raise ValueError('capsule native dependencies differ')
    manifest['program'] = str(folder/'app')
    mappings = []
    for index, source in enumerate(manifest['sources']):
        path = folder/'capsule-sources'/('%04d' % index)/'source.nex'
        if path.relative_to(work).as_posix() not in inventory:
            raise ValueError('capsule lacks frozen source projection')
        # Historical DWARF used an imported unit's basename. The capsule's
        # canonical storage filename must not change the debugger's basename.
        # Materialize an alias only in the fresh, verified staging directory.
        basename = Path(source['debug_path']).name
        if not basename or basename in ('.', '..'):
            raise ValueError('capsule has an invalid source basename')
        if basename != path.name:
            alias = path.with_name(basename)
            with alias.open('xb') as target:
                target.write(path.read_bytes())
            path = alias
        source['projection'] = str(path)
        mappings.append([str(Path(source['debug_path']).parent), str(path.parent)])
    manifest['source_map'] = mappings
    write_json(folder/'debug.json', manifest)
    digest, _ = Files().checked(root/'capsule.json', 8*1024**2)
    if digest != receipt_record:
        raise ValueError('capsule manifest changed during inspection')
    return {'ok': True, 'manifest': str(folder/'debug.json'), 'core': str(root/'process.core'),
            'core_sha256': inventory['process.core']['sha256'],
            'recorded_program': receipt['recorded_program'], 'manifest_sha256': digest['sha256'],
            'files': len(inventory), 'host': receipt['host'], 'native_dependencies': receipt['native_dependencies']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('request', type=Path)
    args = parser.parse_args()
    try:
        request = Files().json(args.request, 65536)
        result = {'export': export, 'prepare': prepare}[request['mode']](request)
        print(json.dumps(result, ensure_ascii=True))
    except Exception as error:
        print(json.dumps({'ok': False, 'error': str(error)[:4096]}, ensure_ascii=True))
        raise SystemExit(1)


if __name__ == '__main__':
    main()
