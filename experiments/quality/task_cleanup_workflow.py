#!/usr/bin/env python3
"""Opt-in public CPU/task part of Q4; physical host-operation fences are separate."""
import argparse
import json
from pathlib import Path
import traceback

from acceptance_support import Evidence, sha


CPU = '''module quality_cpu;
fn work(n:i64)->i64{var i:i64=0;var total:i64=0;while i<2000{total=total+n+i;i=i+1;}return total;}
fn values()->list<i64>{return parallel_map([0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15],work,4);}
fn main()->unit!{io}{print(values()[15]);}
test fn ordered()->unit{let got:list<i64>=values();assert(len(got)==16);assert(got[0]==1999000);assert(got[15]==2029000);}
'''
CANCEL = '''module quality_cancel;
fn solve()->i64!{task}{return with_tasks(1,fn(scope:task_scope)->i64!{task}{
 let ready:channel<bool>=channel_new<bool>(scope,0);
 let child:task<i64>=task_spawn(scope,fn()->i64!{task}{
  let held:list<str>=["owned","Я🦊"];
  assert(task_send(ready,true));while true{task_yield();}return len(held);
 });
 assert(unwrap(task_recv(ready)));assert(task_cancel(child));return 42;
});}
fn main()->unit!{io,task}{print(solve());}
test fn cancelled()->unit!{task}{assert(solve()==42);}
'''
EXPECTED = '''module quality_expected;
fn child()->result<str>!{task}{let held:list<str>=["owned","Я🦊"];task_yield();
 assert(len(held)==2);return err<str>("EXPECTED","ordinary child error");}
fn solve()->i64!{task}{return with_tasks(1,fn(scope:task_scope)->i64!{task}{
 let job:task<result<str>>=task_spawn(scope,child);
 let result:result<str>=task_wait(job);assert(error_code(result)=="EXPECTED");return 42;
});}
fn main()->unit!{io,task}{print(solve());}
test fn expected()->unit!{task}{assert(solve()==42);}
'''
UNOBSERVED = '''module quality_unobserved;
fn main()->unit!{task}{let result:i64=with_tasks(1,fn(scope:task_scope)->i64!{task}{
 let child:task<i64>=task_spawn(scope,fn()->i64!{task}{
  let held:list<str>=["owned","Я🦊"];task_yield();return len(held)/0;
 });return 42;
});}
test fn child_failure()->unit!{task}{main();}
'''
ORDERED_ERROR = '''module quality_ordered_error;
fn work(n:i64)->i64{let held:list<str>=["owned",str(n)];if n==0{return 1/0;}assert(false);return len(held);}
fn main()->unit{let values:list<i64>=parallel_map([0,1],work,2);}
test fn failure()->unit{main();}
'''
GLOBAL_LIMIT = '''module quality_global_limit;
fn recurse(n:i64)->i64{return recurse(n+1);}
fn work(n:i64)->i64{if n==0{return 1/0;}return recurse(n);}
fn main()->unit{let values:list<i64>=parallel_map([0,1],work,2);}
test fn failure()->unit{main();}
'''


