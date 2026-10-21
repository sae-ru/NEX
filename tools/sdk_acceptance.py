#!/usr/bin/env python3
"""Exercise an installed NEX development chain, retaining reviewable evidence."""
import argparse
import base64
import hashlib
import json
import os
import platform
from pathlib import Path
import queue
import re
import shutil
import signal
import sqlite3
import ssl
import subprocess
import sys
import threading
import tempfile
import time
import urllib.error
import urllib.request


# Distribution validators import the contract from their matching SDK. Keep
# action registration checked against it so a missing phase cannot look green.
ACCEPTANCE_PHASES = (
    'discovery', 'editor-tools', 'new-project', 'reviewed-failure',
    'graph-repair-import', 'backend-agreement', 'graph-snapshot-recovery',
    'project-version-boundaries', 'frontend-diagnostics', 'graph-queries',
    'string-ranges', 'binary-values', 'native-indexed-pages', 'core-reports', 'wasm-compute', 'foreign-boundary', 'text-files', 'profile',
    'archive-debug-replay-export', 'scalar-proof', 'traits',
    'authenticated-storage', 'browser', 'project-build')


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def lldb_script_import(script):
    # LLDB parses command arguments, not JSON Unicode escape sequences. Keep
    # UTF-8 path characters literal while quoting spaces, quotes and slashes.
    return 'command script import ' + json.dumps(str(script), ensure_ascii=False)


def standalone_crypto_link(doctor):
    # Bundled Darwin libraries use @rpath install names; ELF bundles also need
    # their selected SDK directory at runtime. Pass linker operands separately
    # so commas, quotes, backslashes and UTF-8 stay literal.
    library = doctor['native_openssl_crypto']
    flags = [library]
    if platform.system() in ('Darwin', 'Linux'):
        flags += ['-Xlinker', '-rpath', '-Xlinker', str(Path(library).parent)]
    if platform.system() == 'Linux':
        flags.append('-ldl')
    return flags


