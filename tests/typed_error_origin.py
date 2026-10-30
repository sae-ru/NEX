"""Retain actual026 identities while the ordinary CLI selects027."""
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
PROBE=Path(sys.argv.pop(2)).resolve()
import support as harness

class TypedErrorOrigin(harness.ToolchainCase):
    def test_actual026_history_rows_ids_and_canonical_revisions_are_preserved(self):
        fixture=harness.REPO/'tests/fixtures/language-0.26-typed-origin'
        meta=json.loads(Path(str(fixture)+'.json').read_text());sql=Path(str(fixture)+'.sql').read_bytes()
        self.assertEqual(meta['language'],'0.26');self.assertFalse(meta['retagged_source'])
        self.assertEqual(meta['producer']['toolchain'],'0.139.0')
        self.assertEqual(hashlib.sha256(sql).hexdigest(),meta['sql_sha256'])
        self.source(meta['source']);(self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'}))
        graph=self.root/'.nex/graph.db';graph.parent.mkdir(exist_ok=True)
        with sqlite3.connect(str(graph)) as db:db.executescript(sql.decode())
        before=harness.database_rows(graph)
        self.assertEqual(len(before[1]),16);self.assertEqual({k:len(v) for k,v in before[1].items()},meta['table_counts'])
        def inspect(mode,**extra):
            request=self.root/'inspect.json'
            request.write_text(json.dumps({'schema':'nex.typed-error-migration-request/1','mode':mode,'project':str(self.root),**extra}))
            observed=subprocess.run([PROBE,request],capture_output=True,text=True,timeout=60)
            self.assertEqual(observed.returncode,0,observed.stdout+observed.stderr)
            return json.loads(observed.stdout)
        for revision,expected,text in zip(meta['revisions'],meta['actual_origin_eval_stdout'],meta['historical_sources']):
            self.assertEqual(self.cli('eval','--revision',revision,ok=False)['code'],'E_LANGUAGE_VERSION')
            retained=inspect('evaluate',revision=revision)
            self.assertEqual(retained['language'],'0.26');self.assertEqual(retained['revision'],revision)
            self.assertEqual(retained['ast'],retained['ir']);self.assertEqual(retained['ast']['stdout'],expected)
            fresh=inspect('inspect-versioned-source',source_language='0.26',sources={'schema':'nex.sources/1','entry':'main.nex','files':{'main.nex':text}})
            self.assertEqual(fresh['revision'],revision);self.assertEqual(fresh['language'],'0.26')
            self.assertEqual(fresh['ast'],retained['ast']);self.assertEqual(fresh['ir'],retained['ir'])
            self.assertEqual(harness.database_rows(graph),before)
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        self.assertEqual(harness.database_rows(graph),before)
        self.assertTrue(self.cli('describe','--field','source_exceptions')['value']['typed_payloads'])

if __name__=='__main__':unittest.main()
