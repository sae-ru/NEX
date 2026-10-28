"""Persistent declaration nodes and checked, atomic cross-store references."""
import copy
import hashlib
import json
import os
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
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.24', 'entry': 'main.nex'}))
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
        (target / 'library.nex').write_text(LIBRARY.replace('return 40;', 'return 41;'))
        new_revision = self.cli('check', cwd=target)['revision']
        args = ('identities', '--kind', 'resolve', '--origin', packet['namespace'],
                '--from-revision', revision, '--node', packet['nodes'][0]['id'])
        self.assertEqual(self.cli(*args, cwd=target, ok=False)['code'], 'E_IDENTITY_REF')
        self.assertEqual(self.cli(*args, '--revision', revision, cwd=target)['target']['revision'], revision)
        self.assertEqual(self.cli('history', cwd=target)['head'], new_revision)

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
        self.assertEqual(self.cli('eval', cwd=first)['stdout'], '42\n')
        self.assertEqual(self.cli('eval', cwd=second)['stdout'], '43\n')

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
        (directory / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': metadata['language'], 'entry': 'main.nex'}))
        with sqlite3.connect(directory / '.nex/graph.db') as db:
            db.executescript(sql.decode())
            source_rows = db.execute('SELECT hash,source,path,language FROM revisions ORDER BY hash').fetchall()
        old = Path(os.environ.get('NEX_LEGACY_043_COMPILER', str(harness.REPO / 'build/nex-043-corrected-verified')))
        if old.exists():
            # Preserve a genuine schema3 database for the original SDK. The
            # schema4 journal deliberately prevents legacy unrecorded writers.
            legacy = self.root / 'legacy'
            (legacy / '.nex').mkdir(parents=True)
            (legacy / 'nex.json').write_text((directory / 'nex.json').read_text())
            with sqlite3.connect(legacy / '.nex/graph.db') as db:db.executescript(sql.decode())
            process = subprocess.run([str(old), 'eval', '--revision', 'HEAD', '--json'], cwd=legacy, capture_output=True, text=True, timeout=30)
            self.assertEqual(process.returncode, 0, process.stdout + process.stderr)
            self.assertEqual(json.loads(process.stdout)['stdout'], metadata['stdout'])
        self.assertEqual(self.cli('graph','--revision',metadata['revision'],cwd=directory,ok=False)['code'],'E_LANGUAGE_VERSION')
        migrated=self.cli('migrate','--revision',metadata['revision'],cwd=directory)['revision']
        graph=self.cli('graph','--revision','HEAD',cwd=directory)
        self.assertEqual(graph['revision'],migrated);self.assertNotEqual(migrated,metadata['revision'])
        with sqlite3.connect(directory / '.nex/graph.db') as db:
            self.assertEqual(db.execute("SELECT value FROM metadata WHERE key='schema'").fetchone()[0], '4')
            self.assertTrue(set(source_rows)<=set(db.execute('SELECT hash,source,path,language FROM revisions ORDER BY hash').fetchall()))
            self.assertEqual([list(r) for r in db.execute('SELECT module,name,id FROM node_ids ORDER BY module,name')], metadata['node_ids'])
            old_revisions={row[0] for row in source_rows}
            self.assertEqual([list(r) for r in db.execute('SELECT revision,function,path,id,hash,site FROM operation_versions ORDER BY revision,function,path') if r[0] in old_revisions], metadata['operations'])
        self.assertEqual(self.cli('eval', '--revision', 'HEAD', cwd=directory)['stdout'], metadata['stdout'])
        self.assertTrue(graph['declaration_graph']['nodes'])
        if old.exists():
            before_refusal = self.rows(directory)
            process = subprocess.run([str(old), 'eval', '--revision', 'HEAD', '--json'], cwd=directory, capture_output=True, text=True, timeout=30)
            self.assertNotEqual(process.returncode, 0)
            self.assertEqual(json.loads(process.stdout)['code'], 'E_SCHEMA')
            self.assertEqual(self.rows(directory), before_refusal)

    def test_malformed_page_metadata_and_out_of_scope_records_are_atomic(self):
        first, _ = self.project('source')
        second, _ = self.project('target')
        packet = self.packet(first)
        baseline = self.rows(second)
        variants = []
        for key in packet:
            missing = copy.deepcopy(packet)
            del missing[key]
            variants.append((f'missing {key}', missing))
        for key, value in [('offset', -1), ('offset', 0.5), ('total', len(packet['nodes'])-1),
                           ('truncated', True), ('selection', {}), ('selection', {'entity': 'function', 'symbol': 'common::bump'}),
                           ('extra', True)]:
            changed = copy.deepcopy(packet)
            changed[key] = value
            variants.append((key, changed))
        for label, changed in variants:
            with self.subTest(label=label):
                self.reconcile(second, changed, ok=False)
                self.assertEqual(self.rows(second), baseline)
        for args in [('--origin', 'bad'), ('--manifest', 'missing.json'),
                     ('--kind', 'resolve', '--origin', 'bad', '--from-revision', packet['revision'], '--node', 'x')]:
            self.cli('identities', *args, cwd=second, ok=False)
        self.assertEqual(self.rows(second), baseline)

    def test_corrupt_local_metadata_is_rejected_instead_of_being_exported(self):
        mutations = [
            "UPDATE declaration_versions SET hash='bad' WHERE kind='type'",
            "DELETE FROM graph_edges WHERE source_kind='module'",
            "UPDATE operation_versions SET site='bad' WHERE rowid=(SELECT min(rowid) FROM operation_versions)",
            "UPDATE operation_versions SET kind='bad'",
            "UPDATE operation_functions SET content_hash='bad'",
            "UPDATE metadata SET value='bad' WHERE key='identity_namespace'",
            "UPDATE identity_revisions SET policy='future-policy'",
        ]
        for index, mutation in enumerate(mutations):
            directory, _ = self.project('corrupt-'+str(index))
            with sqlite3.connect(directory / '.nex/graph.db') as db:
                db.execute(mutation)
            before = self.rows(directory)
            self.cli('identities', cwd=directory, ok=False)
            self.assertEqual(self.rows(directory), before)

    def test_source_deleted_graph_import_paging_and_archived_resolution(self):
        first, revision = self.project('source', MAIN+'test fn consistent()->unit{assert(lib::bump(2)==42);}')
        graph = self.cli('graph', cwd=first)
        graph_file = self.root / 'graph.json'
        graph_file.write_text(json.dumps(graph))
        second = self.root / 'imported'
        second.mkdir()
        (second / 'nex.json').write_text(json.dumps({'language': '0.24', 'entry': 'main.nex'}))
        self.assertEqual(self.cli('import', graph_file, cwd=second)['revision'], revision)
        (first / 'main.nex').unlink()
        (first / 'library.nex').unlink()
        full = self.packet(first)
        mapped = []
        for offset in range(0, full['total'], 7):
            page = self.cli('identities', '--offset', str(offset), '--limit', '7', cwd=first)
            mapped += self.reconcile(second, page)['mappings']
        self.assertEqual(len(mapped), full['total'])
        remote = full['nodes'][-1]
        resolved = self.cli('identities', '--kind', 'resolve', '--origin', full['namespace'],
                            '--from-revision', revision, '--node', remote['id'], cwd=second)
        self.assertEqual(resolved['target']['node']['context_hash'], remote['context_hash'])
        self.assertEqual(self.cli('eval', '--revision', 'HEAD', cwd=second)['stdout'], '42\n')
        self.assertEqual(self.cli('run', '--revision', 'HEAD', cwd=second)['stdout'], '42\n')
        tested = self.cli('test', '--revision', 'HEAD', '--target', 'web', cwd=second)
        self.assertTrue(tested['ok'])
        self.assertFalse((second / 'main.nex').exists())

    def test_declaration_context_has_bounded_utf8_source_definitions_and_references(self):
        big = 'struct Big{// '+('я'*3000)+'\n'+''.join('field_'+str(i)+':i64;' for i in range(500))+'}\n'
        many = ''.join('struct Row'+str(i)+'{value:i64;}\n' for i in range(110))
        directory, _ = self.project('bounded', 'module bounds;'+big+many+'fn main()->unit{}')
        module = self.cli('context', '--entity', 'module', '--symbol', 'bounds', cwd=directory)['node']
        self.assertTrue(module['definition_omitted'])
        self.assertIsNone(module['definition'])
        self.assertEqual(len(module['references']), 100)
        self.assertTrue(module['references_truncated'])
        node = self.cli('context', '--entity', 'type', '--symbol', 'Big', cwd=directory)['node']
        self.assertTrue(node['source_truncated'])
        self.assertLessEqual(len(node['source'].encode()), 4096)
        self.assertTrue(node['definition_omitted'])
        self.assertTrue(node['editable'])

    def test_concurrent_conflicting_aliases_commit_one_complete_page(self):
        first, _ = self.project('source')
        second, revision = self.project('target')
        packet = self.packet(first, '--entity', 'function', '--symbol', 'common::bump')
        changed = copy.deepcopy(packet)
        changed['nodes'][0]['id'] = 'conflicting-remote-id'
        processes = []
        for index, value in enumerate((packet, changed)):
            file = self.root / ('page-'+str(index)+'.json')
            file.write_text(json.dumps(value))
            processes.append(subprocess.Popen([harness.NEX, 'identities', '--kind', 'reconcile',
                '--manifest', str(file), '--expected-revision', revision, '--json'],
                cwd=second, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        results = []
        for process in processes:
            out, err = process.communicate(timeout=30)
            results.append((process.returncode, json.loads(out)))
            self.assertFalse(err)
        self.assertEqual(sorted(code for code, _ in results), [0, 1])
        self.assertEqual(next(value['code'] for code, value in results if code), 'E_IDENTITY_CONFLICT')
        self.assertEqual(len(self.rows(second)['identity_links']), 1)
        self.assertEqual(self.cli('history', cwd=second)['head'], revision)

    def test_endpoint_references_include_handler_context_and_explicit_context_kind(self):
        source = '''module app;import "std/api.nex" as api;
server fn read(context:api::Context)->result<i64>{return ok(42);}
endpoint fetch_value("GET","/api/value")=read;
fn main()->unit{}
'''
        first, _ = self.project('source', source)
        second, _ = self.project('target', source)
        packet = self.packet(first, '--entity', 'endpoint', '--symbol', 'fetch_value')
        self.assertEqual(len(packet['nodes']), 1)
        self.reconcile(second, packet)
        self.assertEqual(self.cli('context', '--entity', 'endpoint', '--symbol', 'fetch_value', cwd=second)['kind'], 'endpoint')
        function = self.cli('context', '--entity', 'function', '--symbol', 'read', cwd=second)
        self.assertNotIn('kind', function)
        self.assertEqual(self.cli('context', '--entity', 'endpoint', '--symbol', 'read', cwd=second, ok=False)['code'], 'E_IDENTITY_SYMBOL')
        self.assertIn('return ok(42)', function['source'])
        (second / 'main.nex').write_text(source.replace('ok(42)', 'ok(43)'))
        self.cli('check', cwd=second)
        local = self.packet(second, '--entity', 'endpoint', '--symbol', 'fetch_value')['nodes'][0]
        self.assertEqual(local['hash'], packet['nodes'][0]['hash'])
        self.assertNotEqual(local['context_hash'], packet['nodes'][0]['context_hash'])
        self.assertEqual(self.reconcile(second, packet, ok=False)['code'], 'E_IDENTITY_CONTENT')

    def test_manifest_file_boundaries_and_special_files(self):
        first, _ = self.project('source')
        second, revision = self.project('target')
        packet = json.dumps(self.packet(first, '--entity', 'function', '--symbol', 'common::bump')).encode()
        file = self.root / 'packet.json'
        file.write_bytes(packet+b' '*(4*1048576-len(packet)))
        def reconcile(path, ok=True):
            return self.cli('identities', '--kind', 'reconcile', '--manifest', path,
                            '--expected-revision', revision, cwd=second, ok=ok, timeout=5)
        self.assertTrue(reconcile(file)['ok'])
        baseline = self.rows(second)
        file.write_bytes(file.read_bytes()+b' ')
        self.assertEqual(reconcile(file, False)['code'], 'E_IDENTITY_LIMIT')
        file.write_bytes(packet.replace(b'common::bump', b'common::bu\xffp'))
        self.assertEqual(reconcile(file, False)['code'], 'E_JSON')
        link = self.root / 'link.json'
        link.symlink_to(file)
        fifo = self.root / 'fifo.json'
        os.mkfifo(fifo)
        for path in (link, fifo, self.root):
            self.assertEqual(reconcile(path, False)['code'], 'E_IDENTITY_LIMIT')
        self.assertEqual(self.rows(second), baseline)

    def test_identity_order_and_hashes_ignore_import_alias_paths_and_declaration_order(self):
        directory, revision = self.project('reordered')
        original = self.packet(directory)
        (directory / 'library.nex').rename(directory / 'relocated.nex')
        reordered = LIBRARY.replace('pub fn value()->i64{return 40;}\n', '')+'pub fn value()->i64{return 40;}\n'
        (directory / 'relocated.nex').write_text(reordered)
        (directory / 'main.nex').write_text(MAIN.replace('library.nex', 'relocated.nex').replace('as lib;', 'as renamed;').replace('lib::', 'renamed::'))
        after = self.cli('identities', directory / 'main.nex', '--limit', '1000', cwd=directory)
        self.assertEqual(after['revision'], revision)
        self.assertNotEqual(after['source_hash'], original['source_hash'])
        self.assertEqual(after['nodes'], original['nodes'])
        old_choice = next(n for n in original['nodes'] if n['kind'] == 'type' and n['symbol'] == 'common::Choice')
        (directory / 'relocated.nex').write_text(reordered.replace('pub enum Choice{None;Some(value:i64);}', ''))
        self.cli('check', cwd=directory)
        self.assertFalse(any(n['symbol'] == 'common::Choice' for n in self.packet(directory)['nodes']))
        (directory / 'relocated.nex').write_text(reordered)
        self.cli('check', cwd=directory)
        restored = next(n for n in self.packet(directory)['nodes'] if n['kind'] == 'type' and n['symbol'] == 'common::Choice')
        self.assertEqual(restored, old_choice)


    def test_deep_statement_matches_have_linear_dependency_traversal(self):
        body = 'return 42;'
        for _ in range(30):
            body = 'match true{true=>{'+body+'}false=>{return 0;}}'
        source = 'module deep;fn calculate()->i64{'+body+'}fn main()->i64{return calculate();}test fn exercise()->unit{assert(calculate()==42);}'
        self.source(source)
        self.cli('check', self.file, timeout=5)
        packet = self.cli('identities', '--entity', 'function', '--symbol', 'calculate', timeout=5)
        self.assertEqual(len(packet['nodes']), 1)
        self.assertEqual(self.cli('eval', '--revision', 'HEAD')['value'], 42)
        self.assertTrue(self.cli('test', '--revision', 'HEAD')['ok'])
        self.assertTrue(self.cli('test', '--revision', 'HEAD', '--target', 'web')['ok'])

    def test_statement_match_arm_local_types_participate_in_context(self):
        source = '''module arm_types;enum Tag{One;Two;}
fn calculate()->i64{match true{true=>{let local:Tag=Tag::One();return 42;}false=>{return 0;}}}
fn main()->i64{return calculate();}
'''
        directory, _ = self.project('arm-types', source)
        before = self.packet(directory, '--entity', 'function', '--symbol', 'calculate')['nodes'][0]
        (directory / 'main.nex').write_text(source.replace('enum Tag{One;Two;}', 'enum Tag{One;Two;Three;}'))
        self.cli('check', cwd=directory)
        after = self.packet(directory, '--entity', 'function', '--symbol', 'calculate')['nodes'][0]
        self.assertEqual(before['hash'], after['hash'])
        self.assertNotEqual(before['context_hash'], after['context_hash'])


if __name__ == '__main__':
    unittest.main()
