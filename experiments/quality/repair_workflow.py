#!/usr/bin/env python3
"""Opt-in Q3: one reviewed bug, real stopped frame, repair, profile and replay."""
import argparse
import copy
import json
from pathlib import Path
import sqlite3
import traceback

from acceptance_support import Evidence, sha, files
from quality_dap import DAP


SOURCE = '''module quality_repair;
pub fn helper(x:i64)->i64{return x+1;}
fn child(input:i64)->i64!{task}{
 let initialized:i64=input;
 task_yield();
 return helper(initialized);
}
fn main()->unit!{io,task}{print(child(41));}
test fn answer()->unit!{task}{assert(child(41)==42);}
'''
LIMITS = {'steps': 200000, 'timeout_ms': 5000, 'workers': 2}


def rows(project):
    # SQLite may initialize WAL sidecars even for SELECTs. Open only this
    # existing DB, then prohibit SQL writes; compare every logical table row.
    with sqlite3.connect((project / '.nex/graph.db').as_uri() + '?mode=rw', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        tables = [name for name, in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return {name: sorted(db.execute('SELECT * FROM "' + name + '"').fetchall(), key=repr) for name in tables}


def profile(path, compiler_build):
    saved = json.loads(path.read_text())
    assert saved['schema'] == 'nex.profile/2'
    assert saved['build']['compiler_build'] == compiler_build
    assert saved['stdout'] == '42\n'
    assert saved['completeness']['aggregates'] and saved['completeness']['memory']
    assert not saved['completeness']['timeline'] and saved['dropped_events'] > 0
    functions = {f['name']: f for f in saved['functions']}
    for name in ('main', 'child', 'helper'):
        item = functions['quality_repair::' + name]
        assert (item['calls'], item['completed'], item['aborted']) == (1, 1, 0)
    for pool in saved['memory']:
        assert pool['live'] == pool['live_shallow_bytes'] == 0
        assert pool['allocations'] == pool['frees']
    assert saved['tasks'] and all(t['terminal'] and t['active_invocations'] == 0 for t in saved['tasks'])
    return saved


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run = Evidence(args.compiler, args.resources, args.output, 'nex.quality-repair-workflow/1')
    run.report.update(runner_sha256=sha(Path(__file__)), dap_transport_sha256=sha(Path(__file__).with_name('quality_dap.py')),
        scope='One source-only task bug and original reviewed acceptance intent. '
              'Actual LLDB-backed NEX-DAP and separate profile actions, not combined debug/profile. '
              'Source paths removed for replay; no kernel isolation or model-cost claim.')
    try:
        actual = run.cli('describe', run.output, 'describe', '--field', 'version')
        assert actual['value'] == '0.20'
        run.report.update(toolchain=actual['toolchain'], language=actual['value'], compiler_build=actual['compiler_build'])
        project = run.output / 'project'
        project.mkdir()
        source = project / 'main.nex'
        source.write_text(SOURCE)
        (project / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.20', 'entry': 'main.nex'}) + '\n')
        task = run.cli('init-contract', project, 'task', source, '--kind', 'init')
        task['goal'] = 'Return42 from input41; preserve the original test and reviewed limits.'
        for check in task['checks']:
            check['task_limits'] = LIMITS
        web = copy.deepcopy(next(c for c in task['checks'] if c['kind'] == 'test'))
        web.update(id='web-answer', target='web')

        def add(check, symbol):
            check['program'] = 'app'
            task['checks'].append(check)
            task['requirements'].append({'id': check['id'], 'text': 'Keep the reviewed42 result',
                'bindings': [{'program': 'app', 'kind': 'function', 'symbol': symbol}],
                'targets': [check['target']], 'checks': [check['id']]})

        add(web, 'quality_repair::answer')
        add({'id': 'observe', 'kind': 'run', 'target': 'native', 'entry': 'quality_repair::main',
             'expect': {'stdout': '42\n', 'exit_code': 0}, 'task_limits': LIMITS}, 'quality_repair::main')
        add({'id': 'profile', 'kind': 'profile', 'target': 'native', 'entry': 'quality_repair::main',
             'scenario': 'one repaired candidate', 'budget': {'max_calls': {'quality_repair::helper': '1'},
             'max_peak_handles': '10000', 'max_peak_objects': '10000'},
             'task_limits': LIMITS, 'timeout_seconds': 180}, 'quality_repair::main')
        taskfile = project / 'task.json'
        taskfile.write_text(json.dumps(task, indent=2) + '\n')
        original_task_bytes = taskfile.read_bytes()
        checked = run.cli('check-intent', project, 'task', taskfile, '--kind', 'check')
        task_hash = checked['task_hash']
        source.write_text(SOURCE.replace('return x+1;', 'return x+2;'))
        failed = run.cli('actual-failing-candidate', project, 'task', taskfile, '--kind', 'run',
                         '--task-hash', task_hash, '--directory', run.output / 'failed-capture', expected=1)
        assert failed['status'] == 'not_satisfied' and any(c['status'] == 'failed' for c in failed['checks'])
        bug = run.cli('check-bug', project, 'check')['revision']
        assert run.cli('observe-bug', project, 'eval', '--revision', bug)['stdout'] == '43\n'
        session = run.cli('prepare-debug', project, 'debug', '--revision', bug, '--kind', 'nex-dap',
                          '--task-timeout-ms', '60000', '--task-workers', '2')
        assert session['nex_adapter']['available'], 'actual LLDB/DAP is required'
        manifest = Path(session['manifest'])
        run.report['debug'] = {'revision': bug, 'build_key': session['build_key'],
            'manifest': str(manifest), 'manifest_sha256': sha(manifest),
            'program_sha256': sha(session['launch']['program'])}
        dap = DAP(session['adapter_command'], project, run.output, run.env)
        try:
            dap.request('initialize', {'adapterID': 'nex', 'pathFormat': 'path', 'linesStartAt1': True, 'columnsStartAt1': True})
            launch = dap.send('launch', dict(session['launch'], disableASLR=False))
            dap.event('initialized')
            placed = dap.request('setFunctionBreakpoints', {'breakpoints': [{'name': 'quality_repair::child'}]})
            assert placed['breakpoints'][0]['verified']
            dap.request('configurationDone')
            dap.response(launch)
            stop = dap.event('stopped')
            assert stop['allThreadsStopped']
            selected = dap.request('threads')['nex']['selected']
            stack = dap.request('stackTrace', {'threadId': selected})['stackFrames']
            assert [frame['name'] for frame in stack] == ['quality_repair::child', 'quality_repair::main']
            frame = stack[0]['id']
            scope = dap.request('scopes', {'frameId': frame})['scopes'][0]['variablesReference']
            values = dap.request('variables', {'variablesReference': scope})['variables']
            assert next(v['value'] for v in values if v['name'] == 'input') == '41'
            watch = dap.request('evaluate', {'expression': 'input+1', 'frameId': frame, 'context': 'watch'})
            assert watch['nex']['value'] == '42'
            initialized = False
            for index in range(3):
                dap.request('next', {'threadId': selected, 'singleThread': True})
                dap.event('stopped')
                if index == 0:
                    stale = dap.send('variables', {'variablesReference': scope})
                    rejected = dap.wait(lambda m: m.get('type') == 'response' and m.get('request_seq') == stale)
                    assert rejected.get('success') is False
                fresh = dap.request('stackTrace', {'threadId': selected})['stackFrames'][0]['id']
                assert fresh != frame
                reference = dap.request('scopes', {'frameId': fresh})['scopes'][0]['variablesReference']
                locals_ = dap.request('variables', {'variablesReference': reference})['variables']
                if any(v['name'] == 'initialized' and v['value'] == '41' for v in locals_):
                    observed = dap.request('evaluate', {'expression': 'initialized+1', 'frameId': fresh, 'context': 'watch'})
                    assert observed['nex']['value'] == '42'
                    initialized = True
                    break
            assert initialized
            dap.request('continue', {'threadId': selected})
            assert dap.event('exited')['exitCode'] == 0
            dap.event('terminated')
            stdout = ''.join(row['receive'].get('body', {}).get('output', '') for row in dap.trace
                if row.get('receive', {}).get('event') == 'output' and
                row['receive'].get('body', {}).get('category') == 'stdout')
            # LLDB's target pseudo-terminal can publish CRLF. Retain the raw
            # protocol and accept only the exact expected single output line.
            assert stdout in ('43\n', '43\r\n'), stdout
            run.report['debug']['raw_stdout'] = stdout
        finally:
            dap.close()
        assert sha(manifest) == run.report['debug']['manifest_sha256']
        patch = project / 'repair.json'
        patch.write_text(json.dumps({'expected_revision': bug, 'replacements': [
            {'name': 'quality_repair::helper', 'source': 'pub fn helper(x:i64)->i64{return x+1;}'}]}) + '\n')
        fixed = run.cli('apply-repair', project, 'apply', '--patch', patch)['revision']
        assert fixed != bug
        assert run.cli('repaired-reference', project, 'eval', '--revision', fixed)['stdout'] == '42\n'
        assert run.cli('repaired-release', project, 'run', '--revision', fixed, '--profile', 'release')['stdout'] == '42\n'
        assert run.cli('repaired-typescript', project, 'test', '--revision', fixed, '--target', 'web')['ok']
        source_before = source.read_bytes()
        graph_before = rows(project)
        source.write_text(source.read_text().replace('assert(child(41)==42);', 'assert(true);'))
        try:
            refused = run.cli('reject-weakened-test', project, 'task', taskfile, '--kind', 'check', expected=1)
            assert refused['code'] == 'E_TASK_TEST_CHANGED'
            # prepare() archives a checked candidate before validating task
            # intent. An unaccepted candidate may extend history; it must not
            # replace HEAD, erase prior rows or create a successful task run.
            rejected_graph = rows(project)
            assert rejected_graph['head'] == graph_before['head']
            assert rejected_graph['task_runs'] == graph_before['task_runs']
            for name, previous in graph_before.items():
                assert set(map(repr, previous)) <= set(map(repr, rejected_graph[name])), name
            run.report['rejected_candidate_history_rows_added'] = {
                name: len(rejected_graph[name]) - len(previous) for name, previous in graph_before.items()
                if len(rejected_graph[name]) != len(previous)}
        finally:
            source.write_bytes(source_before)
        accepted = run.cli('accept-original-contract', project, 'task', taskfile, '--kind', 'run',
            '--revision', fixed, '--task-hash', task_hash, '--directory', run.output / 'accepted-capture')
        assert accepted['task_hash'] == task_hash and all(c['status'] == 'passed' for c in accepted['checks'])
        assert taskfile.read_bytes() == original_task_bytes
        measured = run.cli('repaired-profile', project, 'profile', '--revision', fixed, '--events', '0',
                           '--task-steps', '200000', '--task-timeout-ms', '5000', '--task-workers', '2')
        saved = profile(Path(measured['output']), actual['compiler_build'])
        assert saved['revision'] == fixed and saved['build_key'] == measured['build_key']
        budget = copy.deepcopy(task)
        next(c for c in budget['checks'] if c['kind'] == 'profile')['budget']['max_calls']['quality_repair::helper'] = '0'
        budgetfile = project / 'budget.json'
        budgetfile.write_text(json.dumps(budget, indent=2) + '\n')
        failing = run.cli('failing-call-budget', project, 'task', budgetfile, '--kind', 'run', '--revision', fixed,
                          '--directory', run.output / 'failed-budget', expected=1)
        assert next(c for c in failing['checks'] if c['id'] == 'profile')['status'] == 'failed'
        receipt = Path(accepted['output'])
        captured_inputs = files(receipt.parent / 'inputs')
        graph_before = rows(project)
        source.unlink()
        taskfile.unlink()
        budgetfile.unlink()
        replay = run.cli('source-deleted-replay', project, 'task', receipt, '--kind', 'replay',
                         '--directory', run.output / 'replay')
        assert replay['task_hash'] == task_hash and replay['programs'] == accepted['programs']
        assert all(c['status'] == 'passed' for c in replay['checks'])
        assert rows(project) == graph_before and files(receipt.parent / 'inputs') == captured_inputs
        assert run.cli('archived-bug-preserved', project, 'eval', '--revision', bug)['stdout'] == '43\n'
        run.guard()
        run.report.update(ok=True, state='passed', phase='complete', bug_revision=bug, repaired_revision=fixed,
            task_hash=task_hash, initialized_local_and_watch=True, stale_reference_rejected=True,
            original_intent_preserved=True, weakened_test_rejected=True, profile_calls_balanced=True,
            failing_budget_detected=True, source_deleted_replay=True, old_bug_revision_preserved=True)
    except BaseException as error:
        run.report.update(state='failed', error=repr(error))
        traceback.print_exc()
    finally:
        run.save()
        print(json.dumps({key: run.report.get(key) for key in ('schema', 'ok', 'state', 'seconds', 'error')}))
    return 0 if run.report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
