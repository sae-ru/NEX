"""Consistent, identity-preserving graph snapshots and non-overwriting recovery."""
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time
import unittest
import support as harness

SOURCE='module snapshots;fn value()->i64{return 41;}fn main()->unit!{io}{print(value());}test fn value_test()->unit{assert(value()>=40);}'

class GraphSnapshots(harness.ToolchainCase):
    def ready(self):
        self.source(SOURCE)
        return self.cli('check','--note','first 🧠')['revision']

    def rows(self,root=None):
        with sqlite3.connect((root or self.root)/'.nex/graph.db') as db:
            names=[n for n, in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
            return {n:sorted(db.execute('SELECT * FROM "'+n.replace('"','""')+'"').fetchall(),key=repr) for n in names}

    def edit(self,number):
        patch=self.root/('patch-'+str(number)+'.json')
        patch.write_text(json.dumps({'expected_revision':self.cli('history')['head'],
            'replacements':[{'name':'value','source':'fn value()->i64{return '+str(number)+';}'}]}))
        return self.cli('apply','--patch',patch)['revision']

    def snapshot(self,name='saved'):
        path=self.root/name
        result=self.cli('snapshot','--directory',path)
        return path,result,json.loads((path/'snapshot.json').read_text())

    def recover(self,snapshot,name='recovered',ok=True):
        path=self.root/name;result=self.cli('recover',snapshot,'--directory',path,ok=ok)
        return path,result

    def test_source_deleted_recovery_retains_every_row_uuid_and_both_revisions(self):
        old=self.ready();new=self.edit(42);graph=self.cli('graph');before=self.rows();self.file.unlink()
        archive,result,manifest=self.snapshot()
        self.assertTrue(result['source_unchanged']);self.assertEqual(self.rows(),before)
        self.assertEqual(manifest['state']['head'],new)
        self.assertEqual(manifest['database']['sha256'],hashlib.sha256((archive/'graph.db').read_bytes()).hexdigest())
        recovered,result=self.recover(archive)
        self.assertFalse(result['materialized']);self.assertTrue(result['existing_project_unchanged'])
        self.assertEqual(self.rows(recovered),before)
        self.assertEqual(self.cli('graph',cwd=recovered)['nodes'],graph['nodes'])
        self.assertEqual(self.cli('changes',cwd=recovered),self.cli('changes'))
        self.assertEqual(self.cli('run','--revision','HEAD',cwd=recovered)['stdout'],'42\n')
        self.assertEqual(self.cli('eval','--revision',old,cwd=recovered)['stdout'],'41\n')
        self.assertTrue(self.cli('test','--revision','HEAD','--target','web',cwd=recovered)['ok'])
        self.assertFalse((recovered/'main.nex').exists())
        self.assertEqual(self.rows(),before)
        self.assertEqual((archive.stat().st_mode&0o777,(archive/'graph.db').stat().st_mode&0o777),(0o700,0o600))

    def test_committed_wal_data_is_included_in_a_standalone_snapshot(self):
        self.ready()
        held=sqlite3.connect(self.root/'.nex/graph.db')
        try:
            held.execute('PRAGMA journal_mode=WAL');held.execute('PRAGMA wal_autocheckpoint=0')
            target=self.edit(42);wal=self.root/'.nex/graph.db-wal'
            self.assertTrue(wal.is_file());self.assertGreater(wal.stat().st_size,0)
            archive,_,manifest=self.snapshot()
            self.assertEqual(manifest['state']['head'],target)
            self.assertFalse((archive/'graph.db-wal').exists());self.assertFalse((archive/'graph.db-shm').exists())
            recovered,_=self.recover(archive)
            self.assertEqual(self.cli('eval','--revision','HEAD',cwd=recovered)['stdout'],'42\n')
        finally:held.close()

    def test_timestamp_defaults_preserve_schema_and_stored_values(self):
        self.ready()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            db.execute("CREATE TABLE timestamp_probe(value TEXT DEFAULT(strftime('%s','now'))) STRICT")
            db.execute('INSERT INTO timestamp_probe DEFAULT VALUES')
            schema=db.execute("SELECT sql FROM sqlite_schema WHERE name='timestamp_probe'").fetchone()[0]
        before=self.rows();archive,_,_=self.snapshot();recovered,_=self.recover(archive)
        self.assertEqual(self.rows(),before);self.assertEqual(self.rows(recovered),before)
        with sqlite3.connect(recovered/'.nex/graph.db') as db:
            self.assertEqual(db.execute("SELECT sql FROM sqlite_schema WHERE name='timestamp_probe'").fetchone()[0],schema)

    def test_current_writer_and_snapshot_observe_one_coherent_database(self):
        self.ready()
        def writer():
            for value in range(42,62):self.edit(value)
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(writer)
            archive,_,manifest=self.snapshot()
            future.result(timeout=60)
        recovered,_=self.recover(archive)
        report=self.cli('changes',cwd=recovered)
        self.assertEqual(report['head'],manifest['state']['head'])
        self.assertEqual(report['head'],report['changes'][0]['revision'])
        self.assertEqual(report['total'],manifest['state']['table_counts']['change_journal'])
        for newer,older in zip(report['changes'],report['changes'][1:]):self.assertEqual(newer['previous_change'],older['hash'])

    def test_uncommitted_wal_writer_does_not_block_or_leak_into_capture(self):
        revision=self.ready();held=sqlite3.connect(self.root/'.nex/graph.db')
        try:
            held.execute('PRAGMA journal_mode=WAL');held.execute('BEGIN IMMEDIATE')
            held.execute("INSERT INTO metadata(key,value) VALUES('uncommitted_writer','must not leak')")
            # The write transaction remains open for the entire CLI capture.
            # A WAL reader must finish without waiting for this writer to commit.
            archive,_,manifest=self.snapshot()
            self.assertEqual(manifest['state']['head'],revision)
            recovered,_=self.recover(archive)
            self.assertNotIn('uncommitted_writer',dict(self.rows(recovered)['metadata']))
        finally:held.rollback();held.close()

    def test_genuine048_schema3_capture_and_recovery_do_not_migrate_source(self):
        fixture=harness.REPO/'tests/fixtures/history-0.48'
        metadata=json.loads(Path(str(fixture)+'.json').read_text());sql=Path(str(fixture)+'.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        (self.root/'.nex').mkdir()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:db.executescript(sql.decode())
        before=self.rows();archive,_,manifest=self.snapshot()
        self.assertEqual(manifest['state']['graph_schema'],3);self.assertEqual(self.rows(),before)
        recovered,_=self.recover(archive);self.assertEqual(self.rows(recovered),before)
        self.assertEqual(dict(self.rows()['metadata'])['schema'],'3')
        self.assertEqual(self.cli('changes',cwd=recovered)['total'],0)
        self.assertEqual(dict(self.rows()['metadata'])['schema'],'3')
        archived=self.rows(recovered)
        self.assertEqual(self.cli('run','--revision','HEAD',cwd=recovered,ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.rows(recovered),archived)
        migrated=self.cli('migrate','--revision',metadata['head_revision'],cwd=recovered)['revision']
        self.assertNotEqual(migrated,metadata['head_revision'])
        after=self.rows(recovered)
        for table,values in archived.items():
            if table not in ('metadata','head'):self.assertTrue(set(values)<=set(after[table]),table)
        self.assertEqual(self.cli('run','--revision','HEAD',cwd=recovered)['stdout'],'42\n')
        self.assertEqual(self.rows(),before)

    def test_multi_module_and_frozen_library_source_survive_deletion(self):
        library=self.root/'library';library.mkdir();(library/'math.nex').write_text('module numbers;pub fn answer()->i64{return 42;}')
        (self.root/'nex.json').write_text(json.dumps({'language':'0.23','entry':'main.nex','libraries':{'numbers':'./library'}}))
        self.source('module app;import "numbers/math.nex" as n;fn main()->unit!{io}{print(n::answer());}')
        self.cli('check');archive,_,_=self.snapshot();self.file.unlink();shutil.rmtree(library)
        recovered,_=self.recover(archive)
        self.assertEqual(self.cli('run','--revision','HEAD',cwd=recovered)['stdout'],'42\n')

    def test_existing_targets_never_change_and_bad_members_are_cleaned_up(self):
        self.ready();archive,_,_=self.snapshot();existing=self.root/'existing';existing.mkdir();sentinel=existing/'keep';sentinel.write_text('keep')
        self.assertEqual(self.cli('snapshot','--directory',existing,ok=False)['code'],'E_EXISTS')
        self.assertEqual(self.cli('recover',archive,'--directory',existing,ok=False)['code'],'E_EXISTS')
        self.assertEqual(sentinel.read_text(),'keep')
        database=archive/'graph.db';original=database.read_bytes();database.write_bytes(original+b'corrupt')
        target,error=self.recover(archive,ok=False);self.assertEqual(error['code'],'E_SNAPSHOT_INTEGRITY');self.assertFalse(target.exists())
        database.write_bytes(original)
        data=json.loads((archive/'snapshot.json').read_text());data['state']['head']='0'*64;(archive/'snapshot.json').write_text(json.dumps(data))
        target,error=self.recover(archive,ok=False);self.assertEqual(error['code'],'E_SNAPSHOT_INTEGRITY');self.assertFalse(target.exists())

    def test_manifest_shape_utf8_bounds_and_links_are_rejected(self):
        self.ready();archive,_,_=self.snapshot();path=archive/'snapshot.json';original=path.read_bytes()
        variants=[b'\xff',b'['*1000+b']'*1000,b' '*65537]
        data=json.loads(original);data['database']['file']='../outside.db';variants.append(json.dumps(data).encode())
        for key,value in [('created','2026-01-01X12:00:00Z'),('toolchain',''),('toolchain','x'*65),('compiler_build','bad')]:
            data=json.loads(original);data[key]=value;variants.append(json.dumps(data).encode())
        for index,value in enumerate(variants):
            path.write_bytes(value);target,error=self.recover(archive,name='bad-'+str(index),ok=False)
            self.assertEqual(error['code'],'E_SNAPSHOT_FORMAT');self.assertFalse(target.exists())
        path.write_bytes(original)
        database=archive/'graph.db';database.rename(archive/'original.db');database.symlink_to(archive/'original.db')
        target,error=self.recover(archive,ok=False);self.assertEqual(error['code'],'E_SNAPSHOT_FILE');self.assertFalse(target.exists())
        database.unlink()
        path.unlink();os.mkfifo(path)
        target,error=self.recover(archive,name='fifo',ok=False);self.assertEqual(error['code'],'E_SNAPSHOT_FILE');self.assertFalse(target.exists())

    def test_discovery_guides_and_model_pack_match_snapshot_protocol(self):
        descriptor=self.cli('describe');pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertIn('consistent_sqlite_backup',descriptor['snapshot_features'])
        self.assertEqual(descriptor['snapshot_schema'],pack['documents']['graph_snapshot_schema'])
        self.assertEqual(descriptor['snapshot_guide'],pack['documents']['snapshots'])
        self.assertEqual(descriptor['snapshot_limits']['manifest_bytes'],65536)
        self.assertFalse(descriptor['snapshot_external_artifacts_included'])
        guide=self.cli('guide','--kind','snapshot')
        self.assertEqual(guide['text'],(harness.REPO/'docs/snapshots.md').read_text())
        self.assertIn('nex recover',self.cli('guide','--kind','prompt')['text'])

    def test_capture_and_recovery_do_not_need_sdk_or_physical_source(self):
        self.ready();before=self.rows();self.file.unlink()
        environment={'NEX_RESOURCE_DIR':str(self.root/'missing-sdk')}
        archive=self.root/'saved'
        self.cli('snapshot','--directory',archive,env=environment)
        recovered=self.root/'recovered'
        self.cli('recover',archive,'--directory',recovered,env=environment)
        self.assertEqual(self.rows(recovered),before)
        self.assertEqual(self.cli('eval','--revision','HEAD',cwd=recovered)['stdout'],'41\n')

    def test_source_views_and_triggers_are_not_executed_or_packaged(self):
        self.ready()
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            db.execute('CREATE VIEW unwanted AS SELECT 1')
        before=self.rows();target=self.root/'bad'
        self.assertEqual(self.cli('snapshot','--directory',target,ok=False)['code'],'E_SNAPSHOT_FORMAT')
        self.assertFalse(target.exists());self.assertEqual(self.rows(),before)
        with sqlite3.connect(self.root/'.nex/graph.db') as db:
            db.execute('DROP VIEW unwanted')
            db.execute("CREATE TRIGGER unwanted BEFORE INSERT ON metadata BEGIN UPDATE revisions SET source='destroyed';END")
        before=self.rows()
        self.assertEqual(self.cli('snapshot','--directory',target,ok=False)['code'],'E_SNAPSHOT_FORMAT')
        self.assertFalse(target.exists());self.assertEqual(self.rows(),before)

    def test_empty_existing_graph_is_recovered_with_its_namespace(self):
        original=self.cli('changes');before=self.rows()
        archive,_,manifest=self.snapshot();self.assertEqual(manifest['state']['head'],'')
        recovered,result=self.recover(archive)
        self.assertEqual(result['namespace'],original['namespace']);self.assertEqual(result['head'],'')
        self.assertEqual(self.rows(recovered),before)

    def test_legitimate_parent_alias_is_supported_but_final_member_links_are_not(self):
        self.ready();parent=self.root/'alias';parent.symlink_to(self.root,target_is_directory=True)
        output=parent/'saved';self.cli('snapshot','--directory',output)
        recovered,result=self.recover(output)
        self.assertTrue(result['ok'])
        self.assertEqual(self.cli('eval','--revision','HEAD',cwd=recovered)['stdout'],'41\n')

    def test_exclusive_rollback_journal_lock_has_a_bounded_timeout(self):
        self.ready();held=sqlite3.connect(self.root/'.nex/graph.db')
        try:
            held.execute('PRAGMA journal_mode=DELETE');held.execute('BEGIN EXCLUSIVE')
            started=time.monotonic();target=self.root/'timeout'
            error=self.cli('snapshot','--directory',target,'--timeout','1',ok=False,timeout=8)
            self.assertEqual(error['code'],'E_SNAPSHOT_TIMEOUT');self.assertLess(time.monotonic()-started,6);self.assertFalse(target.exists())
        finally:held.rollback();held.close()

    def test_missing_database_and_unsupported_options_do_not_create_state(self):
        self.assertEqual(self.cli('snapshot','--directory',self.root/'missing',ok=False)['code'],'E_SNAPSHOT_FILE')
        self.assertFalse((self.root/'.nex').exists())
        for args in [('--timeout','0'),('--timeout','3601'),('--revision','HEAD'),('--target','web'),('--','ignored')]:
            error=self.cli('snapshot','--directory',self.root/'unsupported',*args,ok=False)
            self.assertEqual(error['code'],'E_OPTION');self.assertFalse((self.root/'unsupported').exists())

if __name__=='__main__':unittest.main()
