"""Owned SDK fixtures exercise archive integrity and extraction boundaries."""
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location('sdk_archive', Path(__file__).resolve().parents[1]/'tools/sdk_archive.py')
archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)


class Archives(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex archive, % 🧠 ')
        self.root = Path(self.temp.name)
        self.sdk = self.root/'SDK'
        for name, value in [('bin/nex', b'owned executable'), ('include/header.h', b'owned header'),
                            ('notes, 🧠.txt', b'UTF-8 paths')]:
            path = self.sdk/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(value)
            path.chmod(0o755 if name == 'bin/nex' else 0o644)
        (self.sdk/'bin/compiler').symlink_to('nex')
        self.manifest = {'schema': 'nex.sdk-bundle/1', 'ok': True, 'acceptance_passed': False,
                         'toolchain': '0.33.0', 'language': '0.14', 'platform': 'macos', 'files': {}}
        for path in self.sdk.rglob('*'):
            if path.is_file() or path.is_symlink():
                name = str(path.relative_to(self.sdk))
                self.manifest['files'][name] = ({'symlink': str(path.readlink())} if path.is_symlink() else
                    {'sha256': archive.digest(path), 'bytes': path.stat().st_size,
                     'executable': bool(path.stat().st_mode & 0o111)})
        self.save()

    def tearDown(self):
        self.temp.cleanup()

    def save(self, value=None):
        path = self.sdk/archive.MANIFEST; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.manifest if value is None else value, ensure_ascii=False))

    def test_inventory_roundtrip_ignores_only_regular_python_caches(self):
        cache = self.sdk/'tools/__pycache__/module.cpython-39.pyc'
        cache.parent.mkdir(parents=True); cache.write_bytes(b'not a distribution input')
        result = archive.create(self.sdk, self.root/'sdk.tar.gz', 'nex-sdk-test')
        self.assertEqual(result['excluded_python_cache_files'], [str(cache.relative_to(self.sdk))])
        restored = archive.restore(result['path'], self.root/'restored', result['sha256'])
        self.assertEqual((restored/'bin/nex').read_bytes(), b'owned executable')
        self.assertEqual((restored/'notes, 🧠.txt').read_bytes(), b'UTF-8 paths')
        self.assertEqual(str((restored/'bin/compiler').readlink()), 'nex')
        self.assertFalse((restored/'tools/__pycache__').exists())
        self.assertEqual(archive.inventory(restored)[0], self.manifest)
        (self.sdk/'unexpected').write_text('must not ship')
        with self.assertRaisesRegex(ValueError, 'unmanifested'):
            archive.inventory(self.sdk)

    def test_normalized_archive_is_identical_after_mtime_changes(self):
        first = archive.create(self.sdk, self.root/'first.tar.gz', 'nex-sdk-test')
        for path in self.sdk.rglob('*'):
            if not path.is_symlink(): os.utime(path, (123456789, 123456789))
        second = archive.create(self.sdk, self.root/'second.tar.gz', 'nex-sdk-test')
        self.assertEqual(first['sha256'], second['sha256'])
        with tarfile.open(first['path']) as package:
            for item in package:
                self.assertEqual((item.uid, item.gid, item.mtime, item.uname, item.gname), (0, 0, 0, '', ''))
                self.assertFalse(item.mode & 0o7000)

    def test_hash_modes_sizes_and_duplicate_manifest_keys_fail(self):
        for key, value in [('sha256', '0'*64), ('bytes', 1), ('executable', False), ('bytes', True)]:
            manifest = copy.deepcopy(self.manifest); manifest['files']['bin/nex'][key] = value; self.save(manifest)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError): archive.inventory(self.sdk)
        self.save()
        path = self.sdk/archive.MANIFEST
        path.write_text(path.read_text().replace('"ok": true', '"ok": false, "ok": true'))
        with self.assertRaisesRegex(ValueError, 'duplicate'): archive.inventory(self.sdk)

    def test_paths_privilege_bits_and_links_cannot_escape_inventory(self):
        for name in ['../outside', '/outside', 'bin/./nex', 'bin//nex', 'bin\\nex']:
            manifest = copy.deepcopy(self.manifest); manifest['files'][name] = manifest['files'].pop('bin/nex'); self.save(manifest)
            with self.subTest(name=name), self.assertRaises(ValueError): archive.inventory(self.sdk)
        self.save()
        path = self.sdk/'bin/nex'; path.chmod(0o4755)
        # Some temporary filesystems discard setuid on chmod. The tar test
        # below checks privileged metadata independently of that host policy.
        if path.stat().st_mode & 0o4000:
            with self.assertRaisesRegex(ValueError, 'privilege'): archive.inventory(self.sdk)
        path.chmod(0o755)
        alias = self.sdk/'bin/compiler'; alias.unlink(); alias.symlink_to('../../outside')
        manifest = copy.deepcopy(self.manifest); manifest['files']['bin/compiler']['symlink'] = '../../outside'; self.save(manifest)
        with self.assertRaises(ValueError): archive.inventory(self.sdk)

    def test_manifest_symlink_ancestor_is_rejected_before_read(self):
        (self.sdk/archive.MANIFEST).unlink(); (self.sdk/'share/nex').rmdir(); (self.sdk/'share').rmdir()
        (self.sdk/'share').symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, 'manifest has a symlink ancestor'):
            archive.inventory(self.sdk)

    def malicious(self, rows):
        path = self.root/'malicious.tar.gz'
        with tarfile.open(path, 'w:gz') as package:
            for name, kind, target in rows:
                item = tarfile.TarInfo(name); item.type = kind
                if kind == tarfile.SYMTYPE: item.linkname = target
                data = b'{}' if kind == tarfile.REGTYPE else b''
                item.size = len(data); package.addfile(item, io.BytesIO(data) if data else None)
        return path

    def test_archive_structural_attacks_fail_before_destination_creation(self):
        baseline = [('SDK', tarfile.DIRTYPE, ''), ('SDK/share', tarfile.DIRTYPE, ''),
                    ('SDK/share/nex', tarfile.DIRTYPE, ''), ('SDK/'+archive.MANIFEST, tarfile.REGTYPE, '')]
        attacks = [[('../outside', tarfile.REGTYPE, '')], [('/outside', tarfile.REGTYPE, '')],
                   [('SDK/link', tarfile.SYMTYPE, '../../outside')],
                   [('SDK/share', tarfile.REGTYPE, '')], [('SDK/hard', tarfile.LNKTYPE, '')],
                   [('SDK/link', tarfile.SYMTYPE, 'share'), ('SDK/link/payload', tarfile.REGTYPE, '')],
                   [('SDK/a', tarfile.SYMTYPE, 'b'), ('SDK/b', tarfile.SYMTYPE, 'a')],
                   [('SDK/link', tarfile.SYMTYPE, 'missing')]]
        for index, extra in enumerate(attacks):
            path = self.malicious(baseline+extra); destination = self.root/('extract-'+str(index))
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                archive.restore(path, destination, archive.digest(path))
            self.assertFalse(destination.exists())
            self.assertFalse((self.root/'outside').exists())

    def test_archive_checksum_and_existing_destinations_are_preserved(self):
        result = archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            archive.restore(result['path'], self.root/'new', '0'*64)
        destination = self.root/'existing'; destination.mkdir(); (destination/'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError, 'must be new'):
            archive.restore(result['path'], destination, result['sha256'])
        self.assertEqual((destination/'keep').read_text(), 'keep')
        with self.assertRaises(FileExistsError): archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')

    def test_privileged_archive_header_is_rejected_before_extraction(self):
        original = archive.create(self.sdk, self.root/'sdk.tar.gz', 'SDK')
        changed = self.root/'privileged.tar.gz'
        with tarfile.open(original['path']) as source, tarfile.open(changed, 'w:gz') as output:
            for item in source:
                data = source.extractfile(item) if item.isfile() else None
                if item.name == 'SDK/bin/nex': item.mode |= 0o4000
                output.addfile(item, data)
        with self.assertRaisesRegex(ValueError, 'unsafe SDK archive metadata'):
            archive.restore(changed, self.root/'restored', archive.digest(changed))
        self.assertFalse((self.root/'restored').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
