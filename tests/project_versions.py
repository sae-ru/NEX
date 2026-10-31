"""Declared source versions, reachable libraries and explicit archived migration."""
from sqlite_fixture import connection as sqlite_connection
import json
from pathlib import Path
import sqlite3
import shutil
import unittest
import support as harness

SOURCE='module project_versions;fn value()->i64{return 42;}fn main()->unit!{io}{print(value());}test fn value_test()->unit{assert(value()==42);}'

class ProjectVersions(harness.ToolchainCase):
    def manifest(self,**fields):
        value={'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'main.nex',**fields}
        (self.root/'nex.json').write_text(json.dumps(value), newline="\n")
        return value

    def ready(self):
        self.source(SOURCE);self.manifest();return self.cli('check')['revision']

    def rows(self):
        with sqlite_connection(self.root/'.nex/graph.db') as db:
            names=[name for name, in db.execute("SELECT name FROM sqlite_schema WHERE type='table'")]
            return {name:sorted(db.execute('SELECT * FROM "'+name.replace('"','""')+'"').fetchall(),key=repr) for name in names}

    def test_explicit_other_languages_reject_all_physical_workflows_without_new_rows(self):
        self.ready();before=self.rows()
        commands=[('check',),('check',self.file),('eval',),('run',),('test',),('build',),
            ('emit','--kind','typescript'),('web','--directory',self.root/'web-output'),
            ('api',),('lock',),('profile','--scenario','blocked','--timeout','1'),
            ('ffi','--symbol','main'),('diagnose','--manifest',self.root/'debug.json','--log',self.root/'stderr.log'),('declarations',self.file),('identities',self.file),
            ('task',self.file,'--kind','init')]
        for version in ['0.22','0.21','0.20','0.19','0.14','0.10','0.99','unknown']:
            self.manifest(language=version)
            for command in commands:
                with self.subTest(version=version,command=command[0]):
                    result=self.cli(*command,ok=False)
                    self.assertEqual(result['code'],'E_LANGUAGE_VERSION')
                    self.assertEqual(result['file'],'nex.json')
                    self.assertEqual(self.rows(),before)
            self.assertEqual(json.loads((self.root/'nex.json').read_text())['language'],version)
        self.assertEqual(self.file.read_text(),SOURCE)
        self.assertFalse((self.root/'web-output').exists())

    def test_omitted_legacy_metadata_and_extra_editor_metadata_remain_supported(self):
        self.source(SOURCE)
        for extra in [{},{'schema':'nex.project/1'},{'language':harness.CURRENT_LANGUAGE},
                      {'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'editor':{'layout':'custom'}}]:
            (self.root/'nex.json').write_text(json.dumps({'entry':'main.nex',**extra}), newline="\n")
            self.cli('check');self.assertEqual(self.cli('graph')['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(self.cli('eval')['stdout'],'42\n')

    def test_old_physical_project_is_rejected_before_a_graph_store_is_created(self):
        self.source(SOURCE);self.manifest(language='0.14')
        for command in [('check',),('task',self.file,'--kind','init'),('diagnose','--manifest',self.root/'debug.json','--log',self.root/'stderr.log')]:
            self.assertEqual(self.cli(*command,ok=False)['code'],'E_LANGUAGE_VERSION')
            self.assertFalse((self.root/'.nex').exists())

    def test_malformed_declared_metadata_is_rejected_with_preserved_graph(self):
        self.ready();before=self.rows()
        variants=[('language',None),('language',True),('language',15),('language',''),
            ('language','x'*33),('language','0.15\0'),('schema',None),('schema',False),
            ('schema','nex.project/2'),('entry',None),('entry',''),('entry','bad\0.nex')]
        for key,value in variants:
            self.manifest(**{key:value})
            error=self.cli('check',self.file,ok=False)
            self.assertEqual(error['code'],'E_MANIFEST',(key,value,error))
            self.assertEqual(self.rows(),before)

    def test_archived_queries_execution_and_restore_ignore_old_live_manifest(self):
        revision=self.ready();graph=self.cli('graph');before=self.rows();self.manifest(language='0.14')
        self.assertEqual(self.cli('graph')['nodes'],graph['nodes'])
        self.assertEqual(self.cli('run','--revision',revision)['stdout'],'42\n')
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'42\n')
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])
        self.assertFalse(self.cli('restore','--revision',revision,'--expected-revision',revision)['changed'])
        self.assertEqual(self.rows(),before)
        exported=self.root/'exported-current';self.cli('export','--revision',revision,'--directory',exported)
        self.assertEqual(json.loads((exported/'nex.json').read_text())['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(self.cli('run',cwd=exported)['stdout'],'42\n')
        self.assertEqual(self.cli('run',ok=False)['code'],'E_LANGUAGE_VERSION')

    def test_genuine_old_archive_migrates_with_old_manifest_then_exports_current_project(self):
        metadata=json.loads((harness.REPO/'tests/fixtures/language-0.14.json').read_text())
        self.source(metadata['source']);self.historical_store('0.14');self.manifest(language='0.14')
        old=metadata['revision'];before=self.rows()
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.rows(),before)
        self.assertEqual(dict(before['metadata'])['schema'],'3')
        migrated=self.cli('migrate');self.assertEqual(migrated['language'],harness.CURRENT_LANGUAGE)
        self.assertFalse(migrated['materialized'])
        self.assertEqual({v['language'] for v in self.cli('history')['revisions']},{'0.14',harness.CURRENT_LANGUAGE})
        change,=self.cli('changes')['changes']
        self.assertEqual((change['action'],change['previous_revision']),('migrate',old))
        self.assertEqual(json.loads((self.root/'nex.json').read_text())['language'],'0.14')
        self.assertEqual(self.file.read_text(),metadata['source'])
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        exported=self.root/'migrated-source';self.cli('export','--directory',exported)
        self.assertEqual(json.loads((exported/'nex.json').read_text())['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(self.cli('check',cwd=exported)['revision'],migrated['revision'])

    def library(self):
        self.source('module application;import "numbers/value.nex" as n;fn main()->unit!{io}{print(n::value());}')
        self.manifest(libraries={'numbers':'./library','unused':'./unused'})
        library=self.root/'library';library.mkdir()
        (library/'value.nex').write_text('module numbers;pub fn value()->i64{return 42;}', newline="\n")
        return library

    def test_reachable_library_declared_versions_are_checked_without_loading_unused_libraries(self):
        library=self.library();unused=self.root/'unused';unused.mkdir()
        (unused/'nex.json').write_text(json.dumps({'language':'0.14'}), newline="\n")
        (library/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE}), newline="\n")
        revision=self.cli('check')['revision'];before=self.rows()
        (library/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.14'}), newline="\n")
        error=self.cli('check',ok=False);self.assertEqual(error['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(Path(error['file']).resolve(),(library/'nex.json').resolve())
        self.assertEqual(self.rows(),before)
        self.assertEqual(self.cli('run','--revision',revision)['stdout'],'42\n')
        (library/'nex.json').unlink()
        self.assertEqual(self.cli('check')['revision'],revision)

    def test_reachable_library_bad_schema_and_metadata_are_rejected(self):
        library=self.library();self.cli('check');before=self.rows()
        for value in [{'schema':'nex.project/2'},{'language':None},[]]:
            (library/'nex.json').write_text(json.dumps(value), newline="\n")
            self.assertEqual(self.cli('check',ok=False)['code'],'E_MANIFEST')
            self.assertEqual(self.rows(),before)

    def test_task_physical_preflight_preserves_store_but_archived_candidate_is_allowed(self):
        revision=self.ready();task=self.cli('task',self.file,'--kind','init')
        path=self.root/'task.json';path.write_text(json.dumps(task), newline="\n")
        checked=self.cli('task',path,'--kind','check');self.manifest(language='0.14');before=self.rows()
        self.assertEqual(self.cli('task',path,'--kind','check',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertTrue(self.cli('task',path,'--kind','check','--revision',revision)['ok'])
        self.assertEqual(self.rows(),before)
        other=self.root/'old-with-task';other.mkdir()
        for name in ['nex.json','main.nex','task.json']:shutil.copy2(self.root/name,other/name)
        for options in [('check',),('run','--task-hash',checked['task_hash'])]:
            self.assertEqual(self.cli('task',other/'task.json','--kind',*options,cwd=other,ok=False)['code'],'E_LANGUAGE_VERSION')
            self.assertFalse((other/'.nex').exists())

    def test_snapshot_recovery_uses_archived_language_instead_of_stale_physical_manifest(self):
        self.ready();self.manifest(language='0.14');before=self.rows()
        snapshot=self.root/'saved';self.cli('snapshot','--directory',snapshot)
        recovered=self.root/'recovered';self.cli('recover',snapshot,'--directory',recovered)
        self.assertEqual(json.loads((recovered/'nex.json').read_text())['language'],harness.CURRENT_LANGUAGE)
        self.assertEqual(self.cli('run','--revision','HEAD',cwd=recovered)['stdout'],'42\n')
        self.assertEqual(self.rows(),before)

    def test_discovery_and_model_pack_expose_actual_manifest_contract(self):
        descriptor=self.cli('describe');pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertIn('declared_source_language_guard',descriptor['project_features'])
        self.assertIn('reachable_library_language_guard',descriptor['project_features'])
        self.assertEqual(descriptor['project_manifest_schema'],pack['documents']['project_manifest_schema'])
        self.assertEqual(self.cli('guide','--kind','compatibility')['text'],(harness.REPO/'docs/compatibility.md').read_text())

if __name__=='__main__':unittest.main()
