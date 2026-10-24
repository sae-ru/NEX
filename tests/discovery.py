"""Actual readonly discovery projections and exact capability preservation."""
import json
import os
import stat
import unittest
import support as harness


class Discovery(harness.ToolchainCase):
    def test_default_and_explicit_full_are_identical_and_index_is_complete(self):
        full = self.cli('describe')
        self.assertEqual(self.cli('describe', '--kind', 'full'), full)
        index = self.cli('describe', '--kind', 'index')
        self.assertEqual(index['schema'], 'nex.discovery/1')
        self.assertEqual(index['full_schema'], full['schema'])
        self.assertEqual(index['language'], full['version'])
        self.assertEqual(index['fields'], sorted(full))
        self.assertRegex(index['compiler_build'], r'^[0-9a-f]{64}$')
        self.assertRegex(index['descriptor_hash'], r'^[0-9a-f]{64}$')
        self.assertEqual(self.cli('describe', '--kind', 'index'), index)
        self.assertFalse((self.root / '.nex').exists())

    def test_every_indexed_field_preserves_its_actual_json_value(self):
        full = self.cli('describe')
        index = self.cli('describe', '--kind', 'index')
        for name in index['fields']:
            value = self.cli('describe', '--field', name)
            self.assertEqual(value['kind'], 'field')
            self.assertEqual(value['field'], name)
            self.assertEqual(value['value'], full[name], name)
            for key in ('schema', 'language', 'toolchain', 'compiler_build', 'descriptor_hash'):
                self.assertEqual(value[key], index[key], name)
            self.assertNotIn('fields', value)

    def test_nested_values_keep_types_and_pending_status(self):
        full = self.cli('describe')
        paths = ['scoped_discovery.field_bytes', 'scoped_discovery.graph_store_opened',
                 'project_build.features', 'project_build.server_workload',
                 'source_concurrency.status', 'source_concurrency.source_operations']
        for path in paths:
            expected = full
            for part in path.split('.'):
                expected = expected[part]
            selected = self.cli('describe', '--kind', 'field', '--field', path)
            self.assertEqual(selected['value'], expected)
            self.assertEqual(type(selected['value']), type(expected))
        self.assertEqual(self.cli('describe', '--field', 'source_concurrency.status')['value'], 'development_ordered_cpu_mapping')
        self.assertIs(self.cli('describe', '--field', 'source_concurrency.source_operations')['value'], True)
        self.assertIs(self.cli('describe', '--field', 'source_concurrency.browser_workers')['value'], False)

    def test_invalid_paths_and_mixed_options_do_not_fall_back_to_full(self):
        paths = ['', '.', '..', '.types', 'types.', 'types..item', 'types.0',
                 'types.child', 'absent', 'scoped_discovery.absent', 'types[*]',
                 'types/../version', 'version\n', 'тип', 'a' * 257,
                 '.'.join(['a'] * 9)]
        for path in paths:
            result = self.cli('describe', '--field', path, ok=False)
            self.assertEqual(result['code'], 'E_OPTION', repr(path))
            self.assertNotIn('types', result)
        for args in [('--kind', 'unknown'), ('--kind', 'field'),
                     ('--kind', 'full', '--field', 'types'),
                     ('--kind', 'index', '--field', 'types'),
                     ('--kind', 'full', '--field', ''),
                     ('--symbol', 'main'), ('--library',), ('main.nex',),
                     ('--', 'argument')]:
            self.assertEqual(self.cli('describe', *args, ok=False)['code'], 'E_OPTION', args)
        self.assertFalse((self.root / '.nex').exists())

    def test_empty_stale_and_invalid_projects_are_not_loaded(self):
        for text in ['{', json.dumps({'schema': 'nex.project/1', 'language': 'old', 'entry': 'absent.nex'})]:
            (self.root / 'nex.json').write_text(text)
            self.assertEqual(self.cli('describe', '--field', 'version')['value'], '0.21')
            self.assertEqual(self.cli('describe', '--kind', 'index')['language'], '0.21')
            self.assertFalse((self.root / '.nex').exists())

    def test_existing_graph_rows_ids_and_readonly_inputs_stay_unchanged(self):
        self.source('module existing; fn main()->i64{return 42;}')
        self.cli('check')
        database = self.root / '.nex/graph.db'
        before = harness.database_rows(database)
        (self.root / 'nex.json').write_text('{invalid live project')
        paths = [self.file, self.root / 'nex.json']
        modes = {path: stat.S_IMODE(path.stat().st_mode) for path in paths}
        for path in paths:
            path.chmod(0o400)
        try:
            self.cli('describe', '--kind', 'index')
            self.cli('describe', '--field', 'project_build')
            self.cli('describe', '--field', 'absent', ok=False)
            self.assertEqual(harness.database_rows(database), before)
        finally:
            for path, mode in modes.items():
                path.chmod(mode)

    def test_pack_guides_and_schema_are_installed_capability_contracts(self):
        full = self.cli('describe')
        pack = json.loads((harness.REPO / 'llm/language-pack.json').read_text())
        self.assertEqual(full['scoped_discovery'], pack['scoped_discovery'])
        self.assertEqual(full['task_value_retirement'], pack['task_value_retirement'])
        self.assertFalse(full['task_value_retirement']['source_resource_transport'])
        self.assertEqual(full['resource_regions'], pack['resource_regions'])
        self.assertTrue(full['resource_regions']['native_scheduler'])
        self.assertFalse(full['resource_regions']['source_support'])
        self.assertTrue(full['resource_regions']['reference_scheduler'])
        self.assertEqual(full['resource_regions']['maximum']['scope_depth'], 256)
        self.assertEqual(full['resource_executor'], pack['resource_executor'])
        self.assertFalse(full['resource_executor']['source_support'])
        self.assertFalse(full['resource_executor']['source_task_bridge'])
        self.assertFalse(full['resource_executor']['actual_GPU_NPU_resources'])
        self.assertIn('pre-reserved', full['resource_executor']['cleanup_admission'])
        self.assertEqual(full['model'], pack['model'])
        self.assertEqual(full['model']['import'], 'std/model.nex')
        self.assertFalse(full['model']['builtin_cpu_inference'])
        self.assertFalse(full['model']['source_task_bridge'])
        self.assertEqual(full['structured_tasks_runtime'], pack['structured_tasks_runtime'])
        self.assertEqual(full['task_profile_collector'], pack['task_profile_collector'])
        self.assertTrue(full['task_profile_collector']['source_support'])
        self.assertTrue(full['task_profile_collector']['runtime_integration'])
        self.assertTrue(full['task_profile_collector']['public_profile_enabled'])
        self.assertEqual(full['task_profiling'], pack['task_profiling'])
        self.assertTrue(full['task_profiling']['source_support'])
        self.assertEqual(full['task_profiling']['cli_language'], '0.21')
        self.assertEqual(full['task_profiling']['execution_task_abi'], 3)
        self.assertEqual(full['task_profiling']['report_schema'], 'nex.profile/2')
        self.assertFalse(full['task_profiling']['tracy'])
        self.assertFalse(full['task_profiling']['async_debugger'])
        self.assertFalse(full['task_profiling']['typescript'])
        self.assertTrue(full['structured_tasks_runtime']['source_support'])
        self.assertTrue(full['structured_tasks_runtime']['ordinary_applications_enabled'])
        self.assertFalse(full['structured_tasks_runtime']['private_lifetime_analysis']['fully_static'])
        self.assertTrue(full['structured_tasks_runtime']['private_lifetime_analysis']['mandatory_runtime_guards'])
        self.assertEqual(full['browser_workers'], pack['browser_workers'])
        self.assertTrue(full['browser_workers']['source_support'])
        self.assertFalse(full['browser_workers']['parallel_map_workers'])
        self.assertEqual(full['scoped_discovery']['field_bytes'], 256)
        self.assertEqual(full['scoped_discovery']['path_components'], 8)
        for kind, key in [('discovery', 'scoped_discovery'), ('bootstrap', 'bootstrap_prompt'),
                          ('quality', 'quality_contract'), ('tasks-runtime','tasks_runtime_design'),
                          ('browser-worker','browser_workers'), ('model','model')]:
            guide = self.cli('guide', '--kind', kind)
            self.assertEqual(guide['text'], (harness.REPO / pack['documents'][key]).read_text())
        schema = json.loads((harness.REPO / full['scoped_discovery']['schema_file']).read_text())
        self.assertEqual(schema['properties']['schema']['const'], 'nex.discovery/1')

    def test_projected_responses_are_smaller_without_claiming_token_counts(self):
        full = self.cli('describe', machine=False).stdout.encode()
        index = self.cli('describe', '--kind', 'index', machine=False).stdout.encode()
        types = self.cli('describe', '--field', 'types', machine=False).stdout.encode()
        self.assertLess(len(index), len(full) // 3)
        self.assertLess(len(types), len(full) // 5)
        self.assertTrue(json.loads(index)['fields'])
        self.assertEqual(json.loads(types)['value'], json.loads(full)['types'])


if __name__ == '__main__':
    unittest.main()
