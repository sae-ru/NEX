"""Checked HTTP value semantics and actual model-facing discovery."""
import json
import shutil
import unittest
import support as harness


class HTTPClientLibrary(harness.ToolchainCase):
    def test_actual_compiler_pack_and_guide_agree_without_opening_a_graph(self):
        pack = json.loads((harness.REPO / 'llm/language-pack.json').read_text())
        capability = self.cli('describe', '--field', 'http_client_provider')
        self.assertEqual(capability['value'], pack['http_client_provider'])
        self.assertEqual(capability['language'], harness.CURRENT_LANGUAGE)
        self.assertIs(capability['value']['source_ABI_changed'], False)
        self.assertIs(capability['value']['native_provider_process_sandbox'], False)
        self.assertIs(capability['value']['public_URL_private_IP_filter'], False)
        guide = self.cli('guide', '--kind', 'http-client')
        self.assertEqual(guide['kind'], 'http-client')
        self.assertFalse((self.root / '.nex').exists())

    def test_portable_HTTP_values_agree_across_backends(self):
        library = (harness.REPO / 'lib/http_client.nex').read_text()
        library = library.replace('module std::http_client;', 'module http_validation;', 1)
        library = library.replace('test fn ', 'fn ')
        self.source(library + '\nfn main()->unit !{io}{portable_request_and_response();print(42);}\n'
                    'test fn boundaries()->unit{portable_request_and_response();}\n')
        self.assertEqual(self.cli('eval')['stdout'], '42\n')
        for profile in ('debug', 'release'):
            self.assertEqual(self.cli('run', '--profile', profile)['stdout'], '42\n')
        self.assertIsNotNone(shutil.which('node'), 'Node is required for actual TypeScript agreement')
        self.cli('test', '--target', 'web')


if __name__ == '__main__':
    unittest.main()
