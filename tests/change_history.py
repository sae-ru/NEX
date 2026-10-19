"""Committed source provenance and optimistic, source-deleted graph restoration."""
import concurrent.futures
import copy
import hashlib
from pathlib import Path
import json
import sqlite3
import unittest
import support as harness

SOURCE='module history;fn value()->i64{return 41;}fn main()->unit!{io}{print(value());}test fn value_test()->unit{assert(value()>=40);}'

class ChangeHistory(harness.ToolchainCase):
    def ready(self):
        self.source(SOURCE)
        return self.cli('check','--note','initial 🧠','--actor','operator')['revision']

    def rows(self):
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            names=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {n:sorted(db.execute('SELECT * FROM "'+n+'"').fetchall(),key=repr) for n in names}

    def patch(self,number,revision=None):
        path=self.root/('patch-'+str(number)+'.json')
        path.write_text(json.dumps({'expected_revision':revision or self.cli('history')['head'],
            'replacements':[{'name':'history::value','source':'fn value()->i64{return '+str(number)+';}'}]}))
        return path

    def edit(self,number):
        return self.cli('apply','--patch',self.patch(number),'--actor','model-label','--note','change to '+str(number))['revision']

    def restore(self,target,expected,**kwargs):
        return self.cli('restore','--revision',target,'--expected-revision',expected,**kwargs)

    def test_changes_record_actual_heads_sources_commands_and_declared_labels(self):
        before=self.ready();after=self.edit(42)
        report=self.cli('changes');self.assertEqual(report['total'],2)
        self.assertEqual(report['author_trust'],'declared')
        newer,older=report['changes']
        self.assertEqual([newer['sequence'],older['sequence']],[2,1])
        self.assertEqual(newer['previous_change'],older['hash'])
        self.assertEqual((newer['previous_revision'],newer['revision']),(before,after))
        self.assertEqual((older['action'],older['command'],older['actor'],older['note']),('synchronize','check','operator','initial 🧠'))
        self.assertEqual((newer['action'],newer['command'],newer['actor']),('apply','apply','model-label'))
        self.assertEqual(newer['source_hash'],self.cli('operations','--symbol','value')['source_hash'])
        self.assertEqual(len(newer['request_hash']),64)
        self.assertNotEqual(newer['hash'],older['hash'])
        rows=self.rows();self.cli('history');self.cli('graph');self.cli('eval','--revision',before)
        self.assertEqual(self.rows(),rows)

    def test_restore_retains_ids_revisions_and_backend_execution_without_sources(self):
        before=self.ready();original=self.cli('graph');after=self.edit(42)
        self.file.unlink()
        result=self.restore(before,after);self.assertTrue(result['changed']);self.assertFalse(result['materialized'])
        self.assertEqual(result['previous_revision'],after)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'41\n')
        self.assertEqual(self.cli('graph')['nodes'],original['nodes'])
        self.assertTrue(self.cli('test','--revision','HEAD')['ok'])
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web')['ok'])
        self.restore(after,before)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'42\n')
        self.assertEqual(self.cli('eval','--revision',before)['stdout'],'41\n')
        self.assertFalse(self.file.exists())
        self.assertEqual([r['action'] for r in self.cli('changes')['changes']],['restore','restore','apply','synchronize'])

    def test_noop_restore_and_same_semantics_do_not_invent_transitions(self):
        revision=self.ready();before=self.rows()
        self.assertFalse(self.restore(revision,revision)['changed'])
        self.assertEqual(self.rows(),before)
        self.source(SOURCE.replace('module history;','module history;\n// formatting 🧠\n'))
        self.assertEqual(self.cli('check','--note','formatting only')['revision'],revision)
        self.assertEqual(self.rows(),before)

    def test_stale_missing_and_bad_restore_requests_do_not_mutate_rows(self):
        before=self.ready();after=self.edit(42);baseline=self.rows()
        for target,expected,code in [(before,before,'E_CONFLICT'),('0'*64,after,'E_REVISION'),('bad',after,'E_OPTION'),(before,'HEAD','E_OPTION')]:
            self.assertEqual(self.restore(target,expected,ok=False)['code'],code)
            self.assertEqual(self.rows(),baseline)
        for arguments in [('--target','web'),('--profile','release'),('--','ignored')]:
            self.assertEqual(self.cli('restore','--revision',before,'--expected-revision',after,*arguments,ok=False)['code'],'E_OPTION')
            self.assertEqual(self.rows(),baseline)

    def test_competing_restore_and_patch_commit_one_head_and_one_record(self):
        first=self.ready();second=self.edit(42);patch=self.patch(43,second)
        commands=[('restore','--revision',first,'--expected-revision',second),('apply','--patch',patch)]
        def invoke(args):
            return harness.subprocess.run([harness.NEX,*map(str,args),'--json'],cwd=self.root,text=True,capture_output=True,timeout=30)
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(invoke,commands))
        self.assertEqual(sum(r.returncode==0 for r in results),1,[r.stdout+r.stderr for r in results])
        loser=next(r for r in results if r.returncode);self.assertEqual(json.loads(loser.stdout)['code'],'E_CONFLICT')
        winner=json.loads(next(r for r in results if r.returncode==0).stdout)['revision']
        report=self.cli('changes');self.assertEqual(report['total'],3)
        self.assertEqual((report['changes'][0]['previous_revision'],report['changes'][0]['revision']),(second,winner))
        self.assertEqual(self.cli('history')['head'],winner)
        self.assertEqual(self.cli('eval','--revision',second)['stdout'],'42\n')

    def test_corrupt_latest_record_rejects_query_and_rolls_back_candidate(self):
        self.ready();self.edit(42)
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            db.execute("UPDATE change_journal SET data=replace(data,'change to 42','changed text') WHERE sequence=2")
        before=self.rows()
        self.assertEqual(self.cli('changes',ok=False)['code'],'E_CHANGE_INTEGRITY')
        self.assertEqual(self.cli('apply','--patch',self.patch(43),ok=False)['code'],'E_CHANGE_INTEGRITY')
        self.assertEqual(self.rows(),before)

    def test_head_rewritten_outside_journal_is_rejected_without_new_rows(self):
        first=self.ready();self.edit(42)
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            db.execute('UPDATE head SET revision=? WHERE id=1',(first,))
        before=self.rows()
        self.assertEqual(self.cli('changes',ok=False)['code'],'E_CHANGE_INTEGRITY')
        self.assertEqual(self.cli('apply','--patch',self.patch(43),ok=False)['code'],'E_CHANGE_INTEGRITY')
        self.assertEqual(self.restore(first,first,ok=False)['code'],'E_CHANGE_INTEGRITY')
        self.assertEqual(self.rows(),before)

    def test_paging_export_and_utf8_provenance_limits(self):
        self.ready()
        for number in range(42,47):self.edit(number)
        page=self.cli('changes','--offset','2','--limit','2')
        self.assertEqual(page['total'],6);self.assertEqual([v['sequence'] for v in page['changes']],[4,3]);self.assertTrue(page['truncated'])
        output=self.root/'page.json';self.cli('changes','--offset','2','--limit','2','-o',output)
        self.assertEqual(json.loads(output.read_text()),page)
        self.cli('apply','--patch',self.patch(47),'--note','🧠'*256,'--actor','🧠'*32)
        before=self.rows()
        for option,value in [('--note','🧠'*257),('--actor','🧠'*33)]:
            self.assertEqual(self.cli('apply','--patch',self.patch(48),option,value,ok=False)['code'],'E_CHANGE')
            self.assertEqual(self.rows(),before)
        for args in [('--limit','0'),('--limit','1001'),('--offset','-1'),('--offset','10000001'),('--limit','')]:
            self.assertEqual(self.cli('changes',*args,ok=False)['code'],'E_OPTION')

    def test_retained_nonhead_task_candidate_has_no_false_change_record(self):
        before=self.ready();self.source(SOURCE.replace('return 41;','return 42;'))
        task=self.cli('task',self.file,'--kind','init')
        candidate=task['programs'][0]['baseline_revision'];self.assertNotEqual(candidate,before)
        self.assertEqual(self.cli('history')['head'],before)
        self.assertEqual(self.cli('changes')['total'],1)
        self.restore(candidate,before)
        self.assertEqual(self.cli('eval','--revision','HEAD')['stdout'],'42\n')
        self.assertEqual(self.cli('changes')['total'],2)

    def test_actual048_database_upgrade_preserves_rows_and_has_no_fabricated_legacy_events(self):
        fixture=harness.REPO/'tests/fixtures/history-0.48'
        metadata=json.loads(Path(str(fixture)+'.json').read_text());sql=Path(str(fixture)+'.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        (self.root/'.nex').mkdir()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:db.executescript(sql.decode())
        original=self.rows();report=self.cli('changes');upgraded=self.rows()
        self.assertEqual((report['total'],report['head'],report['base_revision']),(0,metadata['head_revision'],metadata['head_revision']))
        for table,rows in original.items():
            if table!='metadata':self.assertEqual(upgraded[table],rows,table)
        previous_metadata=dict(original['metadata']);current_metadata=dict(upgraded['metadata'])
        self.assertEqual(current_metadata['schema'],'4')
        self.assertEqual(current_metadata['change_base_revision'],metadata['head_revision'])
        for key,value in previous_metadata.items():
            if key!='schema':self.assertEqual(current_metadata[key],value,key)
        self.assertEqual(self.cli('graph',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.restore(metadata['before_revision'],metadata['head_revision'],ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.rows(),upgraded)
        migrated_before=self.cli('migrate','--revision',metadata['before_revision'])['revision']
        migrated_head=self.cli('migrate','--revision',metadata['head_revision'])['revision']
        current=self.cli('graph')
        self.assertNotEqual(current['revision'],metadata['head_revision'])
        self.assertEqual(current['source'],metadata['graph']['source'])
        self.assertEqual({n['name']:n['id'] for n in current['nodes']},
                         {n['name']:n['id'] for n in metadata['graph']['nodes']})
        old_ops={(n['function'],n['path']):n for n in metadata['graph']['operation_graph']['nodes']}
        new_ops={(n['function'],n['path']):n for n in current['operation_graph']['nodes']}
        self.assertEqual(set(old_ops),set(new_ops))
        for key,prior in old_ops.items():
            for field in ('kind','definition','location','function_id'):self.assertEqual(new_ops[key][field],prior[field],field)
        self.restore(migrated_before,migrated_head)
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'41\n')
        changes=self.cli('changes');self.assertEqual(changes['total'],3)
        self.assertEqual(changes['base_revision'],metadata['head_revision'])
        self.assertEqual([e['action'] for e in changes['changes']],['restore','migrate','migrate'])
        event=changes['changes'][0]
        self.assertEqual((event['sequence'],event['previous_revision'],event['revision']),(3,migrated_head,migrated_before))
        after=self.rows()
        for table,values in original.items():
            if table not in ('metadata','head'):self.assertTrue(set(values)<=set(after[table]),table)

    def test_restore_older_language_requires_explicit_migration_and_keeps_history(self):
        metadata=json.loads((harness.REPO/'tests/fixtures/language-0.14.json').read_text())
        self.source(metadata['source']);self.historical_store('0.14')
        old=self.cli('history')['head'];before=self.rows()
        self.assertEqual(self.restore(old,old,ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.rows(),before)
        self.assertEqual(self.cli('changes')['total'],0)
        migrated=self.cli('migrate','--note','explicit language migration')['revision']
        event,=self.cli('changes')['changes']
        self.assertEqual((event['action'],event['previous_revision'],event['revision']),('migrate',old,migrated))
        self.assertIn(old,[r['revision'] for r in self.cli('history')['revisions']])

    def test_empty_head_can_adopt_a_retained_candidate_with_explicit_empty_guard(self):
        self.source(SOURCE)
        task=self.cli('task',self.file,'--kind','init')
        target=task['programs'][0]['baseline_revision']
        report=self.cli('changes');self.assertEqual((report['head'],report['base_revision'],report['total']),('','',0))
        self.file.unlink();self.restore(target,'EMPTY')
        event,=self.cli('changes')['changes'];self.assertEqual(event['previous_revision'],'')
        self.assertEqual(self.cli('run','--revision','HEAD')['stdout'],'41\n')

    def test_change_pages_are_consistent_while_another_process_commits(self):
        self.ready()
        def writer():
            for number in range(42,52):self.edit(number)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(writer)
            for _ in range(12):
                report=self.cli('changes');rows=report['changes']
                self.assertEqual(report['total'],len(rows));self.assertFalse(report['truncated'])
                self.assertEqual(report['head'],rows[0]['revision'])
                self.assertEqual([r['sequence'] for r in rows],list(range(report['total'],0,-1)))
                for new,old in zip(rows,rows[1:]):self.assertEqual(new['previous_change'],old['hash'])
            future.result(timeout=30)

    def test_invalid_utf8_declared_author_is_rejected_before_any_graph_change(self):
        self.ready();path=self.patch(42);before=self.rows()
        result=harness.subprocess.run([harness.os.fsencode(harness.NEX),b'apply',b'--patch',harness.os.fsencode(path),
            b'--actor',b'\xff',b'--json'],cwd=self.root,capture_output=True,timeout=10)
        self.assertNotEqual(result.returncode,0)
        self.assertEqual(json.loads(result.stdout.decode())['code'],'E_CHANGE')
        self.assertEqual(self.rows(),before)

if __name__=='__main__':unittest.main()
