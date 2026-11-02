#!/usr/bin/env python3
"""Opt-in finite Q1--Q5 acceptance on one installed SDK and this host."""
import argparse
import json
from pathlib import Path
import sys
import traceback

from acceptance_support import Evidence, checked_language, sha


def fence(report, run, sanitizer):
    assert report['schema'] == 'nex.task-provider-debug-private-lifetime/1'
    assert report['state'] == 'passed' and report['compiler_unchanged'] is True
    assert report['compiler_sha256'] == run.report['compiler_sha256']
    assert report['driver_source_sha256'] == sha(Path(__file__).with_name('quality_task_fence.cpp'))
    assert report['harness_source_sha256'] == sha(Path(__file__).with_name('quality_task_fence.py'))
    result = report['result']
    assert result['ok'] and result['cases'] == 4 and result['runtime_mappings'] == 1
    assert result['catalog_abi'] == 2 and result['registry_abi'] == 1 and result['live_objects'] == 0
    assert report['commands'] and all(row['exit_code'] == 0 for row in report['commands'])
    assert report['commands'][-1]['stderr'] == '', 'runtime/sanitizer output is not clean'
    instrumentation = report['instrumentation']
    assert instrumentation['requested'] == (sanitizer or 'none')
    assert instrumentation['common_runtime_instrumented'] is bool(sanitizer)
    assert instrumentation['driver_instrumented'] is bool(sanitizer)
    assert instrumentation['generated_provider_ir_instrumented'] is False
    assert instrumentation['production_records_retagged'] is False
    if sanitizer:
        assert instrumentation['sources_verified_equal'] is True
    inputs = report['captured_runtime_sha256']
    assert inputs and set(inputs) == set(report['runtime_inputs'])
    for name, expected in inputs.items():
        path = Path(name)
        assert not path.is_absolute() and path.as_posix() == name
        assert all(p not in ('.', '..') for p in path.parts)
        actual = run.resources / 'runtime' / path
        assert actual.is_file() and not actual.is_symlink() and sha(actual) == expected
    runtime = Path(report['runtime']['path'])
    assert sha(runtime) == report['runtime']['sha256']
    assert Path(result['runtime_image_path']).resolve() == runtime.resolve()
    for artifact in report['artifacts'].values():
        path = Path(artifact['path'])
        assert sha(path) == artifact['sha256']
        assert sha(path.parent / 'build.json') == artifact['metadata_sha256']
        assert sha(path.parent / 'task-provider.json') == artifact['provider_record_sha256']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browsers-path', type=Path)
    args = parser.parse_args()
    run = Evidence(args.compiler, None, args.output, 'nex.quality-acceptance/1')
    tools = Path(__file__).resolve().parent
    run.report.update(runner_sha256=sha(Path(__file__)),
        scope='Exactly Q1--Q5 on one installed SDK/host. Physical completion uses '
              'a private controlled generated-DSO observer. Sanitizers instrument the '
              'common C++ runtime and driver, not generated provider LLVM IR. '
              'No kernel isolation, universal platform/throughput parity or LLM token-cost claim.',
        scenarios={}, physical_fences=[], quality_claims={'cross_model_cost_measured': False,
        'cpp_python_parity_measured': False, 'all_platforms_verified': False})
    try:
        assert run.resources == run.compiler.parent.parent / 'share/nex', 'the complete pack requires an installed SDK'
        actual = run.cli('describe', run.output, 'describe', '--field', 'version')
        language = checked_language(actual)
        run.report.update(language=actual['value'], toolchain=actual['toolchain'], compiler_build=actual['compiler_build'])
        scripts = [('Q1', 'type_edit_workflow.py', 'nex.quality-type-edit-workflow/1'),
                   ('Q2', 'server_web_edit.py', 'nex.quality-server-web-edit/1'),
                   ('Q3', 'repair_workflow.py', 'nex.quality-repair-workflow/1'),
                   ('Q4public', 'task_cleanup_workflow.py', 'nex.quality-task-cleanup-public/1'),
                   ('Q5', 'scale_100x100.py', 'nex.quality-scale/1')]
        for name, script_name, schema in scripts:
            script = tools / script_name
            output = run.output / name
            argv = [sys.executable, '-B', script, '--compiler', run.compiler, '--output', output]
            if name == 'Q5':
                argv += ['--language', language]
            if name == 'Q2' and args.browsers_path:
                argv += ['--browsers-path', args.browsers_path.resolve(strict=True)]
            run.command(name, argv, run.output, timeout=7200 if name == 'Q5' else 900)
            receipt = output / 'report.json'
            result = json.loads(receipt.read_text())
            assert result['schema'] == schema and result['ok'] is True and result['state'] == 'passed'
            assert result['compiler_sha256'] == run.report['compiler_sha256']
            assert result['language'] == language and result['toolchain'] == actual['toolchain']
            assert result['compiler_build'] == actual['compiler_build']
            assert result['resource_inventory'] == run.report['resource_inventory']
            assert result['runner_sha256'] == sha(script)
            if name == 'Q2':
                assert result['browser_passes'] == 30
                assert result['durable_across_edit_and_restart'] and result['transaction_rollback']
            if name == 'Q3':
                assert result['original_intent_preserved'] and result['stale_reference_rejected']
                assert result['source_deleted_replay'] and result['failing_budget_detected']
            if name == 'Q4public':
                assert result['complete_q4'] is False
                assert len(result['cases']) == 6 and all(c['passed'] for c in result['cases'])
            if name == 'Q5':
                assert (result['modules'], result['declarations']) == (100, 10000)
                assert result['actual_llvm_calls'] == [9900, 0, 1] and result['all10000_ids_preserved']
                assert result['source_deleted_replay']
            run.report['scenarios'][name] = {'report': str(receipt), 'sha256': sha(receipt), 'passed': True}
            run.save()
        for name, sanitizer in [('plain', ''), ('asan-ubsan-lsan', 'address,undefined'), ('tsan', 'thread')]:
            output = run.output / ('physical-' + name)
            run.command('physical-' + name,
                [sys.executable, '-B', tools / 'quality_task_fence.py', run.compiler, tools / 'quality_task_fence.cpp'],
                run.output, env={'NEX_TASK_PROVIDER_DEBUG_LIFETIME_OUTPUT': str(output),
                    'NEX_TASK_PROVIDER_DEBUG_SANITIZERS': sanitizer}, timeout=900)
            receipt = output / 'report.json'
            fence(json.loads(receipt.read_text()), run, sanitizer)
            run.report['physical_fences'].append({'report': str(receipt), 'sha256': sha(receipt),
                'instrumentation': name, 'cases': 4, 'passed': True})
            run.save()
        run.guard()
        run.report.update(ok=True, state='passed', phase='complete', complete_q4=True,
                          complete_scenarios=['Q1', 'Q2', 'Q3', 'Q4', 'Q5'])
    except BaseException as error:
        run.report.update(state='failed', error=repr(error))
        traceback.print_exc()
    finally:
        run.save()
        print(json.dumps({key: run.report.get(key) for key in ('schema', 'ok', 'state', 'seconds', 'error')}))
    return 0 if run.report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
