#!/usr/bin/env python3
"""Execute checked HTTP clients through NEX AST and native debug/release tasks.

All DNS, HTTP and TLS peers are owned loopback fixtures. This is conformance,
not a throughput measurement or evidence about external network services.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

from fixtures import Fixtures, digest

ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


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
    parser.add_argument('--case', action='append', help='Run named cases; omit for the complete suite')
    args = parser.parse_args()
    temporary = args.output is None
    out = args.output.absolute() if args.output else Path(tempfile.mkdtemp(prefix='nex-http-source-'))
    if not temporary:
        out.mkdir(parents=True)
    report = {'schema': 'nex.http-source-conformance/1', 'ok': False, 'cases': [],
              'commands': [], 'full_objective_complete': False,
              'network_scope': 'owned loopback DNS/HTTP/HTTP2/TLS only',
              'source_HTTP_executed': False}
    report['complete_suite_selected'] = args.case is None
    started = time.monotonic()
    peer = None

    def save():
        report['seconds'] = round(time.monotonic() - started, 3)
        write(out / 'report.json', report)

    def run(label, argv, *, cwd=None, env=None, expected=0, parsed=True):
        argv = list(map(str, argv))
        row = {'label': label, 'argv': argv, 'state': 'running'}
        report['commands'].append(row)
        report['state'] = label
        save()
        result = subprocess.run(argv, cwd=cwd or out, env=env,
                                capture_output=True, text=True, timeout=240)
        (out / (label + '.stdout')).write_text(result.stdout)
        (out / (label + '.stderr')).write_text(result.stderr)
        row.update(exit_code=result.returncode,
                   state='passed' if result.returncode == expected else 'failed')
        save()
        assert result.returncode == expected, (label, result.stdout[-4000:], result.stderr[-2500:])
        return json.loads(result.stdout) if parsed else result

    try:
        for name in ('verify.py', 'fixtures.py', 'http2_fixture.js'):
            shutil.copy2(Path(__file__).parent / name, out / ('input-' + name))
        if args.sdk:
            sdk = args.sdk.resolve(strict=True)
        else:
            if not args.compiler or not args.resources:
                parser.error('use --sdk or --compiler and --resources')
            sdk = out / 'source-projection'
            (sdk / 'bin').mkdir(parents=True)
            (sdk / 'share').mkdir()
            shutil.copy2(args.compiler.resolve(strict=True), sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex'))
            (sdk / 'share/nex').symlink_to(args.resources.resolve(strict=True), target_is_directory=True)
        compiler = sdk / 'bin' / ('nex.exe' if os.name=='nt' else 'nex')
        resources = sdk / 'share/nex'
        env = {**os.environ, 'NEX_RESOURCE_DIR': str(resources), 'PYTHONDONTWRITEBYTECODE': '1',
               'NEX_TRACY': '0'}
        env.pop('NEX_FOREIGN_CONFIG', None)
        doctor = run('doctor', [compiler, 'doctor', '--json'], env=env)
        peer = Fixtures(out, doctor)
        env.update(NEX_FILES_ROOT=str(peer.files), NEX_FILES_WRITE='1',
                   http_proxy='http://127.0.0.1:9', https_proxy='http://127.0.0.1:9',
                   HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9',
                   ALL_PROXY='http://127.0.0.1:9', NO_PROXY='', no_proxy='',
                   SSLKEYLOGFILE=str(out / 'forbidden-ambient-keylog'))
        projects = {}
        for kind in ('normal', 'capacity', 'cross-origin'):
            config = peer.config(1 if kind == 'capacity' else 16)
            if kind == 'cross-origin':
                config['authorities'][0]['cross_origin_redirects'] = True
            target = out / (kind + '-targets.json')
            write(target, config)
            project = out / (kind + ' project % 🧠')
            run('prepare-' + kind, [sys.executable, '-B', ROOT / 'tools/http_provider/prepare.py',
                '--sdk', sdk, '--targets', target, '--http-prefix', args.http_prefix.resolve(strict=True),
                '--output', project, '--diagnostics'], env=env, parsed=False)
            prepared = json.loads((project / 'evidence/report.json').read_text())
            assert prepared['ok'] and not prepared['network_executed'] and not prepared['module_initialized']
            assert peer.dns.count() == 0 and not peer.events
            projects[kind] = (project, (project / 'main.nex').read_text().split('server fn main()->unit', 1)[0])
            if kind == 'normal':
                report.update(actual_compiler_toolchain=prepared['toolchain'], language=prepared['language'],
                              compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
                              provider_tools_from=str(ROOT), runtime_resources_from=str(resources),
                              provider_manifest_sha256=prepared['manifest_sha256'],
                              provider_module_sha256=prepared['module_sha256'])

        http = 'http://api.example.test:' + str(peer.http_port)
        https = 'https://api.example.test:' + str(peer.https_port)
        quoted = lambda value: json.dumps(value, ensure_ascii=False)

        def request(path='/ok', *, url=None, method='GET', authority='backend', timeout=1000,
                    body='utf8_bytes("")', reply=262144, redirects=0, protocol='auto', headers='[]'):
            return ('httpc::Request(' + ','.join([quoted(authority), quoted(method), quoted(url or http + path),
                    headers, body, str(reply), str(timeout), str(redirects), quoted(protocol)]) + ')')

        def response(expr, *, status=200, body='utf8_bytes("42")', protocol='1.1'):
            return ('let response:httpc::Response=unwrap(httpc::execute(make_client(),' + expr + '));'
                    'assert(response.status==' + str(status) + ');assert(response.body==' + body + ');'
                    'assert(response.protocol==' + quoted(protocol) + ');')

        def failure(expr, code):
            return 'assert(error_code(send_raw(' + expr + '))==' + quoted(code) + ');'

        cases = []

        def case(name, body, *, project='normal', fatal=None, silent=False, started_path=None):
            cases.append(dict(name=name, body=body, project=project, fatal=fatal,
                              silent=silent, started_path=started_path))

        case('HTTP-1.1', response(request()))
        case('HTTPS-HTTP2', response(request(url=https + '/ok'), protocol='2'))
        case('HTTPS-forced-1.1', response(request(url=https + '/ok', protocol='1.1')))
        binary = 'unwrap(bytes([0,255,128,208,175,240,159,167,160]))'
        case('binary-POST', response(request('/echo', method='POST', body=binary), body=binary))
        case('IPv4-literal', response(request(url='http://127.0.0.1:' + str(peer.http_port) + '/ok', authority='ip4')))
        case('IPv6-literal', response(request(url='http://[::1]:' + str(peer.http6_port) + '/ok', authority='ip6')))
        case('HEAD', response(request(method='HEAD'), body='utf8_bytes("")'))
        case('ordinary-404', response(request('/missing'), status=404) + 'assert(error_code(httpc::require_success(response))=="HTTP_STATUS");')
        case('invalid-UTF8', response(request('/invalid-UTF8'), body='unwrap(bytes([255,128,0]))') + 'assert(error_code(httpc::text(response))=="E_UTF8");')
        case('header-bytes', response(request('/header-bytes')) + 'var seen:bool=false;var i:i64=0;while i<len(response.headers){if response.headers[i].name=="x-bytes"{assert(response.headers[i].value==unwrap(bytes([255])));seen=true;}i=i+1;}assert(seen);')
        case('repeated-HTTP2-headers', response(request(url=https + '/ok'), protocol='2') + 'var count:i64=0;var i:i64=0;while i<len(response.headers){if response.headers[i].name=="set-cookie"{count=count+1;}i=i+1;}assert(count==2);')
        case('denied', ''.join(failure(expr, 'CAPABILITY') for expr in [
            request(authority='missing'), request(url='http://evil-example.test:' + str(peer.http_port) + '/ok'),
            request(url='http://api.example.test:9/ok'), request(method='DELETE')]), silent=True)
        case('invalid', ''.join(failure(expr, 'VALIDATION') for expr in [
            request(timeout=9223372036854775807), request(reply=0), request(method='CONNECT'),
            request(headers='[httpc::header("X-Value","bad\r\nInjected: value")]'.replace('\r', '\\r').replace('\n', '\\n')),
            request(headers='[httpc::header("Host","elsewhere.test")]')]), silent=True)
        case('reply-limit', failure(request('/many', reply=8), 'E_HTTP_LIMIT'))
        case('header-limit', failure(request('/too-many-headers'), 'E_HTTP_LIMIT'))
        case('redirect-disabled', response(request('/redirect'), status=302))
        case('redirect-follow', response(request('/redirect', redirects=1)))
        case('redirect-loop', failure(request('/loop', redirects=2), 'E_HTTP_REDIRECT'))
        case('redirect-cross-denied', failure(request('/cross', redirects=1), 'CAPABILITY'))
        credentials = '[httpc::header("Authorization","Bearer private-test"),httpc::header("Cookie","private=1")]'
        case('redirect-credentials-stripped', response(request('/cross', redirects=1, headers=credentials),
             body='utf8_bytes(' + quoted('{"authorization": null, "cookie": null}') + ')'), project='cross-origin')
        case('hostname-rejected', failure(request(url='https://other.example.test:' + str(peer.https_port) + '/ok'), 'E_TLS'))
        case('TLS-own-timeout', failure(request(url='https://api.example.test:' + str(peer.stall_port) + '/', timeout=60), 'E_HTTP_TIMEOUT') + response(request()))
        case('own-timeout', failure(request('/held-own-@LABEL@', timeout=60), 'E_HTTP_TIMEOUT') +
             'assert(statistics_raw()[2]==0);assert(statistics_raw()[6]==0);' + response(request()))
        for transport, base in [('HTTP', http), ('HTTP2', https)]:
            path = '/held-progress-' + transport + '-@LABEL@'
            child = 'let child:task<result<httpc::Response>>=task_spawn(s,server fn()->result<httpc::Response> !{task,ffi}{return send_raw(' + request(url=base + path, timeout=5000) + ');});'
            gate = 'while !is_ok(file_read_text("@GATE@.ready")){task_yield();}'
            case('progress-' + transport, 'let total:i64=with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,fs}{' + child + gate +
                 'var i:i64=0;while i<1000{i=i+1;}assert(unwrap(file_write_text("@GATE@.release","go")));'
                 'assert(unwrap(task_wait(child)).body==utf8_bytes("42"));return i;});assert(total==1000);', started_path=path)
            path = '/held-cancel-' + transport + '-@LABEL@'
            child = 'let child:task<result<httpc::Response>>=task_spawn(s,server fn()->result<httpc::Response> !{task,ffi}{return send_raw(' + request(url=base + path, timeout=30000) + ');});'
            case('cancel-' + transport, 'with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs}{' + child + gate +
                 'assert(task_cancel(child));task_wait(child);});', fatal='E_CANCELLED', started_path=path)
            path = '/held-parent-' + transport + '-@LABEL@'
            case('parent-deadline-' + transport, 'send_raw(' + request(url=base + path, timeout=30000) + ');', fatal='E_TIMEOUT', started_path=path)
        path = '/held-capacity-@LABEL@'
        case('capacity', 'with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs}{'
             'let child:task<result<httpc::Response>>=task_spawn(s,server fn()->result<httpc::Response> !{task,ffi}{return send_raw(' + request(path, timeout=500) + ');});'
             'while !is_ok(file_read_text("@GATE@.ready")){task_yield();}' + failure(request(), 'E_HTTP_BUSY') +
             'assert(error_code(task_wait(child))=="E_HTTP_TIMEOUT");});' + response(request()) +
             'assert(statistics_raw()[3]==1);', project='capacity', started_path=path)

        if args.case:
            unknown = set(args.case) - {item['name'] for item in cases}
            if unknown:
                raise ValueError('unknown HTTP cases: ' + ', '.join(sorted(unknown)))
            cases = [item for item in cases if item['name'] in args.case]
        for item in cases:
            for mode in ('eval', 'debug', 'release'):
                name, fatal = item['name'], item['fatal']
                label = name + '-' + mode
                project, prefix = projects[item['project']]
                path = item['started_path'].replace('@LABEL@', label) if item['started_path'] else None
                body = item['body'].replace('@LABEL@', label).replace('@GATE@', digest(path) if path else '')
                program = source_for_selected_sdk(prefix + 'server fn main()->unit !{task,ffi,fs,io}{' + body + ('print(42);' if not fatal else '') + '}\n', sdk)
                (out / (label + '.nex')).write_text(program)
                (project / 'main.nex').write_text(program)
                before_dns, before_http = peer.dns.count(), len(peer.events)
                argv = [compiler, 'eval' if mode == 'eval' else 'run', '--foreign', project / 'foreign.json',
                        '--task-workers', '1', '--task-steps', '4000000', '--task-timeout-ms',
                        '2000' if name.startswith('parent-deadline') else '10000', '--json']
                if mode != 'eval':
                    argv += ['--profile', mode]
                result = run(label, argv, cwd=project, env=env, expected=(1 if mode == 'eval' else 70) if fatal else 0)
                if fatal:
                    if mode == 'eval':
                        assert result.get('code') == fatal, (label, result)
                    else:
                        diagnostics = result.get('native_diagnostics', {}).get('diagnostics', [])
                        assert result.get('exit_code') == 70 and len(diagnostics) == 1 and diagnostics[0]['status'] == 'mapped' and diagnostics[0]['report']['code'] == fatal, (label, result)
                else:
                    assert result['ok'] and result['stdout'] == '42\n', (label, result)
                if item['silent'] or name.startswith('IPv'):
                    assert peer.dns.count() == before_dns, label
                if item['silent']:
                    assert len(peer.events) == before_http, label
                if path:
                    assert (peer.files / (digest(path) + '.ready')).is_file(), label
                stderr = (out / (label + '.stderr')).read_text() + '\n' + result.get('stderr', '')
                retired = [json.loads(s) for s in re.findall(r'NEX_HTTP_RETIRE (\{[^\n]+\})', stderr)]
                assert retired and all(s['dns_opened'] == s['dns_closed'] and s['dns_live'] == 0 and s['sockets_opened'] == s['sockets_closed'] and s['sockets_live'] == 0 for s in retired), (label, stderr)
                assert not (out / 'forbidden-ambient-keylog').exists(), label
                report['cases'].append({'name': name, 'mode': mode, 'passed': True,
                    'expected_fatal': fatal, 'DNS_packets': peer.dns.count() - before_dns,
                    'HTTP1_requests': len(peer.events) - before_http, 'retired': retired})
                save()
        report.update(ok=True, state='passed', case_count=len(report['cases']), source_HTTP_executed=True)
    except BaseException as error:
        report.update(state='failed', error=repr(error))
        raise
    finally:
        if peer:
            report['DNS_events'], report['HTTP1_events'] = peer.dns.events, peer.events
            peer.close()
        save()
    print(json.dumps({key: report.get(key) for key in ('ok', 'case_count', 'language', 'actual_compiler_toolchain', 'seconds')}))
    if temporary and report['ok']:
        shutil.rmtree(out)


if __name__ == '__main__':
    main()
