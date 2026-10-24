"""Atomic source-type edits, archived layouts and checked backend agreement."""
import copy
import json
import shutil
import sqlite3
import subprocess
import unittest

import support as harness

MODEL = '''module model;
pub struct Row{value:i64;}
pub fn make()->Row{return Row(41);}
'''
MAIN = '''module app;import "./model.nex" as m;
fn main()->unit!{io}{print(m::make().value);}
test fn value_test()->unit{assert(m::make().value==41);}
'''


class TypePatches(harness.ToolchainCase):
    def project(self, model=MODEL, main=MAIN):
        (self.root / 'nex.json').write_text(json.dumps({'language':'0.21','entry':'main.nex'}))
        self.source(main)
        (self.root / 'model.nex').write_text(model)
        return self.cli('check')['revision']

    def rows(self):
        with sqlite3.connect(self.root / '.nex/graph.db') as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: sorted(db.execute('SELECT * FROM "'+name+'"').fetchall(), key=repr) for name in names}

    def apply(self, revision, replacements, ok=True):
        patch = self.root / 'patch.json'
        patch.write_text(json.dumps({'expected_revision':revision,'replacements':replacements}))
        return self.cli('apply','--patch',patch,ok=ok)

    def changed(self, value='after'):
        return [
            {'name':'model::Row','kind':'type','source':'pub struct Row{value:str;}'},
            {'name':'model::make','kind':'function','source':'pub fn make()->Row{return Row("'+value+'");}'},
            {'name':'app::value_test','source':'test fn value_test()->unit{assert(m::make().value=="'+value+'");}'},
        ]

    def test_type_and_callers_change_atomically_with_persistent_ids_and_old_layouts(self):
        original = self.project()
        before = self.cli('context','--entity','type','--symbol','model::Row')['node']
        self.assertTrue(before['editable'])
        self.assertEqual(self.cli('run','--revision',original)['stdout'],'41\n')
        replacements = self.changed()
        revised = self.apply(original,replacements)['revision']
        self.assertNotEqual(original,revised)
        after = self.cli('context','--entity','type','--symbol','model::Row')['node']
        self.assertEqual(before['id'],after['id'])
        self.assertNotEqual(before['hash'],after['hash'])
        self.assertIn('value:str',after['source'])
        self.assertEqual((self.root/'model.nex').read_text(),MODEL)
        self.assertEqual(self.file.read_text(),MAIN)
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'after\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'after\n')
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])
        self.assertEqual(self.cli('run','--revision',original)['stdout'],'41\n')
        old = self.cli('context','--revision',original,'--entity','type','--symbol','model::Row')['node']
        self.assertEqual(old['hash'],before['hash'])
        baseline = self.rows()
        self.assertEqual(self.apply(original,replacements,False)['code'],'E_CONFLICT')
        self.assertEqual(self.rows(),baseline)

    def test_bad_type_only_edit_and_visibility_do_not_partially_commit(self):
        revision = self.project()
        baseline = self.rows()
        for source in ('pub struct Row{value:str;}', 'struct Row{value:i64;}'):
            self.apply(revision,[{'name':'model::Row','kind':'type','source':source}],False)
            self.assertEqual(self.rows(),baseline)
            self.assertEqual(self.cli('history')['head'],revision)

    def test_generic_structure_templates_regenerate_instances_and_reject_derived_edits(self):
        model = 'module model;pub struct Box<T>{value:T;}pub fn make()->Box<i64>{return Box(42);}'
        main = MAIN.replace('==41','==42')
        revision = self.project(model,main)
        template = self.cli('context','--entity','type','--symbol','model::Box')['node']
        instance = self.cli('context','--entity','type','--symbol','model::Box<i64>')['node']
        self.assertTrue(template['editable'])
        self.assertFalse(instance['editable'])
        baseline = self.rows()
        self.assertEqual(self.apply(revision,[{'name':'model::Box<i64>','kind':'type','source':'pub struct Box<T>{value:T;}'}],False)['code'],'E_PATCH_SPECIALIZATION')
        self.assertEqual(self.rows(),baseline)
        replacements = [{'name':'model::Box','source':'pub struct Box<T>{value:T;label:str;}'},
                        {'name':'model::make','source':'pub fn make()->Box<i64>{return Box(42,"tag");}'}]
        revised = self.apply(revision,replacements)['revision']
        self.assertNotEqual(revised,revision)
        after = self.cli('context','--entity','type','--symbol','model::Box<i64>')['node']
        self.assertEqual(after['id'],instance['id'])
        self.assertNotEqual(after['hash'],instance['hash'])
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])

    def test_generic_enum_payload_and_exhaustive_consumers_change_together(self):
        model = 'module model;pub enum Choice<T>{None;Some(value:T);}'
        main = '''module app;import "./model.nex" as m;
fn read(value:m::Choice<i64>)->i64{match value{m::Choice::None()=>{return 0;}m::Choice::Some(x)=>{return x;}}}
fn main()->i64{return read(m::Choice<i64>::Some(42));}
test fn value_test()->unit{assert(read(m::Choice<i64>::Some(42))==42);}
'''
        revision = self.project(model,main)
        before = self.cli('context','--entity','type','--symbol','model::Choice<i64>')['node']
        replacements = [
            {'name':'model::Choice','kind':'type','source':'pub enum Choice<T>{None;Some(value:T,flag:bool);}'},
            {'name':'read','source':'fn read(value:m::Choice<i64>)->i64{match value{m::Choice::None()=>{return 0;}m::Choice::Some(x,flag)=>{if flag{return x;}return 0;}}}'},
            {'name':'main','source':'fn main()->i64{return read(m::Choice<i64>::Some(42,true));}'},
            {'name':'value_test','source':'test fn value_test()->unit{assert(read(m::Choice<i64>::Some(42,true))==42);assert(read(m::Choice<i64>::Some(42,false))==0);}'},
        ]
        self.apply(revision,replacements)
        after = self.cli('context','--entity','type','--symbol','model::Choice<i64>')['node']
        self.assertEqual(before['id'],after['id'])
        self.assertEqual(self.cli('eval','--revision','HEAD')['value'],42)
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])

    def test_structure_can_be_refactored_to_enum_in_one_checked_patch(self):
        revision = self.project()
        before = self.cli('context','--entity','type','--symbol','model::Row')['node']
        self.apply(revision,[
            {'name':'model::Row','source':'pub enum Row{Value(value:str);}'},
            {'name':'model::make','source':'pub fn make()->Row{return Row::Value("enum");}'},
            {'name':'main','source':'fn main()->unit!{io}{match m::make(){m::Row::Value(value)=>{print(value);}}}'},
            {'name':'value_test','source':'test fn value_test()->unit{match m::make(){m::Row::Value(value)=>{assert(value=="enum");}}}'},
        ])
        after = self.cli('context','--entity','type','--symbol','model::Row')['node']
        self.assertEqual(before['id'],after['id'])
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'enum\n')
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])
        self.assertEqual(self.cli('eval','--revision',revision)['stdout'],'41\n')

    def test_type_fragment_boundaries_unknown_kinds_and_duplicates_are_rejected(self):
        revision = self.project()
        baseline = self.rows()
        fragments = ['pub struct Other{value:i64;}',
                     'pub struct Row{value:i64;}struct Extra{x:i64;}',
                     'pub struct Row{value:i64;}fn extra()->unit{}',
                     'pub struct Row{value:i64;}import "./missing.nex" as missing;',
                     'fn Row()->i64{return 1;}']
        for fragment in fragments:
            self.apply(revision,[{'name':'model::Row','source':fragment}],False)
            self.assertEqual(self.rows(),baseline)
        for kind,code in [('function','E_PATCH_TARGET'),('enum','E_JSON'),(None,'E_JSON')]:
            self.assertEqual(self.apply(revision,[{'name':'model::Row','kind':kind,'source':'pub struct Row{value:i64;}'}],False)['code'],code)
            self.assertEqual(self.rows(),baseline)
        self.apply(revision,[{'name':'model::Row','source':'pub struct Row{value:i64;}'},
                             {'name':'model::Row','kind':'type','source':'pub struct Row{value:i64;}'}],False)
        self.assertEqual(self.rows(),baseline)

    def test_strict_patch_fields_and_revision_shape_preserve_existing_graph(self):
        revision = self.project()
        baseline = self.rows()
        documents = [
            {'expected_revision':revision,'replacements':[{'name':'model::Row','source':'pub struct Row{value:i64;}','typo':True}]},
            {'expected_revision':revision,'replacements':[{'name':'model::Row','source':'pub struct Row{value:i64;}'}],'typo':True},
            {'expected_revision':revision+'\n','replacements':self.changed()},
        ]
        for document in documents:
            path = self.root/'bad.json'
            path.write_text(json.dumps(document))
            self.assertEqual(self.cli('apply','--patch',path,ok=False)['code'],'E_JSON')
            self.assertEqual(self.rows(),baseline)

    def test_archived_type_edits_export_and_run_after_sources_disappear(self):
        original = self.project()
        revised = self.apply(original,self.changed())['revision']
        self.file.unlink()
        (self.root/'model.nex').unlink()
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'after\n')
        self.assertEqual(self.cli('eval','--revision',original)['stdout'],'41\n')
        destination = self.root/'exported'
        self.cli('export','--directory',destination)
        self.assertEqual(self.cli('check',cwd=destination)['revision'],revised)
        self.assertEqual(self.cli('run',cwd=destination)['stdout'],'after\n')
        self.assertTrue(self.cli('test',cwd=destination)['ok'])

    def test_concurrent_type_patches_adopt_one_complete_bundle(self):
        revision = self.project()
        processes = []
        for value in ('first','second'):
            path = self.root/(value+'.json')
            path.write_text(json.dumps({'expected_revision':revision,'replacements':self.changed(value)}))
            processes.append(subprocess.Popen([harness.NEX,'apply','--patch',str(path),'--json'],
                cwd=self.root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True))
        results = []
        for process in processes:
            out,err = process.communicate(timeout=30)
            self.assertFalse(err)
            results.append((process.returncode,json.loads(out)))
        self.assertEqual(sorted(code for code,_ in results),[0,1])
        self.assertEqual(next(value['code'] for code,value in results if code),'E_CONFLICT')
        self.assertEqual(len(self.cli('history')['revisions']),2)
        self.assertIn(self.cli('eval','--revision','HEAD')['stdout'],('first\n','second\n'))
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])

    def test_language_pack_example_is_pinned_and_runs_on_both_backends(self):
        example = harness.REPO/'examples/type-patches'
        for name in ('main.nex','model.nex','nex.json','patch.json'):
            shutil.copy2(example/name,self.root/name)
        revision = self.cli('check')['revision']
        patch = json.loads((self.root/'patch.json').read_text())
        self.assertEqual(patch['expected_revision'],revision)
        self.cli('apply','--patch',self.root/'patch.json')
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'43\nготово\n')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'43\nготово\n')
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])

    def test_cached_caller_serialization_tracks_archived_type_layout_changes(self):
        main = '''module app;import "./model.nex" as m;
fn main()->unit!{io}{print(encode_json(m::make()));}
test fn value_test()->unit{assert(unwrap(decode_json<m::Row>(encode_json(m::make()))).value==41);}
'''
        revision = self.project(main=main)
        before = next(n['hash'] for n in self.cli('graph')['nodes'] if n['name']=='app::main')
        self.assertEqual(json.loads(self.cli('run','--revision','HEAD')['stdout']),{'value':'41'})
        self.apply(revision,[
            {'name':'model::Row','kind':'type','source':'pub struct Row{value:i64;label:str;}'},
            {'name':'model::make','source':'pub fn make()->Row{return Row(42,"tag");}'},
            {'name':'value_test','source':'test fn value_test()->unit{assert(unwrap(decode_json<m::Row>(encode_json(m::make()))).label=="tag");}'},
        ])
        after = next(n['hash'] for n in self.cli('graph')['nodes'] if n['name']=='app::main')
        self.assertEqual(before,after)
        native = json.loads(self.cli('run','--revision','HEAD')['stdout'])
        self.assertEqual(native,{'value':'42','label':'tag'})
        self.assertEqual(json.loads(self.cli('eval','--revision','HEAD')['stdout']),native)
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])


if __name__ == '__main__':
    unittest.main()
