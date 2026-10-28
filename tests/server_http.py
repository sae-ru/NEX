"""Real native HTTP/TLS, hashed credentials, durable per-principal APIs and rollback."""
import concurrent.futures
import hashlib
import http.client
import json
import os
from pathlib import Path
import queue
import re
import signal
import sqlite3
import ssl
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request
import support as harness


class HTTP(harness.ToolchainCase):
    def launch(self, executable, auth, *, tls=False, budget=10000, timeout=5000, foreign=None, env=None, cors=()):
        args = [executable, '--auth', str(auth), '--database', str(self.root / 'app.sqlite'), '--port', '0',
                '--static', str(self.root / 'assets'), '--budget', str(budget), '--timeout-ms', str(timeout)]
        if tls:
            args += ['--cert', str(self.root / 'cert.pem'), '--key', str(self.root / 'key.pem')]
        if foreign is not None:
            args += ['--foreign', str(foreign)]
        for origin in cors:
            args += ['--cors-origin', origin]
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                   env=None if env is None else {**os.environ, **env})
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            line = lines.get(timeout=15)
            match = re.match(r'NEX server (https?)://127\.0\.0\.1:([0-9]+)', line)
            self.assertIsNotNone(match, line + (process.stderr.read() if process.poll() is not None else ''))
            self.base = '%s://127.0.0.1:%s' % match.groups()
            self.port = int(match.group(2))
            self.context = ssl.create_default_context(cafile=str(self.root / 'cert.pem')) if tls else None
            return process
        except BaseException:
            process.terminate(); process.communicate(timeout=10); raise

    def stop(self, process):
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=15)
        self.assertEqual(process.returncode, 0, stdout + stderr)
        self.assertNotIn('E_INTERNAL_LEAK', stderr)
        self.assertNotIn('libc++abi', stderr)

    def request(self, path, *, token=None, method='GET', body=None):
        headers = {}
        if token is not None:
            headers['Authorization'] = 'Bearer ' + token
        if body is not None:
            headers['Content-Type'] = 'application/json'
            body = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
        request = urllib.request.Request(self.base + path, data=body, headers=headers, method=method)
        try:
            response = urllib.request.urlopen(request, context=self.context, timeout=15)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            payload = response.read()
            return response.status, json.loads(payload), response.headers

    def test_explicit_cors_preflight_authentication_and_denied_mutations(self):
        self.source((harness.REPO/'examples/server/main.nex').read_text())
        auth=self.root/'private-auth.json';alice=self.cli('token','--user','alice','--auth',auth)['token']
        assets=self.root/'assets';assets.mkdir();(assets/'index.html').write_text('<h1>CORS</h1>')
        executable=self.cli('build','--target','server','--profile','release',timeout=180)['executable']
        process=self.launch(executable,auth,cors=('capacitor://localhost','https://localhost','https://client.test'))
        def raw(method='GET',headers=(),body=None):
            connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=3)
            connection.putrequest(method,'/api/tasks')
            for name,value in headers:connection.putheader(name,value)
            connection.endheaders(body)
            response=connection.getresponse();result=response.status,response.read(),response.headers
            connection.close();return result
        try:
            for origin in ('capacitor://localhost','https://localhost','https://client.test'):
                headers=[('Origin',origin),('Access-Control-Request-Method','POST'),('Access-Control-Request-Headers','authorization, Content-Type')]
                status,body,reply=raw('OPTIONS',headers)
                self.assertEqual((status,body),(204,b''));self.assertEqual(reply['Access-Control-Allow-Origin'],origin)
                self.assertIsNone(reply['Access-Control-Allow-Credentials']);self.assertIsNone(reply['X-Request-Id'])
                self.assertIn('Access-Control-Request-Headers',reply['Vary'])
                status,_,reply=raw(headers=[('Origin',origin)])
                self.assertEqual(status,401);self.assertEqual(reply['Access-Control-Allow-Origin'],origin)
                self.assertEqual(reply['WWW-Authenticate'],'Bearer')
                status,_,reply=raw(headers=[('Origin',origin),('Authorization','Bearer '+alice)])
                self.assertEqual(status,200);self.assertEqual(reply['Access-Control-Allow-Origin'],origin)
            for origin in ('https://evil.test','null','capacitor://evil','capacitor://localhost.evil','https://client.test/path','https://client.test:443'):
                payload=b'{"text":"must not commit"}'
                status,_,reply=raw('POST',[('Origin',origin),('Authorization','Bearer '+alice),('Content-Length',str(len(payload))),('Content-Type','application/json')],payload)
                self.assertEqual(status,403);self.assertIsNone(reply['Access-Control-Allow-Origin'])
            bad=[ [('Access-Control-Request-Method','POST')],
                  [('Origin','capacitor://localhost'),('Access-Control-Request-Method','TRACE')],
                  [('Origin','capacitor://localhost'),('Access-Control-Request-Method','POST'),('Access-Control-Request-Headers','X-Other')],
                  [('Origin','capacitor://localhost'),('Access-Control-Request-Method','POST'),('Content-Length','999999999')],
                  [('Origin','capacitor://localhost'),('Access-Control-Request-Method','POST'),('Access-Control-Request-Method','GET')],
                  [('Origin','capacitor://localhost'),('Origin','https://client.test'),('Access-Control-Request-Method','POST')] ]
            for headers in bad:
                self.assertIn(raw('OPTIONS',headers)[0],(400,403))
            self.assertEqual(raw('OPTIONS',[('Origin','capacitor://localhost')])[0],401)
            self.assertEqual(self.request('/api/tasks',token=alice)[1],[])
            # Same-origin browser POST remains usable when a remote allowlist is enabled.
            payload=b'{"text":"same origin"}'
            status,_,_=raw('POST',[('Origin',self.base),('Authorization','Bearer '+alice),('Content-Length',str(len(payload)))],payload)
            self.assertEqual(status,201)
            self.assertEqual(len(self.request('/api/tasks',token=alice)[1]),1)
        finally:self.stop(process)
        for origins in [('*',),('null',),('https://client.test/path',),('https://user@client.test',),
                        ('https://client.test','https://client.test'),tuple('https://client%d.test'%i for i in range(17))]:
            args=[executable,'--auth',str(auth),'--database',str(self.root/'app.sqlite'),'--port','0']
            for origin in origins:args+=['--cors-origin',origin]
            failed=subprocess.run(args,capture_output=True,text=True,timeout=5)
            self.assertNotEqual(failed.returncode,0);self.assertIn('CORS requires',failed.stderr)

    def test_native_http_api_authentication_persistence_and_fault_containment(self):
        original = (harness.REPO / 'examples/server/main.nex').read_text()
        injection = '''
  if request.path == "/api/trap" { store_put("probe", "uncommitted"); assert(false); }
  if request.path == "/api/loop" { store_put("probe", "uncommitted"); while true {} }
  if request.path == "/api/probe" { return http::json_response(200, encode_json(store_get("probe"))); }
'''
        self.source(original.replace('  let loaded: result<State> = load();', injection + '  let loaded: result<State> = load();'))
        auth = self.root / 'private-auth.json'
        alice = self.cli('token', '--user', 'alice', '--auth', auth)['token']
        bob = self.cli('token', '--user', 'bob', '--auth', auth)['token']
        data = json.loads(auth.read_text())
        self.assertNotIn(alice, auth.read_text()); self.assertNotIn(bob, auth.read_text())
        self.assertEqual(data['tokens'][0]['sha256'], hashlib.sha256(alice.encode()).hexdigest())
        self.assertEqual(auth.stat().st_mode & 0o777, 0o600)
        assets = self.root / 'assets'; assets.mkdir(); (assets / 'index.html').write_text('<h1>Static client</h1>')
        (assets / 'outside-link.txt').symlink_to(auth)
        built = self.cli('build', '--target', 'server', '--profile', 'release', timeout=180)
        self.assertEqual(built['kind'], 'http_server')
        notices = Path(built['notices']).read_text()
        for license_file in ('JSON-LICENSE.MIT', 'HTTPLIB-LICENSE'):
            self.assertIn((harness.REPO / 'runtime/third_party' / license_file).read_text(), notices)
        process = self.launch(built['executable'], auth)
        try:
            self.assertEqual(self.request('/health')[0], 200)
            self.assertEqual(self.request('/api/tasks')[0], 401)
            self.assertEqual(self.request('/api/tasks', token='invalid')[0], 401)
            status, identity, headers = self.request('/api/me', token=alice)
            self.assertEqual((status, identity['user']), (200, 'alice'))
            self.assertEqual(headers['X-Request-Id'], identity['request_id'])
            self.assertEqual(self.request('/api/tasks', token=alice)[1], [])
            status, task, _ = self.request('/api/tasks', token=alice, method='POST', body={'text': 'Я🦊 saved'})
            self.assertEqual(status, 201); self.assertEqual(task['id'], '1')
            self.assertEqual(self.request('/api/tasks', token=bob)[1], [])
            self.assertEqual(self.request('/api/tasks', token=bob, method='PUT', body={**task, 'complete': True})[0], 404)
            for body in [b'{"text":"x","text":"y"}', {'text': 'x', 'user': 'bob'}, {'text': ''}, {'text': 3}, {'text': '\ud800'}]:
                payload = json.dumps(body).encode() if isinstance(body, dict) else body
                self.assertEqual(self.request('/api/tasks', token=alice, method='POST', body=payload)[0], 400)
            self.assertEqual(self.request('/api/tasks', token=alice, method='PUT', body={**task, 'text': 'updated', 'complete': True})[0], 200)
            self.assertTrue(self.request('/api/tasks', token=alice)[1][0]['complete'])
            def create(i):
                status, created, _ = self.request('/api/tasks', token=alice, method='POST', body={'text': 'parallel ' + str(i)})
                return status, created
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                created = list(executor.map(create, range(24)))
            self.assertTrue(all(status == 201 for status, _ in created))
            self.assertEqual(len({item['id'] for _, item in created}), 24)
            self.assertEqual(len(self.request('/api/tasks', token=alice)[1]), 25)
            self.assertEqual(self.request('/api/trap', token=alice, method='POST', body={})[0], 500)
            self.assertEqual(self.request('/api/loop', token=alice, method='POST', body={})[0], 429)
            self.assertEqual(self.request('/api/probe', token=alice)[1]['error']['code'], 'NOT_FOUND')
            self.assertEqual(self.request('/health')[0], 200)
            self.assertEqual(self.request('/api/tasks', token=alice, method='DELETE', body={'id': '1'})[0], 200)
            self.assertEqual(len(self.request('/api/tasks', token=alice)[1]), 24)
            # Authentication runs before body buffering and does not drain an oversized rejected upload.
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
            connection.request('POST', '/api/tasks', headers={'Content-Length': '999999999'})
            self.assertEqual(connection.getresponse().status, 401); connection.close()
            connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
            connection.request('POST', '/api/tasks', headers={'Content-Length': '1048577', 'Authorization': 'Bearer ' + alice})
            self.assertEqual(connection.getresponse().status, 413); connection.close()
            with urllib.request.urlopen(self.base + '/active') as response:
                self.assertIn(b'Static client', response.read())
            with self.assertRaises(urllib.error.HTTPError) as missing:
                urllib.request.urlopen(self.base + '/outside-link.txt')
            self.assertEqual(missing.exception.code, 404)
        finally:
            self.stop(process)
        process = self.launch(built['executable'], auth, budget=100000000, timeout=5000)
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=3)
        connection.request('POST', '/api/loop', body=b'{}', headers={'Authorization': 'Bearer ' + alice})
        try:
            active = False
            for _ in range(100):
                with sqlite3.connect(self.root / 'app.sqlite', timeout=0) as observer:
                    try:
                        observer.execute('BEGIN IMMEDIATE'); observer.rollback()
                    except sqlite3.OperationalError as error:
                        self.assertIn('locked', str(error)); active = True; break
                self.assertIsNone(process.poll()); time.sleep(0.01)
            self.assertTrue(active, 'native request never acquired its transaction')
        finally:
            self.stop(process); connection.close()
        with sqlite3.connect(self.root / 'app.sqlite') as observer:
            self.assertEqual(observer.execute("SELECT count(*) FROM nex_kv WHERE owner='alice' AND key='probe'").fetchone()[0], 0)
        # The executable starts without NEX/LLVM/model services and keeps its committed data.
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost',
                        '-keyout', str(self.root / 'key.pem'), '-out', str(self.root / 'cert.pem')], check=True, capture_output=True)
        process = self.launch(built['executable'], auth, tls=True)
        try:
            self.assertEqual(len(self.request('/api/tasks', token=alice)[1]), 24)
            self.assertEqual(self.request('/api/tasks', token=bob)[1], [])
            self.assertEqual(self.request('/api/me', token=bob)[1]['user'], 'bob')
        finally:
            self.stop(process)
        process = self.launch(built['executable'], auth, budget=100000000, timeout=30)
        try:
            self.assertEqual(self.request('/api/loop', token=alice, method='POST', body={})[0], 504)
            self.assertEqual(self.request('/api/probe', token=alice)[1]['error']['code'], 'NOT_FOUND')
        finally:
            self.stop(process)

    def test_http_contract_and_token_file_validation(self):
        self.source('module invalid; server fn handle() -> unit {}')
        self.assertEqual(self.cli('build', '--target', 'server', ok=False)['code'], 'E_HTTP_SIGNATURE')
        auth = self.root / 'auth.json'
        auth.write_text('{"schema":"nex.auth/1","tokens":[],"tokens":[]}')
        self.assertEqual(self.cli('token', '--user', 'alice', '--auth', auth, ok=False)['code'], 'E_AUTH')
        self.assertEqual(auth.read_text(), '{"schema":"nex.auth/1","tokens":[],"tokens":[]}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
