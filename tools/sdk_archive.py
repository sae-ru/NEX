"""Inventory-preserving SDK archives shared by distribution workflows."""
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile

MANIFEST = 'share/nex/sdk-bundle.json'
MAX_FILES = 100000
MAX_BYTES = 16 * 1024**3


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''):
            value.update(block)
    return value.hexdigest()


def relative(name):
    if (not isinstance(name, str) or not name or '\\' in name or '\0' in name or
            name.startswith('/') or any(part in ('', '.', '..') for part in name.split('/'))):
        raise ValueError('SDK paths must be canonical relative POSIX paths: ' + repr(name))
    try:
        name.encode('utf-8', 'strict')
    except UnicodeError as error:
        raise ValueError('SDK paths require Unicode scalar text') from error
    return PurePosixPath(name)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate SDK manifest key: ' + key)
        result[key] = value
    return result


def inventory(sdk, allow_python_cache=True):
    sdk = Path(sdk).resolve(strict=True)
    path = sdk / MANIFEST
    if any(parent.is_symlink() for parent in (sdk/'share', sdk/'share/nex')):
        raise ValueError('SDK manifest has a symlink ancestor')
    if not stat.S_ISREG(path.lstat().st_mode) or path.stat().st_size > 16 * 1024**2:
        raise ValueError('SDK manifest must be a bounded regular file')
    manifest = json.loads(path.read_text(encoding='utf-8'), object_pairs_hook=unique_object)
    if not isinstance(manifest, dict):
        raise ValueError('SDK manifest must be an object')
    files = manifest.get('files')
    if (manifest.get('schema') != 'nex.sdk-bundle/1' or manifest.get('ok') is not True or
            not isinstance(files, dict) or not files or len(files) > MAX_FILES or MANIFEST in files):
        raise ValueError('expected an assembled SDK with an exact file inventory')
    if (not isinstance(manifest.get('toolchain'), str) or
            not re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+(?:[-+][A-Za-z0-9.-]+)?', manifest['toolchain'])):
        raise ValueError('invalid SDK toolchain version')
    selected = set(files) | {MANIFEST}
    total = 0
    for name, item in files.items():
        relative(name)
        if not isinstance(item, dict):
            raise ValueError('invalid SDK file metadata: ' + name)
        candidate = sdk / name
        for parent in candidate.parents:
            if parent == sdk:
                break
            if parent.is_symlink():
                raise ValueError('SDK file has a symlink ancestor: ' + name)
        mode = candidate.lstat().st_mode
        if 'symlink' in item:
            if set(item) != {'symlink'}:
                raise ValueError('SDK link metadata must contain only its target')
            target = item['symlink']; relative(target)
            if not stat.S_ISLNK(mode) or str(candidate.readlink()) != target:
                raise ValueError('SDK link differs: ' + name)
            resolved = candidate.resolve(strict=True)
            if sdk not in resolved.parents or not resolved.is_file():
                raise ValueError('SDK link does not resolve to an owned regular file: ' + name)
            if str(resolved.relative_to(sdk)) not in files:
                raise ValueError('SDK link target is outside its inventory: ' + name)
        else:
            size, checksum, executable = item.get('bytes'), item.get('sha256'), item.get('executable')
            if (type(size) is not int or size < 0 or not isinstance(checksum, str) or
                    not re.fullmatch('[0-9a-f]{64}', checksum) or type(executable) is not bool):
                raise ValueError('invalid SDK file size/hash/mode: ' + name)
            total += size
            if total > MAX_BYTES or not stat.S_ISREG(mode) or mode & 0o7000:
                raise ValueError('SDK file kind, privilege bits or total size is invalid: ' + name)
            if candidate.stat().st_size != size or bool(mode & 0o111) != executable or digest(candidate) != checksum:
                raise ValueError('SDK bytes or executable mode differ: ' + name)
    extras = []
    for directory, folders, names in os.walk(sdk, followlinks=False):
        for name in [*folders, *names]:
            candidate = Path(directory) / name
            if candidate.is_dir() and not candidate.is_symlink():
                continue
            key = str(candidate.relative_to(sdk))
            if key not in selected:
                if (allow_python_cache and candidate.is_file() and not candidate.is_symlink() and
                        '__pycache__' in candidate.relative_to(sdk).parts and candidate.suffix == '.pyc'):
                    extras.append(key)
                else:
                    raise ValueError('unmanifested SDK file: ' + key)
    return manifest, selected, sorted(extras)


def create(sdk, archive, name):
    sdk, archive = Path(sdk).resolve(strict=True), Path(archive)
    if len(relative(name).parts) != 1:
        raise ValueError('archive root must be one directory name')
    manifest, selected, extras = inventory(sdk)
    directories = {''}
    for key in selected:
        directories.update(str(p) for p in PurePosixPath(key).parents if str(p) != '.')
    with archive.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as compressed:
            with tarfile.open(fileobj=compressed, mode='w', format=tarfile.PAX_FORMAT) as output:
                for key in sorted(directories):
                    info = tarfile.TarInfo(name + ('/' + key if key else ''))
                    info.type = tarfile.DIRTYPE; info.mode = 0o755; output.addfile(info)
                for key in sorted(selected):
                    path = sdk / key
                    info = output.gettarinfo(str(path), arcname=name + '/' + key)
                    info.uid = info.gid = 0; info.uname = info.gname = ''; info.mtime = 0; info.pax_headers = {}
                    info.mode = 0o755 if bool(path.lstat().st_mode & 0o111) else 0o644
                    if info.issym():
                        output.addfile(info)
                    else:
                        with path.open('rb') as source:
                            output.addfile(info, source)
    return {'path': str(archive.resolve()), 'sha256': digest(archive), 'bytes': archive.stat().st_size,
            'files_in_inventory': len(manifest['files']), 'excluded_python_cache_files': extras}


def restore(archive, destination, expected_sha256):
    archive, destination = Path(archive), Path(destination)
    if not re.fullmatch('[0-9a-f]{64}', expected_sha256) or digest(archive) != expected_sha256:
        raise ValueError('SDK archive checksum differs')
    if destination.exists():
        raise ValueError('archive destination must be new')
    with tarfile.open(archive, 'r:gz') as source:
        members = []
        for item in source:
            members.append(item)
            if len(members) > MAX_FILES * 3:
                raise ValueError('SDK archive member count exceeds its bound')
        if not members:
            raise ValueError('SDK archive member count exceeds its bound')
        rows, total = {}, 0
        for item in members:
            path = relative(item.name)
            if str(path) in rows or item.type not in (tarfile.REGTYPE, tarfile.AREGTYPE, tarfile.DIRTYPE, tarfile.SYMTYPE):
                raise ValueError('duplicate or unsupported SDK archive member: ' + item.name)
            if item.size < 0 or item.mode & 0o7000 or set(item.pax_headers) - {'path', 'linkpath'}:
                raise ValueError('unsafe SDK archive metadata: ' + item.name)
            total += item.size
            if total > MAX_BYTES:
                raise ValueError('SDK archive exceeds its uncompressed byte bound')
            if not item.isfile() and item.size:
                raise ValueError('SDK archive non-file carries data')
            if item.issym():
                relative(item.linkname)
            rows[str(path)] = item
        roots = {relative(key).parts[0] for key in rows}
        if len(roots) != 1:
            raise ValueError('SDK archive must contain exactly one top directory')
        top = next(iter(roots))
        if top not in rows or not rows[top].isdir() or top + '/' + MANIFEST not in rows:
            raise ValueError('SDK archive lacks its directory or manifest')
        for key, item in rows.items():
            for parent in PurePosixPath(key).parents:
                if str(parent) != '.' and (str(parent) not in rows or not rows[str(parent)].isdir()):
                    raise ValueError('SDK archive member has a non-directory ancestor: ' + key)
            if item.issym():
                target, visited = str(PurePosixPath(key).parent / item.linkname), {key}
                while target in rows and rows[target].issym():
                    if target in visited or len(visited) > 128:
                        raise ValueError('SDK archive contains a symlink cycle')
                    visited.add(target)
                    target = str(PurePosixPath(target).parent / rows[target].linkname)
                if target not in rows or not rows[target].isfile():
                    raise ValueError('SDK archive link target must be an archived regular file')
        destination.mkdir(parents=True)
        source.extractall(destination, members=members)
    sdk = destination / top
    inventory(sdk, allow_python_cache=False)
    return sdk
