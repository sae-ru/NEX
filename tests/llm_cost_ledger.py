"""Offline accounting controls; all campaign records here are synthetic."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

# tests/numbers.py is a compiler driver, not the standard library numbers module.
sys.path = [entry for entry in sys.path
            if Path(entry or '.').resolve() != Path(__file__).resolve().parent]
SCRIPT = Path(__file__).resolve().parents[1] / 'experiments/quality/llm_cost.py'
spec = importlib.util.spec_from_file_location('llm_cost', SCRIPT)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
PIN = 'a' * 64


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex-synthetic-llm-cost-')
        self.root = Path(self.temp.name)
        self.path = self.root / 'ledger.json'
        self.addCleanup(self.temp.cleanup)

    def artifact(self, name, value):
        raw = json.dumps(value).encode('utf-8')
        (self.root / name).write_bytes(raw)
        return {'path': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    def campaign(self, models=1, repeats=2, kind='synthetic'):
        campaign = {'schema': 'nex.llm-cost-ledger/1', 'data_kind': kind,
                    'languages': ['nex', 'cpp', 'python'], 'repeats': repeats,
                    'protocol': self.artifact('protocol.json', {'synthetic': True}),
                    'models': [], 'tasks': [{'id': 'task', 'contract_sha256': PIN}], 'runs': []}
        for m in range(models):
            model = 'model-' + str(m)
            campaign['models'].append({'id': model, 'provider': 'synthetic-provider',
                'revision': model + '-snapshot', 'tokenizer': 'synthetic-tokenizer', 'settings_sha256': PIN})
            for repeat in range(repeats):
                for language in campaign['languages']:
                    trial = model + '-' + str(repeat) + '-' + language
                    receipt = {'schema': 'nex.llm-acceptance/1', 'trial_id': trial,
                        'contract_sha256': PIN, 'passed': True, 'checks': [{'name': 'synthetic-check', 'exit_code': 0}]}
                    evidence = self.artifact(trial + '-usage.json', {'synthetic': True, 'id': trial})
                    campaign['runs'].append({'id': trial, 'model': model, 'task': 'task', 'language': language,
                        'repeat': repeat, 'status': 'accepted', 'wall_ms': 123,
                        'acceptance': self.artifact(trial + '-acceptance.json', receipt),
                        'calls': [{'id': trial, 'evidence': evidence,
                            'usage': {'input_tokens': 100, 'cached_input_tokens': 40, 'output_tokens': 20},
                            'confirmed_cost': None}]})
        return campaign

    def save(self, campaign):
        self.path.write_text(json.dumps(campaign), encoding='utf-8')

    def inspect(self, campaign):
        self.save(campaign)
        return tool.summarize(self.path)

    def fail_trial(self, run, status='failed'):
        run['status'] = status
        receipt = json.loads((self.root / run['acceptance']['path']).read_text())
        receipt['passed'] = False
        receipt['checks'][0]['exit_code'] = 1
        run['acceptance'] = self.artifact(run['acceptance']['path'], receipt)

    def test_retries_failed_tokens_and_cache_subset(self):
        campaign = self.campaign()
        nex = [r for r in campaign['runs'] if r['language'] == 'nex']
        self.fail_trial(nex[1])
        nex[0]['calls'].append({'id': 'repair-call', 'evidence': self.artifact('repair.json', {'synthetic': True}),
            'usage': {'input_tokens': 10, 'cached_input_tokens': 0, 'output_tokens': 5}, 'confirmed_cost': None})
        result = self.inspect(campaign)['results']['model-0']['nex']
        self.assertEqual(result['known_total_tokens'], 255)
        self.assertEqual(result['known_input_tokens'], 210)
        self.assertEqual(result['known_cached_input_tokens'], 80)
        self.assertEqual(result['known_uncached_input_tokens'], 130)
        self.assertEqual(result['all_tokens_per_accepted_trial'], {'numerator': 255, 'denominator': 1})
        self.assertEqual(result['median_trial_tokens'], {'numerator': 255, 'denominator': 2})
        self.assertEqual(result['p95_trial_tokens'], 135)
        self.assertEqual(result['accepted_trials'], 1)

    def test_failure_penalty_in_comparison(self):
        campaign = self.campaign()
        self.fail_trial(campaign['runs'][0], 'budget_exhausted')
        result = self.inspect(campaign)['comparisons']['model-0']['cpp']
        self.assertEqual(result['nex_to_baseline_tokens_per_accepted_trial'], {'numerator': 2, 'denominator': 1})
        self.assertFalse(result['nex_success_rate_at_least_baseline'])

    def test_unknown_usage_cannot_become_zero_or_a_comparison(self):
        campaign = self.campaign()
        campaign['runs'][0]['calls'][0]['usage'] = None
        result = self.inspect(campaign)
        group = result['results']['model-0']['nex']
        self.assertEqual(group['known_total_tokens'], 120)
        self.assertEqual(group['calls_without_usage'], 1)
        self.assertIsNone(group['all_tokens_per_accepted_trial'])
        self.assertFalse(result['usage_complete_for_observed_calls'])
        self.assertIsNone(result['comparisons']['model-0']['cpp']['nex_to_baseline_tokens_per_accepted_trial'])

    def test_missing_matrix_slot_is_explicit(self):
        campaign = self.campaign()
        campaign['runs'].pop()
        result = self.inspect(campaign)
        self.assertFalse(result['matrix_complete'])
        self.assertEqual(result['missing_trials'], [('model-0', 'task', 1, 'python')])
        self.assertIsNone(result['results']['model-0']['python']['all_tokens_per_accepted_trial'])

    def test_zero_success_retains_expenditure(self):
        campaign = self.campaign()
        for run in campaign['runs']:
            self.fail_trial(run, 'timeout')
        result = self.inspect(campaign)['results']['model-0']['nex']
        self.assertEqual(result['known_total_tokens'], 240)
        self.assertEqual(result['terminal_statuses']['timeout'], 2)
        self.assertIsNone(result['all_tokens_per_accepted_trial'])

    def test_synthetic_data_and_small_campaign_never_qualify(self):
        self.assertFalse(self.inspect(self.campaign(models=3))['eligible_for_comparison_review'])
        self.assertFalse(self.inspect(self.campaign(kind='observed'))['eligible_for_comparison_review'])
        self.assertFalse(self.inspect(self.campaign(models=3, repeats=1, kind='observed'))['eligible_for_comparison_review'])

    def test_observed_label_only_qualifies_for_external_review(self):
        # This tests the input label, not a real experiment or provider provenance.
        result = self.inspect(self.campaign(models=3, kind='observed'))
        self.assertTrue(result['eligible_for_comparison_review'])
        self.assertFalse(result['provider_usage_and_billing_authenticity_verified'])
        self.assertFalse(result['acceptance_semantics_and_protocol_fairness_verified'])
        self.assertFalse(result['actual_multi_model_benchmark_completed_by_this_tool'])

    def test_summary_does_not_echo_unrecognized_metadata(self):
        campaign = self.campaign()
        campaign['models'][0]['unrelated'] = 'do-not-copy-into-summary'
        campaign['tasks'][0]['unrelated'] = 'do-not-copy-into-summary'
        result = self.inspect(campaign)
        self.assertNotIn('do-not-copy-into-summary', json.dumps(result))

    def test_each_task_has_its_own_matrix_and_contract(self):
        campaign = self.campaign()
        campaign['tasks'].append({'id': 'second-task', 'contract_sha256': 'b' * 64})
        result = self.inspect(campaign)
        self.assertEqual(len(result['missing_trials']), 6)
        self.assertIsNone(result['results']['model-0']['nex']['all_tokens_per_accepted_trial'])
        for original in list(campaign['runs']):
            run = copy.deepcopy(original)
            run['id'] += '-second';run['task'] = 'second-task';run['calls'][0]['id'] += '-second'
            receipt = {'schema': 'nex.llm-acceptance/1', 'trial_id': run['id'],
                'contract_sha256': 'b' * 64, 'passed': True, 'checks': [{'name': 'second-check', 'exit_code': 0}]}
            run['acceptance'] = self.artifact(run['id'] + '.json', receipt)
            campaign['runs'].append(run)
        result = self.inspect(campaign)
        self.assertTrue(result['matrix_complete'])
        self.assertEqual(result['results']['model-0']['nex']['attempted_trials'], 4)

    def test_acceptance_receipt_binding_and_failed_checks(self):
        for field, value in [('trial_id', 'other'), ('contract_sha256', 'b' * 64), ('passed', False),
                             ('checks', [{'name': 'failed', 'exit_code': 1}])]:
            with self.subTest(field=field):
                campaign = self.campaign()
                run = campaign['runs'][0]
                receipt = json.loads((self.root / run['acceptance']['path']).read_text())
                receipt[field] = value
                run['acceptance'] = self.artifact(run['acceptance']['path'], receipt)
                with self.assertRaises(tool.LedgerError):
                    self.inspect(campaign)

    def test_duplicate_trial_slot_provider_request_and_model_alias(self):
        for kind in ['trial', 'slot', 'request', 'model']:
            with self.subTest(kind=kind):
                campaign = self.campaign(models=2)
                if kind == 'trial':
                    campaign['runs'].append(copy.deepcopy(campaign['runs'][0]))
                elif kind == 'slot':
                    campaign['runs'][3]['repeat'] = 0
                elif kind == 'request':
                    campaign['runs'][1]['calls'][0]['id'] = campaign['runs'][0]['calls'][0]['id']
                else:
                    campaign['models'][1]['revision'] = campaign['models'][0]['revision']
                with self.assertRaises(tool.LedgerError):
                    self.inspect(campaign)

    def test_token_counts_are_integers_and_cache_is_subset(self):
        for field, value in [('input_tokens', True), ('input_tokens', -1), ('input_tokens', 1.5),
                             ('input_tokens', 10**12 + 1), ('cached_input_tokens', 101), ('output_tokens', None)]:
            with self.subTest(field=field, value=value):
                campaign = self.campaign()
                campaign['runs'][0]['calls'][0]['usage'][field] = value
                with self.assertRaises(tool.LedgerError):
                    self.inspect(campaign)

    def test_unknown_cache_split_preserves_actual_total_usage(self):
        campaign = self.campaign()
        nex = [run for run in campaign['runs'] if run['language'] == 'nex']
        nex[0]['calls'][0]['usage']['cached_input_tokens'] = None
        report = self.inspect(campaign)
        row = report['results']['model-0']['nex']
        self.assertTrue(row['usage_complete'])
        self.assertFalse(row['cache_usage_complete'])
        self.assertEqual(row['calls_without_cache_usage'], 1)
        self.assertEqual(row['known_input_tokens'], 200)
        self.assertEqual(row['known_cached_input_tokens'], 40)
        self.assertEqual(row['known_uncached_input_tokens'], 60)
        self.assertEqual(row['all_tokens_per_accepted_trial'], {'numerator': 120, 'denominator': 1})
        self.assertTrue(report['usage_complete_for_observed_calls'])
        self.assertFalse(report['cache_usage_complete_for_observed_calls'])
        del nex[0]['calls'][0]['usage']['cached_input_tokens']
        with self.assertRaises(tool.LedgerError):
            self.inspect(campaign)

    def test_artifact_mutation_wrong_pin_and_escape(self):
        for kind in ['mutation', 'pin', 'parent', 'absolute', 'symlink']:
            with self.subTest(kind=kind):
                campaign = self.campaign()
                reference = campaign['runs'][0]['calls'][0]['evidence']
                if kind == 'mutation':
                    (self.root / reference['path']).write_text('changed')
                elif kind == 'pin':
                    reference['sha256'] = 'b' * 64
                elif kind == 'parent':
                    reference['path'] = '../outside.json'
                elif kind == 'absolute':
                    reference['path'] = str(self.root / reference['path'])
                else:
                    link = self.root / 'outside-link.json'
                    link.symlink_to(SCRIPT)
                    self.addCleanup(lambda: link.unlink(missing_ok=True))
                    reference['path'] = link.name
                with self.assertRaises((tool.LedgerError, OSError)):
                    self.inspect(campaign)

    def test_costs_remain_exact_and_currencies_separate(self):
        campaign = self.campaign()
        runs = [r for r in campaign['runs'] if r['language'] == 'nex']
        for run in runs:
            run['calls'][0]['confirmed_cost'] = {'amount': '999999999999.999999999999', 'currency': 'USD'}
        result = self.inspect(campaign)['results']['model-0']['nex']
        self.assertEqual(result['confirmed_costs']['USD'], '1999999999999.999999999998')
        self.assertEqual(result['calls_without_confirmed_cost'], 0)
        runs[1]['calls'][0]['confirmed_cost']['currency'] = 'EUR'
        result = self.inspect(campaign)['results']['model-0']['nex']
        self.assertEqual(set(result['confirmed_costs']), {'USD', 'EUR'})
        runs[0]['calls'][0]['confirmed_cost'] = None
        result = self.inspect(campaign)['results']['model-0']['nex']
        self.assertEqual(result['calls_without_confirmed_cost'], 1)
        self.assertEqual(result['all_tokens_per_accepted_trial'], {'numerator': 120, 'denominator': 1})

    def test_invalid_costs_are_rejected(self):
        for amount in ['-1', 'NaN', '1e3', '0.0000000000001', 1.5]:
            with self.subTest(amount=amount):
                campaign = self.campaign()
                campaign['runs'][0]['calls'][0]['confirmed_cost'] = {'amount': amount, 'currency': 'USD'}
                with self.assertRaises(tool.LedgerError):
                    self.inspect(campaign)

    def test_cli_success_partial_invalid_and_exclusive_output(self):
        campaign = self.campaign()
        self.save(campaign)
        output = self.root / 'summary.json'
        args = [sys.executable, '-B', str(SCRIPT), str(self.path), '--output', str(output)]
        before = self.path.read_bytes()
        result = subprocess.run(args, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['data_kind'], 'synthetic')
        saved = output.read_bytes()
        self.assertEqual(subprocess.run(args, capture_output=True).returncode, 2)
        self.assertEqual(output.read_bytes(), saved)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(subprocess.run(args[:-1] + [str(self.path)], capture_output=True).returncode, 2)
        self.assertEqual(self.path.read_bytes(), before)
        campaign['runs'].pop()
        self.save(campaign)
        self.assertEqual(subprocess.run(args[:4], capture_output=True).returncode, 1)
        self.path.write_bytes(b'{"schema":NaN}')
        self.assertEqual(subprocess.run(args[:4], capture_output=True).returncode, 2)

    def test_malformed_json_and_missing_metadata(self):
        for raw in [b'{"x":1,"x":2}', b'{"x":Infinity}', b'\xff']:
            self.path.write_bytes(raw)
            with self.assertRaises(tool.LedgerError):
                tool.summarize(self.path)
        campaign = self.campaign()
        del campaign['models'][0]['tokenizer']
        with self.assertRaises(tool.LedgerError):
            self.inspect(campaign)


if __name__ == '__main__':
    unittest.main()
