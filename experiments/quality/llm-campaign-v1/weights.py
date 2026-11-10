"""Pin existing local Qwen GGUF files without downloading or loading a model."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

MODEL = 'qwen/qwen3.8-27b'
PRIMARY = 'Qwen3.8-27B-Q8_0.gguf'


def pin(root, output):
    root = Path(root).resolve(strict=True)
    if not root.is_dir(): raise ValueError('expected an existing local model directory')
    paths = sorted(p for p in root.rglob('*') if not p.is_dir() and p.name != '.DS_Store')
    if not 1 <= len(paths) <= 32 or root / PRIMARY not in paths:
        raise ValueError('expected the selected Qwen3.8 27B Q8_0 GGUF and at most32 artifacts')
    records = []
    for path in paths:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError('model artifacts must be regular files inside the selected root')
        before = path.stat(); digest = hashlib.sha256()
        with path.open('rb') as stream:
            if path.name == PRIMARY:
                if stream.read(4) != b'GGUF': raise ValueError('selected model lacks the GGUF header')
                stream.seek(0)
            while chunk := stream.read(16 * 1024 * 1024): digest.update(chunk)
        after = path.stat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns')
        if tuple(getattr(before, field) for field in fields) != tuple(getattr(after, field) for field in fields):
            raise ValueError('model artifact changed during its SHA256 pass')
        records.append({'path': path.relative_to(root).as_posix(), 'sha256': digest.hexdigest(),
                        'bytes': after.st_size, 'mtime_ns': after.st_mtime_ns,
                        'dev': after.st_dev, 'ino': after.st_ino})
    value = {'schema': 'nex.local-model-artifacts/1',
             'utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
             'model': MODEL, 'quantization': 'Q8_0', 'root': str(root), 'files': records,
             'primary_gguf': PRIMARY, 'total_bytes': sum(item['bytes'] for item in records),
             'tokenizer_identity': 'embedded in primary GGUF; covered by its full SHA256',
             'models_loaded': 0, 'inference_calls': 0}
    with Path(output).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2); stream.write('\n')
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = pin(args.root, args.output)
        print(json.dumps({'ok': True, 'artifacts': len(result['files']), 'bytes': result['total_bytes']}))
    except (OSError, ValueError) as error:
        parser.exit(2, str(error) + '\n')
