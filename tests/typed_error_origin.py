"""Genuine026 history retained before the future typed-error migration."""
import hashlib
import json
from pathlib import Path
import sqlite3
import unittest
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
        for revision,expected in zip(meta['revisions'],meta['actual_origin_eval_stdout']):
            self.assertEqual(self.cli('eval','--revision',revision)['stdout'],expected)
            self.assertEqual(harness.database_rows(graph),before)
        self.assertEqual(self.cli('check')['revision'],meta['head'])
        self.assertEqual(harness.database_rows(graph),before)
        fresh=self.root/'fresh';fresh.mkdir()
        (fresh/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.26','entry':'main.nex'}))
        for text,revision in zip(meta['historical_sources'],meta['revisions']):
            (fresh/'main.nex').write_text(text)
            self.assertEqual(self.cli('check',cwd=fresh)['revision'],revision)
        self.assertFalse(self.cli('describe','--field','source_exceptions')['value']['typed_payloads'])

if __name__=='__main__':unittest.main()
