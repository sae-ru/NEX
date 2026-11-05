"""Check completed CTest JUnit results against the declared fixture closure."""
import argparse
import hashlib
import json
from pathlib import Path
import stat
import sys
import xml.etree.ElementTree as ET


class ReportError(ValueError):
    pass


def _label(value):
    if not isinstance(value, str) or not value or '\0' in value:
        return False
    try:
        value.encode('utf-8')
    except UnicodeError:
        return False
    return True


def fixture_closure(registry, selected=None):
    tests = registry.get('tests') if isinstance(registry, dict) else None
    if not isinstance(tests, list) or not 0 < len(tests) <= 100000:
        raise ReportError('registry requires a nonempty bounded test list')
    properties = {}
    for test in tests:
        name = test.get('name') if isinstance(test, dict) else None
        if not _label(name) or name in properties:
            raise ReportError('registry test names must be nonempty and unique')
        row = {}
        entries = test.get('properties', [])
        if not isinstance(entries, list):
            raise ReportError('registry properties must be an array')
        for item in entries:
            if not isinstance(item, dict):
                raise ReportError('invalid registry property')
            kind = item.get('name')
            if kind not in ('FIXTURES_REQUIRED', 'FIXTURES_SETUP', 'FIXTURES_CLEANUP'):
                continue
            if kind in row:
                raise ReportError('duplicate fixture property')
            value = item.get('value')
            if isinstance(value, str):
                value = value.split(';') if value else []
            if not isinstance(value, list) or any(not _label(x) for x in value):
                raise ReportError('fixture names must be nonempty strings')
            row[kind] = set(value)
        properties[name] = row
    if selected is not None and (not isinstance(selected, (list, tuple, set, frozenset)) or
                                 any(not _label(name) for name in selected)):
        raise ReportError('selected tests must be group names')
    roots = set(properties) if selected is None else set(selected)
    if not roots or not roots <= properties.keys():
        raise ReportError('selected tests must be a nonempty declared group set')
    providers = {}
    for name, row in properties.items():
        for fixture in row.get('FIXTURES_SETUP', set()) | row.get('FIXTURES_CLEANUP', set()):
            providers.setdefault(fixture, set()).add(name)
    wanted, pending = set(roots), list(roots)
    while pending:
        for fixture in properties[pending.pop()].get('FIXTURES_REQUIRED', set()):
            for name in providers.get(fixture, ()):
                if name not in wanted:
                    wanted.add(name)
                    pending.append(name)
    return roots, wanted


def inspect_report(registry, junit, *, ctest_exit_code, selected=None):
    if type(ctest_exit_code) is not int:
        raise ReportError('the actual CTest process exit code is required')
    roots, wanted = fixture_closure(registry, selected)
    try:
        text = junit.decode('utf-8-sig') if isinstance(junit, bytes) else junit
        if not isinstance(text, str) or '<!DOCTYPE' in text or '<!ENTITY' in text:
            raise ReportError('expected UTF-8 CTest XML without DTD declarations')
        suite = ET.fromstring(text)
    except (UnicodeError, ET.ParseError) as error:
        raise ReportError('invalid UTF-8 JUnit document: ' + str(error)) from error
    if suite.tag not in ('testsuite', 'testsuites'):
        raise ReportError('expected a CTest JUnit test suite')
    for parent in suite.iter():
        if any(child.tag == 'testcase' for child in parent) and parent.tag != 'testsuite':
            raise ReportError('test cases must belong directly to test suites')
    cases = list(suite.iter('testcase'))
    observed = [case.get('name') for case in cases]
    if any(not isinstance(name, str) or not name for name in observed) or len(observed) != len(set(observed)):
        raise ReportError('JUnit test names must be nonempty and unique')
    if set(observed) != wanted:
        raise ReportError('JUnit groups differ from declared fixture closure; missing=' +
                          repr(sorted(wanted - set(observed))) + '; unexpected=' +
                          repr(sorted(set(observed) - wanted)))
    declared = suite.get('tests')
    if declared is not None and (not declared.isascii() or not declared.isdigit() or int(declared) != len(cases)):
        raise ReportError('JUnit test count contradicts its cases')
    rows = {'passed': [], 'failed': [], 'skipped': []}
    for case in cases:
        status = case.get('status')
        if status not in ('run', 'fail', 'notrun', 'disabled'):
            raise ReportError('JUnit case lacks a supported CTest status: ' + case.get('name'))
        skipped = case.find('skipped')
        unavailable = skipped is not None and skipped.get('message') in (
            'Unable to find executable', 'Fixture dependency failed')
        state = ('failed' if case.find('failure') is not None or case.find('error') is not None or
                 status == 'fail' or unavailable else
                 'skipped' if skipped is not None or status in ('notrun', 'disabled') else 'passed')
        rows[state].append(case.get('name'))
    return {'schema': 'nex.ctest-verification/1',
            'ok': ctest_exit_code == 0 and not rows['failed'] and not rows['skipped'],
            'ctest_exit_code': ctest_exit_code,
            'selected_groups': sorted(roots), 'required_fixture_groups': sorted(wanted - roots),
            'expected_groups': sorted(wanted), 'observed_groups': observed, 'results': rows}


def _read(path, limit):
    path = Path(path)
    if not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > limit:
        raise ReportError('report input must be a bounded regular file: ' + str(path))
    with path.open('rb') as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ReportError('report input exceeds its size limit')
    return data


def _pairs(items):
    result = {}
    for key, value in items:
        if key in result:
            raise ReportError('duplicate JSON key: ' + key)
        result[key] = value
    return result


def _constant(value):
    raise ReportError('non-finite JSON constant: ' + value)


def inspect_files(registry, junit, *, ctest_exit_code, selected=None):
    raw_registry, raw_junit = _read(registry, 32 * 1024**2), _read(junit, 64 * 1024**2)
    try:
        declared = json.loads(raw_registry.decode('utf-8-sig'), object_pairs_hook=_pairs,
                              parse_constant=_constant)
    except (UnicodeError, ValueError) as error:
        raise ReportError('invalid UTF-8 CTest registry: ' + str(error)) from error
    result = inspect_report(declared, raw_junit, ctest_exit_code=ctest_exit_code, selected=selected)
    result.update(registry_sha256=hashlib.sha256(raw_registry).hexdigest(),
                  junit_sha256=hashlib.sha256(raw_junit).hexdigest())
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--registry', type=Path, required=True)
    parser.add_argument('--junit', type=Path, required=True)
    parser.add_argument('--ctest-exit-code', type=int, required=True)
    parser.add_argument('--select', action='append')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        result = inspect_files(args.registry, args.junit,
                               ctest_exit_code=args.ctest_exit_code, selected=args.select)
        code = 0 if result['ok'] else 1
    except (OSError, ReportError) as error:
        result = {'schema': 'nex.ctest-verification/1', 'ok': False,
                  'valid_report': False, 'error': str(error)}
        code = 2
    text = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output is not None:
        try:
            if args.output.resolve() in (args.registry.resolve(), args.junit.resolve()):
                raise ReportError('derived output must differ from its input reports')
            args.output.write_text(text, encoding='utf-8')
        except (OSError, ReportError) as error:
            text = json.dumps({'schema': 'nex.ctest-verification/1', 'ok': False,
                               'error': 'cannot save derived report: ' + str(error)},
                              ensure_ascii=False, indent=2) + '\n'
            code = 2
    if hasattr(sys.stdout, 'buffer'):
        sys.stdout.buffer.write(text.encode('utf-8'))
    else:
        print(text, end='')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
