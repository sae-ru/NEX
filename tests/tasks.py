"""Task intent, candidate snapshots, acceptance evidence and owned process cleanup."""
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import sqlite3
import subprocess
import sys
import time
import unittest
import support as harness


STRUCTURED_SOURCE = '''module taskdemo;
pub fn solve()->i64 !{task}{
 return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
  let queue:channel<i64>=channel_new<i64>(scope,0);
  let captured:i64=40;
  let sender:task<unit>=task_spawn(scope,fn()->unit !{task}{
   task_yield();assert(task_send(queue,captured+2));assert(task_close(queue));
  });
  let value:i64=unwrap(task_recv(queue));task_wait(sender);
  assert(!is_ok(task_recv(queue)));return value;
 });
}
fn main()->i64 !{io,task}{print(solve());return 0;}
test fn examples()->unit !{task}{assert(solve()==42);}
'''


class Tasks(harness.ToolchainCase):
    def test_new_capture_and_replay_use_canonical_owned_output_directories(self):
        task=self.scaffold();task['checks']=[];task['requirements']=[]
        self.requirement(task,{'id':'effects','kind':'effects','target':'source',
            'symbols':['taskdemo::increment'],'allowed_effects':[]});self.save(task)
        physical=self.root/'physical-runs';physical.mkdir()
        alias=self.root/'run-alias';alias.symlink_to(physical,target_is_directory=True)
        run=self.task('run','--directory',alias/'captured')
        receipt=Path(run['output'])
        self.assertEqual(receipt,(physical/'captured/receipt.json').resolve(strict=True))
        self.assertEqual(receipt,receipt.resolve(strict=True))
        replay=self.cli('task',receipt,'--kind','replay','--directory',alias/'replayed',timeout=180)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],run['programs'])
        self.assertEqual(Path(replay['output']),(physical/'replayed/receipt.json').resolve(strict=True))

    def test_nested_receipt_replay_keeps_ancestor_and_source_project_graphs_unchanged(self):
        ancestor=self.root;outer=ancestor/'ancestor.nex';outer.write_text('module ancestor;fn main()->i64{return 71;}')
        (ancestor/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.23','entry':'ancestor.nex'}));self.cli('check',outer)
        child=ancestor/'child';child.mkdir();(child/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.23','entry':'main.nex'}))
        self.root=child;self.file=child/'main.nex';task=self.scaffold();task['checks']=[];task['requirements']=[]
        self.requirement(task,{'id':'effects','kind':'effects','target':'source','symbols':['taskdemo::increment'],'allowed_effects':[]});self.save(task)
        run=self.task('run','--directory',ancestor/'captures/run');receipt=Path(run['output'])
        before=harness.database_rows(ancestor/'.nex/graph.db');source_before=harness.database_rows(child/'.nex/graph.db')
        replay=self.cli('task',receipt,'--kind','replay',timeout=180)
        self.assertTrue(replay['ok']);self.assertEqual(replay['programs'],run['programs'])
        self.assertEqual(harness.database_rows(ancestor/'.nex/graph.db'),before)
        self.assertEqual(harness.database_rows(child/'.nex/graph.db'),source_before)
        state=Path(replay['output']).parent/'state';self.assertTrue((state/'.nex/graph.db').is_file())
        self.assertFalse((receipt.parent/'.nex/graph.db').exists())
        self.assertEqual(self.cli('task',state/'task.json','--kind','history')['runs'][0]['status'],'passed')
        saved=json.loads(Path(replay['output']).read_text());ids={row[2] for row in harness.database_rows(state/'.nex/graph.db')[1]['node_ids']}
        self.assertTrue(all(binding['node_id'] in ids for group in saved['bindings'].values() for binding in group if 'node_id' in binding))
        self.assertIn(receipt.parent/'.nex/tasks/runs',Path(replay['output']).parents)

    def test_replay_reads_a_readonly_receipt_and_keeps_its_tree_unchanged(self):
        task=self.scaffold();task['checks']=[];task['requirements']=[]
        self.requirement(task,{'id':'effects','kind':'effects','target':'source','symbols':['taskdemo::increment'],'allowed_effects':[]});self.save(task)
        run=self.task('run','--directory',self.root/'saved-run');folder=Path(run['output']).parent
        import hashlib
        before={p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()}
        paths=sorted(folder.rglob('*'),key=lambda p:len(p.parts),reverse=True)
        for p in paths:
            if not p.is_symlink():p.chmod(0o500 if p.is_dir() else 0o400)
        folder.chmod(0o500)
        try:
            replay=self.cli('task',folder/'receipt.json','--kind','replay','--directory',self.root/'new-run',timeout=180)
            self.assertTrue(replay['ok']);self.assertEqual(before,{p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.rglob('*') if p.is_file()})
            self.assertFalse((folder/'.nex').exists())
        finally:
            folder.chmod(0o700)
            for p in reversed(paths):
                if not p.is_symlink():p.chmod(0o700 if p.is_dir() else 0o600)

    def scaffold(self, source=None):
        self.source(source or '''module taskdemo;
pub fn increment(x: i64) -> i64 { return x + 1; }
fn main() -> i64 !{io} { print(increment(2)); return 0; }
test fn examples() -> unit { assert(increment(2) == 3); }
''')
        task = self.cli('task', self.file, '--kind', 'init')
        self.taskfile = self.root / 'task.json'
        self.save(task)
        return task

    def save(self, task):
        self.taskfile.write_text(json.dumps(task, indent=2) + '\n')

    def task(self, kind='run', *args, **kwargs):
        return self.cli('task', self.taskfile, '--kind', kind, *args, timeout=180, **kwargs)

    def requirement(self, task, check, symbol='taskdemo::increment', kind='function'):
        check.setdefault('program', 'app')
        task['checks'].append(check)
        task['requirements'].append({'id': check['id'], 'text': 'Exercise an explicit acceptance condition',
            'bindings': [{'program': check['program'], 'kind': kind, 'symbol': symbol}],
            'targets': [check['target']], 'checks': [check['id']]})

    def structured_receipt(self, receipt, revision):
        """Check actual backend observations, not only acceptance status flags."""
        folder=Path(receipt).parent;saved=json.loads(Path(receipt).read_text())
        self.assertEqual(saved['status'],'passed')
        self.assertEqual(saved['programs'][0]['revision'],revision)
        self.assertTrue(all(row['status']=='passed' for row in saved['checks']))
        rows={row['id']:row for row in saved['checks']}
        for name,target in [('test-0','native'),('test-task-web','web')]:
            test,=rows[name]['tests'];self.assertEqual(test['symbol'],'taskdemo::examples');self.assertTrue(test['ok'])
            command=json.loads((folder/test['receipt']).read_text())
            self.assertEqual(command['exit_code'],0);self.assertFalse(command['timed_out']);self.assertFalse(command['output_limit']);self.assertEqual(command['interrupted'],0)
            actual,=command['response']['tests']
            self.assertEqual(actual['name'],'taskdemo::examples');self.assertTrue(actual['ok']);self.assertFalse(actual.get('skipped',False))
            self.assertEqual(actual['native'],target=='native');self.assertEqual(actual['web'],target=='web')
        observed=rows['observe-task']
        for backend in ['reference','native']:
            command=json.loads((folder/observed[backend]).read_text())
            self.assertEqual(command['exit_code'],0)
            self.assertEqual(command['response']['stdout'],'42\n')
            self.assertEqual(command['response']['value' if backend=='reference' else 'exit_code'],0)
        self.assertEqual(rows['task-effects']['violations'],[])
        self.assertEqual(rows['entry-effects']['violations'],[])
        module=folder/'artifacts/task-module/module'
        mapping=json.loads((module/'nex-map.json').read_text())
        self.assertEqual(mapping['schema'],'nex.typescript-map/1');self.assertEqual(mapping['language'],saved['language'])
        self.assertEqual(mapping['revision'],revision);self.assertEqual(mapping['execution'],'task-generator')
        self.assertTrue((module/'nex-task-runtime.ts').is_file())
        for path in ['runtime/nex_task_application.cpp','web/nex-task-runtime.ts']:
            self.assertTrue((folder/'inputs/resources'/path).is_file())
        return saved

    def test_public_structured_source_task_contract_native_typescript_and_source_deleted_replay(self):
        descriptor=self.cli('describe');self.assertTrue(descriptor['structured_tasks_runtime']['source_support'])
        schema=json.loads((harness.REPO/'llm/task.schema.json').read_text())
        effect_shape=next(value for value in schema['properties']['checks']['items']['oneOf']
                          if value['properties']['kind'].get('const')=='effects')
        self.assertEqual(set(effect_shape['properties']['allowed_effects']['items']['enum']),set(descriptor['effects']))
        self.source('module retained_head;fn main()->i64{return 71;}')
        head=self.cli('check')['revision'];database=self.root/'.nex/graph.db';original=harness.database_rows(database)
        task=self.scaffold(STRUCTURED_SOURCE);candidate=task['programs'][0]['baseline_revision']
        self.assertEqual(task['language'],descriptor['version']);self.assertNotEqual(candidate,head)
        context=self.cli('context','--symbol','taskdemo::solve','--revision',candidate)
        self.assertEqual(context['revision'],candidate)
        self.assertEqual(self.cli('history')['head'],head)
        web=copy.deepcopy(next(check for check in task['checks'] if check['kind']=='test'))
        web.update(id='test-task-web',target='web')
        self.requirement(task,web,'taskdemo::solve')
        self.requirement(task,{'id':'observe-task','kind':'run','target':'native','entry':'taskdemo::main',
                              'expect':{'stdout':'42\n','exit_code':0}},'taskdemo::solve')
        self.requirement(task,{'id':'task-effects','kind':'effects','target':'source','symbols':['taskdemo::solve'],
                              'allowed_effects':['task'],'allowed_realms':['shared']},'taskdemo::solve')
        self.requirement(task,{'id':'entry-effects','kind':'effects','target':'source','symbols':['taskdemo::main'],
                              'allowed_effects':['io','task'],'allowed_realms':['shared']},'taskdemo::main')
        self.requirement(task,{'id':'task-module','kind':'build','target':'web','mode':'module','entry':'taskdemo::solve'},'taskdemo::solve')
        self.save(task);prepared=harness.database_rows(database)
        self.assertEqual(prepared[0],original[0])
        for name,rows in original[1].items():
            self.assertLessEqual(set(rows),set(prepared[1][name]),name)
        self.assertEqual(prepared[1]['head'],original[1]['head'])
        checked=self.task('check','--revision',candidate)
        self.assertTrue(checked['ok']);self.assertTrue(all(c['status']=='ready' for c in checked['checks']))
        self.assertEqual(harness.database_rows(database),prepared)
        self.assertFalse((self.root/'.nex/tasks').exists());self.assertFalse((self.root/'.nex/build').exists())
        result=self.task('run','--revision',candidate,'--task-hash',checked['task_hash'],'--directory',self.root/'structured-run')
        self.assertEqual(result['task_hash'],checked['task_hash'])
        saved=self.structured_receipt(result['output'],candidate)
        after=harness.database_rows(database);self.assertEqual(after[0],prepared[0])
        for name,rows in prepared[1].items():
            if name!='task_runs':self.assertEqual(after[1][name],rows,name)
        self.assertEqual(self.task('history')['runs'][0]['status'],'passed')
        self.file.unlink();self.taskfile.unlink()
        receipt=Path(result['output']);inputs=receipt.parent/'inputs'
        import hashlib
        before_inputs={p.relative_to(inputs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in inputs.rglob('*') if p.is_file()}
        replay=self.cli('task',receipt,'--kind','replay','--directory',self.root/'structured-replay',timeout=180)
        self.assertEqual(replay['task_hash'],result['task_hash']);self.assertEqual(replay['programs'],result['programs'])
        self.structured_receipt(replay['output'],candidate)
        self.assertEqual(harness.database_rows(database),after)
        self.assertEqual(self.cli('history')['head'],head)
        self.assertEqual(before_inputs,{p.relative_to(inputs).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                                      for p in inputs.rglob('*') if p.is_file()})
        self.assertEqual(json.loads(receipt.read_text()),saved)
        state=Path(replay['output']).parent/'state'
        self.assertTrue((state/'.nex/graph.db').is_file())
        self.assertEqual(self.cli('task',state/'task.json','--kind','history')['runs'][0]['status'],'passed')

    def test_structured_task_effect_allowlist_omission_and_unknown_effect_preserve_graph(self):
        task=self.scaffold(STRUCTURED_SOURCE);task['checks']=[];task['requirements']=[]
        self.requirement(task,{'id':'allowed','kind':'effects','target':'source','symbols':['taskdemo::solve'],
                              'allowed_effects':['task']},'taskdemo::solve')
        self.requirement(task,{'id':'omitted','kind':'effects','target':'source','symbols':['taskdemo::solve'],
                              'allowed_effects':[]},'taskdemo::solve')
        self.save(task);database=self.root/'.nex/graph.db';before=harness.database_rows(database)
        # A valid policy can fail acceptance: preflight is not a passed effects observation.
        checked=self.task('check');self.assertTrue(checked['ok']);self.assertEqual(harness.database_rows(database),before)
        result=self.task('run','--task-hash',checked['task_hash'],ok=False)
        self.assertEqual(result['status'],'not_satisfied')
        rows={row['id']:row for row in result['checks']}
        self.assertEqual(rows['allowed']['status'],'passed');self.assertEqual(rows['allowed']['violations'],[])
        self.assertEqual(rows['omitted']['status'],'failed')
        self.assertTrue(rows['omitted']['violations'])
        self.assertTrue(all(row.get('effect')=='task' for row in rows['omitted']['violations']))
        self.assertIn({'symbol':'taskdemo::solve','effect':'task'},rows['omitted']['violations'])
        after=harness.database_rows(database);self.assertEqual(before[0],after[0])
        for name,values in before[1].items():
            if name!='task_runs':self.assertEqual(after[1][name],values,name)
        self.assertEqual(self.task('history')['runs'][0]['status'],'not_satisfied')
        for effect in ['async','network']:
            invalid=copy.deepcopy(task);invalid['checks'][0]['allowed_effects']=['task',effect];self.save(invalid)
            for kind in ['check','run']:
                destination=self.root/('unknown-'+effect+'-'+kind)
                arguments=[] if kind=='check' else ['--directory',destination]
                error=self.task(kind,*arguments,ok=False)
                self.assertEqual(error['code'],'E_TASK');self.assertIn('unknown effect',error['message'])
                self.assertFalse(destination.exists());self.assertEqual(harness.database_rows(database),after)

    def test_scaffold_head_preservation_selection_and_readonly_check(self):
        task = self.scaffold()
        old = self.cli('check')['revision']
        original = self.file.read_text()
        self.file.write_text(original.replace('x + 1', 'x + 2'))
        fresh = self.cli('task', self.file, '--kind', 'init')
        self.assertNotEqual(fresh['programs'][0]['baseline_revision'], old)
        self.assertEqual(self.cli('graph')['revision'], old)
        self.file.write_text(original)
        check = self.task('check')
        self.assertTrue(check['ok'])
        self.assertFalse((self.root / '.nex/tasks').exists())
        self.assertFalse((self.root / '.nex/build').exists())
        self.assertTrue(check['bindings']['test-0'][0]['node_id'])
        selected = self.cli('test', '--symbol', 'taskdemo::examples')
        self.assertEqual([r['name'] for r in selected['tests']], ['taskdemo::examples'])
        self.assertEqual(self.cli('test', '--symbol', 'main', ok=False)['code'], 'E_TEST')

    def test_acceptance_evidence_proof_profile_observations_and_history(self):
        task = self.scaffold()
        contract = self.cli('contract', '--symbol', 'increment')
        contract['functions'][0].update(requires=['x < 9223372036854775807'], ensures=['result == x + 1'])
        contract_path = self.root / 'proof.json'
        contract_path.write_text(json.dumps(contract))
        intent = self.cli('contract', '--kind', 'intent', '--contracts', contract_path)['intent_hash']
        self.requirement(task, {'id': 'proof', 'kind': 'verify', 'target': 'source', 'contracts': 'proof.json', 'intent_hash': intent})
        self.requirement(task, {'id': 'observe', 'kind': 'run', 'target': 'native', 'entry': 'taskdemo::main', 'expect': {'stdout': '3\n', 'exit_code': 0}})
        self.requirement(task, {'id': 'effects', 'kind': 'effects', 'target': 'source', 'symbols': ['taskdemo::increment'], 'allowed_effects': [], 'allowed_realms': ['shared']})
        self.requirement(task, {'id': 'measure', 'kind': 'profile', 'target': 'native', 'entry': 'taskdemo::main', 'scenario': 'increment once', 'budget': {'max_peak_handles': '0', 'max_calls': {'taskdemo::increment': '1'}}})
        web = copy.deepcopy(task['checks'][0]); web.update(id='test-web', target='web')
        self.requirement(task, web)
        self.save(task)
        checked = self.task('check')
        result = self.task('run', '--task-hash', checked['task_hash'])
        self.assertTrue(all(r['status'] == 'passed' for r in result['requirements']))
        receipt = Path(result['output'])
        saved = json.loads(receipt.read_text())
        self.assertEqual(saved['task_hash'], checked['task_hash'])
        inputs = json.loads((receipt.parent / 'inputs/manifest.json').read_text())
        self.assertEqual(inputs['task_hash'], checked['task_hash'])
        self.assertIn('inputs/programs/app.json', inputs['files'])
        self.assertTrue((receipt.parent / 'artifacts/build-native/app').is_file())
        history = self.task('history')
        self.assertEqual(history['runs'][0]['status'], 'passed')
        self.assertEqual(history['runs'][0]['run_id'], saved['run_id'])
        report = json.loads((receipt.parent / 'artifacts/measure/profile.json').read_text())
        self.assertFalse(report['tracy'])
        self.assertEqual(report['scenario'], 'increment once')
        self.assertEqual(report['revision'], saved['programs'][0]['revision'])

    def test_same_task_accepts_repaired_archived_candidate_and_rejects_weakened_test(self):
        task = self.scaffold()
        self.file.write_text(self.file.read_text().replace('return x + 1', 'return x + 2'))
        failed = self.task(ok=False)
        self.assertEqual(failed['status'], 'not_satisfied')
        self.assertEqual(failed['checks'][0]['status'], 'failed')
        expected_hash = failed['task_hash']
        self.cli('check')
        graph = self.cli('graph')
        patch = {'expected_revision': graph['revision'], 'replacements': [{'name': 'taskdemo::increment', 'source': 'pub fn increment(x: i64) -> i64 { return x + 1; }'}]}
        patchfile = self.root / 'patch.json'; patchfile.write_text(json.dumps(patch))
        fixed = self.cli('apply', '--patch', patchfile)['revision']
        result = self.task('run', '--revision', fixed, '--task-hash', expected_hash)
        self.assertEqual(result['task_hash'], expected_hash)
        self.assertEqual(result['programs'][0]['revision'], fixed)
        self.file.write_text(self.file.read_text().replace('assert(increment(2) == 3);', 'assert(true);'))
        self.assertEqual(self.task('check', ok=False)['code'], 'E_TASK_TEST_CHANGED')
        task['goal'] = 'Changed acceptance intent'
        self.save(task)
        self.assertEqual(self.task('run', '--task-hash', expected_hash, ok=False)['code'], 'E_TASK_INTENT')

    def test_formal_intent_rebases_snapshot_but_does_not_weaken_property(self):
        task = self.scaffold()
        contract = self.cli('contract', '--symbol', 'increment')
        contract['functions'][0].update(requires=['x >= 0', 'x <= 100'], ensures=['result == x + 1'])
        path = self.root / 'proof.json'; path.write_text(json.dumps(contract))
        intent = self.cli('contract', '--kind', 'intent', '--contracts', path)['intent_hash']
        self.requirement(task, {'id': 'proof', 'kind': 'verify', 'target': 'source', 'contracts': 'proof.json', 'intent_hash': intent})
        self.save(task)
        self.file.write_text(self.file.read_text().replace('return x + 1;', 'return 1 + x;'))
        result = self.task()
        self.assertEqual(result['checks'][-1]['status'], 'passed')
        derived = json.loads((Path(result['output']).parent / 'inputs/contracts/proof.json').read_text())
        self.assertNotEqual(derived['expected_revision'], contract['expected_revision'])
        self.assertEqual(derived['functions'][0]['ensures'], contract['functions'][0]['ensures'])
        contract['functions'][0]['ensures'] = ['true']; path.write_text(json.dumps(contract))
        self.assertEqual(self.task('check', ok=False)['code'], 'E_TASK_INTENT')

    def test_replay_survives_deleted_sources_and_rejects_tampering(self):
        self.scaffold()
        original = self.task()
        receipt = Path(original['output'])
        self.file.unlink()
        self.taskfile.unlink()
        replay = self.cli('task', receipt, '--kind', 'replay', timeout=180)
        self.assertEqual(replay['status'], 'passed')
        self.assertEqual(replay['task_hash'], original['task_hash'])
        self.assertEqual(replay['programs'], original['programs'])
        self.assertNotEqual(replay['output'], original['output'])
        extra = receipt.parent / 'inputs/resources/runtime/unindexed.h'
        extra.write_text('unindexed input')
        self.assertEqual(self.cli('task', receipt, '--kind', 'replay', ok=False)['code'], 'E_TASK_INTEGRITY')
        extra.unlink()
        source = receipt.parent / 'inputs/programs/app.json'
        source.write_text(source.read_text() + ' ')
        error = self.cli('task', receipt, '--kind', 'replay', ok=False)
        self.assertEqual(error['code'], 'E_TASK_INTEGRITY')

    def test_multiple_programs_archive_selection_and_consistent_shared_sources(self):
        task = self.scaffold()
        original = self.cli('check')['revision']
        other = self.root / 'client.nex'
        other.write_text('module frontend; client fn main() -> i64 { return 7; }\n')
        client = self.cli('check', other)['revision']
        task['programs'].append({'id': 'client', 'entry': 'client.nex'})
        self.requirement(task, {'id': 'client-module', 'program': 'client', 'kind': 'build', 'target': 'web', 'entry': 'frontend::main', 'mode': 'module'}, 'frontend::main')
        self.save(task)
        candidates = self.root / 'candidates.json'; candidates.write_text(json.dumps({'app': original, 'client': client}))
        self.file.unlink(); other.unlink()
        result = self.task('run', '--candidates', candidates)
        self.assertEqual({p['revision'] for p in result['programs']}, {original, client})
        folder = Path(result['output']).parent
        self.assertTrue((folder / 'artifacts/client-module/module/program.ts').is_file())
        replay = self.cli('task', result['output'], '--kind', 'replay', timeout=180)
        self.assertTrue(replay['ok'])
        self.assertEqual(self.task('check', '--revision', original, ok=False)['code'], 'E_TASK')

    def test_no_false_success_for_unsupported_target_realm_or_unlinked_requirement(self):
        task = self.scaffold()
        task['checks'][1]['target'] = 'ios'
        task['requirements'][1]['targets'] = ['ios']
        self.save(task)
        checked = self.task('check', ok=False)
        self.assertEqual(checked['checks'][1]['status'], 'unsupported')
        result = self.task(ok=False)
        self.assertEqual(result['checks'][1]['status'], 'unsupported')
        task['requirements'][0]['targets'].append('web'); self.save(task)
        self.assertEqual(self.task('check', ok=False)['code'], 'E_TASK')
        task = self.scaffold('module taskdemo; server test fn examples() -> unit { assert(true); }')
        task['checks'][0]['target'] = 'web'; task['requirements'][0]['targets'] = ['web']; self.save(task)
        self.assertEqual(self.task(ok=False)['checks'][0]['status'], 'unsupported')

    def test_budget_failures_do_not_hide_independent_checks_or_runtime_traps(self):
        task = self.scaffold('''module taskdemo;
pub fn increment(x: i64) -> i64 !{io} { print(x); return x + 1; }
fn main() -> i64 !{io} { print(increment(2)); return 0; }
fn trap() -> i64 { return 9223372036854775807 + 1; }
test fn examples() -> unit !{io} { assert(increment(2) == 3); }
''')
        self.requirement(task, {'id': 'effects', 'kind': 'effects', 'target': 'source', 'symbols': ['taskdemo::increment'], 'allowed_effects': []})
        self.requirement(task, {'id': 'measure', 'kind': 'profile', 'target': 'native', 'entry': 'taskdemo::main', 'scenario': 'too many calls', 'budget': {'max_calls': {'taskdemo::increment': '0'}}})
        self.requirement(task, {'id': 'trap', 'kind': 'run', 'target': 'native', 'entry': 'taskdemo::trap', 'expect': {'stdout': '', 'exit_code': 70, 'runtime_code': 'E_OVERFLOW'}}, 'taskdemo::trap')
        self.save(task)
        result = self.task(ok=False)
        self.assertEqual([c['status'] for c in result['checks']], ['passed', 'passed', 'failed', 'failed', 'passed'])
        self.assertEqual(result['checks'][2]['violations'][0]['effect'], 'io')
        self.assertEqual(result['checks'][3]['budget_failures'], ['taskdemo::increment'])

    def test_api_server_web_application_and_native_library_deliverables(self):
        task = self.scaffold('''module taskdemo;
import "std/web.nex" as web;
client fn title() -> str { return "Contract application"; }
client fn initial() -> i64 { return 0; }
client fn update(state: i64, event: web::Event) -> i64 { return state + 1; }
client fn view(state: i64) -> web::View { return web::text(str(state)); }
server fn sentinel() -> str { return "SERVER_ONLY_TASK_SENTINEL"; }
client test fn transitions() -> unit { assert(update(initial(), web::Event("click", "", "/")) == 1); }
''')
        service = self.root / 'server.nex'
        service.write_text('''module service;
import "std/api.nex" as api;
import "std/http.nex" as http;
pub struct Payload { value: i64; }
endpoint echo_route("POST", "/api/echo") = echo;
server fn echo(context: api::Context, input: Payload) -> result<Payload> { return ok(input); }
server fn handle(request: http::Request) -> http::Response { return http::Response(200, "ok", "text/plain"); }
server test fn echo_test() -> unit { assert(unwrap(echo(api::Context("alice", "req"), Payload(7))).value == 7); }
''')
        other = self.cli('task', service, '--kind', 'init')
        task['programs'].append({**other['programs'][0], 'id': 'service'})
        for check in other['checks']:
            check = {**check, 'id': 'service-' + check['id'], 'program': 'service'}
            self.requirement(task, check, check['tests'][0]['symbol'] if check['kind'] == 'test' else 'service::handle')
        self.requirement(task, {'id': 'api', 'program': 'service', 'kind': 'api', 'target': 'source'}, 'service::echo_route', kind='endpoint')
        self.requirement(task, {'id': 'library', 'program': 'service', 'kind': 'build', 'target': 'native', 'mode': 'library', 'entry': 'service::echo'}, 'service::Payload', kind='structure')
        self.save(task)
        result = self.task()
        folder = Path(result['output']).parent / 'artifacts'
        self.assertTrue((folder / 'build-web/dist/index.html').is_file())
        self.assertTrue((folder / 'build-web/dist/THIRD_PARTY_NOTICES.txt').is_file())
        self.assertTrue((folder / 'service-build-server/app').is_file())
        self.assertTrue((folder / 'library/libnex.a').is_file())
        openapi = json.loads((folder / 'api/generated/openapi.json').read_text())
        self.assertIn('/api/echo', openapi['paths'])
        for js in (folder / 'build-web/dist').rglob('*.js'):
            self.assertNotIn('SERVER_ONLY_TASK_SENTINEL', js.read_text())

    def test_unicode_zero_bytes_exit_status_and_malformed_task_rejection(self):
        task = self.scaffold('module taskdemo; fn main() -> i64 !{io} { print("Unicode \u0410\U0001f98a\\u0000"); return 257; }')
        self.requirement(task, {'id': 'observe', 'kind': 'run', 'target': 'native', 'entry': 'taskdemo::main', 'expect': {'stdout': 'Unicode \u0410\U0001f98a\x00\n', 'exit_code': 1}}, 'taskdemo::main')
        self.save(task)
        self.assertTrue(self.task()['ok'])
        invalid = copy.deepcopy(task); invalid['checks'][0]['command'] = 'unexpected shell step'; self.save(invalid)
        self.assertEqual(self.task('check', ok=False)['code'], 'E_TASK')
        invalid = copy.deepcopy(task); invalid['programs'][0]['entry'] = '../main.nex'; self.save(invalid)
        self.assertEqual(self.task('check', ok=False)['code'], 'E_TASK')
        invalid = copy.deepcopy(task)
        self.requirement(invalid, {'id': 'duration', 'kind': 'profile', 'target': 'native', 'entry': 'taskdemo::main', 'scenario': 'host must be pinned', 'budget': {'max_duration_ns': '1'}}, 'taskdemo::main')
        self.save(invalid)
        self.assertEqual(self.task('check', ok=False)['code'], 'E_TASK')

    def test_conflicting_shared_module_candidates_are_rejected_before_execution(self):
        common = self.root / 'common.nex'
        common.write_text('module common; pub fn value() -> i64 { return 1; }')
        task = self.scaffold('module taskdemo; import "./common.nex" as common; fn main() -> i64 { return common::value(); }')
        app = self.cli('check')['revision']
        client = self.root / 'client.nex'
        client.write_text('module frontend; import "./common.nex" as common; client fn main() -> i64 { return common::value(); }')
        common.write_text('module common; pub fn value() -> i64 { return 2; }')
        changed = self.cli('check', client)['revision']
        task['programs'].append({'id': 'client', 'entry': 'client.nex'})
        self.requirement(task, {'id': 'client', 'program': 'client', 'kind': 'build', 'target': 'web', 'mode': 'module', 'entry': 'frontend::main'}, 'frontend::main')
        self.save(task)
        candidates = self.root / 'candidates.json'; candidates.write_text(json.dumps({'app': app, 'client': changed}))
        self.assertEqual(self.task('run', '--candidates', candidates, ok=False)['code'], 'E_TASK_SNAPSHOT')
        self.assertFalse((self.root / '.nex/tasks').exists())

    def process_task(self, mode):
        task = self.scaffold('module taskdemo; test fn examples() -> unit { assert(true); }')
        task['checks'][0].update(target='web', timeout_seconds=2)
        task['requirements'][0]['targets'] = ['web']; self.save(task)
        marker = self.root / 'heartbeat'
        wrapper = self.root / 'owned-node'
        child = "import time; from pathlib import Path; p=Path(" + repr(str(marker)) + ");\nwhile True: p.write_text(str(time.time_ns())); time.sleep(.03)\n"
        wrapper.write_text('#!/usr/bin/env python3\nimport subprocess,sys,time\n' +
            'subprocess.Popen([sys.executable,"-c",' + repr(child) + '])\n' +
            'time.sleep(.2)\n' + {'timeout': 'time.sleep(60)\n', 'normal': 'sys.exit(0)\n', 'output': 'sys.stderr.write("x"*(9*1024*1024)); sys.stderr.flush(); sys.exit(1)\n'}[mode])
        wrapper.chmod(0o755)
        return wrapper, marker

    def assert_stopped(self, marker):
        self.assertTrue(marker.is_file())
        first = marker.read_text(); time.sleep(.2)
        self.assertEqual(marker.read_text(), first, 'task descendant survived process-group cleanup')

    def test_timeout_stops_descendants_and_keeps_failure_receipt(self):
        wrapper, marker = self.process_task('timeout')
        result = self.task(ok=False, env={'NEX_NODE': str(wrapper)})
        self.assertEqual(result['checks'][0]['code'], 'E_TASK_TIMEOUT')
        self.assert_stopped(marker)
        self.assertTrue(Path(result['output']).is_file())
        self.assertEqual(self.task('history')['runs'][0]['status'], 'not_satisfied')

    def test_normal_exit_also_cleans_descendants_and_output_limit_is_failure(self):
        wrapper, marker = self.process_task('normal')
        self.task(env={'NEX_NODE': str(wrapper)})
        self.assert_stopped(marker)
        wrapper, marker = self.process_task('output')
        result = self.task(ok=False, env={'NEX_NODE': str(wrapper)})
        self.assertEqual(result['checks'][0]['code'], 'E_TASK_OUTPUT')
        self.assert_stopped(marker)
        logs = Path(result["output"]).parent / "logs"
        self.assertTrue(all(p.stat().st_size <= 8*1024*1024 for p in logs.rglob("*") if p.is_file()))

    def test_interruption_saves_checkpoint_and_stops_owned_processes(self):
        wrapper, marker = self.process_task('timeout')
        task = json.loads(self.taskfile.read_text()); task['checks'][0]['timeout_seconds'] = 30; self.save(task)
        child = subprocess.Popen([harness.NEX, 'task', str(self.taskfile), '--kind', 'run', '--json'], cwd=self.root,
            env={**os.environ, 'NEX_NODE': str(wrapper)}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 10
            while not marker.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(.03)
            self.assertTrue(marker.exists())
            child.send_signal(signal.SIGTERM)
            stdout, stderr = child.communicate(timeout=15)
            self.assertEqual(child.returncode, 143, stdout + stderr)
            report = json.loads(stdout)
            self.assertEqual(report['status'], 'interrupted')
            self.assertEqual(report['signal'], 15)
            self.assertEqual(report['checks'][0]['status'], 'interrupted')
            self.assert_stopped(marker)
        finally:
            if child.poll() is None:
                child.terminate()
                child.communicate(timeout=15)


if __name__ == '__main__':
    unittest.main(verbosity=2)
