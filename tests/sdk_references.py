"""Focused invocation of the installed030 SDK sub-workflow; not full SDK acceptance."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('compiler', type=Path)
parser.add_argument('--resources', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--browser', action='store_true')
parser.add_argument('--live', action='store_true')
args = parser.parse_args()
compiler = args.compiler.resolve(strict=True)
resources = args.resources.resolve(strict=True)
root = args.output.resolve()
root.mkdir(parents=True, exist_ok=False)
spec = importlib.util.spec_from_file_location('sdk_reference_workflow', resources/'tools/sdk_acceptance.py')
acceptance = importlib.util.module_from_spec(spec); spec.loader.exec_module(acceptance)
environment = {**os.environ, 'NEX_RESOURCE_DIR': str(resources)}
commands = []
doctor = None


def run(command, cwd=root, expected_success=True, timeout=180):
    command = list(map(str, command))
    options = dict(cwd=cwd, env=environment, capture_output=True, text=True,
                   encoding='utf-8', timeout=timeout)
    if acceptance.sdk_host.WINDOWS and acceptance.sdk_host.compiler_command(command):
        observed = acceptance.sdk_host.compile_fixture(command, doctor=doctor, **options)
    else:
        observed = subprocess.run(command, **options)
    commands.append({'command': command, 'cwd': str(cwd),
                     'exit_code': observed.returncode, 'stdout': observed.stdout, 'stderr': observed.stderr})
    (root/'commands.json').write_text(json.dumps(commands, ensure_ascii=False, indent=2) + '\n')
    if (observed.returncode == 0) != expected_success:
        raise RuntimeError('unexpected command result; inspect ' + str(root/'commands.json'))
    return observed.stdout


def cli(*arguments, cwd=root, expected_success=True, timeout=180):
    arguments = list(arguments); arguments.insert(arguments.index('--') if '--' in arguments else len(arguments), '--json')
    return json.loads(run([compiler, *arguments], cwd, expected_success, timeout))


doctor = cli('doctor')
value = acceptance.sdk_references.exercise(cli=cli, run=run, compiler=compiler, resources=resources,
    root=root, browser=args.browser, live=args.live, doctor=doctor, environment=environment,
    dap_factory=acceptance.DAP)
report = {'compiler_sha256': acceptance.sdk_references.sha(compiler),
          'resource_hashes': value['resource_sha256'], 'evidence': {'reference030': value,
          'browser_build': args.browser, 'live_debugger': args.live}, 'complete_SDK_workflow_claimed': False}
acceptance.sdk_references.validate(report)
(root/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({'ok': True, 'commands': len(commands), 'provider_modes': len(value['providers']),
                  'browser': args.browser, 'live': args.live, 'complete_SDK_workflow_claimed': False}))
