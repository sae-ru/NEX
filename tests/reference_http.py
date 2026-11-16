"""Real source030 HTTP requests own independent sequential reference contexts."""
from pathlib import Path
from host_fixture import stop_server
import argparse
import concurrent.futures
import hashlib
import http.client
import json
import os
import queue
import re
import ssl
import subprocess
import tempfile
import threading
import time

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('probe', type=Path)
p.add_argument('--openssl', default=os.environ.get('NEX_OPENSSL', 'openssl'))
p.add_argument('--output', type=Path)
a = p.parse_args()
root = Path(__file__).resolve().parents[1]
out = (a.output or Path(tempfile.mkdtemp(prefix='nex-reference-http-'))).resolve()
out.mkdir(parents=True, exist_ok=True)
probe = a.probe.resolve()
fixture = root/'tests/fixtures/reference-http'
files = {name: (fixture/name).read_text() for name in ['core.nex', 'server.nex']}
files['@std/http.nex'] = (root/'lib/http.nex').read_text()
bundle = out/'server.json'
bundle.write_text(json.dumps({'schema': 'nex.sources/1', 'entry': 'server.nex', 'files': files}))
report = {'schema': 'nex.reference-http-acceptance/1', 'ok': False,
          'probe_sha256': hashlib.sha256(probe.read_bytes()).hexdigest(),
          'sources_sha256': {name: hashlib.sha256(text.encode()).hexdigest() for name, text in files.items()},
          'images': [], 'servers': [], 'requests': [], 'controls': [], 'agreement': [], 'rejections': []}


