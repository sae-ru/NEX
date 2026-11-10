"""Real three-language host controls, not a model/token-saving experiment."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
NEX = Path(sys.argv.pop(1)).resolve()
BASE = REPO / 'experiments/quality/llm-campaign-v1'
spec = importlib.util.spec_from_file_location('nex_campaign_acceptance', BASE / 'acceptance.py')
a = importlib.util.module_from_spec(spec); spec.loader.exec_module(a)


class Campaign(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex-campaign-control-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def review(self, task, materialized, path):
        item = a.catalogue()[task]
        a.save(path, {'schema': 'nex.llm-source-review/1', 'candidate_digest': materialized['source_digest'],
            'contract_sha256': item['contract_sha256'], 'passed': True,
            'reviewer': 'synthetic host fixture control; not a model trial',
            'rules': item['contract']['acceptance_rules']})
        return path

    def test_real_control_matrix(self):
        destination = os.environ.get('NEX_CAMPAIGN_OUTPUT')
        out = Path(destination).resolve() if destination else self.root / 'evidence'
        out.mkdir(parents=True, exist_ok=False)
        env = dict(os.environ, NEX_RESOURCE_DIR=str(REPO))
        doctor = json.loads(subprocess.check_output([NEX, 'doctor', '--json'], env=env))
        cpp = shutil.which(doctor['native_compiler']) or doctor['native_compiler']
        cpp = Path(cpp).absolute()
        self.assertTrue(cpp.is_file())
        matrix = {(task, language, variant) for task in a.catalogue()
                  for language in ['nex', 'cpp', 'python'] for variant in ['solution', 'start']}
        selected = matrix
        if os.environ.get('NEX_CAMPAIGN_CONTROL_SELECTION'):
            selected = {tuple(x) for x in json.loads(os.environ['NEX_CAMPAIGN_CONTROL_SELECTION'])}
            self.assertTrue(selected and selected <= matrix, 'invalid bounded control selection')
        rows = []
        for task in a.catalogue():
            for language in ['nex', 'cpp', 'python']:
                for variant, passes in [('solution', True), ('start', False)]:
                    if (task, language, variant) not in selected: continue
                    name = task + '-' + language + '-' + variant
                    directory = out / (name + '-source')
                    materialized = a.materialize(task, language, directory, variant=variant)
                    review = self.review(task, materialized, out / (name + '-review.json')) if passes else None
                    with self.subTest(task=task, language=language, variant=variant):
                        result = a.check(directory, task, language, out / name, compiler=NEX, cpp=cpp,
                            resources=REPO, cache=out / 'native-cache', review=review,
                            windows_observer=os.environ.get('NEX_WINDOWS_JOB_OBSERVER'))
                        rows.append({'task': task, 'language': language, 'variant': variant,
                            'functional_passed': result['functional_passed'], 'accepted': result['accepted'],
                            'report': name + '/report.json'})
                        a.save(out / 'matrix.json', {'schema': 'nex.llm-campaign-controls/1', 'model_calls': 0, 'results': rows})
                        self.assertEqual(result['functional_passed'], passes, result['errors'])
                        self.assertEqual(result['accepted'], passes, result['errors'])
                        self.assertFalse(any(e['step'] == 'infrastructure' for e in result['errors']))
                        self.assertTrue(all(c['stopped'] is None and c['exit_code'] in (0, 1)
                                            for c in result['commands']), 'a crash/timeout is not a qualified host control')
                        self.assertEqual(a.read_candidate(directory, task, language), a.fixtures.files(task, language, variant))
        if len(rows) == len(selected) and all(r['accepted'] == (r['variant'] == 'solution') for r in rows):
            if (out / 'native-cache').exists(): shutil.rmtree(out / 'native-cache')

    def test_functional_success_is_not_source_review_and_pins_are_enforced(self):
        candidate = self.root / 'candidate'
        materialized = a.materialize('bounded-total', 'python', candidate, variant='solution')
        report = a.check(candidate, 'bounded-total', 'python', self.root / 'functional-only')
        self.assertTrue(report['functional_passed']); self.assertFalse(report['accepted'])
        self.assertFalse(json.loads((self.root / 'functional-only/acceptance.json').read_bytes())['passed'])
        path = self.review('bounded-total', materialized, self.root / 'review.json')
        review = json.loads(path.read_bytes()); review['candidate_digest'] = '0' * 64; a.save(path, review)
        with self.assertRaisesRegex(ValueError, 'does not bind'):
            a.check(candidate, 'bounded-total', 'python', self.root / 'must-not-execute', review=path)
        self.assertFalse((self.root / 'must-not-execute').exists())
        (candidate / 'unexpected.py').write_text('raise RuntimeError("must not execute")')
        with self.assertRaisesRegex(ValueError, 'unexpected path'):
            a.check(candidate, 'bounded-total', 'python', self.root / 'no-extra-code')

    def test_held_out_cases_reject_a_visible_case_lookup(self):
        candidate = self.root / 'lookup'
        a.materialize('bounded-total', 'python', candidate)
        (candidate / 'candidate.py').write_text('def total(n):\n    return {0: 0, 1: 1, 10: 55, 100: 5050}.get(n, 0)\n')
        visible = a.check(candidate, 'bounded-total', 'python', self.root / 'visible', visible_only=True)
        self.assertTrue(visible['functional_passed']); self.assertFalse(visible['accepted'])
        actual = a.check(candidate, 'bounded-total', 'python', self.root / 'held-out')
        self.assertFalse(actual['functional_passed']); self.assertFalse(actual['accepted'])

    def test_owned_timeout_and_output_budgets(self):
        if os.name == 'nt' and not os.environ.get('NEX_WINDOWS_JOB_OBSERVER'):
            self.fail('Windows process checks require the existing calibrated private-job observer')
        row = a.command([sys.executable, '-I', '-B', '-c', 'import time;time.sleep(10)'],
                        self.root, os.environ.copy(), self.root, 'timeout', timeout=0.15,
                        windows_observer=os.environ.get('NEX_WINDOWS_JOB_OBSERVER'))
        self.assertEqual(row['stopped'], 'timeout'); self.assertNotEqual(row['exit_code'], 0)
        if os.name != 'nt':
            row = a.command([sys.executable, '-I', '-B', '-c', 'import os\nwhile True: os.write(1,b"x"*65536)'],
                            self.root, os.environ.copy(), self.root, 'output', timeout=10)
            self.assertEqual(row['stopped'], 'output_limit'); self.assertNotEqual(row['exit_code'], 0)


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v', *sys.argv[1:]])
