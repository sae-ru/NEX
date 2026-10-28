#!/usr/bin/env python3
"""Opt-in Q2: one API/browser fixture, a 2000-to-64 scalar edit, durable data."""
import argparse
import http.client
import http.server
import json
from pathlib import Path
import shutil
import threading
import traceback
import urllib.error
import urllib.request

from acceptance_support import Evidence, sha


TRANSACTIONS = '''
endpoint quality_fail("POST", "/api/quality-fail") = quality_fail_write;
endpoint quality_probe("GET", "/api/quality-probe") = quality_probe_write;
server fn quality_fail_write(context:api::Context,trap:bool)->result<bool>!{db}{
 store_put("quality-probe","uncommitted");if trap{assert(false);}
 return err("DENIED","Rejected");
}
server fn quality_probe_write(context:api::Context)->result<str>!{db}{
 return store_get("quality-probe");
}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browsers-path', type=Path)
    args = parser.parse_args()
    run = Evidence(args.compiler, args.resources, args.output, 'nex.quality-server-web-edit/1')
    run.report.update(runner_sha256=sha(Path(__file__)),
        scope='One fixture edit on this host. Real HTTP and three browser engines; '
              'no task UI adapter, general platform or model-cost claim.')
    try:
        actual = run.cli('describe', run.output, 'describe', '--field', 'version')
        assert actual['value'] == '0.21', actual
        run.report.update(language=actual['value'], toolchain=actual['toolchain'],
                          compiler_build=actual['compiler_build'])
        fixtures = {}
        for stage, maximum in [('before', 2000), ('after', 64)]:
            fixture = run.output / stage
            fixture.mkdir()
            for name in ('model.nex', 'service.nex', 'client.nex'):
                text = (run.resources / 'examples/api' / name).read_text()
                if name == 'service.nex':
                    text += TRANSACTIONS
                if stage == 'after' and name in ('service.nex', 'client.nex'):
                    assert text.count('2000') == (4 if name == 'service.nex' else 3)
                    text = text.replace('2000', '64')
                (fixture / name).write_text(text)
            (fixture / 'nex.json').write_text(json.dumps({
                'schema': 'nex.project/1', 'language': '0.21', 'entry': 'service.nex'}) + '\n')
            fixtures[stage] = {'path': str(fixture), 'maximum_unicode_scalars': maximum,
                'sources': {p.name: sha(p) for p in sorted(fixture.glob('*.nex'))}}
        assert fixtures['before']['sources']['model.nex'] == fixtures['after']['sources']['model.nex']
        assert [name for name in fixtures['before']['sources'] if
                fixtures['before']['sources'][name] != fixtures['after']['sources'][name]] == [
                    'client.nex', 'service.nex']
        run.report['fixtures'] = fixtures
        auth, database = run.output / 'auth.json', run.output / 'data.sqlite'
        tokens = {name: run.cli('token-' + name, run.output, 'token', '--user', name,
                               '--auth', auth)['token'] for name in
                  ['api-alice', 'api-bob'] + [engine + '-' + who for engine in
                   ('chromium', 'firefox', 'webkit') for who in ('alice', 'bob')]}
        spec = Path(__file__).with_name('server_web_edit.spec.mjs')
        run.report['browser_spec_sha256'] = sha(spec)
        browser_tokens = {engine: {who: tokens[engine + '-' + who] for who in ('alice', 'bob')}
                          for engine in ('chromium', 'firefox', 'webkit')}

        def request(address, label, method='GET', path='/api/tasks', body=None, principal='api-alice'):
            data = body if isinstance(body, bytes) else None if body is None else json.dumps(body).encode()
            token = tokens.get(principal, principal)
            req = urllib.request.Request(address + path, method=method, data=data,
                headers={'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            try:
                response = urllib.request.urlopen(req, timeout=15)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                raw = response.read(1048577)
                assert len(raw) <= 1048576
                value = json.loads(raw)
                row = {'name': label, 'method': method, 'path': path, 'principal': principal,
                       'status': response.status, 'response': value}
                run.report['http'].append(row)
                run.save()
                return response.status, value

        seed = None
        for stage, maximum in [('before', 2000), ('after', 64)]:
            fixture = Path(fixtures[stage]['path'])
            generated = run.cli(stage + '-api', fixture, 'api', fixture / 'service.nex',
                                '--directory', fixture / 'generated')
            server = run.cli(stage + '-server-build', fixture, 'build', generated['server_entry'],
                             '--target', 'server', '--profile', 'release')
            web = run.cli(stage + '-web-build', fixture, 'build', fixture / 'client.nex',
                          '--target', 'web', '--profile', 'release')
            dist, webdir = Path(web['dist']), Path(web['directory'])
            assert (dist / 'index.html').is_file()
            for asset in dist.rglob('*'):
                if asset.is_file():
                    data = asset.read_bytes()
                    assert b'SERVER_ONLY_TYPED_API_SENTINEL' not in data
                    assert b'quality_fail_write' not in data
                    assert all(t.encode() not in data for t in tokens.values())
            run.report.setdefault('builds', {})[stage] = {
                'server': server, 'web': web, 'server_sha256': sha(server['executable']),
                'dist': {p.relative_to(dist).as_posix(): sha(p) for p in sorted(dist.rglob('*')) if p.is_file()}}
            destination = webdir / 'tests/quality-edit.spec.mjs'
            destination.parent.mkdir(exist_ok=True)
            shutil.copyfile(spec, destination)

            class Proxy(http.server.BaseHTTPRequestHandler):
                protocol_version = 'HTTP/1.1'

                def log_message(self, *ignored):
                    pass

                def forward(self):
                    if self.path == '/api/redirect':
                        self.send_response(302)
                        self.send_header('Location', '/redirect-target')
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    if self.path == '/redirect-target':
                        self.server.redirect_followed += 1
                        self.send_response(200)
                        self.send_header('Content-Length', '0')
                        self.end_headers()
                        return
                    connection = http.client.HTTPConnection('127.0.0.1', self.server.backend_port, timeout=15)
                    try:
                        body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                        headers = {k: v for k, v in self.headers.items() if k.lower() not in ('host', 'connection')}
                        connection.request(self.command, self.path, body=body, headers=headers)
                        response = connection.getresponse()
                        data = response.read(1048577)
                        assert len(data) <= 1048576
                        self.send_response(response.status)
                        for key, value in response.getheaders():
                            if key.lower() not in ('content-length', 'transfer-encoding', 'connection'):
                                self.send_header(key, value)
                        self.send_header('Content-Length', str(len(data)))
                        self.end_headers()
                        if self.command != 'HEAD':
                            self.wfile.write(data)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                    finally:
                        connection.close()

                do_GET = do_POST = do_PUT = do_DELETE = do_HEAD = do_OPTIONS = forward

            proxy = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Proxy)
            proxy.daemon_threads = True
            proxy.redirect_followed = 0
            thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            thread.start()
            config = webdir / 'playwright.quality.config.mjs'
            config.write_text("import {defineConfig,devices} from '@playwright/test';\n"
                "export default defineConfig({testDir:'./tests',testMatch:'quality-edit.spec.mjs',"
                "workers:3,fullyParallel:false,timeout:30000,reporter:[['json']],use:{baseURL:"
                + json.dumps('http://127.0.0.1:' + str(proxy.server_port)) +
                ",trace:'off'},projects:[{name:'chromium',use:{...devices['Desktop Chrome']}},"
                "{name:'firefox',use:{...devices['Desktop Firefox']}},"
                "{name:'webkit',use:{...devices['Desktop Safari']}}]});\n")
            browser_env = {'NEX_TEST_TYPED_API': '1', 'NEX_TEST_TOKENS': json.dumps(browser_tokens),
                           'NEX_QUALITY_TEXT_MAX': str(maximum)}
            if args.browsers_path:
                browser_env['PLAYWRIGHT_BROWSERS_PATH'] = str(args.browsers_path.resolve(strict=True))
            try:
                for phase in ('initial', 'restart'):
                    with run.server(stage + '-' + phase + '-server', server['executable'], auth, database, dist) as address:
                        proxy.backend_port = int(address.rsplit(':', 1)[1])
                        if phase == 'initial':
                            if seed is None:
                                status, created = request(address, 'seed', 'POST', body={'text': 'durable seed 🦊'})
                                assert status == 201
                                seed = created['ok']
                            assert request(address, stage + '-seed-preserved')[1] == {'ok': [seed]}
                            assert request(address, stage + '-isolation', principal='api-bob')[1] == {'ok': []}
                            assert request(address, stage + '-bad-token', principal='invalid')[0] == 401
                            for index, bad in enumerate([{'text': 'x', 'user': 'api-bob'},
                                    b'{"text":"x","text":"y"}', b'{"text":"\xc0\x80"}']):
                                assert request(address, stage + '-strict-' + str(index), 'POST', body=bad)[0] == 400
                            status, boundary = request(address, stage + '-scalar-boundary', 'POST', body={'text': '🦊' * maximum})
                            assert status == 201
                            assert request(address, stage + '-scalar-overflow', 'POST', body={'text': '🦊' * (maximum + 1)})[0] == 422
                            assert request(address, stage + '-remove-boundary', 'DELETE', body={'id': boundary['ok']['id']})[0] == 200
                            for trap in (False, True):
                                assert request(address, stage + '-rollback-' + str(trap), 'POST',
                                    path='/api/quality-fail', body=trap)[0] == (500 if trap else 422)
                                status, probe = request(address, stage + '-probe-' + str(trap), path='/api/quality-probe')
                                assert status == 422 and probe['error']['code'] == 'NOT_FOUND'
                            assert request(address, stage + '-no-partial-write')[1] == {'ok': [seed]}
                        raw = run.command(stage + '-browser-' + phase,
                            [webdir / 'node_modules/.bin/playwright', 'test', '--config', config], webdir,
                            env={**browser_env, 'NEX_TEST_PHASE': phase}, timeout=180)
                        result = json.loads(raw)
                        assert result['stats']['unexpected'] == result['stats']['flaky'] == 0
                        assert result['stats']['expected'] == (12 if phase == 'initial' else 3)
                        if phase == 'restart':
                            assert request(address, stage + '-seed-after-restart')[1] == {'ok': [seed]}
                            # Browser scenarios seed their own principals. Remove only those
                            # records after the restart assertion, preserving the API seed.
                            for engine in browser_tokens:
                                principal = engine + '-alice'
                                _, listed = request(address, stage + '-browser-clean-' + engine, principal=principal)
                                for item in listed['ok']:
                                    assert request(address, stage + '-browser-delete-' + engine, 'DELETE',
                                        body={'id': item['id']}, principal=principal)[0] == 200
                assert proxy.redirect_followed == 0
            finally:
                proxy.shutdown()
                proxy.server_close()
                thread.join(timeout=5)
            assert sha(server['executable']) == run.report['builds'][stage]['server_sha256']
        run.guard()
        run.report.update(ok=True, state='passed', phase='complete',
                          seed=seed, edited_files=['client.nex', 'service.nex'],
                          browser_passes=30, browser_engines=['chromium', 'firefox', 'webkit'],
                          strict_inputs=True, transaction_rollback=True, durable_across_edit_and_restart=True,
                          reachable_client_only=True)
    except BaseException as error:
        run.report.update(state='failed', error=repr(error))
        traceback.print_exc()
    finally:
        run.save()
        print(json.dumps({key: run.report.get(key) for key in ('schema', 'ok', 'state', 'seconds', 'error')}))
    return 0 if run.report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
