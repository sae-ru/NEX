#!/usr/bin/env python3
"""Check pinned local Qwen transport with one benign, non-benchmark request.

Owns only a unique instance created by this invocation and unloads that instance.
Does not execute model-authored code, download weights or run a task trial.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('nex_local_provider', HERE / 'local_provider.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)


def verify_weights(path):
    raw = Path(path).read_bytes(); value = p.decode(raw)
    if value.get('schema') != 'nex.local-model-artifacts/1' or value.get('model') != p.MODEL or value.get('quantization') != 'Q8_0':
        raise ValueError('expected pinned local Qwen Q8_0 artifacts')
    root = Path(value['root']).resolve(strict=True); files = value['files']
    if not isinstance(files, list) or not 1 <= len(files) <= 32: raise ValueError('invalid artifact list')
    names = set()
    for record in files:
        name = record['path']; rel = Path(name)
        if rel.is_absolute() or rel.as_posix() != name or '..' in rel.parts or name in names:
            raise ValueError('invalid artifact path')
        names.add(name); target = root / rel
        if target.is_symlink() or not target.is_file() or not target.resolve().is_relative_to(root):
            raise ValueError('artifact must be a regular file inside its model root')
        info = target.stat()
        if [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns] != [record[k] for k in ['dev', 'ino', 'bytes', 'mtime_ns']]:
            raise ValueError('artifact changed since its full SHA256 pass: ' + name)
        if not re.fullmatch('[0-9a-f]{64}', record['sha256']): raise ValueError('invalid artifact pin')
    if value['primary_gguf'] not in names or not value['primary_gguf'].endswith('-Q8_0.gguf'):
        raise ValueError('primary model is not the selected Q8_0 GGUF')
    return value, raw


def run(profile, weights, output, lms):
    selection = p.decode(Path(profile).read_bytes()); artifacts, raw = verify_weights(weights)
    if (selection.get('model_key') != p.MODEL or selection.get('quantization') != 'Q8_0'
            or selection.get('local_only') is not True or selection.get('paid_APIs_allowed') is not False):
        raise ValueError('local Qwen-only policy is required')
    client = p.Client(selection['base_url'], token=os.environ.get('LM_API_TOKEN'))
    inventory = client.models()
    selected = [model for model in inventory['models'] if model.get('key') in (p.MODEL, p.MODEL + '@q8_0')
                and model.get('format') == 'gguf' and isinstance(model.get('quantization'), dict)
                and model['quantization'].get('name') == 'Q8_0']
    if len(selected) != 1: raise ValueError('the selected local Qwen GGUF Q8_0 is not uniquely available')
    if any(model.get('loaded_instances') for model in inventory['models']):
        raise ValueError('readiness requires an idle local service; it never unloads existing user models')
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    (output / 'weights.json').write_bytes(raw)
    (output / 'selection.json').write_bytes(Path(profile).read_bytes())
    instance = 'nex-cost-qwen38-27b-' + uuid.uuid4().hex[:12]
    report = {'schema': 'nex.local-readiness/1', 'ok': False, 'instance': instance,
              'model': p.MODEL, 'quantization': 'Q8_0', 'context': 16384,
              'benchmark_trials': 0, 'generation_request_attempts': 0, 'response_generations_observed': 0,
              'probe_kind': 'transport_readiness_not_benchmark',
              'model_authored_programs_executed': 0, 'weights_downloaded': 0,
              'owned_instance_unloaded': False, 'errors': []}
    attempted_load = False
    def retain():
        temporary = output / 'report.json.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        temporary.replace(output / 'report.json')
    retain()
    def command(name, args, timeout):
        (output / (name + '.argv.json')).write_text(json.dumps(list(map(str, args)), indent=2) + '\n')
        result = subprocess.run(list(map(str, args)), stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
        (output / (name + '.stdout')).write_bytes(result.stdout); (output / (name + '.stderr')).write_bytes(result.stderr)
        if result.returncode: raise ValueError(name + ' failed with exit ' + str(result.returncode))
    try:
        attempted_load = True
        report['phase'] = 'loading'; retain()
        # The CLI takes its base model key; REST's @q8_0 variant key is not a
        # CLI resource identifier. Quantization is checked before and after load.
        command('load', [lms, 'load', p.MODEL, '--identifier', instance,
            '--context-length', '16384', '--parallel', '1', '--gpu', 'max',
            '--ttl', '600', '--yes'], 180)
        loaded = client.models(); report['loaded_config'] = p.authorized_instance(loaded, instance)
        (output / 'loaded-models.json').write_text(json.dumps(loaded, indent=2) + '\n')
        verify_weights(weights)
        report['phase'] = 'probe'; report['generation_request_attempts'] = 1; retain()
        content, call = client.chat(instance, 'Reply with exactly the JSON object requested. Use no tools.',
                                    'Return only {"ready":true}', output / 'probe', max_tokens=32)
        report['call_id'] = call['id']; report['usage'] = call['usage']
        if call.get('http_status') == 200 and call.get('returned_instance') == instance:
            report['response_generations_observed'] = 1
        if call['error']: raise ValueError(call['error'])
        parsed = p.decode(content.encode('utf-8'))
        if not isinstance(parsed, dict) or set(parsed) != {'ready'} or parsed['ready'] is not True:
            raise ValueError('readiness response differs')
        if call['usage'] is None: raise ValueError('local provider did not report actual token usage')
        verify_weights(weights); report['ok'] = True
    except Exception as error:
        report['errors'].append({'type': type(error).__name__, 'message': str(error)})
    finally:
        if attempted_load:
            try:
                command('unload', [lms, 'unload', instance], 45)
                after = client.models()
                report['owned_instance_unloaded'] = not any(x.get('id') == instance
                    for model in after['models'] for x in model.get('loaded_instances', []))
                if not report['owned_instance_unloaded']: report['ok'] = False
            except Exception as error:
                report['ok'] = False; report['errors'].append({'step': 'owned-unload', 'message': str(error)})
        report['phase'] = 'finished'; retain()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=HERE / 'local-model.json')
    parser.add_argument('--weights', type=Path, required=True); parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lms', type=Path, default=Path.home() / '.lmstudio/bin/lms')
    args = parser.parse_args()
    try:
        result = run(args.profile, args.weights, args.output, args.lms)
        print(json.dumps(result, ensure_ascii=False)); raise SystemExit(0 if result['ok'] else 1)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(json.dumps({'schema': 'nex.local-readiness/1', 'ok': False, 'error': str(error)})); raise SystemExit(2)
