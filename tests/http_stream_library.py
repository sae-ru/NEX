"""Actual discovery and portable stream values across NEX execution backends."""
import json
import shutil
import unittest
import support as harness


class HTTPStreamLibrary(harness.ToolchainCase):
    def test_compiler_pack_and_guide_agree(self):
        pack = json.loads((harness.REPO / 'llm/language-pack.json').read_text())
        capability = self.cli('describe', '--field', 'http_response_streams')
        self.assertEqual(capability['value'], pack['http_response_streams'])
        self.assertEqual(capability['language'], '0.24')
        self.assertIs(capability['value']['source_ABI_changed'], False)
        self.assertIs(capability['value']['installed_SDK_accepted'], False)
        self.assertEqual(self.cli('guide', '--kind', 'http-stream')['kind'], 'http-stream')
        self.assertFalse((self.root / '.nex').exists())

    def test_portable_request_and_chunk_values_agree(self):
        for name in ('http_client.nex', 'http_stream.nex'):
            shutil.copy2(harness.REPO / 'lib' / name, self.root / name)
        self.source('''module portable_stream;
import "./http_stream.nex" as hs;
fn values()->unit{
 let request:hs::Request=hs::request("backend","GET","https://example.test/",utf8_bytes("abc"),1048576,3000);
 assert(is_ok(hs::validate(request)));
 assert(request.body==utf8_bytes("abc")&&request.protocol=="auto"&&request.total_limit==1048576);
 let part:hs::Chunk=hs::Chunk(unwrap(bytes([0,128,255])),false);
 let copy:hs::Chunk=part;
 assert(copy.data==unwrap(bytes([0,128,255]))&&!copy.done);
}
fn main()->unit !{io}{values();print(42);}
test fn portable()->unit{values();}
''')
        self.assertEqual(self.cli('eval')['stdout'], '42\n')
        for profile in ('debug', 'release'):
            self.assertEqual(self.cli('run', '--profile', profile)['stdout'], '42\n')
        self.assertIsNotNone(shutil.which('node'), 'Node is required for actual TypeScript agreement')
        self.cli('test', '--target', 'web')


if __name__ == '__main__':
    unittest.main()
