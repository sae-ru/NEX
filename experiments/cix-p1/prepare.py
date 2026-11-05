#!/usr/bin/env python3
"""Prepare a new, explicitly granted CIX fixture; never execute the accelerator."""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess


_helper=Path(__file__).resolve().parents[2]/'tools/provider_sdk.py'
_spec=importlib.util.spec_from_file_location('cix_provider_sdk',_helper)
provider_sdk=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(provider_sdk)


def check_source_sdk(sdk):
    origin=Path(__file__).resolve().parent
    source=(origin/'main.nex.in').read_text().replace('@PIN@','0'*64)
    return provider_sdk.check_sdk(sdk,source,{},['gpu_affine','npu_mul'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--check-sdk', action='store_true', help='check current source and FFI signatures without native compilation or device execution')
    parser.add_argument('--cxx', default='g++')
    args = parser.parse_args()
    if args.check_sdk:
        if args.output:
            parser.error('--check-sdk cannot be combined with --output')
        print(json.dumps(check_source_sdk(args.sdk)))
        return
    if args.output is None:
        parser.error('native preparation requires --output')
    if platform.system() != 'Linux' or platform.machine() not in ('aarch64', 'arm64'):
        parser.error('this experimental adapter requires Linux ARM64')
    sdk = args.sdk.resolve(strict=True)
    compiler = provider_sdk.sdk_compiler(sdk)
    resources = sdk / 'share/nex'
    origin = Path(__file__).resolve().parent
    root = args.output.absolute()
    root.mkdir(parents=False, exist_ok=False)
    environment = {**os.environ, 'NEX_RESOURCE_DIR': str(resources),
                   'PATH': str(sdk / 'bin') + os.pathsep + os.environ.get('PATH', '')}

    def run(arguments):
        result = subprocess.run(list(map(str, arguments)), cwd=root, env=environment,
                                capture_output=True, text=True, timeout=180)
        if result.returncode:
            raise RuntimeError(result.stderr or result.stdout)
        return result.stdout

    def cli(*arguments):
        return json.loads(run([compiler, *arguments, '--json']))

    def sha(path):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    descriptor = cli('describe')
    language=descriptor.get('version')
    if language=='0.16':
        # Preserve preparation with the original SDK's actual source dialect.
        if descriptor.get('schema')!='nex.language/1' or descriptor.get('foreign_boundary',{}).get('source_support') is not True:
            raise RuntimeError('requires checked language0.16 source FFI support')
    else:
        language=provider_sdk.source_language(descriptor)
    for name in ('module.cpp', 'main.nex.in', 'model.json'):
        shutil.copy2(origin / name, root / name)
    shutil.copytree(origin / 'include', root / 'include')
    (root / 'nex.json').write_text(json.dumps({
        'schema': 'nex.project/1', 'language': language, 'entry': 'main.nex'}))
    template = (root / 'main.nex.in').read_text()
    (root / 'main.nex').write_text(template.replace('@PIN@', '0' * 64))
    signatures = {name: cli('ffi', '--symbol', name)
                  for name in ('gpu_affine', 'npu_mul')}
    digests = {name: hashlib.sha256(json.dumps(value, sort_keys=True,
               separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
               for name, value in signatures.items()}
    fixture = json.loads((root / 'model.json').read_text())
    model = base64.b64decode(fixture['model_base64'], validate=True)
    digest = hashlib.sha256(model).hexdigest()
    if digest != '71f431c4e9321ec6fbeb158d02ed240459a7dcc98673fa79a4f439ce42efaf10':
        raise RuntimeError('unexpected model fixture bytes')
    (root / 'model.inc').write_text(
        'static constexpr unsigned char modelData[]={' + ','.join(map(str, model)) + '};\n'
        'static constexpr const char *modelSHA256="' + digest + '";\n')
    bundle = root / 'bundle'
    bundle.mkdir()
    run([args.cxx, '-std=c++20', '-O2', '-shared', '-fPIC', '-fvisibility=hidden',
         '-Wall', '-Wextra', '-I' + str(root / 'include'), '-I' + str(resources / 'runtime'),
         '-DNEX_GPU_SIGNATURE="' + digests['gpu_affine'] + '"',
         '-DNEX_NPU_SIGNATURE="' + digests['npu_mul'] + '"',
         root / 'module.cpp', '-o', bundle / 'module.so', '-ldl', '-pthread'])
    notices = 'Experimental NEX CIX fixture: trusted native code, no stable generic accelerator ABI.\n'
    for heading, path in (
        ('Khronos OpenCL-Headers and Arm China Zhouyi declaration, Apache-2.0', root / 'include/OPENCL-LICENSE'),
        ('Microsoft ONNX Runtime C API and fixture, MIT', root / 'include/ONNX-LICENSE'),
        ('nlohmann/json, MIT', resources / 'runtime/third_party/JSON-LICENSE.MIT')):
        notices += '\n' + heading + '\n' + path.read_text()
    (bundle / 'NOTICE').write_text(notices)
    manifest = {'schema': 'nex.foreign-bundle/1', 'platform': 'linux-arm64',
                'entry': 'module.so', 'files': [{'path': name, 'sha256': sha(bundle / name)}
                for name in ('module.so', 'NOTICE')], 'exports': digests, 'notices': ['NOTICE']}
    (bundle / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    pin = sha(bundle / 'manifest.json')
    (root / 'main.nex').write_text(template.replace('@PIN@', pin))
    host = {'schema': 'nex.foreign-host/1', 'module_limit': 64,
            'libraries': {'cix': {'directory': 'bundle', 'manifest_sha256': pin,
                                'exports': ['gpu_affine', 'npu_mul']}}}
    (root / 'host.json').write_text(json.dumps(host, indent=2) + '\n')
    cli('check')
    catalogue = cli('foreign', root / 'host.json')
    result = {'ok': True, 'directory': str(root), 'module_sha256': sha(bundle / 'module.so'),
              'manifest_sha256': pin, 'catalogue': catalogue, 'hardware_executed': False}
    (root / 'preparation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'catalogue'}))


if __name__ == '__main__':
    main()
