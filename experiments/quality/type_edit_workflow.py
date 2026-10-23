#!/usr/bin/env python3
"""Opt-in finite Q1: one atomic Row type edit shared by CLI and generated HTTP.

Runs the selected compiler/resources, retaining bounded raw evidence. This is an
acceptance fixture, not a language feature, benchmark, or whole-toolchain claim.
"""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import signal
import sqlite3
import subprocess
import threading
import time
import traceback
import urllib.request


MODEL = 'module model;pub struct Row{value:i64;}pub fn make()->Row{return Row(41);}\n'
APP = '''module app;
import "../model/value.nex" as m;import "std/api.nex" as api;
fn main()->unit!{io}{print(m::make().value);}
test fn row_test()->unit{assert(m::make().value==41);}
server fn fetch(context:api::Context)->result<m::Row>{return ok(m::make());}
endpoint row("GET","/api/row")=fetch;
'''


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inventory(root):
    rows = {}
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts:
            continue
        if path.is_symlink():
            raise ValueError('symlink in reviewed resource input: ' + str(path))
        if path.is_file():
            rows[path.relative_to(root).as_posix()] = {
                'sha256': sha(path), 'mode': path.stat().st_mode & 0o777}
    if not rows:
        raise ValueError('empty resources')
    return rows


