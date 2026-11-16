#!/usr/bin/env python3
"""Offline checks for dependency-build failure reporting; no Docker required."""
import contextlib
import io
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools/linux'))
from check import prepare_image
from debugger_packages import prepare,selected,NAMES


class PreparationTests(unittest.TestCase):
    def package_lock(self):
        version='1:23.1.6-test';payloads={};packages={}
        for name in NAMES:
            filename='pool/main/l/llvm-toolchain-23/'+name+'_test_amd64.deb';data=name.encode();payloads[filename]=data
            packages[name]={'Filename':filename,'Version':version,'Architecture':'amd64','SHA256':hashlib.sha256(data).hexdigest(),'Size':str(len(data))}
        return {'schema':'nex.linux-debugger-packages/1','apt_version':version,'repository':'https://apt.llvm.org/noble/','packages':{'amd64':packages}},payloads

    def test_package_cache_download_then_offline_restore(self):
        lock,payloads=self.package_lock();requests=[]
        def open_package(url,timeout):requests.append(url);return io.BytesIO(payloads[url.removeprefix(lock['repository'])])
        with tempfile.TemporaryDirectory(prefix='nex-debugger-cache-')as folder:
            first=prepare(lock,folder,'amd64',opener=open_package)
            self.assertEqual(len(requests),5);self.assertTrue(all(not row['cached']for row in first['packages']))
            def offline(*args,**kwargs):raise AssertionError('cache restore accessed network')
            second=prepare(lock,folder,'amd64',opener=offline,fetch=False)
            self.assertTrue(all(row['cached']for row in second['packages']))
            self.assertTrue(all(Path(row['path']).stat().st_mode&0o444==0o444 for row in second['packages']))

    def test_differing_download_does_not_publish_a_package(self):
        lock,_=self.package_lock()
        with tempfile.TemporaryDirectory(prefix='nex-debugger-difference-')as folder:
            with self.assertRaises(ValueError):prepare(lock,folder,'amd64',opener=lambda *a,**k:io.BytesIO(b'wrong'))
            self.assertEqual(list((Path(folder)/'amd64').iterdir()),[])

    def test_install_input_requires_every_matching_file(self):
        lock,_=self.package_lock()
        with tempfile.TemporaryDirectory(prefix='nex-debugger-missing-')as folder:
            with self.assertRaises(ValueError):prepare(lock,folder,'amd64',fetch=False)
        root=Path(__file__).resolve().parents[1]
        actual=json.loads((root/'tools/linux/debugger-packages.json').read_text())
        for arch in ('amd64','arm64'):self.assertEqual(set(selected(actual,arch)),NAMES)
        self.assertIn('ARG LLDB_APT_VERSION='+actual['apt_version'],(root/'tools/linux/Dockerfile').read_text())

    def test_success_keeps_log_without_failure_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix='nex-image-log-') as folder:
            path = Path(folder) / 'image.log'
            console = io.StringIO()
            with contextlib.redirect_stderr(console):
                prepare_image([sys.executable, '-I', '-B', '-c', 'print("prepared")'], path)
            self.assertEqual(path.read_bytes(), b'prepared\n')
            self.assertEqual(console.getvalue(), '')

    def test_failure_preserves_exit_code_complete_bytes_and_bounded_diagnostic(self):
        with tempfile.TemporaryDirectory(prefix='nex-image-log-') as folder:
            path = Path(folder) / 'image.log'
            console = io.StringIO()
            command = [sys.executable, '-I', '-B', '-c',
                       'import sys;sys.stdout.buffer.write(b"x"*100000+b"\\xff\\nupstream connection failed\\n");sys.exit(7)']
            with contextlib.redirect_stderr(console), self.assertRaises(subprocess.CalledProcessError) as failure:
                prepare_image(command, path)
            self.assertEqual(failure.exception.returncode, 7)
            self.assertEqual(failure.exception.cmd, command)
            self.assertEqual(path.read_bytes(), b'x'*100000+b'\xff\nupstream connection failed\n')
            self.assertIn('NEX checks have not started', console.getvalue())
            self.assertIn('upstream connection failed', console.getvalue())
            self.assertIn('\ufffd', console.getvalue())
            self.assertLess(len(console.getvalue()), 17000)


if __name__ == '__main__':
    unittest.main()
