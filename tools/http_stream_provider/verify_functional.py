#!/usr/bin/env python3
"""Ordinary large-response and explicit-close checks through actual NEX code."""
import argparse
import http.server
import hashlib
import json
import re
import os
from pathlib import Path
import shutil
import selectors
import queue
import subprocess
import sys
import threading
import time
import tempfile


def source_for_selected_sdk(program, sdk):
    """Author fresh025/026 scope/join fixtures; retain matching024 fixture effects."""
    language = json.loads((sdk/'share/nex/llm/language-pack.json').read_text())['language_version']
    if language not in ('0.25','0.26','0.27', '0.28'):
        return program
    program = re.sub(r'(fn\([^)]*:task_scope\)->[^{}]*!)\{(task,ffi(?:,fs)?)\}',
                     r'\1{\2,throw}', program)
    for effects in ['task,ffi,fs,io', 'task,ffi,io']:
        program = program.replace('server fn main()->unit !{'+effects+'}',
                                  'server fn main()->unit !{'+effects+',throw}')
    return program


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path)
    parser.add_argument('--compiler', type=Path)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--http-prefix', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--case', action='append')
    parser.add_argument('--transport', choices=['http1', 'https1', 'https2'], default='http1')
    parser.add_argument('--package-notices',type=Path)
    parser.add_argument('--package', action='store_true', help='Also execute a relocated standalone download application')
    args = parser.parse_args()
    if not args.sdk and not (args.compiler and args.resources):
        parser.error('use --sdk or --compiler and --resources')
    temporary = args.output is None
    out = Path(tempfile.mkdtemp(prefix='nex-http-stream-')) if temporary else args.output.absolute()
    if not temporary:
        out.mkdir(parents=True)
    if args.sdk:
        sdk = args.sdk.resolve(strict=True)
    else:
        sdk = out / 'source-projection'
        (sdk / 'bin').mkdir(parents=True)
        (sdk / 'share').mkdir()
        shutil.copy2(args.compiler.resolve(strict=True), sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'))
        (sdk / 'share/nex').symlink_to(args.resources.resolve(strict=True), target_is_directory=True)
    shutil.copy2(__file__, out / 'verify-input.py')
    started = time.monotonic()
    report = {'schema': 'nex.http-stream-functional/1', 'ok': False, 'commands': [], 'cases': [],
              'ordinary_functional_checks_only': True, 'HTTP2_HTTPS_streaming_executed': False,
              'transport': args.transport,
              'full_objective_complete': False}
    server = None
    node = None
    node_log = None
    env = {**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'NEX_RESOURCE_DIR': str(sdk / 'share/nex')}
    env.pop('NEX_FOREIGN_CONFIG', None)
    files = out / 'files'
    files.mkdir()
    env.update(NEX_FILES_ROOT=str(files), NEX_FILES_WRITE='1')
    release = out / 'peer.release'

    def save():
        report['seconds'] = round(time.monotonic() - started, 3)
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(label, argv, cwd=None, run_env=None):
        row = {'label': label, 'argv': list(map(str, argv)), 'state': 'running'}
        report['commands'].append(row)
        report['state'] = label
        save()
        selected_env = env if run_env is None else run_env
        if label.startswith('concurrent-reads-'):
            with (out / (label + '.stdout')).open('w') as stdout, (out / (label + '.stderr')).open('w') as stderr:
                child = subprocess.Popen(row['argv'], cwd=cwd or out, env=selected_env, stdout=stdout, stderr=stderr)
                try:
                    deadline = time.monotonic() + 240
                    observed = False
                    while child.poll() is None:
                        if 'NEX_HTTP_STREAM_READ_ACTIVE {"current":2}' in (out / (label + '.stderr')).read_text():
                            release.write_text('two provider calls are active\n')
                            observed = True
                        if time.monotonic() >= deadline:
                            raise subprocess.TimeoutExpired(row['argv'], 240)
                        time.sleep(.005)
                    result = subprocess.CompletedProcess(row['argv'], child.wait(),
                        (out / (label + '.stdout')).read_text(), (out / (label + '.stderr')).read_text())
                    if result.returncode == 0:
                        assert observed, 'two simultaneous provider calls were not observed'
                finally:
                    if child.poll() is None:
                        child.kill()
                        child.wait(timeout=10)
        else:
            result = subprocess.run(row['argv'], cwd=cwd or out, env=selected_env, capture_output=True, text=True, timeout=240)
            (out / (label + '.stdout')).write_text(result.stdout)
            (out / (label + '.stderr')).write_text(result.stderr)
        row.update(exit_code=result.returncode, state='passed' if result.returncode == 0 else 'failed')
        save()
        assert result.returncode == 0, (label, result.stdout[-3500:], result.stderr[-2000:])
        return result

    try:
        amount = 2 * 1024 * 1024 + 17
        payload = bytes(range(256)) * 64

        class Server(http.server.ThreadingHTTPServer):
            daemon_threads = True

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def handle(self):
                try:
                    super().handle()
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-Length', str(amount))
                self.end_headers()
                self.wfile.flush()
                if self.path == '/concurrent':
                    deadline = time.monotonic() + 35
                    while not release.exists():
                        if time.monotonic() >= deadline:
                            return
                        time.sleep(.005)
                sent = 0
                try:
                    while sent < amount:
                        part = payload[:min(len(payload), amount - sent)]
                        self.wfile.write(part)
                        sent += len(part)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        scheme = 'http'
        protocol = '1.1'
        ca = None
        if args.transport == 'http1':
            server = Server(('127.0.0.1', 0), Handler)
            threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .02}, daemon=True).start()
            port = server.server_address[1]
        else:
            scheme = 'https'
            protocol = '2' if args.transport == 'https2' else '1.1'
            doctor = json.loads(run('doctor', [sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'), 'doctor', '--json']).stdout)
            openssl = Path(doctor['native_openssl_crypto']).resolve().parent.parent / 'bin' / ('openssl.exe' if os.name=='nt' else 'openssl')
            if not openssl.is_file():
                openssl = shutil.which('openssl')
            assert openssl, 'OpenSSL certificate tool is required'
            certificate = out / 'certificate'
            certificate.mkdir()
            ca = certificate / 'peer.pem'
            key = certificate / 'peer.key'
            run('certificate', [openssl, 'req', '-x509', '-newkey', 'rsa:2048', '-noenc',
                '-subj', '/CN=NEX stream loopback peer', '-keyout', key, '-out', ca,
                '-days', '2', '-addext', 'subjectAltName=IP:127.0.0.1',
                '-addext', 'basicConstraints=critical,CA:TRUE'])
            key.chmod(0o600)
            node_executable = shutil.which('node')
            assert node_executable, 'Node with built-in HTTP2 is required'
            fixture = Path(__file__).parent / 'tls_fixture.js'
            shutil.copy2(fixture, out / 'tls-fixture-input.js')
            node_log = (out / 'tls-peer.stderr').open('w')
            node = subprocess.Popen([node_executable, str(fixture), str(key), str(ca), str(out / 'peer-events.ndjson'), str(release)],
                                    stdout=subprocess.PIPE, stderr=node_log, text=True)
            if os.name=='nt':
                ready=queue.Queue(maxsize=1);threading.Thread(target=lambda:ready.put(node.stdout.readline()),daemon=True).start()
                try:line=ready.get(timeout=10)
                except queue.Empty:raise RuntimeError('owned TLS peer did not become ready') from None
                port=json.loads(line)['port']
            else:
                with selectors.DefaultSelector() as readiness:
                    readiness.register(node.stdout, selectors.EVENT_READ)
                    assert readiness.select(10), 'owned TLS peer did not become ready'
                    port = json.loads(node.stdout.readline())['port']
        target = out / 'targets.json'
        configuration = {'schema': 'nex.http-targets/1',
            'resolvers': [{'address': '127.0.0.1', 'port': 5353}],
            'authorities': [{'name': 'test', 'domain': '127.0.0.1', 'subdomains': False,
                             'schemes': [scheme], 'ports': [port], 'methods': ['GET']}]}
        if ca:
            configuration['ca_file'] = str(ca)
        target.write_text(json.dumps(configuration) + '\n')
        project = out / 'NEX stream project'
        run('prepare', [sys.executable, '-B', Path(__file__).parent / 'prepare.py', '--sdk', sdk,
            '--targets', target, '--http-prefix', args.http_prefix.resolve(strict=True),
            '--output', project, '--diagnostics'])
        prepared = json.loads((project / 'evidence/report.json').read_text())
        assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized']
        report.update(actual_compiler_toolchain=prepared['toolchain'], language=prepared['language'])
        context = json.loads(run('read-context', [sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'), 'context', '--symbol', 'std::http_stream::read', '--json'], project).stdout)
        assert context['symbol'] == 'std::http_stream::read' and context['language'] == prepared['language']
        prefix = (project / 'main.nex').read_text().split('server fn main()->unit', 1)[0]
        prefix += ('fn source_request()->hs::Request{return hs::Request("test","GET",'
                   + json.dumps(scheme + '://127.0.0.1:' + str(port) + '/data')
                   + ',[],utf8_bytes(""),16777216,30000,0,' + json.dumps(protocol) + ');}\n')
        common = ('let ctx:hs::Client=make_client();let response:hs::Response=unwrap(hs::open(ctx,source_request()));'
                  'assert(response.status==200);assert(response.protocol==' + json.dumps(protocol) + ');')
        cases = {
            'large-response': common + 'var total:i64=0;var done:bool=false;while !done{'
                'var maximum:i64=65536;if total==0{maximum=3;}'
                'let part:hs::Chunk=unwrap(hs::read(ctx,response.body,maximum));'
                'assert(len(part.data)<=maximum);if len(part.data)>0{'
                'assert(part.data[0]==total%256);assert(part.data[len(part.data)-1]==(total+len(part.data)-1)%256);}'
                'total=total+len(part.data);done=part.done;}'
                'assert(total==' + str(amount) + ');let eof:hs::Chunk=unwrap(hs::read(ctx,response.body,3));'
                'assert(eof.done&&len(eof.data)==0);let alias:hs::Body=response.body;assert(hs::close(alias));'
                'assert(!resource_is_open(response.body));print(total);',
            'explicit-close': common + 'let part:hs::Chunk=unwrap(hs::read(ctx,response.body,17));'
                'assert(len(part.data)==17);assert(part.data[0]==0&&part.data[16]==16);'
                'assert(hs::close(response.body));assert(!resource_is_open(response.body));print(len(part.data));',
            'download-file': 'let ctx:hs::Client=make_client();let total:i64=unwrap(hs::download(ctx,source_request(),"download-@MODE@.bin"));'
                'assert(total==' + str(amount) + ');print(total);',
            'task-handoff': common + 'let first:hs::Chunk=with_tasks(1,server fn(s:task_scope)->hs::Chunk !{task,ffi}{'
                'let child:task<result<hs::Chunk>>=task_spawn(s,server fn()->result<hs::Chunk> !{task,ffi}{return hs::read(ctx,response.body,17);});'
                'return unwrap(task_wait(child));});assert(len(first.data)==17&&first.data[0]==0&&first.data[16]==16);'
                'let second:hs::Chunk=unwrap(hs::read(ctx,response.body,3));assert(second.data==unwrap(bytes([17,18,19])));'
                'assert(hs::close(response.body));print(len(first.data));',
            'concurrent-reads': common + 'let parts:list<hs::Chunk>=with_tasks(2,server fn(s:task_scope)->list<hs::Chunk> !{task,ffi}{'
                'let go:channel<bool>=channel_new<bool>(s,0);'
                'let a:task<result<hs::Chunk>>=task_spawn(s,server fn()->result<hs::Chunk> !{task,ffi}{assert(unwrap(task_recv(go)));return hs::read(ctx,response.body,17);});'
                'let b:task<result<hs::Chunk>>=task_spawn(s,server fn()->result<hs::Chunk> !{task,ffi}{assert(unwrap(task_recv(go)));return hs::read(ctx,response.body,31);});'
                'assert(task_send(go,true));assert(task_send(go,true));return [unwrap(task_wait(a)),unwrap(task_wait(b))];});'
                'assert(len(parts[0].data)>0&&len(parts[0].data)<=17);assert(len(parts[1].data)>0&&len(parts[1].data)<=31);'
                'let observation:list<i64>=statistics_raw();assert(len(observation)>=14&&observation[12]==0&&observation[13]==2);'
                'var first:i64=0;if parts[1].data[0]==0{first=1;}let ordered:list<hs::Chunk>=[parts[first],parts[1-first]];'
                'var total:i64=0;var item:i64=0;while item<2{var index:i64=0;while index<len(ordered[item].data){'
                'assert(ordered[item].data[index]==total%256);total=total+1;index=index+1;}item=item+1;}'
                'var done:bool=false;while !done{let part:hs::Chunk=unwrap(hs::read(ctx,response.body,65536));'
                'if len(part.data)>0{assert(part.data[0]==total%256);assert(part.data[len(part.data)-1]==(total+len(part.data)-1)%256);}'
                'total=total+len(part.data);done=part.done;}assert(total==' + str(amount) + ');assert(hs::close(response.body));print(total);'
        }
        if args.case:
            assert set(args.case) <= set(cases), 'unknown functional case'
            cases = {name: body for name, body in cases.items() if name in args.case}
        for name, body in cases.items():
            program = source_for_selected_sdk(prefix + 'server fn main()->unit !{task,ffi,fs,io}{' + body + '}\n', sdk)
            if name == 'concurrent-reads':
                program = program.replace('/data"', '/concurrent"')
            (out / (name + '.nex')).write_text(program)
            (project / 'main.nex').write_text(program)
            for mode in ['eval', 'debug', 'release']:
                if name == 'concurrent-reads':
                    release.unlink(missing_ok=True)
                (project / 'main.nex').write_text(program.replace('@MODE@', mode))
                (out / (name + '-' + mode + '.nex')).write_text(program.replace('@MODE@', mode))
                argv = [sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'), 'eval' if mode == 'eval' else 'run', '--foreign', project / 'foreign.json',
                        '--task-workers', '2' if name == 'concurrent-reads' else '1', '--task-steps', '50000000', '--task-timeout-ms', '30000', '--json']
                if mode != 'eval':
                    argv += ['--profile', mode]
                if name == 'concurrent-reads' and mode != 'eval':
                    built = json.loads(run('build-' + name + '-' + mode,
                        [sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'), 'build', '--profile', mode, '--output', out / ('concurrent-' + mode),
                         '--task-workers', '2', '--task-steps', '50000000', '--task-timeout-ms', '30000', '--json'], project).stdout)
                    executed = run(name + '-' + mode, [built['executable'], '--nex-foreign', project / 'foreign.json'], project)
                    result = {'ok': True, 'stdout': executed.stdout}
                else:
                    result = json.loads(run(name + '-' + mode, argv, project).stdout)
                assert result['ok'] and result['stdout'] == str(17 if name in ('explicit-close', 'task-handoff') else amount) + '\n'
                if name == 'download-file':
                    assert (files / ('download-' + mode + '.bin')).read_bytes() == payload * (amount // len(payload)) + payload[:amount % len(payload)]
                if mode == 'eval':
                    assert result['foreign_resource_bytes_after_scope'] == 0
                report['cases'].append({'name': name, 'mode': mode, 'passed': True})
                if name == 'concurrent-reads':
                    report['cases'][-1]['two_simultaneous_provider_calls_observed'] = True
                    report['cases'][-1]['native_executable_launched_directly'] = mode != 'eval'
                save()
        if args.package:
            program = source_for_selected_sdk(prefix + 'server fn main()->unit !{task,ffi,fs,io}{', sdk)
            program += 'let total:i64=unwrap(hs::download(make_client(),source_request(),"download-package.bin"));'
            program += 'assert(total==' + str(amount) + ');print(total);}\n'
            (project / 'main.nex').write_text(program)
            (out / 'package-program.nex').write_text(program)
            shutil.copytree(project / 'evidence', out / 'prepared-package-evidence')
            notice_names = ['NOTICE', 'SOURCE.json', 'curl-LICENSE.txt', 'nghttp2-LICENSE.txt', 'c-ares-LICENSE.txt']
            components = [{'name': 'nex-http-stream-provider', 'version': prepared['toolchain'],
                'url': 'https://github.com/sae-ru/NEX', 'roots': [str(project / 'bundle')],
                'license_files': [str(project / 'bundle' / name) for name in notice_names]}]
            if args.package_notices:
                external=args.package_notices.resolve(strict=True);selected=json.loads(external.read_text());assert selected['schema']=='nex.sdk-notices/1'
                for row in selected['components']:
                    item=dict(row)
                    for field in ('roots','license_files'):item[field]=[str((external.parent/p).resolve(strict=True)) for p in row[field]]
                    components.append(item)
            elif sys.platform == 'darwin' and not (sdk / 'share/nex/sdk-bundle.json').is_file():
                doctor = json.loads(run('package-doctor', [sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'), 'doctor', '--json']).stdout)
                crypto = Path(doctor['native_openssl_crypto']).resolve(strict=True)
                license_path = crypto.parent.parent / 'LICENSE.txt'
                assert license_path.is_file(), 'selected OpenSSL needs its complete license'
                components.append({'name': 'openssl', 'version': crypto.parent.parent.name,
                    'url': 'https://www.openssl.org/', 'roots': [str(crypto.parent)],
                    'license_files': [str(license_path)]})
            notices = out / 'package-notices.json'
            notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': components}, indent=2) + '\n')
            package = out / 'package'
            argv = [sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'), 'package', '--foreign', project / 'foreign.json',
                    '--notices', notices, '--directory', package, '--json']
            if sys.platform.startswith('linux'):
                argv += ['--dpkg-notices']
            run('package', argv, project)
            application = json.loads((package / 'application.json').read_text())
            assert application['execution_verified'] is False
            moved = out / 'moved package % 🧠'
            package.rename(moved)
            shutil.rmtree(project)
            if ca:
                ca.unlink()
            standalone={'PATH': '/usr/bin:/bin', 'NEX_FILES_ROOT': str(files), 'NEX_FILES_WRITE': '1'}
            if os.name=='nt':
                standalone.update({key:os.environ[key] for key in ('SystemRoot','WINDIR','TEMP','TMP','USERPROFILE') if key in os.environ});standalone['PATH']=str(Path(os.environ['SystemRoot'])/'System32')
            independent = run('moved-package-download', [moved / 'bin' / ('app.exe' if os.name=='nt' else 'app')], files,standalone)
            assert independent.stdout == str(amount) + '\n'
            assert (files / 'download-package.bin').read_bytes() == payload * (amount // len(payload)) + payload[:amount % len(payload)]
            for name in ['curl-LICENSE.txt', 'nghttp2-LICENSE.txt', 'c-ares-LICENSE.txt']:
                originals = out / 'prepared-package-evidence/inputs/licenses' / name
                copies = list(moved.rglob(name))
                assert copies and all(path.read_bytes() == originals.read_bytes() for path in copies)
            (out / 'moved-inventory.json').write_text(json.dumps({path.relative_to(moved).as_posix():
                {'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                for path in moved.rglob('*') if path.is_file()}, indent=2) + '\n')
            report.update(relocated_package_download_passed=True, original_project_deleted=True,
                          original_CA_deleted=ca is not None, packaged_download_bytes=amount,
                          static_dependency_licenses_preserved=True)
        if node:
            events = [json.loads(line) for line in (out / 'peer-events.ndjson').read_text().splitlines()]
            assert len(events) == len(report['cases']) + int(args.package)
            assert all(event['protocol'] == ('2.0' if protocol == '2' else '1.1') for event in events), events
            report['peer_observed_protocol'] = events[0]['protocol']
        report.update(ok=True, state='passed', case_count=len(report['cases']), NEX_source_executed=True,
                      large_response_bytes=amount, HTTP2_HTTPS_streaming_executed=args.transport != 'http1')
    except BaseException as error:
        report.update(state='failed', error=repr(error))
        raise
    finally:
        if server:
            server.shutdown()
            server.server_close()
        if node:
            node.terminate()
            node.wait(timeout=5)
        if node_log:
            node_log.close()
        save()
    print(json.dumps({key: report.get(key) for key in ('ok', 'state', 'error', 'case_count', 'seconds')}))
    if temporary and report['ok']:
        shutil.rmtree(out)


if __name__ == '__main__':
    main()
