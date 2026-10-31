"""Public mobile artifact boundaries and URL-origin isolation."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('nex_mobile_project', ROOT / 'tools/mobile_project.py')
mobile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mobile)


class MobileProjects(unittest.TestCase):
    def test_api_origin_and_configured_asset_provenance(self):
        for value in ('https://api.example.test','https://localhost:9443','https://127.0.0.1:9443'):
            self.assertEqual(mobile.api_origin(value),value)
        for value in ('http://api.test','https://api.test/','https://a:b@api.test','https://api.test?q',
                      'https://api.test#hash','https://API.test','https://api.test:443','https://api.test:0',
                      'https://api.test:65536','https://api.test:0443','https://127.1','https://0x7f000001',
                      'https://api..test','https://-api.test','https://api.test\n','https://[::1]:9443'):
            with self.subTest(value=value),self.assertRaises(mobile.Failure) as caught:mobile.api_origin(value)
            self.assertEqual(caught.exception.code,'E_MOBILE_API')
        with tempfile.TemporaryDirectory() as directory:
            index=Path(directory)/'index.html';index.write_text('<html><head></head><body></body></html>', newline="\n")
            before=mobile.sha(index);receipt=mobile.configure_api(index,'https://api.test:9443')
            self.assertEqual(receipt['original_sha256'],before)
            self.assertEqual(receipt['configured_sha256'],mobile.sha(index))
            self.assertNotEqual(before,mobile.sha(index))
            self.assertIn('<meta name="nex-api-origin" content="https://api.test:9443">',index.read_text())
            with self.assertRaises(mobile.Failure):mobile.configure_api(index,'https://other.test')

    def test_real_url_policy_and_opaque_origins(self):
        result = subprocess.run([os.environ.get('NEX_NODE','node'), str(ROOT/'tests/url_policy.mjs'), str(ROOT/'web/urls.ts')],
                                capture_output=True,text=True,timeout=30)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_unsafe_native_identifiers_labels_and_platforms_rejected(self):
        for value in ('one','a.class','a.while','a.b; touch unsafe','dev.nex/../app','dev.nex-x','dev.\napp','dev.🧠','dev..app','Dev.nex'):
            with self.subTest(value=value), self.assertRaises(mobile.Failure) as caught:
                mobile.configuration(value,'NEX','both')
            self.assertEqual(caught.exception.code,'E_MOBILE_ID')
        for value in ('','  ','x\nname','x\x00name','\ud800','a'*81):
            with self.subTest(label=repr(value)), self.assertRaises(mobile.Failure) as caught:
                mobile.configuration('dev.nex.app',value,'ios')
            self.assertEqual(caught.exception.code,'E_MOBILE_NAME')
        with self.assertRaises(mobile.Failure):mobile.configuration('dev.nex.app','NEX','windows')
        self.assertEqual(mobile.configuration('dev.nex.app','NEX 🧠','both')['appName'],'NEX 🧠')

    def test_existing_and_symlink_outputs_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);output=root/'existing';output.mkdir();marker=output/'keep.txt';marker.write_text('keep', newline="\n")
            args=type('Args',(),dict(app_id='dev.nex.app',name='NEX',platform='ios',directory=str(output)))()
            with self.assertRaises(mobile.Failure) as caught:mobile.generate(args)
            self.assertEqual(caught.exception.code,'E_EXISTS');self.assertEqual(marker.read_text(),'keep')
            symlink=root/'link';symlink.symlink_to(output,target_is_directory=True);args.directory=str(symlink)
            with self.assertRaises(mobile.Failure) as caught:mobile.generate(args)
            self.assertEqual(caught.exception.code,'E_EXISTS');self.assertEqual(marker.read_text(),'keep')

    def test_offline_missing_and_tampered_frameworks_never_become_projects(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cache=root/'cache';cache.mkdir()
            for name in ('missing','tampered'):
                project=root/name;project.mkdir()
                if name=='tampered':
                    manifest=json.loads((ROOT/'mobile/ios-artifacts.json').read_text())
                    (cache/(manifest['artifacts'][0]['sha256']+'.zip')).write_bytes(b'changed native framework')
                with self.assertRaises(mobile.Failure) as caught:mobile.ios_artifacts(project,cache,True)
                self.assertEqual(caught.exception.code,'E_MOBILE_CACHE')
                self.assertFalse((project/'native-dependencies/capacitor-ios/Package.swift').exists())
                self.assertFalse(any(project.rglob('*.xcframework')))


if __name__ == '__main__':
    unittest.main(verbosity=2)
