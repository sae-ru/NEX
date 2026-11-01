"""Reviewed vendor notices must survive packaging and captured task inputs."""
import importlib.util
from pathlib import Path
import shutil
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('acceptance',ROOT/'tools/sdk_acceptance.py')
acceptance=importlib.util.module_from_spec(spec);spec.loader.exec_module(acceptance)

class Notices(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nex-reviewed-notices-');self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name).resolve();self.sdk=self.root/'sdk';self.sdk.mkdir()
        self.vendor=self.root/'vendor';self.vendor.mkdir();self.crypto=self.vendor/'libcrypto.so.3';self.crypto.write_bytes(b'private vendor fixture')
        self.license=self.vendor/'LICENSE';self.license.write_text('Complete independent test fixture notice.\n', newline="\n")
        self.component={'name':'vendor','version':'1','url':'https://example.invalid/vendor',
                        'roots':[str(self.crypto)],'license_files':[str(self.license)]}

    def test_explicit_vendor_precedes_automatic_debian_discovery(self):
        class Forbidden:
            def __init__(self,*args):raise AssertionError('Debian ownership queried for explicitly reviewed vendor')
        with patch.object(acceptance.platform,'system',return_value='Linux'),patch.dict(sys.modules,{'sdk_bundle':types.SimpleNamespace(DebianNotices=Forbidden)}):
            self.assertEqual(acceptance.external_crypto_components(self.sdk,self.crypto,[self.component]),[self.component])

    def test_directory_and_symlink_roots_resolve_to_actual_library(self):
        alias=self.root/'crypto-alias';alias.symlink_to(self.crypto)
        component={**self.component,'roots':[str(self.vendor)]}
        self.assertEqual(acceptance.external_crypto_components(self.sdk,alias,[component]),[component])

    def test_sibling_with_same_textual_prefix_does_not_gain_coverage(self):
        other=self.root/'vendor-other';other.mkdir();library=other/'libcrypto.so.3';library.write_bytes(b'other')
        class Unmanaged:
            def __init__(self,*args):pass
            def component(self,path):raise ValueError('unmanaged exact vendor')
        with patch.object(acceptance.platform,'system',return_value='Linux'),patch.dict(sys.modules,{'sdk_bundle':types.SimpleNamespace(DebianNotices=Unmanaged)}):
            with self.assertRaisesRegex(ValueError,'unmanaged exact vendor'):
                acceptance.external_crypto_components(self.sdk,library,[{**self.component,'roots':[str(self.vendor)]}])

    def test_identical_relocated_license_deduplicates_without_losing_local_path(self):
        copied=self.root/'copied-notice';shutil.copyfile(self.license,copied)
        local={**self.component,'license_files':[str(copied)]}
        merged=acceptance.merge_notice_components([self.component],[local]);self.assertEqual(merged,[local])
        merged[0]['roots'].clear();self.assertEqual(self.component['roots'],[str(self.crypto)])

    def test_same_name_with_different_version_or_authority_is_rejected(self):
        for field,value in [('version','2'),('roots',[str(self.vendor)])]:
            with self.subTest(field=field),self.assertRaisesRegex(RuntimeError,'conflicting package notice component: vendor'):
                acceptance.merge_notice_components([self.component],[{**self.component,field:value}])

    def test_same_name_with_different_license_bytes_is_rejected(self):
        other=self.root/'different-license';other.write_text('Different notice.\n', newline="\n")
        with self.assertRaisesRegex(RuntimeError,'conflicting package notice component: vendor'):
            acceptance.merge_notice_components([self.component],[{**self.component,'license_files':[str(other)]}])

    def test_all_reviewed_dependencies_survive_fixture_merge(self):
        dependency={**self.component,'name':'second-vendor'}
        fixture={**self.component,'name':'fixture'}
        result=acceptance.merge_notice_components([fixture],[self.component,dependency])
        self.assertEqual([c['name'] for c in result],['fixture','vendor','second-vendor'])

    def test_existing_sdk_owned_crypto_keeps_inventory_contract(self):
        internal=self.sdk/'crypto';internal.write_bytes(b'bundled')
        self.assertEqual(acceptance.external_crypto_components(self.sdk,internal),[])

    def test_project_capture_owns_complete_notice_bytes(self):
        project=self.root/'project';project.mkdir()
        captured=acceptance.project_notice_components(project,[self.component])
        self.assertEqual(captured[0]['roots'],self.component['roots'])
        local=project/captured[0]['license_files'][0]
        self.assertTrue(local.is_relative_to(project));self.assertEqual(local.read_bytes(),self.license.read_bytes())
        self.assertFalse(Path(captured[0]['license_files'][0]).is_absolute())
        self.license.unlink();self.assertEqual(local.read_text(),'Complete independent test fixture notice.\n')
        with self.assertRaises(FileExistsError):acceptance.project_notice_components(project,[])

if __name__=='__main__':unittest.main()
