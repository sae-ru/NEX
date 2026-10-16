"""Opt-in real compiled client/native API checks in three installed browsers."""
import argparse
import json
import http.client
import http.server
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import threading

parser = argparse.ArgumentParser()
parser.add_argument('compiler', type=Path)
parser.add_argument('project', type=Path, help='built examples/fullstack/client.nex web project')
parser.add_argument('--browsers-path', type=Path)
parser.add_argument('--api-contract', action='store_true', help='test the generated endpoint server and typed client')
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
compiler, project = args.compiler.resolve(), args.project.resolve()
environment = dict(os.environ)
if args.browsers_path:
    environment['PLAYWRIGHT_BROWSERS_PATH'] = str(args.browsers_path.resolve())
shutil.copyfile(repo / 'tests/fullstack-browser.spec.js', project / 'tests/fullstack-browser.spec.js')
with tempfile.TemporaryDirectory(prefix='nex-browser-api-') as temporary:
    root = Path(temporary)
    def cli(*arguments):
        process = subprocess.run([str(compiler), *map(str, arguments), '--json'], cwd=root, capture_output=True, text=True, timeout=180)
        assert process.returncode == 0, process.stdout + process.stderr
        return json.loads(process.stdout)
    shutil.copytree(repo / ('examples/api' if args.api_contract else 'examples/fullstack'), root / 'source', ignore=shutil.ignore_patterns('generated'))
    entry=root / 'source/server.nex'
    if args.api_contract:
        generated=cli('api',root/'source/service.nex','--directory',root/'generated')
        entry=Path(generated['server_entry'])
        environment['NEX_TEST_TYPED_API']='1'
    built = cli('build', entry, '--target', 'server', '--profile', 'release')
    auth, database = root / 'auth.json', root / 'tasks.sqlite'
    tokens = {engine: {who: cli('token', '--user', engine + '-' + who, '--auth', auth)['token']
                       for who in ('alice', 'bob')} for engine in ('chromium', 'firefox', 'webkit')}
    for asset in (project / 'dist').rglob('*'):
        if asset.is_file():
            data = asset.read_bytes()
            assert b'SERVER_ONLY_FULLSTACK_SENTINEL' not in data
            assert b'SERVER_ONLY_TYPED_API_SENTINEL' not in data
            assert all(token.encode() not in data for roles in tokens.values() for token in roles.values())
    environment['NEX_TEST_TOKENS'] = json.dumps(tokens)
    config = project / 'playwright.fullstack.config.js'
    class Proxy(http.server.BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'
        def log_message(self, *arguments):
            pass
        def forward(self):
            if self.path == '/api/redirect':
                self.send_response(302); self.send_header('Location', '/redirect-target')
                self.send_header('Content-Length', '0'); self.end_headers(); return
            if self.path == '/redirect-target':
                self.server.redirect_followed += 1
                self.send_response(200); self.send_header('Content-Length', '0'); self.end_headers(); return
            connection = http.client.HTTPConnection('127.0.0.1', self.server.backend_port, timeout=15)
            try:
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                headers = {name: value for name, value in self.headers.items() if name.lower() not in ('host', 'connection')}
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse(); data = response.read()
                self.send_response(response.status)
                for name, value in response.getheaders():
                    if name.lower() not in ('content-length', 'transfer-encoding', 'connection'):
                        self.send_header(name, value)
                self.send_header('Content-Length', str(len(data))); self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                connection.close()
        do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = forward
    proxy = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
    proxy.daemon_threads = True; proxy.redirect_followed = 0
    proxy_thread = threading.Thread(target=proxy.serve_forever, daemon=True)
    proxy_thread.start()
    def launch():
        process = subprocess.Popen([built['executable'], '--auth', str(auth), '--database', str(database), '--static', str(project / 'dist'), '--port', '0'],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        lines = queue.Queue()
        threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
        try:
            match = re.match(r'NEX server (http://127\.0\.0\.1:\d+)', lines.get(timeout=15))
            assert match, 'server did not report its address'
            proxy.backend_port = int(match.group(1).rsplit(':', 1)[1])
            config.write_text("import { defineConfig, devices } from '@playwright/test';\nexport default defineConfig({ testDir: './tests', testMatch: 'fullstack-browser.spec.js', workers: 3, fullyParallel: false, timeout: 30000, use: { baseURL: " + json.dumps('http://127.0.0.1:' + str(proxy.server_port)) + ", trace: 'off' }, projects: [{name:'chromium',use:{...devices['Desktop Chrome']}},{name:'firefox',use:{...devices['Desktop Firefox']}},{name:'webkit',use:{...devices['Desktop Safari']}}] });\n")
            return process
        except BaseException:
            process.terminate(); process.communicate(timeout=10); raise
    def stop(process):
        output, errors = process.communicate(timeout=15) if process.poll() is not None else terminate(process)
        assert process.returncode == 0, output + errors
        assert 'E_INTERNAL_LEAK' not in errors
    def terminate(process):
        process.send_signal(signal.SIGTERM)
        return process.communicate(timeout=15)
    try:
        for phase, selection in (('initial', ['--grep-invert', 'survives native server restart']), ('restart', ['--grep', 'survives native server restart'])):
            server = launch()
            try:
                subprocess.run([str(project / 'node_modules/.bin/playwright'), 'test', '--config', str(config), *selection],
                               cwd=project, env={**environment, 'NEX_TEST_PHASE': phase}, check=True, timeout=150)
            finally:
                stop(server)
        assert proxy.redirect_followed == 0, 'browser followed a forbidden redirect'
    finally:
        proxy.shutdown(); proxy.server_close(); proxy_thread.join(timeout=5)
print('Compiled full-stack browser/API tests passed with server restart and clean shutdown.')