def graph_rows(path):
    # Logical contents, including IDs/history; SQLite may maintain WAL metadata.
    with sqlite3.connect(path.resolve().as_uri() + '?mode=rw', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        names = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted(db.execute('SELECT * FROM "' + name + '"').fetchall(), key=repr)
                for name in names}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--resources', type=Path,
                        help='default: COMPILER/../../share/nex')
    parser.add_argument('--output', type=Path, required=True, help='must not exist')
    args = parser.parse_args()
    compiler = args.compiler.resolve(strict=True)
    resources = (args.resources or compiler.parent.parent/'share/nex').resolve(strict=True)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error('--output must be a new directory')
    output.mkdir(parents=True)
    output = output.resolve()
    project = output/'project'
    (project/'app').mkdir(parents=True)
    (project/'model').mkdir()
    runner = Path(__file__).resolve()
    report = {'schema': 'nex.quality-type-edit-workflow/1', 'state': 'running', 'ok': False,
              'compiler': str(compiler), 'compiler_sha256': sha(compiler),
              'resources': str(resources), 'resource_inventory': inventory(resources),
              'runner': str(runner), 'runner_sha256': sha(runner),
              'host': {'system': platform.system(), 'machine': platform.machine(),
                       'python': platform.python_version()},
              'limits': {'command_timeout_seconds': 180, 'server_seconds': 30,
                         'http_timeout_seconds': 10, 'http_response_bytes': 1048576,
                         'output_bytes_per_stream': 8388608},
              'scope': 'One sync Row fixture and one atomic patch. Actual selected compiler cohort only; '
                       'not task HTTP, model-token/performance, unrelated tests, full-suite, '
                       'all-platform or kernel source isolation evidence.', 'commands': []}
    started = time.monotonic()
    env = dict(os.environ, NEX_RESOURCE_DIR=str(resources), PYTHONDONTWRITEBYTECODE='1')
    for name in ('NEX_CLANG', 'NEX_TOOLCHAIN', 'NEX_PROFILE_OUTPUT', 'NEX_TRACY'):
        env.pop(name, None)

    def save():
        report.update(updated=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                      seconds=round(time.monotonic()-started, 6))
        temporary = output/'report.json.tmp'
        temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        temporary.replace(output/'report.json')

    def guard():
        assert sha(compiler) == report['compiler_sha256'], 'compiler changed'
        assert sha(runner) == report['runner_sha256'], 'runner changed during proof'
        assert inventory(resources) == report['resource_inventory'], 'resources changed'

    def launch(name, argv, cwd, timeout=180, overrides=None):
        if type(timeout) is not int or not 1 <= timeout <= 180:
            raise ValueError('typed timeout must be1..180 seconds')
        guard()
        row = {'name': name, 'argv': list(map(str, argv)), 'cwd': str(cwd),
               'timeout_seconds': timeout, 'env_overrides': overrides or {}, 'status': 'running'}
        report['commands'].append(row)
        save()
        stdout, stderr = output/(name+'.stdout'), output/(name+'.stderr')
        streams = stdout.open('xb'), stderr.open('xb')
        process = subprocess.Popen(row['argv'], cwd=cwd, env={**env, **(overrides or {})},
                                   stdout=streams[0], stderr=streams[1], start_new_session=True)
        done, reasons = threading.Event(), []
        began = time.monotonic()

        def monitor():
            while not done.wait(0.05):
                reason = ('timeout' if time.monotonic()-began > timeout else
                          'output_limit' if max(stdout.stat().st_size, stderr.stat().st_size) > 8388608 else None)
                if reason:
                    reasons.append(reason)
                    try:
                        os.killpg(process.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    return

        watcher = threading.Thread(target=monitor, daemon=True)
        watcher.start()

        def finish():
            try:
                process.wait()
            finally:
                done.set()
                watcher.join()
                for stream in streams:
                    stream.close()
            row.update(exit_code=process.returncode, seconds=round(time.monotonic()-began, 6),
                       status=reasons[0] if reasons else ('passed' if not process.returncode else 'failed'))
            for key, path in [('stdout', stdout), ('stderr', stderr)]:
                row[key] = {'path': path.name, 'sha256': sha(path), 'bytes': path.stat().st_size}
            save()
            guard()
            assert not reasons and max(stdout.stat().st_size, stderr.stat().st_size) <= 8388608, row
            return row, stdout.read_text(), stderr.read_text()
        return process, stdout, finish

    def command(name, argv, cwd=project, ok=True, timeout=180, overrides=None):
        _, _, finish = launch(name, argv, cwd, timeout, overrides)
        row, stdout, stderr = finish()
        assert (row['exit_code'] == 0) == ok, (name, row, stdout, stderr)
        if not ok:
            row['status'] = 'expected_rejection'
            save()
        return stdout

    def nex(name, *argv, cwd=project, ok=True):
        return json.loads(command(name, [compiler, *argv, '--json'], cwd, ok))

    def source_guard():
        assert (project/'model/value.nex').read_text() == MODEL
        assert (project/'app/main.nex').read_text() == APP

    def contexts(label, revision):
        result = {}
        for index, (name, kind) in enumerate([
                ('model::Row', 'type'), ('model::make', 'function'),
                ('app::main', 'function'), ('app::row_test', 'function'),
                ('app::fetch', 'function'), ('app::row', 'endpoint')]):
            context = nex(label+'-'+str(index), 'context', '--revision', revision,
                          '--entity', kind, '--symbol', name)
            if kind == 'type':
                result[name] = context['node']
            else:
                module, local = name.rsplit('::', 1)
                local = '@endpoint/'+local if kind == 'endpoint' else local
                with sqlite3.connect((project/'.nex/graph.db').resolve().as_uri()+'?mode=rw', uri=True) as db:
                    db.execute('PRAGMA query_only=ON')
                    rows = db.execute('SELECT n.id,n.hash FROM node_ids i JOIN nodes n ON n.id=i.id '
                                      'WHERE i.module=? AND i.name=? AND n.revision=?',
                                      (module, local, revision)).fetchall()
                assert len(rows) == 1, (name, rows)
                result[name] = {'id':rows[0][0], 'hash':rows[0][1], 'context':context}
        return result

    def agreement(label, revision, expected):
        for backend in ('eval', 'run'):
            value = nex(label+'-'+backend, backend, '--revision', revision)
            assert value['stdout'] == expected+'\n', value
        assert nex(label+'-test-native', 'test', '--revision', revision)['ok']
        assert nex(label+'-test-ts', 'test', '--revision', revision, '--target', 'web')['ok']

    def generate(label, revision, expected_type):
        generated = nex(label+'-api', 'api', '--revision', revision, '--directory', output/label)
        assert generated['revision'] == revision
        document = json.loads(Path(generated['openapi']).read_text())
        assert document['info']['version'] == revision
        models = [s for s in document['components']['schemas'].values()
                  if 'value' in s.get('properties', {})]
        assert len(models) == 1
        field = models[0]['properties']['value']
        assert field['type'] == 'string'
        if expected_type == 'i64':
            assert field['x-nex-type'] == 'i64' and 'pattern' in field
        else:
            assert field.get('x-nex-type', 'str') == 'str' and 'pattern' not in field
        client = Path(generated['client_entry']).parent
        model = client/'models/model.nex'
        assert re.search(r'value\s*:\s*'+expected_type+r'\b', model.read_text())
        for path in client.rglob('*.nex'):
            assert 'server fn fetch' not in path.read_text()
        return generated, client

    def client_agreement(label, client, value, new_type):
        payload = json.dumps({'ok': {'value': value}}, separators=(',', ':'))
        quote = json.dumps(payload)
        expected = json.dumps(value) if new_type else value
        source = '''module client_probe;import "./api.nex" as sdk;import "./models/model.nex" as model;
import "std/net.nex" as net;import "std/web.nex" as web;
fn sample()->result<model::Row>{let response:net::Response=net::Response("1",200,ok(PAYLOAD));return sdk::response_row(web::Event("received",encode_json(response),"/"));}
fn main()->unit!{io}{print(unwrap(sample()).value);}
test fn codec()->unit{assert(unwrap(sample()).value==EXPECTED);OLD_REJECT}
'''.replace('PAYLOAD', quote).replace('EXPECTED', expected)
        old_reject = '' if new_type else '''let bad:net::Response=net::Response("1",200,ok("{\\"ok\\":{\\"value\\":\\"after\\"}}"));assert(error_code(sdk::response_row(web::Event("received",encode_json(bad),"/")))=="E_JSON");'''
        (client/'probe.nex').write_text(source.replace('OLD_REJECT', old_reject))
        for backend in ('eval', 'run'):
            result = nex(label+'-'+backend, backend, client/'probe.nex', cwd=client)
            assert result['stdout'] == value+'\n'
        for target in ('native', 'web'):
            options = [] if target == 'native' else ['--target', 'web']
            assert nex(label+'-test-'+target, 'test', client/'probe.nex', *options, cwd=client)['ok']

    def exported_archive(label, revision, expected):
        destination = output/('export-'+label)
        nex(label+'-export', 'export', '--revision', revision, '--directory', destination)
        assert nex(label+'-export-check', 'check', cwd=destination)['revision'] == revision
        manifest = {'schema': 'nex.project-build/1', 'default_configuration': 'release',
                    'configurations': {'release': {'profile': 'release'}}, 'components': {
                        'model': {'kind': 'static_library', 'root': 'model', 'entry': 'model/value.nex', 'entry_function': 'make'},
                        'cli': {'kind': 'executable', 'root': 'app', 'entry': 'app/main.nex', 'dependencies': {'model': 'static'}}}}
        (destination/'nex.build.json').write_text(json.dumps(manifest, indent=2)+'\n')
        built = nex(label+'-static-build', 'project', '--kind', 'build', '--component', 'cli', cwd=destination)
        artifacts = {row['component']: row for row in built['artifacts']}
        provider, app = artifacts['model'], artifacts['cli']
        compilation = json.loads(Path(app['compilation']).read_text())
        assert all('model::make' not in unit['functions'] for unit in compilation['units'])
        metadata = json.loads(Path(provider['debug_manifest']).read_text())
        symbol = next(f['native_symbol'] for f in metadata['functions'] if f['name'] == 'model::make')
        nm = shutil.which('nm')
        assert nm, 'native symbol tool nm required'
        archive_symbols = command(label+'-archive-nm', [nm, '-g', provider['artifact']])
        pattern = r'\b[Tt]\s+_?'+re.escape(symbol)+r'\s*$'
        assert len(re.findall(pattern, archive_symbols, re.M)) == 1
        imported = []
        for index, unit in enumerate(compilation['units']):
            text = command(label+'-object-'+str(index)+'-nm', [nm, '-g', unit['object']])
            assert not re.search(pattern, text, re.M)
            if re.search(r'\bU\s+_?'+re.escape(symbol)+r'\s*$', text, re.M):
                imported.append(unit['object'])
        assert imported, 'consumer must import the actual archive symbol'
        executable = Path(app['artifact'])
        assert command(label+'-static-execute', [executable]) == expected+'\n'
        report.setdefault('archive_ownership', {})[label] = {
            'revision': revision, 'provider': str(provider['artifact']), 'provider_sha256': sha(provider['artifact']),
            'consumer': str(executable), 'consumer_sha256': sha(executable), 'symbol': symbol,
            'consumer_import_objects': imported, 'consumer_compilation_sha256': sha(app['compilation'])}
        return destination, executable

    try:
        save()
        actual = nex('describe', 'describe', '--field', 'version')
        assert actual['value'] == '0.20', actual
        report.update(toolchain=actual['toolchain'], language=actual['value'], compiler_build=actual['compiler_build'])
        report['cohort_note'] = 'Evidence is for these actual selected identities; no inference of126 or another source cohort.'
        (project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'app/main.nex'})+'\n')
        (project/'model/value.nex').write_text(MODEL)
        (project/'app/main.nex').write_text(APP)
        original = nex('check-original', 'check')['revision']
        before = contexts('context-old', original)
        baseline = graph_rows(project/'.nex/graph.db')
        bad = project/'bad-type.json'
        bad.write_text(json.dumps({'expected_revision':original,'replacements':[{
            'name':'model::Row','kind':'type','source':'pub struct Row{value:str;}'}]}))
        rejected = nex('bad-type-only', 'apply', '--patch', bad, ok=False)
        assert rejected['code'] == 'E_TYPE'
        assert graph_rows(project/'.nex/graph.db') == baseline
        assert nex('history-after-reject', 'history')['head'] == original
        source_guard()
        agreement('old', original, '41')
        old_generated, old_client = generate('api-old', original, 'i64')
        patch = project/'atomic.json'
        patch.write_text(json.dumps({'expected_revision':original,'replacements':[
            {'name':'model::Row','kind':'type','source':'pub struct Row{value:str;}'},
            {'name':'model::make','kind':'function','source':'pub fn make()->Row{return Row("after");}'},
            {'name':'app::row_test','kind':'function','source':'test fn row_test()->unit{assert(m::make().value=="after");}'}]}))
        revised = nex('apply-atomic', 'apply', '--patch', patch)['revision']
        assert revised != original
        after = contexts('context-new', revised)
        assert {n:v['id'] for n,v in before.items()} == {n:v['id'] for n,v in after.items()}
        assert before['model::Row']['hash'] != after['model::Row']['hash']
        assert contexts('context-old-again', original) == before
        assert len(nex('history-final', 'history')['revisions']) == 2
        source_guard()
        agreement('new', revised, 'after')
        new_generated, new_client = generate('api-new', revised, 'str')
        client_agreement('client-old-strict', old_client, '41', False)
        client_agreement('client-new', new_client, 'after', True)
        old_export, old_image = exported_archive('old', original, '41')
        new_export, new_image = exported_archive('new', revised, 'after')
        server = nex('server-build', 'build', new_generated['server_entry'], '--target', 'server', '--profile', 'release')
        auth = output/'auth.json'
        token = nex('server-token', 'token', '--user', 'q1', '--auth', auth)['token']
        removed = []
        for folder in (project, old_export, new_export, output/'api-old', output/'api-new'):
            for path in sorted(p for p in folder.rglob('*.nex') if p.is_file()):
                removed.append({'path':str(path),'sha256':sha(path)})
                path.unlink()
        report['removed_physical_sources'] = removed
        assert not any(p.is_file() for p in project.rglob('*.nex'))
        for label, revision, expected, destination, image in (
                ('old',original,'41',old_export,old_image),('new',revised,'after',new_export,new_image)):
            assert nex(label+'-archived-eval', 'eval', '--revision', revision)['stdout'] == expected+'\n'
            assert nex(label+'-archived-run', 'run', '--revision', revision)['stdout'] == expected+'\n'
            assert nex(label+'-export-archived-run', 'run', '--revision', revision, cwd=destination)['stdout'] == expected+'\n'
            standalone = output/'standalone'/label
            standalone.parent.mkdir(exist_ok=True)
            shutil.copy2(image, standalone)
            assert sha(standalone) == sha(image)
            assert command(label+'-standalone-no-path', [standalone], cwd=output/'standalone', overrides={'PATH':''}) == expected+'\n'
        process, stdout, finish = launch('http-server', [server['executable'],'--auth',auth,
                                                     '--database',output/'http.sqlite','--port','0'], output, timeout=30)
        try:
            deadline = time.monotonic()+15
            address = None
            while not address and time.monotonic()<deadline and process.poll() is None:
                match = re.search(r'NEX server (http://127\.0\.0\.1:\d+)', stdout.read_text())
                if match:
                    address = match.group(1)
                else:
                    time.sleep(0.05)
            assert address, 'bounded server startup failed'
            request = urllib.request.Request(address+'/api/row', headers={'Authorization':'Bearer '+token}, method='GET')
            began = time.monotonic()
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=10) as response:
                payload = response.read(1048577)
                assert len(payload) <= 1048576 and response.status == 200
                assert json.loads(payload) == {'ok':{'value':'after'}}
            (output/'http-response.json').write_bytes(payload)
            report['http'] = {'method':'GET','path':'/api/row','status':200,'revision':revised,
                              'response_sha256':sha(output/'http-response.json'), 'bytes':len(payload),
                              'seconds':round(time.monotonic()-began,6), 'physical_fixture_sources_absent':True}
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGTERM)
            row, _, stderr = finish()
            assert row['exit_code'] == 0 and 'E_INTERNAL_LEAK' not in stderr
        report.update(state='passed',ok=True,old_revision=original,new_revision=revised,
                      declaration_ids={name:node['id'] for name,node in before.items()},
                      claims={'atomic_one_library_edit':True,'same_revision_cli_http':True,
                              'strict_old_decoder_rejection':True,'reference_native_typescript_agreement':True,
                              'physical_static_archive_ownership':True,'archived_source_runs':True,
                              'whole_acceptance_pack':False,'kernel_source_isolation':False})
        guard()
        save()
        print(json.dumps({'ok':True,'schema':report['schema'],'toolchain':report['toolchain'],
                          'compiler_build':report['compiler_build'],'report':str(output/'report.json')}))
        return 0
    except BaseException as error:
        report.update(state='failed',failure=str(error),traceback=traceback.format_exc())
        save()
        raise


if __name__ == '__main__':
    raise SystemExit(main())
