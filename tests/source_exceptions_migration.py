#!/usr/bin/env python3
"""Migrate genuine024 stores without changing their origins, IDs or schema."""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import support as harness
import unittest


class Public025Migration(harness.ToolchainCase):
    def restore(self,name):
        base=harness.REPO/'tests/fixtures/public025-migration'/name
        metadata=json.loads(base.with_suffix('.json').read_text())
        sql=base.with_suffix('.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(),metadata['sql_sha256'])
        self.source(metadata['source'])
        (self.root/'nex.json').write_text(json.dumps(metadata['manifest']))
        directory=self.root/'.nex';directory.mkdir()
        with sqlite3.connect(str(directory/'graph.db')) as db:
            db.executescript(sql.decode())
        return metadata

    def state(self):
        with sqlite3.connect(str(self.root/'.nex/graph.db')) as db:
            db.execute('pragma query_only=on')
            schema=db.execute('select * from sqlite_master order by name').fetchall()
            tables=[r[0] for r in db.execute("select name from sqlite_master where type='table' order by name")]
            return schema,{name:sorted(db.execute('select * from "'+name+'"').fetchall(),key=repr) for name in tables}

    def preserved(self,before,after):
        self.assertEqual(before[0],after[0]);self.assertEqual(len(after[1]),16)
        for table,rows in before[1].items():
            if table!='head':
                self.assertFalse(collections.Counter(map(repr,rows))-collections.Counter(map(repr,after[1][table])),table)

    def test_unmodified_origin_and_idempotent_apply(self):
        metadata=self.restore('ordinary');before=self.state()
        manifest=(self.root/'nex.json').read_bytes();source=self.file.read_bytes()
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(self.state(),before)
        plan=self.cli('migrate','--kind','plan')
        self.assertTrue(plan['origin_verified'] and plan['target_valid'] and plan['graph_read_only'])
        self.assertEqual(self.state(),before)
        result=self.cli('migrate','--expected-revision',metadata['head'])
        self.assertTrue(result['changed'] and result['origin_verified'])
        self.assertFalse(result['candidate_used']);self.assertEqual(result['language'],'0.25')
        self.assertNotEqual(result['revision'],metadata['head'])
        after=self.state();self.preserved(before,after)
        self.assertEqual((self.root/'nex.json').read_bytes(),manifest);self.assertEqual(self.file.read_bytes(),source)
        self.assertEqual(self.cli('eval','--revision','HEAD')['value'],42)
        self.assertFalse(self.cli('migrate','--expected-revision',result['revision'])['changed'])
        self.assertEqual(self.state(),after)
        with sqlite3.connect(str(self.root/'.nex/graph.db')) as db:
            self.assertEqual(db.execute("select hash from revisions where language='0.24' order by hash").fetchall(),[(v,) for v in sorted(metadata['revisions'])])

    def repair(self,name,diagnostic,target):
        metadata=self.restore(name);before=self.state()
        plan=self.cli('migrate','--kind','plan')
        self.assertTrue(plan['origin_verified']);self.assertFalse(plan['target_valid'])
        self.assertEqual(plan['target_diagnostic']['code'],diagnostic)
        self.assertEqual(self.state(),before)
        self.assertEqual(self.cli('migrate',ok=False)['code'],diagnostic)
        self.assertEqual(self.state(),before)
        candidate=plan['candidate'];candidate['sources']['files']['main.nex']=target
        file=self.root/'candidate.json';file.write_text(json.dumps(candidate))
        bad=dict(candidate);bad['origin_source_hash']='0'*64
        badfile=self.root/'bad.json';badfile.write_text(json.dumps(bad))
        self.assertEqual(self.cli('migrate','--candidate',badfile,ok=False)['code'],'E_MIGRATION_CANDIDATE')
        self.assertEqual(self.state(),before)
        repaired=self.cli('migrate','--candidate',file,'--kind','plan')
        self.assertTrue(repaired['target_valid'] and repaired['candidate_used'])
        self.assertEqual(self.state(),before)
        self.assertEqual(self.cli('migrate','--candidate',file,'--expected-revision','0'*64,ok=False)['code'],'E_CONFLICT')
        self.assertEqual(self.state(),before)
        result=self.cli('migrate','--candidate',file,'--expected-revision',metadata['head'])
        self.assertTrue(result['origin_verified'] and result['candidate_used'])
        self.preserved(before,self.state())
        self.assertEqual(self.cli('eval','--revision','HEAD')['value'],42)
        self.assertEqual(self.file.read_text(),metadata['source'])

    def test_contextual_identifier_requires_reviewed_repair(self):
        self.repair('reserved','E_PARSE','module retained;fn raise_value()->i64{return 42;}fn main()->i64{return raise_value();}')

    def test_new_task_delivery_effect_requires_reviewed_repair(self):
        self.repair('tasks','E_EFFECT','module retained;fn main()->i64 !{task,throw}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{return 42;});}')


if __name__=='__main__':
    unittest.main()
