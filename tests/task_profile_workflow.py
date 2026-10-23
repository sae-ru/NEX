"""Actual local task profiling, graph provenance, limits and reviewed replay."""
import json
from pathlib import Path
import unittest
import support as harness

SOURCE = '''module measured;
fn helper(x:i64)->i64{return x+1;}
fn leaf()->i64!{task}{task_yield();return helper(41);}
fn main()->unit!{io,task}{
 print(with_tasks(2,fn(scope:task_scope)->i64!{task}{
  let child:task<i64>=task_spawn(scope,leaf);task_yield();return task_wait(child);
 }));
}
'''
LIMITS = {'steps': 200000, 'timeout_ms': 2000, 'workers': 2}


class TaskProfileWorkflow(harness.ToolchainCase):
    def limits(self, execution, configured=LIMITS, effective=None):
        self.assertEqual(execution['configured'], configured)
        self.assertEqual(execution['effective'], effective or configured)
        self.assertEqual(execution['executor_workers'], (effective or configured)['workers'])
        self.assertTrue(execution['cooperative_deadline'])

    def measured(self, report, project=False):
        self.assertEqual(report['schema'], 'nex.profile-session/2')
        self.assertEqual(report['stdout'], '42\n')
        self.assertNotIn('invocations', report)
        self.assertNotIn('segments', report)
        self.assertNotIn('tasks', report)
        self.assertEqual(report['function_sort_key'], 'self_cpu_ns')
        saved = json.loads(Path(report['output']).read_text())
        self.assertEqual(saved['schema'], 'nex.profile/2')
        self.assertEqual(saved['language'], '0.20')
        self.assertEqual(saved['build']['language'], saved['language'])
        self.assertEqual(saved['build']['revision'], saved['revision'])
        self.assertEqual(saved['build']['build_key'], saved['build_key'])
        self.assertEqual(saved['build']['compiler_build'], self.cli('describe', '--kind', 'index')['compiler_build'])
        self.assertFalse(saved['tracy'])
        self.assertTrue(saved['completeness']['aggregates'])
        self.assertTrue(saved['completeness']['memory'])
        functions = {f['name']: f for f in saved['functions']}
        for name in ['main', 'leaf', 'helper']:
            f = functions['measured::' + name]
            self.assertEqual((f['calls'], f['completed'], f['aborted']), (1, 1, 0), f)
            self.assertGreaterEqual(f['inclusive_cpu_ns'], f['self_cpu_ns'])
            self.assertGreaterEqual(f['active_elapsed_ns'], f['self_active_elapsed_ns'])
            self.assertNotIn('self_ns', f)
            self.assertTrue(Path(f['file']).is_file())
            if project:
                self.assertIsNone(f['node_id'])
                self.assertEqual(f['identity_scope'], 'captured_project')
            else:
                self.assertIsInstance(f['node_id'], str)
        self.assertTrue(saved['tasks'])
        self.assertTrue(all(t['terminal'] and t['active_invocations'] == 0 for t in saved['tasks']))
        for pool in saved['memory']:
            self.assertEqual(pool['live'], 0, pool)
            self.assertEqual(pool['live_shallow_bytes'], 0, pool)
            self.assertEqual(pool['allocations'], pool['frees'], pool)
        return saved

    def test_direct_zero_events_limits_and_archived_source_deleted_profile(self):
        self.source(SOURCE)
        arguments = ['--task-steps', '200000', '--task-timeout-ms', '2000', '--task-workers', '2']
        report = self.cli('profile', '--events', '0', '--scenario', 'task workflow', *arguments, timeout=240)
        saved = self.measured(report)
        self.limits(saved['task_execution'])
        self.assertFalse(saved['completeness']['timeline'])
        self.assertGreater(saved['dropped_events'], 0)
        self.assertEqual(self.cli('run', '--profile', 'release', *arguments, timeout=240)['stdout'], saved['stdout'])
        graph = {n['name']: n for n in self.cli('graph')['nodes']}
        for f in saved['functions']:
            self.assertEqual((f['node_id'], f['content_hash']), (graph[f['name']]['id'], graph[f['name']]['hash']))
        self.file.unlink()
        replayed = self.cli('profile', '--revision', report['revision'], '--events', '0', *arguments, timeout=240)
        second = self.measured(replayed)
        self.assertEqual(second['revision'], saved['revision'])
        self.limits(second['task_execution'])

    def test_invalid_task_profile_options_fail_before_execution(self):
        self.source(SOURCE)
        for args in [('--task-workers', '0'), ('--task-workers', '17'), ('--task-steps', '0'),
                     ('--task-timeout-ms', '3600001'), ('--steps', '100'), ('--target', 'web')]:
            with self.subTest(args=args):
                self.assertEqual(self.cli('profile', *args, ok=False)['code'], 'E_OPTION')
        self.source('module pure;fn main()->unit{}')
        self.assertEqual(self.cli('profile', '--task-workers', '1', ok=False)['code'], 'E_OPTION')

    def project(self):
        (self.root/'app').mkdir()
        self.file = self.root/'app/main.nex'
        self.source(SOURCE)
        (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'app/main.nex'}))
        description = {'schema':'nex.project-build/1','default_configuration':'measured',
            'configurations':{'measured':{'profile':'profile','task_limits':LIMITS}},
            'components':{'app':{'kind':'executable','root':'app','entry':'app/main.nex'}}}
        (self.root/'nex.build.json').write_text(json.dumps(description))

    def test_source_only_project_records_effective_lowered_runtime_limits(self):
        self.project()
        reduced = {'steps':100000,'timeout_ms':1000,'workers':1}
        result = self.cli('project', '--kind', 'profile', '--component', 'app', '--events', '0',
                          '--', '--nex-task-steps', '100000', '--nex-task-timeout-ms', '1000', '--nex-task-workers', '1', timeout=240)
        saved = self.measured(result['observation'], project=True)
        self.limits(saved['task_execution'], effective=reduced)
        self.assertFalse(result['graph_store_opened'])
        self.assertFalse((self.root/'.nex/graph.db').exists())

    def task(self, project=False, maximum='1'):
        if project:
            value = self.cli('task', self.root/'nex.build.json', '--kind', 'init', '--component', 'app', '--configuration', 'measured')
        else:
            self.source(SOURCE)
            value = self.cli('task', self.file, '--kind', 'init')
        value['checks'] = []
        value['requirements'] = []
        check = {'id':'profile-task','kind':'profile','program':'app','target':'native','entry':'measured::main',
                 'scenario':'exact source calls across yields','budget':{'max_calls':{'measured::helper':maximum},'max_peak_handles':'10000','max_peak_objects':'10000'},'timeout_seconds':180}
        if project:
            check['configuration'] = 'measured'
        else:
            check['task_limits'] = LIMITS
        value['checks'].append(check)
        value['requirements'].append({'id':'profile-task','text':'Measure actual task source calls',
            'bindings':[{'program':'app','kind':'function','symbol':'measured::main'}], 'targets':['native'],'checks':['profile-task']})
        path = self.root/'task.json'
        path.write_text(json.dumps(value))
        return path

    def test_reviewed_direct_capture_budget_and_source_deleted_replay(self):
        task = self.task()
        run = self.cli('task', task, '--kind', 'run', '--directory', self.root/'capture', timeout=300)
        receipt = Path(run['output'])
        saved = json.loads(receipt.read_text())
        check, = saved['checks']
        self.assertEqual(check['status'], 'passed')
        self.assertEqual(check['budget_failures'], [])
        self.limits(check['task_execution'])
        report = json.loads((receipt.parent/'artifacts/profile-task/profile.json').read_text())
        self.assertEqual(report['schema'], 'nex.profile/2')
        self.assertTrue(report['completeness']['aggregates'])
        self.assertFalse(report['completeness']['timeline'])
        self.file.unlink()
        task.unlink()
        replay = self.cli('task', receipt, '--kind', 'replay', '--directory', self.root/'replay', timeout=300)
        repeated = json.loads(Path(replay['output']).read_text())
        actual, = repeated['checks']
        self.assertEqual(actual['status'], 'passed')
        self.limits(actual['task_execution'])
        self.assertEqual(repeated['programs'][0]['revision'], saved['programs'][0]['revision'])

    def test_reviewed_source_only_project_profile_and_failing_call_budget(self):
        self.project()
        task = self.task(project=True, maximum='0')
        run = self.cli('task', task, '--kind', 'run', '--directory', self.root/'failed-budget', ok=False, timeout=300)
        receipt = json.loads(Path(run['output']).read_text())
        check, = receipt['checks']
        self.assertEqual(check['status'], 'failed')
        self.assertEqual(check['budget_failures'], ['measured::helper'])
        self.limits(check['task_execution'])
        report = json.loads((Path(run['output']).parent/'artifacts/profile-task/profile.json').read_text())
        self.assertEqual(report['stdout'], '42\n')
        self.assertEqual(report['schema'], 'nex.profile/2')


if __name__ == '__main__':
    unittest.main()
