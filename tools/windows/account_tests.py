"""Account for inner Python cases in a completed native Windows verification."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verification', type=Path, required=True)
    args = parser.parse_args()
    output = args.verification.resolve(strict=True)
    report = json.loads((output / 'report.json').read_bytes())
    if not (report.get('state') == 'complete' and
            report.get('full_windows_regression_accepted') is True and
            report.get('inputs_unchanged') is True):
        raise ValueError('the complete immutable regression has not been accepted')
    xml = output / 'ctest.xml'
    if sha(xml) != report['ctest_xml_sha256']:
        raise ValueError('the completed JUnit report differs')
    cases = ET.parse(xml).getroot().findall('.//testcase')
    count = report['declared_test_count']
    if len(cases) != count:
        raise ValueError('the JUnit inventory differs from the full cohort')
    command = next(c['argv'] for c in report['commands'] if c['name'] == 'ctest')
    cohort = Path(command[command.index('--test-dir') + 1])
    full_log = output / 'ctest-LastTest.log'
    if not full_log.exists():
        shutil.copy2(cohort / 'Testing/Temporary/LastTest.log', full_log)
    blocks = re.split(r'(?m)^\d+/' + str(count) + r' Testing: ',
                      full_log.read_text(encoding='utf-8', errors='replace'))[1:]
    logs = {b.splitlines()[0]: b.split('Output:\n', 1)[1].split('<end of output>', 1)[0]
            for b in blocks}
    if len(blocks) != count or set(logs) != {c.get('name') for c in cases}:
        raise ValueError('the complete log inventory differs from JUnit')
    rows = []
    for case in cases:
        if case.find('failure') is not None or case.find('error') is not None:
            raise ValueError('a failed group cannot have accepted accounting')
        text = logs[case.get('name')]
        rows.append({'group': case.get('name'),
            'ctest_skipped': case.find('skipped') is not None,
            'unittest_cases_reported': sum(map(int, re.findall(r'^Ran (\d+) tests?', text, re.M))),
            'unittest_skipped_reported': sum(map(int, re.findall(r'^OK \([^\n]*?skipped=(\d+)', text, re.M))),
            'skip_details': [line.strip() for line in text.splitlines()
                             if re.search(r'\.\.\. skipped ', line)]})
    result = {'schema': 'nex.windows-regression-case-accounting/1',
        'compiler_sha256': report['compiler_sha256'], 'junit_sha256': sha(xml),
        'complete_log_sha256': sha(full_log), 'ctest_groups': len(rows),
        'ctest_skipped_groups': sum(r['ctest_skipped'] for r in rows),
        'unittest_cases_reported': sum(r['unittest_cases_reported'] for r in rows),
        'unittest_skipped_reported': sum(r['unittest_skipped_reported'] for r in rows),
        'note': 'Counts use the completed full LastTest.log because CTest truncates some verbose '
            'JUnit system-out fields. Native C++ assertions and custom runners are not represented '
            'by unittest case totals. Skipped methods are not assumed covered elsewhere: inspect '
            'the listed reasons. Non-live modes and OS-only unavailable cases remain separate.',
        'groups': rows}
    (output / 'case-accounting.json').write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in result.items() if k != 'groups'}, ensure_ascii=False))


if __name__ == '__main__':
    main()
