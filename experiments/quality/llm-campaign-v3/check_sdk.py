#!/usr/bin/env python3
"""Compile and run two trusted controls using an installed macOS NEX SDK."""
import argparse
import json
from pathlib import Path

import collector

TASKS = ('bounded-total', 'joined-yielding-child')


def check_sdk(sdk, cpp, output):
    sdk = sdk.resolve(strict=True)
    compiler = sdk / 'bin/nex'
    manifest = collector.sdk_toolchain.sdk_manifest(compiler)
    if manifest != sdk / 'share/nex/sdk-host.json':
        raise ValueError('select an installed portable macOS SDK')
    output.mkdir(parents=True, exist_ok=False)
    results = []
    for task in TASKS:
        candidate = output / (task + '-source')
        evidence = output / task
        collector.acceptance.materialize(task, 'nex', candidate, variant='solution')
        report = collector.check(candidate, task, 'nex', evidence, compiler=compiler, cpp=cpp,
                                 resources=sdk / 'share/nex', cache=output / (task + '-cache'),
                                 isolate=True)
        row = {'task': task, 'ok': False, 'errors': report['errors']}
        if report['functional_passed']:
            doctor = json.loads((evidence / 'toolchain-info.stdout').read_text())
            selected = json.loads((evidence / 'toolchain.json').read_text())
            runtime = Path(doctor['runtime']).resolve(strict=True)
            row.update(runtime=str(runtime), native_compiler=selected['compiler'],
                       apple_sysroot=selected['sysroot'],
                       observations={item['step']: len(item['values']) for item in report['observations']})
            row['ok'] = (doctor['sdk_manifest'] == str(manifest)
                         and runtime.is_relative_to(sdk / 'share/nex/runtime')
                         and Path(selected['compiler']).resolve(strict=True).is_relative_to(sdk)
                         and set(row['observations']) == {'reference', 'native'})
        results.append(row)
    result = {'schema': 'nex.llm-portable-sdk-control/1', 'ok': all(row['ok'] for row in results),
              'compiler_sha256': collector.engine.sha(compiler), 'model_calls': 0,
              'sdk_manifest_sha256': collector.engine.sha(manifest), 'cases': results}
    collector.acceptance.save(output / 'report.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--cpp', type=Path, help='Optional selected C++ comparison driver')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = check_sdk(args.sdk, args.cpp, args.output.resolve())
    print(json.dumps(result))
    raise SystemExit(0 if result['ok'] else 1)
