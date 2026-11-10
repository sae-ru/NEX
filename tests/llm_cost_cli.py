"""Public cost CLI: same ledger, real resource selection, no project writes.

All usage records in these controls are synthetic. No model is contacted.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
import support as h

HELPER = h.REPO / 'experiments/quality/llm_cost.py'


class CostCLI(h.ToolchainCase):
    def setUp(self):
        super().setUp()
        self.env = dict(os.environ, NEX_RESOURCE_DIR=str(h.REPO), NEX_PYTHON=sys.executable)
        # This command must work beside a malformed/old project and graph. Any
        # project load would fail; any write would change the complete snapshot.
        (self.root / 'nex.json').write_text('{"language":"0.1","entry":"missing.nex"}')
        graph = self.root / '.nex'
        graph.mkdir()
        (graph / 'graph.db').write_bytes(b'not a database\0preserve me')
        self.ledger = self.root / "cost %, 🧠 $(not-a-command).json"
        self.campaign = self.make_campaign()
        self.save()

    def evidence(self, name, value):
        raw = json.dumps(value, ensure_ascii=False).encode('utf-8')
        (self.root / name).write_bytes(raw)
        return {'path': name, 'sha256': hashlib.sha256(raw).hexdigest()}

    def make_campaign(self):
        contract = hashlib.sha256(b'synthetic contract').hexdigest()
        value = {'schema': 'nex.llm-cost-ledger/1', 'data_kind': 'synthetic',
                 'languages': ['nex', 'cpp', 'python'], 'repeats': 1,
                 'protocol': self.evidence('protocol.json', {'synthetic': True}),
                 'models': [{'id': 'synthetic-model', 'provider': 'synthetic-provider',
                             'revision': 'synthetic-revision', 'tokenizer': 'synthetic-tokenizer',
                             'settings_sha256': 'a' * 64}],
                 'tasks': [{'id': 'synthetic-task', 'contract_sha256': contract}], 'runs': []}
        for language in value['languages']:
            value['runs'].append({'id': language, 'model': 'synthetic-model', 'task': 'synthetic-task',
                'repeat': 0, 'language': language, 'status': 'accepted', 'wall_ms': 1,
                'acceptance': self.evidence(language + '-acceptance.json', {
                    'schema': 'nex.llm-acceptance/1', 'trial_id': language,
                    'contract_sha256': contract, 'passed': True,
                    'checks': [{'name': 'synthetic-check', 'exit_code': 0}]}),
                'calls': [{'id': language, 'evidence': self.evidence(language + '-response.json',
                    {'synthetic': True, 'untrusted_text': 'recorded text is never executed 🧠'}),
                    'usage': {'input_tokens': 10, 'cached_input_tokens': 2, 'output_tokens': 3},
                    'confirmed_cost': None}]})
        return value

    def save(self):
        self.ledger.write_text(json.dumps(self.campaign, ensure_ascii=False), encoding='utf-8')

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): p.read_bytes()
                for p in self.root.rglob('*') if p.is_file()}

    def call(self, *args, compiler=h.NEX, env=None):
        return subprocess.run([str(compiler), *map(str, args)], cwd=self.root,
                              env=self.env if env is None else env, capture_output=True, timeout=15)

    def test_same_bytes_and_exit_codes_as_the_existing_ledger(self):
        for kind, code in [('complete', 0), ('missing', 1), ('unknown-usage', 1), ('invalid', 2)]:
            with self.subTest(kind=kind):
                if kind == 'missing':
                    saved_run = self.campaign['runs'].pop()
                elif kind == 'unknown-usage':
                    self.campaign['runs'].append(saved_run)
                    self.campaign['runs'][0]['calls'][0]['usage'] = None
                self.save()
                if kind == 'invalid':
                    self.ledger.write_bytes(b'{"schema":1,"schema":2}')
                before = self.snapshot()
                direct = subprocess.run([sys.executable, '-I', '-B', '-X', 'utf8', str(HELPER),
                                         str(self.ledger)], cwd=self.root, capture_output=True, timeout=15)
                public = self.call('cost', self.ledger)
                self.assertEqual(public.returncode, code, public.stderr)
                self.assertEqual((public.returncode, public.stdout, public.stderr),
                                 (direct.returncode, direct.stdout, direct.stderr))
                self.assertEqual(self.snapshot(), before)
                summary = json.loads(public.stdout)
                self.assertEqual(summary['schema'], 'nex.llm-cost-summary/1')
                if code != 2:
                    self.assertEqual(summary['data_kind'], 'synthetic')
                    self.assertFalse(summary['eligible_for_comparison_review'])

    def test_exclusive_output_preserves_input_and_existing_files(self):
        before = self.snapshot()
        output = self.root / 'new summary 🧠.json'
        success = self.call('cost', self.ledger, '--output', output, '--json')
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual(output.read_bytes(), success.stdout)
        expected = dict(before, **{output.name: success.stdout})
        self.assertEqual(self.snapshot(), expected)
        for target in [output, self.ledger, self.root / 'missing' / 'out.json']:
            result = self.call('cost', self.ledger, '-o', target)
            self.assertEqual(result.returncode, 2, result.stderr)
            self.assertFalse(json.loads(result.stdout)['valid'])
            self.assertEqual(self.snapshot(), expected)

    def test_installed_layout_and_explicit_resources_do_not_fall_back(self):
        stage = self.root / 'installation %, 🧠'
        binary = stage / 'bin' / Path(h.NEX).name
        binary.parent.mkdir(parents=True)
        shutil.copy2(h.NEX, binary)
        resources = stage / 'share/nex'
        helper = resources / 'experiments/quality/llm_cost.py'
        helper.parent.mkdir(parents=True)
        shutil.copy2(HELPER, helper)
        env = dict(self.env, NEX_RESOURCE_DIR=str(resources))
        if os.name == 'nt':
            # This is a resource-layout check, not DLL-closure qualification.
            env['PATH'] = str(Path(h.NEX).parent) + os.pathsep + env.get('PATH', '')
        observed = self.call('cost', self.ledger, '--json', compiler=binary, env=env)
        ordinary = self.call('cost', self.ledger, '--json')
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.assertEqual(observed.stdout, ordinary.stdout)
        helper.unlink()
        failed = self.call('cost', self.ledger, '--json', compiler=binary, env=env)
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(json.loads(failed.stdout)['code'], 'E_RESOURCE')

    def test_invalid_options_and_missing_python_never_create_output(self):
        before = self.snapshot()
        for args in [(), (self.ledger, self.ledger), (self.ledger, '--kind', 'run'),
                     (self.ledger, '--interpreter-only'), (self.ledger, '--', 'anything'),
                     (self.ledger, '--output', ''), (self.ledger, '--task-steps', '1'),
                     (self.ledger, '--output', 'never.json', '-o', 'also-never.json')]:
            with self.subTest(args=args):
                failed = self.call('cost', *args, '--json')
                self.assertEqual(failed.returncode, 1, failed.stderr)
                self.assertEqual(json.loads(failed.stdout)['code'], 'E_OPTION')
                self.assertEqual(self.snapshot(), before)
        for python, code in [('nex-cost-deliberately-missing-python-executable', 'E_TOOL'),
                             (str(self.root / 'missing Python'), 'E_PROCESS')]:
            failed = self.call('cost', self.ledger, '--json',
                               env=dict(self.env, NEX_PYTHON=python))
            self.assertEqual(failed.returncode, 1)
            self.assertEqual(json.loads(failed.stdout)['code'], code)
            self.assertEqual(self.snapshot(), before)

    def test_isolated_python_and_advertised_scope(self):
        poisoned = self.root / 'python-path'
        poisoned.mkdir()
        marker = self.root / 'sitecustomize-ran'
        (poisoned / 'sitecustomize.py').write_text(
            'from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("executed")\n')
        observed = self.call('cost', self.ledger, '--json',
                             env=dict(self.env, PYTHONPATH=str(poisoned)))
        self.assertEqual(observed.returncode, 0, observed.stderr)
        self.assertFalse(marker.exists())
        feature = json.loads(self.call('describe', '--field', 'llm_cost', '--json').stdout)['value']
        self.assertEqual(feature, json.loads((h.REPO / 'llm/language-pack.json').read_bytes())['llm_cost'])
        for field in ['model_calls', 'network_requests', 'acceptance_commands_executed',
                      'graph_store_opened', 'missing_usage_estimated', 'synthetic_data_is_experiment',
                      'provider_usage_authenticated', 'output_overwrite']:
            self.assertIs(feature[field], False)
        guide = self.call('guide', '--kind', 'cost', '--json')
        self.assertEqual(guide.returncode, 0, guide.stderr)
        self.assertEqual(json.loads(guide.stdout)['text'], HELPER.with_suffix('.md').read_text())


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v'])
