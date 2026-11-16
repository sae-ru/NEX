"""Source030 checking, explicit execution gates and retained backend behavior."""
import json
import unittest
import support as h

CELL_TASK = '''module cell_tasks;
fn main()->unit!{state,task,throw}{
 let value:cell<i64>=cell_new(1);
 let answer:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{
  let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{
   task_yield();cell_write(value,42);return cell_read(value);
  });return task_wait(child);
 });assert(answer==42);
}
'''


class Boundaries(h.ToolchainCase):
    def project(self, text):
        self.source(text)
        path = self.root / 'nex.json'
        manifest = json.loads(path.read_text())
        manifest['language'] = '0.30'
        path.write_text(json.dumps(manifest) + '\n')

    def test_stateful_callbacks_check_but_all_public_backends_retain_the_gate(self):
        self.project(CELL_TASK)
        checked = self.cli('check')
        self.assertTrue(checked['ok'])
        field = self.cli('describe', '--field',
                         'managed_references.source030_development.reference_tasks')['value']
        self.assertTrue(field['frontend_state_callbacks'])
        self.assertTrue(field['reference_interpreter'])
        self.assertFalse(field['public_source_enabled'])
        self.assertFalse(field['native'])
        self.assertFalse(field['typescript'])
        for command in [('eval',), ('build', '--build-directory', str(self.root / 'native')),
                        ('emit', '--kind', 'typescript')]:
            with self.subTest(command=command):
                self.assertEqual(self.cli(*command, ok=False)['code'], 'E_CELL_CONCURRENCY')

    def test_stateful_callback_requires_its_callers_state_effect(self):
        self.project('''module effect;
fn main()->unit!{task,throw}{
 let value:i64=with_tasks(1,fn(s:task_scope)->i64!{state}{return cell_read(cell_new(42));});
}
''')
        result = self.cli('check', ok=False)
        self.assertEqual(result['code'], 'E_EFFECT')
        self.assertIn('state', result['message'])

    def test_reference_free_source030_tasks_still_execute_in_all_backends(self):
        self.project('''module inherited;
fn compute()->i64!{task,throw}{
 return with_tasks(1,fn(s:task_scope)->i64!{task,throw}{
  let child:task<i64>=task_spawn(s,fn()->i64!{task}{task_yield();return 42;});return task_wait(child);
 });
}
fn main()->unit!{task,throw,io}{print(compute());}
test fn answer()->unit!{task,throw}{assert(compute()==42);}
''')
        self.assertEqual(self.cli('eval')['stdout'], '42\n')
        self.assertEqual(self.cli('run', '--profile', 'release')['stdout'], '42\n')
        self.assertTrue(self.cli('test', '--target', 'web')['ok'])

    def test_sequential_source030_cells_keep_their_normal_backends(self):
        self.project('''module sequential;
fn compute()->i64!{state}{let value:cell<i64>=cell_new(1);cell_write(value,42);cell_collect();return cell_read(value);}
fn main()->unit!{state,io}{print(compute());}
test fn answer()->unit!{state}{assert(compute()==42);}
''')
        self.assertEqual(self.cli('eval')['stdout'], '42\n')
        self.assertEqual(self.cli('run', '--profile', 'release')['stdout'], '42\n')
        self.assertTrue(self.cli('test', '--target', 'web')['ok'])


if __name__ == '__main__':
    unittest.main(argv=[__file__, '-v'])