def profile_invariants(value, expected_schema):
    assert value['schema'] == expected_schema
    if expected_schema == 'nex.profile/2':
        assert value['completeness']['aggregates'] and value['completeness']['memory']
    else:
        # Existing synchronous CPU maps retain their original profile/1 format.
        # Its explicit counters, rather than invented v2 fields, prove that no
        # source/frame/allocation accounting was dropped.
        assert all(value[key] == 0 for key in
                   ('dropped_functions', 'dropped_frames', 'dropped_allocations', 'untracked_frees'))
    assert value['memory'], 'missing owned-pool accounting'
    for pool in value['memory']:
        assert pool['live'] == pool['live_shallow_bytes'] == 0, pool
        assert pool['allocations'] == pool['frees'], pool
    for function in value['functions']:
        assert function['calls'] == function['completed'] + function['aborted'], function
    for task in value.get('tasks', []):
        assert task['terminal'] and task['active_invocations'] == 0, task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler', type=Path, required=True)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run = Evidence(args.compiler, args.resources, args.output, 'nex.quality-task-cleanup-public/1')
    run.report.update(runner_sha256=sha(Path(__file__)), complete_q4=False,
        scope='Public CPU/task semantic observations. Source cancellation handshake proves '
              'child initialization, not physical completion of arbitrary host I/O. '
              'Q4 additionally requires matching controlled external-operation/DSO fence evidence.')
    try:
        actual = run.cli('describe', run.output, 'describe', '--field', 'version')
        assert actual['value'] == '0.21'
        run.report.update(language=actual['value'], toolchain=actual['toolchain'],
                          compiler_build=actual['compiler_build'])
        cases = [('cpu', CPU, '2029000\n', None), ('cancel', CANCEL, '42\n', None),
                 ('expected', EXPECTED, '42\n', None), ('unobserved', UNOBSERVED, '', 'E_DIV_ZERO'),
                 ('ordered-error', ORDERED_ERROR, '', 'E_DIV_ZERO'),
                 ('global-limit', GLOBAL_LIMIT, '', 'E_LIMIT')]
        run.report['cases'] = []
        for name, source, stdout, error in cases:
            project = run.output / name
            project.mkdir()
            entry = project / 'main.nex'
            entry.write_text(source)
            (project / 'nex.json').write_text(json.dumps({
                'schema': 'nex.project/1', 'language': '0.21', 'entry': 'main.nex'}) + '\n')
            checked = run.cli(name + '-check', project, 'check')
            row = {'name': name, 'revision': checked['revision'], 'source_sha256': sha(entry),
                   'expected_stdout': stdout, 'expected_error': error}
            run.report['cases'].append(row)
            reference = run.cli(name + '-reference', project, 'eval', expected=1 if error else 0)
            if error:
                assert reference['code'] == error, reference
            else:
                assert reference['stdout'] == stdout
            # The CLI propagates actual native status (70 for checked traps).
            native = run.cli(name + '-native', project, 'run', '--profile', 'release',
                             expected=70 if error else 0)
            assert native['stdout'] == stdout
            if error:
                assert native['exit_code'] == 70 and native['stderr'].startswith(error + ':'), native
                assert 'E_INTERNAL_LEAK' not in native['stderr']
            web = run.cli(name + '-typescript', project, 'test', '--target', 'web',
                          expected=1 if error else 0)
            if error:
                assert error in json.dumps(web), web
            else:
                assert web['ok']
                assert run.cli(name + '-native-tests', project, 'test')['ok']
            measured = run.cli(name + '-profile', project, 'profile', '--events', '10000',
                               '--scenario', 'quality ' + name, expected=70 if error else 0)
            assert measured['stdout'] == stdout
            if error:
                assert measured['exit_code'] == 70 and error in measured['stderr']
            raw = Path(measured['output'])
            value = json.loads(raw.read_text())
            profile_invariants(value, 'nex.profile/2' if name in
                               ('cancel', 'expected', 'unobserved') else 'nex.profile/1')
            row['profile'] = {'path': str(raw), 'sha256': sha(raw)}
            if name == 'cpu':
                events = [event for event in value['traceEvents'] if event.get('name') == 'quality_cpu::work']
                assert len(events) == 16
                threads = {event['tid'] for event in events}
                assert len(threads) >= 2
                assert any(a['tid'] != b['tid'] and max(a['ts'], b['ts']) <
                           min(a['ts'] + a['dur'], b['ts'] + b['dur']) for a in events for b in events)
                row.update(actual_threads=len(threads), overlapping_workers=True)
            if name == 'cancel':
                assert value['tasks'] and any(task['terminal'] for task in value['tasks'])
                row['initialized_child_cancelled'] = True
            row['passed'] = True
            run.save()
        run.guard()
        run.report.update(ok=True, state='passed', phase='public-observations-complete',
                          ordered_results=True, ordinary_child_result=True,
                          unobserved_child_failure=True, lowest_index_error=True,
                          fatal_limit_precedence=True, balanced_profile_cleanup=True)
    except BaseException as error:
        run.report.update(state='failed', error=repr(error))
        traceback.print_exc()
    finally:
        run.save()
        print(json.dumps({key: run.report.get(key) for key in
                         ('schema', 'ok', 'state', 'seconds', 'complete_q4', 'error')}))
    return 0 if run.report['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
