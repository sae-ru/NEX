#!/usr/bin/env python3
"""Exercise the proposed nex.cli-consumer/1 success contract on two installed SDKs."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from sdk_compat_snapshot import cli

CONTRACT = 'nex.cli-consumer/1'
# Only fields read by this profile are part of its contract. Object keys may be added.
FIELDS = {
    'describe': {'schema': str, 'kind': str, 'field': str, 'toolchain': str, 'value': [str]},
    'init': {'ok': bool, 'directory': str},
    'check': {'ok': bool, 'revision': str},
    'test': {'ok': bool, 'tests': [{'name': str, 'ok': bool, 'native': bool}]},
    'eval': {'ok': bool, 'stdout': str, 'value': int},
    'run': {'ok': bool, 'stdout': str, 'stderr': str, 'exit_code': int},
}
SOURCE = '''module consumer;
fn total() -> i64 !{state} {
  let counter: cell<i64> = cell_new(37);
  cell_write(counter, cell_read(counter) + 5);
  return cell_read(counter);
}
fn largest() -> i64 { return 9223372036854775807; }
fn main() -> i64 !{io,state} { print(total()); return 0; }
test fn sample_total() -> unit !{state} { assert(total() == 42); }
'''


def require(condition, message):
    if not condition:
        raise ValueError('CLI consumer contract: ' + message)


def project_fields(value, shape, path):
    """Read declared fields, accepting unknown members at any object depth."""
    if isinstance(shape, dict):
        require(isinstance(value, dict), path + ' must be an object')
        out = {}
        for name, child in shape.items():
            require(name in value, path + '.' + name + ' is required')
            out[name] = project_fields(value[name], child, path + '.' + name)
        return out
    if isinstance(shape, list):
        require(isinstance(value, list), path + ' must be an array')
        return [project_fields(item, shape[0], path + '[]') for item in value]
    # Python bool is a subclass of int. JSON booleans are never integer results.
    require(type(value) is shape, path + ' has the wrong JSON type')
    return value


def check_reply(command, reply):
    """Return only the consumer fields of one successful, in-scope invocation."""
    projected = project_fields(reply, FIELDS[command], command)
    if command == 'describe':
        require((projected['schema'], projected['kind'], projected['field']) ==
                ('nex.discovery/1', 'field', 'project_languages'), 'unexpected discovery projection')
        require(projected['toolchain'] and '0.30' in projected['value'], '0.30 support required')
    else:
        require(projected['ok'], command + ' did not succeed')
        if command == 'check':
            require(re.fullmatch('[0-9a-f]{64}', projected['revision']), 'invalid revision')
        if command == 'eval':
            require(-(2**63) <= projected['value'] < 2**63, 'eval value outside i64')
    return projected


def observe(nex, work):
    work.mkdir()
    project = work / 'consumer project'
    reports = {'describe': cli(nex, work, 'describe', '--field', 'project_languages'),
               'init': cli(nex, work, 'init', str(project), '--language-version', '0.30')}
    require((work / check_reply('init', reports['init'])['directory']).resolve() == project, 'unexpected init path')
    manifest = json.loads((project / 'nex.json').read_bytes())
    require(manifest.get('schema') == 'nex.project/1' and manifest.get('language') == '0.30',
            'init did not create a 0.30 project')
    entry = (project / manifest['entry']).resolve(strict=True)
    require(project in entry.parents and entry.is_file(), 'unexpected manifest entry')
    entry.write_bytes(SOURCE.encode('utf-8'))
    for command in ('check', 'test', 'eval', 'run'):
        reports[command] = cli(nex, project, command)
    revision = check_reply('check', reports['check'])['revision']
    pinned = check_reply('eval', cli(nex, project, 'eval', '--entry', 'largest', '--revision', revision))
    require(pinned['value'] == 2**63 - 1 and pinned['stdout'] == '', 'wrong pinned i64 result')
    return project, reports, pinned['value']


def check_workflow(reports, project, revision):
    out = {cmd: check_reply(cmd, reports[cmd]) for cmd in FIELDS}
    require((project.parent / out['init']['directory']).resolve() == project, 'wrong initialized project')
    require(out['check']['revision'] == revision, 'revision differs for the same 0.30 source')
    require(out['test']['tests'] == [{'name': 'consumer::sample_total', 'native': True, 'ok': True}],
            'expected the declared native test to pass')
    require(out['eval']['stdout'] == '42\n' and out['eval']['value'] == 0, 'wrong evaluated result')
    require(out['run']['stdout'] == '42\n' and out['run']['stderr'] == '' and out['run']['exit_code'] == 0,
            'wrong native result')
    return out


def mutation_controls(reports, project, revision):
    # Mutate real replies, including a nested test row and the bool/int overlap.
    extended = deepcopy(reports)
    for reply in extended.values():
        reply['future_member'] = {'extra': [17]}
    extended['test']['tests'][0]['future_member'] = 'new backend metadata'
    require(check_workflow(extended, project, revision) == check_workflow(reports, project, revision),
            'an additive member changed the projection')
    wrong = {'describe': ('value', ['0.29']), 'init': ('directory', str(project / 'different')),
             'check': ('revision', ('1' if revision[0] == '0' else '0') + revision[1:]),
             'test': ('native', False), 'eval': ('value', 17), 'run': ('stdout', 'wrong\n')}
    rejected = dict.fromkeys(('missing_field', 'wrong_type', 'wrong_result'), 0)
    for cmd, (field, incompatible) in wrong.items():
        for reason in rejected:
            changed = deepcopy(reports)
            row = changed[cmd]['tests'][0] if cmd == 'test' else changed[cmd]
            if reason == 'missing_field':
                del row[field]
            elif reason == 'wrong_type':
                row[field] = {'eval': True, 'test': 1}.get(cmd)
            else:
                row[field] = incompatible
            try:
                check_workflow(changed, project, revision)
            except ValueError:
                rejected[reason] += 1
            else:
                raise ValueError(f'CLI consumer contract: accepted {reason} in {cmd}')
    return {'additive_members_accepted': len(reports) + 1, **rejected}


def check_cli(baseline_nex: Path, candidate_nex: Path, root: Path) -> dict:
    """Run each compiler with its own resources and fresh physical project."""
    require(not Path(baseline_nex).samefile(candidate_nex), 'separate SDK executables required')
    work = Path(root).resolve() / 'cli-compatibility'
    work.mkdir(parents=True, exist_ok=False)
    results = {}
    revision = None
    for role, nex in (('baseline', baseline_nex), ('candidate', candidate_nex)):
        nex = Path(nex).resolve(strict=True)
        project, reports, pinned_i64 = observe(nex, work / role)
        if role == 'baseline':
            revision = check_reply('check', reports['check'])['revision']
        out = check_workflow(reports, project, revision)
        results[role] = {'toolchain': out['describe']['toolchain'],
                         'compiler_sha256': hashlib.sha256(nex.read_bytes()).hexdigest(),
                         'init_language': '0.30', 'revision': revision, 'tests': out['test']['tests'],
                         'eval': out['eval'], 'run': out['run'], 'pinned_i64': str(pinned_i64),
                         'controls': mutation_controls(reports, project, revision)}
    return {'schema': 'nex.cli-consumer-compatibility/1', 'contract': CONTRACT, 'ok': True,
            'commands': list(FIELDS), 'fixture_sha256': hashlib.sha256(SOURCE.encode()).hexdigest(), **results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path, help='installed baseline nex executable')
    parser.add_argument('--candidate', required=True, type=Path, help='installed candidate nex executable')
    parser.add_argument('--output', required=True, type=Path, help='new output directory')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    receipt = check_cli(args.baseline, args.candidate, args.output)
    (args.output / 'report.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(args.output / 'report.json')
