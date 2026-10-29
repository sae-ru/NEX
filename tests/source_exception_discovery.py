"""Private exception scope and retained024 syntax/graph identity."""
import json
import unittest
import support as harness


class SourceExceptionDiscovery(harness.ToolchainCase):
    def test_private_descriptor_pack_and_guide_stay_separate_from_public025(self):
        pack = json.loads((harness.REPO / 'llm/language-pack.json').read_text())
        actual = self.cli('describe', '--field', 'source_exception_prototype')
        self.assertEqual(actual['value'], pack['source_exception_prototype'])
        self.assertEqual(actual['language'], '0.26')
        public=self.cli('describe','--field','source_exceptions')
        self.assertEqual(public['value'],pack['source_exceptions'])
        self.assertEqual(public['value']['source_language'],'0.26')
        self.assertTrue(public['value']['frontend'] and public['value']['reference'])
        grants=self.cli('describe','--field','structured_tasks_runtime.http_server.file_grants')['value']
        self.assertEqual(grants,pack['structured_tasks_runtime']['http_server']['file_grants'])
        self.assertEqual(grants['root_option'],'--files-root')
        self.assertEqual(grants['write_option'],'--files-write')
        self.assertFalse(grants['writable_default'])
        self.assertTrue(grants['root_pinned_before_workers'] and grants['per_request_lexical_scope'])
        self.assertTrue(grants['synchronous_handlers'] and grants['task_handlers'])
        self.assertFalse(grants['complete_delivery_accepted'])
        self.assertEqual(self.cli('guide','--kind','exception')['text'],
                         (harness.REPO/'docs/exceptions.md').read_text())
        self.assertIs(actual['value']['source_support'], False)
        self.assertIs(actual['value']['native'], False)
        self.assertIs(actual['value']['private_native_sequential_experiment'], True)
        self.assertEqual(actual['value']['private_native_emitter'], 'emitSourceExceptionsPrototypeMLIR')
        self.assertIs(actual['value']['typescript'], False)
        self.assertIs(actual['value']['private_typescript_sequential_experiment'], True)
        self.assertEqual(actual['value']['private_typescript_emitter'], 'emitSourceExceptionsPrototypeTypeScript')
        self.assertIs(actual['value']['private_task_reference_experiment'], True)
        self.assertIs(actual['value']['private_task_native'], True)
        self.assertIs(actual['value']['private_task_native_physical_workers'], True)
        self.assertIs(actual['value']['private_task_native_complete_delivery'], False)
        self.assertIs(actual['value']['private_task_native_global_resource_fatal'], True)
        self.assertIs(actual['value']['private_task_native_profile'], True)
        self.assertIs(actual['value']['private_task_native_profile_cli'], False)
        self.assertIs(actual['value']['private_task_native_debug'], True)
        self.assertIs(actual['value']['private_task_native_debug_cli'], False)
        self.assertIs(actual['value']['private_task_native_debug_LLDB_DAP'], True)
        self.assertIs(actual['value']['private_task_native_debug_all_stop'], True)
        self.assertIs(actual['value']['private_task_native_debug_expressions'], True)
        self.assertIs(actual['value']['private_task_native_host_bridges'], True)
        self.assertEqual(actual['value']['private_task_native_host_descriptor_abi'], '0x4e45585400002502')
        self.assertIs(actual['value']['private_task_native_host_http'], True)
        self.assertIs(actual['value']['private_task_native_http_public_build'], False)
        self.assertIs(actual['value']['private_task_native_http_profile'], False)
        self.assertIs(actual['value']['private_task_native_http_logical_debug'], False)
        self.assertEqual(self.cli('guide', '--kind', 'exception-http')['text'],
                         (harness.REPO / 'docs/source-exception-http.md').read_text())
        self.assertIs(actual['value']['private_task_native_host_binary_providers'], True)
        self.assertIs(actual['value']['private_task_native_module_public_build'], False)
        self.assertIs(actual['value']['private_task_native_module_HTTP'], True)
        self.assertEqual(actual['value']['private_task_native_module_HTTP_record'], 'nex.private-task-module/4')
        self.assertEqual(self.cli('guide', '--kind', 'exception-module-http')['text'],
                         (harness.REPO / 'docs/source-exception-module-http.md').read_text())
        self.assertIs(actual['value']['private_task_native_module_profile'], True)
        self.assertIs(actual['value']['private_task_native_module_HTTP_profile'], True)
        self.assertIs(actual['value']['private_task_native_module_HTTP_profile_request_ID_correlation'], False)
        self.assertIs(actual['value']['private_task_native_module_profile_public_CLI'], False)
        self.assertEqual(self.cli('guide', '--kind', 'exception-module-profile')['text'],
                         (harness.REPO / 'docs/source-exception-module-profile.md').read_text())
        self.assertIs(actual['value']['private_task_native_module_logical_debug'], True)
        self.assertIs(actual['value']['private_task_native_module_HTTP_logical_debug'], True)
        self.assertEqual(actual['value']['private_task_native_module_HTTP_debug_request_ID'], 'req.request_id')
        self.assertEqual(actual['value']['private_task_native_module_HTTP_debug_conformance'], 'source_exception_module_http_debug')
        self.assertEqual(actual['value']['private_task_native_module_debug_context'], 'nex.private-task-debug/2')
        self.assertEqual(self.cli('guide', '--kind', 'exception-module-debug')['text'],
                         (harness.REPO / 'docs/source-exception-module-debug.md').read_text())
        self.assertIs(actual['value']['private_task_native_module_mixed_frontiers'], True)
        self.assertIs(actual['value']['private_task_native_module_unique_physical_image'], True)
        self.assertIs(actual['value']['private_task_native_module_consumer_trait_specializations'], True)
        self.assertEqual(actual['value']['private_task_native_instance_catalogue'], 'describeSourceExceptionTaskInstances')
        self.assertEqual(actual['value']['private_task_native_instance_record'], 'nex.private-task-module/3')
        self.assertIs(actual['value']['private_task_native_instance_catalogue_template_filter'], True)
        self.assertEqual(actual['value']['private_task_native_instance_catalogue_default_limit'], 64)
        self.assertEqual(actual['value']['private_task_native_instance_catalogue_max_limit'], 256)
        self.assertIs(actual['value']['private_task_native_instance_automatic_placement'], False)
        self.assertEqual(self.cli('guide', '--kind', 'exception-instances')['text'],
                         (harness.REPO / 'docs/source-exception-instances.md').read_text())
        self.assertEqual(actual['value']['private_task_native_module_image_plan'], 'nex.private-task-modules/2')
        self.assertEqual(self.cli('guide', '--kind', 'exception-frontiers')['text'],
                         (harness.REPO / 'docs/source-exception-frontiers.md').read_text())
        self.assertEqual(self.cli('guide', '--kind', 'exception-modules')['text'],
                         (harness.REPO / 'docs/source-exception-modules.md').read_text())
        self.assertIs(actual['value']['private_task_native_host_typescript'], False)
        self.assertEqual(self.cli('guide', '--kind', 'exception-host')['text'],
                         (harness.REPO / 'docs/source-exception-host.md').read_text())
        self.assertEqual(actual['value']['private_task_native_debug_inspector'], 'inspect-private-task')
        self.assertEqual(self.cli('guide', '--kind', 'exception-task-watch')['text'],
                         (harness.REPO / 'docs/source-exception-task-watch.md').read_text())
        self.assertEqual(self.cli('guide', '--kind', 'exception-task-lldb')['text'],
                         (harness.REPO / 'docs/source-exception-task-lldb.md').read_text())
        self.assertEqual(self.cli('guide', '--kind', 'exception-task-debug')['text'],
                         (harness.REPO / 'docs/source-exception-task-debug.md').read_text())
        self.assertEqual(self.cli('guide', '--kind', 'exception-task-control-profile')['text'],
                         (harness.REPO / 'docs/source-exception-task-control-profile.md').read_text())
        self.assertEqual(self.cli('guide', '--kind', 'exception-native-tasks')['text'],
                         (harness.REPO / 'docs/source-exception-native-tasks.md').read_text())
        self.assertIs(actual['value']['private_task_typescript'], True)
        self.assertIs(actual['value']['private_task_lifetime_analysis'], True)
        self.assertIs(actual['value']['private_task_ir'], True)
        self.assertIs(actual['value']['private_task_ir_compiled_native_execution'], False)
        self.assertEqual(self.cli('guide', '--kind', 'exception-task-ir')['text'],
                         (harness.REPO / 'docs/source-exception-task-ir.md').read_text())
        self.assertIs(actual['value']['private_task_lifetime_complete_region_inference'], False)
        self.assertEqual(self.cli('guide', '--kind', 'exception-lifetimes')['text'],
                         (harness.REPO / 'docs/source-exception-lifetimes.md').read_text())
        self.assertEqual(actual['value']['private_task_typescript_emitter'], 'emitSourceExceptionTasksPrototypeTypeScript')
        self.assertEqual(self.cli('guide', '--kind', 'exception-tasks-prototype')['text'],
                         (harness.REPO / 'docs/source-exception-tasks-prototype.md').read_text())
        self.assertEqual(self.cli('guide', '--kind', 'exception-prototype')['text'],
                         (harness.REPO / 'docs/source-exceptions-prototype.md').read_text())
        self.assertFalse((self.root / '.nex').exists())

    def test_retained024_contextual_words_and_canonical_definitions(self):
        fixture = json.loads((harness.REPO / 'tests/fixtures/source-exceptions/retained-024.json').read_text())
        exported=harness.REPO/'tests/fixtures/source-exceptions/retained-024-graph.json'
        graph=json.loads(exported.read_text())
        nodes = {node['name']: {'hash': node['hash'], 'definition': node['definition']} for node in graph['nodes']}
        self.assertEqual(nodes, fixture['functions'])
        (self.root / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': '0.24', 'entry': 'main.nex'}))
        self.source(fixture['source'])
        self.assertEqual(self.cli('check',ok=False)['code'],'E_LANGUAGE_VERSION')
        plan=self.cli('migrate',exported,'--kind','plan')
        self.assertTrue(plan['origin_verified'] and plan['graph_read_only'])
        self.assertEqual(plan['origin_revision'],graph['revision'])
        self.assertEqual(plan['origin_language'],'0.24')
        self.assertFalse(plan['target_valid'])
        self.assertEqual(plan['target_diagnostic']['code'],'E_PARSE')
        self.assertFalse((self.root/'.nex').exists())

    def test_private_identity_cannot_enable_a_public_project_or_store(self):
        self.source('module x;fn main()->i64{return 42;}')
        for language in ('0.25', '0.25-prototype'):
            (self.root / 'nex.json').write_text(json.dumps({'schema': 'nex.project/1', 'language': language, 'entry': 'main.nex'}))
            rejected = self.cli('check', ok=False)
            self.assertEqual(rejected['code'], 'E_LANGUAGE_VERSION')
            self.assertFalse((self.root / '.nex').exists())
        (self.root / 'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':harness.CURRENT_LANGUAGE,'entry':'main.nex'}))
        self.assertTrue(self.cli('check')['ok'])


if __name__ == '__main__':
    unittest.main()
