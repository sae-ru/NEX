"""Actual installed030 application/provider consumption; no source-tree fallback."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys


HOST_RUNTIME = ('runtime.cpp', 'nex_cells.cpp', 'nex_cell_host.cpp', 'nex_task_session.cpp',
                'nex_task_frame.cpp', 'nex_task_external.cpp', 'nex_files.cpp',
                'nex_resource_region.cpp', 'nex_external_resource.cpp', 'nex_resource_executor.cpp')
HOST_TESTS = ('native_task_sessions.py', 'native_task_session.cpp', 'native_task_session_images.cpp', 'host_test.h')
EXAMPLES = ('reference-task-profiling', 'persistent-ui', 'native-host-session')
PROFILE_FUNCTIONS = ('ref_profile_app::main', 'ref_profile_leaf::make', 'ref_profile_leaf::work',
                     'ref_profile_mid::work', 'ref_profile_pure::offset')
UI_CASES = {'persistent-identity-snapshots-serial-events', 'independent-heaps-and-explicit-close',
            'close-before-initialization', 'cancel-active-source-update', 'external-application-cancellation',
            'deadline-owned-cleanup', 'budget-owned-cleanup', 'host-completion-failure-owned-cleanup',
            'uncaught-cell-packet-and-new-context', 'bounded-pending-event-queue', 'opaque-state-host-boundary',
            'queued-input-and-published-view-snapshots', 'invalid-host-options'}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def resource_names(resources):
    names = ['tools/sdk_references.py', 'tests/persistent_ui_cases.mjs',
             'llm/native-reference-task-provider.schema.json', 'llm/project-reference-task-linkage.schema.json',
             'docs/reference-task-profiling.md', 'docs/native-task-sessions.md', 'docs/persistent-ui.md']
    names += ['runtime/' + name for name in HOST_RUNTIME]
    names += ['runtime/' + name for name in ('nex_task_session.h', 'nex_task_protocol.h', 'nex_cells.h', 'nex_value.h')]
    names += ['tests/' + name for name in HOST_TESTS]
    for example in EXAMPLES:
        names += [path.relative_to(resources).as_posix() for path in sorted((resources/'examples'/example).rglob('*'))
                  if path.is_file() and '.nex' not in path.relative_to(resources/'examples'/example).parts]
    return sorted(set(names))


def profile_summary(session, identity, providers=True, exit_code=0, timeline=True):
    data = read(session['output'])
    require(session['schema'] == ('nex.profile-session/3' if providers else 'nex.profile-session/2') and
            session['exit_code'] == exit_code and session['stdout'] == ('42\n' if not exit_code else '') and
            data['language'] == '0.30' and data['build']['compiler_build'] == identity['compiler_build'] and
            data['task_execution']['executor_workers'] == 1, 'installed030 profile identity/executor differs')
    require(all(data['completeness'][key] is True for key in ('aggregates', 'memory', 'cpu', 'elapsed', 'lifetime')) and
            data['completeness']['timeline'] is timeline and
            all(data[key] == 0 for key in ('dropped_tasks', 'dropped_invocations', 'dropped_guards',
                'suppressed_hooks', 'invalid_transitions', 'clock_failures', 'counter_overflows',
                'serialization_overflows', 'dropped_allocations', 'untracked_frees')),
            'installed030 profile lost observations')
    require(all(row['terminal'] and not row['active_invocations'] for row in data['tasks']) and
            all(row['live'] == 0 and row['live_shallow_bytes'] == 0 and row['allocations'] == row['frees'] for row in data['memory']),
            'installed030 profile retained tasks or tracked values')
    counts = {row['name']: {key: row[key] for key in ('calls', 'completed', 'aborted')} for row in data['functions']}
    if not exit_code:
        for name in PROFILE_FUNCTIONS:
            require(counts.get(name) == {'calls': 1, 'completed': int(name != 'ref_profile_leaf::work'),
                    'aborted': int(name == 'ref_profile_leaf::work')}, 'installed030 source-call oracle differs: ' + name)
        if timeline:
            site = next(i for i, row in enumerate(data['functions']) if row['name'] == 'ref_profile_leaf::work')
            invocations = [row for row in data['invocations'] if row['site'] == site]
            require(len(invocations) == 1 and sum(row['invocation_id'] == invocations[0]['id'] for row in data['segments']) > 1,
                    'installed030 yields became extra source calls')
    return {'report': session['output'], 'report_sha256': sha(session['output']),
            'schema': data['schema'], 'build': data['build'], 'exit_code': exit_code,
            'executor_workers': 1, 'tracked_memory_balanced': True, 'terminal_tasks': True,
            'completeness': data['completeness'],
            'source_counts': counts}


def exercise(*, cli, run, compiler, resources, root, browser, live, doctor, environment, dap_factory=None):
    base = root/'reference030'; base.mkdir()
    identity = cli('describe', '--kind', 'index')
    capability = cli('describe', '--field', 'managed_references')['value']
    pack = read(resources/'llm/language-pack.json')
    require(capability == pack['managed_references'] and capability['public_source_enabled'] is True and
            capability['source030_development']['native_task_profiling']['execution_task_ABI'] == 8 and
            capability['source030_development']['native_providers']['profiles'] == ['debug', 'release', 'profile'],
            'installed030 reference capability/language pack differs')
    pins = {name: sha(resources/name) for name in resource_names(resources)}
    fresh = base/'created'; cli('init', fresh)
    require(read(fresh/'nex.json')['language'] == '0.30', 'new SDK project did not select030')
    result = {'schema': 'nex.sdk-reference030/1', 'ok': False, 'source_language': '0.30', 'execution_task_ABI': 8,
              'compiler_sha256': sha(compiler), 'compiler_build': identity['compiler_build'],
              'descriptor_hash': identity['descriptor_hash'], 'resource_sha256': pins,
              'init_language': '0.30', 'providers': [], 'complete_SDK_workflow_claimed': False}
    mixed = None
    for mode in ('static', 'shared', 'mixed'):
        directory = base/mode
        shutil.copytree(resources/'examples/reference-task-profiling', directory, ignore=shutil.ignore_patterns('.nex'))
        config = read(directory/'nex.build.json')
        for name, component in config['components'].items():
            if name != 'app':
                component['kind'] = 'shared_library' if mode == 'shared' or (mode == 'mixed' and name == 'leaf') else 'static_library'
        for component in config['components'].values():
            component['dependencies'] = {name: 'dynamic' if config['components'][name]['kind'] == 'shared_library' else 'static'
                                         for name in component.get('dependencies', {})}
        (directory/'nex.build.json').write_text(json.dumps(config) + '\n')
        require(cli('eval', cwd=directory)['stdout'] == '42\n', 'installed030 reference source oracle differs')
        native = {}
        for profile in ('debug', 'release'):
            observed = cli('project', '--kind', 'run', '--component', 'app', '--configuration', profile, cwd=directory, timeout=360)
            require(observed['observation']['stdout'] == '42\n' and observed['observation']['exit_code'] == 0 and
                    observed['observation']['task_execution']['executor_workers'] == 1, 'installed030 native provider execution differs')
            native[profile] = '42\n'
        measured = cli('project', '--kind', 'profile', '--component', 'app', '--configuration', 'measured', cwd=directory, timeout=360)
        summary = profile_summary(measured['observation'], identity)
        for component in measured['plan']['components']:
            linkage = component['task_linkage']
            require(linkage['schema'] == 'nex.project-task-linkage/19' and linkage['execution_abi'] == 8,
                    'installed030 profile plan lost ABI8')
        images = {}
        for artifact in measured['artifacts']:
            path = Path(artifact['artifact']); record = read(path.parent/'task-provider.json')
            require(record['schema'] == 'nex.native-task-provider/19' and record['descriptor_abi'] == 0x4e45585400000008,
                    'installed030 profile image lost ABI8')
            images[artifact['component']] = {'sha256': sha(path), 'record_sha256': sha(path.parent/'task-provider.json')}
        result['providers'].append({'mode': mode, 'reference_stdout': '42\n', 'native': native,
                                    'profile': summary, 'images': images})
        if mode == 'static':
            session = cli('profile', 'app/main.nex', '--task-timeout-ms', '10000', cwd=directory, timeout=360)
            result['standalone_profile'] = profile_summary(session, identity, False)
            if browser:
                target = base/'typescript'
                cli('emit', 'app/main.nex', '--kind', 'typescript', '--directory', target, cwd=directory)
                mapping = read(target/'nex-map.json')
                require(mapping['schema'] == 'nex.typescript-map/4', 'installed030 async map differs')
                (target/'package.json').write_text('{"type":"module"}\n')
                runner = target/'run.mjs'; runner.write_text("import {entry} from './program.ts';await entry();\n")
                output = run([os.environ.get('NEX_NODE') or 'node', '--no-warnings', '--experimental-strip-types', runner])
                require(output == '42\n', 'installed030 TypeScript source execution differs')
        if mode == 'mixed':
            mixed = directory
    result['typescript'] = {'requested': browser, 'executed': browser, 'stdout': '42\n' if browser else None}
    control = base/'control'; control.mkdir()
    (control/'nex.json').write_text('{"schema":"nex.project/1","language":"0.30","entry":"main.nex"}\n')
    (control/'main.nex').write_text('module sdk_control;enum Link{End();Next(next:cell<Link>);}'
        'fn main()->unit!{task,state}{let c:cell<Link>=cell_new(Link::End());cell_write(c,Link::Next(c));while true{task_yield();}}\n')
    result['controls'] = []
    for code, flags in [('E_LIMIT', ['--task-steps', '1000']),
                        ('E_TIMEOUT', ['--task-steps', '9007199254740991', '--task-timeout-ms', '25'])]:
        session = cli('profile', *flags, cwd=control, expected_success=False, timeout=360)
        require(code in session['stderr'], 'installed030 control outcome differs')
        result['controls'].append({'code': code, **profile_summary(session, identity, False, 70)})
    result['debugger'] = debug(cli, resources, mixed, live, environment, dap_factory)
    result['delivery'] = delivery(cli, run, resources, mixed, base, identity)
    result['native_host_sessions'] = native_host(cli, run, compiler, resources, base, doctor)
    result['persistent_UI'] = persistent_ui(cli, run, resources, base, browser)
    require(pins == {name: sha(resources/name) for name in pins}, 'installed030 workflow changed SDK resources')
    result['ok'] = True
    return result


def delivery(cli, run, resources, directory, base, identity):
    task = cli('task', 'nex.build.json', '--kind', 'init', '--component', 'app', '--configuration', 'measured', cwd=directory)
    task['checks'] = [{'id': 'profile', 'kind': 'profile', 'program': 'app', 'target': 'native', 'configuration': 'measured',
                       'entry': 'ref_profile_app::main', 'scenario': 'SDK030 cells/errors/cycles',
                       'budget': {'max_calls': {'ref_profile_leaf::work': '1'}, 'max_peak_handles': '100000',
                                  'max_peak_objects': '100000'}, 'timeout_seconds': 240}]
    task['requirements'] = [{'id': 'profile', 'text': 'Measure checked030 state across library images',
        'bindings': [{'program': 'app', 'kind': 'function', 'symbol': 'ref_profile_app::main'}],
        'targets': ['native'], 'checks': ['profile']}]
    taskfile = directory/'task.json'; taskfile.write_text(json.dumps(task) + '\n')
    accepted = cli('task', taskfile, '--kind', 'run', '--directory', base/'capture', cwd=directory, timeout=900)
    receipt = Path(accepted['output']); record = read(receipt); check, = record['checks']
    require(accepted['ok'] and check['status'] == 'passed', 'installed030 captured profile failed')
    captured = read(receipt.parent/'inputs/projects/app.json')
    require(all(c['task_linkage']['schema'] == 'nex.project-task-linkage/19' and c['task_linkage']['execution_abi'] == 8
                for c in captured['expectations']['measured']), 'installed030 capture lost its profile source union')
    measured = profile_summary(read(receipt.parent/check['receipt'])['response'], identity, timeline=False)
    packages = {}
    for configuration in ('release', 'measured'):
        destination = base/('package-' + configuration)
        cli('project', '--kind', 'package', '--component', 'app', '--configuration', configuration,
            '--directory', destination, cwd=directory, timeout=360)
        package = destination/'apps/app'; manifest = read(package/'application.json')
        provenance = manifest['task_provenance' if configuration == 'release' else 'task_profile_provenance']
        require(provenance['metadata_rewritten'] is False, 'installed030 package rewrote its originals')
        packages[configuration] = package
    for name in ('app', 'leaf', 'mid', 'pure', '.nex'):
        shutil.rmtree(directory/name)
    for name in ('nex.json', 'nex.build.json', 'task.json'):
        (directory/name).unlink()
    raw = base/'packaged-profile.json'
    for configuration, package in packages.items():
        executable = package/'bin'/('app.exe' if os.name == 'nt' else 'app')
        command = [executable]
        if configuration == 'measured':
            # Child-only environment: keep the command in the owning SDK ledger.
            command = [sys.executable, '-I', '-c',
                'import os,subprocess,sys;env=dict(os.environ,NEX_PROFILE_OUTPUT=sys.argv[1]);'
                'sys.exit(subprocess.call(sys.argv[2:],env=env))', raw, executable]
        require(run(command, cwd=base) == '42\n', 'installed030 source-absent package output differs')
    value = read(raw)
    require(value['schema'] == 'nex.profile-runtime/3' and
            all(p['live'] == 0 and p['allocations'] == p['frees'] for p in value['memory']), 'installed030 packaged profile retained data')
    replay = cli('task', receipt, '--kind', 'replay', '--directory', base/'replay', cwd=base, timeout=900)
    require(replay['ok'] and replay['programs'] == accepted['programs'], 'installed030 replay changed its source identities')
    return {'ok': True, 'source_absent': True, 'profile': measured, 'receipt_sha256': sha(receipt),
            'captured_source_sha256': sha(receipt.parent/'inputs/projects/app.json'), 'replay_programs_equal': True,
            'ordinary_package_stdout': '42\n', 'profile_package_stdout': '42\n', 'raw_profile_sha256': sha(raw),
            'metadata_rewritten': False}


def native_host(cli, run, compiler, resources, base, doctor):
    host = base/('native-host.exe' if os.name == 'nt' else 'native-host')
    flags = ['-Wl,--export-all-symbols', '-Xlinker', '--out-implib', '-Xlinker',
             str(host.parent/('lib' + host.stem + '.dll.a'))] if os.name == 'nt' else (
        ['-Wl,-export_dynamic'] if sys.platform == 'darwin' else ['-rdynamic', '-ldl'])
    command = [doctor['native_compiler'], '-std=c++20', '-pthread', '-O0',
               '-DNEX_STRUCTURED_WORKERS', '-DNEX_ASYNC_TASKS', '-DNEX_MANAGED_TASKS',
               '-I' + str(resources/'runtime'), '-I' + str(resources/'tests'),
               resources/'tests/native_task_session.cpp', resources/'tests/native_task_session_images.cpp',
               *[resources/'runtime'/name for name in HOST_RUNTIME], *flags, '-o', host]
    run(command, timeout=420)
    destination = base/'host-sessions'
    run([sys.executable, '-B', resources/'tests/native_task_sessions.py', compiler,
         '--host', host, '--clang', doctor['native_compiler'], '--output', destination], timeout=1200)
    value = read(destination/'report.json')
    require(value['compiler_sha256'] == sha(compiler) and value['kernel']['ok'] and
            value['kernel']['cases'] == 14 and value['kernel']['live_delta'] == 0 and len(value['profiles']) == 2 and
            {p['profile'] for p in value['profiles']} == {'debug', 'release'} and
            all(p['host']['ok'] and p['host']['cases'] == 13 and p['host']['live_delta'] == 0 for p in value['profiles']),
            'installed030 matching-runtime native host session differs')
    return {'ok': True, 'kernel_cases': 14, 'profiles': ['debug', 'release'], 'compiled_cases_per_profile': 13,
            'live_delta': 0, 'report_sha256': sha(destination/'report.json'), 'host_sha256': sha(host)}


def persistent_ui(cli, run, resources, base, browser):
    directory = base/'persistent-ui'
    shutil.copytree(resources/'examples/persistent-ui', directory, ignore=shutil.ignore_patterns('.nex'))
    target = base/'generated-ui'
    cli('web', '--directory', target, cwd=directory)
    mapping = read(target/'nex-map.json')
    require(mapping['schema'] == 'nex.typescript-application/1', 'installed030 persistent UI map differs')
    output = run([os.environ.get('NEX_NODE') or 'node', '--no-warnings', '--experimental-strip-types',
                  resources/'tests/persistent_ui_cases.mjs', target], timeout=300)
    observed = json.loads(output)
    require(observed['ok'] is True and observed['cases'] == len(observed['results']) == len(UI_CASES) and
            {r['name'] for r in observed['results']} == UI_CASES and all(r['passed'] for r in observed['results']),
            'installed030 persistent UI/controller cases failed')
    if browser:
        built = cli('build', '--target', 'web', '--profile', 'release', cwd=directory, timeout=360)
        require((Path(built['dist'])/'index.html').is_file() and any(Path(built['dist']).rglob('*.js')),
                'installed030 persistent UI production build is absent')
    return {'ok': True, 'controller': observed, 'map_sha256': sha(target/'nex-map.json'), 'browser_build': browser}


def debug(cli, resources, directory, live, environment, dap_factory):
    prepared = cli('project', '--kind', 'debug', '--component', 'app', '--configuration', 'debug',
                   '--adapter', 'nex-dap', cwd=directory, timeout=360)
    session = prepared['observation']; manifest = read(session['manifest'])
    require(manifest['execution_task_abi'] == '0x4e45585400000008' and manifest['task_debug']['abi'] == 2,
            'installed030 provider debugger lost ABI8/catalog2')
    result = {'requested': live, 'executed': False, 'manifest_sha256': sha(session['manifest']), 'mode': 'mixed'}
    if not live:
        return result
    require(dap_factory is not None, 'installed030 live debug requires the matching DAP client')
    client = dap_factory(session['adapter_command'], directory, environment)
    try:
        client.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path', 'linesStartAt1': True})
        pending = client.send('launch', dict(session['launch'], disableASLR=False)); client.event('initialized')
        points = client.request('setFunctionBreakpoints', {'breakpoints': [{'name': 'ref_profile_leaf::work'}]})
        require(points['breakpoints'][0]['verified'], 'installed030 cell breakpoint is unverified')
        client.request('configurationDone'); client.response(pending); client.event('stopped')
        logical = client.request('threads')['nex']['selected']
        frames = client.request('stackTrace', {'threadId': logical})
        frame = frames['stackFrames'][0]['id']
        scope = client.request('scopes', {'frameId': frame})['scopes'][0]['variablesReference']
        variables = client.request('variables', {'variablesReference': scope})['variables']
        state = next(r for r in variables if r['name'] == 'state')
        children = client.request('variables', {'variablesReference': state['variablesReference']})['variables']
        require(next(r['value'] for r in children if r['name'] == 'value') == '41', 'installed030 DAP cell snapshot differs')
        watch = client.request('evaluate', {'expression': 'input+pure::offset()', 'frameId': frame, 'context': 'watch'})
        require(watch['nex']['value'] == '42' and watch['nex']['source_identity']['component'] == 'leaf',
                'installed030 watch lost its checked source owner')
        client.request('stepOut', {'threadId': logical}); client.event('stopped')
        parent = client.request('stackTrace', {'threadId': logical})
        require(parent['stackFrames'][0]['name'] == 'ref_profile_mid::work', 'installed030 error step-out lost its caller')
        client.request('continue', {'threadId': logical}); require(client.event('exited')['exitCode'] == 0, 'installed030 debuggee failed')
        result.update(executed=True, cell_value='41', pure_watch='42', caller='ref_profile_mid::work')
    finally:
        client.close()
    return result


def validate(report):
    value = report.get('evidence', {}).get('reference030', {})
    require(isinstance(value, dict) and value.get('schema') == 'nex.sdk-reference030/1' and value.get('ok') is True and
            value.get('source_language') == value.get('init_language') == '0.30' and
            type(value.get('execution_task_ABI')) is int and value['execution_task_ABI'] == 8 and
            value.get('compiler_sha256') == report.get('compiler_sha256') and value.get('complete_SDK_workflow_claimed') is False,
            'SDK lacks installed030 reference consumption')
    for key in ('compiler_build', 'descriptor_hash'):
        require(isinstance(value.get(key), str) and re.fullmatch('[0-9a-f]{64}', value[key]), 'installed030 identity is missing')
    pins = value.get('resource_sha256', {})
    mandatory = {'tools/sdk_references.py', 'tests/native_task_sessions.py', 'tests/persistent_ui_cases.mjs',
                 'runtime/nex_task_session.cpp', 'examples/reference-task-profiling/app/main.nex',
                 'examples/persistent-ui/main.nex', 'examples/native-host-session/app/main.nex'}
    require(isinstance(pins, dict) and mandatory <= set(pins) and
            all(isinstance(v, str) and re.fullmatch('[0-9a-f]{64}', v) and report.get('resource_hashes', {}).get(k) == v
                for k, v in pins.items()), 'installed030 resource pins differ')
    providers = value.get('providers', [])
    require(isinstance(providers, list) and len(providers) == 3 and {r.get('mode') for r in providers} == {'static', 'shared', 'mixed'},
            'installed030 provider mode coverage differs')
    def checked_profile(profile, providers=True, exit_code=0, timeline=True):
        require(isinstance(profile, dict) and profile.get('schema') == ('nex.profile/3' if providers else 'nex.profile/2') and
                profile.get('exit_code') == exit_code and type(profile.get('executor_workers')) is int and profile['executor_workers'] == 1 and
                profile.get('tracked_memory_balanced') is True and profile.get('terminal_tasks') is True and
                profile.get('build', {}).get('compiler_build') == value['compiler_build'] and
                isinstance(profile.get('report_sha256'), str) and re.fullmatch('[0-9a-f]{64}', profile['report_sha256']),
                'installed030 profile execution evidence differs')
        require(all(profile.get('completeness', {}).get(k) is True for k in ('aggregates', 'memory', 'cpu', 'elapsed', 'lifetime')) and
                profile['completeness'].get('timeline') is timeline, 'installed030 profile completeness scope differs')
        if not exit_code:
            for name in PROFILE_FUNCTIONS:
                counts = profile.get('source_counts', {}).get(name, {})
                require(counts == {'calls': 1, 'completed': int(name != 'ref_profile_leaf::work'),
                    'aborted': int(name == 'ref_profile_leaf::work')} and all(type(v) is int for v in counts.values()),
                    'installed030 source-call counts differ')
    for row in providers:
        require(row.get('reference_stdout') == '42\n' and row.get('native') == {'debug': '42\n', 'release': '42\n'} and
                set(row.get('images', {})) == {'app', 'leaf', 'mid', 'pure'}, 'installed030 native/reference evidence differs')
        checked_profile(row.get('profile'))
    checked_profile(value.get('standalone_profile'), False)
    controls = value.get('controls', [])
    require(isinstance(controls, list) and len(controls) == 2 and {r.get('code') for r in controls} == {'E_LIMIT', 'E_TIMEOUT'},
            'installed030 control cleanup evidence differs')
    for control in controls:
        checked_profile(control, False, 70)
    delivered = value.get('delivery', {})
    require(all(delivered.get(k) is True for k in ('ok', 'source_absent', 'replay_programs_equal')) and
            delivered.get('metadata_rewritten') is False and delivered.get('ordinary_package_stdout') == delivered.get('profile_package_stdout') == '42\n',
            'installed030 source-absent delivery evidence differs')
    checked_profile(delivered.get('profile'), timeline=False)
    host = value.get('native_host_sessions', {})
    require(host.get('ok') is True and host.get('kernel_cases') == 14 and host.get('compiled_cases_per_profile') == 13 and
            host.get('profiles') == ['debug', 'release'] and host.get('live_delta') == 0, 'installed030 persistent host evidence differs')
    browser = report.get('evidence', {}).get('browser_build')
    ui = value.get('persistent_UI', {})
    require(type(browser) is bool and ui.get('ok') is True and ui.get('browser_build') is browser and
            ui.get('controller', {}).get('ok') is True and type(ui['controller'].get('cases')) is int and
            ui['controller']['cases'] == len(ui['controller'].get('results', [])) == len(UI_CASES) and
            {r.get('name') for r in ui['controller']['results']} == UI_CASES and
            all(r.get('passed') is True for r in ui['controller'].get('results', [])), 'installed030 UI evidence differs')
    ts = value.get('typescript', {})
    require(ts.get('requested') is browser and ts.get('executed') is browser and (not browser or ts.get('stdout') == '42\n'),
            'installed030 TypeScript scope differs')
    live = report.get('evidence', {}).get('live_debugger')
    debugged = value.get('debugger', {})
    require(type(live) is bool and debugged.get('requested') is live and debugged.get('executed') is live and
            (not live or (debugged.get('cell_value') == '41' and debugged.get('pure_watch') == '42' and
                          debugged.get('caller') == 'ref_profile_mid::work')), 'installed030 debugger scope differs')
