"""Loopback-only provider accounting with a local synthetic HTTP peer."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nex_local_provider', ROOT / 'experiments/quality/llm-campaign-v1/local_provider.py')
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
INSTANCE = 'nex-cost-synthetic'


def inventory():
    return {'models': [{'type': 'llm', 'key': p.MODEL, 'format': 'gguf',
        'architecture': 'qwen35', 'quantization': {'name': 'Q8_0'},
        'loaded_instances': [{'id': INSTANCE, 'config': {'context_length': 16384, 'parallel': 1}}]}]}


class Provider(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex-local-provider-')
        self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        self.requests = []; self.raw_requests = []; self.request_id = None
        self.status = 200; self.location = None; self.models = inventory()
        self.response = {'model_instance_id': INSTANCE,
            'output': [{'type': 'reasoning', 'content': 'synthetic reasoning'},
                       {'type': 'message', 'content': '{"action":"submit"}'}],
            'stats': {'input_tokens': 23, 'total_output_tokens': 7, 'reasoning_output_tokens': 4}}
        owner = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def do_GET(self):
                owner.requests.append(('GET', self.path, None))
                self.send_response(200); self.end_headers(); self.wfile.write(json.dumps(owner.models).encode())
            def do_POST(self):
                raw = self.rfile.read(int(self.headers['Content-Length']))
                owner.raw_requests.append(raw)
                owner.requests.append(('POST', self.path, json.loads(raw)))
                self.send_response(owner.status)
                if owner.request_id: self.send_header('X-Request-ID', owner.request_id)
                if owner.location: self.send_header('Location', owner.location)
                self.end_headers(); self.wfile.write(json.dumps(owner.response).encode())
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.addCleanup(self.stop)
        self.client = p.Client('http://127.0.0.1:' + str(self.server.server_port), timeout=3)

    def stop(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(timeout=5)

    def test_actual_totals_unknown_cache_no_reasoning_double_count_and_no_proxy(self):
        self.request_id = 'synthetic-provider-request'
        with patch.dict(os.environ, {'HTTP_PROXY': 'http://192.0.2.1:1', 'http_proxy': 'http://192.0.2.1:1'}):
            text, record = self.client.chat(INSTANCE, 'system 🧠', 'task', self.root / 'call')
        self.assertIsNone(record['error']); self.assertEqual(text, '{"action":"submit"}')
        self.assertEqual(record['usage'], {'input_tokens': 23, 'cached_input_tokens': None, 'output_tokens': 7})
        self.assertIsNone(record['confirmed_cost'])
        self.assertEqual(record['id'], self.request_id); self.assertTrue(record['producer_trace_id'].startswith('host-'))
        posts = [row for row in self.requests if row[0] == 'POST']; self.assertEqual(len(posts), 1)
        payload = posts[0][2]
        self.assertEqual(payload['integrations'], []); self.assertFalse(payload['store']); self.assertFalse(payload['stream'])
        self.assertEqual(payload['max_output_tokens'], 4096)
        self.assertEqual(payload['reasoning'], 'off')
        self.assertEqual(json.loads((self.root / 'call/request.json').read_bytes()), payload)
        self.assertEqual(self.raw_requests[0], (self.root / 'call/request.json').read_bytes())
        self.assertEqual(json.loads((self.root / 'call/response.json').read_bytes()), self.response)
        self.assertEqual(json.loads((self.root / 'call/call.json').read_bytes()), record)
        self.assertEqual(record['request_sha256'], __import__('hashlib').sha256((self.root / 'call/request.json').read_bytes()).hexdigest())

    def test_external_hosts_credentials_redirects_and_unowned_models_are_rejected(self):
        for url in ['https://127.0.0.1:1234', 'http://localhost:1234', 'http://192.168.1.99:1234',
                    'https://api.openai.com', 'http://user:secret@127.0.0.1:1234',
                    'http://127.0.0.1:1234/path', 'http://127.0.0.1:1234?proxy=x']:
            with self.subTest(url=url), self.assertRaises(ValueError): p.Client(url)
        with self.assertRaises(ValueError): self.client.request('POST', '/api/v1/models/download', {})
        self.status = 302; self.location = 'http://192.0.2.1:9999/cloud'; self.response = {}
        _, record = self.client.chat(INSTANCE, 'system', 'task', self.root / 'redirect')
        self.assertIn('HTTP status 302', record['error']); self.assertIsNone(record['usage'])
        self.assertEqual(len([r for r in self.requests if r[0] == 'POST']), 1)
        self.models['models'][0]['key'] = 'other-model'
        with self.assertRaises(ValueError): self.client.chat(INSTANCE, 's', 't', self.root / 'wrong-model')
        self.assertFalse((self.root / 'wrong-model').exists())

    def test_failed_calls_identity_mismatch_and_missing_usage_remain_evidence(self):
        self.response['model_instance_id'] = 'other-instance'
        _, record = self.client.chat(INSTANCE, 's', 't', self.root / 'identity')
        self.assertIn('another model', record['error']); self.assertEqual(record['usage']['output_tokens'], 7)
        self.response['model_instance_id'] = INSTANCE; del self.response['stats']
        _, record = self.client.chat(INSTANCE, 's', 't', self.root / 'missing-usage')
        self.assertIsNone(record['error']); self.assertIsNone(record['usage'])
        self.status = 500; self.response = {'error': 'synthetic server error'}
        _, record = self.client.chat(INSTANCE, 's', 't', self.root / 'error')
        self.assertIn('HTTP status 500', record['error']); self.assertIsNone(record['usage'])
        self.assertTrue((self.root / 'error/response.json').is_file())

    def test_invalid_and_partial_token_records_are_not_estimated(self):
        for bad in [True, -1, 1.2, 10**12 + 1]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p.usage({'stats': {'input_tokens': bad, 'total_output_tokens': 1}})
        self.assertIsNone(p.usage({'stats': {'input_tokens': 123}}))
        with self.assertRaises(ValueError): p.usage({'stats': {'input_tokens': 1, 'total_output_tokens': 2, 'cached_input_tokens': 2}})
        with self.assertRaises(ValueError): p.usage({'stats': {'input_tokens': 1, 'total_output_tokens': 2, 'reasoning_output_tokens': 3}})
        for raw in [b'{"x":1,"x":2}', b'{"x":NaN}', b'\xff']:
            with self.assertRaises(ValueError): p.decode(raw)

    def test_interrupted_call_is_retained_without_a_guessed_usage(self):
        original = self.client.request
        def interrupted(method, *args, **kwargs):
            if method == 'POST': raise KeyboardInterrupt()
            return original(method, *args, **kwargs)
        with patch.object(self.client, 'request', side_effect=interrupted), self.assertRaises(KeyboardInterrupt):
            self.client.chat(INSTANCE, 's', 't', self.root / 'interrupted')
        record = json.loads((self.root / 'interrupted/call.json').read_bytes())
        self.assertTrue(record['interrupted']); self.assertTrue(record['transport_finished'])
        self.assertIsNone(record['usage']); self.assertEqual(record['error'], 'KeyboardInterrupt')
        self.assertTrue((self.root / 'interrupted/request.json').is_file())


class Readiness(unittest.TestCase):
    """Synthetic ownership controls; no real model/CLI is loaded here."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex-readiness-control-')
        self.addCleanup(self.temp.cleanup); self.root = Path(self.temp.name)
        source = ROOT / 'experiments/quality/llm-campaign-v1/readiness.py'
        spec = importlib.util.spec_from_file_location('nex_readiness', source)
        self.r = importlib.util.module_from_spec(spec); spec.loader.exec_module(self.r)
        model = self.root / 'model'; model.mkdir(); file = model / 'Qwen3.8-27B-Q8_0.gguf'; file.write_bytes(b'GGUF synthetic')
        info = file.stat(); self.weights = self.root / 'weights.json'
        self.weights.write_text(json.dumps({'schema': 'nex.local-model-artifacts/1', 'model': p.MODEL,
            'quantization': 'Q8_0', 'root': str(model), 'primary_gguf': file.name,
            'files': [{'path': file.name, 'sha256': __import__('hashlib').sha256(file.read_bytes()).hexdigest(),
                'dev': info.st_dev, 'ino': info.st_ino, 'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}]}))
        self.profile = ROOT / 'experiments/quality/llm-campaign-v1/local-model.json'
        self.instance = None; self.commands = []; self.existing = False; self.content = '{"ready":true}'
        owner = self
        class Fake:
            def models(self):
                data = inventory()
                data['models'][0]['loaded_instances'] = ([] if owner.instance is None and not owner.existing else
                    [{'id': owner.instance or 'user-existing', 'config': {'context_length': 16384, 'parallel': 1}}])
                return data
            def chat(self, instance, system, prompt, output, **kwargs):
                owner.assertEqual(instance, owner.instance); owner.assertEqual(kwargs['max_tokens'], 32)
                output.mkdir()
                return owner.content, {'id': 'synthetic-response', 'http_status': 200, 'returned_instance': instance,
                    'error': None, 'usage': {'input_tokens': 10, 'cached_input_tokens': None, 'output_tokens': 4}}
        self.client_patch = patch.object(self.r.p, 'Client', side_effect=lambda *args, **kwargs: Fake())
        self.client_patch.start(); self.addCleanup(self.client_patch.stop)
        def command(argv, **kwargs):
            owner.commands.append(argv)
            if argv[1] == 'load':
                owner.assertEqual(argv[2], p.MODEL)
                owner.assertNotIn('--no-engine-config-file', argv)
                owner.assertNotIn('--no-engine-cwd', argv)
                owner.instance = argv[argv.index('--identifier') + 1]
            elif argv[1] == 'unload':
                owner.assertEqual(argv[2], owner.instance); owner.assertNotIn('--all', argv); owner.instance = None
            else: owner.fail('unexpected synthetic CLI action')
            return __import__('subprocess').CompletedProcess(argv, 0, b'', b'')
        self.command_patch = patch.object(self.r.subprocess, 'run', side_effect=command)
        self.command_patch.start(); self.addCleanup(self.command_patch.stop)

    def test_owned_probe_unloads_only_its_instance(self):
        result = self.r.run(self.profile, self.weights, self.root / 'probe', Path('/synthetic/lms'))
        self.assertTrue(result['ok']); self.assertTrue(result['owned_instance_unloaded'])
        self.assertEqual(result['benchmark_trials'], 0); self.assertEqual(result['response_generations_observed'], 1)
        self.assertIsNone(self.instance); self.assertEqual(len(self.commands), 2)

    def test_artifact_pins_are_reproducible_and_changed_files_rejected(self):
        spec = importlib.util.spec_from_file_location('nex_weight_pins',
            ROOT / 'experiments/quality/llm-campaign-v1/weights.py')
        weights = importlib.util.module_from_spec(spec); spec.loader.exec_module(weights)
        destination = self.root / 'fresh-weights.json'
        result = weights.pin(self.root / 'model', destination)
        observed, raw = self.r.verify_weights(destination)
        self.assertEqual(result, observed)
        self.assertEqual(observed['files'][0]['sha256'],
            __import__('hashlib').sha256(b'GGUF synthetic').hexdigest())
        with self.assertRaises(FileExistsError): weights.pin(self.root / 'model', destination)
        (self.root / 'model' / weights.PRIMARY).write_bytes(b'GGUF changed')
        with self.assertRaisesRegex(ValueError, 'changed'): self.r.verify_weights(destination)

    def test_invalid_boolean_response_is_not_success_and_still_unloads(self):
        self.content = '{"ready":1}'
        result = self.r.run(self.profile, self.weights, self.root / 'invalid', Path('/synthetic/lms'))
        self.assertFalse(result['ok']); self.assertTrue(result['owned_instance_unloaded'])
        self.assertIsNone(self.instance); self.assertEqual(len(self.commands), 2)

    def test_existing_user_instance_is_never_replaced_or_unloaded(self):
        self.existing = True
        with self.assertRaises(ValueError): self.r.run(self.profile, self.weights, self.root / 'busy', Path('/synthetic/lms'))
        self.assertEqual(self.commands, []); self.assertFalse((self.root / 'busy').exists())


if __name__ == '__main__': unittest.main(verbosity=2)
