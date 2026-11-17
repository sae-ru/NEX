#!/usr/bin/env python3
"""Run the local study with its fourth frozen response-envelope policy."""
import importlib.util
from pathlib import Path
import signal

HERE = Path(__file__).resolve().parent
PREVIOUS = HERE.with_name('llm-campaign-v3')
spec = importlib.util.spec_from_file_location('nex_v4_previous_engine', PREVIOUS / 'collector.py')
v3 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v3)
engine = v3.engine
engine.__doc__ = __doc__
strict_model_object = engine.model_object


def model_object(text):
    """Treat a lone opening tool tag as framing only for a complete action."""
    raw = text.strip()
    opening, closing = '<tool_call>', '</tool_call>'
    if raw.startswith(opening) and not raw.endswith(closing):
        body = raw[len(opening):].lstrip()
        if not body.startswith('{'):
            raise ValueError('opening-only tool tag requires one complete JSON action object')
        # Parse the complete remainder. Trailing content, duplicate keys,
        # partial JSON and a second packet still fail the inherited decoder.
        packet = strict_model_object(body)
        if type(packet.get('action')) is not str:
            raise ValueError('opening-only tool tag requires one complete JSON action object')
        return packet
    return strict_model_object(raw)


def read_freeze(root):
    return v3.acceptance.decode(engine.checked_file(root / 'freeze.json'))


def verify(root, *, deep=False):
    root = Path(root).resolve(strict=True)
    value = read_freeze(root)
    if (value.get('schema') != 'nex.local-collection/4'
            or value.get('study_protocol_version') != 4
            or value.get('collector_policy_version') != 7
            or value.get('source_language') != '0.30'):
        raise ValueError('version4 requires a new freeze; historical campaigns stay in their own runner')
    if (root / 'freeze.sha256').read_text().strip() != engine.sha(root / 'freeze.json'):
        raise ValueError('collection freeze changed')

    def unchanged(row, check_digest=False):
        path = Path(row['path'])
        info = path.stat()
        signature = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        expected = tuple(row[k] for k in ('dev', 'ino', 'bytes', 'mtime_ns'))
        return (path.is_symlink() == row['symlink'] and str(path.resolve()) == row['resolved']
                and signature == expected and (not check_digest or engine.sha(path) == row['sha256']))

    for row in value['pinned_files']:
        if not unchanged(row, deep):
            raise ValueError('frozen input changed: ' + row['path'])
    engine.r.verify_weights(root / 'weights.json')
    if not all(unchanged(row) for row in value['host']['files']):
        raise ValueError('selected runtime/default artifact changed since freeze')
    if engine.sha(root / 'resources/review-references.json') != value['review_reference_sha256']:
        raise ValueError('frozen review references changed')
    if value.get('portable_sdk') and (
        str(v3.sdk_toolchain.apple_macos_sysroot()) != value['portable_sdk']['apple_sysroot']
    ):
        raise ValueError('selected Apple macOS SDK changed since freeze')
    return value


def freeze(output, **kwargs):
    value = v3.freeze(output, **kwargs)
    output = Path(output).resolve()
    (output / 'freeze.json').rename(output / 'preparation-v3-freeze.json')
    (output / 'freeze.sha256').rename(output / 'preparation-v3-freeze.sha256')
    value.update(schema='nex.local-collection/4', study_protocol_version=4, collector_policy_version=7,
                 protocol='experiments/quality/llm-campaign-v4/README.md',
                 response_envelopes='policy7: accept a lone opening tool_call tag only before one complete JSON action')
    for slot in value['order']:
        if not slot['id'].startswith('v3-'):
            raise ValueError('unexpected preparation trial identity')
        slot['id'] = 'v4-' + slot['id'][3:]
    for item in sorted(HERE.iterdir()):
        if item.name not in ('collector.py', 'README.md'):
            continue
        info = item.stat()
        value['pinned_files'].append({'path': str(item), 'resolved': str(item.resolve()), 'symlink': item.is_symlink(),
            'sha256': engine.sha(item), 'dev': info.st_dev, 'ino': info.st_ino, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns})
    v3.acceptance.save(output / 'freeze.json', value)
    (output / 'freeze.sha256').write_text(engine.sha(output / 'freeze.json') + '\n')
    verify(output, deep=True)
    return value


engine.verify = verify
engine.freeze = freeze
engine.model_object = model_object

if __name__ == '__main__':
    def interrupted(signum, frame):
        raise InterruptedError('collection interrupted by SIGTERM')
    signal.signal(signal.SIGTERM, interrupted)
    raise SystemExit(engine.main())
