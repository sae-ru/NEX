"""Select a portable macOS SDK's native build inputs for the local runner."""
import importlib.util
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent.with_name('llm-campaign-v1')
spec = importlib.util.spec_from_file_location('nex_v3_mac_isolation', BASE / 'isolation.py')
isolation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isolation)
HOST_ENV = {'PATH': '/usr/bin:/bin', 'HOME': '/nonexistent', 'LANG': 'C'}


def apple_macos_sysroot():
    result = subprocess.run(['/usr/bin/xcrun', '--sdk', 'macosx', '--show-sdk-path'],
                            env=HOST_ENV, capture_output=True, text=True, encoding='utf-8',
                            timeout=15, check=True)
    path = Path(result.stdout.strip())
    if not path.is_absolute() or not (path / 'SDKSettings.json').is_file():
        raise ValueError('selected Apple macOS SDK lacks SDKSettings.json')
    return path.resolve(strict=True)


def sdk_manifest(compiler):
    if compiler is None:
        return None
    executable = Path(compiler).resolve(strict=True)
    descriptor = executable.parent.parent / 'share/nex/sdk-host.json'
    return descriptor if descriptor.exists() else None


class PortableSDKToolchain:
    """Read the selected compiler's host configuration from a trusted host process."""
    def __init__(self, compiler, descriptor):
        self.resources = descriptor.parent
        self.root = self.resources.parents[1]
        self.manifest = self._inside(descriptor)
        env = {**HOST_ENV, 'NEX_RESOURCE_DIR': str(self.resources)}
        result = subprocess.run([compiler, 'doctor', '--json'], env=env, capture_output=True,
                                text=True, encoding='utf-8', timeout=30, check=True)
        doctor = json.loads(result.stdout)
        if doctor.get('schema') != 'nex.doctor/1' or doctor.get('sdk_manifest') != str(descriptor):
            raise ValueError('selected compiler did not report its portable SDK manifest')

        self.tools = set()
        self.files = {self.manifest}
        self.roots = set()
        for key in ('native_compiler', 'native_archiver', 'native_debug_packager', 'native_linker'):
            if doctor.get(key):
                path = self._inside(doctor[key])
                self.tools.update((path, path.resolve(strict=True)))
        for key in ('native_sqlite_include', 'native_openssl_include', 'native_sysroot'):
            if doctor.get(key):
                self.roots.add(self._inside(doctor[key], directory=True))
        for key in ('native_sqlite_library', 'native_openssl_ssl', 'native_openssl_crypto'):
            if doctor.get(key):
                path = self._inside(doctor[key])
                self.files.update((path, path.resolve(strict=True)))

        native = self._inside(doctor['native_compiler'])
        # Clang resolves its builtin includes next to the bundled driver.
        # Ask the driver instead of granting the whole LLVM or SDK prefix.
        resource = subprocess.run([native, '-print-resource-dir'], env=env, capture_output=True,
                                  text=True, encoding='utf-8', timeout=15, check=True).stdout.strip()
        self.roots.add(self._inside(resource, directory=True))
        # This is the libc++ header location in the macOS SDK assembler.
        headers = native.parent.parent / 'include/c++/v1'
        if headers.is_dir():
            self.roots.add(self._inside(headers, directory=True))
        lto = native.parent.parent / 'lib/libLTO.dylib'
        if lto.is_file():
            self.files.add(self._inside(lto))

        # The portable bundle uses the operator's Apple SDK and linker.
        # Resolve the developer selection before running the build subprocess.
        self.apple_sysroot = apple_macos_sysroot()

        linked_images = {self._inside(compiler), *self.tools}
        linked_images.update(path for path in self.files if path.suffix == '.dylib')
        pending, seen = list(linked_images), set()
        while pending:
            tool = pending.pop().resolve(strict=True)
            if tool in seen:
                continue
            seen.add(tool)
            dependencies, _ = isolation.image_paths(tool)
            for path in dependencies:
                if path.is_relative_to(self.root):
                    self.files.add(self._inside(path))
                    pending.append(path)

    def frozen_files(self):
        roots = self.roots | {self.resources / name for name in ('runtime', 'lib', 'debug')}
        files = self.files | self.tools | {self.apple_sysroot / 'SDKSettings.json'}
        for root in roots:
            for path in root.rglob('*'):
                if path.is_file():
                    files.add(self._inside(path))
        return files

    def _inside(self, value, *, directory=False):
        path = Path(value)
        real = path.resolve(strict=True)
        if (not path.is_absolute() or not path.is_relative_to(self.root)
                or real == self.root or not real.is_relative_to(self.root)
                or not (real.is_dir() if directory else real.is_file())):
            raise ValueError('portable SDK input must stay inside its selected installation')
        return path


class MacSDKBuildSandbox(isolation.MacSandbox):
    def __init__(self, *, compiler=None, cpp=None, resources=None):
        descriptor = sdk_manifest(compiler)
        sdk = PortableSDKToolchain(compiler, descriptor) if descriptor else None
        if sdk and cpp is None:
            cpp = '/usr/bin/clang++'
        super().__init__(compiler=compiler, cpp=cpp, resources=sdk.resources if sdk else resources)
        if sdk:
            if not any(sdk.apple_sysroot.is_relative_to(path) for path in self.compile_roots):
                raise ValueError('Apple SDK must belong to the selected developer toolchain')
            driver_prefix = self.cpp.resolve().parent.parent
            if driver_prefix.is_relative_to(sdk.root):
                self.roots.discard(driver_prefix)
            self.native_sysroot = sdk.apple_sysroot
            self.compile_files.update(sdk.files)
            self.compile_images.update(sdk.tools)
            self.compile_roots.update(sdk.roots)
