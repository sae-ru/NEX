"""Explicit operator provenance for source-built application package fixtures."""
import hashlib
import json
from pathlib import Path
import sys


_selected = None
if '--package-notices' in sys.argv:
    at = sys.argv.index('--package-notices')
    path = Path(sys.argv[at + 1]).resolve(strict=True)
    if not path.is_file():
        raise ValueError('--package-notices must name a file')
    _selected = path, hashlib.sha256(path.read_bytes()).hexdigest()
    del sys.argv[at:at + 2]


def selected():
    if _selected is None:
        return None
    path, digest = _selected
    if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError('operator package notice catalogue changed during the test')
    return path


def flags():
    path = selected()
    return ['--notices', str(path)] if path else []


def retain(destination, extra=None):
    """Keep complete notices inside a task project, with exact vendor roots."""
    path = selected()
    if path is None:
        return extra
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False)
    result = {'schema': 'nex.sdk-notices/1', 'components': []}
    for catalogue in [path, *([Path(extra)] if extra else [])]:
        value = json.loads(catalogue.read_bytes())
        if value['schema'] != result['schema']:
            raise ValueError('expected nex.sdk-notices/1')
        for component in value['components']:
            row = dict(component)
            row['roots'] = [str((catalogue.parent / p).resolve(strict=True)) for p in component['roots']]
            row['license_files'] = []
            for name in component['license_files']:
                source = (catalogue.parent / name).resolve(strict=True)
                data = source.read_bytes()
                data.decode('utf-8', errors='strict')
                target = destination / (str(len(result['components'])) + '-' + str(len(row['license_files'])) + '.txt')
                target.write_bytes(data)
                row['license_files'].append(target.name)
            result['components'].append(row)
    selected()
    output = destination / 'notices.json'
    output.write_text(json.dumps(result, indent=2) + '\n', newline='\n')
    return output