def save():
    (out/'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def run(command, label, expected=0, env=None):
    r = subprocess.run(list(map(str, command)), cwd=out, env=env, capture_output=True,
                       text=True, encoding='utf-8', timeout=300)
    (out/(label+'.stdout')).write_text(r.stdout, encoding='utf-8')
    (out/(label+'.stderr')).write_text(r.stderr, encoding='utf-8')
    assert r.returncode == expected, (label, r.returncode, r.stdout[-2000:], r.stderr[-3000:])
    return r


payloads = ['', 'λ\0🙂', '🧠e\u0301', 'line\nnext']
wrapper = 'module reference_http_agreement;import "./core.nex" as core;\nfn main()->unit !{state,io,throw}{\n'
for text in payloads:
    literal = json.dumps(text, ensure_ascii=False)
    wrapper += 'print(encode_json(core::exercise("alice",'+literal+')));\n'
wrapper += 'print(core::caught("typed"));}\n'
agreement = out/'agreement.json'
agreement.write_text(json.dumps({'schema': 'nex.sources/1', 'entry': 'main.nex',
                                 'files': {'main.nex': wrapper, 'core.nex': files['core.nex']}}))
reference = json.loads(run([probe, 'reference', agreement], 'reference').stdout)
assert reference['kind'] == 'return' and reference['live_delta'] == 0
entry = json.loads(run([probe, 'entry-test', agreement, out/'typescript 🧠'], 'typescript').stdout)
assert entry['ok'] and not entry['stderr'] and entry['stdout'] == reference['output']
expected = [json.loads(line) for line in reference['output'].splitlines()]
assert expected[-1] == 42 and len(expected) == len(payloads)+1
for body, result in zip(payloads, expected):
    assert result == {'user': 'alice', 'body': body+'!', 'initial': '41',
                      'live': str(41+len(body)), 'captured': str(41+len(body)), 'snapshot': body}
report['agreement'] = expected

auth = out/'auth.json'
auth.write_text(json.dumps({'schema': 'nex.auth/1', 'tokens': [
    {'user': user, 'sha256': hashlib.sha256(('fixture-'+user).encode()).hexdigest()}
    for user in ['alice', 'bob']]}))
file_root = out/'files'
file_root.mkdir(exist_ok=True)
(file_root/'input').write_text('abcdef')
(out/'certificate.cnf').write_text('[req]\ndistinguished_name=dn\nx509_extensions=ext\nprompt=no\n[dn]\nCN=127.0.0.1\n[ext]\nsubjectAltName=IP:127.0.0.1\nbasicConstraints=CA:TRUE\n')
run([a.openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
     '-config', out/'certificate.cnf', '-keyout', out/'key.pem', '-out', out/'cert.pem'], 'certificate')
tls_context = ssl.create_default_context(cafile=str(out/'cert.pem'))

negative = {
    'request-type': ('server fn handle(req:str)->http::Response !{state}{return http::text_response(200,str(cell_read(cell_new(42))));}', 'E_HTTP_SIGNATURE'),
    'result-type': ('server fn handle(req:http::Request)->cell<i64> !{state}{return cell_new(42);}', 'E_HTTP_SIGNATURE'),
    'realm': ('fn handle(req:http::Request)->http::Response !{state}{return http::text_response(200,str(cell_read(cell_new(42))));}', 'E_HTTP_SIGNATURE'),
    'parallel-context': ('server fn handle(req:http::Request)->http::Response !{state,task}{let value:cell<i64>=cell_new(42);let items:list<i64>=parallel_map([1],fn(x:i64)->i64{return x;},1);task_yield();return http::text_response(200,str(cell_read(value)));}', 'E_CELL_CONCURRENCY'),
}
for name, (body, code) in negative.items():
    path = out/('reject-'+name+'.json')
    path.write_text(json.dumps({'schema': 'nex.sources/1', 'entry': 'main.nex', 'files': {
        'main.nex': 'module rejected_reference_http;import "std/http.nex" as http;'+body+'fn main()->unit{}',
        '@std/http.nex': files['@std/http.nex']}}))
    rejected = run([probe, 'server', path, out/'rejected-builds', 'debug'], 'reject-'+name, expected=1)
    assert code in rejected.stderr, (name, rejected.stderr)
    report['rejections'].append({'name': name, 'code': code, 'passed': True})


class Server:
    def __init__(self, image, label, *, tls=False, budget=10000000, timeout=10000, files=True):
        self.label, self.tls = label, tls
        for name in ['started', 'finalizer']:
            (file_root/name).unlink(missing_ok=True)
        command = [str(image), '--auth', str(auth), '--database', str(out/(label+'.sqlite')),
                   '--port', '0', '--workers', '4', '--budget', str(budget), '--timeout-ms', str(timeout)]
        if files:
            command += ['--files-root', str(file_root), '--files-write', '1']
        if tls:
            command += ['--cert', str(out/'cert.pem'), '--key', str(out/'key.pem')]
        self.error_path = out/(label+'-server.stderr')
        self.error_file = self.error_path.open('w', encoding='utf-8')
        self.process = subprocess.Popen(command, cwd=out, stdout=subprocess.PIPE, stderr=self.error_file,
                                        text=True, encoding='utf-8', env={**os.environ, 'NEX_RESOURCE_DIR': str(out/'absent-resources')})
        self.lines = queue.Queue()
        self.reader = threading.Thread(target=lambda: self.lines.put(self.process.stdout.readline()), daemon=True)
        self.reader.start()
        try:
            self.first = self.lines.get(timeout=20)
            match = re.fullmatch(r'NEX server (https?)://127\.0\.0\.1:([0-9]+)\n', self.first)
            assert match and (match[1] == 'https') == tls, (label, self.first)
            self.port = int(match[2])
        except BaseException:
            self.stop()
            raise

    def connection(self):
        return http.client.HTTPSConnection('127.0.0.1', self.port, context=tls_context, timeout=8) if self.tls else http.client.HTTPConnection('127.0.0.1', self.port, timeout=8)

    def request(self, path, body='λ\0🙂', user='alice', method='POST'):
        connection = self.connection()
        try:
            connection.request(method, path, body=body.encode(), headers={'Authorization': 'Bearer fixture-'+user})
            response = connection.getresponse()
            raw = response.read().decode('utf-8')
            result = json.loads(raw) if response.getheader('Content-Type').startswith('application/json') else raw
            row = {'server': self.label, 'path': path, 'user': user, 'status': response.status,
                   'body': result, 'request_id': response.getheader('X-Request-Id')}
            assert row['request_id']
            return row
        finally:
            connection.close()

    def stop(self):
        if self.process.poll() is None:
            stop_server(self.process)
        try:
            stdout, _ = self.process.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.kill(); self.process.communicate(); raise
        self.reader.join(timeout=2)
        self.error_file.close()
        stderr = self.error_path.read_text(encoding='utf-8')
        (out/(self.label+'-server.stdout')).write_text(getattr(self, 'first', '')+stdout)
        assert self.process.returncode == 0 and 'E_INTERNAL_LEAK' not in stderr and 'left live values' not in stderr, (self.label, self.process.returncode, stderr)
        report['servers'].append({'label': self.label, 'exit': self.process.returncode, 'no_live_values': True})
        save()
        return stderr


images = []
plain = out/'plain.json'
plain.write_text(json.dumps({'schema': 'nex.sources/1', 'entry': 'plain.nex', 'files': {
    'plain.nex': (fixture/'plain.nex').read_text(), 'core.nex': files['core.nex'],
    '@std/http.nex': files['@std/http.nex']}}))
for profile in ['debug', 'release']:
    exports = json.dumps({'entry': 'reference_http_core::exercise',
                          'exports': ['reference_http_core::'+name for name in ['cycle', 'fail', 'caught']]})
    archive = json.loads(run([probe, 'library', bundle, out/'builds', profile, exports], profile+'-archive').stdout)
    for linked in [False, True]:
        label = profile+('-archive' if linked else '-whole')
        command = [probe, 'server-library' if linked else 'server', bundle, out/'builds', profile]
        if linked:
            command.append(json.dumps({'entry': 'handle', 'libraries': [archive]}))
        built = json.loads(run(command, label+'-build').stdout)
        warm = json.loads(run(command, label+'-warm').stdout)
        assert warm['cached'] and warm['key'] == built['key']
        image = Path(built['artifact'])
        metadata = json.loads((image.parent/'build.json').read_text())
        context = metadata['reference_context']
        assert context['schema'] == 'nex.reference-http-context/1' and context['thread_affine'] and not context['shared_between_requests']
        assert not metadata['runtime_requirements']['tasks']
        projection = Path(metadata['runtime_source_projection'])
        for name in ['nex_cells.cpp', 'nex_cells.h', 'nex_cell_host.cpp', 'nex_cell_host.h']:
            assert (projection/name).read_bytes() == (root/'runtime'/name).read_bytes()
        bridge = (image.parent/'server-bridge.cpp').read_text()
        assert 'nex_cell_request_enter(0)' in bridge and 'diagnostic.payload.reset()' in bridge
        if linked:
            assert built['library_abi'] == archive['library_abi']
        report['images'].append({'label': label, 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                                 'key': built['key'], 'context': context, 'warm_cached': True})
        images.append((label, image))
    built = json.loads(run([probe, 'server', plain, out/'builds', profile], profile+'-plain-build').stdout)
    image = Path(built['artifact'])
    bridge = (image.parent/'server-bridge.cpp').read_text()
    assert 'nex_cell_request_enter(0)' in bridge and 'nexrt::Handle**' not in bridge
    metadata = json.loads((image.parent/'build.json').read_text())
    report['images'].append({'label': profile+'-plain', 'sha256': hashlib.sha256(image.read_bytes()).hexdigest(),
                             'key': built['key'], 'context': metadata['reference_context'], 'declares_throw': False})
    for tls in [False, True]:
        server = Server(image, profile+'-plain'+('-https' if tls else '-http'), tls=tls, files=False)
        try:
            for body, value in zip(payloads, expected):
                row = server.request('/api/normal', body)
                assert row['status'] == 200 and row['body'] == value, row
                report['requests'].append(row)
        finally:
            assert not server.stop()
save()
bundle.rename(out/'retained-server-input.json')
plain.rename(out/'retained-plain-input.json')

for label, image in images:
    for tls in [False, True]:
        server = Server(image, label+('-https' if tls else '-http'), tls=tls)
        try:
            for body, value in zip(payloads, expected):
                row = server.request('/api/normal', body)
                assert row['status'] == 200 and row['body'] == value, row
                report['requests'].append(row)
            def one_request(index):
                user = 'alice' if index % 2 == 0 else 'bob'
                body = 'request'+str(index)+'\0🧠'
                row = server.request('/api/normal', body, user)
                assert row['status'] == 200 and row['body'] == {'user': user, 'body': body+'!', 'initial': '41', 'live': str(41+len(body)), 'captured': str(41+len(body)), 'snapshot': body}, row
                return row
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
                rows = list(pool.map(one_request, range(24)))
            assert len({row['request_id'] for row in rows}) == 24
            report['requests'] += rows
            for path, status, body in [('/api/caught', 200, '42'), ('/api/uncaught', 500, None), ('/api/trap', 500, None), ('/api/caught', 200, '42')]:
                row = server.request(path)
                assert row['status'] == status, row
                if body is not None:
                    assert row['body'] == body
                else:
                    assert row['body']['error']['code'] == ('E_ASSERT' if path == '/api/trap' else 'E_SOURCE_EXCEPTION')
                report['requests'].append(row)
            for path, body, status, result in [('/api/put', 'committed', 200, 'committed'), ('/api/rollback', 'discarded', 400, 'rolled back'), ('/api/get', '', 200, 'committed'), ('/api/db-throw', 'also discarded', 500, None), ('/api/get', '', 200, 'committed')]:
                row = server.request(path, body)
                assert row['status'] == status and (row['body'] == result if result is not None else row['body']['error']['code'] == 'E_SOURCE_EXCEPTION'), row
                report['requests'].append(row)
        finally:
            stderr = server.stop()
        packets = [json.loads(line[len('NEX_SOURCE_EXCEPTION '):]) for line in stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION ')]
        assert len(packets) == 2 and all(row['code'] == 'reference_http_core::Fault' for row in packets), packets

for kind, budget, timeout, expected_code in [('budget', 2000, 60000, 'E_LIMIT'), ('deadline', 100000000, 20, 'E_TIMEOUT'), ('cancel', 100000000, 30000, 'E_CANCELLED')]:
    server = Server(images[-1][1], 'control-'+kind, budget=budget, timeout=timeout)
    try:
        if kind == 'cancel':
            connection = server.connection()
            connection.request('POST', '/api/spin', body=b'loop', headers={'Authorization': 'Bearer fixture-alice'})
            deadline = time.monotonic()+5
            while not (file_root/'started').exists() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert (file_root/'started').is_file()
            connection.close()
            deadline = time.monotonic()+6
            while b'E_CANCELLED' not in server.error_path.read_bytes() and time.monotonic() < deadline:
                time.sleep(0.01)
            assert b'E_CANCELLED' in server.error_path.read_bytes(), 'disconnect did not cancel before server shutdown'
        else:
            row = server.request('/api/spin', 'loop')
            assert row['body']['error']['code'] == expected_code, row
            report['requests'].append(row)
        deadline = time.monotonic()+6
        while time.monotonic() < deadline:
            row = server.request('/api/caught')
            if row['status'] == 200:
                break
        assert row['status'] == 200 and row['body'] == '42'
    finally:
        stderr = server.stop()
    assert (file_root/'started').is_file() and not (file_root/'finalizer').exists()
    assert expected_code in stderr, (kind, stderr)
    report['controls'].append({'kind': kind, 'code': expected_code, 'finalizer_skipped': True, 'next_request_passed': True})
    save()
report['ok'] = True
save()
print(json.dumps({'ok': True, 'images': len(report['images']), 'servers': len(report['servers']), 'requests': len(report['requests']), 'report': str(out/'report.json')}))
