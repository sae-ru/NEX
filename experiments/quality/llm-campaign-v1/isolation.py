"""macOS allowlist profiles for compilation and pure benchmark execution.

No global settings change. Profiles apply only to newly owned child processes.
Runtime candidates may use threads, stdout/stderr and their copied inputs, but
cannot fork, access the network, read arbitrary host data or write other files.
"""
import json
import hashlib
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys


def quote(path):
    return json.dumps(str(path), ensure_ascii=False)


def image_paths(image):
    """Read trusted Mach-O dependency metadata, without executing an image."""
    image = Path(image).resolve(strict=True)
    listing = subprocess.run(['/usr/bin/otool', '-L', image], capture_output=True, timeout=15, check=True).stdout.decode()
    commands = subprocess.run(['/usr/bin/otool', '-l', image], capture_output=True, timeout=15, check=True).stdout.decode()
    rpaths = []
    for match in re.finditer(r'cmd LC_RPATH\n\s+cmdsize \d+\n\s+path (.*?) \(offset', commands):
        value = match[1].replace('@loader_path', str(image.parent)).replace('@executable_path', str(image.parent))
        if value.startswith('/'): rpaths.append(Path(value))
    files, roots = [], list(rpaths)
    for line in listing.splitlines()[1:]:
        value = line.strip().rsplit(' (', 1)[0]
        if value.startswith('/'): candidates = [Path(value)]
        elif value.startswith('@loader_path/') or value.startswith('@executable_path/'):
            candidates = [image.parent / value.split('/', 1)[1]]
        elif value.startswith('@rpath/'):
            candidates = [p / value[len('@rpath/'):] for p in rpaths]
        else: continue
        for candidate in candidates:
            if candidate.is_file():
                files.append(candidate.resolve()); roots.append(candidate.resolve().parent); break
    return files, roots