def validate_completed_report(report):
    require(report.get('schema') == 'nex.sdk-acceptance/1' and report.get('ok') is True,
            'SDK acceptance did not complete successfully')
    phases = report.get('phases', [])
    require(tuple(phase.get('name') for phase in phases) == ACCEPTANCE_PHASES and
            all(phase.get('status') == 'passed' for phase in phases),
            'SDK acceptance differs from the complete workflow phase contract')
    commands = report.get('commands', [])
    # Expected rejections and runtime traps have nonzero exit codes. Their
    # recorded status comes from the acceptance action's expected outcome.
    require(bool(commands) and all(command.get('status') == 'passed' for command in commands),
            'SDK acceptance contains an incomplete or failed command')
    version = report.get('doctor', {}).get('version', '0.0.0').split('.')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 59, 0):
        core = report.get('evidence', {}).get('core_reports', {})
        require(core.get('capsule_helper_input_rejected') is True,
                'SDK acceptance lacks the installed core capsule helper control')
        if report.get('evidence', {}).get('live_debugger'):
            capsule = core.get('capsule_report', {})
            require(core.get('actual_capsule_read') is True and core.get('original_executable_absent') is True and
                    capsule.get('capsule', {}).get('inventory_checked') is True and
                    capsule.get('watch', {}).get('value') == 'Я🧠2' and not capsule.get('inferior_execution', True),
                    'SDK acceptance lacks actual source-deleted moved core capsule evidence')
    if len(version) == 3 and all(part.isascii() and part.isdigit() for part in version) and tuple(map(int, version)) >= (0, 60, 0):
        wasm = report.get('evidence', {}).get('wasm_compute', {})
        require(all(wasm.get(key) is True for key in ('exact_bigint', 'checked_overflow',
                'input_rejection', 'resource_stop', 'post_trap_recovery', 'module_integrity',
                'source_deleted', 'independent_runtime', 'cache_integrity', 'server_exclusion')),
                'SDK acceptance lacks complete installed scalar Wasm evidence')


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
    parser.add_argument('--package-notices', type=Path,
                        help='Additional operator nex.sdk-notices/1 provenance for private application/module runtime dependencies')
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
    # Source commands without a deeper manifest must remain inside this owned
    # evidence project, even when --output is below another NEX workspace.
    (root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.16','entry':'acceptance-scope.nex'})+'\n')
    (root/'acceptance-scope.nex').write_text('module acceptance_scope;fn main()->unit{}\n')
    logs = root / 'logs'
    logs.mkdir()
    environment = dict(os.environ, NEX_RESOURCE_DIR=str(resources))
    report = {'schema': 'nex.sdk-acceptance/1', 'ok': False, 'sdk': str(sdk),
              'output': str(root), 'required_phases': list(ACCEPTANCE_PHASES),
              'phases': [], 'commands': [], 'evidence': {}}
    started = time.monotonic()

    def notice_components(path):
        path = path.resolve(strict=True)
        document = json.loads(path.read_text())
        require(document.get('schema') == 'nex.sdk-notices/1', 'expected nex.sdk-notices/1')
        components = []
        for component in document['components']:
            item = dict(component)
            for field in ('roots', 'license_files'):
                item[field] = [str((path.parent / value).resolve(strict=True)) for value in item[field]]
            components.append(item)
        return components

    extra_notices = notice_components(args.package_notices) if args.package_notices else []
    if args.package_notices:
        report['package_notices'] = {'path': str(args.package_notices.resolve()),
            'sha256': hashlib.sha256(args.package_notices.read_bytes()).hexdigest()}

    def save():
        (root / 'report.json').write_text(json.dumps(report, indent=2) + '\n')

    def run(command, cwd=root, expected_success=True, timeout=180):
        command = list(map(str, command))
        packaging = (len(command) > 1 and
                     ((command[0] == str(compiler) and command[1] == 'package') or
                      command[1] == str(resources / 'tools/foreign_bundle.py')))
        if extra_notices and packaging:
            components = list(extra_notices)
            if '--notices' in command:
                index = command.index('--notices')
                components += notice_components(Path(command[index + 1]))
                del command[index:index + 2]
            directory = root / 'package-notices'; directory.mkdir(exist_ok=True)
            path = directory / ('%03d.json' % len(report['commands']))
            path.write_text(json.dumps({'schema': 'nex.sdk-notices/1', 'components': components}) + '\n')
            command += ['--notices', str(path)]
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
        require('snapshot_scoped_identity_reconciliation' in descriptor['graph_features'] and
                descriptor['graph_identity_policy'] == 'nex.graph-identity/1',
                'SDK lacks checked graph references')
        require('type' in descriptor.get('patch_entities', []), 'SDK lacks atomic source-type replacements')
        require('operation' in descriptor.get('patch_entities', []) and
                'exact_source_guard' in descriptor.get('patch_features', []),
                'SDK lacks exact source-operation replacements')
        require('optimistic_archived_restore' in descriptor.get('history_features', []) and
                descriptor.get('graph_database_schema') == 4,
                'SDK lacks checked change history and revision restore')
        require({'unicode_scalar_shape', 'bounded_text_range_captures', 'readonly_utf8_streaming_provider'} <=
                set(descriptor.get('string_debug_features', [])), 'SDK lacks bounded stopped-string ranges')
        require({'literal_source_search', 'paged_dependency_radius', 'independent_node_edge_pages'} <=
                set(descriptor.get('graph_query_features', [])), 'SDK lacks bounded archived graph queries')
        require({'captured_source_inputs', 'uncommitted_candidate_context', 'watch_frame_bound_context'} <=
                set(descriptor.get('frontend_diagnostic_features', [])), 'SDK lacks captured frontend error context')
        require({'declared_source_language_guard', 'root_version_preflight_before_store',
                 'reachable_library_language_guard', 'archived_manifest_independence'} <=
                set(descriptor.get('project_features', [])), 'SDK lacks explicit physical project version boundaries')
        require('consistent_sqlite_backup' in descriptor.get('snapshot_features', []) and
                descriptor.get('snapshot_external_artifacts_included') is False,
                'SDK lacks identity-preserving graph snapshot/recovery')
        require('manifest_checked_trap_mapping' in descriptor.get('diagnostic_features', []),
                'SDK lacks checked native runtime diagnostics')
        require({'native_checked_i64_ssa', 'cold_integer_failure_calls', 'cold_native_assertions'} <=
                set(descriptor.get('build_features', [])), 'SDK lacks checked native scalar fast paths')
        require('wire' in descriptor['generic_constraints'], 'SDK lacks checked wire constraints')
        require('bytes' in descriptor['types'] and
                'immutable_contiguous_octets' in descriptor['binary_features'],
                'SDK lacks checked binary values')
        require('fs' in descriptor['effects'] and
                'no_implicit_http_capability' in descriptor['file_features'] and
                descriptor['file_environment']['http_inherits_environment'] is False,
                'SDK lacks explicit filesystem capability policy')
        pack = json.loads((resources / 'llm/language-pack.json').read_text())
        require({'frame_module_identity_guard', 'core_recorded_mapping_image_guard'} <= set(descriptor['debug_features']) and
                descriptor['native_debug_image_binding'] == pack['native_debug_image_binding'],
                'SDK lacks frame-to-loaded-image identity binding')
        require(descriptor['native_core'] == pack['native_core'] and descriptor['native_core']['readonly'], 'SDK lacks checked read-only core reports')
        require(pack['language_version'] == doctor['language'] == descriptor['version'], 'language pack mismatch')
        inventory = {}
        for name in [*pack['documents'].values(), *pack['examples'].values()]:
            path = (resources / name).resolve()
            require(resources.resolve() in path.parents and path.is_file(), 'missing/escaped language resource: ' + name)
            path.read_text()  # A pack offered to another model must contain actual UTF-8 text.
            inventory[name] = hashlib.sha256(path.read_bytes()).hexdigest()
        for kind in ('prompt', 'language', 'grammar', 'protocol', 'web', 'server', 'api',
                     'debug', 'build', 'profile', 'verify', 'task', 'expression', 'operation', 'graph', 'history', 'snapshot', 'compatibility', 'frontend', 'query', 'string-debug', 'linux', 'match', 'function', 'files', 'bytes', 'resources', 'ffi', 'editor', 'lsp', 'core', 'wasm', 'project'):
            require(cli('guide', '--kind', kind)['text'], 'empty guide: ' + kind)
        report.update(doctor=doctor, compiler_sha256=hashlib.sha256(compiler.read_bytes()).hexdigest(),
                      version=doctor['version'], language=doctor['language'], host=doctor['host'],
                      resource_hashes=inventory)

    def editor_tools():
        node = os.environ.get('NEX_NODE') or shutil.which('node')
        require(node, 'editor acceptance requires the SDK Node development prerequisite')
        directory = resources / 'editor/vscode'
        names = ['package.json', 'package-lock.json', 'extension.js', 'session.js',
                 'language-configuration.json', 'README.md', 'test.js', 'language.js', 'lsp-client.js', 'language.test.js', 'lsp-acceptance.js']
        hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in names}
        package = json.loads((directory / 'package.json').read_text())
        require(package['name'] == 'nex-language-tools' and not package.get('dependencies'),
                'installed editor extension runtime dependencies differ')
        require(package['capabilities']['untrustedWorkspaces']['supported'] is False,
                'installed editor extension lost its workspace trust gate')
        # Node's test entry is a glob pattern. A literal backslash in a POSIX
        # SDK directory must stay in cwd rather than entering that pattern.
        run([node, '--test', 'test.js', 'language.test.js'], cwd=directory)
        evidence = {'extension_version': package['version'], 'installed_sources': hashes,
                    'focused_node_contracts': True, 'actual_ide_run': False,
                    'native_session_preparation': False}
        if args.live:
            project = root / 'editor-session'; project.mkdir()
            source = project / 'main with spaces.nex'
            source.write_text('module editor_sdk; fn main()->unit!{io} {print(42);}')
            (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
                'language': report['doctor']['language'], 'entry': source.name}))
            code = ('const {prepareSession}=require(process.argv[1]);'
                'prepareSession(JSON.parse(process.argv[2]),{compiler:process.argv[3]})'
                '.then(value=>process.stdout.write(JSON.stringify(value)))'
                '.catch(error=>{console.error(error.message);process.exitCode=1;});')
            prepared = json.loads(run([node, '-e', code, directory / 'session.js',
                json.dumps({'type': 'nex', 'request': 'launch', 'source': str(source), 'cwd': str(project)}),
                compiler], cwd=project))
            require(any(pair[1] == str(source) for pair in prepared['originalSourceMappings']),
                    'installed editor lost the exact original-file mapping')
            require(not prepared['frozenSourceFallbacks'] and Path(prepared['launch']['program']).is_file(),
                    'installed editor did not prepare its exact native build')
            evidence.update(native_session_preparation=True, revision=prepared['revision'],
                            build_key=prepared['buildKey'])
        report['evidence']['editor'] = evidence
        language_report = json.loads(run([sys.executable, resources / 'editor/lsp/acceptance.py',
            compiler, '--output', root / 'language-server']))
        require(language_report['ok'] and language_report['source_and_graph_unchanged'] and language_report.get('reference_checks') and language_report.get('type_reference_checks') and language_report.get('identifier_checks'),
                'installed compiler language-server acceptance failed')
        report['evidence']['language_server'] = language_report
        client_report = json.loads(run([node, directory / 'lsp-acceptance.js', compiler, root / 'editor-language-client']))
        require(client_report['ok'] and client_report['source_and_graph_unchanged'] and client_report.get('reference_checks') and client_report.get('type_reference_checks') and client_report.get('identifier_checks'), 'installed Node language client failed')
        report['evidence']['editor_language_client'] = client_report

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
        imported_ids = cli('identities', '--limit', '1000', cwd=imported)
        mappings = []
        offset = 0
        first_node = None
        while True:
            page = cli('identities', '--offset', str(offset), '--limit', '100', cwd=project)
            require(page['revision'] == state['after'], 'identity export selected another revision')
            if first_node is None:
                first_node = page['nodes'][0]
                source_namespace = page['namespace']
            packet = root / ('identities-'+str(offset)+'.json')
            packet.write_text(json.dumps(page))
            reconciled = cli('identities', '--kind', 'reconcile', '--manifest', packet,
                             '--expected-revision', state['after'], cwd=imported)
            mappings += reconciled['mappings']
            offset += len(page['nodes'])
            if not page['truncated']:
                break
        require(cli('identities', '--limit', '1000', cwd=imported) == imported_ids,
                'reconciliation rewrote destination identities')
        resolved = cli('identities', '--kind', 'resolve', '--origin', source_namespace,
                       '--from-revision', state['after'], '--node', first_node['id'], cwd=imported)
        require(resolved['target']['node']['context_hash'] == first_node['context_hash'] and
                cli('history', cwd=imported)['head'] == state['after'],
                'imported graph reference changed content or HEAD')
        report['evidence']['graph_reconciliation'] = {
            'source_namespace': source_namespace, 'target_namespace': imported_ids['namespace'],
            'mappings': len(mappings), 'resolved': resolved, 'destination_ids_unchanged': True}
        typed_project = root / 'atomic-type-patch'
        typed_project.mkdir()
        for name in ('main.nex', 'model.nex', 'nex.json', 'patch.json'):
            shutil.copy2(resources / 'examples/type-patches' / name, typed_project / name)
        typed_before = cli('check', cwd=typed_project)['revision']
        typed_ids = {n['symbol']: n['id'] for n in cli('declarations', '--entity', 'type', cwd=typed_project)['nodes']}
        typed_patch = json.loads((typed_project / 'patch.json').read_text())
        require(typed_patch['expected_revision'] == typed_before, 'type example source no longer matches its reviewed patch')
        partial_file = typed_project / 'partial.json'
        partial_file.write_text(json.dumps({'expected_revision': typed_before,
                                          'replacements': [typed_patch['replacements'][0]]}))
        cli('apply', '--patch', partial_file, cwd=typed_project, expected_success=False)
        require(cli('history', cwd=typed_project)['head'] == typed_before, 'invalid type-only edit changed HEAD')
        typed_after = cli('apply', '--patch', typed_project / 'patch.json', cwd=typed_project)['revision']
        require({n['symbol']: n['id'] for n in cli('declarations', '--entity', 'type', cwd=typed_project)['nodes']} == typed_ids,
                'atomic type replacement rewrote persistent type IDs')
        require(cli('context', '--entity', 'type', '--symbol', 'type_patch::model::Parcel', cwd=typed_project)['node']['editable'],
                'source type context is not editable')
        for name in ('main.nex', 'model.nex'):
            (typed_project / name).unlink()
        typed_expected = '43\nготово\n'
        require(cli('eval', '--revision', 'HEAD', cwd=typed_project)['stdout'] == typed_expected and
                cli('run', '--revision', 'HEAD', cwd=typed_project)['stdout'] == typed_expected,
                'source-deleted type replacement disagrees across reference/native')
        cli('test', '--revision', 'HEAD', cwd=typed_project)
        cli('test', '--revision', 'HEAD', '--target', 'web', cwd=typed_project)
        require(cli('eval', '--revision', typed_before, cwd=typed_project)['stdout'] == '42\n',
                'type replacement changed archived layout behavior')
        report['evidence']['atomic_type_patches'] = {
            'before_revision': typed_before, 'after_revision': typed_after,
            'persistent_type_ids': len(typed_ids), 'invalid_partial_edit_rejected': True,
            'source_deleted': True, 'native_reference_typescript': True}
        passed = cli('task', state['task'], '--kind', 'run', '--revision', state['after'],
                     '--task-hash', state['task_hash'], cwd=project, timeout=300)
        require(passed['status'] == 'passed' and passed['task_hash'] == state['task_hash'], 'reviewed task changed or failed')
        state['accepted'] = passed
        report['evidence'].update(after_revision=state['after'], passed_receipt=passed['output'], graph=str(exported_graph))

    def wasm_compute():
        workspace = root / 'wasm-project'
        workspace.mkdir()
        (workspace / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = workspace / 'main.nex'
        source.write_text((resources / 'examples/wasm/main.nex').read_text() + '''
pub fn bounded(n:i64)->i64{var i:i64=0;while i<n{i=i+1;}return i;}
server fn excluded()->str !{io}{print("SDK_WASM_SERVER_EXCLUDED_060");return "SDK_WASM_SERVER_EXCLUDED_060";}
''')
        cli('test', cwd=workspace)
        cli('test', '--target', 'web', cwd=workspace)
        arguments = ['build', '--target', 'wasm', '--entry', 'compute', '--profile', 'release']
        built = cli(*arguments, cwd=workspace)
        require(not built['cached'], 'cold Wasm build unexpectedly reused an artifact')
        require(cli(*arguments, cwd=workspace)['cached'], 'warm Wasm build did not reuse complete artifacts')
        module = Path(built['module'])
        original = module.read_bytes()
        module.write_bytes(original + b'changed')
        require(not cli(*arguments, cwd=workspace)['cached'] and module.read_bytes() == original,
                'changed Wasm module survived cache validation')
        bounded = cli('build', '--target', 'wasm', '--entry', 'bounded', '--profile', 'release', cwd=workspace)
        for label in ('module', 'wrapper', 'metadata', 'mlir', 'llvm'):
            require(b'SDK_WASM_SERVER_EXCLUDED_060' not in Path(built[label]).read_bytes(),
                    'server code entered a scalar Wasm artifact')
        source.unlink()
        exported = root / 'independent-wasm'
        materialized = cli(*arguments, '--revision', built['revision'], '-o', exported, cwd=workspace)
        require(Path(materialized['module']).read_bytes() == original, 'archived Wasm export differs')
        bounded_export = exported / 'bounded'
        bounded_export.mkdir()
        for name in ('module.wasm', 'module.mjs', 'module.json', 'THIRD_PARTY_NOTICES.txt'):
            shutil.copyfile(Path(bounded['directory']) / name, bounded_export / name)
        driver = exported / 'check.mjs'
        driver.write_text('''import fs from 'node:fs';
import {createNexWasm} from './module.mjs';
const raw=fs.readFileSync(new URL('./module.wasm',import.meta.url));
const module=await createNexWasm(raw);
if(module.call([9007199254740993n,1n])!==9007199254740993n)throw Error('integer precision differs');
let overflow;try{module.call([9223372036854775807n,2n])}catch(error){overflow=error;}
if(overflow?.code!=='E_OVERFLOW'||!overflow.site?.site)throw Error('checked overflow differs');
for(const args of [[1,2n],[9223372036854775808n,1n]]){
 let code;try{module.call(args)}catch(error){code=error.code;}if(code!=='E_WASM_INPUT')throw Error('input accepted');
}
if(module.call([6n,7n])!==42n)throw Error('failed post-trap recovery');
const mutated=raw.slice();mutated[mutated.length-1]^=1;
let rejected;try{await createNexWasm(mutated)}catch(error){rejected=error.code;}
if(rejected!=='E_WASM_MODULE')throw Error('changed module accepted');
const boundedFactory=(await import('./bounded/module.mjs')).createNexWasm;
const bounded=await boundedFactory(fs.readFileSync(new URL('./bounded/module.wasm',import.meta.url)));
let stopped;try{bounded.call([1000n],{budget:10})}catch(error){stopped=error.code;}
if(stopped!=='E_WASM_BUDGET'||bounded.call([3n])!==3n)throw Error('resource bound/recovery differs');
console.log(JSON.stringify({exact_bigint:true,checked_overflow:true,input_rejection:true,
 resource_stop:true,post_trap_recovery:true,module_integrity:true}));
''')
        previous = environment['NEX_RESOURCE_DIR']
        try:
            environment['NEX_RESOURCE_DIR'] = str(root / 'absent-wasm-resources')
            # Node treats literal backslashes in physical POSIX module paths as
            # separators. Execute byte-identical independent assets in an owned
            # ordinary /tmp path, including when the SDK work root has one.
            with tempfile.TemporaryDirectory(prefix='nex-sdk-wasm-', dir='/tmp') as temporary:
                independent = Path(temporary) / 'runtime'
                shutil.copytree(exported, independent)
                for path in exported.rglob('*'):
                    if path.is_file():
                        require(path.read_bytes() == (independent / path.relative_to(exported)).read_bytes(),
                                'independent Wasm runtime copy differs')
                observed = json.loads(run([os.environ.get('NEX_NODE') or shutil.which('node'), independent / 'check.mjs'], cwd=independent))
                require(not (independent / '.nex').exists(), 'independent Wasm runtime created a graph')
        finally:
            environment['NEX_RESOURCE_DIR'] = previous
        require(not source.exists() and not (exported / '.nex').exists(), 'standalone Wasm execution created source/graph state')
        observed.update(source_deleted=True, independent_runtime=True, cache_integrity=True, server_exclusion=True,
                        build=built, exported=materialized, bounded=bounded,
                        module_sha256=hashlib.sha256(original).hexdigest())
        report['evidence']['wasm_compute'] = observed

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
        operation_project = root / 'operation-patches'
        operation_project.mkdir()
        for name in ('main.nex', 'nex.json'):
            shutil.copy2(resources / 'examples/operation-patches' / name, operation_project / name)
        operation_before = cli('check', cwd=operation_project)['revision']
        page = cli('operations', '--symbol', 'operation_patch::adjust', cwd=operation_project)
        selected, = [n for n in page['nodes'] if n['kind'] == 'expression.integer'
                     and n['definition']['number'] == '1']
        context = cli('context', '--operation', selected['id'], cwd=operation_project)
        require(context['nodes'][0]['source_range']['editable'] and
                context['nodes'][0]['source_preview'] == '1', 'SDK operation context differs')
        operation_file = root / 'operation-edit.json'
        operation_file.write_text(json.dumps({'expected_revision': operation_before,
            'expected_source_hash': page['source_hash'],
            'replacements': [{'operation_id': selected['id'], 'source': '2 // isolated comment'}]}))
        (operation_project / 'main.nex').unlink()
        operation_after = cli('apply', '--patch', operation_file, cwd=operation_project)['revision']
        require(cli('context', '--operation', selected['id'], cwd=operation_project)['nodes'][0]['site'] != selected['site'],
                'SDK source-operation edit lost its local ID or retained its old site')
        require(cli('run', '--revision', operation_before, cwd=operation_project)['stdout'] == '41\n' and
                cli('eval', '--revision', operation_after, cwd=operation_project)['stdout'] == '42\n' and
                cli('run', '--revision', operation_after, cwd=operation_project)['stdout'] == '42\n',
                'SDK source-deleted operation patch disagrees across native/reference/history')
        cli('test', '--revision', operation_after, cwd=operation_project)
        cli('test', '--revision', operation_after, '--target', 'web', cwd=operation_project)
        require(cli('apply', '--patch', operation_file, cwd=operation_project,
                    expected_success=False)['code'] == 'E_CONFLICT', 'SDK accepted stale operation patch')
        restored = cli('restore', '--revision', operation_before, '--expected-revision', operation_after,
                       '--note', 'Return to retained original', '--actor', 'SDK scenario', cwd=operation_project)
        require(restored['changed'] and not restored['materialized'] and
                cli('run', '--revision', 'HEAD', cwd=operation_project)['stdout'] == '41\n',
                'SDK source-deleted restore did not recover the original')
        cli('restore', '--revision', operation_after, '--expected-revision', operation_before,
            '--note', 'Return to revised implementation', cwd=operation_project)
        require(cli('run', '--revision', 'HEAD', cwd=operation_project)['stdout'] == '42\n',
                'SDK restore lost the revised source')
        transitions = cli('changes', cwd=operation_project)
        require(transitions['total'] == 4 and transitions['changes'][0]['action'] == 'restore' and
                transitions['changes'][0]['previous_revision'] == operation_before and
                transitions['changes'][1]['previous_revision'] == operation_after and
                transitions['author_trust'] == 'declared', 'SDK change provenance differs')
        report['evidence']['change_history'] = {'transitions': 4,
            'namespace': transitions['namespace'], 'tip_hash': transitions['changes'][0]['hash'],
            'before': operation_before, 'after': operation_after, 'source_deleted_restore': True,
            'physical_sources_absent': not (operation_project / 'main.nex').exists(),
            'both_archives_preserved': True, 'declared_author_labels': True}
        report['evidence']['source_operation_patches'] = {'before': operation_before,
            'after': operation_after, 'local_operation_id': selected['id'],
            'source_deleted': True, 'native_reference_typescript': True,
            'stale_rejected': True, 'same_local_id_new_site': True}
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

        integer_project = root / 'native-integers'
        integer_project.mkdir()
        (integer_project / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        integer_source = integer_project / 'main.nex'
        shutil.copy2(resources / 'examples/native-arithmetic.nex', integer_source)
        integer_revision = cli('check', cwd=integer_project)['revision']
        cli('test', cwd=integer_project)
        cli('test', '--target', 'web', cwd=integer_project)
        cli('test', '--profile', 'release', cwd=integer_project)
        integer_source.unlink()
        cli('test', '--revision', integer_revision, cwd=integer_project)
        cli('test', '--revision', integer_revision, '--target', 'web', cwd=integer_project)
        report['evidence']['native_integer_lowering'] = {'revision': integer_revision,
            'source_example': 'examples/native-arithmetic.nex', 'sample_loop_iterations': 1000,
            'checked_boundaries': True, 'native_and_reference': True, 'typescript': True,
            'native_profiles': ['debug', 'release'], 'source_deleted': True}

        diagnostic_project = root / 'native-diagnostics'
        diagnostic_project.mkdir()
        (diagnostic_project / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        diagnostic_source = diagnostic_project / 'main.nex'
        diagnostic_source.write_text('module sdk_trap;fn divide(n:i64)->i64{return 42/n;}fn main()->unit!{io}{print("before");print(divide(0));}')
        checked = cli('check', cwd=diagnostic_project)
        expected_error = cli('eval', cwd=diagnostic_project, expected_success=False)
        for profile in ('debug', 'release'):
            failed = cli('run', '--profile', profile, cwd=diagnostic_project, expected_success=False)
            records = failed['native_diagnostics']['diagnostics']
            require(failed['exit_code'] == 70 and failed['stdout'] == 'before\n' and len(records) == 1,
                    'native trap process observation differs')
            record = records[0]
            require(record['status'] == 'mapped' and record['report']['code'] == 'E_DIV_ZERO' and
                    record['operation_id'] == expected_error['operation_id'] and
                    record['operation_site'] == expected_error['operation_site'],
                    'native/interpreter operation attribution differs')
        built = cli('build', '--profile', 'release', cwd=diagnostic_project)
        graph_file = root / 'native-diagnostic-graph.json'
        graph_file.write_text(json.dumps(cli('graph', cwd=diagnostic_project)))
        standalone = root / 'native-diagnostic-app'
        shutil.copy2(built['executable'], standalone)
        diagnostic_source.unlink()
        require(run([standalone], expected_success=False) == 'before\n' and report['commands'][-1]['exit_code'] == 70,
                'source-deleted standalone did not retain its native trap')
        diagnostic_log = Path(report['commands'][-1]['stderr'])
        restored = root / 'native-diagnostic-restored'
        restored.mkdir()
        (restored / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        cli('import', graph_file, cwd=restored)
        mapped = cli('diagnose', '--revision', checked['revision'], '--manifest', built['debug_manifest'],
                     '--log', diagnostic_log, cwd=restored)['diagnostics'][0]
        require(mapped['status'] == 'mapped' and mapped['operation_site'] == record['operation_site'] and
                mapped['operation_id'] != record['operation_id'] and not (restored / 'main.nex').exists(),
                'source-deleted imported graph did not resolve its own local operation ID')
        report['evidence']['native_diagnostics'] = {'revision': checked['revision'],
            'site': mapped['operation_site'], 'native_profiles': ['debug', 'release'],
            'native_interpreter_agreement': True, 'source_deleted': True,
            'standalone_without_sdk_lookup': str(standalone), 'new_store_local_ids': True,
            'manifest': built['debug_manifest']}

    def graph_snapshot_recovery():
        original = root / 'snapshot-original'
        original.mkdir()
        (original / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = original / 'main.nex'
        source.write_text('module sdk_snapshot;fn value()->i64{return 41;}'
            'fn main()->unit!{io}{print(value());}'
            'test fn retains_value()->unit{assert(value()>=41);}')
        first = cli('check', cwd=original)['revision']
        patch = original / 'patch.json'
        patch.write_text(json.dumps({'expected_revision': first, 'replacements': [
            {'name': 'value', 'source': 'fn value()->i64{return 42;}'}]}))
        second = cli('apply', '--patch', patch, cwd=original)['revision']
        graph = cli('graph', cwd=original)
        changes = cli('changes', cwd=original)
        source.unlink()
        def rows(project):
            with sqlite3.connect(project / '.nex/graph.db') as database:
                names = [name for name, in database.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
                return {name: sorted(database.execute('SELECT * FROM "' + name.replace('"', '""') + '"').fetchall(), key=repr)
                        for name in names}
        before = rows(original)
        archive = root / 'graph-snapshot'
        captured = cli('snapshot', '--directory', archive, cwd=original)
        require(rows(original) == before and captured['source_unchanged'], 'snapshot changed original graph rows')
        require(not (archive / 'graph.db-wal').exists() and not (archive / 'graph.db-shm').exists(),
                'snapshot depends on SQLite sidecar files')
        manifest = json.loads((archive / 'snapshot.json').read_text())
        digest = hashlib.sha256((archive / 'graph.db').read_bytes()).hexdigest()
        require(manifest['database']['sha256'] == captured['database_sha256'] == digest,
                'snapshot manifest differs from database bytes')
        shutil.rmtree(original)
        moved = root / 'moved-graph-snapshot'
        archive.rename(moved)
        recovered = root / 'snapshot-recovered'
        result = cli('recover', moved, '--directory', recovered)
        require(rows(recovered) == before and not result['materialized'] and
                result['namespace'] == changes['namespace'], 'recovery changed database rows or namespace')
        require(cli('recover', moved, '--directory', recovered, expected_success=False)['code'] == 'E_EXISTS' and
                rows(recovered) == before, 'existing recovered project was overwritten')
        require(cli('graph', cwd=recovered)['nodes'] == graph['nodes'] and
                cli('changes', cwd=recovered) == changes, 'recovery lost local IDs or change journal')
        require(cli('run', '--revision', first, cwd=recovered)['stdout'] == '41\n' and
                cli('eval', '--revision', second, cwd=recovered)['stdout'] == '42\n' and
                cli('run', '--revision', 'HEAD', cwd=recovered)['stdout'] == '42\n',
                'recovered native/reference archives disagree')
        cli('test', '--revision', 'HEAD', cwd=recovered)
        cli('test', '--revision', 'HEAD', '--target', 'web', cwd=recovered)
        require(not (recovered / 'main.nex').exists() and rows(recovered) == before,
                'archived execution materialized sources or changed retained graph rows')
        report['evidence']['graph_snapshot'] = {'before': first, 'head': second,
            'namespace': changes['namespace'], 'database_sha256': digest,
            'tables': len(before), 'all_rows_preserved': True, 'local_ids_preserved': True,
            'change_journal_preserved': True, 'original_project_deleted': True,
            'snapshot_moved': True, 'materialized': False, 'existing_target_rejected': True,
            'native_reference_typescript': True, 'external_artifacts_included': False}

    def project_version_boundaries():
        project = root / 'project-version-boundaries'
        project.mkdir()
        manifest = project / 'nex.json'
        source = project / 'main.nex'
        source.write_text('module sdk_version_boundary;fn main()->unit{}')
        config = {'schema': 'nex.project/1', 'language': '0.14', 'entry': 'main.nex'}
        manifest.write_text(json.dumps(config))
        require(cli('check', cwd=project, expected_success=False)['code'] == 'E_LANGUAGE_VERSION' and
                not (project / '.nex').exists(), 'old root language created/upgraded graph state')
        library = project / 'library'
        library.mkdir()
        library_manifest = library / 'nex.json'
        library_manifest.write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.14'}))
        (library / 'value.nex').write_text('module sdk_version_library;pub fn answer()->i64{return 42;}')
        source.write_text('module sdk_version_boundary;import "numbers/value.nex" as n;'
            'fn main()->unit!{io}{print(n::answer());}test fn accepted()->unit{assert(n::answer()==42);}')
        config.update(language=report['doctor']['language'], libraries={'numbers': './library'})
        manifest.write_text(json.dumps(config))
        require(cli('check', cwd=project, expected_success=False)['code'] == 'E_LANGUAGE_VERSION' and
                cli('history', cwd=project)['head'] == '', 'old library was silently adopted')
        library_manifest.write_text(json.dumps({'schema': 'nex.project/1', 'language': report['doctor']['language']}))
        revision = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        config['language'] = '0.14'
        manifest.write_text(json.dumps(config))
        require(cli('check', cwd=project, expected_success=False)['code'] == 'E_LANGUAGE_VERSION',
                'stale physical root declaration was ignored')
        require(cli('eval', '--revision', revision, cwd=project)['stdout'] == '42\n' and
                cli('run', '--revision', 'HEAD', cwd=project)['stdout'] == '42\n' and
                cli('changes', cwd=project) == changes, 'archived execution used stale physical metadata')
        exported = root / 'current-version-export'
        cli('export', '--revision', revision, '--directory', exported, cwd=project)
        require(json.loads((exported / 'nex.json').read_text())['language'] == report['doctor']['language'] and
                cli('check', cwd=exported)['revision'] == revision, 'archive export did not create current source projection')
        report['evidence']['project_versions'] = {'revision': revision,
            'old_root_rejected_before_store': True, 'old_reachable_library_rejected': True,
            'current_library_accepted': True, 'stale_physical_manifest_rejected': True,
            'archived_native_reference_execution': True, 'journal_preserved': True,
            'current_export_checked': True}

    def frontend_diagnostics():
        project = root / 'frontend-error-context'
        project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = project / 'main.nex'
        original = ('module sdk_frontend;fn value()->i64{return 41;}'
            'fn main()->unit!{io}{print(value());}test fn retained()->unit{assert(value()>=41);}')
        source.write_text(original)
        before = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        patch = project / 'candidate.json'
        request = {'expected_revision': before, 'replacements': [
            {'name': 'value', 'source': 'fn value()->i64{return "bad";}'}]}
        patch.write_text(json.dumps(request))
        error = cli('apply', '--patch', patch, cwd=project, expected_success=False)
        context = error.get('frontend', {})
        require(error['code'] == 'E_TYPE' and context.get('schema') == 'nex.frontend-diagnostic/1' and
                context.get('phase') == 'check' and context.get('input_kind') == 'project' and
                context.get('source_inputs_complete') is True and
                'return "bad"' in context['preview']['data'], 'failed candidate context refers to wrong input')
        require(source.read_text() == original and cli('changes', cwd=project) == changes and
                'revision' not in error and 'operation_id' not in error,
                'failed candidate changed source/history or fabricated graph identity')
        require(cli('apply', '--patch', patch, cwd=project, expected_success=False)['frontend']['id'] == context['id'],
                'identical failed input changed diagnostic identity')
        session = cli('debug', cwd=project)
        identity = json.loads(Path(session['manifest']).read_text())
        frame = {'schema': 'nex.debug-frame/1', 'language': report['doctor']['language'],
            'revision': identity['revision'], 'build_key': identity['build_key'],
            'function': 'sdk_frontend::value',
            'stop': {'process_id': '1', 'thread_id': '2', 'frame_id': 0, 'stop_id': '1'},
            'bindings': [], 'truncated': False}
        frame_file = project / 'frame.json'
        frame_file.write_text(json.dumps(frame))
        watched = cli('inspect', frame_file, '--manifest', session['manifest'], '--expression', '1 + true',
                      cwd=project, expected_success=False)
        require(watched['frontend']['input_kind'] == 'expression' and
                watched['frontend']['phase'] == 'check' and
                watched['frontend']['watch']['revision'] == before and
                watched['frontend']['watch']['build_key'] == identity['build_key'],
                'static watch error lost its source/frame identity')
        raw = b'module bad;\n\xff'
        source.write_bytes(raw)
        invalid = cli('check', cwd=project, expected_success=False)
        require(invalid['code'] == 'E_UTF8' and invalid['frontend']['source']['utf8'] is False and
                invalid['frontend']['preview']['encoding'] == 'base64' and
                base64.b64decode(invalid['frontend']['preview']['data'], validate=True) == raw and
                cli('changes', cwd=project) == changes, 'invalid UTF-8 source context is lossy or mutates history')
        source.write_text(original)
        request['replacements'][0]['source'] = 'fn value()->i64{return 42;}'
        patch.write_text(json.dumps(request))
        after = cli('apply', '--patch', patch, cwd=project)['revision']
        require(cli('run', '--revision', after, cwd=project)['stdout'] == '42\n' and source.read_text() == original,
                'repaired candidate failed archived execution or overwrote physical source')
        report['evidence']['frontend_diagnostics'] = {'before': before, 'after': after,
            'diagnostic_id': context['id'], 'candidate_source_hash': context['source']['hash'],
            'source_inputs_hash': context['source_inputs_hash'], 'captured_uncommitted_candidate': True,
            'physical_source_preserved': True, 'failed_transition_absent': True,
            'repeatable_error_identity': True, 'invalid_utf8_lossless': True,
            'static_watch_supplied_frame': True, 'watch_frame_hash': watched['frontend']['watch']['frame_hash'],
            'repaired_archived_native_execution': True}

    def graph_queries():
        project = root / 'graph-query-workflow'
        project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = project / 'main.nex'
        original = ('module sdk_query;fn leaf()->i64{return 40;}'
            'fn middle()->i64{return leaf()+2;}fn main()->unit!{io}{print(middle());}')
        source.write_text(original)
        revision = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        found = cli('search', '--query', 'leaf', '--field', 'symbol', cwd=project)
        require(found['revision'] == revision and len(found['nodes']) == 1 and
                found['nodes'][0]['symbol'] == 'sdk_query::leaf', 'query did not discover exact checked declaration')
        graph = cli('subgraph', '--symbol', 'main', '--depth', '2', cwd=project)
        require({n['symbol'] for n in graph['nodes']} ==
                {'sdk_query::main', 'sdk_query::middle', 'sdk_query::leaf'} and
                graph['edge_page']['total'] == 2 and graph['depth_limited'] is False,
                'query dependency radius differs from the checked program')
        reverse = cli('subgraph', '--symbol', 'leaf', '--direction', 'dependents', '--depth', '2', cwd=project)
        require('sdk_query::main' in {n['symbol'] for n in reverse['nodes']} and
                any(e['source']['symbol'] == 'sdk_query::middle' and
                    e['target']['symbol'] == 'sdk_query::leaf' for e in reverse['edges']),
                'reverse query changed edge direction or lost incoming references')
        page = cli('search', '--query', '::', '--field', 'symbol', '--limit', '1', cwd=project)
        seen = list(page['nodes'])
        identity = page['query_hash']
        while page['page']['next_offset'] is not None:
            page = cli('search', '--query', '::', '--field', 'symbol', '--limit', '1',
                '--offset', str(page['page']['next_offset']), '--revision', revision, cwd=project)
            require(page['query_hash'] == identity, 'query pages mixed selection identities')
            seen.extend(page['nodes'])
        require(len(seen) == 3 and len({n['id'] for n in seen}) == 3, 'query cursor lost or duplicated declarations')
        context = cli('context', '--symbol', found['nodes'][0]['symbol'], '--revision', revision, cwd=project)
        require('return 40' in context['source'], 'query followup read another declaration')
        source.unlink()
        (project / 'nex.json').write_text(json.dumps({'language': '0.14', 'entry': 'main.nex'}))
        require(cli('search', '--query', 'leaf', '--field', 'symbol', '--revision', revision, cwd=project) == found and
                cli('subgraph', '--symbol', 'main', '--depth', '2', '--revision', revision, cwd=project) == graph and
                cli('changes', cwd=project) == changes, 'query depended on physical source or changed graph history')
        patch = project / 'discovered-repair.json'
        patch.write_text(json.dumps({'expected_revision': revision, 'expected_source_hash': found['source_hash'],
            'replacements': [{'name': found['nodes'][0]['symbol'], 'source': 'fn leaf()->i64{return 41;}'}]}))
        after = cli('apply', '--patch', patch, cwd=project)['revision']
        require(cli('eval', '--revision', after, cwd=project)['stdout'] == '43\n' and
                cli('run', '--revision', after, cwd=project)['stdout'] == '43\n' and not source.exists(),
                'discovered guarded repair failed archived native/reference execution')
        report['evidence']['graph_queries'] = {'before': revision, 'after': after,
            'namespace': found['namespace'], 'node_id': found['nodes'][0]['id'],
            'search_query_hash': found['query_hash'], 'subgraph_query_hash': graph['query_hash'],
            'exact_archived_source_hash': found['source_hash'], 'source_deleted_lookup': True,
            'stale_physical_metadata_ignored': True, 'incoming_edges_checked': True,
            'stable_complete_query_pages': True, 'queries_preserve_history': True,
            'guarded_repair_from_discovery': True, 'native_reference_after_repair': True}

    def traits():
        require({'associated_value_types','constructor_kinds','static_dispatch'} <= set(cli('describe').get('trait_features',[])),'SDK lacks source trait capabilities')
        project = root / 'trait-workflow'; project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':'main.nex'}))
        for filename, expected in [('main.nex','🧠\n'),('mapping.nex','[2,3]\n')]:
            source = project / filename
            source.write_text((resources / 'examples/traits' / filename).read_text())
            require(cli('eval',source,cwd=project)['stdout']==expected,'trait reference result differs')
            require(cli('run',source,cwd=project)['stdout']==expected,'trait native result differs')
            cli('test',source,cwd=project);cli('test',source,'--target','web',cwd=project)
        source = project / 'main.nex'
        source.write_text((resources / 'examples/traits/watch.nex').read_text())
        revision = cli('check',cwd=project)['revision'];changes=cli('changes',cwd=project)
        session = cli('debug',cwd=project);identity=json.loads(Path(session['manifest']).read_text())
        frame={'schema':'nex.debug-frame/1','language':report['doctor']['language'],
            'revision':revision,'build_key':identity['build_key'],'function':'trait_watch::observe<list>',
            'stop':{'process_id':'1','thread_id':'2','frame_id':0,'stop_id':'1'},
            'bindings':[{'name':'value','type':'list<i64>','value':['41']}],'truncated':False}
        framefile=project/'supplied-frame.json';framefile.write_text(json.dumps(frame))
        expression='Mapper<F>::map<i64,i64>(value,increase)'
        require(cli('inspect',framefile,'--manifest',session['manifest'],'--expression',expression,cwd=project)['value']==['42'],'trait constructor watch failed')
        live=None
        if args.live:
            projected=identity['sources'][0]['projection']
            line=next(i+1 for i,text in enumerate(source.read_text().splitlines()) if '// TRAIT_STOP' in text)
            script,recording=project/'record_trait_frame.py',project/'native-recording.json'
            script.write_text('''import json,lldb
def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  frame=process.GetSelectedThread().GetSelectedFrame();stop=process.GetStopID();handle=frame.FindVariable('value').GetValueAsUnsigned()
  values={'value':command('nex-eval Mapper<F>::map<i64,i64>(value,increase)'),
   'identity':command('nex-eval identity<F<i64>>(value)'),
   'snapshot':command('nex-frame Mapper<F>::map<i64,i64>(value,increase)')}
  assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
  assert frame.FindVariable('value').GetValueAsUnsigned()==handle
  values['unchanged_stop_and_handle']=True
  with open(RECORDING,'w') as output:json.dump(values,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE',repr(projected)).replace('LINE',str(line)).replace('RECORDING',repr(str(recording))))
            run([compiler,'debug','--revision',revision,'--','--no-lldbinit','--batch','-o',
                 lldb_script_import(script)],cwd=project,timeout=180)
            require(recording.is_file(),'live constructor trait frame was not recorded')
            live=json.loads(recording.read_text());require(live['value']['value']==['42'] and live['identity']['value']==['41'] and live['unchanged_stop_and_handle'],'live constructor trait watch differs or changed stop')
            framefile=project/'native-frame.json';framefile.write_text(json.dumps(live['snapshot']))
        source.unlink()
        require(cli('inspect',framefile,'--manifest',session['manifest'],'--expression',expression,cwd=project)['value']==['42'],'source-deleted trait frame replay failed')
        require(cli('changes',cwd=project)==changes,'trait watch changed graph history')
        legacy=project/'legacy';legacy.mkdir();(legacy/'.nex').mkdir()
        (legacy/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.15','entry':'main.nex'}))
        metadata=json.loads((resources/'examples/traits/legacy-0.15.json').read_text());sql=(resources/'examples/traits/legacy-0.15.sql').read_bytes()
        require(hashlib.sha256(sql).hexdigest()==metadata['sql_sha256'],'historical trait fixture hash differs')
        database=legacy/'.nex/graph.db'
        with sqlite3.connect(database) as db:db.executescript(sql.decode())
        def rows():
            with sqlite3.connect(database) as db:
                names=[name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
                return {name:set(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall()) for name in names}
        before=rows();migrated=cli('migrate','--revision',metadata['revision'],cwd=legacy)
        require(migrated['revision']!=metadata['revision'],'migration reused the old language identity')
        after=rows()
        require(all(old<=after[name] for name,old in before.items() if name!='head'),'migration rewrote historical rows')
        require(cli('eval','--revision','HEAD',cwd=legacy)['stdout']==metadata['stdout'],'migrated contextual names changed meaning')
        api_project=project/'api-models'
        shutil.copytree(resources/'examples/traits/api',api_project)
        cli('test',cwd=api_project)
        generated=cli('api','--directory',api_project/'generated',cwd=api_project)
        client=Path(generated['client_entry']).parent
        consumer=client/'consumer.nex';shutil.copyfile(api_project/'client.nex',consumer)
        for path in client.rglob('*.nex'):
            require('NEX_SERVER_TRAIT_EXAMPLE_SENTINEL' not in path.read_text(),
                    'server trait body entered generated client')
        client_native=cli('test',consumer,cwd=client)
        client_web=cli('test',consumer,'--target','web',cwd=client)
        required_test='traits::api::consumer::values'
        require(required_test in {test['name'] for test in client_native['tests']} and
                required_test in {test['name'] for test in client_web['tests']},
                'generated trait API consumer was not tested')
        server_build=cli('build',generated['server_entry'],'--target','server',cwd=api_project,timeout=180)
        report['evidence']['traits']={'revision':revision,'build_key':identity['build_key'],
            'native_typescript_reference':True,'source_deleted_watch_replay':True,
            'live_constructor_trait_frame':bool(live),'unchanged_stop_and_handle':bool(live),
            'genuine015_fixture':True,'old_revision':metadata['revision'],'migrated_revision':migrated['revision'],
            'old_non_head_rows_retained':True,
            'api_models':{'generated_revision':generated['revision'],'native_typescript_consumer':True,
                'real_client_shared_trait_method':True,'excluded_server_trait_body':True,
                'server_native_build':server_build['executable']}}

    def string_ranges():
        project = root / 'string-range-workflow'
        project.mkdir()
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1',
            'language': report['doctor']['language'], 'entry': 'main.nex'}))
        source = project / 'main.nex'
        source.write_text((resources / 'examples/debugging/strings.nex').read_text())
        revision = cli('check', cwd=project)['revision']
        changes = cli('changes', cwd=project)
        session = cli('debug', cwd=project)
        identity = json.loads(Path(session['manifest']).read_text())
        frame = {'schema': 'nex.debug-frame/2', 'language': report['doctor']['language'],
            'revision': revision, 'build_key': identity['build_key'], 'function': 'string_debug::observe',
            'stop': {'process_id': '1', 'thread_id': '2', 'frame_id': 0, 'stop_id': '1'},
            'bindings': [{'name': 'text', 'type': 'str', 'unavailable': 'whole string not captured'}],
            'truncated': False, 'captures': [
                {'binding': 'text', 'path': [], 'kind': 'shape', 'value': {'length': '2097152'}},
                {'binding': 'text', 'path': [], 'kind': 'text_range', 'start': '2097148', 'count': '4',
                 'value': 'A🌍\u0000λ'}]}
        # The first frame is supplied data; an optional live recording below has
        # separately verified process/stop identity and actual memory reads.
        frame['captures'][-1]['value'] = 'A🌍' + chr(0) + 'λ'
        framefile = project / 'supplied-frame.json'
        framefile.write_text(json.dumps(frame))
        length = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'len(text)', cwd=project)
        window = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'slice(text,len(text)-4,4)', cwd=project)
        last = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'text[len(text)-1]', cwd=project)
        require(length['value'] == '2097152' and window['value'] == 'A🌍' + chr(0) + 'λ' and last['value'] == 'λ',
                'supplied string windows lost Unicode scalar semantics or contained-range reuse')
        demand = cli('inspect', framefile, '--manifest', session['manifest'], '--expression', 'text[0]', '--kind', 'demand', cwd=project)
        require(demand['request']['kind'] == 'text_range' and demand['request']['start'] == '0' and
                demand['request']['count'] == '1', 'missing string range became a fabricated whole/empty value')
        live = None
        if args.live:
            projected = identity['sources'][0]['projection']
            line = next(i+1 for i, text in enumerate(source.read_text().splitlines()) if '// STRING_STOP' in text)
            script, recording = project / 'record_string_range.py', project / 'native-recording.json'
            script.write_text('''import json,lldb

def __lldb_init_module(debugger,_):
 debugger.SetAsync(False);debugger.HandleCommand('settings set target.disable-aslr false')
 target=debugger.GetSelectedTarget();target.BreakpointCreateByLocation(SOURCE,LINE)
 process=target.LaunchSimple(None,None,None)
 def command(text):
  result=lldb.SBCommandReturnObject();debugger.GetCommandInterpreter().HandleCommand(text,result)
  assert result.Succeeded(),(text,result.GetOutput(),result.GetError())
  return json.loads(result.GetOutput())
 try:
  assert process.GetState()==lldb.eStateStopped
  stop=process.GetStopID();handle=process.GetSelectedThread().GetSelectedFrame().FindVariable('text').GetValueAsUnsigned()
  values={'length':command('nex-eval len(text)'), 'range':command('nex-eval slice(text,len(text)-4,4)'),
   'snapshot':command('nex-frame slice(text,len(text)-4,4)')}
  assert process.GetState()==lldb.eStateStopped and process.GetStopID()==stop
  assert process.GetSelectedThread().GetSelectedFrame().FindVariable('text').GetValueAsUnsigned()==handle
  values['unchanged_stop_and_handle']=True
  with open(RECORDING,'w') as output:json.dump(values,output)
  process.Continue();assert process.GetState()==lldb.eStateExited and process.GetExitStatus()==0
 finally:
  if process.GetState() not in (lldb.eStateExited,lldb.eStateInvalid):process.Kill()
'''.replace('SOURCE', repr(projected)).replace('LINE', str(line)).replace('RECORDING', repr(str(recording))))
            run([compiler, 'debug', '--revision', revision, '--', '--no-lldbinit', '--batch', '-o',
                 lldb_script_import(script)], cwd=project, timeout=180)
            require(recording.is_file(), 'live string provider did not retain a recording')
            live = json.loads(recording.read_text())
            require(live['length']['value'] == '2097152' and live['range']['value'] == 'A🌍' + chr(0) + 'λ' and
                    live['unchanged_stop_and_handle'] is True and
                    any(c['kind'] == 'text_range' for c in live['snapshot']['captures']),
                    'live string scan/range changed the stop or returned another payload')
            (project / 'native-frame.json').write_text(json.dumps(live['snapshot']))
        source.unlink()
        replay_file = project / 'native-frame.json' if live else framefile
        replay = cli('inspect', replay_file, '--manifest', session['manifest'], '--expression', 'text[len(text)-1]', cwd=project)
        require(replay['value'] == 'λ' and cli('changes', cwd=project) == changes,
                'string snapshot replay depended on physical source or changed graph history')
        report['evidence']['string_ranges'] = {'revision': revision, 'build_key': identity['build_key'],
            'supplied_frame_scalar_length': length['value'], 'contained_range_replay': True,
            'missing_range_is_explicit_demand': True, 'physical_source_deleted': True, 'history_preserved': True,
            'live_native_streaming': bool(live), 'live_unchanged_stop_and_handle': bool(live),
            'native_utf8_bytes': 4194304 if live else None,
            'native_snapshot': str(replay_file) if live else None,
            'supplied_frame': str(framefile), 'replayed_stop': replay['stop']}

    def core_reports():
        directory = root / 'core-reports'
        directory.mkdir()
        source = directory / 'main.nex'
        source.write_text('''module sdk_core;
fn observe(value:i64,text:str,items:list<i64>)->unit !{io}{
 let answer:i64=value+items[1];
 print(answer);
}
fn main()->unit !{io}{observe(40,"Я🧠",[1,2,3]);}
''')
        (directory / 'nex.json').write_text(json.dumps({'language': report['doctor']['language'], 'entry': 'main.nex'}))
        session = cli('debug', '--kind', 'nex-dap', cwd=directory)
        core = directory / 'process.core'
        core.write_bytes(b'x')
        rejected = cli('core', core, '--manifest', session['manifest'],
                       cwd=directory, expected_success=False)
        require(rejected['code'] == 'E_CORE_INPUT', 'core reader accepted a truncated core')
        evidence = {'retained_build': session['manifest'], 'truncated_core_rejected': True,
                    'actual_core_read': False, 'actual_capsule_read': False}
        malformed = directory / 'invalid-capsule'
        malformed.mkdir()
        (malformed / 'capsule.json').write_text('{}')
        rejected = cli('core', '--capsule', malformed, cwd=directory, expected_success=False)
        require(rejected['code'] == 'E_CORE_CAPSULE', 'installed capsule helper accepted an invalid receipt')
        evidence['capsule_helper_input_rejected'] = True
        if args.live:
            core.unlink()
            captured = run([compiler, 'debug', '--', '--no-lldbinit', '--batch',
                '-o', 'settings set target.disable-aslr false',
                '-o', 'breakpoint set --file source.nex --line 4', '-o', 'run',
                '-o', 'process save-core --style modified-memory ' + json.dumps(str(core), ensure_ascii=False),
                '-o', 'continue'], cwd=directory, timeout=90)
            require('exited with status = 0' in captured and core.is_file() and core.stat().st_size < 16*1024*1024,
                    'native core fixture did not stop/save/complete')
            digest = hashlib.sha256(core.read_bytes()).hexdigest()
            source.unlink()
            graph = directory / '.nex/graph.db'
            graph_before = graph.read_bytes()
            observed = cli('core', core, '--manifest', session['manifest'],
                           '--expression', 'text + str(items[1])', cwd=directory, timeout=120)
            require(observed['schema'] == 'nex.core-report/1' and observed['ok'] and
                    observed['watch']['value'] == 'Я🧠2' and observed['core']['sha256'] == digest and
                    observed['core']['unchanged'] and observed['stop_unchanged'] and
                    observed['build_completion_checked'] and not observed['inferior_execution'] and
                    observed['revision'] == session['revision'] and
                    observed['executable']['uuid'] == observed['frames'][observed['selected_frame']]['module_uuid'],
                    'read-only core report differs from the retained program')
            require(graph.read_bytes() == graph_before and not source.exists() and
                    hashlib.sha256(core.read_bytes()).hexdigest() == digest,
                    'core inspection changed source/graph/core bytes')
            evidence.update(actual_core_read=True, source_deleted=True, graph_unchanged=True,
                            exact_watch=observed['watch']['value'], report=observed)
            capsule = directory / 'capsule'
            exported = cli('core', core, '--manifest', session['manifest'], '--export', capsule,
                           '--expression', 'text + str(items[1])', cwd=directory, timeout=180)
            require(exported['schema'] == 'nex.core-capsule-export/1' and exported['read_after_export'],
                    'installed SDK did not validate a newly exported core capsule')
            original_program = Path(session['launch']['program'])
            original_program.parent.rename(directory / 'retained-original-build')
            moved = directory / 'moved capsule "quoted" \\ % `data` 🧠'
            capsule.rename(moved)
            require(not original_program.exists(), 'original core executable path still exists')
            capsule_report = cli('core', '--capsule', moved, '--expression', 'text + str(items[1])',
                                 cwd=directory, timeout=120)
            require(capsule_report['capsule']['inventory_checked'] and capsule_report['watch']['value'] == 'Я🧠2' and
                    capsule_report['revision'] == session['revision'] and capsule_report['core']['sha256'] == digest and
                    capsule_report['stop_unchanged'] and not capsule_report['inferior_execution'] and
                    graph.read_bytes() == graph_before and not source.exists(),
                    'moved core capsule lost its original values/build/graph identity')
            evidence.update(actual_capsule_read=True, original_executable_absent=True,
                            capsule_export=exported, capsule_report=capsule_report)
        report['evidence']['core_reports'] = evidence

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
             *standalone_crypto_link(report['doctor']), '-o', module_host])
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
             *standalone_crypto_link(report['doctor']), '-o', scoped_host])
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

    def native_pages():
        descriptor=cli('describe')
        require('paged_native_indexed_roots' in descriptor['debug_features'] and
                descriptor['native_debug_pages']['page_items']==1000,
                'SDK lacks bounded native indexed pages')
        directory=root/'native-indexed-pages';directory.mkdir()
        source=directory/'main.nex'
        source.write_bytes((resources/'examples/debugging/pages.nex').read_bytes())
        (directory/'nex.json').write_text(json.dumps({'schema':'nex.project/1',
            'language':report['doctor']['language'],'entry':source.name}))
        session=cli('debug','--kind','nex-dap',cwd=directory)
        evidence={'native_descriptor':True,'live_dap_pages':False,'page_limit':1000}
        if args.live:
            require(session['nex_adapter']['available'],'installed SDK lacks its native DAP backend')
            manifest=json.loads(Path(session['manifest']).read_text())
            projected=manifest['sources'][0]['projection']
            line=next(i+1 for i,text in enumerate(source.read_text().splitlines()) if 'NATIVE_PAGE_STOP' in text)
            client=DAP(session['adapter_command'],directory,environment)
            try:
                client.request('initialize',{'adapterID':'nex','pathFormat':'path','linesStartAt1':True,'supportsVariablePaging':True})
                pending=client.send('launch',dict(session['launch'],disableASLR=False));client.event('initialized')
                placed=client.request('setBreakpoints',{'source':{'path':projected},'breakpoints':[{'line':line}]})
                require(placed['breakpoints'][0]['verified'],'native pages breakpoint was not verified')
                client.request('configurationDone');client.response(pending)
                stop=client.event('stopped');frame=client.request('stackTrace',{'threadId':stop['threadId']})['stackFrames'][0]['id']
                scopes=client.request('scopes',{'frameId':frame})['scopes'];roots={}
                for scope in scopes:
                    if not scope.get('expensive'):
                        roots.update({v['name']:v for v in client.request('variables',{'variablesReference':scope['variablesReference']})['variables']})
                before=client.request('evaluate',{'expression':'len(items)+len(data)','frameId':frame,'context':'watch'})
                require(before['nex']['value']=='4227072','native root lengths differ before paging')
                pages={}
                for name,total,expected in [('items',32768,['40','42']),('data',4194304,['120','255'])]:
                    reference=roots[name]['variablesReference']
                    require(roots[name]['indexedVariables']==total,'native root lost its indexed child count')
                    tail=client.request('variables',{'variablesReference':reference,'filter':'indexed','start':total-2,'count':2})
                    require([(v['name'],v['value']) for v in tail['variables']]==[(f'[{total-2}]',expected[0]),(f'[{total-1}]',expected[1])],
                        'native indexed tail differs')
                    require(not client.request('variables',{'variablesReference':reference,'filter':'named','count':2})['variables'],
                        'native indexed root returned named children')
                    default=client.request('variables',{'variablesReference':reference})
                    large=client.request('variables',{'variablesReference':reference,'start':1000,'count':1000000})
                    require(len(default['variables'])==len(large['variables'])==1000 and large['variables'][0]['name']=='[1000]',
                        'native page request exceeded or lost its bound/offset')
                    require(large['nex']['native_page']=={'start':1000,'requested_count':1000000,'returned_count':1000,'limit':1000},
                        'native page metadata differs')
                    pages[name]={'indexed_children':total,'tail':[(v['name'],v['value']) for v in tail['variables']],
                        'default_count':len(default['variables']),'large_request_count':len(large['variables'])}
                first=client.request('evaluate',{'expression':'items[len(items)-1]+data[len(data)-1]','frameId':frame,'context':'watch'})
                second=client.request('evaluate',{'expression':'len(data)','frameId':frame,'context':'watch'})
                require(first['nex']['value']=='297' and second['nex']['stop']==first['nex']['stop']==before['nex']['stop'],
                    'native paging changed the stopped watch state')
                client.request('continue',{'threadId':stop['threadId']});require(client.event('exited')['exitCode']==0,'native page application failed')
                for name in ('items','data'):
                    try:client.request('variables',{'variablesReference':roots[name]['variablesReference'],'count':1})
                    except RuntimeError as error:require('unknown or stale variables reference' in str(error),'native page failed for a different reason after execution')
                    else:raise RuntimeError('native page handle survived execution')
                evidence.update(live_dap_pages=True,pages=pages,unchanged_watch_stop=first['nex']['stop'],native_exit_code=0,stale_handles_rejected=True)
            finally:client.close()
        report['evidence']['native_indexed_pages']=evidence

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

    def project_build():
        full_descriptor = cli('describe'); description = full_descriptor['project_build']
        require('project_architecture_tasks' in full_descriptor['task_features'], 'SDK lacks project task captures/replay')
        require('project_task_packages' in full_descriptor['task_features'], 'SDK lacks project package acceptance checks')
        require(description['manifest_schema'] == 'nex.project-build/1' and
                description['dependency_linkage'] == ['source', 'static', 'dynamic'] and
                'shared_library' in description['artifact_kinds'] and
                {'project_binary_execution','project_owned_tests','project_native_debug_descriptors','project_native_profiles'} <= set(description['features']), 'SDK project build contract differs')
        architecture = root / 'project-architecture'
        shutil.copytree(resources / 'examples/project-build', architecture)
        planned = cli('project', '--kind', 'plan', cwd=architecture)
        require(planned['schema'] == 'nex.project-plan/1' and planned['source_checked'] and
                not planned['external_tools_invoked'] and not (architecture / '.nex').exists(),
                'project plan did not remain read-only')
        selected = cli('project', '--kind', 'plan', '--component', 'app', cwd=architecture)
        require([c['name'] for c in selected['components']] == ['core', 'app'], 'project dependency closure differs')
        native = cli('project', '--kind', 'build', '--component', 'app', '--configuration', 'release', cwd=architecture)
        application, = native['artifacts']
        require(application['kind'] == 'executable' and run([application['artifact']]) == '22\n',
                'project application did not execute its shared source')
        archive = cli('project', '--kind', 'build', '--component', 'archive', '--configuration', 'release', cwd=architecture)
        library, = archive['artifacts']
        debug = json.loads(Path(library['debug_manifest']).read_text())
        symbol = next(f['native_symbol'] for f in debug['functions'] if f['name'] == 'project::archive::answer')
        host = architecture / 'archive-host.cpp'
        host.write_text('extern "C" long long ' + symbol + '();int main(){return ' + symbol + '()==22?0:1;}')
        executable = architecture / 'archive-host'
        run([report['doctor']['native_compiler'], '-std=c++20', host, library['artifact'], '-o', executable])
        run([executable])
        warm = cli('project', '--kind', 'build', '--component', 'app', '--configuration', 'release', cwd=architecture)
        require(warm['plan_hash'] == native['plan_hash'] and warm['artifacts'][0]['cached'], 'project cache/plan changed')
        manifest = architecture / 'nex.build.json'
        broken = json.loads(manifest.read_text()); broken['components']['app']['dependencies'] = {}
        manifest.write_text(json.dumps(broken))
        rejected = cli('project', '--kind', 'build', '--component', 'app', cwd=architecture, expected_success=False)
        require(rejected['code'] == 'E_PROJECT_BOUNDARY', 'undeclared architecture edge was accepted')
        shutil.copy2(resources / 'examples/project-build/nex.build.json', manifest)
        web_result = None
        if args.browser:
            built = cli('project', '--kind', 'build', '--component', 'browser', '--configuration', 'release', cwd=architecture, timeout=300)
            web_result, = built['artifacts']
            require(web_result['kind'] == 'web' and (Path(web_result['result']['dist']) / 'index.html').is_file(),
                    'project browser artifact is missing')
        require(not (architecture / '.nex/graph.db').exists(), 'project build synchronized graph history')
        binary_project = root / 'native-library-project'
        shutil.copytree(resources / 'examples/native-libraries', binary_project)
        binary_plan = cli('project', '--kind', 'plan', cwd=binary_project)
        require(not (binary_project / '.nex').exists(), 'binary dependency plan created a cache/store')
        binary_build = cli('project', '--kind', 'build', '--configuration', 'release', cwd=binary_project)
        binary_artifacts = {a['component']: a for a in binary_build['artifacts']}
        require(run([binary_artifacts['app']['artifact']]) == '22\nNEX 🧠\n', 'archive consumer differs')
        compilation = json.loads(Path(binary_artifacts['app']['compilation']).read_text())
        require(not any(f.startswith('native_library::math::') for u in compilation['units'] for f in u['functions'])
                and len(compilation['static_libraries']) == 1, 'consumer recompiled its binary dependency')
        binary_archive = Path(binary_artifacts['core']['artifact'])
        binary_abi = json.loads((binary_archive.parent / 'library-abi.json').read_text())
        require(binary_abi['code_only'] and binary_archive.read_bytes().startswith(b'!<arch>\n'), 'code-only archive missing')
        binary_warm = cli('project', '--kind', 'build', '--configuration', 'release', cwd=binary_project)
        require(all(a['cached'] for a in binary_warm['artifacts']), 'binary dependencies did not reuse checked artifacts')
        require(not (binary_project / '.nex/graph.db').exists(), 'binary build opened graph history')
        report['evidence']['project_build'] = {'plan_hash': planned['plan_hash'], 'selected_plan_hash': selected['plan_hash'],
            'native_artifact': application['artifact'], 'archive': library['artifact'], 'archive_host_executed': True,
            'source_linkage': True, 'undeclared_import_rejected': True, 'web_built': web_result is not None,
            'static_archive_consumption': True, 'consumer_definitions_excluded': True,
            'binary_plan_hash': binary_plan['plan_hash'], 'binary_artifacts': binary_artifacts,
            'graph_store_opened': False}
        shared_project = root/'shared-library-project'
        shutil.copytree(resources/'examples/native-libraries', shared_project)
        shared_description = json.loads((shared_project/'nex.build.json').read_text())
        shared_description['configurations']['profile'] = {'profile': 'profile'}
        shared_description['components']['core']['kind'] = 'shared_library'
        (shared_project/'bridge').mkdir()
        bridge = shared_project/'bridge/main.nex'
        bridge.write_text('''module sdk_shared::bridge;
import "../core/math.nex" as m;
pub fn render(x:i64)->str{
 let held:str=str(m::make(40)(x));
 return m::decorate(held); // SHARED_STOP
}
test fn bridge_checks()->unit{assert(render(2)=="42 🧠");}
''')
        shared_description['components']['bridge'] = {'kind': 'shared_library', 'root': 'bridge',
            'entry': 'bridge/main.nex', 'entry_function': 'render', 'dependencies': {'core': 'dynamic'}}
        shared_description['components']['app']['dependencies'] = {'bridge': 'dynamic'}
        app_source = shared_project/'app/main.nex'
        app_source.write_text('module sdk_shared::app;import "../bridge/main.nex" as b;fn main()->unit!{io}{print(b::render(2));}test fn app_checks()->unit{assert(b::render(2)=="42 🧠");}')
        (shared_project/'nex.build.json').write_text(json.dumps(shared_description))
        def shared_build(profile):
            return cli('project', '--kind', 'build', '--configuration', profile, cwd=shared_project, timeout=300)
        linked = shared_build('release'); images = {a['component']: a for a in linked['artifacts']}
        require(run([images['app']['artifact']]) == '42 🧠\n', 'shared project application differs')
        compilation = json.loads(Path(images['app']['compilation']).read_text())
        require(len(compilation['owned_images']) == 3 and not compilation['static_libraries'] and
                sum(i['kind'] == 'runtime' for i in compilation['owned_images']) == 1 and
                all(u['identity'].startswith('sdk_shared::app::') for u in compilation['units']),
                'shared project did not consume separate binary images and one runtime')
        require(all(a['cached'] for a in shared_build('release')['artifacts']), 'shared project cache missed')
        app_source.write_text(app_source.read_text().replace('render(2)', 'render(3)'))
        edited = shared_build('release'); edited_images = {a['component']: a for a in edited['artifacts']}
        require(edited['native_runtime_image'] == linked['native_runtime_image'] and
                all(edited_images[n]['build_key'] == images[n]['build_key'] and edited_images[n]['cached']
                    for n in ('core', 'bridge')) and run([edited_images['app']['artifact']]) == '43 🧠\n',
                'application edit changed independent shared providers/runtime')
        moved_app = root/'moved shared app % 🧠'; moved_app.mkdir()
        executable = Path(edited_images['app']['artifact'])
        shutil.copy2(executable, moved_app/'app'); shutil.copytree(executable.parent/'images', moved_app/'images')
        hidden = root/'retained-shared-project'
        shared_project.rename(hidden)
        try:
            require(run([moved_app/'app'], cwd=moved_app) == '43 🧠\n', 'moved shared application needs its original project')
        finally:
            hidden.rename(shared_project)
        app_source.write_text(app_source.read_text().replace('render(3)', 'render(2)'))
        profiled = {a['component']: a for a in shared_build('profile')['artifacts']}
        profile_path = root/'shared-profile.json'
        previous = {k: environment.get(k) for k in ('NEX_TRACY', 'NEX_PROFILE_OUTPUT')}
        environment.update(NEX_TRACY='0', NEX_PROFILE_OUTPUT=str(profile_path))
        try:
            require(run([profiled['app']['artifact']]) == '42 🧠\n', 'shared profile execution differs')
        finally:
            for key, value in previous.items():
                if value is None: environment.pop(key, None)
                else: environment[key] = value
        measured = json.loads(profile_path.read_text())
        require(measured['build']['build_key'] == profiled['app']['build_key'] and measured['memory'] and
                all(p['live'] == 0 and p['allocations'] == p['frees'] for p in measured['memory']),
                'shared profile is unbound or retains owned values')
        action_run=cli('project','--kind','run','--component','app','--configuration','release',cwd=shared_project,timeout=300)
        require(action_run['observation']['stdout']=='42 🧠\n' and not action_run['graph_store_opened'], 'project run did not execute its declared images')
        action_tests=cli('project','--kind','test','--component','app','--configuration','debug',cwd=shared_project,timeout=300)
        require({t['name'] for t in action_tests['tests']}=={'sdk_shared::bridge::bridge_checks','sdk_shared::app::app_checks'} and
                all(t['native'] and t['reference'] and t['typescript'] and t['ok'] for t in action_tests['tests']), 'project owned/native/TypeScript/reference tests differ')
        action_debug=cli('project','--kind','debug','--component','app','--adapter','nex-dap',cwd=shared_project,timeout=300)
        debug_artifact=next(a for a in action_debug['artifacts'] if a['component']=='app')
        require(action_debug['observation']['launch']['program']==debug_artifact['artifact'] and
                action_debug['observation']['build_key']==debug_artifact['build_key'], 'project debugger independently rebuilt source')
        action_profile=cli('project','--kind','profile','--component','app','--configuration','profile',cwd=shared_project,timeout=300)
        actual_profile=action_profile['observation']
        require(actual_profile['stdout']=='42 🧠\n' and any(f['name']=='sdk_shared::bridge::render' for f in actual_profile['functions']) and
                all(f['node_id'] is None and f['identity_scope']=='captured_project' for f in actual_profile['functions']) and
                not (shared_project/'.nex/graph.db').exists(), 'project profile lost provider attribution or created graph IDs')
        task_project=root/'project-task-example';shutil.copytree(resources/'examples/project-tasks',task_project)
        notice_fixture=task_project/'fixture-notice.txt';notice_fixture.write_text('SDK acceptance notice-capture data fixture; not a dependency redistribution notice.\n')
        (task_project/'notices.json').write_text(json.dumps({'schema':'nex.sdk-notices/1','components':[
            {'name':'sdk-notice-capture-fixture','version':'test','url':'https://github.com/sae-ru/NEX',
             'roots':['core/value.nex'],'license_files':['fixture-notice.txt']}]}))
        notice_pin=cli('task','notices.json','--kind','notices',cwd=task_project)
        require(not notice_pin['graph_store_opened'] and not notice_pin['external_tools_invoked'] and not (task_project/'.nex').exists(), 'notice inspector executed tools or opened a graph')
        task_contract=json.loads((task_project/'task.json').read_text())
        next(c for c in task_contract['checks'] if c['kind']=='package').update(notices='notices.json',notices_hash=notice_pin['inputs_hash'])
        (task_project/'task.json').write_text(json.dumps(task_contract))
        task_checked=cli('task','task.json','--kind','check',cwd=task_project,timeout=300)
        task_run=cli('task','task.json','--kind','run','--task-hash',task_checked['task_hash'],'--directory',root/'project-task-run',cwd=task_project,timeout=600)
        require(task_run['ok'] and all(c['status']=='passed' for c in task_run['checks']), 'project acceptance task failed')
        task_receipt=Path(task_run['output']);saved_task=json.loads(task_receipt.read_text())
        task_build=next(c for c in saved_task['checks'] if c['id']=='build-native')
        task_app=task_receipt.parent/next(c['directory'] for c in task_build['components'] if c['component']=='app')/'compilation.json'
        task_compilation=json.loads(task_app.read_text())
        require(len(task_compilation['owned_images'])==2 and all(u['identity'].startswith('project_task::app::') for u in task_compilation['units']), 'task recompiled its shared provider')
        task_native=json.loads((task_receipt.parent/'artifacts/output/commands/native.json').read_text())
        require(task_native['command'][0]!=str(compiler) and '--revision' not in task_native['command'], 'task did not supervise the actual native image directly')
        task_package=next(c for c in saved_task['checks'] if c['kind']=='package')
        require(task_package['notices_hash']==notice_pin['inputs_hash'] and (task_receipt.parent/'inputs/package-notices/package/licenses/0.txt').is_file(), 'task did not capture its reviewed notice data')
        task_deployment=task_receipt.parent/task_package['package']
        require(not task_package['application_execution'] and (task_deployment/'apps/app/THIRD_PARTY_NOTICES.txt').is_file(), 'task package is missing build-only deployment evidence')
        shutil.rmtree(task_project)
        packaged_task_stdout=run([task_deployment/'apps/app/bin/app'],cwd=root,timeout=30)
        require(packaged_task_stdout=='42 🧠\n', 'task package failed after source deletion')
        task_replay=cli('task',task_receipt,'--kind','replay','--directory',root/'project-task-replay',cwd=root,timeout=600)
        require(task_replay['ok'] and task_replay['programs']==task_run['programs'], 'project task replay fell back to deleted source')
        require((Path(task_replay['output']).parent/'state/.nex/graph.db').is_file() and not (task_receipt.parent/'.nex/graph.db').exists() and not (root/'.nex/graph.db').exists(), 'project replay used its input or enclosing evidence/workspace graph')
        report['evidence']['project_architecture_task']={'ok':True,'source_deleted_replay':True,'original':str(task_receipt),'replay':task_replay['output'],
            'task_hash':task_checked['task_hash'],'actual_shared_provider':True,'native_execution_supervised_directly':True,
            'deployment_package_after_source_deletion':True,'pinned_notice_source_deleted_replay':True,'checks':len(saved_task['checks'])}
        deployment = root/'shared-project-package'
        packaged = cli('project', '--kind', 'package', '--configuration', 'release', '--component', 'app',
                       '--directory', deployment, cwd=shared_project, timeout=300)
        require(packaged['schema'] == 'nex.project-package/1' and not packaged['application_execution'] and
                not packaged['graph_store_opened'], 'project package executed/synchronized its source')
        package_app = next(c for c in packaged['components'] if c['component'] == 'app')
        native_package = json.loads((deployment/package_app['manifest']).read_text())
        owned = [r for r in native_package['files'].values() if 'owned_image_kind' in r]
        require(len(owned) == 3 and sum(r['owned_image_kind'] == 'runtime' for r in owned) == 1,
                'project package did not retain its two libraries and common runtime')
        hidden = root/'source-hidden-during-package-run'; shared_project.rename(hidden)
        moved_deployment = root/'moved project package % 🧠'; deployment.rename(moved_deployment)
        try:
            require(run([moved_deployment/package_app['entry']]) == '42 🧠\n', 'relocated project package needs its original build')
        finally:
            hidden.rename(shared_project)
        architecture_package = root/'architecture-package'
        package_selection = [] if args.browser else ['--component', 'app']
        architecture_deployment = cli('project', '--kind', 'package', '--configuration', 'release',
            '--directory', architecture_package, *package_selection, cwd=architecture, timeout=300)
        require(run([architecture_package/'apps/app/bin/app']) == '22\n', 'source-architecture package differs')
        if args.browser:
            require((architecture_package/'web/browser/index.html').is_file() and
                    (architecture_package/'web/browser/THIRD_PARTY_NOTICES.txt').is_file(), 'project package lost browser assets/notices')
        shared_evidence = {'separate_shared_libraries': 2, 'one_runtime': True, 'consumer_did_not_recompile_providers': True,
            'moved_application': str(moved_app/'app'), 'provider_reuse_after_app_edit': True,
            'profile_identity_checked': True, 'profile_cleanup_checked': True, 'actual_shared_core': False}
        shared_evidence.update(project_package=str(moved_deployment), relocated_project_package_executed=True,
            package_preserved_shared_edges=True, architecture_package=str(architecture_package), native_and_web_packaged=args.browser)
        shared_evidence.update(project_run=True,project_owned_tests=len(action_tests['tests']),project_debug_descriptor=True,
            project_profile=True,captured_project_identities=True)
        if args.live:
            debug_images = {a['component']: a for a in shared_build('debug')['artifacts']}
            debug_app = debug_images['app']; manifest = Path(debug_app['debug_manifest'])
            metadata = json.loads(manifest.read_text())
            projection = next(s['projection'] for s in metadata['sources'] if Path(s['original']).resolve() == bridge.resolve())
            line = next(i+1 for i, s in enumerate(Path(projection).read_text().splitlines()) if 'SHARED_STOP' in s)
            core = root/'shared-project.core'
            lldb = os.environ.get('NEX_LLDB') or shutil.which('lldb')
            require(lldb is not None, 'shared core acceptance requires LLDB')
            captured = run([lldb, debug_app['artifact'], '--no-lldbinit', '--batch',
                '-o', 'settings set target.disable-aslr false',
                '-o', 'command script import '+json.dumps(str(manifest.parent/'debugger/lldb_nex.py'), ensure_ascii=False),
                '-o', 'nex-load-debug '+json.dumps(str(manifest), ensure_ascii=False)+' --compiler '+json.dumps(str(compiler), ensure_ascii=False),
                '-o', 'breakpoint set --file '+json.dumps(projection, ensure_ascii=False)+' --line '+str(line),
                '-o', 'run', '-o', 'nex-eval held',
                '-o', 'process save-core --style modified-memory '+json.dumps(str(core), ensure_ascii=False),
                '-o', 'continue'], cwd=shared_project, timeout=120)
            require(core.is_file() and 'exited with status = 0' in captured, 'shared library stop/core did not complete')
            for name in ('core', 'bridge', 'app'): shutil.rmtree(shared_project/name)
            observed = cli('core', core, '--manifest', manifest, '--expression', 'held', cwd=shared_project, timeout=120)
            require(observed['watch']['value'] == '42' and not observed['inferior_execution'] and
                    'libnex_bridge_' in observed['frames'][observed['selected_frame']]['module'], 'shared core frame/watch differs')
            capsule = root/'shared-core-capsule'
            exported = cli('core', core, '--manifest', manifest, '--export', capsule, '--expression', 'held', cwd=shared_project, timeout=180)
            require(exported['read_after_export'], 'shared capsule was not checked after export')
            original = Path(debug_app['artifact']).parent; original.rename(root/'retained-shared-core-build')
            moved = root/'moved shared core % 🧠'; capsule.rename(moved)
            replay = cli('core', '--capsule', moved, '--expression', 'held', cwd=shared_project, timeout=120)
            require(replay['watch']['value'] == '42' and replay['stop_unchanged'] and not replay['inferior_execution'] and
                    replay['capsule']['dependency_scope'] == 'captured_first_party_and_matching_host_system',
                    'source/image-deleted shared capsule replay differs')
            shared_evidence.update(actual_shared_core=True, moved_capsule=str(moved), exact_watch='42')
        report['evidence']['shared_project_build'] = shared_evidence

    try:
        actions = [('discovery', discover), ('editor-tools', editor_tools), ('new-project', new_project),
                ('reviewed-failure', baseline_failure), ('graph-repair-import', repair),
                ('backend-agreement', backend_agreement), ('graph-snapshot-recovery', graph_snapshot_recovery),
                ('project-version-boundaries', project_version_boundaries), ('frontend-diagnostics', frontend_diagnostics),
                ('graph-queries', graph_queries), ('string-ranges', string_ranges),
                ('binary-values', binary_values), ('native-indexed-pages', native_pages), ('core-reports', core_reports), ('wasm-compute', wasm_compute),
                ('foreign-boundary', foreign_boundary), ('text-files', text_files), ('profile', measured),
                ('archive-debug-replay-export', sources_and_debug), ('scalar-proof', proof),
                ('traits', traits), ('authenticated-storage', authenticated_storage), ('browser', browser), ('project-build', project_build)]
        require(tuple(name for name, _ in actions) == ACCEPTANCE_PHASES,
                'SDK action registration differs from its workflow phase contract')
        for name, action in actions:
            phase(name, action)
        report['ok'] = True
        validate_completed_report(report)
    except BaseException as error:
        report['ok'] = False
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
