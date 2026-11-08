"""Qualify self-contained NEX FFI test images in fresh Windows AppContainers.

The supplied images must be checked test applications that exercise the selected
catalogue and exit zero on success. This is a host acceptance tool, not automatic
sandboxing of arbitrary projects or complete SDK acceptance.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import time
import traceback

from appcontainer import Profile, sha


def copy_bundle(source, target, expected):
    if source.is_symlink() or source.lstat().st_file_attributes & 0x400:
        raise ValueError('bundle root is a link/reparse point')
    metadata = source / 'manifest.json'
    if metadata.is_symlink() or metadata.lstat().st_file_attributes & 0x400:
        raise ValueError('bundle manifest is a link/reparse point')
    raw = metadata.read_bytes()
    if len(raw) > 1048576 or hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError('bundle manifest differs from the selected catalogue')
    manifest = json.loads(raw.decode('utf-8'))
    members = manifest.get('files')
    if manifest.get('schema') != 'nex.foreign-bundle/1' or not isinstance(members, list) or not 0 < len(members) <= 4096:
        raise ValueError('expected a bounded native foreign bundle')
    target.mkdir()
    (target / 'manifest.json').write_bytes(raw)
    total, seen, pins = 0, {'manifest.json'}, {str(source / 'manifest.json'): expected}
    for member in members:
        name, digest = member['path'], member['sha256']
        if (not isinstance(name, str) or not name or len(name.encode('utf-8')) > 4096
                or any(c in name for c in ('\\', ':', '\0')) or name.endswith('/')
                or not re.fullmatch('[0-9a-f]{64}', digest)):
            raise ValueError('invalid pinned bundle member')
        parts = name.split('/')
        if len(parts) > 128 or any(p in ('', '.', '..') or len(p.encode('utf-8')) > 255 for p in parts):
            raise ValueError('invalid relative bundle member')
        relative = PurePosixPath(name)
        if relative.is_absolute() or name in seen:
            raise ValueError('absolute/duplicate bundle member')
        seen.add(name)
        path = source
        for part in parts:
            path /= part
            if path.is_symlink() or path.lstat().st_file_attributes & 0x400:
                raise ValueError('bundle member traverses a link/reparse point')
        size = path.stat().st_size
        total += size
        if not path.is_file() or size > 64*1024**2 or total > 256*1024**2 or sha(path) != digest:
            raise ValueError('bundle member differs or exceeds its size limit')
        output = target.joinpath(*parts)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, output)
        if sha(output) != digest or sha(path) != digest:
            raise ValueError('bundle member changed during copy')
        pins[str(path)] = digest
    return pins


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--observer', type=Path, required=True)
    parser.add_argument('--debug', type=Path, required=True)
    parser.add_argument('--release', type=Path, required=True)
    parser.add_argument('--foreign', type=Path, required=True)
    parser.add_argument('--outside-catalogue', type=Path,
                        help='Optional existing private catalogue whose OS read denial must be tested without changing its ACL')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.name != 'nt':
        parser.error('native Windows is required')
    root = args.output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    started, profiles = time.monotonic(), []
    report = {'schema': 'nex.windows-native-AppContainer-FFI/1', 'ok': False,
              'state': 'preflight', 'controller_python': sys.version, 'controller_pid': os.getpid(),
              'cases': [], 'full_SDK_accepted': False, 'original_ACLs_or_network_policy_changed': False}
    def save():
        report['seconds'] = time.monotonic() - started
        temporary = root / 'report.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(root / 'report.json')
    try:
        helper = args.observer.resolve(strict=True)
        catalogue = args.foreign.resolve(strict=True)
        raw = catalogue.read_bytes()
        if len(raw) > 1048576:
            raise ValueError('foreign catalogue exceeds 1MiB')
        host = json.loads(raw.decode('utf-8'))
        libraries = host.get('libraries')
        if host.get('schema') != 'nex.foreign-host/1' or not isinstance(libraries, dict) or not 0 < len(libraries) <= 128:
            raise ValueError('expected a bounded foreign catalogue')
        inputs = root / 'inputs'
        inputs.mkdir()
        applications = inputs / 'applications'
        applications.mkdir()
        pins, modules = {str(catalogue): sha(catalogue)}, {}
        for name, image in [('debug', args.debug), ('release', args.release)]:
            image = image.resolve(strict=True)
            if not image.is_file() or image.stat().st_size > 128*1024**2:
                raise ValueError('self-contained test image must be at most128MiB')
            digest = sha(image)
            shutil.copyfile(image, applications / (name + '.exe'))
            assert sha(image) == sha(applications / (name + '.exe')) == digest
            pins[str(image)] = digest
        for index, (name, grant) in enumerate(libraries.items()):
            directory = Path(grant['directory'])
            if not directory.is_absolute():
                directory = catalogue.parent / directory
            target = inputs / ('module-' + str(index))
            pins.update(copy_bundle(directory, target, grant['manifest_sha256']))
            modules[name] = target
        if args.outside_catalogue:
            outside = args.outside_catalogue.resolve(strict=True)
            pins[str(outside)] = sha(outside)
        catalogues, apps = [], []
        for index in range(2):
            profile = Profile()
            profiles.append(profile)
            profile.create()
            apps.append(profile.copy_tree(applications, 'applications', max_files=2, max_bytes=256*1024**2))
            local = json.loads(json.dumps(host))
            for number, (name, source) in enumerate(modules.items()):
                module = profile.copy_tree(source, 'module-' + str(number),
                                           max_files=4097, max_bytes=257*1024**2)
                local['libraries'][name]['directory'] = str(module)
            staged = inputs / ('catalogue-' + str(index))
            staged.mkdir()
            (staged / 'host.json').write_text(json.dumps(local, indent=2) + '\n')
            catalogues.append(profile.copy_tree(staged, 'configuration', max_files=1, max_bytes=1048576) / 'host.json')
        active = profiles[0]
        environment = {k: v for k, v in os.environ.items()
                       if not k.startswith(('NEX_', 'PYTHON', 'OPENSSL_', 'SSL_'))}
        environment['PATH'] = 'C:/Windows/System32;C:/Windows'
        environment = active.native_environment(environment)
        cases = [('missing-grant', [apps[0] / 'debug.exe'], False, 'E_FFI_'),
                 ('opposite-profile-denied', [apps[0] / 'debug.exe', '--nex-foreign', catalogues[1]], False, 'E_FFI_IO'),
                 ('local-debug', [apps[0] / 'debug.exe', '--nex-foreign', catalogues[0]], True, ''),
                 ('local-release', [apps[0] / 'release.exe', '--nex-foreign', catalogues[0]], True, '')]
        if args.outside_catalogue:
            cases.insert(1, ('outside-private-catalogue-denied',
                            [apps[0] / 'debug.exe', '--nex-foreign', outside], False, 'E_FFI_IO'))
        for name, command, success, diagnostic in cases:
            report['state'] = name
            save()
            output = root / 'observations' / name
            observation = active.run(list(map(str, command)), output, environment, observer=helper, timeout=60)
            stdout = (output / 'stdout').read_text(encoding='utf-8', errors='replace')
            stderr = (output / 'stderr').read_text(encoding='utf-8', errors='replace')
            report['cases'].append({'name': name, 'observation': observation,
                                    'stdout': stdout, 'stderr': stderr})
            save()
            assert not observation['timed_out'] and observation['active_job_processes'] == 0
            assert observation['appcontainer_verified_before_resume'] and observation['appcontainer_capabilities'] == []
            assert ((observation['parent_exit_code'] == 0) if success
                    else (observation['parent_exit_code'] != 0 and diagnostic in stdout + stderr)), name
            assert not list(active.temp.iterdir()), 'native snapshot cleanup retained temporary files'
            for profile in profiles:
                profile.verify_copies()
        assert all(sha(Path(path)) == digest for path, digest in pins.items())
        report.update(ok=True, state='native-debug-release-denials-and-snapshot-cleanup-passed',
                      original_pins=pins, native_Temp_empty_after_every_case=True)
    except BaseException as error:
        report.update(state='failed', error=repr(error)[:2000], traceback=traceback.format_exc()[-5000:])
    finally:
        for profile in reversed(profiles):
            try:
                profile.close()
                if profile.created:
                    assert profile.deleted and not profile.path.exists()
                    parent = profile.path.parent
                    assert parent.name.casefold() == profile.name.casefold()
                    if parent.exists():
                        parent.rmdir()
            except BaseException as error:
                report.setdefault('cleanup_errors', []).append({'profile': profile.name, 'error': repr(error)[:1000]})
        report['profiles'] = [{'name': p.name, 'SID': p.sid, 'deleted': p.deleted,
                               'path': str(p.path) if p.path else None,
                               'parent_absent': p.path is not None and not p.path.parent.exists()} for p in profiles]
        if report.get('cleanup_errors') or not all(not p.created or (p.deleted and not p.path.parent.exists()) for p in profiles):
            report.update(ok=False, state='failed-cleanup')
        save()
    print(json.dumps({k: report.get(k) for k in ['ok', 'state', 'error', 'seconds', 'cleanup_errors']}))
    return 0 if report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
