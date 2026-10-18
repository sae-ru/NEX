#!/usr/bin/env python3
"""Exercise an installed NEX development chain, retaining reviewable evidence."""
import argparse
import hashlib
import json
import os
import platform
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
        require('bytes' in descriptor['types'] and
                'immutable_contiguous_octets' in descriptor['binary_features'],
                'SDK lacks checked binary values')
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
                     'debug', 'build', 'profile', 'verify', 'task', 'expression', 'operation', 'linux', 'match', 'function', 'files', 'bytes', 'resources', 'ffi'):
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

    def foreign_boundary():
        directory = root / 'foreign-boundary'
        directory.mkdir()
        descriptor = cli('describe')['foreign_boundary']
        require(descriptor['source_support'] is True and descriptor['abi_version'] == 1,
                'source FFI requires the current checked C transport')
        c = directory / 'producer.c'
        c.write_text(r'''#include "nex_ffi.h"
#include <string.h>
nex_ffi_status producer(const nex_ffi_api_v1 *api,nex_ffi_call call,
    const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user) {
  uint8_t bytes[4],text[]={0xd0,0xaf,0,0xf0,0x9f,0xa7,0xa0};
  uint64_t n=0; nex_ffi_ref value=0; nex_ffi_status status; (void)user;
  if(count!=1 || api->abi_version!=1)return NEX_FFI_ARGUMENT;
  status=api->copy_bytes(call,args[0],0,bytes,4,&n);
  if(status || n!=4 || bytes[0]!=0 || bytes[1]!=255 || bytes[2]!=128 || bytes[3]!=1)return NEX_FFI_TYPE;
  status=api->make_string(call,text,sizeof(text),&value);memset(text,0,sizeof(text));
  if(status)return status;
  return api->make_success(call,value,out);
}
''')
        host = directory / 'host.cpp'
        host.write_text(r'''#include "nex_ffi_host.h"
#include <array>
#include <iostream>
extern "C" nex_ffi_status producer(const nex_ffi_api_v1*,nex_ffi_call,const nex_ffi_ref*,uint64_t,nex_ffi_ref*,void*);
int main() {
  std::array<uint8_t,4> data{0,255,128,1};
  std::vector<nexrt::Value> args{nexrt::Value(nexrt::bytes(nexrt::ByteBuffer::copy(data)))};
  auto value=nexrt::unwrap(nexrt::invokeForeign(producer,args));
  if(value.object->text!=std::string("\xd0\xaf\0\xf0\x9f\xa7\xa0",7))return 1;
  std::cout<<"C ABI OK\n";
}
''')
        runtime = resources / 'runtime'
        driver = report['doctor']['native_compiler']
        obj = directory / 'producer.o'
        executable = directory / 'host'
        run([driver, '-x', 'c', '-std=c11', '-I' + str(runtime), '-c', c, '-o', obj])
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime), host, obj,
             runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp', '-o', executable])
        c.unlink(); host.unlink(); obj.unlink()
        original = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-foreign-resources')
            require(run([executable]) == 'C ABI OK\n', 'independent installed C ABI example differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary'] = {'abi_version': 1, 'source_support': True,
            'c11_producer': True, 'cpp20_host': True, 'copied_utf8_and_bytes': True,
            'sources_deleted': True, 'standalone': str(executable),
            'runtime_inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                for name in ('nex_ffi.h', 'nex_ffi_host.h', 'nex_ffi.cpp', 'nex_ffi_types.h',
                             'nex_ffi_types.cpp', 'nex_files.cpp', 'nex_json.cpp')}}
        typed = directory / 'typed'
        typed.mkdir()
        for name in ('main.nex', 'producer.c', 'host.cpp'):
            shutil.copyfile(resources / 'examples/ffi' / name, typed / name)
        (typed / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        revision = cli('check', cwd=typed)['revision']
        contract = cli('ffi', '--symbol', 'ffi_example::contract', cwd=typed)
        contract_file = typed / 'signature.json'
        contract_file.write_text(json.dumps(contract))
        expected_typed = cli('eval', cwd=typed)['stdout']
        for profile in ('debug', 'release'):
            require(cli('run', '--profile', profile, cwd=typed)['stdout'] == expected_typed,
                    'typed C model native/reference output differs')
        cli('test', '--target', 'web', cwd=typed)
        typed_obj = typed / 'producer.o'
        typed_host = typed / 'host'
        run([driver, '-x', 'c', '-std=c11', '-I' + str(runtime), '-c', typed / 'producer.c', '-o', typed_obj])
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime), typed / 'host.cpp', typed_obj,
             runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp', '-o', typed_host])
        for name in ('main.nex', 'producer.c', 'host.cpp', 'producer.o'):
            (typed / name).unlink()
        require(cli('ffi', '--revision', revision, '--symbol', 'ffi_example::contract', cwd=typed) == contract,
                'archived C value contract changed after source deletion')
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-typed-foreign-resources')
            require(run([typed_host, contract_file]) == expected_typed,
                    'independent typed C/NEX model output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary']['typed_nominal'] = {
            'schema': contract['schema'], 'model_revision': revision,
            'contract_sha256': hashlib.sha256(contract_file.read_bytes()).hexdigest(),
            'checked_record_enum_result': True, 'source_deleted': True,
            'native_reference_typescript_model_agreement': True, 'standalone': str(typed_host)}
        loaded = directory / 'loaded'
        loaded.mkdir()
        bundle = loaded / 'bundle'
        bundle.mkdir()
        for name in ('producer.c', 'module.c', 'module_host.cpp', 'NOTICE'):
            shutil.copyfile(resources / 'examples/ffi' / name, loaded / name)
        canonical = json.dumps(contract, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        signature_pin = hashlib.sha256(canonical.encode()).hexdigest()
        module = bundle / 'module'
        run([driver, '-x', 'c', '-std=c11', '-shared', '-fPIC', '-fvisibility=hidden',
             '-I' + str(runtime), '-DNEX_EXAMPLE_SIGNATURE_SHA256="' + signature_pin + '"',
             loaded / 'producer.c', loaded / 'module.c', '-o', module])
        shutil.copyfile(loaded / 'NOTICE', bundle / 'NOTICE')
        machine = {'aarch64': 'arm64', 'arm64': 'arm64', 'x86_64': 'x86_64', 'AMD64': 'x86_64'}[platform.machine()]
        host_platform = ('macos' if platform.system() == 'Darwin' else 'linux') + '-' + machine
        manifest = {'schema': 'nex.foreign-bundle/1', 'platform': host_platform, 'entry': 'module',
            'files': [{'path': name, 'sha256': hashlib.sha256((bundle / name).read_bytes()).hexdigest()}
                      for name in ('module', 'NOTICE')],
            'exports': {'contract': signature_pin}, 'notices': ['NOTICE']}
        (bundle / 'manifest.json').write_text(json.dumps(manifest))
        manifest_pin = hashlib.sha256((bundle / 'manifest.json').read_bytes()).hexdigest()
        module_host = loaded / 'host'
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime),
             '-I' + report['doctor']['native_openssl_include'], loaded / 'module_host.cpp',
             runtime / 'nex_ffi_loader.cpp', runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp',
             report['doctor']['native_openssl_crypto'],
             *(['-ldl'] if platform.system() == 'Linux' else []), '-o', module_host])
        for name in ('producer.c', 'module.c', 'module_host.cpp', 'NOTICE'):
            (loaded / name).unlink()
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-module-resources')
            require(run([module_host, bundle, manifest_pin, contract_file]) == expected_typed,
                    'loaded module/NEX model output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary']['loaded_module'] = {
            'platform': host_platform, 'manifest_sha256': manifest_pin,
            'signature_sha256': signature_pin, 'c11_shared_module': True,
            'explicit_library_and_export_grant': True, 'source_deleted': True,
            'native_reference_typescript_model_agreement': True,
            'standalone': str(module_host), 'bundle': str(bundle),
            'runtime_inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                for name in ('nex_ffi_loader.cpp', 'nex_ffi_loader.h', 'nex_ffi_module.h', 'nex_resource.h')}}
        scoped_source = loaded / 'scoped_host.cpp'
        shutil.copyfile(resources / 'examples/ffi/scoped_host.cpp', scoped_source)
        host_file = loaded / 'host.json'
        binding_file = loaded / 'binding.json'
        host_file.write_text(json.dumps({'schema': 'nex.foreign-host/1', 'module_limit': 64,
            'libraries': {'example': {'directory': 'bundle', 'manifest_sha256': manifest_pin,
                                      'exports': ['contract']}}}))
        binding_file.write_text(json.dumps({'schema': 'nex.foreign-binding/1', 'library': 'example',
            'export': 'contract', 'manifest_sha256': manifest_pin, 'signature': contract}))
        scoped_host = loaded / 'scoped-host'
        run([driver, '-std=c++20', '-pthread', '-I' + str(runtime),
             '-I' + report['doctor']['native_openssl_include'], scoped_source,
             runtime / 'runtime.cpp', runtime / 'foreign_runtime.cpp', runtime / 'nex_foreign.cpp',
             runtime / 'nex_ffi_loader.cpp', runtime / 'nex_ffi.cpp', runtime / 'nex_ffi_types.cpp',
             runtime / 'nex_files.cpp', runtime / 'nex_json.cpp',
             report['doctor']['native_openssl_crypto'],
             *(['-ldl'] if platform.system() == 'Linux' else []), '-o', scoped_host])
        scoped_source.unlink()
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-scoped-foreign-resources')
            require(run([scoped_host, host_file, binding_file]) == expected_typed,
                    'scoped native value bridge/NEX model output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        report['evidence']['foreign_boundary']['scoped_native_bridge'] = {
            'source_support': False, 'host_schema': 'nex.foreign-host/1',
            'binding_schema': 'nex.foreign-binding/1', 'real_request_scope': True,
            'native_managed_handle_bridge': True, 'sources_deleted': True,
            'matches_nex_model': True, 'standalone': str(scoped_host),
            'host_file': str(host_file), 'binding_file': str(binding_file),
            'runtime_inputs': {name: hashlib.sha256((runtime / name).read_bytes()).hexdigest()
                for name in ('nex_foreign.cpp', 'nex_foreign.h', 'foreign_runtime.cpp',
                             'nex_foreign_abi.h', 'runtime.cpp', 'nex_host.h')}}
        source = directory / 'source'
        source.mkdir()
        source_file = source / 'main.nex'
        source_file.write_text((resources / 'examples/ffi/source.nex.in').read_text().replace('@MANIFEST_SHA256@', manifest_pin))
        (source / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source_revision = cli('check', cwd=source)['revision']
        require(cli('ffi', '--symbol', 'ffi_example::contract', cwd=source) == contract,
                'source declaration changed the value signature')
        require(cli('eval', '--foreign', host_file, cwd=source)['stdout'] == expected_typed,
                'source external interpreter output differs')
        for profile in ('debug', 'release'):
            require(cli('run', '--foreign', host_file, '--profile', profile, cwd=source)['stdout'] == expected_typed,
                    'source external native output differs')
        cli('test', '--foreign', host_file, cwd=source)
        cli('test', '--target', 'web', cwd=source)
        external = cli('build', '--profile', 'release', cwd=source)
        catalogue = cli('foreign', host_file, cwd=source)
        external_task = cli('task', source_file, '--kind', 'init', cwd=source)
        for check in external_task['checks']:
            if check['kind'] == 'test':
                check['foreign_hash'] = catalogue['hash']
        external_task_file = source / 'task.json'
        external_task_file.write_text(json.dumps(external_task))
        checked = cli('task', external_task_file, '--kind', 'check', '--foreign', host_file, cwd=source)
        accepted = cli('task', external_task_file, '--kind', 'run', '--task-hash', checked['task_hash'],
                       '--foreign', host_file, cwd=source)
        require(accepted['ok'] and accepted['foreign_catalogue']['hash'] == catalogue['hash'],
                'reviewed external task failed')
        source_file.unlink()
        external_task_file.unlink()
        require(cli('eval', '--revision', source_revision, '--foreign', host_file, cwd=source)['stdout'] == expected_typed,
                'source-deleted external interpreter replay differs')
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-source-foreign-resources')
            require(run([external['executable'], '--nex-foreign', host_file]) == expected_typed,
                    'standalone source external binary output differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = original
        replayed = cli('task', accepted['output'], '--kind', 'replay', '--foreign', host_file, cwd=source)
        require(replayed['ok'] and replayed['task_hash'] == accepted['task_hash'],
                'source-deleted trusted external task replay differs')
        report['evidence']['foreign_boundary']['source_external'] = {
            'source_support': True, 'language': report['doctor']['language'],
            'revision': source_revision, 'interpreter_debug_release_agreement': True,
            'server_tests': True, 'portable_web_test': True, 'sources_deleted': True,
            'standalone': external['executable'], 'host_file': str(host_file),
            'reviewed_task': {'hash': checked['task_hash'], 'foreign_hash': catalogue['hash'],
                'receipt': accepted['output'], 'replay': replayed['output'],
                'source_deleted_trusted_replay': True}}
        package_bundle = directory / 'package-input-bundle'
        shutil.copytree(bundle, package_bundle)
        package_host = directory / 'package-host.json'
        package_host.write_text(json.dumps({'schema': 'nex.foreign-host/1', 'module_limit': 64,
            'libraries': {'example': {'directory': str(package_bundle), 'manifest_sha256': manifest_pin,
                                     'exports': ['contract']}}}))
        notice_components = [{'name': 'acceptance-module', 'version': 'fixture',
            'url': 'https://example.invalid/nex-sdk-acceptance', 'roots': [str(package_bundle)],
            'license_files': [str(package_bundle / 'NOTICE')]}]
        package_flags = []
        if platform.system() == 'Linux':
            package_flags.append('--dpkg-notices')
        else:
            crypto = Path(report['doctor']['native_openssl_crypto']).resolve(strict=True)
            if sdk not in crypto.parents:
                # A development SDK can use the explicit vendor installation.
                # Preserve its complete license rather than inventing a notice.
                prefix = crypto.parent.parent
                license_file = next((prefix / name for name in ('LICENSE.txt', 'LICENSE')
                                     if (prefix / name).is_file()), None)
                require(license_file is not None, 'development Crypto installation needs its complete vendor license')
                notice_components.append({'name': 'acceptance-crypto', 'version': 'installed-vendor',
                    'url': 'https://openssl-library.org', 'roots': [str(prefix)],
                    'license_files': [str(license_file)]})
        package_notices = directory / 'package-notices.json'
        package_notices.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': notice_components}))
        package = directory / 'before-package'
        packaged = cli('package', '--revision', source_revision, '--foreign', package_host,
                       '--notices', package_notices, '--directory', package, *package_flags, cwd=source)
        manifest = json.loads((package / 'application.json').read_text())
        projection = manifest['foreign_projection']
        require(packaged['source_revision'] == source_revision and
                projection['source_revision'] == source_revision and
                projection['packaged_revision'] == packaged['revision'],
                'packaged foreign source projection differs from actual compiled revision')
        require(manifest['execution_verified'] is False, 'assembly must retain separate execution evidence')
        for name, record in manifest['files'].items():
            path = package / name
            if 'symlink' in record:
                require(path.is_symlink() and str(path.readlink()) == record['symlink'], 'packaged alias differs')
            else:
                require(hashlib.sha256(path.read_bytes()).hexdigest() == record['sha256'], 'packaged file hash differs')
        shutil.rmtree(package_bundle)
        package_host.unlink()
        package_notices.unlink()
        moved_package = directory / 'moved-package'
        package.rename(moved_package)
        saved_environment = dict(environment)
        try:
            environment.clear()
            environment.update(PATH='/usr/bin:/bin', NEX_RESOURCE_DIR=str(root / 'absent-packaged-resources'))
            require(run([moved_package / 'bin/app'], cwd=moved_package) == expected_typed,
                    'independent packaged nominal foreign application differs')
        finally:
            environment.clear()
            environment.update(saved_environment)
        report['evidence']['foreign_boundary']['source_external']['application_package'] = {
            'source_revision': source_revision, 'packaged_revision': packaged['revision'],
            'source_deleted': True, 'module_inputs_deleted': True, 'moved': True,
            'environment_without_sdk': True, 'exact_file_inventory': True,
            'nominal_contract_agreement': True, 'manifest': str(moved_package / 'application.json')}

    def binary_values():
        directory = root / 'binary-values'
        directory.mkdir()
        shutil.copyfile(resources / 'examples/bytes.nex', directory / 'main.nex')
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        revision = cli('check', cwd=directory)['revision']
        expected_binary = 'AP+AQQ==\nE_UTF8\n{"name":"raw","data":"AP+AQQ=="}\n'
        require(cli('eval', cwd=directory)['stdout'] == expected_binary, 'binary reference output differs')
        for profile in ('debug', 'release'):
            cli('test', '--profile', profile, cwd=directory)
            require(cli('run', '--profile', profile, cwd=directory)['stdout'] == expected_binary,
                    'binary native/reference output differs')
        cli('test', '--target', 'web', cwd=directory)
        built = cli('build', '--profile', 'release', cwd=directory)
        standalone = root / 'binary-standalone'
        shutil.copyfile(built['executable'], standalone); standalone.chmod(0o755)
        (directory / 'main.nex').unlink()
        require(cli('run', '--revision', revision, cwd=directory)['stdout'] == expected_binary,
                'binary archived revision failed after source deletion')
        unavailable = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([standalone]) == expected_binary, 'independent binary executable differs')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
        files = root / 'binary-files'; files.mkdir()
        (files / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        (files / 'main.nex').write_text('''module binary_file_handoff;
server fn main()->unit!{io,fs}{
 let value:bytes=unwrap(bytes([0,255,128,65]));
 assert(unwrap(file_write_bytes("octets.bin",value)));
 print(encode_base64(unwrap(file_read_bytes("octets.bin"))));
 print(error_code(file_read_text("octets.bin")));
}
''')
        data = root / 'binary data % 🧠'; data.mkdir()
        saved = {name: environment.get(name) for name in ('NEX_FILES_ROOT', 'NEX_FILES_WRITE')}
        try:
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='1')
            expected_file = 'AP+AQQ==\nE_UTF8\n'
            require(cli('eval', cwd=files)['stdout'] == expected_file, 'binary file reference differs')
            require(cli('run', cwd=files)['stdout'] == expected_file, 'binary file native differs')
            packaged = cli('package', '--directory', root / 'binary-file-application', cwd=files)
            manifest = json.loads(Path(packaged['manifest']).read_text())
            executable = Path(packaged['directory']) / 'bin/app'
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([executable]) == expected_file and
                    (data / 'octets.bin').read_bytes() == bytes([0, 255, 128, 65]),
                    'independent binary file application changed octets')
            require(hashlib.sha256(executable.read_bytes()).hexdigest() == manifest['files']['bin/app']['sha256'],
                    'binary file executable differs from package inventory')
        finally:
            environment['NEX_RESOURCE_DIR'] = unavailable
            for name, value in saved.items():
                if value is None: environment.pop(name, None)
                else: environment[name] = value
        evidence = {'revision': revision, 'native_profiles': ['debug', 'release'], 'typescript': True,
                    'source_deleted_replay': True, 'standalone_without_resources': str(standalone),
                    'binary_file_package': str(executable), 'live_watch': False}
        if args.live:
            debug = root / 'binary-debug'; debug.mkdir()
            (debug / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            source = debug / 'main.nex'
            source.write_text('''module binary_debug_handoff;
fn observe(data:bytes)->unit!{io}{
 print(data[1]); // binary-sdk-stop
}
fn main()->unit!{io}{observe(unwrap(bytes([0,255,128,65])));}
''')
            session = cli('debug', '--kind', 'nex-dap', cwd=debug)
            manifest = json.loads(Path(session['manifest']).read_text())
            projected = manifest['sources'][0]['projection']
            line = next(i+1 for i, text in enumerate(source.read_text().splitlines()) if '// binary-sdk-stop' in text)
            source.unlink()
            client = DAP(session['adapter_command'], debug, environment)
            try:
                client.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path', 'linesStartAt1': True})
                pending = client.send('launch', dict(session['launch'], disableASLR=False))
                client.event('initialized')
                client.request('setBreakpoints', {'source': {'path': projected}, 'breakpoints': [{'line': line}]})
                client.request('configurationDone'); client.response(pending)
                stopped = client.event('stopped')
                frame = client.request('stackTrace', {'threadId': stopped['threadId']})['stackFrames'][0]['id']
                value = client.request('evaluate', {'expression': 'data[1]', 'frameId': frame, 'context': 'watch'})
                require(value['nex']['value'] == '255', 'installed binary index watch differs')
                binary = client.request('evaluate', {'expression': 'data', 'frameId': frame, 'context': 'watch'})
                require(binary['type'] == 'bytes' and binary['indexedVariables'] == 4,
                        'installed byte watch lost its type or length')
                children = client.request('variables', {'variablesReference': binary['variablesReference'],
                    'start': 1, 'count': 2})['variables']
                require([(v['name'], v['value']) for v in children] == [('[1]', '255'), ('[2]', '128')],
                        'installed byte watch page differs')
                client.request('continue', {'threadId': stopped['threadId']})
                require(client.event('exited')['exitCode'] == 0, 'binary debuggee failed')
                evidence['live_watch'] = True
            finally:
                client.close()
        report['evidence']['binary_language'] = evidence

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
            streams = root / 'file-resources'
            streams.mkdir()
            shutil.copyfile(resources / 'examples/resources.nex', streams / 'main.nex')
            (streams / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': 'main.nex'}))
            environment.update(NEX_FILES_ROOT=str(data), NEX_FILES_WRITE='1')
            stream_revision = cli('check', cwd=streams)['revision']
            expected_stream = 'Я🧠\n<file>\n'
            require(cli('eval', cwd=streams)['stdout'] == expected_stream,
                    'installed file resource interpreter output differs')
            for profile in ('debug', 'release'):
                cli('test', '--profile', profile, cwd=streams)
                require(cli('run', '--profile', profile, cwd=streams)['stdout'] == expected_stream,
                        'installed file resource native/reference output differs')
            stream_package = root / 'resource-application'
            cli('package', '--directory', stream_package, cwd=streams)
            (streams / 'main.nex').unlink()
            require(cli('run', '--revision', stream_revision, cwd=streams)['stdout'] == expected_stream,
                    'file resource replay needs original source')
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-resources')
            require(run([stream_package / 'bin/app']) == expected_stream and
                    (data / 'nex-stream.bin').read_bytes() == 'Я🧠'.encode(),
                    'packaged streaming resource program needs compiler resources')
            report['evidence']['file_resources'] = {'revision': stream_revision,
                'language': report['doctor']['language'], 'native_profiles': ['debug', 'release'],
                'alias_close': True, 'seek_and_eof': True, 'scoped_cleanup_iterations': 80,
                'source_deleted_replay': True, 'standalone_without_resources': str(stream_package / 'bin/app')}
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
        binary = root / 'binary-browser'; binary.mkdir()
        shutil.copyfile(resources / 'examples/bytes-web.nex', binary / 'main.nex')
        (binary / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        cli('test', cwd=binary)
        binary_tests = cli('test', '--target', 'web', cwd=binary)
        require('bytes_web::transitions' in {t['name'] for t in binary_tests['tests']},
                'binary browser tests selected another project')
        generated_binary = root / 'generated-binary-web'
        cli('web', '--directory', generated_binary, cwd=binary)
        require(not any('BINARY_WEB_SERVER_ONLY_SENTINEL' in path.read_text()
                        for path in generated_binary.rglob('*.ts')), 'binary server code entered client')
        binary_evidence = {'native_tests': True, 'typescript_tests': True,
                           'generated': str(generated_binary), 'browser_build': args.browser}
        if args.browser:
            built = cli('build', '--target', 'web', '--profile', 'release', cwd=binary, timeout=300)
            dist = Path(built['dist'])
            require((dist / 'index.html').is_file() and any(dist.rglob('*.js')), 'missing binary browser assets')
            for path in dist.rglob('*'):
                if path.is_file():
                    require(b'BINARY_WEB_SERVER_ONLY_SENTINEL' not in path.read_bytes(),
                            'binary server code entered browser assets')
            binary_evidence['dist'] = str(dist)
        report['evidence']['binary_browser'] = binary_evidence
        report['evidence']['browser_build'] = args.browser

    try:
        for name, action in [('discovery', discover), ('new-project', new_project),
                ('reviewed-failure', baseline_failure), ('graph-repair-import', repair),
                ('backend-agreement', backend_agreement), ('binary-values', binary_values),
                ('foreign-boundary', foreign_boundary), ('text-files', text_files), ('profile', measured),
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
