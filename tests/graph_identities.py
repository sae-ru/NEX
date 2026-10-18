"""Persistent declaration nodes and checked, atomic cross-store references."""
import copy
import hashlib
import json
import shutil
import sqlite3
import subprocess
import unittest
from pathlib import Path

import support as harness

LIBRARY = '''module common;
pub struct Box<T>{value:T;}
pub enum Choice{None;Some(value:i64);}
pub fn value()->i64{return 40;}
pub fn bump(x:i64)->i64{return x+value();}
pub fn echo<T>(value:T)->T{return value;}
'''
MAIN = '''module app;import "./library.nex" as lib;
fn main()->unit!{io}{let box:lib::Box<i64>=lib::Box(2);print(lib::bump(lib::echo(box.value)));}
'''


class GraphIdentities(harness.ToolchainCase):
    def project(self, name, source=MAIN, library=LIBRARY):
        directory = self.root / name
        directory.mkdir()
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.15', 'entry': 'main.nex'}))
        (directory / 'main.nex').write_text(source)
        (directory / 'library.nex').write_text(library)
        checked = self.cli('check', cwd=directory)
        return directory, checked['revision']

    def packet(self, directory, *args):
        return self.cli('identities', '--limit', '1000', *args, cwd=directory)

    def reconcile(self, directory, packet, *, expected=None, ok=True):
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(packet))
        if expected is None:
            expected = self.cli('history', cwd=directory)['head']
        return self.cli('identities', '--kind', 'reconcile', '--manifest', path,
                        '--expected-revision', expected, cwd=directory, ok=ok)

    def rows(self, directory):
        with sqlite3.connect(directory / '.nex/graph.db') as db:
            names = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {name: sorted(db.execute('SELECT * FROM "' + name + '"').fetchall(), key=repr) for name in names}

    def test_declared_type_and_module_ids_survive_edits_and_old_revisions(self):
        directory, original = self.project('first')
        graph = self.cli('graph', cwd=directory)
        self.assertEqual(graph['schema'], 'nex.graph/2')
        self.assertEqual(graph['identity_namespace'], graph['declaration_graph']['namespace'])
        old = {n['symbol']: n for n in graph['declaration_graph']['nodes']}
        self.assertEqual(old['common::Box']['kind'], 'type')
        self.assertIn('common::Box<i64>', old)
        self.assertEqual(graph['modules'][0]['id'], old[graph['modules'][0]['name']]['id'])
        (directory / 'library.nex').write_text(LIBRARY.replace('return 40;', 'return 41;').replace('value:T;', 'value:T;flag:bool;'))
        (directory / 'main.nex').write_text(MAIN.replace('lib::Box(2)', 'lib::Box(2,true)'))
        revised = self.cli('check', cwd=directory)['revision']
        self.assertNotEqual(original, revised)
        new = {n['symbol']: n for n in self.cli('declarations', '--limit', '1000', cwd=directory)['nodes']}
        for name in old:
            self.assertEqual(old[name]['id'], new[name]['id'])
        self.assertNotEqual(old['common']['hash'], new['common']['hash'])
        self.assertNotEqual(old['common::Box']['hash'], new['common::Box']['hash'])
        archived = self.cli('declarations', '--revision', original, '--limit', '1000', cwd=directory)
        self.assertEqual({n['symbol']: n['hash'] for n in archived['nodes']}, {name: n['hash'] for name, n in old.items()})
        context = self.cli('context', '--entity', 'type', '--symbol', 'common::Box', cwd=directory)
        self.assertEqual(context['schema'], 'nex.declaration-context/1')
        self.assertEqual(context['node']['id'], old['common::Box']['id'])
        self.assertIn('flag:bool', context['node']['source'])
        self.assertEqual(self.cli('history', cwd=directory)['head'], revised)

    def test_same_graph_reconciles_every_entity_kind_without_rewriting_local_ids(self):
        source, revision = self.project('source')
        target, _ = self.project('target')
        packet = self.packet(source)
        local = self.packet(target)
        self.assertEqual(packet['revision'], revision)
        self.assertNotEqual(packet['namespace'], local['namespace'])
        self.assertFalse(packet['truncated'])
        before_ids = {(n['kind'], n['symbol'], n['path']): n['id'] for n in local['nodes']}
        self.assertNotEqual([n['id'] for n in packet['nodes']], [n['id'] for n in local['nodes']])
        response = self.reconcile(target, packet)
        self.assertEqual(len(response['mappings']), len(packet['nodes']))
        after = self.packet(target)
        self.assertEqual(before_ids, {(n['kind'], n['symbol'], n['path']): n['id'] for n in after['nodes']})
        self.assertEqual(self.cli('history', cwd=target)['head'], revision)
        for kind in ('module', 'type', 'function', 'operation'):
            remote = next(n for n in packet['nodes'] if n['kind'] == kind)
            resolved = self.cli('identities', '--kind', 'resolve', '--origin', packet['namespace'],
                                '--from-revision', packet['revision'], '--node', remote['id'], cwd=target)
            self.assertEqual(resolved['target']['node']['id'], before_ids[(kind, remote['symbol'], remote['path'])])
        self.assertEqual(self.reconcile(target, packet)['mappings'], response['mappings'])

    def test_shared_library_scope_reconciles_between_different_applications(self):
        first, source_revision = self.project('source')
        other_source = MAIN.replace('module app;', 'module other;').replace('lib::Box<i64>=lib::Box(2)', 'lib::Box<str>=lib::Box("two")').replace('lib::bump(lib::echo(box.value))', 'lib::bump(len(lib::echo(box.value)))')
        second, target_revision = self.project('target', other_source)
        self.assertNotEqual(source_revision, target_revision)
        packet = self.packet(first, '--entity', 'module', '--symbol', 'common')
        self.assertTrue(any(n['kind'] == 'operation' for n in packet['nodes']))
        self.assertFalse(any('<i64>' in n['symbol'] for n in packet['nodes']))
        response = self.reconcile(second, packet)
        self.assertEqual(response['source_revision'], source_revision)
        self.assertEqual(response['revision'], target_revision)
        self.assertEqual(self.cli('eval', cwd=first)['stdout'], self.cli('eval', cwd=second)['stdout'])

    def test_transitive_dependency_changes_reject_unchanged_function_text_atomically(self):
        first, _ = self.project('source')
        second, _ = self.project('target', library=LIBRARY.replace('return 40;', 'return 41;'))
        packet = self.packet(first, '--entity', 'function', '--symbol', 'common::bump')
        local = self.packet(second, '--entity', 'function', '--symbol', 'common::bump')
        self.assertEqual(packet['nodes'][0]['hash'], local['nodes'][0]['hash'])
        self.assertNotEqual(packet['nodes'][0]['context_hash'], local['nodes'][0]['context_hash'])
        before = self.rows(second)
        rejected = self.reconcile(second, packet, ok=False)
        self.assertEqual(rejected['code'], 'E_IDENTITY_CONTENT')
        self.assertEqual(self.rows(second), before)

    def test_duplicates_stale_head_self_namespace_and_conflicts_do_not_partially_write(self):
        first, _ = self.project('source')
        second, revision = self.project('target')
        packet = self.packet(first)
        self.packet(second)
        baseline = self.rows(second)
        stale = self.reconcile(second, packet, expected='0' * 64, ok=False)
        self.assertEqual(stale['code'], 'E_CONFLICT')
        self.assertEqual(self.rows(second), baseline)
        for edit in ('bad_hash', 'duplicate', 'self_namespace'):
            changed = copy.deepcopy(packet)
            if edit == 'bad_hash':
                changed['nodes'][-1]['context_hash'] = 'f' * 64
            elif edit == 'duplicate':
                changed['nodes'][-1]['id'] = changed['nodes'][0]['id']
            else:
                changed['namespace'] = self.packet(second)['namespace']
            self.reconcile(second, changed, ok=False)
            self.assertEqual(self.rows(second), baseline, edit)
        self.reconcile(second, packet)
        mapped = self.rows(second)
        changed = copy.deepcopy(packet)
        changed['nodes'][0]['id'] = 'another-remote-identity'
        self.assertEqual(self.reconcile(second, changed, ok=False)['code'], 'E_IDENTITY_CONFLICT')
        self.assertEqual(self.rows(second), mapped)
        self.assertEqual(self.cli('history', cwd=second)['head'], revision)

    def test_recursion_context_and_pages_are_deterministic(self):
        source = 'module recursive;fn a(n:i64)->i64{if n==0{return 0;}return b(n-1);}fn b(n:i64)->i64{if n==0{return 1;}return a(n-1);}fn main()->i64{return a(3);}'
        directory, old = self.project('recursive', source)
        full = self.packet(directory)
        pages = []
        for offset in range(0, full['total'], 7):
            pages += self.cli('identities', '--offset', str(offset), '--limit', '7', cwd=directory)['nodes']
        self.assertEqual(pages, full['nodes'])
        before = self.packet(directory, '--entity', 'function', '--symbol', 'a')['nodes'][0]
        (directory / 'main.nex').write_text(source.replace('return 1;', 'return 2;'))
        self.cli('check', cwd=directory)
        after = self.packet(directory, '--entity', 'function', '--symbol', 'a')['nodes'][0]
        self.assertEqual(before['id'], after['id'])
        self.assertEqual(before['hash'], after['hash'])
        self.assertNotEqual(before['context_hash'], after['context_hash'])
        archived = self.cli('identities', '--revision', old, '--entity', 'function', '--symbol', 'a', cwd=directory)
        self.assertEqual(archived['nodes'][0], before)

    def test_genuine_043_store_backfills_without_rewriting_history(self):
        metadata = json.loads((harness.REPO / 'tests/fixtures/graph-0.43.json').read_text())
        sql = (harness.REPO / 'tests/fixtures/graph-0.43.sql').read_bytes()
        self.assertEqual(hashlib.sha256(sql).hexdigest(), metadata['sql_sha256'])
        directory = self.root / 'archived'
        (directory / '.nex').mkdir(parents=True)
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.15', 'entry': 'main.nex'}))
        with sqlite3.connect(directory / '.nex/graph.db') as db:
            db.executescript(sql.decode())
            source_rows = db.execute('SELECT hash,source,path,language FROM revisions ORDER BY hash').fetchall()
        graph = self.cli('graph', cwd=directory)
        self.assertEqual(graph['revision'], metadata['revision'])
        with sqlite3.connect(directory / '.nex/graph.db') as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0], '3')
            self.assertEqual(db.execute('SELECT hash,source,path,language FROM revisions ORDER BY hash').fetchall(), source_rows)
            self.assertEqual([list(r) for r in db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name')], metadata['node_ids'])
            self.assertEqual([list(r) for r in db.execute('SELECT revision,function,path,id,hash,site FROM operation_versions ORDER BY revision,function,path')], metadata['operations'])
        self.assertEqual(self.cli('eval', '--revision', 'HEAD', cwd=directory)['stdout'], metadata['stdout'])
        self.assertTrue(graph['declaration_graph']['nodes'])
        old = harness.REPO / 'build/nex-043-corrected-verified'
        if old.exists():
            process = subprocess.run([str(old), 'eval', '--revision', 'HEAD', '--json'], cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(json.loads(process.stdout)['stdout'], metadata['stdout'])


if __name__ == '__main__':
    unittest.main()