class MacSandbox:
    def __init__(self, *, compiler=None, cpp=None, resources=None, extra_read_roots=()):
        if platform.system() != 'Darwin' or not Path('/usr/bin/sandbox-exec').is_file():
            raise ValueError('this execution policy requires macOS sandbox-exec; other hosts need their qualified backend')
        self.compiler = Path(compiler).absolute() if compiler else None
        self.cpp = Path(cpp).absolute() if cpp else None
        self.resources = Path(resources).resolve(strict=True) if resources else None
        if self.compiler and self.cpp is None:
            env = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent'}
            if self.resources: env['NEX_RESOURCE_DIR'] = str(self.resources)
            raw = subprocess.run([self.compiler, 'doctor', '--json'], env=env,
                                 capture_output=True, timeout=30, check=True).stdout
            native = json.loads(raw)['native_compiler']
            self.cpp = Path(shutil.which(native, path=env['PATH']) or native).absolute()
            if not self.cpp.is_file(): raise ValueError('cannot resolve selected native compiler')
        self.os_profile = Path('/System/Library/Sandbox/Profiles/dyld-support.sb')
        self.os_profile_sha256 = hashlib.sha256(self.os_profile.read_bytes()).hexdigest()
        self.roots = {Path('/System'), Path('/usr'), Path('/bin'), Path('/sbin'),
                      Path('/Library/Developer'), Path(sys.base_prefix).resolve()}
        self.images = {Path(sys.executable).resolve()}
        self.compile_roots, self.compile_images = set(), set()
        if self.compiler: self.images.add(self.compiler.resolve(strict=True))
        if self.cpp:
            self.images.add(self.cpp.resolve(strict=True))
            self.roots.add(self.cpp.resolve(strict=True).parent.parent)
            # Homebrew's etc/clang is normally a symlink outside the Cellar.
            # Admit only that selected compiler's canonical configuration tree.
            config = self.cpp.resolve().parent.parent / 'etc/clang'
            if config.is_dir(): self.compile_roots.add(config.resolve())
            environment = {'PATH': str(self.cpp.parent) + ':/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C'}
            linker = subprocess.run([self.cpp, '-print-prog-name=ld'], env=environment,
                                    capture_output=True, timeout=15, check=True).stdout.decode().strip()
            linker = Path(shutil.which(linker, path=environment['PATH']) or linker)
            if not linker.is_absolute() or not linker.is_file(): raise ValueError('selected linker cannot be identified')
            self.compile_images.update([linker.absolute(), linker.resolve()])
            # /usr/bin/ld is an xcrun shim on current macOS. Resolve the
            # operator-selected developer tools rather than substituting a
            # different linker or admitting every application directory.
            developer = subprocess.run(['/usr/bin/xcode-select', '-p'], env=environment,
                                       capture_output=True, timeout=15, check=True).stdout.decode().strip()
            developer = Path(developer).resolve(strict=True)
            self.compile_roots.add(developer)
            actual_ld = subprocess.run(['/usr/bin/xcrun', '--find', 'ld'], env=environment,
                                       capture_output=True, timeout=15, check=True).stdout.decode().strip()
            actual_ld = Path(actual_ld)
            if not actual_ld.is_absolute() or not actual_ld.is_file(): raise ValueError('selected Xcode linker is missing')
            self.linker = actual_ld.absolute()
            self.compile_images.update([actual_ld.absolute(), actual_ld.resolve()])
        pending, seen = list(self.images), set()
        while pending:
            image = pending.pop()
            if image in seen: continue
            seen.add(image)
            dependencies, roots = image_paths(image)
            self.roots.update(p.resolve() for p in roots if p.is_dir())
            pending.extend(p for p in dependencies if p not in seen and not str(p).startswith(('/usr/', '/System/')))
        for value in extra_read_roots:
            path = Path(value).resolve(strict=True)
            if path == Path('/') or path == Path.home() or (self.resources and self.resources.is_relative_to(path)):
                raise ValueError('read roots must not admit the home directory or complete resource repository')
            self.roots.add(path)
        self.roots = {p for p in self.roots if p.exists()}
        for path in self.roots:
            if path == Path('/') or path == Path.home(): raise ValueError('overbroad tool dependency root')

    def environment(self, workspace, *, compile_phase):
        workspace = Path(workspace).resolve()
        temporary = workspace / 'tmp'; temporary.mkdir(exist_ok=True)
        home = workspace / 'home'; home.mkdir(exist_ok=True)
        paths = ([str(self.cpp.parent)] if self.cpp else []) + ['/usr/bin', '/bin']
        result = {'PATH': os.pathsep.join(paths), 'HOME': str(home), 'TMPDIR': str(temporary),
                  'TMP': str(temporary), 'TEMP': str(temporary), 'LANG': 'C', 'LC_ALL': 'C',
                  'TZ': 'UTC', 'PYTHONDONTWRITEBYTECODE': '1'}
        if compile_phase and self.resources: result['NEX_RESOURCE_DIR'] = str(self.resources)
        return result

    def wrap(self, argv, workspace, output, name, *, compile_phase=False, writable_cache=None):
        if hashlib.sha256(self.os_profile.read_bytes()).hexdigest() != self.os_profile_sha256:
            raise ValueError('OS loader profile changed during the cohort')
        argv = list(map(str, argv)); workspace = Path(workspace).resolve(strict=True); output = Path(output).resolve(strict=True)
        image = Path(argv[0])
        if not image.is_absolute() or not image.is_file(): raise ValueError('sandbox command needs a selected absolute image')
        reads = set(self.roots) | {workspace}
        literals = set(self.images) | {image.absolute(), image.resolve(), Path('/dev/null'), Path('/dev/random'), Path('/dev/urandom'), Path('/private/etc/localtime')}
        executables = {image.absolute(), image.resolve(), Path(sys.executable).resolve(), Path(sys.executable).absolute()}
        if compile_phase:
            reads.update(self.compile_roots)
            literals.update(self.compile_images)
            executables.update(self.compile_images)
            if writable_cache: reads.add(Path(writable_cache).resolve())
            if self.resources:
                reads.update(self.resources / p for p in ['runtime', 'lib', 'debug'])
        else:
            # A compiled NEX image can read its own captured library closure.
            # The rest of the cohort's cache and other trial sources stay denied.
            reads.add(image.resolve().parent)
        if any(output.is_relative_to(root) for root in reads):
            raise ValueError('a tool read root would expose host receipts or other trial evidence')
        # Current Apple's system.sb grants these primitive startup operations.
        # They do not authorize higher-level file, network or fork operations;
        # those remain governed by the explicit rules below and denial probes.
        policy = ['(version 1)', '(deny default)', '(import "dyld-support.sb")',
                  '(allow syscall*)', '(allow mach-bootstrap)',
                  '(allow file-read-metadata file-test-existence)',
                  '(allow sysctl-read)', '(allow signal (target self))', '(allow process-info* (target self))']
        policy.append('(allow file-read* file-map-executable ' + ' '.join('(subpath ' + quote(p) + ')' for p in sorted(reads)) +
                      ' ' + ' '.join('(literal ' + quote(p) + ')' for p in sorted(literals)) + ')')
        policy.append('(allow process-exec ' + ' '.join('(literal ' + quote(p) + ')' for p in sorted(executables)) +
                      ((' (subpath "/usr/bin") ' + ('(subpath ' + quote(self.cpp.resolve().parent) + ')' if self.cpp else '')) if compile_phase else '') + ')')
        writes = [output / (name + '.stdout'), output / (name + '.stderr'), Path('/dev/null')]
        rule = '(allow file-write* ' + ' '.join('(literal ' + quote(p) + ')' for p in writes)
        if compile_phase:
            policy.append('(allow process-fork)')
            rule += ' (subpath ' + quote(workspace) + ')'
            if writable_cache: rule += ' (subpath ' + quote(Path(writable_cache).resolve()) + ')'
        policy.append(rule + ')')
        # Network and mach service lookup remain denied by default.
        text = '\n'.join(policy) + '\n'; path = output / (name + '.sb')
        path.write_text(text, encoding='utf-8')
        # Set hard limits before exec, without preexec_fn in a threaded parent.
        cpu, size = (120, 128 * 1024 * 1024) if compile_phase else (15, 2 * 1024 * 1024)
        launch = ('import os,resource,sys;'
                  f'resource.setrlimit(resource.RLIMIT_CPU,({cpu},{cpu}));'
                  f'resource.setrlimit(resource.RLIMIT_FSIZE,({size},{size}));'
                  'resource.setrlimit(resource.RLIMIT_CORE,(0,0));'
                  'resource.setrlimit(resource.RLIMIT_NOFILE,(128,128));'
                  'os.execv(sys.argv[1],sys.argv[1:])')
        return ['/usr/bin/sandbox-exec', '-f', str(path), sys.executable, '-I', '-B', '-X', 'utf8', '-c', launch, *argv]
