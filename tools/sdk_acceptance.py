#!/usr/bin/env python3
"""Exercise an installed NEX development chain, retaining reviewable evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import shutil
import signal
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


class DAP:
    """Small bounded client for the installed stdio adapter, with no test imports."""
    def __init__(self, command, directory, environment):
        self.log = (directory / 'dap-stderr.log').open('wb')
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.log, env=environment)
        self.messages = queue.Queue()
        self.pending = []
        self.sequence = 0

        def read():
            try:
                while True:
                    headers = {}
                    while True:
                        line = self.process.stdout.readline(8193)
                        if not line:
                            return
                        require(len(line) <= 8192, 'oversized DAP header')
                        if line == b'\r\n':
                            break
                        key, value = line.decode().split(':', 1)
                        headers[key.lower()] = value.strip()
                    size = int(headers['content-length'])
                    require(0 < size <= 4 * 1024 * 1024, 'oversized DAP message')
                    body = bytearray()
                    while len(body) < size:
                        part = self.process.stdout.read(size - len(body))
                        require(part, 'truncated DAP message')
                        body.extend(part)
                    self.messages.put(json.loads(body))
            except Exception as error:
                self.messages.put(error)
            finally:
                self.messages.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, command, arguments=None):
        self.sequence += 1
        body = json.dumps({'seq': self.sequence, 'type': 'request',
                           'command': command, 'arguments': arguments or {}}).encode()
        self.process.stdin.write(('Content-Length: %d\r\n\r\n' % len(body)).encode() + body)
        self.process.stdin.flush()
        return self.sequence

    def wait(self, predicate, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            for index, message in enumerate(self.pending):
                if predicate(message):
                    return self.pending.pop(index)
            message = self.messages.get(timeout=max(.01, deadline - time.monotonic()))
            require(message is not None and not isinstance(message, Exception),
                    'DAP stream stopped: ' + str(message))
            self.pending.append(message)

    def response(self, sequence):
        value = self.wait(lambda m: m.get('type') == 'response' and m.get('request_seq') == sequence)
        require(value.get('success'), 'DAP request failed: ' + str(value))
        return value.get('body', {})

    def request(self, command, arguments=None):
        return self.response(self.send(command, arguments))

    def event(self, name):
        return self.wait(lambda m: m.get('type') == 'event' and m.get('event') == name).get('body', {})

    def close(self):
        try:
            if self.process.poll() is None:
                try:
                    self.request('disconnect', {'terminateDebuggee': True})
                    self.process.wait(timeout=5)
                except (Exception, KeyboardInterrupt):
                    self.process.kill()
                    self.process.wait(timeout=5)
        finally:
            self.process.stdin.close()
            self.reader.join(timeout=5)
            self.process.stdout.close()
            self.log.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('sdk', type=Path, help='Installed SDK prefix containing bin/nex and share/nex')
    parser.add_argument('--output', required=True, type=Path, help='New or empty evidence directory')
    parser.add_argument('--live', action='store_true', help='Require actual LLDB and NEX DAP child launches')
    parser.add_argument('--browser', action='store_true', help='Require a real locked TypeScript/Vite release build')
    parser.add_argument('--forbid-source', action='append', type=Path, default=[],
                        help='Require this source mount path to be absent (repeatable)')
    args = parser.parse_args()
    sdk = args.sdk.resolve()
    root = args.output.resolve()
    resources = sdk / 'share/nex'
    compiler = sdk / 'bin/nex'
    if not compiler.is_file() or not (resources / 'llm/language-pack.json').is_file():
        parser.error('sdk must be an installed NEX SDK')
    if root == sdk or sdk in root.parents:
        parser.error('--output must be outside the SDK')
    if root.exists() and (not root.is_dir() or any(root.iterdir())):
        parser.error('--output must be new or empty; previous evidence is never replaced')
    root.mkdir(parents=True, exist_ok=True)
    logs = root / 'logs'
    logs.mkdir()
    environment = dict(os.environ, NEX_RESOURCE_DIR=str(resources))
    report = {'schema': 'nex.sdk-acceptance/1', 'ok': False, 'sdk': str(sdk),
              'output': str(root), 'phases': [], 'commands': [], 'evidence': {}}
    started = time.monotonic()

    def save():
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(command, cwd=root, expected_success=True, timeout=180):
        number = len(report['commands'])
        row = {'command': list(map(str, command)), 'cwd': str(cwd),
               'stdout': str(logs / ('%03d.stdout' % number)),
               'stderr': str(logs / ('%03d.stderr' % number)), 'status': 'running'}
        report['commands'].append(row)
        save()
        with open(row['stdout'], 'wb') as out, open(row['stderr'], 'wb') as err:
            process = subprocess.Popen(row['command'], cwd=cwd, env=environment,
                                       stdout=out, stderr=err, start_new_session=True)
            try:
                code = process.wait(timeout=timeout)
            except BaseException:
                # Let NEX clean up task-owned children before escalating to SIGKILL.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    process.wait(timeout=10)
                except ProcessLookupError:
                    pass
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
                row['status'] = 'interrupted'
                save()
                raise
        row.update(exit_code=code, status='passed' if (code == 0) == expected_success else 'failed')
        save()
        require(row['status'] == 'passed', 'unexpected command result; inspect ' + row['stderr'])
        return Path(row['stdout']).read_text()

    def cli(*arguments, cwd=root, expected_success=True, timeout=180):
        return json.loads(run([compiler, *arguments, '--json'], cwd, expected_success, timeout))

    def phase(name, action):
        row = {'name': name, 'status': 'running'}
        report['phases'].append(row)
        save()
        action()
        row['status'] = 'passed'
        save()

    project = root / 'project'
    project.mkdir()
    state = {}
    expected = '42\nA\0🌍\n'
    model = '''module handoff_model;
pub enum Maybe<T> { None; Some(value:T); }
pub struct Box<T> { value:T; }
pub fn normalized<T:integer>(value:T) -> T { return value+0; }
pub fn capture<T>(value:T) -> (fn()->T) { return fn()->T { return value; }; }
pub fn roundtrip<T:wire>(value:T) -> T { return unwrap(decode_json<T>(encode_json(value))); }
'''
    choose = '''pub fn choose(value:result<model::Maybe<i64>>) -> i64 {
 return match value { ok(model::Maybe::Some(n)) if n>0 => model::normalized(n), _ => -1 };
}'''
    source = '''module handoff;
import "./model.nex" as model;
CHOOSE
fn observe(value:result<model::Maybe<i64>>,callback:fn()->i64) -> i64 {
 let answer:i64 = choose(value)+callback()-2;
 return answer; // sdk-breakpoint
}
fn main() -> unit !{io} {
 print(observe(ok(model::Maybe::Some(42)),model::capture(2)));
 print(model::Box("A\\u0000🌍").value);
}
test fn examples() -> unit {
 assert(choose(ok(model::Maybe::Some(42))) == 42);
 assert(choose(ok(model::Maybe<i64>::None())) == -1);
 assert(choose(err<model::Maybe<i64>>("E","unread")) == -1);
 assert(model::capture(40)()==40);
 assert(model::capture("A\\u0000🌍")()=="A\\u0000🌍");
 assert(model::roundtrip(["A\\u0000🌍"])==["A\\u0000🌍"]);
}
'''.replace('CHOOSE', choose.replace('model::normalized(n)', 'model::normalized(n)+1'))

    def discover():
        for path in args.forbid_source:
            require(not path.exists(), 'source mount must be absent: ' + str(path))
        report['absent_source_probes'] = list(map(str, args.forbid_source))
        doctor = cli('doctor')
        descriptor = cli('describe')
        require(Path(doctor['runtime']).resolve() == (resources / 'runtime/runtime.cpp').resolve(),
                'compiler selected resources outside this SDK')
        require('typed_nested_patterns' in descriptor['match_features'], 'SDK lacks checked nested patterns')
        require('snapshot_closures' in descriptor['function_value_features'], 'SDK lacks snapshot closures')
        require('wire' in descriptor['generic_constraints'], 'SDK lacks checked wire constraints')
        require('fs' in descriptor['effects'] and
                'no_implicit_http_capability' in descriptor['file_features'] and
                descriptor['file_environment']['http_inherits_environment'] is False,
                'SDK lacks explicit filesystem capability policy')
        pack = json.loads((resources / 'llm/language-pack.json').read_text())
        require(pack['language_version'] == doctor['language'] == descriptor['version'], 'language pack mismatch')
        inventory = {}
        for name in [*pack['documents'].values(), *pack['examples'].values()]:
            path = (resources / name).resolve()
            require(resources.resolve() in path.parents and path.is_file(), 'missing/escaped language resource: ' + name)
            path.read_text()  # A pack offered to another model must contain actual UTF-8 text.
            inventory[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for kind in ('prompt', 'language', 'grammar', 'protocol', 'web', 'server', 'api',
                     'debug', 'build', 'profile', 'verify', 'task', 'expression', 'operation', 'linux', 'match', 'function', 'files', 'bytes'):
            require(cli('guide', '--kind', kind)['text'], 'empty guide: ' + kind)
        report.update(doctor=doctor, compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
                      version=doctor['version'], language=doctor['language'], host=doctor['host'],
                      resource_hashes=inventory)

    def new_project():
        directory = root / 'created'
        cli('init', directory)
        cli('check', cwd=directory)
        cli('test', cwd=directory)
        cli('run', cwd=directory)

    def baseline_failure():
        (project / 'model.nex').write_text(model)
        (project / 'main.nex').write_text(source)
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        state['before'] = cli('check', cwd=project)['revision']
        context = cli('context', '--symbol', 'choose', cwd=project)
        require(context['symbol'] == 'handoff::choose', 'bounded context selected another function')
        state['graph_before'] = cli('graph', cwd=project)
        operations = cli('operations', '--symbol', 'choose', cwd=project)
        require(any(n['kind'] == 'pattern.binding' for n in operations['nodes']), 'pattern bindings missing from graph')
        task = cli('task', project / 'main.nex', '--kind', 'init', cwd=project)
        task.update(id='sdk-handoff', title='Installed SDK development chain',
                    goal='Preserve the reviewed positive-result selection, error fallback and exact Unicode output.')
        native = next(c for c in task['checks'] if c['kind'] == 'test')
        task['checks'] += [dict(native, id='web-examples', target='web'),
            {'id': 'observable', 'kind': 'run', 'program': 'app', 'target': 'native',
             'entry': 'handoff::main', 'expect': {'stdout': expected, 'exit_code': 0}}]
        task['requirements'] = [{'id': 'selection',
            'text': 'Positive Some values are preserved; None/errors return -1. Main prints 42 and the exact NUL/Unicode string.',
            'bindings': [{'program': 'app', 'kind': 'function', 'symbol': 'handoff::choose'}],
            'targets': ['native', 'web'], 'checks': [c['id'] for c in task['checks']]}]
        state['task'] = project / 'task.json'
        state['task'].write_text(json.dumps(task, indent=2) + '\n')
        cli('task', state['task'], '--kind', 'check', cwd=project)
        failed = cli('task', state['task'], '--kind', 'run', cwd=project, expected_success=False, timeout=300)
        require(failed['status'] == 'not_satisfied' and not failed['ok'] and
                all(c['status'] == 'failed' for c in failed['checks'] if c['kind'] in ('test', 'run')),
                'deliberately wrong implementation did not fail its behavior checks')
        state['task_hash'] = failed['task_hash']
        report['evidence'].update(before_revision=state['before'], failed_receipt=failed['output'], task_hash=failed['task_hash'])

    def repair():
        patch = root / 'repair.json'
        patch.write_text(json.dumps({'expected_revision': state['before'],
            'replacements': [{'name': 'handoff::choose', 'source': choose}]}, indent=2) + '\n')
        state['after'] = cli('apply', '--patch', patch, cwd=project)['revision']
        require(state['after'] != state['before'], 'repair did not change semantic revision')
        conflict = cli('apply', '--patch', patch, cwd=project, expected_success=False)
        require(conflict['code'] == 'E_CONFLICT', 'stale patch was accepted')
        after_graph = cli('graph', cwd=project)
        require({n['name']: n['id'] for n in after_graph['nodes']} ==
                {n['name']: n['id'] for n in state['graph_before']['nodes']}, 'function identities changed')
        exported_graph = root / 'graph.json'
        exported_graph.write_text(json.dumps(after_graph, indent=2) + '\n')
        imported = root / 'imported'
        imported.mkdir()
        (imported / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        adopted = cli('import', exported_graph, cwd=imported)
        require(adopted['revision'] == state['after'], 'graph import changed checked revision')
        require((imported / '.nex/graph.db').is_file(), 'graph import used an enclosing project store')
        require(cli('run', '--revision', 'HEAD', cwd=imported)['stdout'] == expected, 'imported graph output differs')
        passed = cli('task', state['task'], '--kind', 'run', '--revision', state['after'],
                     '--task-hash', state['task_hash'], cwd=project, timeout=300)
        require(passed['status'] == 'passed' and passed['task_hash'] == state['task_hash'], 'reviewed task changed or failed')
        state['accepted'] = passed
        report['evidence'].update(after_revision=state['after'], passed_receipt=passed['output'], graph=str(exported_graph))

    def backend_agreement():
        for profile in ('debug', 'release'):
            cli('test', '--revision', state['after'], '--profile', profile, cwd=project)
            observed = cli('run', '--revision', state['after'], '--profile', profile, cwd=project)
            require(observed['stdout'] == expected and observed['exit_code'] == 0, 'native profile output differs')
        require(cli('eval', '--revision', state['after'], cwd=project)['stdout'] == expected, 'reference output differs')
        cli('test', '--revision', state['after'], '--target', 'web', cwd=project)
        built = cli('build', '--revision', state['after'], '--profile', 'release', cwd=project)
        standalone = root / 'standalone'
        shutil.copyfile(built['executable'], standalone)
        standalone.chmod(0o755)
        unavailable = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([standalone]) == expected, 'independent executable output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
        report['evidence']['standalone'] = str(standalone)
        numeric = root / 'numbers'
        numeric.mkdir()
        shutil.copyfile(resources / 'examples/numbers.nex', numeric / 'main.nex')
        (numeric / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        number_revision = cli('check', cwd=numeric)['revision']
        number_output = cli('eval', cwd=numeric)['stdout']
        require(number_output.startswith('2.5e0\n') and '"E_RANGE"' in number_output,
                'numeric SDK example selected another behavior')
        for profile in ('debug', 'release'):
            cli('test', '--profile', profile, cwd=numeric)
            require(cli('run', '--profile', profile, cwd=numeric)['stdout'] == number_output,
                    'numeric native/reference output differs')
        cli('test', '--target', 'web', cwd=numeric)
        number_build = cli('build', '--profile', 'release', cwd=numeric)
        number_standalone = root / 'numeric-standalone'
        shutil.copyfile(number_build['executable'], number_standalone)
        number_standalone.chmod(0o755)
        (numeric / 'main.nex').unlink()
        require(cli('run', '--revision', number_revision, cwd=numeric)['stdout'] == number_output,
                'numeric archived revision did not survive source deletion')
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([number_standalone]) == number_output, 'independent numeric executable differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
        report['evidence']['numeric_language'] = {'revision': number_revision,
            'native_profiles': ['debug', 'release'], 'typescript': True,
            'source_deleted_replay': True, 'standalone_without_resources': str(number_standalone)}
        cached_project = root / 'function-cache'
        cached_project.mkdir()
        cached_source = cached_project / 'main.nex'
        cached_source.write_text('module sdk_cache;\n'
            'fn changed(value:i64)->i64{return value+1;}\n'
            'fn sibling(value:i64)->i64{return value*2;}\n'
            'fn main()->unit!{io}{print(changed(2));print(sibling(3));}\n')
        (cached_project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        before = cli('build', cwd=cached_project)
        require(before['compiled_functions'] == 3, 'initial function cache did not compile all reachable bodies')
        require(run([before['executable']]) == '3\n6\n', 'initial function cache output differs')
        warm = cli('build', cwd=cached_project)
        require(warm['cached'] and warm['compiled_functions'] == 0 and warm['reused_functions'] == 3,
                'warm function cache did not reuse all bodies')
        cached_source.write_text(cached_source.read_text().replace('value+1;', 'value+100;'))
        after = cli('build', cwd=cached_project)
        require(after['compiled_functions'] == 1 and after['reused_functions'] == 2,
                'a same-file body edit recompiled unrelated functions')
        require(run([after['executable']]) == '102\n6\n' and
                cli('eval', cwd=cached_project)['stdout'] == '102\n6\n', 'cached native/reference output differs')
        cached_source.unlink()
        require(cli('run', '--revision', before['revision'], cwd=cached_project)['stdout'] == '3\n6\n' and
                cli('run', '--revision', after['revision'], cwd=cached_project)['stdout'] == '102\n6\n',
                'function cache did not preserve both source-deleted revisions')
        report['evidence']['function_cache'] = {'before_revision': before['revision'],
            'after_revision': after['revision'], 'compiled_after_edit': after['compiled_functions'],
            'reused_after_edit': after['reused_functions'], 'source_deleted_replay': True}

    def text_files():
        directory = root / 'text-files'
        directory.mkdir()
        data = root / 'file data % 🧠'
        data.mkdir()
        shutil.copyfile(resources / 'examples/files.nex', directory / 'main.nex')
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        keys = ('NEX_FILES_ROOT', 'NEX_FILES_WRITE', 'NEX_RESOURCE_DIR')
        saved = {key: environment.get(key) for key in keys}
        try:
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='1')
            revision = cli('check', cwd=directory)['revision']
            expected_text = 'Я🧠\0text\n'
            require(cli('eval', cwd=directory)['stdout'] == expected_text,
                    'installed text-file interpreter output differs')
            for profile in ('debug', 'release'):
                cli('test', '--profile', profile, cwd=directory)
                require(cli('run', '--profile', profile, cwd=directory)['stdout'] == expected_text,
                        'installed text-file native/reference output differs')
            built = cli('build', '--profile', 'release', cwd=directory)
            metadata = json.loads((Path(built['executable']).parent / 'build.json').read_text())
            require('nex_files.cpp' in metadata['runtime_components'] and
                    'nex_store.cpp' not in metadata['runtime_components'] and
                    'nex_json.cpp' not in metadata['runtime_components'],
                    'file-only program selected unrelated runtime components')
            package = root / 'file-application'
            cli('package', '--directory', package, cwd=directory)
            manifest = json.loads((package / 'application.json').read_text())
            require(not manifest['execution_verified'], 'assembly falsely certified execution')
            (directory / 'main.nex').unlink()
            require(cli('run', '--revision', revision, cwd=directory)['stdout'] == expected_text,
                    'text-file revision did not survive source deletion')
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            executable = package / 'bin/app'
            require(run([executable]) == expected_text and
                    (data / 'nex-message.txt').read_bytes() == expected_text[:-1].encode(),
                    'packaged file program needs compiler resources or changed text bytes')
            require(hashlib.sha256(executable.read_bytes()).hexdigest() == manifest['files']['bin/app']['sha256'],
                    'executed file application differs from package inventory')
            environment['NEX_RESOURCE_DIR'] = saved['NEX_RESOURCE_DIR']
            denied = root / 'file-denial'
            denied.mkdir()
            (denied / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            (denied / 'main.nex').write_text('''module file_denial;
server fn main()->unit!{fs,io}{
 print(error_code(file_read_text("nex-message.txt")));
 print(error_code(file_write_text("nex-message.txt","must not replace")));
}
''')
            environment.pop('NEX_FILES_ROOT', None)
            for command in ('eval', 'run'):
                require(cli(command, cwd=denied)['stdout'] == 'CAPABILITY\nCAPABILITY\n',
                        'missing file capability unexpectedly permitted access')
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='0')
            for command in ('eval', 'run'):
                require(cli(command, cwd=denied)['stdout'] == '\nCAPABILITY\n',
                        'read-only file capability unexpectedly permitted writes')
            require((data / 'nex-message.txt').read_bytes() == expected_text[:-1].encode(),
                    'denied write changed the existing file')
            report['evidence']['text_files'] = {'revision': revision,
                'native_profiles': ['debug', 'release'], 'source_deleted_replay': True,
                'strict_unicode_nul_roundtrip': True, 'missing_capability_denied': True,
                'read_only_write_denied': True, 'standalone_without_resources': str(executable),
                'application_manifest_sha256': hashlib.sha256((package / 'application.json').read_bytes()).hexdigest()}
        finally:
            for key, value in saved.items():
                if value is None:
                    environment.pop(key, None)
                else:
                    environment[key] = value

    def measured():
        measured = cli('profile', '--revision', state['after'], '--scenario', 'installed SDK handoff', cwd=project)
        require(measured['stdout'] == expected and measured['exit_code'] == 0, 'profile changed output')
        saved = json.loads(Path(measured['output']).read_text())
        nodes = {n['name']: n for n in cli('graph', cwd=project)['nodes']}
        choose_profile = next(f for f in saved['functions'] if f['name'] == 'handoff::choose')
        require(choose_profile['calls'] == choose_profile['completed'] == 1 and choose_profile['aborted'] == 0,
                'profile call/completion evidence differs')
        for function in saved['functions']:
            require(function['node_id'] == nodes[function['name']]['id'] and
                    function['content_hash'] == nodes[function['name']]['hash'], 'profile graph attribution differs')
        for pool in saved['memory']:
            require(pool['allocations'] == pool['frees'] and pool['live'] == pool['live_shallow_bytes'] == 0,
                    'managed values remain live after normal exit')
        for field in ('dropped_events', 'dropped_functions', 'dropped_frames', 'dropped_allocations', 'untracked_frees'):
            require(saved[field] == 0, 'incomplete profile evidence: ' + field)
        report['evidence']['profile'] = measured['output']

    def sources_and_debug():
        # Only the stale live sources are removed; archived projections and receipts remain.
        (project / 'main.nex').unlink()
        (project / 'model.nex').unlink()
        state['task'].unlink()
        session = cli('debug', '--revision', state['after'], '--kind', 'nex-dap', cwd=project)
        state['session'] = session
        manifest = json.loads(Path(session['manifest']).read_text())
        for item in manifest['sources']:
            require(Path(item['projection']).is_file(), 'archived debugger source is missing')
        if args.live:
            projected = next(s['projection'] for s in manifest['sources'] if Path(s['original']).name == 'main.nex')
            line = next(i + 1 for i, s in enumerate(Path(projected).read_text().splitlines()) if '// sdk-breakpoint' in s)
            client = DAP(session['adapter_command'], root, environment)
            try:
                client.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path', 'linesStartAt1': True})
                pending = client.send('launch', dict(session['launch'], disableASLR=False))
                client.event('initialized')
                placed = client.request('setBreakpoints', {'source': {'path': projected}, 'breakpoints': [{'line': line}]})
                require(placed['breakpoints'][0]['verified'], 'archived source breakpoint was not verified')
                client.request('configurationDone')
                client.response(pending)
                stopped = client.event('stopped')
                frame = client.request('stackTrace', {'threadId': stopped['threadId']})['stackFrames'][0]['id']
                expression = '(match value {ok(model::Maybe::Some(n)) if n>0=>n,_=>-1})+callback()-2'
                value = client.request('evaluate', {'expression': expression, 'frameId': frame, 'context': 'watch'})
                require(value['nex']['value'] == '42' and value['nex']['revision'] == state['after'], 'stopped watch differs')
                callback = client.request('evaluate', {'expression': 'callback', 'frameId': frame, 'context': 'watch'})
                require(callback['type'] == 'fn()->i64' and
                        callback['nex']['wire_schema']['schema'] == 'nex.debug-wire/1' and
                        callback['nex']['value']['captures'] == {'value': '2'}, 'stopped callback differs')
                children = client.request('variables', {'variablesReference': callback['variablesReference'],
                    'start': 1, 'count': 1})['variables']
                require(len(children) == 1 and children[0]['name'] == 'value' and children[0]['value'] == '2',
                        'stopped callback children differ')
                raw = client.request('evaluate', {'expression': '`nex-frame ' + expression, 'frameId': frame, 'context': 'repl'})
                snapshot = root / 'frame.json'
                snapshot.write_text(json.dumps(json.loads(raw['result']), indent=2) + '\n')
                client.request('continue', {'threadId': stopped['threadId']})
                require(client.event('exited')['exitCode'] == 0, 'debuggee failed')
                offline = cli('inspect', snapshot, '--manifest', session['manifest'], '--expression', expression, cwd=project)
                require(offline['value'] == '42', 'offline captured watch differs')
                report['evidence']['frame'] = str(snapshot)
                report['evidence']['checked_callable_watch'] = True
            finally:
                client.close()
        report['evidence']['debug_manifest'] = session['manifest']
        replay = cli('task', state['accepted']['output'], '--kind', 'replay', cwd=project, timeout=300)
        require(replay['status'] == 'passed' and replay['task_hash'] == state['task_hash'], 'source-free replay failed')
        require(cli('run', '--revision', state['before'], cwd=project)['stdout'] == expected.replace('42\n', '43\n', 1),
                'old revision no longer executes its own behavior')
        materialized = root / 'exported'
        cli('export', '--revision', state['after'], '--directory', materialized, cwd=project)
        require(cli('check', cwd=materialized)['revision'] == state['after'], 'materialization changed revision')
        require(cli('run', cwd=materialized)['stdout'] == expected, 'exported sources do not execute')
        report['evidence'].update(replay_receipt=replay['output'], exported=str(materialized),
                                  original_sources_deleted=True, live_debugger=args.live)

    def proof():
        directory = root / 'proof'
        shutil.copytree(resources / 'examples/verification', directory)
        verified = cli('verify', '--contracts', directory / 'contracts.json', cwd=directory)
        require(verified['ok'] and verified['functions'] and
                all(f['status'] == 'proven' for f in verified['functions']), 'installed scalar contracts were not proven')
        report['evidence']['scalar_proof'] = 'proven (installed scalar example, not a proof of matching or compiler correctness)'

    def authenticated_storage():
        directory = root / 'service'
        directory.mkdir()
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        (directory / 'main.nex').write_text('''module installed_service;
import "std/http.nex" as http;
server fn handle(request:http::Request) -> http::Response !{db} {
  if request.method == "POST" {
    let saved:result<bool> = store_put("value",request.body);
    return match saved {ok(_) => http::Response(200,request.user+":"+request.body,"text/plain"),err(_,_) => http::Response(500,"storage failure","text/plain")};
  }
  let loaded:result<str> = store_get("value");
  return match loaded {ok(value) => http::Response(200,request.user+":"+value,"text/plain"),err(_,_) => http::Response(404,"missing","text/plain")};
}
''')
        auth = directory / 'auth.json'
        tokens = {user: cli('token', '--user', user, '--auth', auth, cwd=directory)['token']
                  for user in ('alice', 'bob')}
        built = cli('build', '--target', 'server', '--profile', 'release', cwd=directory)
        certificate, key = directory / 'cert.pem', directory / 'key.pem'
        run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-sha256', '-days', '1',
             '-subj', '/CN=localhost', '-addext', 'subjectAltName=IP:127.0.0.1,DNS:localhost',
             '-keyout', key, '-out', certificate], cwd=directory)
        context = ssl.create_default_context(cafile=str(certificate))
        for encrypted in (False, True):
            command = [built['executable'], '--auth', str(auth), '--database', str(directory / 'data.sqlite'), '--port', '0']
            if encrypted:
                command += ['--cert', str(certificate), '--key', str(key)]
            stderr = logs / ('service-https.stderr' if encrypted else 'service-http.stderr')
            with stderr.open('w') as errors:
                process = subprocess.Popen(command, cwd=directory, env=environment,
                                           stdout=subprocess.PIPE, stderr=errors, text=True)
                try:
                    lines = queue.Queue()
                    threading.Thread(target=lambda: lines.put(process.stdout.readline()), daemon=True).start()
                    line = lines.get(timeout=20)
                    match = re.fullmatch(r'NEX server (https?://127\.0\.0\.1:[0-9]+)\s*', line)
                    require(match is not None, 'installed server did not start; inspect ' + str(stderr))
                    base = match.group(1)
                    require(base.startswith('https:') == encrypted, 'server selected wrong transport')
                    def request(user, body=None):
                        headers = {} if user is None else {'Authorization': 'Bearer ' + tokens[user]}
                        payload = None if body is None else body.encode()
                        value = urllib.request.Request(base + '/api/value', data=payload, headers=headers)
                        try:
                            response = urllib.request.urlopen(value, context=context if encrypted else None, timeout=15)
                        except urllib.error.HTTPError as error:
                            response = error
                        with response:
                            return response.status, response.read().decode()
                    unauthenticated = request(None)
                    require(unauthenticated[0] == 401, 'expected unauthenticated rejection (401), received ' + str(unauthenticated[0]))
                    if not encrypted:
                        require(request('alice', 'Unicode 🧠') == (200, 'alice:Unicode 🧠'), 'alice write failed')
                        require(request('bob')[0] == 404, 'bob could read alice data')
                        require(request('bob', 'separate') == (200, 'bob:separate'), 'bob write failed')
                    require(request('alice') == (200, 'alice:Unicode 🧠'), 'alice persistence/isolation failed')
                    require(request('bob') == (200, 'bob:separate'), 'bob persistence/isolation failed')
                finally:
                    if process.poll() is None:
                        process.terminate()
                    try:
                        process.communicate(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.communicate(timeout=5)
                require(process.returncode == 0, 'installed server failed; inspect ' + str(stderr))
            require('E_INTERNAL_LEAK' not in stderr.read_text(), 'installed server leaked owned values')
        report['evidence']['authenticated_storage'] = {'executable': built['executable'],
            'http_https': True, 'unauthenticated_rejected': True,
            'principal_isolation': True, 'persistent_across_restart': True,
            'metadata': built['metadata']}

    def browser():
        directory = root / 'browser'
        directory.mkdir()
        client = (resources / 'examples/functions/web.nex').read_text()
        client += '\nserver fn sdk_unreachable_sentinel() -> str {return "SDK_SERVER_ONLY_SENTINEL";}\n'
        (directory / 'main.nex').write_text(client)
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        tested = cli('test', '--target', 'web', cwd=directory)
        require('functions::web::transitions' in {t['name'] for t in tested['tests']},
                'browser tests selected another project')
        generated = root / 'generated-web'
        cli('web', '--directory', generated, cwd=directory)
        require(not any('SDK_SERVER_ONLY_SENTINEL' in f.read_text() for f in generated.rglob('*.ts')),
                'server code entered generated client')
        if args.browser:
            built = cli('build', '--target', 'web', '--profile', 'release', cwd=directory, timeout=300)
            dist = Path(built['dist'])
            require((dist / 'index.html').is_file() and any(dist.rglob('*.js')), 'missing production browser assets')
            for path in dist.rglob('*'):
                if path.is_file():
                    require(b'SDK_SERVER_ONLY_SENTINEL' not in path.read_bytes(), 'server code entered browser assets')
            report['evidence']['browser_dist'] = str(dist)
        numeric = root / 'numeric-browser'
        numeric.mkdir()
        shutil.copyfile(resources / 'examples/numbers-web.nex', numeric / 'main.nex')
        (numeric / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        cli('test', cwd=numeric)
        numeric_tests = cli('test', '--target', 'web', cwd=numeric)
        require('numbers_web::transitions' in {t['name'] for t in numeric_tests['tests']},
                'numeric browser tests selected another project')
        numeric_generated = root / 'generated-numeric-web'
        numeric_project = cli('web', '--directory', numeric_generated, cwd=numeric)
        require(not any('FINITE_NUMBERS_SERVER_SENTINEL' in path.read_text()
                        for path in numeric_generated.rglob('*.ts')),
                'numeric server code entered generated client')
        numeric_evidence = {'revision': numeric_project['revision'], 'native_tests': True,
                            'typescript_tests': True, 'generated': str(numeric_generated),
                            'browser_build': args.browser}
        if args.browser:
            numeric_built = cli('build', '--target', 'web', '--profile', 'release', cwd=numeric, timeout=300)
            numeric_dist = Path(numeric_built['dist'])
            require((numeric_dist / 'index.html').is_file() and any(numeric_dist.rglob('*.js')),
                    'missing numeric production browser assets')
            for path in numeric_dist.rglob('*'):
                if path.is_file():
                    require(b'FINITE_NUMBERS_SERVER_SENTINEL' not in path.read_bytes(),
                            'numeric server code entered browser assets')
            numeric_evidence['dist'] = str(numeric_dist)
        report['evidence']['numeric_browser'] = numeric_evidence
        report['evidence']['browser_build'] = args.browser

    try:
        for name, action in [('discovery', discover), ('new-project', new_project),
                ('reviewed-failure', baseline_failure), ('graph-repair-import', repair),
                ('backend-agreement', backend_agreement), ('text-files', text_files), ('profile', measured),
                ('archive-debug-replay-export', sources_and_debug), ('scalar-proof', proof),
                ('authenticated-storage', authenticated_storage), ('browser', browser)]:
            phase(name, action)
        report['ok'] = True
    except BaseException as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
        if report['phases'] and report['phases'][-1]['status'] == 'running':
            report['phases'][-1]['status'] = 'failed'
        raise
    finally:
        report['seconds'] = round(time.monotonic() - started, 3)
        save()
    print(json.dumps({'ok': True, 'report': str(root / 'report.json'), 'host': report['doctor']['host'],
                      'version': report['doctor']['version'], 'live_debugger': args.live,
                      'browser_build': args.browser, 'seconds': report['seconds']}, indent=2), flush=True)


if __name__ == '__main__':
    main()
