"""Real Windows nonregular fixtures in long directories and no-follow readers."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import importlib.util
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / 'tools/windows_files.py'
NATIVE_PROBE = None


@unittest.skipUnless(os.name == 'nt', 'requires actual Windows filesystem handles')
class NonregularFixtures(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location('nex_windows_files_test', MODULE)
        cls.files = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.files)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nex file fixture ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_long_parent_keeps_real_socket_and_regular_file_checks(self):
        parent = self.root / ('long directory % 🧠 ' + 'a' * 48) / 'nested'
        parent.mkdir(parents=True)
        path = parent / 'policy-pipe'
        self.assertGreaterEqual(len(os.fsencode(path)), 108)
        before = os.getcwd()
        self.files.nonregular_fixture(path)
        self.assertEqual(os.getcwd(), before)
        self.assertTrue(os.path.lexists(path))
        kernel = C.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p,
                                      W.DWORD, W.DWORD, W.HANDLE]
        kernel.CreateFileW.restype = W.HANDLE
        kernel.CloseHandle.argtypes = [W.HANDLE]
        kernel.GetFileInformationByHandleEx.argtypes = [W.HANDLE, C.c_int,
                                                        C.c_void_p, W.DWORD]
        kernel.GetFileInformationByHandleEx.restype = W.BOOL
        handle = kernel.CreateFileW(str(path), 0, 7, None, 3, 0x02200000, None)
        self.assertNotEqual(handle, C.c_void_p(-1).value)
        try:
            attributes = (W.DWORD * 2)()
            self.assertTrue(kernel.GetFileInformationByHandleEx(
                handle, 9, attributes, C.sizeof(attributes)))
            self.assertTrue(attributes[0] & 0x400)
            self.assertEqual(attributes[1], 0x80000023)  # IO_REPARSE_TAG_AF_UNIX
        finally:
            kernel.CloseHandle(handle)
        for reader in (self.files.regular, self.files.open_regular_fd):
            with self.subTest(reader=reader.__name__):
                with self.assertRaisesRegex(ValueError, 'regular'):
                    reader(path, 64)
        regular = parent / 'regular file'
        regular.write_bytes(b'42')
        self.assertEqual(self.files.regular(regular, 64), b'42')
        descriptor = self.files.open_regular_fd(regular, 64)
        try:
            self.assertEqual(os.read(descriptor, 2), b'42')
        finally:
            os.close(descriptor)

    def test_existing_file_is_preserved(self):
        path = self.root / 'existing file'
        path.write_bytes(b'keep')
        with self.assertRaises(FileExistsError):
            self.files.nonregular_fixture(path)
        self.assertEqual(path.read_bytes(), b'keep')

    def test_native_name_limit_is_rejected_without_creating_a_file(self):
        path = self.root / ('x' * 108)
        with self.assertRaisesRegex(ValueError, 'name exceeds native limit'):
            self.files.nonregular_fixture(path)
        self.assertFalse(os.path.lexists(path))

    def test_native_resource_checks_keep_real_socket_under_long_unicode_temp(self):
        if NATIVE_PROBE is None:
            self.skipTest('select the native resource probe with --native-probe')
        parent = self.root / ('native long directory % 🧠 ' + 'a' * 64)
        parent.mkdir()
        self.assertGreaterEqual(len(os.fsencode(parent)), 108)
        before = os.getcwd()
        result = subprocess.run([str(NATIVE_PROBE)], env={**os.environ, 'TMP': str(parent),
            'TEMP': str(parent)}, capture_output=True, text=True, encoding='utf-8', timeout=30)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS stream path and nonregular rejection without truncation', result.stdout)
        self.assertIn('resource ownership and streaming files:', result.stdout)
        self.assertEqual(os.getcwd(), before)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module', type=Path, default=MODULE)
    parser.add_argument('--native-probe', type=Path)
    args, remaining = parser.parse_known_args()
    MODULE = args.module.resolve(strict=True)
    NATIVE_PROBE = args.native_probe.resolve(strict=True) if args.native_probe else None
    unittest.main(argv=[sys.argv[0], *remaining])
