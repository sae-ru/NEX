"""Build one committed source snapshot through the maintained SDK workflows.

plan is read-only. run requires a new output directory, retains failed phases,
and never publishes a release or retries/replaces earlier evidence.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import time

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            result.update(block)
    return result.hexdigest()


def decode(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate configuration key: ' + key)
            result[key] = value
        return result
    def invalid(value):
        raise ValueError('nonfinite JSON constant: ' + value)
    return json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=invalid)


def git(source, *args):
    return subprocess.check_output(['git', '-C', str(source), *args], stderr=subprocess.PIPE, env=git_environment())


def git_environment():
    return dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_NO_REPLACE_OBJECTS='1',
                GIT_TERMINAL_PROMPT='0', GIT_OPTIONAL_LOCKS='0')


def selected_tool(value):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ValueError('select a nonempty executable path/name')
    found = shutil.which(str(value))
    if not found:
        raise ValueError('selected executable is unavailable: ' + str(value))
    return str(Path(found).resolve(strict=True))


def notice_inputs(path, output):
    # Reuse the assembler's pure provenance loader; do not create bundle files.
    spec = importlib.util.spec_from_file_location('nex_build_notices', ROOT/'tools/sdk_bundle.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    selected = module.Bundle(output/'installed', output/'distribution', path)
    licenses = {}
    for component in selected.components['components']:
        for name in component['license_files']:
            license = Path(name)
            license.read_text(encoding='utf-8', errors='strict')
            licenses[str(license)] = digest(license)
    return licenses


def plan(config, source, output):
    config, source, output = Path(config).resolve(strict=True), Path(source).resolve(strict=True), Path(output).resolve()
    if output.exists():
        raise ValueError('output must be new; previous attempts are retained')
    raw = config.read_bytes()
    value = decode(raw)
    keys = {'schema', 'target', 'jobs', 'cmake', 'cmake_definitions', 'notices', 'npm_cache',
            'deny_read', 'node', 'npm', 'live', 'skip_image_build', 'image', 'expected_commit'}
    if not isinstance(value, dict) or value.get('schema') != 'nex.sdk-build/1' or set(value) - keys:
        raise ValueError('expected nex.sdk-build/1 with known configuration keys')
    target = value.get('target')
    if target not in ('macos-native', 'linux-arm64', 'linux-amd64'):
        raise ValueError('select macos-native/linux-arm64/linux-amd64; Windows distribution remains pending')
    if target == 'macos-native' and platform.system() != 'Darwin':
        raise ValueError('macos-native requires a macOS host')
    jobs = value.get('jobs', 4)
    if type(jobs) is not int or not 1 <= jobs <= 8:
        raise ValueError('jobs must be1..8')
    for flag in ('live', 'skip_image_build'):
        if flag in value and type(value[flag]) is not bool:
            raise ValueError(flag + ' must be boolean')
    if target.startswith('linux') and value.get('live'):
        raise ValueError('portable Linux workflow does not qualify a live debugger')
    git_root = Path(git(source, 'rev-parse', '--show-toplevel').decode().strip()).resolve(strict=True)
    if git_root != source or not git_root.samefile(source):
        raise ValueError('source must be the Git checkout root')
    commit = git(source, 'rev-parse', 'HEAD').decode().strip()
    if not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('expected a committed SHA1 Git source identity')
    if git(source, 'diff', '--no-ext-diff', '--no-textconv', '--name-only', 'HEAD', '--'):
        raise ValueError('commit tracked source changes before building an SDK')
    if value.get('expected_commit', commit) != commit:
        raise ValueError('source differs from expected_commit')
    entries = git(source, 'ls-tree', '-rz', commit).split(b'\0')
    tracked = []
    for entry in entries:
        if not entry:
            continue
        metadata, name = entry.split(b'\t', 1)
        if metadata.split()[0] not in (b'100644', b'100755'):
            raise ValueError('source snapshot requires regular tracked files, without symlinks/submodules')
        key = name.decode('utf-8', errors='strict')
        path = PurePosixPath(key)
        if path.is_absolute() or any(p in ('', '.', '..') for p in key.split('/')) or '\\' in key:
            raise ValueError('source path is not portable: ' + key)
        tracked.append(key)
    required = {'CMakeLists.txt', 'llm/language-pack.json', 'include/nex/language.h', 'tools/sdk_build.py'}
    if not required <= set(tracked) or len(tracked) > 100000:
        raise ValueError('source is not the current NEX SDK-build checkout')
    cmake = git(source, 'show', commit + ':CMakeLists.txt').decode('utf-8')
    try:
        version_text = git(source, 'show', commit + ':VERSION').decode('utf-8').strip()
        version = (version_text, version_text) if re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', version_text) else None
    except subprocess.CalledProcessError:
        version = re.search(r'project\(NEX VERSION ([0-9.]+)', cmake)
    pack = decode(git(source, 'show', commit + ':llm/language-pack.json'))
    header = git(source, 'show', commit + ':include/nex/language.h').decode('utf-8')
    language = re.search(r'languageVersion\s*=\s*"([^"]+)"', header)
    if not version or not language or pack.get('language_version') != language[1]:
        raise ValueError('committed compiler and language metadata disagree')
    result = {'schema': 'nex.sdk-build-plan/1', 'source': str(source), 'source_commit': commit,
              'source_tree': git(source, 'rev-parse', commit + '^{tree}').decode().strip(),
              'tracked_files': len(tracked), 'toolchain': version[1], 'language': language[1],
              'target': target, 'jobs': jobs, 'output': str(output), 'config': str(config),
              'config_sha256': hashlib.sha256(raw).hexdigest(), 'options': value,
              'python': str(Path(sys.executable).resolve()), 'no_network_during_plan': True,
              'release_qualification': False}
    if target == 'macos-native':
        if {'image', 'skip_image_build'} & value.keys():
            raise ValueError('container options are Linux-only')
        result['cmake'] = selected_tool(value.get('cmake', 'cmake'))
        result['node'] = selected_tool(value.get('node', 'node'))
        # Keep npm's launcher spelling: npm can be a script whose sibling node is used.
        npm = value.get('npm', 'npm')
        if not isinstance(npm, str) or not npm or '\0' in npm:
            raise ValueError('select a nonempty npm launcher path/name')
        result['npm'] = str(Path(shutil.which(npm) or '').absolute())
        if not Path(result['npm']).is_file():
            raise ValueError('selected npm launcher is unavailable')
        definitions = value.get('cmake_definitions', {})
        if not isinstance(definitions, dict):
            raise ValueError('cmake_definitions must be an object')
        for key, text in definitions.items():
            if (not isinstance(key, str) or not re.fullmatch('[A-Za-z_][A-Za-z_0-9]*', key) or not isinstance(text, str) or '\0' in text or
                    key in ('CMAKE_INSTALL_PREFIX', 'CMAKE_HOME_DIRECTORY', 'CMAKE_BUILD_TYPE')):
                raise ValueError('invalid/reserved CMake definition: ' + key)
        roots = value.get('deny_read', [])
        if not isinstance(roots, list) or any(not isinstance(p, str) for p in roots):
            raise ValueError('deny_read must be a path list')
        result['deny_read'] = []
        for root in roots:
            path = (config.parent / root).resolve(strict=True)
            if not path.is_dir() or path == Path(path.anchor):
                raise ValueError('deny_read requires existing non-root directories')
            result['deny_read'].append(str(path))
        for name in ('notices', 'npm_cache'):
            text = value.get(name)
            if not isinstance(text, str) or not text:
                raise ValueError('macos-native requires ' + name)
            path = (config.parent / text).resolve(strict=True)
            if not (path.is_file() if name == 'notices' else path.is_dir()):
                raise ValueError('invalid ' + name)
            result[name] = str(path)
        result['notices_sha256'] = digest(result['notices'])
        result['notice_license_sha256'] = notice_inputs(Path(result['notices']), output)
        denied = [source, output/'source', output/'build', output/'installed',
                  *map(Path, result['deny_read'])]
        for name in ('python', 'node', 'npm'):
            tool = Path(result[name]).resolve(strict=True)
            if any(tool == root or root in tool.parents for root in denied):
                raise ValueError(name + ' must be outside source/build/dependency read-denial roots')
    else:
        if set(value) & {'cmake', 'cmake_definitions', 'notices', 'npm_cache', 'deny_read', 'node', 'npm'}:
            raise ValueError('native host dependency options are macOS-only; Linux uses the pinned container')
        result['docker'] = selected_tool('docker')
        if 'image' in value and (not isinstance(value['image'], str) or not value['image'] or value['image'].startswith('-')):
            raise ValueError('image must be an explicit Docker image reference')
    return result


def export_source(source, commit, archive, destination):
    with Path(archive).open('xb') as stream:
        subprocess.run(['git', '-C', str(source), 'archive', '--format=tar', commit],
                       stdout=stream, check=True, env=git_environment())
    destination = Path(destination)
    destination.mkdir()
    files = {}
    with tarfile.open(archive, 'r:') as contents:
        for item in contents:
            parts = item.name.rstrip('/').split('/')
            if (item.name.startswith('/') or any(p in ('', '.', '..') for p in parts) or
                    '\\' in item.name or item.mode & 0o7000 or not (item.isdir() or item.isfile())):
                raise ValueError('unsupported source archive member: ' + item.name)
            target = destination.joinpath(*parts)
            if item.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with contents.extractfile(item) as original, target.open('xb') as copied:
                    shutil.copyfileobj(original, copied)
                target.chmod(0o755 if item.mode & 0o111 else 0o644)
                files['/'.join(parts)] = {'bytes': item.size, 'sha256': digest(target),
                                         'executable': bool(item.mode & 0o111)}
    return files


def verify_source(root, files):
    observed = {p.relative_to(root).as_posix() for p in Path(root).rglob('*') if p.is_file() or p.is_symlink()}
    if observed != set(files):
        raise ValueError('snapshot file inventory changed')
    for name, row in files.items():
        path = Path(root) / name
        if (not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size != row['bytes'] or
                bool(path.stat().st_mode & 0o111) != row['executable'] or digest(path) != row['sha256']):
            raise ValueError('snapshot changed: ' + name)


class Build:
    def __init__(self, selected):
        self.plan = selected
        self.output = Path(selected['output'])
        self.output.mkdir(parents=True, exist_ok=False)
        self.report = {'schema': 'nex.sdk-build/1', 'ok': False, 'plan': selected, 'phases': [],
                       'release_qualification': False, 'physical_devices_qualified': False}
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith(
            ('NEX_', 'PYTHON', 'DYLD_', 'LD_', 'CTEST_', 'CMAKE_')) and k not in ('DESTDIR', 'CC', 'CXX')}
        self.environment['PYTHONDONTWRITEBYTECODE'] = '1'
        self.save()

    def save(self):
        (self.output / 'report.json').write_text(json.dumps(self.report, indent=2) + '\n', encoding='utf-8')

    def command(self, name, argv):
        row = {'name': name, 'command': list(map(str, argv)), 'status': 'running'}
        self.report['phases'].append(row)
        self.save()
        started = time.monotonic()
        try:
            with (self.output / (name + '.stdout')).open('wb') as stdout, \
                 (self.output / (name + '.stderr')).open('wb') as stderr:
                result = subprocess.run(row['command'], cwd=self.output, env=self.environment,
                                        stdout=stdout, stderr=stderr)
            row.update(exit_code=result.returncode, status='passed' if result.returncode == 0 else 'failed')
            if result.returncode:
                raise RuntimeError(name + ' failed; inspect retained stdout/stderr')
        except BaseException as error:
            row.update(status='failed', error=type(error).__name__ + ': ' + str(error))
            raise
        finally:
            row['seconds'] = round(time.monotonic() - started, 3)
            self.save()

    def run(self):
        started = time.monotonic()
        source = self.output / 'source'
        options = self.plan['options']
        python = self.plan['python']
        try:
            files = export_source(self.plan['source'], self.plan['source_commit'], self.output / 'source.tar', source)
            if len(files) != self.plan['tracked_files']:
                raise ValueError('exported snapshot differs from committed file count')
            self.report['source_inventory'] = files
            self.save()
            if digest(self.plan['config']) != self.plan['config_sha256']:
                raise ValueError('build configuration changed after planning')
            if self.plan['target'].startswith('linux'):
                arch = self.plan['target'].split('-')[1]
                check = [python, '-B', source / 'tools/linux/check.py', '--source', source,
                         '--output', self.output / 'linux', '--tier', 'full', '--arch', arch,
                         '--jobs', self.plan['jobs']]
                if options.get('skip_image_build'):
                    check.append('--skip-image-build')
                if options.get('image'):
                    check += ['--image', options['image']]
                self.command('source-and-installed', check)
                status = decode((self.output / 'linux/verification.json').read_bytes())
                if status.get('ok') is not True or status.get('tier') != 'full' or status.get('ctest', {}).get('ok') is not True:
                    raise ValueError('complete source/installed verification did not pass')
                image = decode((self.output / 'linux/environment.json').read_bytes())['image_id']
                self.command('distribution', [python, '-B', source / 'tools/linux/bundle.py', '--source', source,
                    '--sdk', self.output / 'linux/sdk', '--output', self.output / 'distribution',
                    '--arch', arch, '--toolchain-image', image])
            else:
                if digest(self.plan['notices']) != self.plan['notices_sha256']:
                    raise ValueError('notice catalogue changed after planning')
                build, installed = self.output / 'build', self.output / 'installed'
                definitions = {**options.get('cmake_definitions', {}), 'CMAKE_BUILD_TYPE': 'Release',
                    'Python3_EXECUTABLE': python, 'NEX_PACKAGE_NOTICES_FILE': self.plan['notices']}
                configure = [self.plan['cmake'], '-S', source, '-B', build]
                configure += ['-D' + key + '=' + text for key, text in sorted(definitions.items())]
                self.command('configure', configure)
                self.command('build', [self.plan['cmake'], '--build', build, '-j', self.plan['jobs']])
                dependencies = self.output / 'web-dependencies'
                dependencies.mkdir()
                for name in ('package.json', 'package-lock.json'):
                    shutil.copyfile(source / 'web' / name, dependencies / name)
                self.environment.update(NEX_NODE=self.plan['node'], NEX_NPM=self.plan['npm'],
                    NEX_NPM_CACHE=self.plan['npm_cache'], npm_config_offline='true')
                self.environment['PATH'] = str(Path(self.plan['node']).parent) + os.pathsep + self.environment.get('PATH', '')
                self.command('locked-web', [self.plan['npm'], '--prefix', dependencies, 'ci', '--offline',
                    '--cache', self.plan['npm_cache'], '--ignore-scripts', '--no-audit', '--no-fund'])
                self.environment['NEX_TSC'] = str(dependencies / 'node_modules/typescript/bin/tsc')
                self.command('source-tests', [python, '-B', source / 'tools/ci/ctest.py', '--build', build,
                    '--output', self.output / 'source-tests', '--tier', 'full', '--jobs', str(self.plan['jobs']),
                    '--ctest', Path(self.plan['cmake']).with_name('ctest')])
                self.command('install', [self.plan['cmake'], '--install', build, '--prefix', installed])
                # Installed acceptance prepares its own locked TypeScript tool.
                # The source-test compiler can be inside a denied source root.
                self.environment.pop('NEX_TSC', None)
                roots = list(dict.fromkeys([self.plan['source'], str(source), str(build), str(installed), *self.plan['deny_read']]))
                argv = [python, '-B', source / 'tools/macos/bundle.py', '--sdk', installed,
                    '--notices', self.plan['notices'], '--output', self.output / 'distribution',
                    '--npm-cache', self.plan['npm_cache'], '--node', self.plan['node'],
                    '--npm', self.plan['npm'], '--python', python]
                for root in roots:
                    argv += ['--deny-read', root]
                for probe in (Path(self.plan['source']) / 'LICENSE', source / 'LICENSE', build / 'CMakeCache.txt'):
                    argv += ['--deny-probe', probe]
                if options.get('live'):
                    argv.append('--live')
                self.command('distribution', argv)
            distribution = decode((self.output / 'distribution/verification.json').read_bytes())
            archive = distribution.get('archive', {})
            if distribution.get('ok') is not True or not archive or digest(archive['path']) != archive['sha256']:
                raise ValueError('distribution archive did not pass its maintained workflow')
            verify_source(source, files)
            if digest(self.plan['config']) != self.plan['config_sha256']:
                raise ValueError('build configuration changed during execution')
            if self.plan['target'] == 'macos-native':
                if digest(self.plan['notices']) != self.plan['notices_sha256'] or any(
                        digest(path) != pin for path, pin in self.plan['notice_license_sha256'].items()):
                    raise ValueError('notice inputs changed during execution')
            self.report.update(ok=True, archive=archive, distribution_report_sha256=digest(
                self.output / 'distribution/verification.json'), source_snapshot_unchanged=True)
        except BaseException as error:
            self.report['error'] = type(error).__name__ + ': ' + str(error)
            raise
        finally:
            self.report['seconds'] = round(time.monotonic() - started, 3)
            self.save()
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'run'))
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        selected = plan(args.config, args.source, args.output)
        result = selected if args.action == 'plan' else Build(selected).run()
        print(json.dumps(result if args.action == 'plan' else
            {key: result[key] for key in ('ok', 'archive', 'seconds', 'release_qualification')}, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
