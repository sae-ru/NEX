"""Reviewed task limits survive source/project acceptance and captured replay."""
import copy
import json
from pathlib import Path
import shutil
import unittest
import support as harness

SOURCE='''module capped;
fn solve()->i64 !{task}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
  let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 42;});
  return task_wait(child);
});}
fn main()->i64 !{io,task}{print(solve());return 0;}
test fn checks()->unit !{task}{assert(solve()==42);}
'''
LIMITS={'steps':100000,'timeout_ms':5000,'workers':1}

class TaskLimitsWorkflow(harness.ToolchainCase):
    def save(self,path,value):path.write_text(json.dumps(value,indent=2)+'\n')

    def add(self,task,check):
        check['program']='app';task['checks'].append(check)
        task['requirements'].append({'id':check['id'],'text':'Observe the approved task limits',
          'bindings':[{'program':'app','kind':'function','symbol':'capped::main'}],
          'targets':[check['target']],'checks':[check['id']]})

    def test_nonproject_limits_intent_actual_backends_and_source_deleted_replay(self):
        guide=self.cli('guide','--kind','task-limits');self.assertIn('task execution limits',str(guide).lower())
        self.source(SOURCE);task=self.cli('task',self.file,'--kind','init')
        for check in task['checks']:check['task_limits']=LIMITS
        web=copy.deepcopy(next(c for c in task['checks'] if c['kind']=='test'))
        web['id']='web-capped';web['target']='web';task['checks'].append(web)
        task['requirements'].append({'id':'web-capped','text':'Execute the capped event-loop backend',
          'bindings':[{'program':'app','kind':'function','symbol':'capped::checks'}],
          'targets':['web'],'checks':['web-capped']})
        self.add(task,{'id':'observe','kind':'run','target':'native','entry':'capped::main',
          'expect':{'stdout':'42\n','exit_code':0},'task_limits':LIMITS})
        path=self.root/'task.json';self.save(path,task)
        checked=self.cli('task',path,'--kind','check');self.assertTrue(checked['ok'])
        result=self.cli('task',path,'--kind','run','--task-hash',checked['task_hash'],timeout=300)
        self.assertTrue(all(c['status']=='passed' for c in result['checks']))
        receipt=Path(result['output']);saved=json.loads(receipt.read_text())
        self.assertTrue(all(c['task_limits']==LIMITS for c in saved['checks']))
        captured=json.loads((receipt.parent/'inputs/task.json').read_text())
        self.assertTrue(all(c['task_limits']==LIMITS for c in captured['checks']))
        # Every executor invocation carries the reviewed controls, including eval.
        commands=[json.loads(p.read_text()) for p in (receipt.parent/'artifacts').glob('*/commands/*.json')]
        observed=[c.get('response',{}) for c in commands if isinstance(c.get('response'),dict)]
        executions=[r['task_execution'] for r in observed if 'task_execution' in r]
        executions += [t['task_execution'] for r in observed for t in r.get('tests',[]) if 'task_execution' in t]
        self.assertEqual({e['backend'] for e in executions},{'native','reference','typescript'})
        self.assertTrue(all(e['effective']==LIMITS and e['executor_workers']==1 for e in executions))
        before=harness.database_rows(self.root/'.nex/graph.db')
        self.file.unlink();path.unlink()
        replay=self.cli('task',receipt,'--kind','replay','--directory',self.root/'replay',timeout=300)
        self.assertTrue(replay['ok']);self.assertEqual(replay['task_hash'],checked['task_hash'])
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)

    def test_project_configuration_limits_capture_run_tests_and_replay(self):
        app=self.root/'app';app.mkdir();self.file=app/'main.nex';self.source(SOURCE)
        self.save(self.root/'nex.json',{'schema':'nex.project/1','language':'0.23','entry':'app/main.nex'})
        architecture={'schema':'nex.project-build/1','default_configuration':'debug',
          'configurations':{'debug':{'profile':'debug','task_limits':LIMITS}},
          'components':{'app':{'kind':'executable','root':'app','entry':'app/main.nex'}}}
        manifest=self.root/'nex.build.json';self.save(manifest,architecture)
        plan=self.cli('project','--component','app')
        self.assertEqual(plan['configuration']['task_limits'],LIMITS)
        self.assertFalse((self.root/'.nex').exists())
        result=self.cli('project','--kind','run','--component','app',timeout=180)
        self.assertEqual(result['observation']['stdout'],'42\n')
        self.assertEqual(result['observation']['task_execution']['effective'],LIMITS)
        test=self.cli('project','--kind','test','--component','app',timeout=180)
        self.assertTrue(test['ok']);self.assertEqual(test['tests'][0]['task_execution']['effective'],LIMITS)
        task=self.cli('task',manifest,'--kind','init','--component','app','--configuration','debug',timeout=180)
        self.add(task,{'id':'observe','kind':'run','target':'native','configuration':'debug',
          'entry':'capped::main','expect':{'stdout':'42\n','exit_code':0}})
        path=self.root/'task.json';self.save(path,task)
        result=self.cli('task',path,'--kind','run',timeout=300);receipt=Path(result['output'])
        saved=json.loads(receipt.read_text());executions=[c['task_execution'] for c in saved['checks'] if 'task_execution' in c]
        self.assertTrue(executions);self.assertTrue(all(e['effective']==LIMITS for e in executions))
        shutil.rmtree(app);manifest.unlink();(self.root/'nex.json').unlink();path.unlink()
        before=harness.database_rows(self.root/'.nex/graph.db')
        self.assertTrue(self.cli('task',receipt,'--kind','replay','--directory',self.root/'replay',timeout=300)['ok'])
        self.assertEqual(harness.database_rows(self.root/'.nex/graph.db'),before)

    def test_task_static_provider_readonly_plan_preserves_reviewed_limits_and_ownership(self):
        (self.root/'app').mkdir();(self.root/'core').mkdir()
        self.file=self.root/'app/main.nex'
        self.source(SOURCE.replace('module capped;','module capped;import "../core/value.nex" as c;').replace('return 42;','return c::value();'))
        (self.root/'core/value.nex').write_text('module value;pub fn value()->i64{return 42;}')
        self.save(self.root/'nex.json',{'schema':'nex.project/1','language':'0.23','entry':'app/main.nex'})
        architecture={'schema':'nex.project-build/1','default_configuration':'debug',
          'configurations':{'debug':{'profile':'debug','task_limits':LIMITS}},
          'components':{'app':{'kind':'executable','root':'app','entry':'app/main.nex','dependencies':{'core':'static'}},
                        'core':{'kind':'static_library','root':'core','entry':'core/value.nex','entry_function':'value'}}}
        manifest=self.root/'nex.build.json';self.save(manifest,architecture)
        plan=self.cli('project','--component','app')
        self.assertEqual(plan['configuration']['task_limits'],LIMITS)
        self.assertFalse(plan['external_tools_invoked'])
        components={row['name']:row for row in plan['components']}
        self.assertEqual(components['app']['dependencies'],{'core':'static'})
        linkage=components['app']['task_linkage']
        self.assertEqual(linkage['schema'],'nex.project-static-task-linkage/2')
        self.assertEqual(linkage['execution_abi'],4)
        self.assertTrue(all(row['function'].startswith('capped::') for row in linkage['definitions']))
        imported,=linkage['imports']
        self.assertEqual((imported['function'],imported['provider'],imported['calling_mode']),('value::value','core','sync/1'))
        self.assertEqual(components['core']['task_linkage']['component'],'core')
        self.assertFalse((self.root/'.nex').exists())
        architecture['components']['app']['dependencies']['core']='source'
        self.save(manifest,architecture)
        self.assertTrue(self.cli('project','--component','app')['ok'])
        self.assertFalse((self.root/'.nex').exists())

    def test_invalid_limits_and_task_provider_preflight_fail_before_receipt(self):
        self.source(SOURCE);task=self.cli('task',self.file,'--kind','init');path=self.root/'task.json'
        check=next(c for c in task['checks'] if c['kind']=='build')
        for value in [{},{'steps':0},{'workers':17},{'timeout_ms':True},{'steps':9007199254740992},{'unknown':1}]:
            candidate=copy.deepcopy(task)
            next(c for c in candidate['checks'] if c['kind']=='build')['task_limits']=value
            self.save(path,candidate);out=self.root/'must-not-exist'
            self.assertEqual(self.cli('task',path,'--kind','run','--directory',out,ok=False)['code'],'E_TASK')
            self.assertFalse(out.exists())
        check['mode']='library';self.save(path,task)
        self.assertEqual(self.cli('task',path,'--kind','check',ok=False)['code'],'E_TASK_PROVIDER')
        self.assertEqual(self.cli('task',path,'--kind','run','--directory',self.root/'provider-run',ok=False)['code'],'E_TASK_PROVIDER')
        self.assertFalse((self.root/'provider-run').exists())
        for source in [
            'module cap;pub fn identity(value:task_scope)->task_scope{return value;}',
            'module cap;pub fn identity(value:fn()->i64 !{task})->fn()->i64 !{task}{return value;}',
        ]:
            self.source(source);candidate=self.cli('task',self.file,'--kind','init');self.save(path,candidate)
            self.assertEqual(self.cli('task',path,'--kind','check',ok=False)['code'],'E_TASK_PROVIDER')

if __name__=='__main__':unittest.main()
