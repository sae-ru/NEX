"""Real kernel ownership and PID-reuse guards for Windows workload fixtures."""
import ctypes as C
from ctypes import wintypes as W
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import host_fixture


@unittest.skipUnless(os.name=='nt','native Windows process ownership')
class WindowsWorkloadOwnership(unittest.TestCase):
    def test_recorded_birth_and_owned_job_are_required_on_the_held_handle(self):
        self.assertIsNone(host_fixture._WINDOWS_WORKLOAD_JOB)
        kernel=C.WinDLL('kernel32',use_last_error=True)
        kernel.GetProcessTimes.argtypes=[W.HANDLE,*([C.POINTER(W.FILETIME)]*4)]
        kernel.GetProcessTimes.restype=W.BOOL
        kernel.IsProcessInJob.argtypes=[W.HANDLE,W.HANDLE,C.POINTER(W.BOOL)]
        kernel.IsProcessInJob.restype=W.BOOL

        def birth(peer):
            created,exited,system,user=(W.FILETIME()for _ in range(4))
            self.assertTrue(kernel.GetProcessTimes(peer._handle,C.byref(created),
                C.byref(exited),C.byref(system),C.byref(user)))
            return (created.dwHighDateTime<<32)|created.dwLowDateTime

        def member(peer,job):
            found=W.BOOL()
            self.assertTrue(kernel.IsProcessInJob(peer._handle,job,C.byref(found)))
            return bool(found.value)

        peers=[]
        def peer():
            child=subprocess.Popen([sys.executable,'-u','-B','-c',
                'import sys;sys.stdin.buffer.read(1)'],stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                creationflags=subprocess.CREATE_NO_WINDOW)
            peers.append(child);return child

        try:
            # This peer predates the new unnamed Job. Under an outer observer
            # it still belongs to a Job, so testing merely "any Job" is wrong.
            outside=peer();outside_birth=birth(outside)
            outside_in_any_job=member(outside,None)
            job=host_fixture._windows_workload_job()
            first,second=peer(),peer()
            self.assertFalse(member(outside,job))
            self.assertTrue(member(first,job));self.assertTrue(member(second,job))
            first_birth,second_birth=birth(first),birth(second)
            with tempfile.TemporaryDirectory(prefix='NEX workload ownership 🧠 ')as directory:
                record=Path(directory)/'processes'
                # Old PID-only records cannot authorize any termination.
                record.write_text(f'{first.pid} {os.getpid()} {second.pid}\n')
                with self.assertRaises(ValueError):
                    host_fixture.windows_live_descendants(record,terminate=True)
                # A correct identity outside our Job and a reused/stale birth
                # inside it must both be ignored without signalling either.
                record.write_text(f'{outside.pid} {os.getpid()} {second.pid} '
                                  f'{outside_birth} {second_birth+1}\n')
                self.assertEqual(host_fixture.windows_live_descendants(record,terminate=True),[])
                self.assertIsNone(outside.poll());self.assertIsNone(second.poll())
                record.write_text(f'{first.pid} {os.getpid()} {second.pid} '
                                  f'{first_birth} {second_birth}\n')
                expected=[first.pid,second.pid]
                self.assertEqual(host_fixture.windows_live_descendants(record),expected)
                self.assertEqual(host_fixture.windows_live_descendants(record,terminate=True),expected)
                self.assertEqual(first.wait(timeout=5),137)
                self.assertEqual(second.wait(timeout=5),137)
                self.assertIsNone(outside.poll())
            outside.communicate(input=b'x',timeout=5)
            self.assertEqual(outside.returncode,0)
            print(json.dumps({'schema':'nex.windows-workload-ownership/1','ok':True,
                'outside_peer_in_any_job':outside_in_any_job,
                'outside_peer_in_owned_job':False,'outside_peer_cooperative_exit':0,
                'legacy_PID_only_record_rejected':True,'stale_creation_time_ignored':True,
                'only_held_matching_owned_peers_terminated':True,
                'existing_applications_queried_or_modified':False}))
        finally:
            for child in peers:
                if child.poll()is None:child.terminate()
                child.communicate(timeout=5)


if __name__=='__main__':unittest.main(verbosity=2)
